{
    'name': 'Dental Quick Expense',
    'version': '18.0.1.0.0',
    'category': 'Dental / Accounting',
    'summary': 'Lightweight expense recording wizard over Vendor Bills',
    'depends': ['account', 'dentari_lab'],
    'data': [
        'security/ir.model.access.csv',
        'data/expense_categories.xml',
        # NOTE: 'views/quick_expense_views.xml', 'views/expense_list_views.xml'
        # and 'views/menus.xml' are added back here once Task 6 creates those
        # files. Listing them before they exist breaks module install
        # (Odoo raises FileNotFoundError loading manifest data files).
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
