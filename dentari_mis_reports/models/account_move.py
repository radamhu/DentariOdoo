from odoo import api, fields, models
from dateutil.relativedelta import relativedelta

DEMO_MIS_MARKER = 'dentari-mis-demo'


class AccountMove(models.Model):
    _inherit = 'account.move'

    @api.model
    def _load_dentari_mis_demo_data(self):
        """Idempotent demo-data seeder for the QA test dashboard.

        Creates one posted quick-expense vendor bill (Netto 100 000 Ft) and
        one dental.work.log (Összeg 200 000 Ft) in a single, clearly-labeled
        month, so a dev can eyeball Netto+Áfa=Bruttó and the margin calc
        instantly. Unlike dental_quick_expense's own demo data (left in
        draft on purpose), this bill is posted — the Kiadások KPI only
        counts posted moves, and a draft demo bill would render as zeros.
        """
        Move = self.env['account.move']
        if Move.search_count([('ref', '=', DEMO_MIS_MARKER)]):
            return

        account = self.env.ref(
            'dental_quick_expense.account_expense_fogtechnikai_anyag',
            raise_if_not_found=False,
        )
        if not account:
            return

        partner = self.env['res.partner'].search(
            [('name', '=', 'Demo Kiadás Szállító')], limit=1,
        )
        if not partner:
            partner = self.env['res.partner'].create({
                'name': 'Demo Kiadás Szállító',
            })

        clinic = self.env['res.partner'].search(
            [('name', '=', 'Demo MIS Klinika Kft.')], limit=1,
        )
        if not clinic:
            clinic = self.env['res.partner'].create({
                'name': 'Demo MIS Klinika Kft.',
                'is_company': True,
            })

        tax = self.env['account.tax'].search(
            [('type_tax_use', '=', 'purchase')], limit=1,
        )

        demo_date = fields.Date.context_today(self) - relativedelta(months=1)
        demo_date = demo_date.replace(day=15)

        move = Move.create({
            'move_type': 'in_invoice',
            'partner_id': partner.id,
            'invoice_date': demo_date,
            'ref': DEMO_MIS_MARKER,
            'invoice_line_ids': [(0, 0, {
                'account_id': account.id,
                'name': 'QA Teszt Kiadás – 100 000 Ft',
                'quantity': 1,
                'price_unit': 100000,
                'tax_ids': [(6, 0, [tax.id])] if tax else False,
            })],
        })
        move.action_post()

        self.env['dental.work.log'].create({
            'date': demo_date,
            'partner_id': clinic.id,
            'patient_name': 'QA Teszt Páciens',
            'work_type': 'korona',
            'pieces': 1,
            'price_per_piece': 200000,
            'notes': f'[{DEMO_MIS_MARKER}] QA test dashboard seed record',
        })
