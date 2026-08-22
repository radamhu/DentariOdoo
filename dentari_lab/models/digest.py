from odoo import _, fields, models
from odoo.exceptions import UserError

GROUP_LAB_MANAGER = 'dentari_lab.group_lab_manager'


class Digest(models.Model):
    _inherit = 'digest.digest'

    kpi_dentari_lab_new_logs = fields.Boolean('New Work Logs', default=True)
    kpi_dentari_lab_new_logs_value = fields.Integer(
        compute='_compute_kpi_dentari_lab_new_logs_value',
    )
    kpi_dentari_lab_revenue = fields.Boolean('Lab Revenue', default=True)
    kpi_dentari_lab_revenue_value = fields.Float(
        compute='_compute_kpi_dentari_lab_revenue_value',
        digits=(10, 0),
    )
    kpi_dentari_lab_unbilled = fields.Boolean('Unbilled Work Logs', default=True)
    kpi_dentari_lab_unbilled_value = fields.Integer(
        compute='_compute_kpi_dentari_lab_unbilled_value',
    )

    def _check_dentari_lab_digest_access(self):
        if not self.env.user.has_group(GROUP_LAB_MANAGER):
            raise UserError(_("Do not have access, skip this data for user's digest email"))

    def _compute_kpi_dentari_lab_new_logs_value(self):
        self._check_dentari_lab_digest_access()
        for record in self:
            start, end, _company = record._get_kpi_compute_parameters()
            record.kpi_dentari_lab_new_logs_value = self.env['dental.work.log'].search_count([
                ('create_date', '>=', start),
                ('create_date', '<', end),
            ])

    def _compute_kpi_dentari_lab_revenue_value(self):
        self._check_dentari_lab_digest_access()
        for record in self:
            start, end, _company = record._get_kpi_compute_parameters()
            logs = self.env['dental.work.log'].search([
                ('create_date', '>=', start),
                ('create_date', '<', end),
            ])
            record.kpi_dentari_lab_revenue_value = sum(logs.mapped('total_revenue'))

    def _compute_kpi_dentari_lab_unbilled_value(self):
        self._check_dentari_lab_digest_access()
        for record in self:
            record.kpi_dentari_lab_unbilled_value = self.env['dental.work.log'].search_count([
                ('invoice_id', '=', False),
            ])
