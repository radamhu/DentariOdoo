import re
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
    ('egyeb', 'Egyéb'),
]


class DentalWorkLog(models.Model):
    _name = 'dental.work.log'
    _description = 'Dental Work Log'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

    _sql_constraints = [
        ('dentari_lab_pieces_positive', 'CHECK(pieces >= 1)', 'Darabszám legalább 1 kell legyen.'),
        ('dentari_lab_price_non_negative', 'CHECK(price_per_piece >= 0)', 'Egységár nem lehet negatív.'),
    ]

    name: str = fields.Char(
        compute='_compute_name',
        store=True,
    )
    date: object = fields.Date(
        string='Dátum',
        required=True,
        default=fields.Date.context_today,
        tracking=True,
        index=True,
    )
    partner_id: object = fields.Many2one(
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
    tooth_color: str = fields.Selection(
        selection=VITA_COLORS,
        string='Fogszín (VITA)',
    )
    work_type: str = fields.Selection(
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
    price_per_piece: float = fields.Float(
        string='Egységár (Ft/db)',
        required=True,
        default=5000,
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
    user_id: object = fields.Many2one(
        'res.users',
        string='Rögzítő',
        default=lambda self: self.env.user,
        index=True,
    )

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

    @api.model_create_multi
    def create(self, vals_list):
        return super().create(vals_list)
