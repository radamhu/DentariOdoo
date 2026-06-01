from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
from odoo import api, fields, models, _
from odoo.exceptions import UserError

MONTHS = [
    ('1', 'Január'), ('2', 'Február'), ('3', 'Március'),
    ('4', 'Április'), ('5', 'Május'), ('6', 'Június'),
    ('7', 'Július'), ('8', 'Augusztus'), ('9', 'Szeptember'),
    ('10', 'Október'), ('11', 'November'), ('12', 'December'),
]


class DentalMonthlyWizard(models.TransientModel):
    _name = 'dental.monthly.wizard'
    _description = 'Havi Összesítő Wizard'

    period_year = fields.Integer(
        string='Év',
        required=True,
        default=lambda self: date.today().year,
    )
    period_month = fields.Selection(
        selection=MONTHS,
        string='Hónap',
        required=True,
        default=lambda self: str(date.today().month),
    )
    period_label = fields.Char(
        compute='_compute_period_label',
        string='Időszak',
    )
    partner_ids = fields.Many2many(
        'res.partner',
        string='Partner szűrő',
        domain=[('is_company', '=', True)],
    )
    preview_ids = fields.One2many(
        'dental.monthly.wizard.line',
        'wizard_id',
        string='Megrendelők',
        readonly=True,
    )

    @api.depends('period_year', 'period_month')
    def _compute_period_label(self):
        month_names = dict(MONTHS)
        for rec in self:
            month_str = month_names.get(rec.period_month, rec.period_month or '')
            rec.period_label = f"{rec.period_year}. {month_str.lower()}"

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if 'preview_ids' in fields_list:
            today = date.today()
            year = res.get('period_year', today.year)
            month = int(res.get('period_month', str(today.month)))
            logs = self._search_logs(year, month, [])
            res['preview_ids'] = self._build_preview_vals(logs)
        return res

    @api.onchange('period_year', 'period_month', 'partner_ids')
    def _onchange_period(self):
        self.preview_ids = [(5, 0, 0)]
        if not self.period_month:
            return
        partner_ids = self.partner_ids.ids if self.partner_ids else []
        logs = self._search_logs(self.period_year, int(self.period_month), partner_ids)
        self.preview_ids = self._build_preview_vals(logs)

    @api.model
    def _search_logs(self, year, month, partner_ids):
        date_from = date(year, month, 1)
        date_to = date_from + relativedelta(months=1) - timedelta(days=1)
        domain = [('date', '>=', date_from), ('date', '<=', date_to)]
        if partner_ids:
            domain.append(('partner_id', 'in', partner_ids))
        return self.env['dental.work.log'].search(domain, order='partner_id, date, id')

    @api.model
    def _build_preview_vals(self, logs):
        summary = {}
        for log in logs:
            pid = log.partner_id.id
            if pid not in summary:
                summary[pid] = {
                    'partner_id': pid,
                    'log_count': 0,
                    'total_amount': 0.0,
                    'log_ids': [],
                }
            summary[pid]['log_count'] += 1
            summary[pid]['total_amount'] += log.total_revenue
            summary[pid]['log_ids'].append(log.id)
        result = []
        for vals in summary.values():
            log_ids = vals.pop('log_ids')
            vals['log_ids'] = [(6, 0, log_ids)]
            result.append((0, 0, vals))
        return result

    def action_print_summary(self):
        self.ensure_one()
        partner_ids = self.partner_ids.ids if self.partner_ids else []
        logs = self._search_logs(self.period_year, int(self.period_month), partner_ids)
        if not logs:
            raise UserError(_('Nincs munkalap a kiválasztott időszakban.'))
        # preview_ids is readonly in the view, so it's not sent back on button click;
        # always rebuild from the current period to ensure the report template has correct data.
        self.write({'preview_ids': [(5, 0, 0)] + self._build_preview_vals(logs)})
        return self.env.ref('dentari_lab.action_report_monthly_summary').report_action(self)


class DentalMonthlyWizardLine(models.TransientModel):
    _name = 'dental.monthly.wizard.line'
    _description = 'Havi Összesítő sor'

    wizard_id = fields.Many2one(
        'dental.monthly.wizard',
        required=True,
        ondelete='cascade',
    )
    partner_id = fields.Many2one('res.partner', string='Megrendelő', readonly=True)
    log_count = fields.Integer(string='Munkalapok', readonly=True)
    total_amount = fields.Float(string='Összeg (Ft)', digits=(10, 0), readonly=True)
    log_ids = fields.Many2many(
        'dental.work.log',
        'dental_monthly_wizard_line_log_rel',
        'line_id',
        'log_id',
        string='Munkalapok',
        readonly=True,
    )
