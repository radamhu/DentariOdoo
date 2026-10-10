from odoo import fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    invoice_source = fields.Selection(
        [('odoo', 'Odoo'), ('szamlazz_archive', 'Számlázz.hu archívum')],
        string='Számla forrása',
        default='odoo',
        required=True,
    )
    szamlazz_invoice_number = fields.Char(
        string='Számlázz.hu sorszám',
        copy=False,
        index=True,
    )
