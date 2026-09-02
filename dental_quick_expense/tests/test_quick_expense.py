from odoo.exceptions import ValidationError
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
