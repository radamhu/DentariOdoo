# TICKET-006 — Monthly Statement Wizard (Havi Összesítő)

| Field | Value |
|---|---|
| **Type** | Feature |
| **Priority** | High |
| **Milestone** | M5 — Monthly Statement |
| **Assignee** | — |
| **Reporter** | Dentari Development Team |
| **Created** | 2026-05-31 |
| **Updated** | 2026-05-31 |
| **Status** | Open |
| **Design ref** | [DESIGN.md §4](./DESIGN.md#4-milestone-roadmap) |
| **Depends on** | TICKET-005 (M4 — Invoicing Bridge, done) |

---

## Summary

Period-based wizard that automatically collects all `dental.work.log` records for a given month, groups them by partner, and produces a **QWeb PDF summary report** (Havi Összesítő) per partner. The lab manager sends the PDF to each partner by email, waits for confirmation, and manually records payment in the external invoicing system.

Invoice creation inside Odoo is out of scope for this ticket — it is planned as a follow-up once Odoo invoicing goes live (see [Phase 2](#phase-2-future-odoo-invoicing-go-live) below).

---

## Background

TICKET-005 delivered an invoicing bridge (manual multi-select → draft `account.move`). For month-end billing workflow this is the wrong entry point: the lab currently issues invoices through a third-party system, not Odoo. The immediate need is a **printed summary** to send to partners for approval, not a draft invoice.

### Two-phase rollout

#### Phase 1 — Current scope (this ticket)

Odoo invoicing not yet active. The monthly summary is the sole output.

```
[hónap vége]
     ↓
wizard → időszak + partner szűrő
     ↓
QWeb PDF összesítő / partnerenként
     ↓
email → partner
     ↓
partner visszajelez → lab_manager rögzíti a 3rd party számlázóban
```

#### Phase 2 — Future (separate ticket, no deadline)

Odoo invoicing goes live. The wizard gains an invoice creation step on top of the existing PDF output.

```
[hónap vége]
     ↓
wizard → időszak + partner szűrő
     ↓
QWeb PDF összesítő (ugyanaz, mint 1. fázisban)
     ↓
email → partner visszajelez
     ↓
"Számlák létrehozása" → draft account.move / partnerenként
     ↓
lab_manager: "Confirm" → posted account.move → NAV
```

The Phase 1 wizard model and views are designed to accommodate Phase 2 without structural changes — the invoice creation button is simply not built yet.

### Architecture decisions

- **No `account.move` created in Phase 1** — draft invoices in Odoo would be misleading while the real invoice lives in a third-party system.
- **No `sale` module** — no quotation/order split needed.
- **No partner portal** — partners receive PDF by email and confirm offline.
- **Draft `account.move` as approval document** — Phase 2 only; draft = pending partner approval, posted = confirmed.

---

## Scope

### In scope (Phase 1 — this ticket)

- `dental.monthly.wizard` TransientModel — period-based, collects all logs for the period
- Wizard accessible from a new menu item "Havi Összesítő" (Manager only)
- Period selector: year + month
- Optional partner filter (empty → all partners with logs in the period)
- Preview table: one row per partner, log count, total amount
- **"Összesítő nyomtatása" button** → generates QWeb PDF report, one page per partner
- QWeb report template: period header, partner name, work log lines (date, patient, work type, pieces, unit price, total), grand total

### Out of scope (Phase 1)

- `account.move` creation — Phase 2
- NAV reporting — follows invoice posting, Phase 2
- Automatic/scheduled generation
- Partner portal / online approval
- CRM lead pipeline

---

## Data Model Changes

No new persistent model fields in Phase 1. The existing `dental.work.log` fields are sufficient.

### `dental.monthly.wizard` (new TransientModel)

| Field | Odoo type | Notes |
|---|---|---|
| `period_year` | `Integer` | Default: current year |
| `period_month` | `Selection` (1–12) | Default: current month; Hungarian month names |
| `partner_ids` | `Many2many('res.partner')` | Optional filter; empty = all partners |
| `preview_ids` | `One2many('dental.monthly.wizard.line', ...)` | Computed on `_onchange_period`, readonly |

### `dental.monthly.wizard.line` (new TransientModel, child)

| Field | Odoo type | Notes |
|---|---|---|
| `wizard_id` | `Many2one('dental.monthly.wizard')` | Parent |
| `partner_id` | `Many2one('res.partner')` | Clinic |
| `log_count` | `Integer` | Logs found for this partner in the period |
| `total_amount` | `Float` | `SUM(total_revenue)` |

**Core method sketch:**

```python
def _get_logs(self):
    date_from = date(self.period_year, self.period_month, 1)
    date_to = date_from + relativedelta(months=1) - timedelta(days=1)
    domain = [('date', '>=', date_from), ('date', '<=', date_to)]
    if self.partner_ids:
        domain.append(('partner_id', 'in', self.partner_ids.ids))
    return self.env['dental.work.log'].search(domain)

def action_print_summary(self):
    logs = self._get_logs()
    if not logs:
        raise UserError(_('Nincs munkalap a kiválasztott időszakban.'))
    return self.env.ref('dentari_lab.action_report_monthly_summary').report_action(self)
```

---

## View Changes

### New menu item

```
Dentari Lab
├── Munkalapok
├── Mai munkák
└── Havi Összesítő    ← ÚJ (group_lab_manager only)
```

### Wizard form layout

```
┌──────────────────────────────────────────────────────┐
│  Havi Összesítő                                      │
│                                                      │
│  Időszak:   [2026 ▼]  [Május ▼]                     │
│  Partner szűrő: [                          ] (opt.)  │
│                                                      │
│  ┌──────────────────────────────────────────────┐    │
│  │ Megrendelő        │ Munkalapok │ Összeg (Ft) │    │
│  │ Smile Dental Kft. │     12     │  84 000     │    │
│  │ Fehér Fogászat    │      7     │  49 000     │    │
│  └──────────────────────────────────────────────┘    │
│                                                      │
│  [Összesítő nyomtatása]              [Mégse]         │
└──────────────────────────────────────────────────────┘
```

### QWeb PDF report structure (per partner, per page)

```
┌──────────────────────────────────────────────────────┐
│  DENTARI LAB — HAVI ÖSSZESÍTŐ                        │
│  Időszak: 2026. május   │   Partner: Smile Dental    │
├──────────────────────────────────────────────────────┤
│  Dátum   │ Páciens │ Munka típusa │ db │ Egységár │ Összeg │
│ ─────────────────────────────────────────────────── │
│ 05-03    │ Kiss A. │ Korona       │  3 │  5 000   │ 15 000 │
│ 05-07    │ Nagy B. │ Híd          │  4 │  6 000   │ 24 000 │
│  ...                                                 │
├──────────────────────────────────────────────────────┤
│                              ÖSSZESEN:    84 000 Ft  │
└──────────────────────────────────────────────────────┘
```

---

## Files to Create or Modify

| File | Change |
|---|---|
| `dentari_lab/models/dental_monthly_wizard.py` | New — `dental.monthly.wizard` and `dental.monthly.wizard.line` |
| `dentari_lab/models/__init__.py` | Import `dental_monthly_wizard` |
| `dentari_lab/views/wizard_monthly_views.xml` | New — wizard form view + menu action |
| `dentari_lab/views/menus.xml` | Add "Havi Összesítő" menu item (Manager only) |
| `dentari_lab/report/report_monthly_summary.xml` | New — QWeb report template |
| `dentari_lab/report/report_monthly_summary_action.xml` | New — `ir.actions.report` record |
| `dentari_lab/security/ir.model.access.csv` | Add rows for new wizard models |
| `dentari_lab/__manifest__.py` | Add new files to `data` list |

---

## Acceptance Criteria

### AC-1 Menu access

- [ ] "Havi Összesítő" menu item visible to Lab Managers only.
- [ ] Lab Technicians do not see the menu item.

### AC-2 Period selector

- [ ] Year and month fields default to the current period.
- [ ] Month shown with Hungarian names (Január–December).

### AC-3 Preview computation

- [ ] Changing year or month re-computes `preview_ids` automatically (onchange).
- [ ] Preview shows one row per partner that has logs in the selected period.
- [ ] If `partner_ids` filter is set, only those partners appear.
- [ ] If no logs exist for the period, preview is empty and the print button raises `UserError`.

### AC-4 PDF report

- [ ] "Összesítő nyomtatása" generates a PDF report.
- [ ] Report contains one section per partner.
- [ ] Each section lists all work log lines for the period: date, patient name, work type, pieces, unit price, line total.
- [ ] Each section shows a partner-level grand total.
- [ ] Period and partner name appear in the section header.
- [ ] No `account.move` is created.

### AC-5 Odoo 18 compatibility

- [ ] No `attrs=` XML attributes.
- [ ] Module upgrades cleanly with `-u dentari_lab`.

---

## Phase 2 — Future: Odoo Invoicing Go-Live (separate ticket)

> **No deadline. To be planned when Odoo invoicing is activated.**

When the lab switches from the third-party invoicing system to Odoo, the wizard is extended with invoice creation. No structural model changes are required — Phase 1 already collects and groups the logs correctly.

### Additional scope (Phase 2)

- "Számlák létrehozása" button on the existing wizard form
- Creates one draft `account.move` per partner in `preview_ids`
- Each work log produces one `account.move.line` (same logic as TICKET-005)
- After creation: redirect to newly created draft invoices
- Lab manager uses Odoo "Send & Print" on each draft invoice to email the PDF
- Partner confirms → lab manager clicks "Confirm" → invoice posted → NAV reporting triggered

### Phase 2 design notes

- The QWeb summary PDF (Phase 1) and the Odoo invoice PDF serve the same communication purpose — in Phase 2 the Odoo draft invoice replaces the separate summary PDF for the partner-facing document.
- Draft `account.move` must **not** be created before NAV integration is active to avoid backdated invoice reporting compliance issues.
- `dental.work.log.invoice_id` (from TICKET-005) already exists; Phase 2 sets it when the draft is created.

---

## Definition of Done

- [ ] All Phase 1 acceptance criteria are checked.
- [ ] Lab Manager can open "Havi Összesítő", select a month, see the partner preview, and print the PDF summary.
- [ ] PDF contains correct lines, totals, and partner/period headers.
- [ ] No `account.move` records are created by this wizard.
- [ ] Module upgrades cleanly, smoke test passes.
- [ ] Code reviewed and merged to `develop` branch.
