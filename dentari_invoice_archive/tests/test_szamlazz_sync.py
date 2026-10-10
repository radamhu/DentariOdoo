from unittest.mock import patch

from odoo.tests.common import TransactionCase, tagged

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
        self.income_account = self.env['account.account'].search([
            ('account_type', '=', 'income'),
        ], limit=1) or self.env['account.account'].create({
            'name': 'Teszt árbevétel',
            'code': 'DIA9999',
            'account_type': 'income',
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
            ('company_id', '=', self.env.company.id),
        ]).write({'account_type': 'income_other'})
        mock_query.return_value = (PARSED_OK, b'%PDF-1.4 fake')

        self.sync._cron_sync_invoices()  # must not raise

        self.assertEqual(self.sync.last_run_status, 'error')
        self.assertIn('bevétel', self.sync.last_run_message or '')


@tagged('post_install', '-at_install')
class TestSzamlazzSyncSetup(TransactionCase):

    def test_cron_job_registered(self):
        cron = self.env.ref('dentari_invoice_archive.ir_cron_szamlazz_sync')
        self.assertEqual(cron.model_id.model, 'dentari.szamlazz.sync')
        self.assertTrue(cron.active)

    def test_sync_action_registered(self):
        action = self.env.ref('dentari_invoice_archive.action_szamlazz_sync')
        self.assertEqual(action.res_model, 'dentari.szamlazz.sync')
