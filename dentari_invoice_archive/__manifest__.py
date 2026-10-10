{
    'name': 'Dentari Invoice Archive',
    'version': '18.0.1.0.0',
    'category': 'Dental / Accounting',
    'summary': 'Archives szamlazz.hu-issued invoices into Odoo as draft account.move records',
    'depends': ['account', 'dentari_lab'],
    # Order matters: ACL before the seeded sync singleton, the singleton
    # before the views whose action binds to it via res_id.
    'data': [
        'security/ir.model.access.csv',
        'data/szamlazz_sync_data.xml',
        'data/ir_cron.xml',
        'views/szamlazz_sync_views.xml',
        'views/invoice_archive_views.xml',
        'views/menus.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
