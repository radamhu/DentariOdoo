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

    def action_send(self):
        self.ensure_one()
        if not self.partner_ids:
            raise UserError(_('Nincs kijelölt címzett.'))

        wizard = self.monthly_wizard_id
        report = self.env.ref('dentari_lab.action_report_monthly_summary')
        skipped = []

        for partner in self.partner_ids:
            line = wizard.preview_ids.filtered(lambda l: l.partner_id == partner)
            if not line:
                skipped.append(partner.name or '?')
                continue
            line = line[0]

            pdf_content, _ = report._render_qweb_pdf(report.id, [line.id])

            nfkd = unicodedata.normalize('NFKD', partner.name or 'partner')
            safe_name = re.sub(
                r'[^A-Za-z0-9_\-]', '_',
                nfkd.encode('ASCII', 'ignore').decode('ASCII'),
            )
            filename = (
                f'Havi_Osszesito_{wizard.period_year}'
                f'_{wizard.period_month}_{safe_name}.pdf'
            )

            attachment = self.env['ir.attachment'].create({
                'name': filename,
                'type': 'binary',
                'datas': base64.b64encode(pdf_content),
                'res_model': self._name,
                'res_id': self.id,
            })

            body = self.body.replace('{partner_name}', partner.name or 'Megrendelő')

            mail_vals = {
                'subject': self.subject,
                'body_html': body,
                'attachment_ids': [(4, attachment.id)],
            }
            if partner.email:
                mail_vals['email_to'] = partner.email
            user_email = self.env.user.email
            if user_email:
                mail_vals['email_cc'] = user_email

            if not mail_vals.get('email_to'):
                skipped.append(partner.name or '?')
                continue

            self.env['mail.mail'].create(mail_vals).send()

        if skipped:
            raise UserError(
                _('A következő partnereknek nem sikerült elküldeni: %s')
                % ', '.join(skipped)
            )

        return {'type': 'ir.actions.act_window_close'}
