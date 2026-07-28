import re
import datetime
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

VITA_COLORS = [
    ('A1', 'A1'), ('A2', 'A2'), ('A3', 'A3'), ('A3.5', 'A3.5'), ('A4', 'A4'),
    ('B1', 'B1'), ('B2', 'B2'), ('B3', 'B3'), ('B4', 'B4'),
    ('C1', 'C1'), ('C2', 'C2'), ('C3', 'C3'), ('C4', 'C4'),
    ('D2', 'D2'), ('D3', 'D3'), ('D4', 'D4'),
    ('BL1', 'BL1'), ('BL2', 'BL2'), ('BL3', 'BL3'), ('BL4', 'BL4'),
]

WORK_TYPES = [
    ('korona', 'Korona'),
    ('hid', 'Híd'),
    ('implant', 'Implant'),
    ('facet', 'Facet'),
    ('ideiglenes', 'Ideiglenes'),
    ('javitas', 'Javítás'),
    ('monolitikus', 'Monolitikus'),
    ('grandio', 'Grandio'),
    ('muiny', 'Műíny'),
    ('egyeb', 'Egyéb'),
]


class DentalWorkLog(models.Model):
    _name = 'dental.work.log'
    _description = 'Dental Work Log'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'
    # No company_id / _check_company_auto: single-company deployment only.
    # For multi-company, add company_id + check_company=True on partner_id + allowed_company_ids record rule.

    _sql_constraints = [
        ('dentari_lab_pieces_positive', 'CHECK(pieces >= 1)', 'Darabszám legalább 1 kell legyen.'),
        ('dentari_lab_price_non_negative', 'CHECK(price_per_piece >= 0)', 'Egységár nem lehet negatív.'),
    ]

    name: str = fields.Char(
        compute='_compute_name',
        store=True,
    )
    date: datetime.date = fields.Date(
        string='Dátum',
        required=True,
        default=fields.Date.context_today,
        tracking=True,
        index=True,
    )
    partner_id: int = fields.Many2one(
        'res.partner',
        string='Megrendelő (Klinika)',
        required=True,
        domain=[('is_company', '=', True)],
        tracking=True,
        index=True,
    )
    patient_name: str = fields.Char(
        string='Páciens neve',
        size=100,
    )
    tooth_position: str = fields.Char(
        string='Fogpozíció (FDI)',
        size=50,
    )
    tooth_color: str | bool = fields.Selection(
        selection=VITA_COLORS,
        string='Fogszín (VITA)',
    )
    work_type: str | bool = fields.Selection(
        selection=WORK_TYPES,
        string='Munka típusa',
        tracking=True,
    )
    pieces: int = fields.Integer(
        string='Darabszám',
        required=True,
        default=1,
        tracking=True,
    )
    # Intentionally editable by technicians: they quote per-piece price at record creation.
    # Manager-only pricing would require removing required=True and a separate pricing workflow.
    price_per_piece: float = fields.Float(
        string='Egységár (Ft/db)',
        required=True,
        default=3000,
        tracking=True,
        digits=(10, 0),
    )
    total_revenue: float = fields.Float(
        string='Összeg (Ft)',
        compute='_compute_total_revenue',
        store=True,
        readonly=True,
        digits=(10, 0),
    )
    notes: str = fields.Text(
        string='Megjegyzések',
    )
    attachment_ids: object = fields.Many2many(
        'ir.attachment',
        'dental_work_log_attachment_rel',
        'log_id',
        'attachment_id',
        string='Dokumentumok / Képek',
    )
    attachment_count: int = fields.Integer(
        compute='_compute_attachment_count',
        string='Mellékletek',
    )
    user_id: int = fields.Many2one(
        'res.users',
        string='Rögzítő',
        default=lambda self: self.env.user,
        index=True,
    )
    invoice_id: int = fields.Many2one(
        'account.move',
        string='Számla',
        readonly=True,
        ondelete='set null',
        copy=False,
        index=True,
    )
    invoice_state: str = fields.Char(
        string='Számla állapota',
        compute='_compute_invoice_state',
    )

    @api.depends('attachment_ids')
    def _compute_attachment_count(self):
        if not self.ids:
            self.attachment_count = 0
            return
        self.env.cr.execute(
            "SELECT log_id, COUNT(attachment_id)"
            " FROM dental_work_log_attachment_rel"
            " WHERE log_id = ANY(%s) GROUP BY log_id",
            (self.ids,)
        )
        counts = dict(self.env.cr.fetchall())
        for rec in self:
            rec.attachment_count = counts.get(rec.id, 0)

    @api.depends('invoice_id', 'invoice_id.state')
    def _compute_invoice_state(self):
        state_labels = {
            'draft': 'Piszkozat',
            'posted': 'Könyvelve',
            'cancel': 'Sztornózva',
        }
        for rec in self:
            if rec.invoice_id:
                rec.invoice_state = state_labels.get(rec.invoice_id.state, rec.invoice_id.state)
            else:
                rec.invoice_state = 'Nincs számla'

    @api.depends('pieces', 'price_per_piece')
    def _compute_total_revenue(self):
        for rec in self:
            rec.total_revenue = rec.pieces * rec.price_per_piece

    @api.depends('date', 'partner_id')
    def _compute_name(self):
        for rec in self:
            date_str = rec.date.strftime('%Y-%m-%d') if rec.date else '?'
            partner_str = rec.partner_id.name if rec.partner_id else 'N/A'
            rec.name = f"{date_str} / {partner_str}"

    @api.constrains('pieces')
    def _check_pieces(self):
        for rec in self:
            if not (1 <= rec.pieces <= 100):
                raise ValidationError(_('Darabszám 1 és 100 között kell legyen.'))

    @api.constrains('price_per_piece')
    def _check_price(self):
        for rec in self:
            if not (0 <= rec.price_per_piece <= 500_000):
                raise ValidationError(_('Egységár 0 és 500 000 Ft között kell legyen.'))

    @api.constrains('tooth_position')
    def _check_tooth_position(self):
        for rec in self:
            if rec.tooth_position and not re.match(r'^[\d,.\-]+$', rec.tooth_position):
                raise ValidationError(_('Fogpozíció csak számokat, vesszőt, pontot és kötőjelet tartalmazhat.'))

    def action_open_attachments(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Mellékletek',
            'res_model': 'ir.attachment',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.attachment_ids.ids)],
            'context': {'default_res_model': self._name, 'default_res_id': self.id},
        }
