# TICKET-004 — Dashboard KPI View (M2)

| Field | Value |
|---|---|
| **Type** | Feature |
| **Priority** | Medium |
| **Milestone** | M2 — Statistics & Import |
| **Assignee** | — |
| **Reporter** | Dentari Development Team |
| **Created** | 2026-05-23 |
| **Status** | Open |
| **Design ref** | [DESIGN.md §5](./DESIGN.md#5-milestone-roadmap) |
| **Depends on** | TICKET-001 (M1 — `dental.work.log` model must exist) |

---

## Summary

Add a **Dashboard** view to the `dentari_lab` module that surfaces the most important dental-lab KPIs derived from existing `dental.work.log` data. No new model is required — all aggregates are computed directly from the existing table via Odoo's `dashboard`, `graph`, and `pivot` views.

---

## Background

The `dental.work.log` model (M1) collects all billable work records. As data grows, raw list views become insufficient. A lab manager or technician needs at-a-glance answers to:

- How much did I earn today / this week / this month?
- How many pieces did I produce?
- Which work types are most common?
- Which clients generate the most revenue?

These are the industry-standard KPIs for a small dental prosthetics lab. They require no new data — only aggregated views on the existing `total_revenue`, `pieces`, `partner_id`, `work_type`, and `date` fields.

---

## Industry-Standard KPIs for a Dental Lab

The following KPI set covers the core business visibility needs of a dental technician / small lab. All are derivable from `dental.work.log`.

### 1. Revenue KPIs

| KPI | Calculation | Period |
|---|---|---|
| Havi bevétel (Monthly revenue) | `SUM(total_revenue)` | Current calendar month |
| Heti bevétel (Weekly revenue) | `SUM(total_revenue)` | Current ISO week |
| Mai bevétel (Today's revenue) | `SUM(total_revenue)` | `date = today` |
| Átlagos megrendelés érték (Avg order value) | `AVG(total_revenue)` | Current month |

### 2. Volume KPIs

| KPI | Calculation | Period |
|---|---|---|
| Havi darabszám (Monthly pieces) | `SUM(pieces)` | Current calendar month |
| Mai munkák száma (Jobs today) | `COUNT(*)` | `date = today` |
| Átlagos darab/megrendelés (Avg pieces/job) | `AVG(pieces)` | Current month |

### 3. Client KPIs

| KPI | Calculation | Period |
|---|---|---|
| Aktív megrendelők (Active clients) | `COUNT(DISTINCT partner_id)` | Current month |
| Top megrendelők (Top clients by revenue) | `SUM(total_revenue) GROUP BY partner_id` | Last 30 days, top 5 |

### 4. Work-Type Distribution

| KPI | Calculation | Period |
|---|---|---|
| Munkatípus megoszlás (Work-type breakdown) | `COUNT(*) GROUP BY work_type` | Current month |
| Legjövedelmezőbb munkatípus (Most profitable type) | `SUM(total_revenue) GROUP BY work_type` | Current month |

### 5. Trend KPI

| KPI | Calculation | Period |
|---|---|---|
| Havi bevétel trend (Monthly revenue trend) | `SUM(total_revenue) GROUP BY date:month` | Last 12 months |

---

## Acceptance Criteria

### AC-1 Dashboard view (`<dashboard>` arch)

- [ ] A new `ir.ui.view` with `arch type="dashboard"` is added for `dental.work.log`.
- [ ] The dashboard displays **KPI aggregate boxes** (one row, 4 columns):
  - **Havi bevétel** — `SUM(total_revenue)`, domain `date >= start_of_month`, format as HUF integer (no decimals), suffix `Ft`.
  - **Havi darabszám** — `SUM(pieces)`, domain `date >= start_of_month`, suffix `db`.
  - **Mai munkák** — `COUNT(id)`, domain `date = today`.
  - **Aktív megrendelők** — displayed via embedded graph (see AC-2); this stat requires `COUNT DISTINCT`, which `<aggregate>` does not natively support — implement as a label on the graph view or defer to a separate SQL view (see Out of Scope note).
- [ ] The dashboard embeds a **graph subview** (see AC-2).
- [ ] The dashboard embeds a **pivot subview** (see AC-3).
- [ ] KPI boxes use `<aggregate>` elements with `field`, `string`, `domain`, and `group_operator` attributes.
- [ ] KPI `domain` expressions use `context_today()` so they evaluate at render time, not install time.

### AC-2 Graph view

- [ ] A new `graph` view is added to `dental.work.log`.
- [ ] Default chart type: **bar chart** (`type="bar"`).
- [ ] Default grouping: `date` by month (`<field name="date" interval="month" type="row"/>`).
- [ ] Default measure: `total_revenue` (`<field name="total_revenue" type="measure"/>`).
- [ ] Secondary measure available: `pieces`.
- [ ] The graph view action is accessible standalone from the menu (see AC-5) AND embedded in the dashboard.

### AC-3 Pivot view

- [ ] A new `pivot` view is added to `dental.work.log`.
- [ ] Default row grouping: `work_type`.
- [ ] Default column grouping: `date` by month.
- [ ] Default measures: `total_revenue` (sum) and `pieces` (sum), both present in the measures dropdown.
- [ ] The pivot view action is accessible standalone AND embedded in the dashboard.

### AC-4 Work-type pie chart view

- [ ] A second `graph` view with `type="pie"` showing `COUNT(*)` (or `SUM(total_revenue)`) grouped by `work_type`.
- [ ] This view is accessible via the "Statisztikák" menu (see AC-5), not embedded in the main dashboard to avoid clutter.

### AC-5 Menu structure

- [ ] Existing `Dentari Lab` top-level menu gains a new sub-menu group **"Statisztikák"** (Statistics).
- [ ] Under "Statisztikák":
  - `Irányítópult` (Dashboard) → opens the `dashboard`-arch view (AC-1).
  - `Bevétel trend` (Revenue trend) → opens the `graph` view (AC-2) standalone.
  - `Pivot táblázat` (Pivot table) → opens the `pivot` view (AC-3) standalone.
  - `Munkatípus megoszlás` (Work-type breakdown) → opens the pie `graph` view (AC-4).
- [ ] All "Statisztikák" menu items are visible to both `group_lab_technician` and `group_lab_manager`.
- [ ] Lab Technicians see only their own records in all views (existing record rule already enforces this — no additional work needed).

### AC-6 Default view mode for main action

- [ ] Update the existing `action_dental_work_log` to include `graph` and `pivot` in its `view_mode` list:
  `list,form,graph,pivot`
  so users can switch to graphs from the standard list without using the Statistics submenu.

### AC-7 Odoo 18 compatibility

- [ ] No `attrs=` XML attributes anywhere.
- [ ] All `domain` values in `<aggregate>` elements use `context_today()` not Python `datetime` imports.
- [ ] `<dashboard>` view requires no extra Python model — works directly on `dental.work.log`.
- [ ] New XML views added to `views/dental_work_log_views.xml` (or a new `views/dental_dashboard_views.xml` if the file grows large).
- [ ] New file (if created) added to the `data` list in `__manifest__.py` **after** existing view entries.

---

## Technical Specification

### Files to create or modify

| File | Change |
|---|---|
| `views/dental_work_log_views.xml` | Add `dashboard`, `graph` (bar), `graph` (pie), `pivot` view records; update `action_dental_work_log` view_mode |
| `views/menus.xml` | Add "Statisztikák" menu group and 4 sub-items |
| `dentari_lab/__manifest__.py` | No change needed if views go into existing file; update `data` list if a new XML file is added |

### Dashboard view skeleton (reference implementation)

```xml
<record id="view_dental_work_log_dashboard" model="ir.ui.view">
    <field name="name">dental.work.log.dashboard</field>
    <field name="model">dental.work.log</field>
    <field name="arch" type="xml">
        <dashboard>
            <group col="4" string="Összesítők">
                <aggregate name="revenue_month"
                    field="total_revenue"
                    string="Havi bevétel (Ft)"
                    domain="[('date', '&gt;=', context_today().strftime('%Y-%m-01'))]"
                    group_operator="sum"/>
                <aggregate name="pieces_month"
                    field="pieces"
                    string="Havi darabszám"
                    domain="[('date', '&gt;=', context_today().strftime('%Y-%m-01'))]"
                    group_operator="sum"/>
                <aggregate name="jobs_today"
                    field="id"
                    string="Mai munkák"
                    domain="[('date', '=', context_today().strftime('%Y-%m-%d'))]"
                    group_operator="count"/>
                <aggregate name="revenue_week"
                    field="total_revenue"
                    string="Heti bevétel (Ft)"
                    domain="[('date', '&gt;=', (context_today() + relativedelta(weekday=0, days=-6)).strftime('%Y-%m-%d'))]"
                    group_operator="sum"/>
            </group>
            <view type="graph" ref="dentari_lab.view_dental_work_log_graph_bar"/>
            <view type="pivot" ref="dentari_lab.view_dental_work_log_pivot"/>
        </dashboard>
    </field>
</record>
```

> **Note on `relativedelta` in domain:** Odoo's `<aggregate>` domain evaluates in a Python context that includes `relativedelta`. Verify at runtime; if unavailable, replace the weekly aggregate with a fixed 7-day offset using `timedelta`.

### Graph view skeleton

```xml
<record id="view_dental_work_log_graph_bar" model="ir.ui.view">
    <field name="name">dental.work.log.graph.bar</field>
    <field name="model">dental.work.log</field>
    <field name="arch" type="xml">
        <graph type="bar" sample="1">
            <field name="date" interval="month" type="row" string="Hónap"/>
            <field name="total_revenue" type="measure" string="Bevétel (Ft)"/>
            <field name="pieces" type="measure" string="Darabszám"/>
        </graph>
    </field>
</record>
```

### Pivot view skeleton

```xml
<record id="view_dental_work_log_pivot" model="ir.ui.view">
    <field name="name">dental.work.log.pivot</field>
    <field name="model">dental.work.log</field>
    <field name="arch" type="xml">
        <pivot sample="1">
            <field name="work_type" type="row" string="Munka típusa"/>
            <field name="date" interval="month" type="col" string="Hónap"/>
            <field name="total_revenue" type="measure" string="Bevétel (Ft)"/>
            <field name="pieces" type="measure" string="Darabszám"/>
        </pivot>
    </field>
</record>
```

### Pie chart view skeleton

```xml
<record id="view_dental_work_log_graph_pie" model="ir.ui.view">
    <field name="name">dental.work.log.graph.pie</field>
    <field name="model">dental.work.log</field>
    <field name="arch" type="xml">
        <graph type="pie" sample="1">
            <field name="work_type" type="row" string="Munka típusa"/>
            <field name="total_revenue" type="measure" string="Bevétel (Ft)"/>
        </graph>
    </field>
</record>
```

---

## Out of Scope (do not implement in this ticket)

- `COUNT(DISTINCT partner_id)` aggregate — Odoo's `<aggregate>` widget does not support `count_distinct`; the "Aktív megrendelők" stat is deferred or exposed only via the pivot/list view. A SQL view model (`_auto = False`) could expose this but is M3+ complexity.
- Excel/CSV import wizard (separate M2 sub-ticket).
- Composite DB index `idx_work_log_date_partner` — add when query profiling shows slowness (M2 stretch goal).
- Scheduled reporting or email digests (M5).
- `cohort` view (tracks retention over time; not relevant for a lab).
- Per-technician comparison chart (not meaningful for a solo technician; revisit if multi-user usage grows).

---

## Definition of Done

- [ ] All acceptance criteria above are checked.
- [ ] Dashboard menu item "Irányítópult" renders without JS errors on Odoo 18.
- [ ] KPI boxes show correct values (manually verify against list view totals).
- [ ] Bar chart shows monthly revenue trend with correct month labels.
- [ ] Pivot table shows `work_type × month` breakdown with `total_revenue` and `pieces` measures.
- [ ] Pie chart shows correct work-type share.
- [ ] Lab Technician sees only their own data in all views (record rule already in place).
- [ ] Lab Manager sees all records.
- [ ] Module upgrades cleanly (`-u dentari_lab`) without errors.
- [ ] Smoke test (`tests/smoke_dev.py`) still passes after upgrade.
- [ ] Code reviewed and merged to `dev` branch.
