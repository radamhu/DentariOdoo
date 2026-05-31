# DentariOdoo — System Design Document

**Project:** DentariOdoo  
**Product:** Odoo 18 ERP for dental laboratory operations  
**Authors:** Dentari Development Team  
**Status:** Draft — Milestone 1  
**Last updated:** 2026-05-22

---

## Table of Contents

1. [Purpose and Scope](#1-purpose-and-scope)
2. [High Level Design (HLD)](#2-high-level-design)
   - 2.1 [System Context](#21-system-context)
   - 2.2 [User Roles and Actors](#22-user-roles-and-actors)
   - 2.3 [Module Boundaries](#23-module-boundaries)
   - 2.4 [Data Flow — Work Sheet Entry](#24-data-flow--work-sheet-entry)
3. [System Level Design (SLD)](#3-system-level-design)
   - 3.1 [Custom Module: dentari_lab](#31-custom-module-dentari_lab)
   - 3.2 [Data Model](#32-data-model)
   - 3.3 [Security and Access Control](#33-security-and-access-control)
   - 3.4 [Views and UI Specification](#34-views-and-ui-specification)
   - 3.5 [Business Logic](#35-business-logic)
   - 3.6 [Selection Field Constants](#36-selection-field-constants)
4. [Milestone Roadmap](#4-milestone-roadmap)
5. [Open Questions and Decisions Log](#5-open-questions-and-decisions-log)

---

## 1. Purpose and Scope

### 1.1 Background

DentariOdoo replaces a bespoke Streamlit + FastAPI application (`Dentari`) used by a dental laboratory to track daily work output, manage courier deliveries to dental clinics, and produce monthly revenue reports.

The decision to migrate to Odoo 18 is driven by:
- Native invoicing, partner management, and reporting infrastructure
- Eliminating custom API maintenance overhead
- Role-based access and audit logging out of the box
- Multi-instance (multi-client clinic) support

### 1.2 Scope of this document

This document covers the design of the **`dentari_lab` Odoo custom module** (Milestone 1). It is intended as the reference for all development decisions made in this repository.

### 1.3 Out of scope

- Odoo core modules (accounting, inventory, HR) — referenced but not designed here
- Mobile application
- Third-party integrations (payment gateways, external SMTP beyond relay config)

---

## 2. High Level Design

### 2.1 System Context

```
┌─────────────────────────────────────────────────────────────────┐
│                        Dental Laboratory                        │
│                                                                 │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────────┐  │
│  │  Lab Tech    │    │  Lab Manager │    │    Courier       │  │
│  │  (Technician)│    │  (Owner)     │    │  (Delivery)      │  │
│  └──────┬───────┘    └──────┬───────┘    └────────┬─────────┘  │
│         │                   │                     │            │
│         └───────────────────┴─────────────────────┘            │
│                             │                                   │
│              ┌──────────────▼──────────────┐                   │
│              │        Odoo 18 Web UI        │                   │
│              │    (dentari_lab module)       │                   │
│              └──────────────┬───────────────┘                   │
│                             │ ORM                               │
│              ┌──────────────▼──────────────┐                   │
│              │          PostgreSQL          │                   │
│              └─────────────────────────────┘                   │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 User Roles and Actors

| Role | Odoo Group | Typical Actions |
|---|---|---|
| **Lab Technician** | `dentari_lab.group_lab_technician` | Create work logs, view own records |
| **Lab Manager** | `dentari_lab.group_lab_manager` | Full CRUD on all records, run reports |
| **Courier** | `dentari_lab.group_courier` | Read delivery context (Milestone 3) |
| **Owner / Admin** | `base.group_system` | System configuration, user management |

### 2.3 Module Boundaries

```
Odoo 18 Instance
├── base                    (users, partners, companies)
├── mail                    (chatter, activity tracking)
├── web                     (web client)
└── dentari_lab             ← our custom module
    ├── dental.work.log     (core entity: daily work entries)
    ├── [M2] dashboard      (aggregated KPIs)
    ├── [M2] import wizard  (Excel/CSV with Hungarian headers)
    ├── [M3] courier model  (delivery assignments)
    └── [M4] invoicing      (account.move bridge)
```

Items in `[Mx]` brackets are planned in future milestones and not implemented yet.

### 2.4 Data Flow — Work Sheet Entry

```
Lab Technician
     │
     │  1. Open "Új Munkalap" form
     ▼
Odoo Form View (dental.work.log)
     │
     │  2. Fill: date, partner (clinic), patient, tooth pos/color,
     │          work type, pieces, price/piece, notes
     │
     │  3. Click Save
     ▼
dental.work.log.create()           ← ORM write
     │
     ├── _compute_total_revenue()  ← pieces × price_per_piece → stored
     ├── mail.thread tracking      ← records field changes for history
     │
     ▼
PostgreSQL (dental_work_log table)
```

---

## 3. System Level Design

### 3.1 Custom Module: dentari_lab

**Module identifier:** `dentari_lab`  
**Odoo version:** 18.0  
**Dependencies:** `['base', 'mail']`  
**Category:** `Dental / Laboratory`

Directory layout:

```
addons/dentari_lab/
├── __manifest__.py
├── __init__.py
├── models/
│   ├── __init__.py
│   └── dental_work_log.py
├── views/
│   ├── dental_work_log_views.xml   # form, list, search, action
│   └── menus.xml
├── security/
│   ├── groups.xml
│   ├── ir.model.access.csv
│   └── record_rules.xml            # technician can only see own records
└── data/
    └── (empty in M1 — no seed data required)
```

### 3.2 Data Model

#### 3.2.1 dental.work.log

Maps to the `dental_work_log` PostgreSQL table. Corresponds to the `DentalWorkLog` SQLAlchemy model in the legacy Dentari application.

| Field | Odoo type | DB column | Constraints | Notes |
|---|---|---|---|---|
| `id` | `Integer` (auto) | `id` | PK | |
| `date` | `Date` | `date` | NOT NULL, default=today | Indexed |
| `partner_id` | `Many2one(res.partner)` | `partner_id` | NOT NULL | Clinic; replaces free-text `client_name` |
| `patient_name` | `Char(100)` | `patient_name` | nullable | Optional |
| `tooth_position` | `Char(50)` | `tooth_position` | nullable | FDI notation, e.g. `16-14`, `21.22.23` |
| `tooth_color` | `Selection` | `tooth_color` | nullable | VITA scale — see §3.6 |
| `work_type` | `Selection` | `work_type` | nullable | See §3.6 |
| `pieces` | `Integer` | `pieces` | NOT NULL, ≥1, ≤100 | |
| `price_per_piece` | `Float` | `price_per_piece` | NOT NULL, ≥0, ≤500000 | HUF per piece |
| `total_revenue` | `Float` | `total_revenue` | computed, stored | `pieces × price_per_piece` |
| `notes` | `Text` | `notes` | nullable, max 500 chars | |
| `user_id` | `Many2one(res.users)` | `user_id` | nullable | Who created the entry |
| `create_date` | `Datetime` (auto) | `create_date` | Odoo-managed | |
| `write_date` | `Datetime` (auto) | `write_date` | Odoo-managed | |

**Mixins applied:**
- `mail.thread` — enables chatter and per-field change tracking
- `mail.activity.mixin` — enables scheduling follow-up activities

**Tracked fields** (appear in chatter history):
`date`, `partner_id`, `work_type`, `pieces`, `price_per_piece`

**Python model sketch:**

```python
class DentalWorkLog(models.Model):
    _name = 'dental.work.log'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Dental Work Log (Munkalap)'
    _order = 'date desc, id desc'

    name = fields.Char(
        compute='_compute_name', store=True,
    )  # display name: "2026-05-22 / Smile Dental Kft."

    date = fields.Date(
        required=True, default=fields.Date.today, tracking=True,
        index=True,
    )
    partner_id = fields.Many2one(
        'res.partner', string='Megrendelő (Klinika)',
        required=True, tracking=True, index=True,
        domain=[('is_company', '=', True)],
    )
    patient_name = fields.Char('Páciens neve', size=100)
    tooth_position = fields.Char('Fogpozíció (FDI)', size=50)
    tooth_color = fields.Selection(
        selection='_get_vita_colors', string='Fogszín (VITA)',
    )
    work_type = fields.Selection(
        selection='_get_work_types', string='Munka típusa',
        tracking=True,
    )
    pieces = fields.Integer(
        'Darabszám', required=True, default=1,
    )
    price_per_piece = fields.Float(
        'Egységár (Ft/db)', required=True, default=5000,
        digits=(10, 0),
    )
    total_revenue = fields.Float(
        'Összeg (Ft)', compute='_compute_total_revenue',
        store=True, digits=(10, 0), readonly=True,
    )
    notes = fields.Text('Megjegyzések')
    user_id = fields.Many2one(
        'res.users', string='Rögzítő',
        default=lambda self: self.env.user, index=True,
    )
```

#### 3.2.2 Constraints

```python
_sql_constraints = [
    ('pieces_positive', 'CHECK(pieces >= 1)', 'Darabszám legalább 1 kell legyen.'),
    ('price_non_negative', 'CHECK(price_per_piece >= 0)', 'Egységár nem lehet negatív.'),
]
```

Python-level validation (via `@api.constrains`):
- `pieces` ≤ 100
- `price_per_piece` ≤ 500,000
- `tooth_position` format: digits, commas, dots, hyphens only

#### 3.2.3 Indexes

PostgreSQL indexes created by Odoo ORM for `index=True` fields, plus the implicit PK index. Additional composite index to consider in Milestone 2 if query profiling reveals slow monthly summary queries:

```sql
CREATE INDEX idx_work_log_date_partner
  ON dental_work_log (date, partner_id);
```

### 3.3 Security and Access Control

#### Groups hierarchy

```
base.group_user
    └── dentari_lab.group_lab_technician
            └── dentari_lab.group_lab_manager
```

Lab Manager inherits all Technician permissions and adds delete + unrestricted record access.

#### Model access (ir.model.access.csv)

```
id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink
access_work_log_manager,work log manager,model_dental_work_log,dentari_lab.group_lab_manager,1,1,1,1
access_work_log_technician,work log technician,model_dental_work_log,dentari_lab.group_lab_technician,1,1,1,0
```

#### Record rules

Technicians are restricted to records they created:

```xml
<record model="ir.rule" id="rule_work_log_own_records">
    <field name="name">Work Log: technician sees own records</field>
    <field name="model_id" ref="model_dental_work_log"/>
    <field name="groups" eval="[(4, ref('dentari_lab.group_lab_technician'))]"/>
    <field name="domain_force">[('user_id', '=', user.id)]</field>
    <field name="perm_read" eval="True"/>
    <field name="perm_write" eval="True"/>
    <field name="perm_create" eval="True"/>
    <field name="perm_unlink" eval="False"/>
</record>
```

Lab Managers have no domain restriction (global rule omitted = full access).

### 3.4 Views and UI Specification

#### Form view layout

```
┌─────────────────────────────────────────────────────────────────┐
│  [Breadcrumb] Munkalapok / Új Munkalap                          │
│                                                                 │
│  Összeg: 15,000 Ft          [Mentés]  [Elvetés]                 │
├─────────────────────────────────────────────────────────────────┤
│  DÁTUM          │  MEGRENDELŐ (KLINIKA)                         │
│  2026-05-22     │  Smile Dental Kft.             [▼]            │
├─────────────────────────────────────────────────────────────────┤
│  Col 1 (left)               │  Col 2 (right)                   │
│  ─────────────────────────  │  ─────────────────────────────── │
│  Páciens neve               │  Fogszín (VITA)                  │
│  [Kovács János            ] │  [A2                        ▼]   │
│                             │                                   │
│  Fogpozíció (FDI)           │  Munka típusa                    │
│  [16, 15, 14              ] │  [Korona                    ▼]   │
│                             │                                   │
│                             │  Darabszám       Egységár (Ft)   │
│                             │  [   3    ]      [   5,000  ]    │
├─────────────────────────────────────────────────────────────────┤
│  Megjegyzések                                                   │
│  [                                                           ]  │
│  [                                                           ]  │
├─────────────────────────────────────────────────────────────────┤
│  Chatter / Előzmények                                           │
│  ● Adam Ferenc — 2026-05-22 10:31                               │
│    Munka típusa: (üres) → Korona                                │
└─────────────────────────────────────────────────────────────────┘
```

#### List view columns

`date` | `partner_id` | `patient_name` | `work_type` | `pieces` | `price_per_piece` | `total_revenue`

Optional column: `user_id` (visible to managers only via `groups` attribute).

Sum decorations on `pieces` and `total_revenue` for daily/filtered totals.

#### Search view

**Filters (predefined):**
- Ma (`date = today`)
- E hét (`date >= start_of_week`)
- E hónap (`date >= start_of_month`)

**Group by:**
- Megrendelő (`partner_id`)
- Munka típusa (`work_type`)
- Dátum (`date:day` / `:week` / `:month`)

**Searchbar fields:**
- `partner_id` (M2O name search)
- `patient_name`
- `notes`

#### Menu structure

```
Dentari Lab (top-level menu)
├── Munkalapok              → list+form action, no default filter
└── Mai munkák              → list+form action, filter: date=today
```

### 3.5 Business Logic

#### _compute_total_revenue

```python
@api.depends('pieces', 'price_per_piece')
def _compute_total_revenue(self):
    for rec in self:
        rec.total_revenue = rec.pieces * rec.price_per_piece
```

Stored (`store=True`) so it is queryable and sortable in list views and future reports without re-computation at read time.

#### _compute_name

```python
@api.depends('date', 'partner_id')
def _compute_name(self):
    for rec in self:
        date_str = rec.date.strftime('%Y-%m-%d') if rec.date else '?'
        partner_str = rec.partner_id.name if rec.partner_id else 'N/A'
        rec.name = f"{date_str} / {partner_str}"
```

Used as the display name in breadcrumbs and chatter references.

#### @api.constrains validation

```python
@api.constrains('pieces')
def _check_pieces(self):
    for rec in self:
        if not (1 <= rec.pieces <= 100):
            raise ValidationError('Darabszám 1 és 100 között kell legyen.')

@api.constrains('price_per_piece')
def _check_price(self):
    for rec in self:
        if not (0 <= rec.price_per_piece <= 500_000):
            raise ValidationError('Egységár 0 és 500 000 Ft között kell legyen.')
```

### 3.6 Selection Field Constants

Both lists are defined as module-level tuples in `dental_work_log.py` and referenced via `selection=` parameter.

**VITA color scale:**

```python
VITA_COLORS = [
    ('A1','A1'), ('A2','A2'), ('A3','A3'), ('A3.5','A3.5'), ('A4','A4'),
    ('B1','B1'), ('B2','B2'), ('B3','B3'), ('B4','B4'),
    ('C1','C1'), ('C2','C2'), ('C3','C3'), ('C4','C4'),
    ('D2','D2'), ('D3','D3'), ('D4','D4'),
    ('BL1','BL1'), ('BL2','BL2'), ('BL3','BL3'), ('BL4','BL4'),
]
```

**Work types:**

```python
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
```

---

## 4. Milestone Roadmap

| Milestone | Scope | Status |
|---|---|---|
| **M1 — Work Log CRUD** | `dental.work.log` model, form + list + search views, security groups, record rules | In Progress |
| **M2 — Statistics & Import** | Dashboard KPIs (today/week/month), Excel/CSV import wizard with Hungarian column mapping | Planned |
| **M3 — Courier Module** | Delivery assignment model, route tracking, courier-facing view | Planned |
| **M4 — Invoicing Bridge** | Generate `account.move` draft invoices from grouped work logs | Planned |
| **M5 — PDF Reports** | Monthly lab report, per-client breakdown, Pareto analysis | Planned |

---

## 5. Open Questions and Decisions Log

| # | Question | Decision | Date | Rationale |
|---|---|---|---|---|
| 1 | Should clinics use `res.partner` or a custom model? | `res.partner` | 2026-05-22 | Native autocomplete, deduplication, future invoicing compatibility |
| 2 | Invoicing integration in M1? | Deferred to M4 | 2026-05-22 | Keep M1 scope minimal; standalone tracking first |
| 3 | Undo functionality (matching legacy app)? | Replaced by `mail.thread` chatter tracking | 2026-05-22 | Chatter provides field-level history; explicit undo adds complexity without proportional value |
| 4 | `tooth_color` and `work_type` as Selection or as related models? | Selection (static list) | 2026-05-22 | Lists are stable dental standards (VITA scale, lab work types); a configurable model would add UI overhead for no gain |
| 5 | `total_revenue` stored or computed-only? | Stored (`store=True`) | 2026-05-22 | Required for efficient GROUP BY in monthly reports and list view column sums |

---

## 6. Module Quick Reference

**Module ID:** `dentari_lab`  
**Odoo version:** 18.0.1.0.0  
**Dependencies:** `base`, `mail`  
**Category:** Dental / Laboratory

```
addons/dentari_lab/
├── __manifest__.py
├── __init__.py
├── models/
│   ├── __init__.py
│   └── dental_work_log.py      # core model + business logic
├── views/
│   ├── dental_work_log_views.xml
│   └── menus.xml
├── security/
│   ├── groups.xml
│   ├── ir.model.access.csv
│   └── record_rules.xml
└── data/
```

### Data Model

Core entity: `dental.work.log` → table `dental_work_log`

| Field | Type | Notes |
|-------|------|-------|
| `date` | Date | Required, default today, indexed |
| `partner_id` | Many2one → res.partner | Clinic, required, companies only |
| `patient_name` | Char(100) | Optional |
| `tooth_position` | Char(50) | FDI notation, validated (digits/comma/dot/hyphen) |
| `tooth_color` | Selection | VITA scale — A1–A4, B1–B4, C1–C4, D2–D4, BL1–BL4 |
| `work_type` | Selection | Korona, Híd, Implant, Facet, Ideiglenes, Javítás, Monolitikus, Egyéb |
| `pieces` | Integer | Required, 1–100, default 1 |
| `price_per_piece` | Float (HUF) | Required, 0–500 000, default 5 000 Ft |
| `total_revenue` | Float (computed) | `pieces × price_per_piece`, stored |
| `notes` | Text | Optional |
| `user_id` | Many2one → res.users | Who created the entry |

**Mixins:** `mail.thread` (chatter + field tracking) · `mail.activity.mixin`  
**Tracked fields:** `date`, `partner_id`, `work_type`, `pieces`, `price_per_piece`

### Security & Roles

```
base.group_user
    └── group_lab_technician    — create/read/write own records
            └── group_lab_manager   — full CRUD on all records
```

| Permission | Lab Technician | Lab Manager |
|------------|:--------------:|:-----------:|
| Read own records | ✓ | ✓ |
| Read all records | — | ✓ |
| Create | ✓ | ✓ |
| Edit | ✓ (own) | ✓ |
| Delete | — | ✓ |

Record rule: technicians are domain-restricted to `user_id = uid`.

### UI

**Menu:**
```
Dentari Lab
├── Munkalapok     → all records, full search
└── Mai munkák     → today's records
```

**List view columns:** Date · Clinic · Patient · Work Type · Pieces · Unit Price · Total  
**Column sums** on Pieces and Total Revenue.

**Search:** predefined filters (Today / This Week / This Month), group-by (Clinic / Work Type / Date), free-text on clinic, patient, notes.
