from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestAccountMoveInvoiceSource(TransactionCase):

    def test_new_move_defaults_to_odoo_source(self):
        partner = self.env['res.partner'].create({'name': 'Teszt Ügyfél'})
        move = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': partner.id,
        })
        self.assertEqual(move.invoice_source, 'odoo')
        self.assertFalse(move.szamlazz_invoice_number)

    def test_archive_source_and_number_round_trip(self):
        partner = self.env['res.partner'].create({'name': 'Teszt Ügyfél 2'})
        move = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': partner.id,
            'invoice_source': 'szamlazz_archive',
            'szamlazz_invoice_number': 'E-2026-0042',
        })
        self.assertEqual(move.invoice_source, 'szamlazz_archive')
        self.assertEqual(move.szamlazz_invoice_number, 'E-2026-0042')

    def test_dedup_lookup_finds_existing_archived_invoice(self):
        partner = self.env['res.partner'].create({'name': 'Teszt Ügyfél 3'})
        self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': partner.id,
            'invoice_source': 'szamlazz_archive',
            'szamlazz_invoice_number': 'E-2026-0099',
        })
        found = self.env['account.move'].search([
            ('szamlazz_invoice_number', '=', 'E-2026-0099'),
        ])
        self.assertEqual(len(found), 1)


class TestInvoiceArchiveView(TransactionCase):

    def test_archive_list_action_registered_and_scoped(self):
        action = self.env.ref('dentari_invoice_archive.action_invoice_archive_list')
        self.assertEqual(action.res_model, 'account.move')
        import ast
        domain = ast.literal_eval(action.domain)
        partner = self.env['res.partner'].create({'name': 'Teszt Ügyfél 5'})
        archived = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': partner.id,
            'invoice_source': 'szamlazz_archive',
            'szamlazz_invoice_number': 'E-2026-0077',
        })
        odoo_native = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': partner.id,
        })
        found = self.env['account.move'].search(domain)
        self.assertIn(archived, found)
        self.assertNotIn(odoo_native, found)

    def test_menu_registered(self):
        self.assertTrue(self.env.ref('dentari_invoice_archive.menu_invoice_archive_root'))
