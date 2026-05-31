from odoo import api, fields, models, _
from odoo.exceptions import UserError
from .dental_work_log import WORK_TYPES

WORK_TYPE_MAP = dict(WORK_TYPES)


class DentalInvoiceWizard(models.TransientModel):
    _name = 'dental.invoice.wizard'
    _description = 'Wizard: Számlák generálása'

    work_log_ids = fields.Many2many('dental.work.log', string='Munkalapok')
    invoice_date = fields.Date(
        string='Számla dátuma',
        default=fields.Date.context_today,
        required=True,
    )
    partner_summary_ids = fields.One2many(
        'dental.invoice.wizard.line', 'wizard_id',
        string='Megrendelők',
        readonly=True,
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        active_ids = self.env.context.get('active_ids', [])
        if not active_ids:
            return res
        logs = self.env['dental.work.log'].browse(active_ids)
        if 'work_log_ids' in fields_list:
            res['work_log_ids'] = [(6, 0, active_ids)]
        if 'partner_summary_ids' in fields_list:
            res['partner_summary_ids'] = self._build_summary_vals(logs)
        return res

    def _build_summary_vals(self, logs):
        summary = {}
        for log in logs:
            pid = log.partner_id.id
            if pid not in summary:
                summary[pid] = {'partner_id': pid, 'log_count': 0, 'total_amount': 0.0}
            summary[pid]['log_count'] += 1
            summary[pid]['total_amount'] += log.total_revenue
        return [(0, 0, vals) for vals in summary.values()]

    def create_invoices(self):
        self.ensure_one()
        uninvoiced = self.work_log_ids.filtered(lambda r: not r.invoice_id)
        if not uninvoiced:
            raise UserError(_('A kijelölt munkalapok mind már számlázva vannak.'))

        product_tmpl = self.env.ref('dentari_lab.product_dental_work')
        product = product_tmpl.product_variant_id

        logs_by_partner = {}
        for log in uninvoiced:
            pid = log.partner_id.id
            if pid not in logs_by_partner:
                logs_by_partner[pid] = self.env['dental.work.log']
            logs_by_partner[pid] |= log

        created = self.env['account.move']
        for partner_id, logs in logs_by_partner.items():
            lines = []
            for log in logs:
                label_parts = [WORK_TYPE_MAP.get(log.work_type, log.work_type or 'Egyéb munka')]
                if log.patient_name:
                    label_parts.append(log.patient_name)
                if log.date:
                    label_parts.append(log.date.strftime('%Y-%m-%d'))
                lines.append((0, 0, {
                    'product_id': product.id,
                    'name': ' – '.join(label_parts),
                    'quantity': log.pieces,
                    'price_unit': log.price_per_piece,
                }))
            move = self.env['account.move'].create({
                'move_type': 'out_invoice',
                'partner_id': partner_id,
                'invoice_date': self.invoice_date,
                'invoice_line_ids': lines,
            })
            logs.write({'invoice_id': move.id})
            created |= move

        return {
            'type': 'ir.actions.act_window',
            'name': _('Létrehozott számlák'),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', created.ids)],
            'target': 'current',
        }


class DentalInvoiceWizardLine(models.TransientModel):
    _name = 'dental.invoice.wizard.line'
    _description = 'Wizard sor: Számlák generálása'

    wizard_id = fields.Many2one('dental.invoice.wizard', required=True, ondelete='cascade')
    partner_id = fields.Many2one('res.partner', string='Megrendelő', readonly=True)
    log_count = fields.Integer(string='Munkalapok', readonly=True)
    total_amount = fields.Float(string='Összeg (Ft)', digits=(10, 0), readonly=True)
