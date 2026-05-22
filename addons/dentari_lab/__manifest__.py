{
    'name': 'Dentari Lab',
    'version': '18.0.1.0.0',
    'category': 'Dental / Laboratory',
    'summary': 'Dental laboratory work log tracking',
    'depends': ['base', 'mail'],
    'data': [
        'security/groups.xml',
        'security/ir.model.access.csv',
        'security/record_rules.xml',
        'views/dental_work_log_views.xml',
        'views/menus.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
