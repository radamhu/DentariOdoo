# TICKET-004 — Statistics & KPI Views (M2)

| Field | Value |
|---|---|
| **Type** | Feature |
| **Priority** | Medium |
| **Milestone** | M2 — Statistics & Import |
| **Assignee** | — |
| **Reporter** | Dentari Development Team |
| **Created** | 2026-05-23 |
| **Updated** | 2026-05-25 |
| **Status** | Open |
| **Design ref** | [DESIGN.md §5](./DESIGN.md#5-milestone-roadmap) |
| **Depends on** | TICKET-001 (M1 — `dental.work.log` model must exist) |

---

## Community Edition Constraint

> **`<dashboard>` arch type is Enterprise-only.**
> Odoo 18 Community Edition registers these view types in `ir_ui_view.py`: `list`, `form`, `graph`, `pivot`, `kanban`, `calendar`, `search`. The `<dashboard>` view with `<aggregate>` KPI boxes is provided by the `web_dashboard` Enterprise module and is **not available** in CE. All `<dashboard>` and `<aggregate>` content has been removed from this ticket. KPI number boxes are deferred to M3 (see Out of Scope).

---

## Summary

Add **graph, pivot, and pie chart** statistical views to the `dentari_lab` module that surface the most important dental-lab KPIs derived from existing `dental.work.log` data. No new model is required — all aggregates are computed directly from the existing table via Odoo's `graph` and `pivot` view engines. A combined `graph + pivot` action serves as the CE-compatible "Irányítópult" (landing statistics page).

---

## Background

The `dental.work.log` model (M1) collects all billable work records. As data grows, raw list views become insufficient. A lab manager or technician needs at-a-glance answers to:

- How much did I earn this month / this week?
- How many pieces did I produce?
- Which work types are most common?
- Which clients generate the most revenue?

These are the industry-standard KPIs for a small dental prosthetics lab. They require no new data — only aggregated views on the existing `total_revenue`, `pieces`, `partner_id`, `work_type`, and `date` fields.

---

## Industry-Standard KPIs for a Dental Lab

The following KPI set covers the core business visibility needs of a dental technician / small lab. All are derivable from `dental.work.log`.

### 1. Revenue KPIs

| KPI | Calculation | Covered by |
|---|---|---|
| Havi bevétel (Monthly revenue) | `SUM(total_revenue)` GROUP BY month | Graph bar / Pivot |
| Heti bevétel (Weekly revenue) | `SUM(total_revenue)` filtered | Search filter + list sum footer |
| Mai bevétel (Today's revenue) | `SUM(total_revenue)` filtered | Search filter + list sum footer |
| Átlagos megrendelés érték (Avg order value) | `AVG(total_revenue)` | Pivot |

### 2. Volume KPIs

| KPI | Calculation | Covered by |
|---|---|---|
| Havi darabszám (Monthly pieces) | `SUM(pieces)` | Graph bar (secondary measure) / Pivot |
| Mai munkák száma (Jobs today) | `COUNT(*)` | Search filter "Ma" + list |
| Átlagos darab/megrendelés (Avg pieces/job) | `AVG(pieces)` | Pivot |

### 3. Client & Distribution KPIs

| KPI | Calculation | Covered by |
|---|---|---|
| Top megrendelők (Top clients) | `SUM(total_revenue) GROUP BY partner_id` | Pivot (row = partner_id) |
| Munkatípus megoszlás (Work-type breakdown) | `COUNT(*) GROUP BY work_type` | Pie chart |
| Legjövedelmezőbb munkatípus (Most profitable type) | `SUM(total_revenue) GROUP BY work_type` | Pie chart (measure switch) |

### 4. Trend KPI

| KPI | Calculation | Covered by |
|---|---|---|
| Havi bevétel trend (Monthly revenue trend) | `SUM(total_revenue) GROUP BY date:month` | Graph bar (default view) |

---

## Acceptance Criteria

### AC-1 "Irányítópult" landing action (CE-compatible)

- [ ] A new `ir.actions.act_window` named `action_dental_work_log_dashboard` is added.
- [ ] `view_mode` = `graph,pivot` — graph opens first by default; pivot is accessible via the view-switcher buttons.
- [ ] No explicit `view_id` set — Odoo resolves the bar graph view automatically as the first `graph` view on the model.
- [ ] This action is distinct from `action_dental_work_log_graph` (graph-only) and `action_dental_work_log_pivot` (pivot-only).

### AC-2 Graph view (bar chart)

- [ ] A `graph` view record exists for `dental.work.log` with `id="view_dental_work_log_graph_bar"`.
- [ ] Default chart type: **bar** (`type="bar"`).
- [ ] Default grouping: `date` by month (`<field name="date" interval="month" type="row"/>`).
- [ ] Default measure: `total_revenue`.
- [ ] Secondary measure available: `pieces`.
- [ ] `sample="1"` set so the view renders sample data when the model is empty.
- [ ] Accessible standalone from the "Statisztikák" menu and as the default view of AC-1 action.

### AC-3 Pivot view

- [ ] A `pivot` view record exists for `dental.work.log` with `id="view_dental_work_log_pivot"`.
- [ ] Default row grouping: `work_type`.
- [ ] Default column grouping: `date` by month.
- [ ] Default measures: `total_revenue` (sum) and `pieces` (sum), both present in the measures dropdown.
- [ ] `sample="1"` set.
- [ ] Accessible standalone from the "Statisztikák" menu and as the secondary view of AC-1 action.

### AC-4 Work-type pie chart view

- [ ] A `graph` view record exists with `id="view_dental_work_log_graph_pie"` and `type="pie"`.
- [ ] Default grouping: `work_type`.
- [ ] Default measure: `total_revenue`.
- [ ] `sample="1"` set.
- [ ] Accessible via the "Statisztikák" menu only — not embedded elsewhere.

### AC-5 Menu structure

- [ ] The `Dentari Lab` top-level menu (`menu_dentari_lab_root`) has `groups="dentari_lab.group_lab_technician"` so it is hidden from users outside the module.
- [ ] A sub-menu group **"Statisztikák"** exists under `menu_dentari_lab_root`.
- [ ] Under "Statisztikák", all four items exist in order:
  - `Irányítópult` (sequence 10) → `action_dental_work_log_dashboard` (AC-1)
  - `Bevétel trend` (sequence 20) → `action_dental_work_log_graph`
  - `Pivot táblázat` (sequence 30) → `action_dental_work_log_pivot`
  - `Munkatípus megoszlás` (sequence 40) → `action_dental_work_log_pie`
- [ ] No additional `groups=` needed on individual Statisztikák items — root-level group propagates visibility correctly.
- [ ] Lab Technicians see only their own records in all views (existing record rule enforces this — no extra work needed).

### AC-6 Default view mode for main action

- [ ] `action_dental_work_log` has `view_mode = list,form,graph,pivot` so users can switch to graph/pivot from the standard list without the Statistics submenu.

### AC-7 Odoo 18 Community compatibility

- [ ] No `attrs=` XML attributes anywhere in new or modified XML.
- [ ] No `<dashboard>` or `<aggregate>` XML elements — these are Enterprise-only and must not appear.
- [ ] `context_today()` used in all `domain` expressions that reference the current date (evaluated at render time, not install time).
- [ ] All new view records added to `views/dental_work_log_views.xml`.
- [ ] All new action records added to `views/dental_work_log_views.xml`.
- [ ] Module upgrades cleanly with `-u dentari_lab`.

---

## Technical Specification

### Files to create or modify

| File | Change |
|---|---|
| `views/dental_work_log_views.xml` | Add `graph` (bar), `graph` (pie), `pivot` view records; add dashboard, graph, pivot, pie actions; update `action_dental_work_log` view_mode |
| `views/menus.xml` | Add `groups=` to root menu; add "Statisztikák" parent and 4 sub-items |
| `dentari_lab/__manifest__.py` | No change needed (all views go into existing files) |

### "Irányítópult" action (AC-1)

```xml
<record id="action_dental_work_log_dashboard" model="ir.actions.act_window">
    <field name="name">Irányítópult</field>
    <field name="res_model">dental.work.log</field>
    <field name="view_mode">graph,pivot</field>
</record>
```

### Graph (bar) view (AC-2)

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

### Pivot view (AC-3)

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

### Pie chart view (AC-4)

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

### Menu structure (AC-5)

```xml
<menuitem
    id="menu_dentari_lab_root"
    name="Dentari Lab"
    sequence="100"
    groups="dentari_lab.group_lab_technician"/>

<menuitem
    id="menu_dentari_stats"
    name="Statisztikák"
    parent="menu_dentari_lab_root"
    sequence="30"/>

<menuitem
    id="menu_dentari_stats_dashboard"
    name="Irányítópult"
    parent="menu_dentari_stats"
    action="action_dental_work_log_dashboard"
    sequence="10"/>

<menuitem
    id="menu_dentari_stats_graph"
    name="Bevétel trend"
    parent="menu_dentari_stats"
    action="action_dental_work_log_graph"
    sequence="20"/>

<menuitem
    id="menu_dentari_stats_pivot"
    name="Pivot táblázat"
    parent="menu_dentari_stats"
    action="action_dental_work_log_pivot"
    sequence="30"/>

<menuitem
    id="menu_dentari_stats_pie"
    name="Munkatípus megoszlás"
    parent="menu_dentari_stats"
    action="action_dental_work_log_pie"
    sequence="40"/>
```

---

## Out of Scope (do not implement in this ticket)

- **`<dashboard>` / `<aggregate>` KPI boxes** — Enterprise-only feature (`web_dashboard` module). Not available in Odoo 18 Community Edition. Deferred to M3 via a `dental.lab.kpi` model (`_auto = False`, PostgreSQL view) displayed as a read-only form with stat-button-style fields.
- **`COUNT(DISTINCT partner_id)` "Aktív megrendelők" KPI** — requires the SQL-backed model above; deferred to M3.
- Excel/CSV import wizard (separate M2 sub-ticket).
- Composite DB index `idx_work_log_date_partner` — add when query profiling shows slowness (M2 stretch goal).
- Scheduled reporting or email digests (M5).
- `cohort` view — not relevant for a lab.
- Per-technician comparison chart — not meaningful for a solo technician; revisit if multi-user usage grows.

---

## Definition of Done

- [ ] All acceptance criteria above are checked.
- [ ] "Irányítópult" menu item appears under "Statisztikák" and opens the bar graph view (graph/pivot switcher visible).
- [ ] Bar chart shows monthly revenue trend with correct month labels.
- [ ] Pivot table shows `work_type × month` breakdown with `total_revenue` and `pieces` measures.
- [ ] Pie chart shows correct work-type share.
- [ ] Lab Technician sees only their own data in all views (record rule already in place).
- [ ] Lab Manager sees all records.
- [ ] "Dentari Lab" top-level menu is not visible to users outside the module groups.
- [ ] Module upgrades cleanly (`-u dentari_lab`) without errors.
- [ ] Smoke test (`tests/smoke_dev.py`) still passes after upgrade.
- [ ] Code reviewed and merged to `dev` branch.
