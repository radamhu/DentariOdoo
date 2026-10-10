from odoo.exceptions import UserError
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


@tagged('post_install', '-at_install')
class TestArchivedMoveGuards(TransactionCase):
    """Archived szamlazz.hu moves must never be posted (real journal
    entries + Odoo sequence) or deleted (8-year retention); ordinary
    'odoo'-source moves must be unaffected."""

    def setUp(self):
        super().setUp()
        self.partner = self.env['res.partner'].create({'name': 'Őrző Teszt Ügyfél'})
        # Odoo 18: account.account has company_ids (M2M), not company_id.
        self.income_account = self.env['account.account'].search([
            ('account_type', '=', 'income'),
            ('company_ids', 'in', self.env.company.id),
        ], limit=1) or self.env['account.account'].create({
            'name': 'Teszt árbevétel (őrző)',
            'code': 'DIA9998',
            'account_type': 'income',
            'company_ids': [(6, 0, [self.env.company.id])],
        })

    def _move(self, source, number=False):
        return self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
            'invoice_source': source,
            'szamlazz_invoice_number': number,
            'invoice_date': '2026-10-01',
            'invoice_line_ids': [(0, 0, {
                'name': 'Teszt sor',
                'account_id': self.income_account.id,
                'quantity': 1,
                'price_unit': 1000.0,
                'tax_ids': False,
            })],
        })

    def test_archived_move_cannot_be_deleted(self):
        archived = self._move('szamlazz_archive', 'AE-2026-0101')
        with self.assertRaises(UserError):
            archived.unlink()
        self.assertTrue(archived.exists())

    def test_mixed_recordset_unlink_blocked(self):
        archived = self._move('szamlazz_archive', 'AE-2026-0102')
        plain = self._move('odoo')
        with self.assertRaises(UserError):
            (archived | plain).unlink()

    def test_archived_move_cannot_be_posted(self):
        archived = self._move('szamlazz_archive', 'AE-2026-0103')
        with self.assertRaises(UserError):
            archived.action_post()
        self.assertEqual(archived.state, 'draft')

    def test_archived_move_cannot_be_posted_via_internal_post(self):
        # The "Post entries" mass action (validate.account.move) calls _post().
        archived = self._move('szamlazz_archive', 'AE-2026-0104')
        with self.assertRaises(UserError):
            archived._post(soft=False)
        self.assertEqual(archived.state, 'draft')

    def test_odoo_source_move_can_still_be_posted(self):
        plain = self._move('odoo')
        plain.action_post()
        self.assertEqual(plain.state, 'posted')

    def test_odoo_source_move_can_still_be_deleted(self):
        plain = self._move('odoo')
        plain.unlink()
        self.assertFalse(plain.exists())


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
