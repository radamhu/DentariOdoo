from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestQuickExpenseCategories(TransactionCase):

    def test_eleven_category_accounts_seeded(self):
        from odoo.addons.dental_quick_expense.models.account_move import (
            quick_expense_category_accounts,
        )
        accounts = quick_expense_category_accounts(self.env)
        self.assertEqual(len(accounts), 11)
        self.assertTrue(all(a.account_type == 'expense' for a in accounts))


@tagged('post_install', '-at_install')
class TestQuickExpenseWizard(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env['res.partner'].create({'name': 'Teszt Szállító'})
        from odoo.addons.dental_quick_expense.models.account_move import (
            quick_expense_category_accounts,
        )
        cls.category = quick_expense_category_accounts(cls.env)[0]
        cls.tax = cls.env['account.tax'].search(
            [('type_tax_use', '=', 'purchase')], limit=1,
        )

    def test_action_save_creates_draft_vendor_bill(self):
        wizard = self.env['dental.quick.expense'].create({
            'date': '2026-09-02',
            'partner_id': self.partner.id,
            'category_account_id': self.category.id,
            'description': 'Teszt kiadás',
            'net_amount': 5000,
            'tax_id': self.tax.id,
        })
        wizard.action_save()

        moves = self.env['account.move'].search([
            ('partner_id', '=', self.partner.id),
            ('move_type', '=', 'in_invoice'),
        ])
        self.assertEqual(len(moves), 1)
        move = moves[0]
        self.assertEqual(move.state, 'draft')
        self.assertEqual(len(move.invoice_line_ids), 1)
        line = move.invoice_line_ids[0]
        self.assertEqual(line.account_id, self.category)
        self.assertEqual(line.name, 'Teszt kiadás')
        self.assertEqual(line.price_unit, 5000)

    def test_missing_required_field_blocks_save(self):
        with self.assertRaises(ValidationError):
            self.env['dental.quick.expense'].create({
                'partner_id': self.partner.id,
                'category_account_id': self.category.id,
                'description': 'Teszt hiányos',
                'tax_id': self.tax.id,
                # net_amount intentionally omitted
            })
        moves = self.env['account.move'].search([
            ('partner_id', '=', self.partner.id),
            ('ref', '=', False),
            ('invoice_line_ids.name', '=', 'Teszt hiányos'),
        ])
        self.assertEqual(len(moves), 0)

    def test_attachment_relinked_to_move_not_wizard(self):
        wizard = self.env['dental.quick.expense'].create({
            'date': '2026-09-02',
            'partner_id': self.partner.id,
            'category_account_id': self.category.id,
            'description': 'Kiadás csatolmánnyal',
            'net_amount': 3000,
            'tax_id': self.tax.id,
        })
        attachment = self.env['ir.attachment'].create({
            'name': 'bizonylat.pdf',
            'datas': 'dGVzdA==',
            'res_model': 'dental.quick.expense',
            'res_id': wizard.id,
        })
        wizard.attachment_ids = [(6, 0, [attachment.id])]
        wizard.action_save()

        self.assertEqual(attachment.res_model, 'account.move')
        self.assertNotEqual(attachment.res_id, wizard.id)

    def test_category_domain_excludes_non_expense_accounts(self):
        from odoo.addons.dental_quick_expense.models.account_move import (
            quick_expense_category_accounts,
        )
        revenue_account = self.env['account.account'].create({
            'name': 'Teszt bevétel',
            'code': '9999',
            'account_type': 'income',
        })
        self.assertNotIn(
            revenue_account.id, quick_expense_category_accounts(self.env).ids,
        )


class TestQuickExpenseComputedCategory(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env['res.partner'].create({'name': 'Teszt Szállító 2'})
        from odoo.addons.dental_quick_expense.models.account_move import (
            quick_expense_category_accounts,
        )
        cls.category = quick_expense_category_accounts(cls.env)[0]

    def test_expense_category_id_computed_from_line(self):
        move = self.env['account.move'].create({
            'move_type': 'in_invoice',
            'partner_id': self.partner.id,
            'invoice_line_ids': [(0, 0, {
                'account_id': self.category.id,
                'name': 'Teszt sor',
                'quantity': 1,
                'price_unit': 100,
            })],
        })
        self.assertEqual(move.expense_category_id, self.category)

    def test_expense_category_id_false_for_unrelated_bill(self):
        other_account = self.env['account.account'].search([
            ('account_type', '=', 'expense'),
            ('id', 'not in', self.category.ids),
        ], limit=1)
        move = self.env['account.move'].create({
            'move_type': 'in_invoice',
            'partner_id': self.partner.id,
            'invoice_line_ids': [(0, 0, {
                'account_id': other_account.id,
                'name': 'Nem kiadás',
                'quantity': 1,
                'price_unit': 100,
            })],
        })
        self.assertFalse(move.expense_category_id)


@tagged('post_install', '-at_install')
class TestQuickExpenseViews(TransactionCase):

    def test_views_and_actions_registered(self):
        self.assertTrue(self.env.ref('dental_quick_expense.view_quick_expense_form'))
        self.assertTrue(self.env.ref('dental_quick_expense.action_dental_quick_expense_list'))
        self.assertTrue(self.env.ref('dental_quick_expense.action_dental_quick_expense_new'))
        self.assertTrue(self.env.ref('dental_quick_expense.menu_dental_quick_expense_root'))


@tagged('post_install', '-at_install')
class TestQuickExpenseListScope(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env['res.partner'].create({'name': 'Teszt Szállító 3'})
        from odoo.addons.dental_quick_expense.models.account_move import (
            quick_expense_category_accounts,
        )
        cls.category = quick_expense_category_accounts(cls.env)[0]
        cls.other_expense_account = cls.env['account.account'].search([
            ('account_type', '=', 'expense'),
            ('id', 'not in', cls.category.ids),
        ], limit=1)

    def test_list_domain_excludes_unrelated_vendor_bills(self):
        quick_move = self.env['account.move'].create({
            'move_type': 'in_invoice',
            'partner_id': self.partner.id,
            'invoice_line_ids': [(0, 0, {
                'account_id': self.category.id,
                'name': 'Kiadás',
                'quantity': 1,
                'price_unit': 100,
            })],
        })
        unrelated_move = self.env['account.move'].create({
            'move_type': 'in_invoice',
            'partner_id': self.partner.id,
            'invoice_line_ids': [(0, 0, {
                'account_id': self.other_expense_account.id,
                'name': 'Más számla',
                'quantity': 1,
                'price_unit': 100,
            })],
        })
        action = self.env.ref('dental_quick_expense.action_dental_quick_expense_list')
        domain = eval(action.domain)
        found = self.env['account.move'].search(domain)
        self.assertIn(quick_move, found)
        self.assertNotIn(unrelated_move, found)


@tagged('post_install', '-at_install')
class TestQuickExpenseErrorHandling(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env['res.partner'].create({'name': 'Teszt Szállító 4'})
        cls.tax = cls.env['account.tax'].search(
            [('type_tax_use', '=', 'purchase')], limit=1,
        )

    def test_removed_category_account_blocks_save(self):
        # Uses a freshly-created, unreferenced account.account rather than
        # one of the 11 noupdate="1" seeded category accounts: those are
        # never recreated by a module upgrade, so unlinking one here would
        # permanently remove it from any database this test runs against.
        #
        # The throwaway account must never be assigned to a *persisted*
        # wizard before being deleted: category_account_id is a required
        # Many2one whose FK defaults to ondelete='cascade' (confirmed live
        # against dentari-dev), so deleting a referenced account cascades
        # away the referencing dental.quick.expense row too -- the wizard
        # vanishes outright, and the subsequent action_save() call fails
        # with a MissingError ("Record does not exist") rather than the
        # intended UserError check/message. To exercise action_save()'s
        # own `self.category_account_id.exists()` guard faithfully, the
        # account is deleted *before* it is ever attached to a record, and
        # the wizard is built via .new() (never persisted, so nothing
        # triggers an FK write) with the already-deleted id assigned
        # directly -- the field's domain isn't enforced at the ORM level,
        # only in the UI, so this still exercises the real check.
        throwaway_account = self.env['account.account'].create({
            'name': 'Ideiglenes teszt kategória',
            'code': 'DQE9998',
            'account_type': 'expense',
        })
        throwaway_id = throwaway_account.id
        throwaway_account.unlink()

        wizard = self.env['dental.quick.expense'].new({
            'date': '2026-09-02',
            'partner_id': self.partner.id,
            'category_account_id': throwaway_id,
            'description': 'Kiadás törölt kategóriával',
            'net_amount': 1000,
            'tax_id': self.tax.id,
        })
        with self.assertRaisesRegex(UserError, 'A kiadás kategória nem található'):
            wizard.action_save()
