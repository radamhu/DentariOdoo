from unittest.mock import patch

from odoo import fields
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.dentari_invoice_archive.models.szamlazz_client import InvoiceNotFound

QUERY = 'odoo.addons.dentari_invoice_archive.models.szamlazz_sync.query_invoice'
ATTACH = 'odoo.addons.dentari_invoice_archive.models.szamlazz_sync.attach_pdf'

PARSED_OK = {
    'invoice_number': 'E-2026-0042',
    'issue_date': '2026-10-01',
    'fulfillment_date': '2026-10-01',
    'net_total': 10000.0,
    'vat_total': 2700.0,
    'gross_total': 12700.0,
    'vat_rate': 27.0,
    'currency': 'HUF',
    'is_cancelled': False,
    'partner_name': 'Teszt Ügyfél Kft',
    'partner_tax_number': '12345678-1-42',
    'partner_zip': '1111',
    'partner_city': 'Budapest',
    'partner_address': 'Teszt utca 1.',
}


@tagged('post_install', '-at_install')
class TestSzamlazzSync(TransactionCase):

    def setUp(self):
        super().setUp()
        self.env['ir.config_parameter'].sudo().set_param(
            'dentari_invoice_archive.szamlazz_agent_key', 'fake-key-for-tests',
        )
        # Cron runs on a record with no last_synced_number fall back to this
        # parameter; without it the empty-start guard (correctly) fires first.
        self.env['ir.config_parameter'].sudo().set_param(
            'dentari_invoice_archive.first_invoice_number', 'E-2026-0042',
        )
        # A record of the test's own, distinct from the seeded singleton --
        # self.sync._cron_sync_invoices() must operate on THIS record.
        self.sync = self.env['dentari.szamlazz.sync'].create({})
        # PARSED_OK is net=10000, vat=2700 -- a 27% sale tax (standard HU
        # ÁFA rate) must exist for _sync_one to find and apply it; an income
        # account must exist for the line's required account_id. Neither is
        # guaranteed present on a bare test database, so create them
        # explicitly rather than assume demo Chart of Accounts data.
        self.sale_tax = self.env['account.tax'].search([
            ('type_tax_use', '=', 'sale'), ('amount', '=', 27),
        ], limit=1) or self.env['account.tax'].create({
            'name': 'Teszt ÁFA 27%',
            'amount': 27,
            'type_tax_use': 'sale',
        })
        # Odoo 18: account.account has company_ids (M2M), not company_id.
        self.income_account = self.env['account.account'].search([
            ('account_type', '=', 'income'),
            ('company_ids', 'in', self.env.company.id),
        ], limit=1) or self.env['account.account'].create({
            'name': 'Teszt árbevétel',
            'code': 'DIA9999',
            'account_type': 'income',
            'company_ids': [(6, 0, [self.env.company.id])],
        })

    @patch('odoo.addons.dentari_invoice_archive.models.szamlazz_sync.query_invoice')
    def test_sync_creates_draft_archived_move(self, mock_query):
        mock_query.return_value = (PARSED_OK, b'%PDF-1.4 fake')
        self.sync._sync_one('E-2026-0042')

        move = self.env['account.move'].search([
            ('szamlazz_invoice_number', '=', 'E-2026-0042'),
        ])
        self.assertEqual(len(move), 1)
        self.assertEqual(move.state, 'draft')
        self.assertEqual(move.invoice_source, 'szamlazz_archive')
        self.assertEqual(move.amount_total, 12700.0)

    @patch('odoo.addons.dentari_invoice_archive.models.szamlazz_sync.query_invoice')
    def test_sync_is_idempotent(self, mock_query):
        mock_query.return_value = (PARSED_OK, b'%PDF-1.4 fake')
        self.sync._sync_one('E-2026-0042')
        self.sync._sync_one('E-2026-0042')

        count = self.env['account.move'].search_count([
            ('szamlazz_invoice_number', '=', 'E-2026-0042'),
        ])
        self.assertEqual(count, 1)

    @patch('odoo.addons.dentari_invoice_archive.models.szamlazz_sync.query_invoice')
    def test_cancelled_invoice_marked_not_active_draft(self, mock_query):
        cancelled = dict(PARSED_OK, is_cancelled=True, invoice_number='E-2026-0043')
        mock_query.return_value = (cancelled, b'%PDF-1.4 fake')
        self.sync._sync_one('E-2026-0043')

        move = self.env['account.move'].search([
            ('szamlazz_invoice_number', '=', 'E-2026-0043'),
        ])
        self.assertEqual(move.state, 'cancel')

    @patch('odoo.addons.dentari_invoice_archive.models.szamlazz_sync.query_invoice')
    def test_pdf_failure_still_creates_move(self, mock_query):
        mock_query.return_value = (PARSED_OK, None)
        self.sync._sync_one('E-2026-0042')

        move = self.env['account.move'].search([
            ('szamlazz_invoice_number', '=', 'E-2026-0042'),
        ])
        self.assertEqual(len(move), 1)

    @patch('odoo.addons.dentari_invoice_archive.models.szamlazz_sync.query_invoice')
    def test_api_error_sets_error_status_without_raising(self, mock_query):
        import requests
        mock_query.side_effect = requests.exceptions.Timeout('boom')

        self.sync._cron_sync_invoices()  # must not raise

        self.assertEqual(self.sync.last_run_status, 'error')
        self.assertIn('boom', self.sync.last_run_message or '')

    @patch('odoo.addons.dentari_invoice_archive.models.szamlazz_sync.query_invoice')
    def test_missing_income_account_sets_error_status(self, mock_query):
        self.env['account.account'].search([
            ('account_type', '=', 'income'),
            ('company_ids', 'in', self.env.company.id),
        ]).write({'account_type': 'income_other'})
        mock_query.return_value = (PARSED_OK, b'%PDF-1.4 fake')

        self.sync._cron_sync_invoices()  # must not raise

        self.assertEqual(self.sync.last_run_status, 'error')
        self.assertIn('bevétel', self.sync.last_run_message or '')

    # --- archive fidelity (final review #7) ---

    @patch(QUERY)
    def test_fulfillment_date_stored_as_delivery_date(self, mock_query):
        parsed = dict(PARSED_OK, fulfillment_date='2026-09-28')
        mock_query.return_value = (parsed, None)
        move = self.sync._sync_one('E-2026-0042')
        self.assertEqual(fields.Date.to_string(move.delivery_date), '2026-09-28')
        self.assertEqual(fields.Date.to_string(move.invoice_date), '2026-10-01')

    def _mismatch_messages(self, move):
        return move.message_ids.filtered(lambda m: 'eltérnek' in (m.body or ''))

    @patch(QUERY)
    def test_matching_amounts_post_no_warning(self, mock_query):
        mock_query.return_value = (PARSED_OK, None)
        move = self.sync._sync_one('E-2026-0042')
        self.assertEqual(move.amount_tax, 2700.0)
        self.assertFalse(self._mismatch_messages(move))

    @patch(QUERY)
    def test_vat_mismatch_posts_chatter_warning_but_still_archives(self, mock_query):
        # vat_rate=None -> no tax applied -> Odoo computes 0 ÁFA / 10000
        # gross, while szamlazz.hu reported 2700 / 12700.
        parsed = dict(PARSED_OK, invoice_number='E-2026-0050', vat_rate=None)
        mock_query.return_value = (parsed, None)
        move = self.sync._sync_one('E-2026-0050')
        self.assertTrue(move)
        self.assertEqual(move.state, 'draft')
        warning = self._mismatch_messages(move)
        self.assertEqual(len(warning), 1)
        self.assertIn('2700.00', warning.body)
        self.assertIn('12700.00', warning.body)

    # --- clean stop on InvoiceNotFound (final review #3) ---

    @patch(QUERY)
    def test_invoice_not_found_is_clean_stop_not_error(self, mock_query):
        year = fields.Date.today().year
        self.sync.last_synced_number = f'E-{year}-41'
        found = dict(PARSED_OK, invoice_number=f'E-{year}-42')

        def fake_query(_key, number):
            if number == f'E-{year}-42':
                return found, None
            raise InvoiceNotFound(number)
        mock_query.side_effect = fake_query

        self.sync._cron_sync_invoices()

        self.assertEqual(self.sync.last_run_status, 'ok')
        self.assertEqual(self.sync.last_run_count, 1)
        self.assertEqual(self.sync.last_synced_number, f'E-{year}-42')
        # Same-year number -> no rollover probe: exactly 42 (found) + 43 (not found).
        self.assertEqual(mock_query.call_count, 2)
        self.assertFalse(self.env['account.move'].search([
            ('szamlazz_invoice_number', '=', f'E-{year}-43'),
        ]))

    @patch(QUERY)
    def test_other_errors_still_reported_as_error(self, mock_query):
        mock_query.side_effect = RuntimeError('valódi hiba')
        self.sync._cron_sync_invoices()
        self.assertEqual(self.sync.last_run_status, 'error')
        self.assertIn('valódi hiba', self.sync.last_run_message)

    # --- year rollover heuristic (final review #6) ---

    @patch(QUERY)
    def test_year_rollover_probe_after_not_found(self, mock_query):
        last_year = fields.Date.today().year - 1
        this_year = last_year + 1
        self.sync.last_synced_number = f'AE-{last_year}-37'
        new_year_first = dict(PARSED_OK, invoice_number=f'AE-{this_year}-1')

        def fake_query(_key, number):
            if number == f'AE-{this_year}-1':
                return new_year_first, None
            raise InvoiceNotFound(number)
        mock_query.side_effect = fake_query

        self.sync._cron_sync_invoices()

        self.assertEqual(self.sync.last_run_status, 'ok')
        self.assertEqual(self.sync.last_synced_number, f'AE-{this_year}-1')
        probed = [c.args[1] for c in mock_query.call_args_list]
        # old-year 38 (miss) -> rollover AE-<this>-1 (hit) -> AE-<this>-2
        # (miss, rollover already used) -> stop.
        self.assertEqual(probed, [
            f'AE-{last_year}-38', f'AE-{this_year}-1', f'AE-{this_year}-2',
        ])

    @patch(QUERY)
    def test_year_rollover_miss_is_still_clean_stop(self, mock_query):
        last_year = fields.Date.today().year - 1
        self.sync.last_synced_number = f'AE-{last_year}-37'

        def never_found(_key, number):
            raise InvoiceNotFound(number)
        mock_query.side_effect = never_found

        self.sync._cron_sync_invoices()

        self.assertEqual(self.sync.last_run_status, 'ok')
        self.assertEqual(self.sync.last_run_count, 0)
        self.assertEqual(self.sync.last_synced_number, f'AE-{last_year}-37')
        self.assertEqual(mock_query.call_count, 2)  # old-year probe + one rollover probe

    def test_year_rollover_candidate_only_when_year_passed(self):
        year = fields.Date.today().year
        self.sync.last_synced_number = f'AE-{year}-0037'
        self.assertIsNone(self.sync._year_rollover_candidate())
        self.sync.last_synced_number = f'AE-{year - 1}-0037'
        self.assertEqual(self.sync._year_rollover_candidate(), f'AE-{year}-1')
        self.sync.last_synced_number = False
        self.assertIsNone(self.sync._year_rollover_candidate())

    # --- empty-start guard (final review #6) ---

    @patch(QUERY)
    def test_missing_first_invoice_number_sets_error_without_probing(self, mock_query):
        self.env['ir.config_parameter'].sudo().set_param(
            'dentari_invoice_archive.first_invoice_number', False,  # deletes it
        )
        self.sync._cron_sync_invoices()
        self.assertEqual(self.sync.last_run_status, 'error')
        self.assertIn('first_invoice_number', self.sync.last_run_message)
        mock_query.assert_not_called()

    # --- per-invoice savepoint (final review #4) ---

    @patch(ATTACH)
    @patch(QUERY)
    def test_failure_after_move_create_rolls_back_that_invoice(self, mock_query, mock_attach):
        mock_query.return_value = (PARSED_OK, b'%PDF-1.4 fake')
        mock_attach.side_effect = RuntimeError('pdf csatolás hiba')

        self.sync._cron_sync_invoices()  # must not raise

        self.assertEqual(self.sync.last_run_status, 'error')
        self.assertIn('pdf csatolás hiba', self.sync.last_run_message)
        # No PDF-less move left behind for dedup to return forever.
        self.assertFalse(self.env['account.move'].search([
            ('szamlazz_invoice_number', '=', 'E-2026-0042'),
        ]))
        self.assertFalse(self.sync.last_synced_number)

    # --- record selection: bound record vs. ir.cron's empty recordset (#5) ---

    @patch(QUERY)
    def test_cron_on_empty_recordset_uses_seeded_singleton(self, mock_query):
        import requests
        mock_query.side_effect = requests.exceptions.Timeout('boom')
        singleton = self.env.ref('dentari_invoice_archive.szamlazz_sync_singleton')

        # Exactly how ir.cron's code `model._cron_sync_invoices()` calls it.
        self.env['dentari.szamlazz.sync']._cron_sync_invoices()

        self.assertEqual(singleton.last_run_status, 'error')
        self.assertEqual(self.sync.last_run_status, 'never')


@tagged('post_install', '-at_install')
class TestSzamlazzSyncSetup(TransactionCase):

    def test_cron_job_registered(self):
        cron = self.env.ref('dentari_invoice_archive.ir_cron_szamlazz_sync')
        self.assertEqual(cron.model_id.model, 'dentari.szamlazz.sync')
        self.assertTrue(cron.active)

    def test_sync_action_registered(self):
        action = self.env.ref('dentari_invoice_archive.action_szamlazz_sync')
        self.assertEqual(action.res_model, 'dentari.szamlazz.sync')

    def test_sync_action_opens_seeded_singleton(self):
        singleton = self.env.ref('dentari_invoice_archive.szamlazz_sync_singleton')
        action = self.env.ref('dentari_invoice_archive.action_szamlazz_sync')
        self.assertEqual(action.res_id, singleton.id)
        # Lowest id -> what the cron's search([], limit=1) fallback returns.
        self.assertEqual(self.env['dentari.szamlazz.sync'].search([], limit=1), singleton)
