from odoo import api, fields, models

QUICK_EXPENSE_CATEGORY_XMLIDS = [
    'dental_quick_expense.account_expense_fogtechnikai_anyag',
    'dental_quick_expense.account_expense_futar_szallitas',
    'dental_quick_expense.account_expense_uzemanyag',
    'dental_quick_expense.account_expense_gep_eszkoz',
    'dental_quick_expense.account_expense_gepkarbantartas',
    'dental_quick_expense.account_expense_telefon_internet',
    'dental_quick_expense.account_expense_rezsi',
    'dental_quick_expense.account_expense_konyveles',
    'dental_quick_expense.account_expense_szoftver',
    'dental_quick_expense.account_expense_oktatas',
    'dental_quick_expense.account_expense_egyeb',
]


def quick_expense_category_accounts(env):
    """Return the recordset of the 11 seeded Kiadások category accounts."""
    accounts = env['account.account']
    for xmlid in QUICK_EXPENSE_CATEGORY_XMLIDS:
        account = env.ref(xmlid, raise_if_not_found=False)
        if account:
            accounts |= account
    return accounts


class AccountMove(models.Model):
    _inherit = 'account.move'
