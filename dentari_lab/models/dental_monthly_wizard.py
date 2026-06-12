import base64
import io
import re
import unicodedata
import zipfile
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
            res['preview_ids'] = self._build_preview_vals(logs, year, str(month))
        return res

    def action_query(self):
        self.ensure_one()
        partner_ids = self.partner_ids.ids if self.partner_ids else []
        logs = self._search_logs(self.period_year, int(self.period_month), partner_ids)
        self.write({
            'preview_ids': [(5, 0, 0)] + self._build_preview_vals(
                logs, self.period_year, self.period_month
            ),
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'dental.monthly.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    @api.model
    def _search_logs(self, year, month, partner_ids):
        date_from = date(year, month, 1)
        date_to = date_from + relativedelta(months=1) - timedelta(days=1)
        domain = [('date', '>=', date_from), ('date', '<=', date_to)]
        if partner_ids:
            domain.append(('partner_id', 'in', partner_ids))
        return self.env['dental.work.log'].search(domain, order='partner_id, date, id')

    @api.model
    def _build_preview_vals(self, logs, year, month):
        summary = {}
        for log in logs:
            pid = log.partner_id.id
            if pid not in summary:
                summary[pid] = {
                    'partner_id': pid,
                    'log_count': 0,
                    'total_amount': 0.0,
                    'period_year': year,
                    'period_month': str(month),
                }
            summary[pid]['log_count'] += 1
            summary[pid]['total_amount'] += log.total_revenue
        return [(0, 0, vals) for vals in summary.values()]

    def action_print_summary(self):
        self.ensure_one()
        partner_ids = self.partner_ids.ids if self.partner_ids else []
        logs = self._search_logs(self.period_year, int(self.period_month), partner_ids)
        if not logs:
            raise UserError(_('Nincs munkalap a kiválasztott időszakban.'))
        self.write({
            'preview_ids': [(5, 0, 0)] + self._build_preview_vals(
                logs, self.period_year, self.period_month
            ),
        })
        report = self.env.ref('dentari_lab.action_report_monthly_summary')
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            for line in self.preview_ids:
                pdf_content, _ = report._render_qweb_pdf(report.id, [line.id])
                nfkd = unicodedata.normalize('NFKD', line.partner_id.name or 'partner')
                safe_name = re.sub(r'[^A-Za-z0-9_\-]', '_', nfkd.encode('ASCII', 'ignore').decode('ASCII'))
                filename = f'Havi_Osszesito_{self.period_year}_{self.period_month}_{safe_name}.pdf'
                zf.writestr(filename, pdf_content)
        attachment = self.env['ir.attachment'].create({
            'name': f'Havi_Osszesito_{self.period_year}_{self.period_month}.zip',
            'type': 'binary',
            'datas': base64.b64encode(zip_buffer.getvalue()),
            'res_model': self._name,
            'res_id': self.id,
        })
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'new',
        }

    def action_open_email_wizard(self):
        self.ensure_one()
        partners_with_email = self.preview_ids.mapped('partner_id').filtered(
            lambda p: p.email
        )

        current_user_partner = self.env.user.partner_id
        default_partners = partners_with_email
        if current_user_partner not in default_partners and current_user_partner.email:
            default_partners = default_partners | current_user_partner

        if not default_partners:
            raise UserError(_('Nincs email-cím: sem a megrendelőknek, sem a bejelentkezett felhasználónak.'))

        period_label = self.period_label
        user_name = self.env.user.name
        subject = f'Havi elszámolás – {period_label}'
        body = (
            f'<p>Tisztelt {{partner_name}}!</p>'
            f'<p>Mellékletben küldjük a {period_label} havi elszámolást.</p>'
            f'<p>Üdvözlettel,<br/>{user_name}</p>'
        )

        email_wizard = self.env['dental.monthly.email.wizard'].create({
            'monthly_wizard_id': self.id,
            'subject': subject,
            'body': body,
            'partner_ids': [(6, 0, default_partners.ids)],
            'ops_partner_id': current_user_partner.id,
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'dental.monthly.email.wizard',
            'res_id': email_wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }


class DentalMonthlyWizardLine(models.TransientModel):
    _name = 'dental.monthly.wizard.line'
    _description = 'Havi Összesítő sor'

    wizard_id = fields.Many2one(
        'dental.monthly.wizard',
        required=True,
        ondelete='cascade',
    )
    partner_id = fields.Many2one('res.partner', string='Megrendelő', readonly=True)
    log_count = fields.Integer(string='Munkalapok száma', readonly=True)
    total_amount = fields.Float(string='Összeg (Ft)', digits=(10, 0), readonly=True)
    period_year = fields.Integer()
    period_month = fields.Char()
    log_ids = fields.Many2many(
        'dental.work.log',
        string='Munkalap lista',
        compute='_compute_log_ids',
    )

    @api.depends('period_year', 'period_month', 'partner_id')
    def _compute_log_ids(self):
        empty = self.env['dental.work.log']
        lines_with_data = self.filtered(lambda l: l.period_month and l.partner_id)
        if not lines_with_data:
            self.log_ids = empty
            return

        # All lines share one wizard period — one search covers the entire batch.
        year = lines_with_data[0].period_year
        month = int(lines_with_data[0].period_month)
        date_from = date(year, month, 1)
        date_to = date_from + relativedelta(months=1) - timedelta(days=1)
        partner_ids = lines_with_data.mapped('partner_id').ids
        all_logs = self.env['dental.work.log'].search([
            ('date', '>=', date_from),
            ('date', '<=', date_to),
            ('partner_id', 'in', partner_ids),
        ], order='date, id')

        logs_by_partner = {}
        for log in all_logs:
            pid = log.partner_id.id
            logs_by_partner.setdefault(pid, empty)
            logs_by_partner[pid] |= log

        for line in lines_with_data:
            line.log_ids = logs_by_partner.get(line.partner_id.id, empty)
        (self - lines_with_data).log_ids = empty

    def action_open_logs(self):
        self.ensure_one()
        date_from = date(self.period_year, int(self.period_month), 1)
        date_to = date_from + relativedelta(months=1) - timedelta(days=1)
        month_names = dict(MONTHS)
        period_label = (
            f"{self.period_year}. {month_names.get(self.period_month, self.period_month).lower()}"
        )
        return {
            'type': 'ir.actions.act_window',
            'name': f'{self.partner_id.name} — {period_label}',
            'res_model': 'dental.work.log',
            'view_mode': 'list,form',
            'domain': [
                ('partner_id', '=', self.partner_id.id),
                ('date', '>=', date_from),
                ('date', '<=', date_to),
            ],
            'target': 'new',
        }
