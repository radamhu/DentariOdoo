{
    'name': 'Dentari Invoice Archive',
    'version': '18.0.1.0.0',
    'category': 'Dental / Accounting',
    'summary': 'Archives szamlazz.hu-issued invoices into Odoo as draft account.move records',
    'depends': ['account', 'dentari_lab'],
    # Empty at Task 2 -- account.move field additions need no new security/view
    # file (account.move's own ACL already covers it). Tasks 5 and 6 each
    # append their own new file(s) here as they're created -- never reference
    # a data file in this list before the task that creates it exists, or
    # every `odoo -u` run until then fails with a missing-file error.
    'data': [],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
