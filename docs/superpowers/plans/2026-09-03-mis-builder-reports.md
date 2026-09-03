# MIS Builder Reports Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `dentari_mis_reports` module that gives the practice a monthly
Kiadások (Netto+Áfa) vs Dentari Lab revenue (Összeg) profitability report via
OCA `mis_builder`, plus a dev-only sanity-check dashboard.

**Architecture:** Pure-data addon (one Python file with a single inherited
method for demo seeding; no new business models). One `mis.report` template
defines two `mis.report.query` records (non-GL `dental.work.log`, GL-scoped
`account.move`) feeding five KPIs. One `mis.report.instance` renders them over
a rolling 12-month window; a second, demo-only instance renders one QA month
with round numbers.

**Tech Stack:** Odoo 18.0, OCA `mis_builder` (new pip dependency, package
`odoo-addon-mis-builder`), XML data records, one inherited `account.move`
Python method.

**Spec:** [docs/superpowers/specs/2026-09-03-mis-builder-reports-design.md](../specs/2026-09-03-mis-builder-reports-design.md)

## Global Constraints

- Odoo version: 18.0 (all field/model names below verified against the
  `OCA/mis-builder` `18.0` branch).
- Kiadások domain must stay scoped to `expense_category_id != False` (only
  quick-expense vendor bills, never ordinary AP invoices) and `state=posted`
  (draft bills — including the *existing* `dental_quick_expense` demo data,
  which is deliberately left in draft — never count).
- Lab revenue counts every `dental.work.log`, invoiced or not — no
  `invoice_id` filter on the `lab` query's domain.
- Monetary KPIs render with 0 decimals and a " Ft" suffix (matches the
  `digits=(10, 0)` convention already used on `total_revenue` /
  `price_per_piece`).
- Financial menu entries stay restricted to `dentari_lab.group_lab_manager`
  (same restriction as `menu_dental_monthly_wizard`).
- Demo data (`demo/` manifest key) must never reach prod
  (`dentari-prod-2031`) — only the dev env (`dentari-dev-8780`) installs with
  demo data enabled. Do not add any other gating mechanism.
- **Known risk:** the `ir.model.fields` / `ir.model` external IDs used below
  (e.g. `account.field_account_move__amount_untaxed`) are Odoo's standard
  auto-generated naming convention (`<owning module>.field_<model>__<field>`
  / `<owning module>.model_<model>`) and cannot be verified against a live
  Odoo instance from this environment (no local Odoo install). If module
  install fails in Task 6 with `External ID not found`, look up the correct
  ID via **Settings → Technical → Database Structure → Fields** (filter by
  model) on the dev instance, fix the XML, and re-upgrade.

---

## Task 1: Module skeleton + mis_builder dependency

**Files:**
- Create: `dentari_mis_reports/__init__.py`
- Create: `dentari_mis_reports/__manifest__.py`
- Create: `dentari_mis_reports/models/__init__.py`
- Create: `dentari_mis_reports/models/account_move.py`
- Modify: `requirements.txt`

**Interfaces:**
- Produces: Python package `dentari_mis_reports`, importable model
  extension `account.move._load_dentari_mis_demo_data(self)` (empty body for
  now — filled in Task 4) that later tasks' demo data will call.

- [ ] **Step 1: Pin the mis_builder pip package**

Append to `requirements.txt` (mirrors the existing `pyOpenSSL` pin style):

```
# OCA mis_builder (reporting-engine, 18.0) — provides the mis.report /
# mis.report.instance models the dentari_mis_reports addon builds on.
# Pinned so Odoo's addons_path (which includes the venv's site-packages
# odoo/addons dir) always has a matching version.
odoo-addon-mis-builder==18.0.1.10.0.1
```

- [ ] **Step 2: Create the module skeleton**

`dentari_mis_reports/__init__.py`:

```python
from . import models
```

`dentari_mis_reports/models/__init__.py`:

```python
from . import account_move
```

`dentari_mis_reports/models/account_move.py`:

