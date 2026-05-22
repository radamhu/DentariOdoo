# TICKET-001 — Implement `dentari_lab` Odoo Custom Module (M1)

| Field | Value |
|---|---|
| **Type** | Feature |
| **Priority** | High |
| **Milestone** | M1 — Work Log CRUD |
| **Assignee** | — |
| **Reporter** | Dentari Development Team |
| **Created** | 2026-05-22 |
| **Status** | Open |
| **Design ref** | [DESIGN.md §3](./DESIGN.md#3-system-level-design) |

---

## Summary

Implement the `dentari_lab` Odoo 18 custom addon as specified in [DESIGN.md §3](./DESIGN.md#3-system-level-design). This delivers the core `dental.work.log` model, its form/list/search views, role-based security, and all supporting business logic. It is the foundational module; all future milestones (M2–M5) depend on it.

---

## Background

DentariOdoo replaces a bespoke Streamlit + FastAPI app. M1 scope is deliberately minimal: a single model that lets lab technicians record daily work output and lets the lab manager view all records and run filters. No invoicing, no import wizard, no courier model — those are deferred to M2–M4.

---

## Acceptance Criteria

### AC-1 Module scaffold
- [ ] Directory layout matches exactly:
  ```
  addons/dentari_lab/
  ├── __manifest__.py
  ├── __init__.py
  ├── models/
  │   ├── __init__.py
  │   └── dental_work_log.py
  ├── views/
  │   ├── dental_work_log_views.xml
  │   └── menus.xml
  ├── security/
  │   ├── groups.xml
  │   ├── ir.model.access.csv
  │   └── record_rules.xml
  └── data/
  ```
- [ ] `__manifest__.py` declares `name`, `version = '18.0.1.0.0'`, `depends = ['base', 'mail']`, `category = 'Dental / Laboratory'`, and lists all XML/CSV data files.
- [ ] `data` list load order in manifest is **`groups.xml` → `ir.model.access.csv` → `record_rules.xml` → views** — groups must exist before access rules reference them, and security files must precede view files.
- [ ] Module installs cleanly on a fresh Odoo 18 database with no errors or warnings.

### AC-2 Data model — `dental.work.log`
- [ ] All fields defined per [DESIGN.md §3.2.1](./DESIGN.md#321-dentalworklog) with correct types, sizes, and required flags.
- [ ] `_order = 'date desc, id desc'`
- [ ] Mixins `mail.thread` and `mail.activity.mixin` applied.
- [ ] `tracking=True` on `date`, `partner_id`, `work_type`, `pieces`, `price_per_piece`.
- [ ] `partner_id` domain restricts to `is_company = True`.
- [ ] `price_per_piece` default is `5000`, `digits=(10, 0)`.
- [ ] `pieces` default is `1`.
- [ ] `user_id` defaults to `self.env.user`.
- [ ] `index=True` on `date`, `partner_id`, `user_id`.
- [ ] `@api.model_create_multi` override present (even if it only calls `super()`) — required for Odoo 18 batch-creation compatibility.
- [ ] Type hints on field assignments are used (e.g., `name: str = fields.Char(...)`) — recommended in v18, mandatory in v19.

### AC-3 SQL constraints
- [ ] `_sql_constraints` uses the **list-of-tuples syntax** — `models.Constraint()` class is v19 only and must NOT be used here.
- [ ] `CHECK(pieces >= 1)` with message "Darabszám legalább 1 kell legyen."
- [ ] `CHECK(price_per_piece >= 0)` with message "Egységár nem lehet negatív."
- [ ] Constraint names follow the `<module>_<field>_<check>` convention (e.g., `dentari_lab_pieces_positive`) to avoid upgrade collisions.

### AC-4 Python-level validation (`@api.constrains`)
- [ ] `pieces` raises `ValidationError` if outside `[1, 100]`.
- [ ] `price_per_piece` raises `ValidationError` if outside `[0, 500000]`.
- [ ] `tooth_position` raises `ValidationError` if value contains characters other than digits, commas, dots, and hyphens.

### AC-5 Computed fields
- [ ] `total_revenue` = `pieces × price_per_piece`, `store=True`, `readonly=True`.
- [ ] `name` = `"YYYY-MM-DD / <partner name>"`, `store=True`, recalculates when `date` or `partner_id` changes.

### AC-6 Selection field constants
- [ ] `VITA_COLORS` tuple defined at module level in `dental_work_log.py` with all 20 values (A1–A4, B1–B4, C1–C4, D2–D4, BL1–BL4) per [DESIGN.md §3.6](./DESIGN.md#36-selection-field-constants).
- [ ] `WORK_TYPES` tuple defined at module level with 8 values: `korona`, `hid`, `implant`, `facet`, `ideiglenes`, `javitas`, `monolitikus`, `egyeb`.
- [ ] Both referenced via `selection=` parameter (not hardcoded in field definitions).

### AC-7 Security — groups
- [ ] `groups.xml` defines `group_lab_technician` (inherits `base.group_user`) and `group_lab_manager` (inherits `group_lab_technician`).

### AC-8 Security — model access
- [ ] `ir.model.access.csv` grants Lab Manager: read/write/create/unlink.
- [ ] `ir.model.access.csv` grants Lab Technician: read/write/create, **no** unlink.

### AC-9 Security — record rules
- [ ] `record_rules.xml` restricts Lab Technicians to records where `user_id = uid` for read, write, and create.
- [ ] Lab Manager rule is explicitly defined with `domain_force="[(1, '=', 1)]"` (full access) — preferred over omission for clarity and auditability.
- [ ] The `model_id` external ID in all security files uses the `model_dental_work_log` format (dots → underscores, prefixed with `model_`).

### AC-10 Form view
- [ ] Layout matches the wireframe in [DESIGN.md §3.4](./DESIGN.md#34-views-and-ui-specification): header with `total_revenue` stat button, full-width `date` + `partner_id` row, two-column body (`patient_name`, `tooth_position` left; `tooth_color`, `work_type`, `pieces`, `price_per_piece` right), `notes` textarea, chatter footer.
- [ ] `total_revenue` is read-only in the form.
- [ ] **No `attrs=` attribute used anywhere in XML** — `attrs` was removed in v17. Use direct attributes: `invisible="expr"`, `readonly="expr"`, `required="expr"`.
- [ ] Chatter block uses the explicit three-field pattern (`message_follower_ids`, `activity_ids`, `message_ids`) inside `<div class="oe_chatter">` — not the `<chatter/>` shorthand.

### AC-11 List view
- [ ] Columns: `date`, `partner_id`, `patient_name`, `work_type`, `pieces`, `price_per_piece`, `total_revenue`.
- [ ] `user_id` column present but visible only to `group_lab_manager` (via `groups` attribute).
- [ ] `sum` decoration on `pieces` and `total_revenue`.

### AC-12 Search view
- [ ] Predefined filters: "Ma" (`date = today`), "E hét" (`date >= start_of_week`), "E hónap" (`date >= start_of_month`).
- [ ] Group-by options: `partner_id`, `work_type`, `date` (day / week / month).
- [ ] Searchbar field targets: `partner_id`, `patient_name`, `notes`.

### AC-13 Menu structure
- [ ] Top-level menu item "Dentari Lab".
- [ ] Sub-item "Munkalapok" → list+form action, no default filter.
- [ ] Sub-item "Mai munkák" → list+form action, default filter `date = today`.

---

## Technical Specification

All implementation details are in [DESIGN.md §3](./DESIGN.md#3-system-level-design). Reproduced here for traceability:

- **Model name:** `dental.work.log` → table `dental_work_log`
- **Odoo version:** 18.0
- **Python model base classes:** `models.Model`, `mail.thread`, `mail.activity.mixin`
- **Composite index** (`date, partner_id`) deferred to M2 pending query profiling; do not add in this ticket.
- **No seed data** required in `data/` for M1.
- **No migrations** needed (fresh install only in M1).

### Odoo 18 — Breaking Changes to Avoid

| Removed / deprecated pattern | Correct v18 pattern |
|---|---|
| `track_visibility='onchange'` (removed v15) | `tracking=True` on the field |
| `attrs="{'invisible': [...]}"` (removed v17) | `invisible="state == 'draft'"` direct attribute |
| `@api.multi` (removed v15) | plain `def method(self):` |
| `models.Constraint()` for SQL constraints | `_sql_constraints` list-of-tuples (v19 only for class form) |
| `company_ids` in record rule domains | `allowed_company_ids` |
| Raw SQL with `%s` string formatting | `SQL()` builder from `odoo.tools` |

### Odoo 18 — Recommended Patterns

- **Type hints** on field declarations: `name: str = fields.Char(...)` — recommended in v18, mandatory in v19; start using now for forward compatibility.
- **`@api.model_create_multi`** signature even when only calling `super()`.
- **`digits=(10, 0)`** on `price_per_piece` and `total_revenue` for HUF integer precision (per design).
- **`_sql_constraints` naming:** `<module>_<field>_<check>` — e.g., `dentari_lab_pieces_positive`.

---

## Out of Scope (do not implement in this ticket)

- Dashboard KPIs or statistics views (M2)
- Excel/CSV import wizard (M2)
- Courier model (M3)
- `account.move` invoicing bridge (M4)
- PDF reports (M5)
- Composite index `idx_work_log_date_partner` (M2, pending profiling)
- `Courier` security group (referenced in design but not needed until M3)

---

## Definition of Done

- [ ] All acceptance criteria above are checked.
- [ ] Module installs on a clean Odoo 18 database without errors.
- [ ] A Lab Technician user can create a `dental.work.log` record, save it, and see it in the list view.
- [ ] A Lab Technician cannot see records created by another technician.
- [ ] A Lab Manager can see all records and delete them.
- [ ] `total_revenue` updates automatically when `pieces` or `price_per_piece` changes.
- [ ] Chatter shows field-level history for tracked fields.
- [ ] Python `ValidationError` fires for pieces > 100, price > 500,000, and malformed tooth position.
- [ ] Code reviewed and merged to `dev` branch.
- [ ] Smoke test passes in the CI pipeline (login + create one record).
