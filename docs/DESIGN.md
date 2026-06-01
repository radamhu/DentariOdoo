# DentariOdoo — System Design Document

**Project:** DentariOdoo  
**Product:** Odoo 18 ERP for dental laboratory operations  
**Authors:** Dentari Development Team  
**Status:** Active — Milestone 5a done, M5b deferred  
**Last updated:** 2026-06-01

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
    ├── [M4] invoicing        (account.move bridge) ✓ done
    ├── [M5a] monthly wizard  (period PDF summary per partner) ✓ done
    └── [M5b] monthly wizard+ (draft account.move per partner) deferred
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

#### 3.2.2 dental.monthly.wizard (TransientModel)

Period-based wizard that collects all `dental.work.log` records for a given month and produces a QWeb PDF summary per partner.

| Field | Odoo type | Notes |
|---|---|---|
| `period_year` | `Integer` | Default: current year |
| `period_month` | `Selection` (1–12) | Default: current month; Hungarian month names |
| `period_label` | `Char` (computed) | e.g. `"2026. május"` |
| `partner_ids` | `Many2many(res.partner)` | Optional filter; empty = all partners with logs |
| `preview_ids` | `One2many(dental.monthly.wizard.line)` | Populated by `_onchange_period` and rebuilt by `action_print_summary` |

Key design constraint: `preview_ids` is `readonly="1"` in the form view. Odoo does not include readonly fields in the `write()` payload sent on button click. `action_print_summary` therefore always re-queries `dental.work.log` directly from `period_year`/`period_month` and rebuilds `preview_ids` before rendering the report — it never trusts the DB state of `preview_ids`.

#### 3.2.3 dental.monthly.wizard.line (TransientModel)

One row per partner in the wizard preview.

| Field | Odoo type | Notes |
|---|---|---|
| `wizard_id` | `Many2one(dental.monthly.wizard)` | Parent, cascade delete |
| `partner_id` | `Many2one(res.partner)` | Clinic |
| `log_count` | `Integer` | Count of work logs in the period for this partner |
| `total_amount` | `Float` | `SUM(total_revenue)` |
| `period_year` | `Integer` | Copied from wizard at line creation — see design note below |
| `period_month` | `Char` | Copied from wizard at line creation — see design note below |
| `log_ids` | `Many2many(dental.work.log)` | **Computed** — queries live from `period_year`, `period_month`, `partner_id`; never stored in a relation table |

`period_year` and `period_month` are **copied onto the line** (not read via `wizard_id.*`) so that `_compute_log_ids` works correctly on virtual (onchange) records. When the user changes the period in the wizard form, the wizard DB record is not updated until the user clicks a button. If `_compute_log_ids` read from `wizard_id.period_year`, it would get the stale DB value and return empty results. Reading from `line.period_year` (populated by `_build_preview_vals` during the onchange) always gives the correct period. See decisions log §5 entries 11–13.

#### 3.2.4 Constraints

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

#### 3.2.5 Indexes

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
├── Mai munkák              → list+form action, filter: date=today
└── Havi Összesítő          → opens dental.monthly.wizard dialog (Manager only)
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

#### action_print_summary (dental.monthly.wizard)

Always re-queries `dental.work.log` from the period fields, rebuilds `preview_ids` in the same transaction, then passes `self` to the QWeb report action. The check for "no logs" is done via `_search_logs()`, not via `self.preview_ids`, because `preview_ids` may be stale (readonly in view → not sent back by client on button click).

```python
def action_print_summary(self):
    self.ensure_one()
    partner_ids = self.partner_ids.ids if self.partner_ids else []
    logs = self._search_logs(self.period_year, int(self.period_month), partner_ids)
    if not logs:
        raise UserError(_('Nincs munkalap a kiválasztott időszakban.'))
    self.write({'preview_ids': [(5, 0, 0)] + self._build_preview_vals(logs)})
    return self.env.ref('dentari_lab.action_report_monthly_summary').report_action(self)
```

#### _compute_log_ids (dental.monthly.wizard.line)

Computed Many2many — queries `dental.work.log` live from `wizard_id.period_year`, `wizard_id.period_month`, and `partner_id`. Never stored in a relation table. Ensures the detail popup and the report template always return correct data whether the line record is persisted or virtual (onchange).

