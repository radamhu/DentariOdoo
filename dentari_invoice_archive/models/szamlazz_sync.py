"""
`dentari.szamlazz.sync` -- orchestrates szamlazz_client.query_invoice +
find_or_create_partner + attach_pdf into one idempotent "archive this
invoice number as a draft account.move" operation, plus a cron-safe entry
point that probes sequential invoice numbers and never lets an exception
escape (any failure is recorded on the record's own last_run_* fields
instead, so a human can see it in the sync config form rather than only in
the server log).
"""
import logging
import re

from odoo import fields, models
from odoo.exceptions import UserError

from .szamlazz_client import attach_pdf, find_or_create_partner, query_invoice

_logger = logging.getLogger(__name__)


class SzamlazzSync(models.Model):
    _name = 'dentari.szamlazz.sync'
    _description = 'Számlázz.hu szinkronizálás'

    last_synced_number = fields.Char(string='Utolsó szinkronizált sorszám')
    last_run = fields.Datetime(string='Utolsó futás')
    last_run_status = fields.Selection(
        [('ok', 'Sikeres'), ('error', 'Hiba'), ('never', 'Még nem futott')],
        default='never', string='Állapot',
    )
    last_run_message = fields.Text(string='Üzenet')
    last_run_count = fields.Integer(string='Szinkronizált számlák száma (utolsó futás)')

    def _get_agent_key(self):
        return self.env['ir.config_parameter'].sudo().get_param(
            'dentari_invoice_archive.szamlazz_agent_key',
        )

    def _batch_size(self):
        return int(self.env['ir.config_parameter'].sudo().get_param(
            'dentari_invoice_archive.sync_batch_size', default='20',
        ))

    def _sync_one(self, invoice_number):
        """Fetch, parse, and archive one invoice by number. Idempotent:
        returns the existing move untouched if already archived."""
        self.ensure_one()
        existing = self.env['account.move'].search([
            ('szamlazz_invoice_number', '=', invoice_number),
        ], limit=1)
        if existing:
            return existing

        agent_key = self._get_agent_key()
        parsed, pdf_bytes = query_invoice(agent_key, invoice_number)

        partner = find_or_create_partner(self.env, parsed)
        income_account = self._archive_income_account()
        tax = self._matching_sale_tax(parsed)
        move = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': partner.id,
            'invoice_source': 'szamlazz_archive',
            'szamlazz_invoice_number': parsed['invoice_number'],
            'invoice_date': parsed.get('issue_date'),
            'currency_id': self._currency_id(parsed.get('currency')),
            'invoice_line_ids': [(0, 0, {
                'name': f"Számlázz.hu archívum — {parsed['invoice_number']}",
                'account_id': income_account.id,
                'quantity': 1,
                'price_unit': parsed.get('net_total', 0.0),
                'tax_ids': [(6, 0, tax.ids)] if tax else False,
            })],
        })

        if parsed.get('is_cancelled'):
            move.button_cancel()

        if pdf_bytes:
            attach_pdf(self.env, move, pdf_bytes, f"{parsed['invoice_number']}.pdf")

        return move

    def _currency_id(self, currency_code):
        if not currency_code:
            return self.env.company.currency_id.id
        currency = self.env['res.currency'].search([('name', '=', currency_code)], limit=1)
        return currency.id if currency else self.env.company.currency_id.id

    def _archive_income_account(self):
        """account.move.line.account_id is required -- pick any income
        account for this company. Which one is cosmetic: these moves are
        never posted, so no real ledger is affected by the choice."""
        account = self.env['account.account'].search([
            ('account_type', '=', 'income'),
            ('company_id', '=', self.env.company.id),
        ], limit=1)
        if not account:
            raise UserError(
                'Nincs elérhető bevétel főkönyvi számla (account_type=income) '
                'az archívum sorokhoz -- vegyél fel legalább egyet.'
            )
        return account

    def _matching_sale_tax(self, parsed):
        """Find a sale tax matching the invoice's real afakulcs rate
        (parsed['vat_rate'], confirmed live in the Phase 0 spike -- not a
        ratio derived from totals, which szamlazz.hu already gives us
        directly). For this account's common case (AAM/VAT-exempt,
        vat_rate=0.0), no tax should apply at all -- an explicit 0% sale
        tax, if one exists, is still used so the line shows *something*
        rather than looking untaxed by omission; if none exists, the line
        is created with no tax, which for a 0% rate changes nothing about
        amount_tax (it's correctly 0 either way)."""
        rate = parsed.get('vat_rate')
        if rate is None:
            return self.env['account.tax']
        return self.env['account.tax'].search([
            ('type_tax_use', '=', 'sale'),
            ('amount', '=', rate),
            ('company_id', '=', self.env.company.id),
        ], limit=1)

    def _next_candidate_number(self):
        self.ensure_one()
        if self.last_synced_number:
            return self._increment_number(self.last_synced_number)
        return self.env['ir.config_parameter'].sudo().get_param(
            'dentari_invoice_archive.first_invoice_number', default='',
        )

    def _increment_number(self, invoice_number):
        """Increment the trailing numeric part of an invoice number string,
        e.g. 'E-2026-0042' -> 'E-2026-0043'. Only valid if Task 1 confirmed
        sequential numbering (spec Phase 0 Q2) -- otherwise this whole
        probing approach is replaced by the CSV-import path noted there."""
        match = re.match(r'^(.*?)(\d+)$', invoice_number)
        if not match:
            return invoice_number
        prefix, digits = match.groups()
        return f'{prefix}{str(int(digits) + 1).zfill(len(digits))}'

    def _cron_sync_invoices(self):
        """ir.cron entry point. Never lets an exception escape -- any
        failure (API error, auth failure, or -- until Task 1's findings
        make "not found" distinguishable from "real error" -- the normal
        end of the available sequence) aborts the current run and is
        recorded on this record rather than raised, so a human can see it
        in the sync config form instead of only in the server log."""
        sync = self.search([], limit=1) or self.create({})
        synced_count = 0
        try:
            agent_key = sync._get_agent_key()
            if not agent_key:
                raise ValueError(
                    'SZAMLAZZ_AGENT_KEY nincs beállítva '
                    '(ir.config_parameter: dentari_invoice_archive.szamlazz_agent_key)'
                )

            next_number = sync._next_candidate_number()
            for _ in range(sync._batch_size()):
                move = sync._sync_one(next_number)
                if move:
                    synced_count += 1
                    sync.last_synced_number = next_number
                next_number = sync._increment_number(next_number)

            sync.write({
                'last_run': fields.Datetime.now(),
                'last_run_status': 'ok',
                'last_run_message': f'{synced_count} számla szinkronizálva.',
                'last_run_count': synced_count,
            })
        except Exception as exc:  # noqa: BLE001 -- cron must never raise
            _logger.exception('szamlazz sync failed')
            sync.write({
                'last_run': fields.Datetime.now(),
                'last_run_status': 'error',
                'last_run_message': str(exc),
                'last_run_count': synced_count,
            })

    def action_run_sync(self):
        self.ensure_one()
        self._cron_sync_invoices()
