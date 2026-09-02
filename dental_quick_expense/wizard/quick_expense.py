from odoo import _, fields, models
from odoo.exceptions import UserError

from ..models.account_move import quick_expense_category_accounts


class DentalQuickExpense(models.TransientModel):
    _name = 'dental.quick.expense'
    _description = 'Gyors kiadás rögzítése'

    date = fields.Date(
        string='Dátum', required=True, default=fields.Date.context_today,
    )
    partner_id = fields.Many2one(
        'res.partner', string='Szállító', required=True,
    )
    category_account_id = fields.Many2one(
        'account.account',
        string='Kategória',
        required=True,
        domain=lambda self: [('id', 'in', quick_expense_category_accounts(self.env).ids)],
    )
    description = fields.Char(string='Leírás', required=True)
    currency_id = fields.Many2one(
        'res.currency',
        default=lambda self: self.env.company.currency_id,
        required=True,
    )
    net_amount = fields.Monetary(
        string='Nettó összeg', required=True, currency_field='currency_id',
    )
    tax_id = fields.Many2one(
        'account.tax',
        string='ÁFA',
        required=True,
        domain=[('type_tax_use', '=', 'purchase')],
    )
    ref = fields.Char(string='Bizonylatszám')
    attachment_ids = fields.Many2many('ir.attachment', string='Bizonylat')

    def action_save(self):
        self.ensure_one()
        if not self.category_account_id.exists():
            raise UserError(_('A kiadás kategória nem található.'))

        move = self.env['account.move'].create({
            'move_type': 'in_invoice',
            'partner_id': self.partner_id.id,
            'invoice_date': self.date,
            'ref': self.ref,
            'invoice_line_ids': [(0, 0, {
                'account_id': self.category_account_id.id,
                'name': self.description,
                'quantity': 1,
                'price_unit': self.net_amount,
                'tax_ids': [(6, 0, [self.tax_id.id])],
            })],
        })

        if self.attachment_ids:
            self.attachment_ids.write({
                'res_model': 'account.move',
                'res_id': move.id,
            })

        action = self.env['ir.actions.act_window']._for_xml_id(
            'dental_quick_expense.action_dental_quick_expense_list'
        )
        action['domain'] = [('id', '=', move.id)]
        return action