```python
@api.depends('wizard_id.period_year', 'wizard_id.period_month', 'partner_id')
def _compute_log_ids(self):
    for line in self:
        wizard = line.wizard_id
        if not wizard.period_month or not line.partner_id:
            line.log_ids = self.env['dental.work.log']
            continue
        date_from = date(wizard.period_year, int(wizard.period_month), 1)
        date_to = date_from + relativedelta(months=1) - timedelta(days=1)
        line.log_ids = self.env['dental.work.log'].search([
            ('date', '>=', date_from),
            ('date', '<=', date_to),
            ('partner_id', '=', line.partner_id.id),
        ], order='date, id')
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
| **M1 — Work Log CRUD** | `dental.work.log` model, form + list + search views, security groups, record rules | Done |
| **M2 — Statistics & Import** | Dashboard KPIs (today/week/month), Excel/CSV import wizard with Hungarian column mapping | Planned |
| **M3 — Courier Module** | Delivery assignment model, route tracking, courier-facing view | Planned |
| **M4 — Invoicing Bridge** | `dental.invoice.wizard` — manual multi-select → draft `account.move` per partner | Done |
| **M5a — Monthly Statement (PDF)** | `dental.monthly.wizard` — period-based auto-collect → QWeb PDF summary per partner; lab manager emails PDF, partner confirms offline, invoice in 3rd party system | Done |
| **M5b — Monthly Statement (Invoice)** | Extend M5a wizard with "Számlák létrehozása" button → draft `account.move` per partner; replaces 3rd party invoicing; triggers NAV reporting on post — **no deadline, activates when Odoo invoicing goes live** | Deferred |
| **M6 — CRM / Lead Pipeline** | Replace lab_manager's Excel partner prospecting; `crm` module — no deadline set | Deferred |

---

## 5. Open Questions and Decisions Log

| # | Question | Decision | Date | Rationale |
|---|---|---|---|---|
| 1 | Should clinics use `res.partner` or a custom model? | `res.partner` | 2026-05-22 | Native autocomplete, deduplication, future invoicing compatibility |
| 2 | Invoicing integration in M1? | Deferred to M4 | 2026-05-22 | Keep M1 scope minimal; standalone tracking first |
| 3 | Undo functionality (matching legacy app)? | Replaced by `mail.thread` chatter tracking | 2026-05-22 | Chatter provides field-level history; explicit undo adds complexity without proportional value |
| 4 | `tooth_color` and `work_type` as Selection or as related models? | Selection (static list) | 2026-05-22 | Lists are stable dental standards (VITA scale, lab work types); a configurable model would add UI overhead for no gain |
| 5 | `total_revenue` stored or computed-only? | Stored (`store=True`) | 2026-05-22 | Required for efficient GROUP BY in monthly reports and list view column sums |
| 6 | Install `sale` module for month-end approval flow? | No — draft `account.move` is the approval document | 2026-05-31 | Partners receive PDF by email and confirm offline; no quotation/order split needed; `sale` adds overhead without value for this use case |
| 7 | Install `crm` module for partner prospecting? | Deferred (M6) | 2026-05-31 | Lab manager currently uses Excel; no deadline for migration; `crm` is self-contained and can be added later without affecting core billing flow |
| 8 | Custom approval model (`dental.monthly.statement`) vs draft invoice? | Draft `account.move` — Phase 2 only | 2026-05-31 | Draft→posted lifecycle already implements the approval state machine; custom model would duplicate this without adding value; not created in Phase 1 while 3rd party invoicing is active |
| 9 | Partner portal for approval? | Out of scope for M5 | 2026-05-31 | Partners confirm by email/phone; lab_manager manually posts the invoice; portal can be added in a future milestone without model changes |
| 10 | Create draft `account.move` in Phase 1 (before invoicing go-live)? | No — QWeb PDF only | 2026-05-31 | While a 3rd party system issues the real invoice, Odoo draft invoices would be misleading and risk backdated NAV reporting when eventually posted |
| 11 | `log_ids` on `dental.monthly.wizard.line`: stored Many2many or computed? | Computed | 2026-06-01 | A stored Many2many is only written when `action_print_summary` calls `write()`. Before the first print, the detail popup read from a virtual onchange record where `log_ids` was not in the client cache — always empty. A computed field queries `dental.work.log` live (period + partner), so the popup is correct before and after printing, with no DB state dependency. |
| 12 | Should `action_print_summary` rely on `self.preview_ids` for the "no data" check? | No — always re-query via `_search_logs()` | 2026-06-01 | `preview_ids` is `readonly="1"` in the form; Odoo excludes readonly fields from the `write()` payload on button click. If the user changed the period (onchange updated the client view) and then clicked print, the server-side `preview_ids` was still the initial (possibly empty) state from `create()`. Direct re-query from the non-readonly period fields is the only reliable check. |
| 13 | Should `_compute_log_ids` read the period from `wizard_id.*` or from line-local fields? | Line-local `period_year`/`period_month` fields | 2026-06-01 | Reading `wizard_id.period_year` queries the DB wizard record, which holds the original period until the user clicks a button. For virtual onchange lines (before any button click), this gives the wrong (stale) period → empty `log_ids`. Copying the period into each line during `_build_preview_vals` makes the compute self-contained and correct for both virtual and persisted line records. |

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
