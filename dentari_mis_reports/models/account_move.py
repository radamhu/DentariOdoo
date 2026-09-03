from odoo import api, models

DEMO_MIS_MARKER = 'dentari-mis-demo'


class AccountMove(models.Model):
    _inherit = 'account.move'

    @api.model
    def _load_dentari_mis_demo_data(self):
        """Idempotent demo-data seeder for the QA test dashboard.

        Filled in by Task 4. Left as a no-op here so the module installs
        cleanly (and the <function> hook in demo data has something to
        call) before that task exists.
        """
        return
