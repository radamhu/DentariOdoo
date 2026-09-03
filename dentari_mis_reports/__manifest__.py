{
    'name': 'Dentari MIS Reports',
    'version': '18.0.1.0.0',
    'category': 'Dental / Accounting',
    'summary': 'Kiadások vs Dentari Lab revenue profitability report (mis_builder)',
    'depends': ['mis_builder', 'dentari_lab', 'dental_quick_expense'],
    'data': [
        'data/mis_report_data.xml',
        'data/mis_report_instance_data.xml',
        'views/menu.xml',
    ],
    'demo': [],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
