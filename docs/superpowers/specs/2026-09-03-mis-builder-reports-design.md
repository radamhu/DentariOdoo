# MIS Builder Reports — Design Spec

**Date:** 2026-09-03
**Status:** Approved (pending spec file review)

## Purpose

Give the practice a monthly profitability view: Kiadások (expenses, Netto + Áfa)
against Dentari Lab revenue (Egységár × Darabszám = Összeg), using the OCA
`mis_builder` reporting engine.

## Context (existing code)

- **Kiadások** — [dental_quick_expense/models/account_move.py](../../../dental_quick_expense/models/account_move.py)
  extends `account.move` (vendor bills). Adds `expense_category_id` (computed,
  stored) — set only when an invoice line hits one of the 11 seeded quick-expense
  category accounts. Netto = standard `amount_untaxed`, Áfa = standard
  `amount_tax`, both already posted to GL.
- **Dentari Lab revenue** — [dentari_lab/models/dental_work_log.py](../../../dentari_lab/models/dental_work_log.py)
  `dental.work.log`: `price_per_piece` (Egységár) × `pieces` → `total_revenue`
  (Összeg), computed+stored. **Not** GL data — work logs may or may not be
  invoiced yet (invoicing happens later via `dental.invoice.wizard`).
- `mis_builder` (OCA reporting-engine) is a new dependency — not currently
  installed in this repo.
- Existing menu convention: `dentari_lab` has a "Statisztikák" submenu
  (`menu_dentari_stats`) already holding dashboard/graph/pivot/pie actions —
  new report belongs there.
- Existing demo-data convention: `dental_quick_expense/demo/quick_expense_demo.xml`
  loads via a `_load_demo_*` model function, gated by Odoo's standard `demo`
  manifest key. Per [[oecsh-autodeploy-disabled]], the project runs two
  separate oec.sh environments (`dentari-dev-8780`, `dentari-prod-2031`); demo
  data loads only where demo data is enabled, i.e. dev — never prod.

## Decisions

1. **Lab revenue source:** `dental.work.log.total_revenue` directly, for
   *all* logs regardless of invoice status — not only invoiced amounts. Matches
   the literal ask and avoids undercounting the uninvoiced backlog.
2. **Report content:** P&L-style — Netto, Áfa, Bruttó (Netto+Áfa), Lab
   Összeg, and a computed Eredmény (margin = Összeg − Bruttó).
3. **Periods:** monthly, rolling 12 months (matches existing
   `dental_monthly_wizard` cadence).
4. **Data-access mechanism:** both sides go through mis_builder's `mis.report.query`
   feature (arbitrary model + domain + summed fields), *not* mis_builder's
   GL-balance (`bal[]`) expression engine. Keeps Kiadások and Lab revenue
   symmetric — one mechanism to maintain instead of two. No GL drill-down as a
   result; not a stated requirement (YAGNI).
5. **Dev-only test dashboards:** separate `mis.report.instance` seeded with
   deliberately round demo amounts, gated by the existing demo-data convention
   so it never reaches prod.

## Module

New addon: `dentari_mis_reports` (sibling to `dental_quick_expense`,
`dentari_lab` at repo root).

```
dentari_mis_reports/
├── __init__.py
├── __manifest__.py
├── data/
│   └── mis_report_data.xml
├── demo/
│   └── mis_report_demo.xml
└── views/
    └── menu.xml
```

`__manifest__.py`:
- `depends`: `mis_builder`, `dentari_lab`, `dental_quick_expense`
- `data`: `data/mis_report_data.xml`, `views/menu.xml`
- `demo`: `demo/mis_report_demo.xml`
- `application`: False

No new Python models. No new security/ACL file — mis_builder ships its own
groups; the module only adds a menu item restricted to
`dentari_lab.group_lab_manager` (financial data — same restriction as
`menu_dental_monthly_wizard`).

## Report definition (`data/mis_report_data.xml`)

One `mis.report` template:

**Queries:**
| name | model | domain | date field | summed fields → vars |
|------|-------|--------|-----------|----------------------|
| `lab` | `dental.work.log` | `[]` | `date` | `total_revenue` → `lab.revenue` |
| `exp` | `account.move` | `[('state','=','posted'), ('move_type','in',['in_invoice','in_refund']), ('expense_category_id','!=',False)]` | `invoice_date` | `amount_untaxed` → `exp.netto`, `amount_tax` → `exp.afa` |

**KPIs** (all monetary, 0 decimals, matching the `digits=(10, 0)` convention
used elsewhere in the codebase):
| KPI | Expression |
|-----|-----------|
| Netto | `exp.netto` |
| Áfa | `exp.afa` |
| Bruttó | `exp.netto + exp.afa` |
| Bevétel (Összeg) | `lab.revenue` |
| Eredmény | `lab.revenue - exp.netto - exp.afa` |

**Instance:** one `mis.report.instance` ("Kiadás / Bevétel havi riport"),
12 rolling monthly periods, default company.

## Dev-only test dashboard (`demo/mis_report_demo.xml`)

A `_load_demo_mis_test_data()` function on a thin demo-loader (mirrors
`_load_demo_expenses`'s pattern) that:
- creates a handful of `dental.work.log` + quick-expense `account.move`
  records with round Ft amounts (e.g. 100 000 Netto / 27 000 Áfa / 200 000
  Összeg) in one clearly-labeled recent month
- creates a second `mis.report.instance` ("QA Teszt Riport") scoped to just
  that month, separate from the real rolling instance, so a dev can eyeball
  Netto+Áfa=Bruttó and the margin calc instantly

Loads only when demo data is enabled (dev env) — never prod, per the existing
`dental_quick_expense` convention.

## Menu

One `menuitem` added under `dentari_lab`'s existing `menu_dentari_stats`
("Statisztikák"), pointing at the main instance's dashboard action, restricted
to `dentari_lab.group_lab_manager`.

## Data flow

Nothing stored or triggered by this module. mis_builder computes both queries
live via `read_group` whenever the dashboard/pivot is opened, scoped per
period. Kiadások side only ever sees moves that went through the quick-expense
flow (`expense_category_id` set) — ordinary vendor bills don't leak in. Lab
side sees every logged job regardless of invoice status.

## Error handling

Relies entirely on mis_builder's built-in behavior: an empty period renders as
0/blank per KPI. No custom exception handling in this module.

## Testing

One Odoo test, `tests/test_mis_report_kpis.py` (repo's existing root-level
`tests/` convention): create one work log + one posted quick-expense vendor
bill in a known period, compute the `mis.report.instance` for that period via
mis_builder's public API, assert the 5 KPI values match hand-computed
expectations. No UI/tour test (YAGNI).

## Out of scope

- GL drill-down into journal entries (would require the `bal[]` engine —
  approach rejected per decision 4).
- Per-category breakdown of Kiadások (11 categories) — considered and
  dropped in favor of the flatter Netto/Áfa/Bruttó view.
- Quarter/YTD subtotal columns — considered and dropped in favor of a plain
  rolling 12-month view.
- Ad-hoc user-picked date range — considered and dropped in favor of the
  fixed rolling window.
