import base64
import re
import unicodedata

from odoo import fields, models, _
from odoo.exceptions import UserError


class DentalMonthlyEmailWizard(models.TransientModel):
    _name = 'dental.monthly.email.wizard'
    _description = 'Havi Összesítő – Email Küldés'

    monthly_wizard_id = fields.Many2one(
        'dental.monthly.wizard',
        required=True,
        ondelete='cascade',
    )
    subject = fields.Char(required=True)
    body = fields.Html(required=True)
    partner_ids = fields.Many2many(
        'res.partner',
        string='Címzettek',
    )
    ops_partner_id = fields.Many2one(
        'res.partner',
        string='Operátor partner',
    )

    def action_send(self):
        self.ensure_one()

        if not self.partner_ids:
            raise UserError(_('Nincs kiválasztott címzett. Kérem válasszon legalább egy partnert.'))

        wizard = self.monthly_wizard_id
        report = self.env.ref('dentari_lab.action_report_monthly_summary')
        skipped = []

        for partner in self.partner_ids:
            if not partner.email:
                skipped.append(partner.name or '?')
                continue

            is_ops = (partner == self.env.user.partner_id)
            lines = wizard.preview_ids.filtered(lambda l: l.partner_id == partner)

            if not is_ops and lines:
                # Client partner with their own preview line — send their specific PDF.
                attachment_ids = []
                for line in lines:
                    pdf_content, _mime = report._render_qweb_pdf(report.id, [line.id])
                    nfkd = unicodedata.normalize('NFKD', partner.name or 'partner')
                    safe_name = re.sub(
                        r'[^A-Za-z0-9_\-]', '_',
                        nfkd.encode('ASCII', 'ignore').decode('ASCII'),
                    )
                    filename = (
                        f'Havi_Osszesito_{wizard.period_year}'
                        f'_{wizard.period_month}_{safe_name}.pdf'
                    )
                    att = self.env['ir.attachment'].create({
                        'name': filename,
                        'type': 'binary',
                        'datas': base64.b64encode(pdf_content),
                        'res_model': self._name,
                        'res_id': self.id,
                    })
                    attachment_ids.append((4, att.id))
                body = self.body.replace('{partner_name}', partner.name or 'Megrendelő')
            else:
                # Ops/admin partner — always send all partners' PDFs for the full overview.
                attachment_ids = []
                for line in wizard.preview_ids:
                    pdf_content, _mime = report._render_qweb_pdf(report.id, [line.id])
                    nfkd = unicodedata.normalize('NFKD', line.partner_id.name or 'partner')
                    safe_name = re.sub(
                        r'[^A-Za-z0-9_\-]', '_',
                        nfkd.encode('ASCII', 'ignore').decode('ASCII'),
                    )
                    filename = (
                        f'Havi_Osszesito_{wizard.period_year}'
                        f'_{wizard.period_month}_{safe_name}.pdf'
                    )
                    att = self.env['ir.attachment'].create({
                        'name': filename,
                        'type': 'binary',
                        'datas': base64.b64encode(pdf_content),
                        'res_model': self._name,
                        'res_id': self.id,
                    })
                    attachment_ids.append((4, att.id))
                body = self.body.replace('{partner_name}', partner.name or 'Összesítő')

            self.env['mail.mail'].create({
                'subject': self.subject,
                'body_html': body,
                'email_to': partner.email,
                'attachment_ids': attachment_ids,
                'auto_delete': False,
            }).send()

        if skipped:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Figyelem'),
                    'message': _('A következő partnereknek nem sikerült elküldeni: %s')
                               % ', '.join(skipped),
                    'type': 'warning',
                    'sticky': True,
                    'next': {'type': 'ir.actions.act_window_close'},
                },
            }

        return {'type': 'ir.actions.act_window_close'}
