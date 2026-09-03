from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..models.account_move import quick_expense_category_accounts

DEMO_EXPENSE_MARKER = 'DEMO-QUICK-EXPENSE'


class DentalQuickExpense(models.TransientModel):
    _name = 'dental.quick.expense'
    _description = 'Gyors kiadás rögzítése'

    date = fields.Date(
        string='Dátum', required=True, default=fields.Date.context_today,
    )
    partner_id = fields.Many2one(
        'res.partner', string='Szállító', required=True,
    )
    category_account_id = fields.Many2one(
        'account.account',
        string='Kategória',
        required=True,
        domain=lambda self: [('id', 'in', quick_expense_category_accounts(self.env).ids)],
    )
    description = fields.Char(string='Leírás', required=True)
    currency_id = fields.Many2one(
        'res.currency',
        default=lambda self: self.env.company.currency_id,
        required=True,
    )
    net_amount = fields.Monetary(
        string='Nettó összeg', required=True, currency_field='currency_id',
    )
    tax_id = fields.Many2one(
        'account.tax',
        string='ÁFA',
        required=True,
        domain=[('type_tax_use', '=', 'purchase')],
    )
    ref = fields.Char(string='Bizonylatszám')
    attachment_ids = fields.Many2many('ir.attachment', string='Bizonylat')

    def action_save(self):
        self.ensure_one()
        if not self.category_account_id.exists():
            raise UserError(_('A kiadás kategória nem található.'))

        move = self.env['account.move'].create({
            'move_type': 'in_invoice',
            'partner_id': self.partner_id.id,
            'invoice_date': self.date,
            'ref': self.ref,
            'invoice_line_ids': [(0, 0, {
                'account_id': self.category_account_id.id,
                'name': self.description,
                'quantity': 1,
                'price_unit': self.net_amount,
                'tax_ids': [(6, 0, [self.tax_id.id])],
            })],
        })

        if self.attachment_ids:
            self.attachment_ids.write({
                'res_model': 'account.move',
                'res_id': move.id,
            })

        action = self.env['ir.actions.act_window']._for_xml_id(
            'dental_quick_expense.action_dental_quick_expense_list'
        )
        action['domain'] = [('id', '=', move.id)]
        return action

    @api.model
    def _load_demo_expenses(self):
        """Idempotent demo-data seeder: two draft Vendor Bills per seeded
        category, spread across the last 6 months, so a fresh demo
        database's Kiadások list isn't empty. Uses the same creation
        shape as action_save() — no journal_id set explicitly, no
        auto-posting. Safe to call more than once (checks the marker
        ref first)."""
        Move = self.env['account.move']
        if Move.search_count([('ref', '=', DEMO_EXPENSE_MARKER)]):
            return

        partner = self.env['res.partner'].search(
            [('name', '=', 'Demo Kiadás Szállító')], limit=1,
        )
        if not partner:
            partner = self.env['res.partner'].create({
                'name': 'Demo Kiadás Szállító',
            })

        tax = self.env['account.tax'].search(
            [('type_tax_use', '=', 'purchase')], limit=1,
        )
        accounts = quick_expense_category_accounts(self.env)
        today = fields.Date.context_today(self)

        for i, account in enumerate(accounts):
            for month_offset in (i % 6, (i + 3) % 6):
                invoice_date = today - relativedelta(months=month_offset, days=i)
                Move.create({
                    'move_type': 'in_invoice',
                    'partner_id': partner.id,
                    'invoice_date': invoice_date,
                    'ref': DEMO_EXPENSE_MARKER,
                    'invoice_line_ids': [(0, 0, {
                        'account_id': account.id,
                        'name': f'Demo kiadás – {account.name}',
                        'quantity': 1,
                        'price_unit': 5000 + i * 500,
                        'tax_ids': [(6, 0, [tax.id])] if tax else False,
                    })],
                })