```python
from odoo import api, models

DEMO_MIS_MARKER = 'dentari-mis-demo'


class AccountMove(models.Model):
    _inherit = 'account.move'

    @api.model
    def _load_dentari_mis_demo_data(self):
        """Idempotent demo-data seeder for the QA test dashboard.

        Filled in by Task 4. Left as a no-op here so the module installs
        cleanly (and the <function> hook in demo data has something to
        call) before that task exists.
        """
        return
```

`dentari_mis_reports/__manifest__.py`:

```python
{
    'name': 'Dentari MIS Reports',
    'version': '18.0.1.0.0',
    'category': 'Dental / Accounting',
    'summary': 'Kiadások vs Dentari Lab revenue profitability report (mis_builder)',
    'depends': ['mis_builder', 'dentari_lab', 'dental_quick_expense'],
    'data': [],
    'demo': [],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
```

- [ ] **Step 3: Validate the manifest and Python files parse**

Run:
```bash
python3 -c "import ast; ast.parse(open('dentari_mis_reports/__manifest__.py').read())"
python3 -c "import ast; ast.parse(open('dentari_mis_reports/models/account_move.py').read())"
```
Expected: no output (both parse cleanly).

- [ ] **Step 4: Commit**

```bash
git add dentari_mis_reports requirements.txt
git commit -m "feat: scaffold dentari_mis_reports module, pin mis_builder"
```

---

## Task 2: Report template — queries, style, KPIs

**Files:**
- Create: `dentari_mis_reports/data/mis_report_data.xml`
- Modify: `dentari_mis_reports/__manifest__.py:data` — add `'data/mis_report_data.xml'`
- Create: `tests/test_mis_report.py`

**Interfaces:**
- Consumes: nothing from Task 1 beyond the module existing.
- Produces: XML IDs `dentari_mis_reports.mis_report_style_ft`,
  `dentari_mis_reports.mis_report_query_lab`,
  `dentari_mis_reports.mis_report_query_exp`,
  `dentari_mis_reports.mis_report_kpi_netto`,
  `dentari_mis_reports.mis_report_kpi_afa`,
  `dentari_mis_reports.mis_report_kpi_brutto`,
  `dentari_mis_reports.mis_report_kpi_bevetel`,
  `dentari_mis_reports.mis_report_kpi_eredmeny`,
  `dentari_mis_reports.mis_report_kiadas_bevetel` (the `mis.report`
  template) — Task 3's instance and Task 4's demo instance both reference
  `mis_report_kiadas_bevetel`.

- [ ] **Step 1: Write the report template data file**

