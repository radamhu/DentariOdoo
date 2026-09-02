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
