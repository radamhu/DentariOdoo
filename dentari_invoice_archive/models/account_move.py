from odoo import _, fields, models
from odoo.exceptions import UserError


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

    def _check_not_szamlazz_archive(self, operation):
        """Archived szamlazz.hu invoices are read-only legal records: posting
        one would create real journal entries and consume Odoo's own invoice
        sequence, deleting one would break the 8-year retention requirement.
        Raise if any record in self is an archive record; ordinary
        ('odoo'-source) moves are never affected."""
        archived = self.filtered(lambda m: m.invoice_source == 'szamlazz_archive')
        if archived:
            numbers = ', '.join(archived.mapped(lambda m: m.szamlazz_invoice_number or str(m.id)))
            raise UserError(_(
                'A Számlázz.hu archívumból származó számlák nem %(operation)s '
                '(csak archív másolatok, a hivatalos számla a Számlázz.hu-n '
                'van): %(numbers)s',
                operation=operation, numbers=numbers,
            ))

    def unlink(self):
        # Any archived record in self blocks the whole call (the raise rolls
        # back the transaction anyway); recordsets with no archived records
        # unlink exactly as before.
        self._check_not_szamlazz_archive('törölhetők')
        return super().unlink()

    def action_post(self):
        self._check_not_szamlazz_archive('könyvelhetők')
        return super().action_post()

    def _post(self, soft=True):
        # action_post() funnels into _post(), but the "Post entries" mass
        # action (validate.account.move) and other server paths call _post()
        # directly -- guard here too so no UI path can post an archive record.
        self._check_not_szamlazz_archive('könyvelhetők')
        return super()._post(soft=soft)