`dentari_mis_reports/data/mis_report_data.xml`:

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="mis_report_style_ft" model="mis.report.style">
        <field name="name">Forint (0 tizedes)</field>
        <field name="dp_inherit" eval="False"/>
        <field name="dp">0</field>
        <field name="suffix_inherit" eval="False"/>
        <field name="suffix"> Ft</field>
    </record>

    <record id="mis_report_kiadas_bevetel" model="mis.report">
        <field name="name">Kiadás / Bevétel riport</field>
        <field name="description">Kiadások (Netto+Áfa) vs Dentari Lab bevétel (Összeg)</field>
    </record>

    <record id="mis_report_query_lab" model="mis.report.query">
        <field name="report_id" ref="mis_report_kiadas_bevetel"/>
        <field name="name">lab</field>
        <field name="model_id" ref="dentari_lab.model_dental_work_log"/>
        <field name="field_ids" eval="[(6, 0, [ref('dentari_lab.field_dental_work_log__total_revenue')])]"/>
        <field name="aggregate">sum</field>
        <field name="date_field" ref="dentari_lab.field_dental_work_log__date"/>
        <field name="domain">[]</field>
    </record>

    <record id="mis_report_query_exp" model="mis.report.query">
        <field name="report_id" ref="mis_report_kiadas_bevetel"/>
        <field name="name">exp</field>
        <field name="model_id" ref="account.model_account_move"/>
        <field name="field_ids" eval="[(6, 0, [
            ref('account.field_account_move__amount_untaxed'),
            ref('account.field_account_move__amount_tax'),
        ])]"/>
        <field name="aggregate">sum</field>
        <field name="date_field" ref="account.field_account_move__invoice_date"/>
        <field name="domain">[('state', '=', 'posted'), ('move_type', 'in', ['in_invoice', 'in_refund']), ('expense_category_id', '!=', False)]</field>
    </record>

    <record id="mis_report_kpi_netto" model="mis.report.kpi">
        <field name="report_id" ref="mis_report_kiadas_bevetel"/>
        <field name="name">netto</field>
        <field name="description">Netto</field>
        <field name="expression">exp.amount_untaxed</field>
        <field name="style_id" ref="mis_report_style_ft"/>
        <field name="sequence">10</field>
    </record>

    <record id="mis_report_kpi_afa" model="mis.report.kpi">
        <field name="report_id" ref="mis_report_kiadas_bevetel"/>
        <field name="name">afa</field>
        <field name="description">Áfa</field>
        <field name="expression">exp.amount_tax</field>
        <field name="style_id" ref="mis_report_style_ft"/>
        <field name="sequence">20</field>
    </record>

    <record id="mis_report_kpi_brutto" model="mis.report.kpi">
        <field name="report_id" ref="mis_report_kiadas_bevetel"/>
        <field name="name">brutto</field>
        <field name="description">Bruttó</field>
        <field name="expression">exp.amount_untaxed + exp.amount_tax</field>
        <field name="style_id" ref="mis_report_style_ft"/>
        <field name="sequence">30</field>
    </record>

    <record id="mis_report_kpi_bevetel" model="mis.report.kpi">
        <field name="report_id" ref="mis_report_kiadas_bevetel"/>
        <field name="name">bevetel</field>
        <field name="description">Bevétel (Összeg)</field>
        <field name="expression">lab.total_revenue</field>
        <field name="style_id" ref="mis_report_style_ft"/>
        <field name="sequence">40</field>
    </record>

    <record id="mis_report_kpi_eredmeny" model="mis.report.kpi">
        <field name="report_id" ref="mis_report_kiadas_bevetel"/>
        <field name="name">eredmeny</field>
        <field name="description">Eredmény</field>
        <field name="expression">lab.total_revenue - exp.amount_untaxed - exp.amount_tax</field>
        <field name="style_id" ref="mis_report_style_ft"/>
        <field name="sequence">50</field>
    </record>
</odoo>
```

- [ ] **Step 2: Register the data file in the manifest**

In `dentari_mis_reports/__manifest__.py`, change:
```python
    'data': [],
```
to:
```python
    'data': [
        'data/mis_report_data.xml',
    ],
```

- [ ] **Step 3: Validate the XML is well-formed**

Run:
```bash
python3 -c "import xml.dom.minidom as m; m.parse('dentari_mis_reports/data/mis_report_data.xml')"
```
Expected: no output (parses cleanly). This only checks XML syntax — the
`ref()` external IDs are verified live in Task 6 (see Global Constraints risk
note).

- [ ] **Step 4: Start the smoke test script**

Create `tests/test_mis_report.py`, following this repo's existing
`tests/smoke_dev.py` / `tests/test_monthly_email.py` XML-RPC pattern:

```python
"""
Smoke test — dentari_mis_reports module.

Verifies:
  1. Report template (report, style, queries, KPIs) registered
  2. Rolling 12-month instance + menu registered (Task 3)
  3. Dev-only QA test dashboard computes the expected KPI values (Task 4)

Usage:
  python tests/test_mis_report.py

Credentials are loaded from .env.dev in the repo root.
"""

import os
import sys
import xmlrpc.client
from pathlib import Path


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def fail(msg: str) -> None:
    print(f"FAIL  {msg}", file=sys.stderr)
    sys.exit(1)


def ok(msg: str) -> None:
    print(f"OK    {msg}")


def main() -> None:
    repo_root = Path(__file__).parent.parent
    load_env(repo_root / ".env.dev")

    url = os.environ.get("ODOO_URL", "").rstrip("/")
    db = os.environ.get("ODOO_DATABASE", "")
    username = os.environ.get("ODOO_USERNAME", "admin")
    password = os.environ.get("ODOO_PASSWORD", "")

    if not url or not db or not password:
        fail("ODOO_URL, ODOO_DATABASE, ODOO_PASSWORD must be set (check .env.dev)")

    common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common")
    try:
        uid = common.authenticate(db, username, password, {})
    except Exception as exc:
        fail(f"XML-RPC connection error: {exc}")
    if not uid:
        fail("Login rejected — check credentials")
    ok(f"Login accepted (uid={uid})")

    models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object")

    def call(model: str, method: str, *args, **kwargs):
        return models.execute_kw(db, uid, password, model, method, list(args), kwargs)

    def xmlid(name: str) -> int:
        try:
            _model, res_id = call(
                "ir.model.data", "get_object_reference",
                "dentari_mis_reports", name,
            )
        except Exception:
            fail(
                f"External ID not found: dentari_mis_reports.{name} — "
                "upgrade the module with '-u dentari_mis_reports' first"
            )
        return res_id

    # ------------------------------------------------------------------
    # 1. Report template registered
    # ------------------------------------------------------------------
    report_id = xmlid("mis_report_kiadas_bevetel")
    ok(f"mis.report registered (id={report_id})")

    for kpi_xmlid, expected_expr in [
        ("mis_report_kpi_netto", "exp.amount_untaxed"),
        ("mis_report_kpi_afa", "exp.amount_tax"),
        ("mis_report_kpi_brutto", "exp.amount_untaxed + exp.amount_tax"),
        ("mis_report_kpi_bevetel", "lab.total_revenue"),
        ("mis_report_kpi_eredmeny", "lab.total_revenue - exp.amount_untaxed - exp.amount_tax"),
    ]:
        kpi_id = xmlid(kpi_xmlid)
        kpi = call("mis.report.kpi", "read", [kpi_id], fields=["expression"])[0]
        if kpi["expression"] != expected_expr:
            fail(f"{kpi_xmlid} expression mismatch: {kpi['expression']!r} != {expected_expr!r}")
        ok(f"KPI {kpi_xmlid} expression OK ({expected_expr})")

    print("-" * 60)
    print("PASS  dentari_mis_reports smoke test completed successfully.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Commit**

```bash
git add dentari_mis_reports tests/test_mis_report.py
git commit -m "feat: mis_builder report template for Kiadás/Bevétel KPIs"
```

---

## Task 3: Rolling 12-month instance + menu

**Files:**
- Create: `dentari_mis_reports/data/mis_report_instance_data.xml`
- Create: `dentari_mis_reports/views/menu.xml`
- Modify: `dentari_mis_reports/__manifest__.py:data` — add both files
- Modify: `tests/test_mis_report.py` — append instance/menu assertions

**Interfaces:**
- Consumes: `dentari_mis_reports.mis_report_kiadas_bevetel` (Task 2).
- Produces: XML ID `dentari_mis_reports.mis_report_instance_havi` (the
  rolling instance) — Task 4's QA instance is a sibling, not a consumer of
  this one. Produces menu action reachable via
  `dentari_mis_reports.menu_dentari_mis_havi`.

- [ ] **Step 1: Write the 12-period rolling instance**

`dentari_mis_reports/data/mis_report_instance_data.xml`:

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="mis_report_instance_havi" model="mis.report.instance">
        <field name="name">Kiadás / Bevétel havi riport</field>
        <field name="report_id" ref="mis_report_kiadas_bevetel"/>
    </record>

    <record id="mis_report_period_m11" model="mis.report.instance.period">
        <field name="report_instance_id" ref="mis_report_instance_havi"/>
        <field name="name">M-11</field>
        <field name="mode">relative</field>
        <field name="type">m</field>
        <field name="offset">-11</field>
        <field name="duration">1</field>
        <field name="sequence">10</field>
    </record>
    <record id="mis_report_period_m10" model="mis.report.instance.period">
        <field name="report_instance_id" ref="mis_report_instance_havi"/>
        <field name="name">M-10</field>
        <field name="mode">relative</field>
        <field name="type">m</field>
        <field name="offset">-10</field>
        <field name="duration">1</field>
        <field name="sequence">20</field>
    </record>
    <record id="mis_report_period_m9" model="mis.report.instance.period">
        <field name="report_instance_id" ref="mis_report_instance_havi"/>
        <field name="name">M-9</field>
        <field name="mode">relative</field>
        <field name="type">m</field>
        <field name="offset">-9</field>
        <field name="duration">1</field>
        <field name="sequence">30</field>
    </record>
    <record id="mis_report_period_m8" model="mis.report.instance.period">
        <field name="report_instance_id" ref="mis_report_instance_havi"/>
        <field name="name">M-8</field>
        <field name="mode">relative</field>
        <field name="type">m</field>
        <field name="offset">-8</field>
        <field name="duration">1</field>
        <field name="sequence">40</field>
    </record>
    <record id="mis_report_period_m7" model="mis.report.instance.period">
        <field name="report_instance_id" ref="mis_report_instance_havi"/>
        <field name="name">M-7</field>
        <field name="mode">relative</field>
        <field name="type">m</field>
        <field name="offset">-7</field>
        <field name="duration">1</field>
        <field name="sequence">50</field>
    </record>
    <record id="mis_report_period_m6" model="mis.report.instance.period">
        <field name="report_instance_id" ref="mis_report_instance_havi"/>
        <field name="name">M-6</field>
        <field name="mode">relative</field>
        <field name="type">m</field>
        <field name="offset">-6</field>
        <field name="duration">1</field>
        <field name="sequence">60</field>
    </record>
    <record id="mis_report_period_m5" model="mis.report.instance.period">
        <field name="report_instance_id" ref="mis_report_instance_havi"/>
        <field name="name">M-5</field>
        <field name="mode">relative</field>
        <field name="type">m</field>
        <field name="offset">-5</field>
        <field name="duration">1</field>
        <field name="sequence">70</field>
    </record>
    <record id="mis_report_period_m4" model="mis.report.instance.period">
        <field name="report_instance_id" ref="mis_report_instance_havi"/>
        <field name="name">M-4</field>
        <field name="mode">relative</field>
        <field name="type">m</field>
        <field name="offset">-4</field>
        <field name="duration">1</field>
        <field name="sequence">80</field>
    </record>
    <record id="mis_report_period_m3" model="mis.report.instance.period">
        <field name="report_instance_id" ref="mis_report_instance_havi"/>
        <field name="name">M-3</field>
        <field name="mode">relative</field>
        <field name="type">m</field>
        <field name="offset">-3</field>
        <field name="duration">1</field>
        <field name="sequence">90</field>
    </record>
    <record id="mis_report_period_m2" model="mis.report.instance.period">
        <field name="report_instance_id" ref="mis_report_instance_havi"/>
        <field name="name">M-2</field>
        <field name="mode">relative</field>
        <field name="type">m</field>
        <field name="offset">-2</field>
        <field name="duration">1</field>
        <field name="sequence">100</field>
    </record>
    <record id="mis_report_period_m1" model="mis.report.instance.period">
        <field name="report_instance_id" ref="mis_report_instance_havi"/>
        <field name="name">M-1</field>
        <field name="mode">relative</field>
        <field name="type">m</field>
        <field name="offset">-1</field>
        <field name="duration">1</field>
        <field name="sequence">110</field>
    </record>
    <record id="mis_report_period_m0" model="mis.report.instance.period">
        <field name="report_instance_id" ref="mis_report_instance_havi"/>
        <field name="name">M0 (aktuális hónap)</field>
        <field name="mode">relative</field>
        <field name="type">m</field>
        <field name="offset">0</field>
        <field name="duration">1</field>
        <field name="sequence">120</field>
    </record>
</odoo>
```

- [ ] **Step 2: Write the menu**

`dentari_mis_reports/views/menu.xml`:

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="action_mis_report_instance_havi" model="ir.actions.act_window">
        <field name="name">Kiadás / Bevétel havi riport</field>
        <field name="res_model">mis.report.instance</field>
        <field name="view_mode">form</field>
        <field name="res_id" ref="mis_report_instance_havi"/>
    </record>

    <menuitem
        id="menu_dentari_mis_havi"
        name="Kiadás / Bevétel riport"
        parent="dentari_lab.menu_dentari_stats"
        action="action_mis_report_instance_havi"
        groups="dentari_lab.group_lab_manager"
        sequence="50"
    />
</odoo>
```

- [ ] **Step 3: Register both files in the manifest**

In `dentari_mis_reports/__manifest__.py`, change:
```python
    'data': [
        'data/mis_report_data.xml',
    ],
```
to:
```python
    'data': [
        'data/mis_report_data.xml',
        'data/mis_report_instance_data.xml',
        'views/menu.xml',
    ],
```

- [ ] **Step 4: Validate both XML files are well-formed**

Run:
```bash
python3 -c "import xml.dom.minidom as m; m.parse('dentari_mis_reports/data/mis_report_instance_data.xml')"
python3 -c "import xml.dom.minidom as m; m.parse('dentari_mis_reports/views/menu.xml')"
```
Expected: no output.

- [ ] **Step 5: Append instance/menu assertions to the smoke test**

In `tests/test_mis_report.py`, insert this block right before the final
`print("-" * 60)` / `print("PASS...")` lines:

```python
    # ------------------------------------------------------------------
    # 2. Rolling 12-month instance + menu registered
    # ------------------------------------------------------------------
    instance_id = xmlid("mis_report_instance_havi")
    period_count = call(
        "mis.report.instance.period", "search_count",
        [[("report_instance_id", "=", instance_id)]],
    )
    if period_count != 12:
        fail(f"Expected 12 periods on the rolling instance, found {period_count}")
    ok(f"Rolling instance has {period_count} periods")

    menu_id = xmlid("menu_dentari_mis_havi")
    action_id = xmlid("action_mis_report_instance_havi")
    action = call(
        "ir.actions.act_window", "read", [action_id],
        fields=["res_model", "res_id"],
    )[0]
    if action["res_model"] != "mis.report.instance" or action["res_id"] != instance_id:
        fail(f"Menu action does not point at the rolling instance: {action}")
    ok(f"Menu {menu_id} action points at instance {instance_id}")
```

- [ ] **Step 6: Commit**

```bash
git add dentari_mis_reports tests/test_mis_report.py
git commit -m "feat: rolling 12-month mis.report.instance + Statisztikák menu entry"
```

---

## Task 4: Dev-only QA test dashboard (demo data)

**Files:**
- Modify: `dentari_mis_reports/models/account_move.py` — implement
  `_load_dentari_mis_demo_data`
- Create: `dentari_mis_reports/demo/mis_report_demo.xml`
- Modify: `dentari_mis_reports/__manifest__.py:demo`
- Modify: `tests/test_mis_report.py` — append QA-dashboard assertions

**Interfaces:**
- Consumes: `dentari_mis_reports.mis_report_kiadas_bevetel` (Task 2);
  `dental_quick_expense.account_expense_fogtechnikai_anyag` (existing
  category account xmlid from `dental_quick_expense`).
- Produces: XML ID `dentari_mis_reports.mis_report_instance_qa`. Nothing
  downstream consumes this — it's a leaf, dev-only dashboard.

- [ ] **Step 1: Implement the demo-data seeder**

Replace the body of `_load_dentari_mis_demo_data` in
`dentari_mis_reports/models/account_move.py`:

```python
from odoo import api, fields, models
from dateutil.relativedelta import relativedelta

DEMO_MIS_MARKER = 'dentari-mis-demo'


class AccountMove(models.Model):
    _inherit = 'account.move'

    @api.model
    def _load_dentari_mis_demo_data(self):
        """Idempotent demo-data seeder for the QA test dashboard.

        Creates one posted quick-expense vendor bill (Netto 100 000 Ft) and
        one dental.work.log (Összeg 200 000 Ft) in a single, clearly-labeled
        month, so a dev can eyeball Netto+Áfa=Bruttó and the margin calc
        instantly. Unlike dental_quick_expense's own demo data (left in
        draft on purpose), this bill is posted — the Kiadások KPI only
        counts posted moves, and a draft demo bill would render as zeros.
        """
        Move = self.env['account.move']
        if Move.search_count([('ref', '=', DEMO_MIS_MARKER)]):
            return

        partner = self.env['res.partner'].search(
            [('name', '=', 'Demo Kiadás Szállító')], limit=1,
        )
        if not partner:
            partner = self.env['res.partner'].create({
                'name': 'Demo Kiadás Szállító',
            })

        clinic = self.env['res.partner'].search(
            [('name', '=', 'Demo MIS Klinika Kft.')], limit=1,
        )
        if not clinic:
            clinic = self.env['res.partner'].create({
                'name': 'Demo MIS Klinika Kft.',
                'is_company': True,
            })

        tax = self.env['account.tax'].search(
            [('type_tax_use', '=', 'purchase')], limit=1,
        )
        account = self.env.ref(
            'dental_quick_expense.account_expense_fogtechnikai_anyag',
            raise_if_not_found=False,
        )
        if not account:
            return

        demo_date = fields.Date.context_today(self) - relativedelta(months=1)
        demo_date = demo_date.replace(day=15)

        move = Move.create({
            'move_type': 'in_invoice',
            'partner_id': partner.id,
            'invoice_date': demo_date,
            'ref': DEMO_MIS_MARKER,
            'invoice_line_ids': [(0, 0, {
                'account_id': account.id,
                'name': 'QA Teszt Kiadás – 100 000 Ft',
                'quantity': 1,
                'price_unit': 100000,
                'tax_ids': [(6, 0, [tax.id])] if tax else False,
            })],
        })
        move.action_post()

        self.env['dental.work.log'].create({
            'date': demo_date,
            'partner_id': clinic.id,
            'patient_name': 'QA Teszt Páciens',
            'work_type': 'korona',
            'pieces': 1,
            'price_per_piece': 200000,
            'notes': f'[{DEMO_MIS_MARKER}] QA test dashboard seed record',
        })
```

- [ ] **Step 2: Write the demo instance + function hook**

`dentari_mis_reports/demo/mis_report_demo.xml`:

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <function model="account.move" name="_load_dentari_mis_demo_data" eval="[]"/>

    <record id="mis_report_instance_qa" model="mis.report.instance">
        <field name="name">QA Teszt Riport</field>
        <field name="report_id" ref="mis_report_kiadas_bevetel"/>
    </record>

    <record id="mis_report_period_qa" model="mis.report.instance.period">
        <field name="report_instance_id" ref="mis_report_instance_qa"/>
        <field name="name">QA hónap</field>
        <field name="mode">relative</field>
        <field name="type">m</field>
        <field name="offset">-1</field>
        <field name="duration">1</field>
        <field name="sequence">10</field>
    </record>
</odoo>
```

- [ ] **Step 3: Register the demo file in the manifest**

In `dentari_mis_reports/__manifest__.py`, change:
```python
    'demo': [],
```
to:
```python
    'demo': [
        'demo/mis_report_demo.xml',
    ],
```

- [ ] **Step 4: Validate syntax locally**

Run:
```bash
python3 -c "import ast; ast.parse(open('dentari_mis_reports/models/account_move.py').read())"
python3 -c "import xml.dom.minidom as m; m.parse('dentari_mis_reports/demo/mis_report_demo.xml')"
```
Expected: no output.

- [ ] **Step 5: Append QA-dashboard assertions to the smoke test**

In `tests/test_mis_report.py`, insert this block right before the final
`print("-" * 60)` / `print("PASS...")` lines (this only passes on the dev
env, where demo data is enabled):

```python
    # ------------------------------------------------------------------
    # 3. Dev-only QA test dashboard computes the expected KPI values
    # ------------------------------------------------------------------
    qa_instance_id = xmlid("mis_report_instance_qa")

    demo_moves = call(
        "account.move", "search_read",
        [[("ref", "=", "dentari-mis-demo")]],
        fields=["amount_untaxed", "amount_tax"],
    )
    if not demo_moves:
        fail("Demo Kiadás move not found — is this the dev env with demo data enabled?")
    expected_netto = demo_moves[0]["amount_untaxed"]
    expected_afa = demo_moves[0]["amount_tax"]
    expected_brutto = expected_netto + expected_afa

    demo_logs = call(
        "dental.work.log", "search_read",
        [[("patient_name", "=", "QA Teszt Páciens")]],
        fields=["total_revenue"],
    )
    if not demo_logs:
        fail("Demo work log not found — is this the dev env with demo data enabled?")
    expected_revenue = demo_logs[0]["total_revenue"]
    expected_eredmeny = expected_revenue - expected_brutto

    result = call("mis.report.instance", "compute", [qa_instance_id])
    values_by_label = {
        row["label"]: row["cells"][0]["val"] for row in result["body"]
    }

    checks = [
        ("Netto", expected_netto),
        ("Áfa", expected_afa),
        ("Bruttó", expected_brutto),
        ("Bevétel (Összeg)", expected_revenue),
        ("Eredmény", expected_eredmeny),
    ]
    for label, expected in checks:
        actual = values_by_label.get(label)
        if actual != expected:
            fail(f"QA dashboard KPI '{label}': expected {expected}, got {actual}")
        ok(f"QA dashboard KPI '{label}' = {actual} Ft")
```

- [ ] **Step 6: Commit**

```bash
git add dentari_mis_reports tests/test_mis_report.py
git commit -m "feat: dev-only QA test dashboard with round-number demo data"
```

---

## Task 5: Deploy to dev, upgrade, verify live

**Files:** none (deploy + verification only).

**Interfaces:**
- Consumes: the full `dentari_mis_reports` module (Tasks 1-4) and
  `tests/test_mis_report.py`.

- [ ] **Step 1: Invoke the odoo-oecsh-ticket-deploy skill**

Use the `odoo-oecsh-ticket-deploy` skill to: push this branch, trigger an
oec.sh redeploy of the dev environment (`dentari-dev-8780`), then run a
module upgrade for `dentari_mis_reports` (which will also pull in
`mis_builder` as a new dependency — confirm it appears in Apps; if it
doesn't, see the Global Constraints risk note about `addons_path`).

- [ ] **Step 2: Run the smoke test against dev**

```bash
python tests/test_mis_report.py
```
Expected: `PASS  dentari_mis_reports smoke test completed successfully.`
with every `OK` line printed, including the three QA dashboard KPI checks.

If any step fails with `External ID not found`, resolve per the Global
Constraints risk note (look up the correct field/model xmlid in Settings →
Technical → Database Structure on the dev instance), fix the XML, upgrade
again, and re-run.

- [ ] **Step 3: Visually confirm in the UI**

Use Playwright against the dev instance: log in, navigate to **Dentari Lab
→ Statisztikák → Kiadás / Bevétel riport**, confirm the 12-column monthly
dashboard renders with the 5 KPI rows and no error banner. Take a screenshot
for the ticket/PR.

- [ ] **Step 4: Commit any fixes discovered during live verification**

If Step 2 or Step 3 required XML/Python fixes, commit them:
```bash
git add dentari_mis_reports tests/test_mis_report.py
git commit -m "fix: correct external IDs found during dev verification"
```
(Skip this step if no fixes were needed.)

---

## Self-Review Notes

- **Spec coverage:** revenue source (work.log direct) → Task 2 `lab` query;
  report content (Netto/Áfa/Bruttó/Összeg/Eredmény) → Task 2 KPIs; monthly
  rolling periods → Task 3; Query-based approach for both sides → Task 2;
  dev-only test dashboards with round numbers → Task 4; menu placement →
  Task 3. All five spec decisions have a task.
- **Placeholder scan:** no TBD/TODO left in shipped code — the one
  intentionally-empty method body in Task 1 is filled in by Task 2 of the
  *same* module before any task claims completion, and is explicitly
  labeled as filled in "by Task 4" rather than left vague.
- **Type consistency:** `_load_dentari_mis_demo_data` signature
  (`@api.model`, no args) matches between its Task 1 stub and Task 4
  implementation. `DEMO_MIS_MARKER` value `'dentari-mis-demo'` matches
  between the Python constant (Task 4) and the smoke test's string literal
  (Task 4) — both reference the same value, kept as a literal in the test
  since it's a separate process (XML-RPC) with no access to the Python
  constant.
