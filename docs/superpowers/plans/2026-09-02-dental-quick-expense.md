# Dental Quick Expense Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the `dental_quick_expense` Odoo 18 Community addon — a wizard that lets a dental technician record a business expense in a few fields, saving it as a **draft** `account.move` vendor bill, with no shadow data model.

**Architecture:** Standalone addon depending on `account` and `dentari_lab` (reused security groups only). A `dental.quick.expense` TransientModel wizard collects input and calls `account.move.create()` with one `account.move.line`; no `journal_id`/payable account is set explicitly — Odoo's own defaulting resolves those. An `account.move` computed field `expense_category_id` (stored, computed from the move's line whose `account_id` is one of 11 seeded expense accounts) doubles as both a UI convenience column and the domain that scopes the "Kiadások" list to only this addon's moves — this avoids guessing at journal identity, which the spec leaves for Phase 0 to confirm.

**Tech Stack:** Odoo 18 Community, Python, XML views, Odoo ORM/TransactionCase tests, oec.sh SaaS hosting.

**Spec:** [docs/superpowers/specs/2026-09-02-dental-quick-expense-design.md](/Users/ferko/development/DentariOdoo/docs/superpowers/specs/2026-09-02-dental-quick-expense-design.md)

## Global Constraints

- No dependency on `hr`, `hr_expense`, `purchase`, `stock`, `project`, `mrp` (ticket §3).
- Depends only on `account` and `dentari_lab` (for `group_lab_technician` / `group_lab_manager`) — no new `res.groups` hierarchy.
- Every persisted expense is a standard `account.move` (`move_type='in_invoice'`) — no custom expense model, no second data store.
- Save never calls `.action_post()` — record stays `draft` (ticket §8).
- No Odoo accounting terminology (Journal Entry, Move, Payable Account, Reconciliation) in any user-facing label — all UI strings in Hungarian per spec §UI.
- Uninstalling the addon must not delete `account.move` / `account.move.line` / `ir.attachment` data (ticket §16).
- Out of scope for v1: HR Expense, employees, approval workflow, budgets, PO/Inventory/Project/MRP, timesheets, analytic accounting, OCR, dashboards, custom payment/accounting logic.
- Module name: `dental_quick_expense`, version starts at `18.0.1.0.0`, license `LGPL-3` (matches `dentari_lab` convention).
- Dev environment: oec.sh `dentari-dev-8780`, database `1a918a02-54a2-4bbc-b88f-dd04abb51d77` (alias `dentariodo_dev` in Docker), credentials in `.env.dev`. Auto-deploy on push is **disabled** — every deploy needs an explicit trigger + module upgrade step (see `odoo-oecsh-ticket-deploy` skill).

---

## File Structure

```
dental_quick_expense/
├── __init__.py                     # imports models, wizard
├── __manifest__.py                 # module metadata, data file list
├── data/
│   └── expense_categories.xml      # 11 seeded account.account (type=expense) records
├── models/
│   ├── __init__.py
│   └── account_move.py             # expense_category_id compute + quick_expense_category_accounts() helper
├── wizard/
│   ├── __init__.py
│   └── quick_expense.py            # dental.quick.expense TransientModel + action_save()
├── views/
│   ├── quick_expense_views.xml     # wizard form
│   ├── expense_list_views.xml      # account.move list view + act_window, domain-scoped
│   └── menus.xml                   # Kiadások > Kiadások / Új kiadás
├── security/
│   └── ir.model.access.csv         # ACL for dental.quick.expense (reuses dentari_lab groups)
└── tests/
    ├── __init__.py
    └── test_quick_expense.py       # TransactionCase covering spec's 5 test cases + category/domain checks
```

Root-level, throwaway (not committed as addon code):
```
scripts/spike_quick_expense.py      # Phase 0 spike script (XML-RPC against dev), deleted after Task 1
docs/dental_quick_expense-spike-findings.md   # committed — findings feed Tasks 2-9
```

---

### Task 1: Phase 0 Spike — confirm account.move creation behavior on live dev

**Files:**
- Create: `scripts/spike_quick_expense.py` (throwaway, removed at end of task)
- Create: `docs/dental_quick_expense-spike-findings.md` (committed)

**Interfaces:**
- Consumes: `.env.dev` credentials (`ODOO_URL`, `ODOO_DATABASE`, `ODOO_USERNAME`, `ODOO_PASSWORD`), same loader pattern as `tests/test_monthly_email.py`.
- Produces: `docs/dental_quick_expense-spike-findings.md` — read by a human before Task 3 (wizard `action_save()`) to confirm the minimal-field approach below actually works on this instance. No later task's code depends on unknown values; the doc is a confirmation record, not a source of new field names.

This task answers the spec's 5 Phase-0 questions (design doc "Phase 0 Spike" section) against the real dev instance before trusting the minimal-field design used in Tasks 3-9.

- [ ] **Step 1: Write the spike script**

```python
"""
Phase 0 spike — dental_quick_expense.
Answers the 5 questions in docs/superpowers/specs/2026-09-02-dental-quick-expense-design.md
("Phase 0 Spike" section) against the live dev Odoo instance.

Usage:
  python scripts/spike_quick_expense.py

Credentials loaded from .env.dev in the repo root.
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


def main() -> None:
    load_env(Path(__file__).resolve().parent.parent / ".env.dev")
    url = os.environ["ODOO_URL"]
    db = os.environ["ODOO_DATABASE"]
    username = os.environ["ODOO_USERNAME"]
    password = os.environ["ODOO_PASSWORD"]

    common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common")
    uid = common.authenticate(db, username, password, {})
    models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object")

    def call(model, method, *args, **kwargs):
        return models.execute_kw(db, uid, password, model, method, list(args), kwargs)

    print("=== Q1/Q2: minimal account.move.create() for a draft Vendor Bill ===")
    partner_ids = call("res.partner", "search", [[("supplier_rank", ">", 0)]], limit=1)
    if not partner_ids:
        partner_ids = call("res.partner", "search", [[]], limit=1)
    partner_id = partner_ids[0]

    expense_account_ids = call(
        "account.account", "search",
        [[("account_type", "=", "expense")]], limit=1,
    )
    account_id = expense_account_ids[0]

    tax_ids = call(
        "account.tax", "search",
        [[("type_tax_use", "=", "purchase")]], limit=1,
    )
    tax_id = tax_ids[0] if tax_ids else False

    move_vals = {
        "move_type": "in_invoice",
        "partner_id": partner_id,
        "invoice_date": "2026-09-02",
        "invoice_line_ids": [(0, 0, {
            "account_id": account_id,
            "name": "Spike test line",
            "quantity": 1,
            "price_unit": 1000,
            "tax_ids": [(6, 0, [tax_id])] if tax_id else False,
        })],
    }
    move_id = call("account.move", "create", move_vals)
    move = call(
        "account.move", "read", [move_id],
        {"fields": ["state", "journal_id", "amount_untaxed", "amount_tax", "amount_total"]},
    )[0]
    print("Created move:", move)
    print("-> state should be 'draft'; journal_id shows the auto-picked journal (Q2).")

    print()
    print("=== Q3: existing chart-of-accounts codes for account_type=expense ===")
    expense_accounts = call(
        "account.account", "search_read",
        [[("account_type", "=", "expense")]],
        {"fields": ["code", "name"], "limit": 40, "order": "code"},
    )
    for acc in expense_accounts:
        print(f"  {acc['code']}  {acc['name']}")
    print("-> pick 11 unused codes in this range for data/expense_categories.xml.")

    print()
    print("=== Q4: tax total on the created move ===")
    print(f"amount_untaxed={move['amount_untaxed']} amount_tax={move['amount_tax']} amount_total={move['amount_total']}")
    print("-> confirms tax_ids=[(6,0,[tax_id])] on the line computes the total correctly.")

    print()
    print("=== Q5: relinking an ir.attachment from a transient record onto the move ===")
    attachment_id = call(
        "ir.attachment", "create",
        {
            "name": "spike.txt",
            "datas": "dGVzdA==",  # "test" base64
            "res_model": "dental.quick.expense",
            "res_id": 0,
        },
    )
    call("ir.attachment", "write", [[attachment_id], {
        "res_model": "account.move",
        "res_id": move_id,
    }])
    att = call("ir.attachment", "read", [attachment_id], {"fields": ["res_model", "res_id"]})[0]
    print("Attachment after relink:", att)
    print("-> confirms write({'res_model': ..., 'res_id': ...}) is a safe relink pattern.")

    print()
    print("=== Cleanup ===")
    call("account.move", "unlink", [[move_id]])
    call("ir.attachment", "unlink", [[attachment_id]])
    print("Spike move and attachment removed.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the spike against dev**

Run: `python scripts/spike_quick_expense.py`

Expected: script prints output for all 5 sections without raising. If `account.move.create()` raises a fault (e.g. missing `journal_id`), that is itself a finding — capture the exact fault message.

- [ ] **Step 3: Write the findings doc**

Create `docs/dental_quick_expense-spike-findings.md` with one short answer per question, using the script's actual output:

```markdown
# Dental Quick Expense — Phase 0 Spike Findings

Date: <run date>. Ran against dentari-dev-8780 via `scripts/spike_quick_expense.py`.

1. **Minimal fields for a valid Draft Vendor Bill:** move_type, partner_id,
   invoice_date, one invoice_line_ids tuple (account_id, name, quantity,
   price_unit, tax_ids) — <confirmed / adjustments needed: ...>
2. **journal_id / payable account defaulting:** <which journal Odoo picked,
   and whether it's shared with other vendor bills — this determines
   whether `expense_category_id != False` is a sufficient list-domain
   filter (it is, since it doesn't depend on journal identity) or whether
   a journal-based filter would additionally be needed.>
3. **Expense account codes already in use:** <range/codes observed> —
   11 codes chosen for data/expense_categories.xml: <list>.
4. **Tax computation on a single-line bill:** <amount_untaxed/amount_tax/
   amount_total observed, confirms tax_ids=[(6,0,[tax_id])] is correct>.
5. **Attachment relink pattern:** <confirmed ir.attachment.write({res_model,
   res_id}) works with no error>.
```

- [ ] **Step 4: Remove the throwaway script, commit the findings doc**

```bash
rm scripts/spike_quick_expense.py
git add docs/dental_quick_expense-spike-findings.md
git commit -m "docs: record Phase 0 spike findings for dental_quick_expense"
```

---

### Task 2: Addon scaffold + expense category data

**Files:**
- Create: `dental_quick_expense/__init__.py`
- Create: `dental_quick_expense/__manifest__.py`
- Create: `dental_quick_expense/models/__init__.py`
- Create: `dental_quick_expense/models/account_move.py`
- Create: `dental_quick_expense/wizard/__init__.py`
- Create: `dental_quick_expense/data/expense_categories.xml`
- Create: `dental_quick_expense/security/ir.model.access.csv`
- Create: `dental_quick_expense/tests/__init__.py`
- Test: `dental_quick_expense/tests/test_quick_expense.py`

**Interfaces:**
- Produces: `quick_expense_category_accounts(env)` module function in `models/account_move.py` — returns an `account.account` recordset of the 11 seeded category accounts. Used by Task 3 (wizard field domain), Task 4 (compute), and this task's own test.
- Produces: 11 `account.account` xmlids under the `dental_quick_expense.` prefix (exact codes/names below), matching ticket §9's category list.

Use the codes/names recorded in Task 1's findings doc if they differ from the placeholders below (`4xx` range is illustrative — replace with the actual free codes found in Task 1).

- [ ] **Step 1: Write the failing test**

```python
# dental_quick_expense/tests/test_quick_expense.py
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestQuickExpenseCategories(TransactionCase):

    def test_eleven_category_accounts_seeded(self):
        from odoo.addons.dental_quick_expense.models.account_move import (
            quick_expense_category_accounts,
        )
        accounts = quick_expense_category_accounts(self.env)
        self.assertEqual(len(accounts), 11)
        self.assertTrue(all(a.account_type == 'expense' for a in accounts))
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
docker compose exec odoo odoo \
  -d dentariodo_dev --test-enable --stop-after-init \
  -i dental_quick_expense --test-tags dental_quick_expense
```
Expected: FAIL — module `dental_quick_expense` not found / import error (nothing exists yet).

- [ ] **Step 3: Write the manifest and package init files**

```python
# dental_quick_expense/__manifest__.py
{
    'name': 'Dental Quick Expense',
    'version': '18.0.1.0.0',
    'category': 'Dental / Accounting',
    'summary': 'Lightweight expense recording wizard over Vendor Bills',
    'depends': ['account', 'dentari_lab'],
    'data': [
        'security/ir.model.access.csv',
        'data/expense_categories.xml',
        'views/quick_expense_views.xml',
        'views/expense_list_views.xml',
        'views/menus.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
```

```python
# dental_quick_expense/__init__.py
from . import models
from . import wizard
```

```python
# dental_quick_expense/models/__init__.py
from . import account_move
```

```python
# dental_quick_expense/wizard/__init__.py
```

```python
# dental_quick_expense/tests/__init__.py
from . import test_quick_expense
```

- [ ] **Step 4: Write the category data file**

```xml
<!-- dental_quick_expense/data/expense_categories.xml -->
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <data noupdate="1">
        <record id="account_expense_fogtechnikai_anyag" model="account.account">
            <field name="name">Fogtechnikai anyag</field>
            <field name="code">4001</field>
            <field name="account_type">expense</field>
        </record>
        <record id="account_expense_futar_szallitas" model="account.account">
            <field name="name">Futár / szállítás</field>
            <field name="code">4002</field>
            <field name="account_type">expense</field>
        </record>
        <record id="account_expense_uzemanyag" model="account.account">
            <field name="name">Üzemanyag</field>
            <field name="code">4003</field>
            <field name="account_type">expense</field>
        </record>
        <record id="account_expense_gep_eszkoz" model="account.account">
            <field name="name">Gép / eszköz</field>
            <field name="code">4004</field>
            <field name="account_type">expense</field>
        </record>
        <record id="account_expense_gepkarbantartas" model="account.account">
            <field name="name">Gépkarbantartás</field>
            <field name="code">4005</field>
            <field name="account_type">expense</field>
        </record>
        <record id="account_expense_telefon_internet" model="account.account">
            <field name="name">Telefon / internet</field>
            <field name="code">4006</field>
            <field name="account_type">expense</field>
        </record>
        <record id="account_expense_rezsi" model="account.account">
            <field name="name">Rezsi</field>
            <field name="code">4007</field>
            <field name="account_type">expense</field>
        </record>
        <record id="account_expense_konyveles" model="account.account">
            <field name="name">Könyvelés</field>
            <field name="code">4008</field>
            <field name="account_type">expense</field>
        </record>
        <record id="account_expense_szoftver" model="account.account">
            <field name="name">Szoftver</field>
            <field name="code">4009</field>
            <field name="account_type">expense</field>
        </record>
        <record id="account_expense_oktatas" model="account.account">
            <field name="name">Oktatás</field>
            <field name="code">4010</field>
            <field name="account_type">expense</field>
        </record>
        <record id="account_expense_egyeb" model="account.account">
            <field name="name">Egyéb</field>
            <field name="code">4011</field>
            <field name="account_type">expense</field>
        </record>
    </data>
</odoo>
```

**Note:** if Task 1's findings show codes `4001`-`4011` collide with an existing account, replace the `code` values with the free range found in the spike before this data file is loaded on dev.

- [ ] **Step 5: Write the account_move.py helper (compute field added in Task 4; helper needed now for the test)**

```python
# dental_quick_expense/models/account_move.py
from odoo import api, fields, models

QUICK_EXPENSE_CATEGORY_XMLIDS = [
    'dental_quick_expense.account_expense_fogtechnikai_anyag',
    'dental_quick_expense.account_expense_futar_szallitas',
    'dental_quick_expense.account_expense_uzemanyag',
    'dental_quick_expense.account_expense_gep_eszkoz',
    'dental_quick_expense.account_expense_gepkarbantartas',
    'dental_quick_expense.account_expense_telefon_internet',
    'dental_quick_expense.account_expense_rezsi',
    'dental_quick_expense.account_expense_konyveles',
    'dental_quick_expense.account_expense_szoftver',
    'dental_quick_expense.account_expense_oktatas',
    'dental_quick_expense.account_expense_egyeb',
]


def quick_expense_category_accounts(env):
    """Return the recordset of the 11 seeded Kiadások category accounts."""
    accounts = env['account.account']
    for xmlid in QUICK_EXPENSE_CATEGORY_XMLIDS:
        account = env.ref(xmlid, raise_if_not_found=False)
        if account:
            accounts |= account
    return accounts


class AccountMove(models.Model):
    _inherit = 'account.move'
```

- [ ] **Step 6: Write the ACL file (dental.quick.expense model added in Task 3; placeholder row needed to keep the file valid — will gain the real row in Task 3)**

```csv
id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink
```

(Header only for now — Task 3 adds the `dental.quick.expense` row once that model exists. An empty-but-valid CSV lets the module install cleanly at this step.)

- [ ] **Step 7: Run test to verify it passes**

Run:
```bash
docker compose exec odoo odoo \
  -d dentariodo_dev --test-enable --stop-after-init \
  -i dental_quick_expense --test-tags dental_quick_expense
```
Expected: PASS — `test_eleven_category_accounts_seeded` succeeds, module installs.

- [ ] **Step 8: Commit**

```bash
git add dental_quick_expense/
git commit -m "feat: scaffold dental_quick_expense addon with 11 expense categories"
```

---

### Task 3: Wizard model — action_save() creates a draft Vendor Bill

**Files:**
- Create: `dental_quick_expense/wizard/quick_expense.py`
- Modify: `dental_quick_expense/wizard/__init__.py`
- Modify: `dental_quick_expense/security/ir.model.access.csv`
- Test: `dental_quick_expense/tests/test_quick_expense.py`

**Interfaces:**
- Consumes: `quick_expense_category_accounts(env)` from `models/account_move.py` (Task 2).
- Produces: `dental.quick.expense` TransientModel with fields `date`, `partner_id`, `category_account_id`, `description`, `net_amount`, `currency_id`, `tax_id`, `ref`, `attachment_ids`, and method `action_save()` returning an `ir.actions.act_window` dict (`res_model='account.move'`). Later tasks (4, 5, 7, 8, 9) extend this class and its test file.

- [ ] **Step 1: Write the failing test**

```python
# append to dental_quick_expense/tests/test_quick_expense.py
from odoo.exceptions import ValidationError


@tagged('post_install', '-at_install')
class TestQuickExpenseWizard(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env['res.partner'].create({'name': 'Teszt Szállító'})
        from odoo.addons.dental_quick_expense.models.account_move import (
            quick_expense_category_accounts,
        )
        cls.category = quick_expense_category_accounts(cls.env)[0]
        cls.tax = cls.env['account.tax'].search(
            [('type_tax_use', '=', 'purchase')], limit=1,
        )

    def test_action_save_creates_draft_vendor_bill(self):
        wizard = self.env['dental.quick.expense'].create({
            'date': '2026-09-02',
            'partner_id': self.partner.id,
            'category_account_id': self.category.id,
            'description': 'Teszt kiadás',
            'net_amount': 5000,
            'tax_id': self.tax.id,
        })
        wizard.action_save()

        moves = self.env['account.move'].search([
            ('partner_id', '=', self.partner.id),
            ('move_type', '=', 'in_invoice'),
        ])
        self.assertEqual(len(moves), 1)
        move = moves[0]
        self.assertEqual(move.state, 'draft')
        self.assertEqual(len(move.invoice_line_ids), 1)
        line = move.invoice_line_ids[0]
        self.assertEqual(line.account_id, self.category)
        self.assertEqual(line.name, 'Teszt kiadás')
        self.assertEqual(line.price_unit, 5000)

    def test_missing_required_field_blocks_save(self):
        with self.assertRaises(ValidationError):
            self.env['dental.quick.expense'].create({
                'partner_id': self.partner.id,
                'category_account_id': self.category.id,
                'description': 'Teszt hiányos',
                'tax_id': self.tax.id,
                # net_amount intentionally omitted
            })
        moves = self.env['account.move'].search([
            ('partner_id', '=', self.partner.id),
            ('ref', '=', False),
            ('invoice_line_ids.name', '=', 'Teszt hiányos'),
        ])
        self.assertEqual(len(moves), 0)
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
docker compose exec odoo odoo \
  -d dentariodo_dev --test-enable --stop-after-init \
  -i dental_quick_expense --test-tags dental_quick_expense
```
Expected: FAIL — `dental.quick.expense` model does not exist.

- [ ] **Step 3: Write the wizard model**

```python
# dental_quick_expense/wizard/quick_expense.py
from odoo import _, fields, models
from odoo.exceptions import UserError

from ..models.account_move import quick_expense_category_accounts


class DentalQuickExpense(models.TransientModel):
    _name = 'dental.quick.expense'
    _description = 'Gyors kiadás rögzítése'

    date = fields.Date(
        string='Dátum', required=True, default=fields.Date.context_today,
    )
    partner_id = fields.Many2one(
        'res.partner', string='Szállító', required=True,
    )
    category_account_id = fields.Many2one(
        'account.account',
        string='Kategória',
        required=True,
        domain=lambda self: [('id', 'in', quick_expense_category_accounts(self.env).ids)],
    )
    description = fields.Char(string='Leírás', required=True)
    currency_id = fields.Many2one(
        'res.currency',
        default=lambda self: self.env.company.currency_id,
        required=True,
    )
    net_amount = fields.Monetary(
        string='Nettó összeg', required=True, currency_field='currency_id',
    )
    tax_id = fields.Many2one(
        'account.tax',
        string='ÁFA',
        required=True,
        domain=[('type_tax_use', '=', 'purchase')],
    )
    ref = fields.Char(string='Bizonylatszám')
    attachment_ids = fields.Many2many('ir.attachment', string='Bizonylat')

    def action_save(self):
        self.ensure_one()
        if not self.category_account_id.exists():
            raise UserError(_('A kiadás kategória nem található.'))

        move = self.env['account.move'].create({
            'move_type': 'in_invoice',
            'partner_id': self.partner_id.id,
            'invoice_date': self.date,
            'ref': self.ref,
            'invoice_line_ids': [(0, 0, {
                'account_id': self.category_account_id.id,
                'name': self.description,
                'quantity': 1,
                'price_unit': self.net_amount,
                'tax_ids': [(6, 0, [self.tax_id.id])],
            })],
        })

        if self.attachment_ids:
            self.attachment_ids.write({
                'res_model': 'account.move',
                'res_id': move.id,
            })

        return {
            'type': 'ir.actions.act_window',
            'name': _('Kiadás'),
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': move.id,
            'target': 'current',
        }
```

```python
# dental_quick_expense/wizard/__init__.py
from . import quick_expense
```

- [ ] **Step 4: Add the ACL row**

```csv
id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink
access_quick_expense_technician,quick expense technician,model_dental_quick_expense,dentari_lab.group_lab_technician,1,1,1,0
access_quick_expense_manager,quick expense manager,model_dental_quick_expense,dentari_lab.group_lab_manager,1,1,1,1
```

- [ ] **Step 5: Run test to verify it passes**

Run:
```bash
docker compose exec odoo odoo \
  -d dentariodo_dev --test-enable --stop-after-init \
  -i dental_quick_expense --test-tags dental_quick_expense
```
Expected: PASS — both tests in `TestQuickExpenseWizard` succeed.

- [ ] **Step 6: Commit**

```bash
git add dental_quick_expense/
git commit -m "feat: dental.quick.expense wizard creates draft Vendor Bill"
```

---

### Task 4: account.move computed field expense_category_id

**Files:**
- Modify: `dental_quick_expense/models/account_move.py`
- Test: `dental_quick_expense/tests/test_quick_expense.py`

**Interfaces:**
- Consumes: `quick_expense_category_accounts(env)` (Task 2), `dental.quick.expense` wizard (Task 3).
- Produces: `account.move.expense_category_id` (stored `Many2one('account.account')`), `False` for any move whose lines don't touch a seeded category account. Task 6 uses this field as the Kiadások list domain.

- [ ] **Step 1: Write the failing test**

```python
# append to dental_quick_expense/tests/test_quick_expense.py
class TestQuickExpenseComputedCategory(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env['res.partner'].create({'name': 'Teszt Szállító 2'})
        from odoo.addons.dental_quick_expense.models.account_move import (
            quick_expense_category_accounts,
        )
        cls.category = quick_expense_category_accounts(cls.env)[0]

    def test_expense_category_id_computed_from_line(self):
        move = self.env['account.move'].create({
            'move_type': 'in_invoice',
            'partner_id': self.partner.id,
            'invoice_line_ids': [(0, 0, {
                'account_id': self.category.id,
                'name': 'Teszt sor',
                'quantity': 1,
                'price_unit': 100,
            })],
        })
        self.assertEqual(move.expense_category_id, self.category)

    def test_expense_category_id_false_for_unrelated_bill(self):
        other_account = self.env['account.account'].search([
            ('account_type', '=', 'expense'),
            ('id', 'not in', self.category.ids),
        ], limit=1)
        move = self.env['account.move'].create({
            'move_type': 'in_invoice',
            'partner_id': self.partner.id,
            'invoice_line_ids': [(0, 0, {
                'account_id': other_account.id,
                'name': 'Nem kiadás',
                'quantity': 1,
                'price_unit': 100,
            })],
        })
        self.assertFalse(move.expense_category_id)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec odoo odoo -d dentariodo_dev --test-enable --stop-after-init -i dental_quick_expense --test-tags dental_quick_expense`
Expected: FAIL — `expense_category_id` field does not exist on `account.move`.

- [ ] **Step 3: Add the compute**

```python
# dental_quick_expense/models/account_move.py — replace the AccountMove class body
class AccountMove(models.Model):
    _inherit = 'account.move'

    expense_category_id = fields.Many2one(
        'account.account',
        string='Kategória',
        compute='_compute_expense_category_id',
        store=True,
    )

    @api.depends('invoice_line_ids.account_id')
    def _compute_expense_category_id(self):
        category_accounts = quick_expense_category_accounts(self.env)
        for move in self:
            line = move.invoice_line_ids.filtered(
                lambda l: l.account_id in category_accounts
            )
            move.expense_category_id = line[:1].account_id
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec odoo odoo -d dentariodo_dev --test-enable --stop-after-init -i dental_quick_expense --test-tags dental_quick_expense`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add dental_quick_expense/models/account_move.py dental_quick_expense/tests/test_quick_expense.py
git commit -m "feat: compute expense_category_id on account.move"
```

---

### Task 5: Attachment relink and category-domain tests

**Files:**
- Test: `dental_quick_expense/tests/test_quick_expense.py`

**Interfaces:**
- Consumes: `action_save()` (Task 3), `quick_expense_category_accounts(env)` (Task 2). No production code changes — Task 3's `action_save()` already relinks attachments and Task 3's field domain already restricts categories; this task adds the two spec-mandated regression tests that prove it.

- [ ] **Step 1: Write the tests**

```python
# append to TestQuickExpenseWizard in dental_quick_expense/tests/test_quick_expense.py
    def test_attachment_relinked_to_move_not_wizard(self):
        wizard = self.env['dental.quick.expense'].create({
            'date': '2026-09-02',
            'partner_id': self.partner.id,
            'category_account_id': self.category.id,
            'description': 'Kiadás csatolmánnyal',
            'net_amount': 3000,
            'tax_id': self.tax.id,
        })
        attachment = self.env['ir.attachment'].create({
            'name': 'bizonylat.pdf',
            'datas': 'dGVzdA==',
            'res_model': 'dental.quick.expense',
            'res_id': wizard.id,
        })
        wizard.attachment_ids = [(6, 0, [attachment.id])]
        wizard.action_save()

        self.assertEqual(attachment.res_model, 'account.move')
        self.assertNotEqual(attachment.res_id, wizard.id)

    def test_category_domain_excludes_non_expense_accounts(self):
        from odoo.addons.dental_quick_expense.models.account_move import (
            quick_expense_category_accounts,
        )
        revenue_account = self.env['account.account'].search([
            ('account_type', '=', 'income'),
        ], limit=1)
        self.assertNotIn(
            revenue_account.id, quick_expense_category_accounts(self.env).ids,
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec odoo odoo -d dentariodo_dev --test-enable --stop-after-init -i dental_quick_expense --test-tags dental_quick_expense`
Expected: FAIL if a revenue account doesn't exist in a fresh test DB — if so, create one inline in the test (`self.env['account.account'].create({'name': 'Teszt bevétel', 'code': '9999', 'account_type': 'income'})`) rather than relying on seed data. Update the test accordingly before re-running.

- [ ] **Step 3: Run test to verify it passes**

Run: `docker compose exec odoo odoo -d dentariodo_dev --test-enable --stop-after-init -i dental_quick_expense --test-tags dental_quick_expense`
Expected: PASS — both new tests succeed alongside the existing ones.

- [ ] **Step 4: Commit**

```bash
git add dental_quick_expense/tests/test_quick_expense.py
git commit -m "test: cover attachment relink and category domain exclusion"
```

---

### Task 6: Views — wizard form, Kiadások list, menus

**Files:**
- Create: `dental_quick_expense/views/quick_expense_views.xml`
- Create: `dental_quick_expense/views/expense_list_views.xml`
- Create: `dental_quick_expense/views/menus.xml`
- Test: `dental_quick_expense/tests/test_quick_expense.py`

**Interfaces:**
- Consumes: `dental.quick.expense` model (Task 3), `account.move.expense_category_id` (Task 4).
- Produces: xmlids `dental_quick_expense.view_quick_expense_form`, `dental_quick_expense.action_dental_quick_expense_list`, `dental_quick_expense.action_dental_quick_expense_new`, `dental_quick_expense.menu_dental_quick_expense_root`. Task 3's `action_save()` references `dental_quick_expense.action_dental_quick_expense_list` by xmlid — this task must define that action with exactly that id.

**Note:** update `wizard/quick_expense.py`'s `action_save()` (Task 3) to return the Kiadások list narrowed to the new move, per spec, instead of the form — this task supersedes Task 3's temporary return value.

- [ ] **Step 1: Write the failing test**

```python
# append to test_quick_expense.py
@tagged('post_install', '-at_install')
class TestQuickExpenseViews(TransactionCase):

    def test_views_and_actions_registered(self):
        self.assertTrue(self.env.ref('dental_quick_expense.view_quick_expense_form'))
        self.assertTrue(self.env.ref('dental_quick_expense.action_dental_quick_expense_list'))
        self.assertTrue(self.env.ref('dental_quick_expense.action_dental_quick_expense_new'))
        self.assertTrue(self.env.ref('dental_quick_expense.menu_dental_quick_expense_root'))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec odoo odoo -d dentariodo_dev --test-enable --stop-after-init -i dental_quick_expense --test-tags dental_quick_expense`
Expected: FAIL — xmlids don't exist yet.

- [ ] **Step 3: Write the wizard form view**

```xml
<!-- dental_quick_expense/views/quick_expense_views.xml -->
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="view_quick_expense_form" model="ir.ui.view">
        <field name="name">dental.quick.expense.form</field>
        <field name="model">dental.quick.expense</field>
        <field name="arch" type="xml">
            <form string="Új kiadás">
                <group>
                    <field name="date"/>
                    <field name="partner_id"/>
                    <field name="category_account_id"/>
                    <field name="description"/>
                    <field name="net_amount"/>
                    <field name="currency_id" invisible="1"/>
                    <field name="tax_id"/>
                    <field name="ref"/>
                    <field name="attachment_ids" widget="many2many_binary" string="Bizonylat"/>
                </group>
                <footer>
                    <button name="action_save" type="object"
                            string="Mentés" class="btn-primary"/>
                    <button string="Mégse" class="btn-secondary" special="cancel"/>
                </footer>
            </form>
        </field>
    </record>

    <record id="action_dental_quick_expense_new" model="ir.actions.act_window">
        <field name="name">Új kiadás</field>
        <field name="res_model">dental.quick.expense</field>
        <field name="view_mode">form</field>
        <field name="target">new</field>
    </record>
</odoo>
```

- [ ] **Step 4: Write the Kiadások list view**

```xml
<!-- dental_quick_expense/views/expense_list_views.xml -->
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="view_dental_quick_expense_list" model="ir.ui.view">
        <field name="name">dental.quick.expense.account.move.list</field>
        <field name="model">account.move</field>
        <field name="arch" type="xml">
            <list string="Kiadások" create="false">
                <field name="invoice_date" string="Dátum"/>
                <field name="partner_id" string="Szállító"/>
                <field name="expense_category_id" string="Kategória"/>
                <field name="amount_untaxed" string="Nettó"/>
                <field name="amount_tax" string="ÁFA"/>
                <field name="state" string="Státusz"/>
            </list>
        </field>
    </record>

    <record id="action_dental_quick_expense_list" model="ir.actions.act_window">
        <field name="name">Kiadások</field>
        <field name="res_model">account.move</field>
        <field name="view_mode">list,form</field>
        <field name="domain">[('expense_category_id', '!=', False)]</field>
        <field name="view_id" ref="view_dental_quick_expense_list"/>
    </record>
</odoo>
```

- [ ] **Step 5: Write the menus**

```xml
<!-- dental_quick_expense/views/menus.xml -->
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <menuitem
        id="menu_dental_quick_expense_root"
        name="Kiadások"
        sequence="110"
        groups="dentari_lab.group_lab_technician"
    />

    <menuitem
        id="menu_dental_quick_expense_list"
        name="Kiadások"
        parent="menu_dental_quick_expense_root"
        action="action_dental_quick_expense_list"
        sequence="10"
    />

    <menuitem
        id="menu_dental_quick_expense_new"
        name="Új kiadás"
        parent="menu_dental_quick_expense_root"
        action="action_dental_quick_expense_new"
        sequence="20"
    />
</odoo>
```

- [ ] **Step 6: Point action_save() at the Kiadások list**

Modify `dental_quick_expense/wizard/quick_expense.py` — replace `action_save()`'s `return` statement:

```python
        action = self.env['ir.actions.act_window']._for_xml_id(
            'dental_quick_expense.action_dental_quick_expense_list'
        )
        action['domain'] = [('id', '=', move.id)]
        return action
```

- [ ] **Step 7: Run test to verify it passes**

Run: `docker compose exec odoo odoo -d dentariodo_dev --test-enable --stop-after-init -i dental_quick_expense --test-tags dental_quick_expense`
Expected: PASS — all tests including `test_action_save_creates_draft_vendor_bill` (still passes since it doesn't inspect the return value) and the new view test.

- [ ] **Step 8: Commit**

```bash
git add dental_quick_expense/views/ dental_quick_expense/wizard/quick_expense.py dental_quick_expense/tests/test_quick_expense.py
git commit -m "feat: wizard form, Kiadások list, and menu wiring"
```

---

### Task 7: Kiadások list scoping and error-handling regression tests

**Files:**
- Test: `dental_quick_expense/tests/test_quick_expense.py`

**Interfaces:**
- Consumes: `action_dental_quick_expense_list` domain (Task 6), `action_save()` category-missing `UserError` (Task 3).

- [ ] **Step 1: Write the tests**

```python
# append to test_quick_expense.py
from odoo.exceptions import UserError


@tagged('post_install', '-at_install')
class TestQuickExpenseListScope(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env['res.partner'].create({'name': 'Teszt Szállító 3'})
        from odoo.addons.dental_quick_expense.models.account_move import (
            quick_expense_category_accounts,
        )
        cls.category = quick_expense_category_accounts(cls.env)[0]
        cls.other_expense_account = cls.env['account.account'].search([
            ('account_type', '=', 'expense'),
            ('id', 'not in', cls.category.ids),
        ], limit=1)

    def test_list_domain_excludes_unrelated_vendor_bills(self):
        quick_move = self.env['account.move'].create({
            'move_type': 'in_invoice',
            'partner_id': self.partner.id,
            'invoice_line_ids': [(0, 0, {
                'account_id': self.category.id,
                'name': 'Kiadás',
                'quantity': 1,
                'price_unit': 100,
            })],
        })
        unrelated_move = self.env['account.move'].create({
            'move_type': 'in_invoice',
            'partner_id': self.partner.id,
            'invoice_line_ids': [(0, 0, {
                'account_id': self.other_expense_account.id,
                'name': 'Más számla',
                'quantity': 1,
                'price_unit': 100,
            })],
        })
        action = self.env.ref('dental_quick_expense.action_dental_quick_expense_list')
        domain = eval(action.domain)
        found = self.env['account.move'].search(domain)
        self.assertIn(quick_move, found)
        self.assertNotIn(unrelated_move, found)


@tagged('post_install', '-at_install')
class TestQuickExpenseErrorHandling(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env['res.partner'].create({'name': 'Teszt Szállító 4'})
        from odoo.addons.dental_quick_expense.models.account_move import (
            quick_expense_category_accounts,
        )
        cls.category = quick_expense_category_accounts(cls.env)[0]
        cls.tax = cls.env['account.tax'].search(
            [('type_tax_use', '=', 'purchase')], limit=1,
        )

    def test_removed_category_account_blocks_save(self):
        wizard = self.env['dental.quick.expense'].create({
            'date': '2026-09-02',
            'partner_id': self.partner.id,
            'category_account_id': self.category.id,
            'description': 'Kiadás törölt kategóriával',
            'net_amount': 1000,
            'tax_id': self.tax.id,
        })
        category_id = self.category.id
        self.category.unlink()
        wizard.invalidate_recordset()
        with self.assertRaises(UserError):
            wizard.action_save()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec odoo odoo -d dentariodo_dev --test-enable --stop-after-init -i dental_quick_expense --test-tags dental_quick_expense`
Expected: FAIL if `self.category.unlink()` itself raises (e.g. the account is referenced elsewhere by an ondelete-restrict FK) — if so, use a freshly created, unreferenced `account.account` for this test instead of one of the 11 seeded categories (create it, add it to a throwaway list monkeypatched via `category_account_id` directly rather than via the domain-restricted helper — the field itself doesn't enforce the domain at the ORM level, only in the UI, so setting an out-of-domain id directly still exercises `action_save()`'s existence check).

- [ ] **Step 3: Run test to verify it passes**

Run: `docker compose exec odoo odoo -d dentariodo_dev --test-enable --stop-after-init -i dental_quick_expense --test-tags dental_quick_expense`
Expected: PASS — full test suite green.

- [ ] **Step 4: Commit**

```bash
git add dental_quick_expense/tests/test_quick_expense.py
git commit -m "test: cover Kiadások list scoping and missing-category error handling"
```

---

### Task 8: Deploy to dev and verify live

**Files:** none (deploy + manual verification only)

**Interfaces:**
- Consumes: the full `dental_quick_expense/` addon (Tasks 2-7).

Use the `odoo-oecsh-ticket-deploy` skill for this task — it covers push, oec.sh redeploy trigger, Odoo dev-mode + module install/upgrade, Playwright screenshot, and issue-tracker (KAN-27) comment. Key points specific to this project (see `[[oecsh-autodeploy-disabled]]` memory):

- [ ] **Step 1: Push the branch and trigger an explicit dev deploy** (auto-deploy is disabled on `develop`/`main` — a push alone does not redeploy).

- [ ] **Step 2: Install/upgrade the module on dev**

```bash
docker compose exec odoo odoo -d dentariodo_dev -i dental_quick_expense --stop-after-init
```
(or the oec.sh `quick-update` / Apps UI equivalent per the skill).

- [ ] **Step 3: Manual E2E check** — log in to `https://dentari-dev-8780.apps.oec.sh`, open **Kiadások → Új kiadás**, fill all fields, attach a file, click **Mentés**. Verify: the Kiadások list opens showing exactly the new row, the underlying `account.move` is in Draft, and the attachment is visible on the bill (not on a transient record).

- [ ] **Step 4: Screenshot the flow via Playwright** and attach to the KAN-27 ticket comment, per the `odoo-oecsh-ticket-deploy` skill.

- [ ] **Step 5: Comment on KAN-27** summarizing what shipped and linking the dev environment.

---

## Self-Review Notes

- **Spec coverage:** menu structure (Task 6), wizard fields in ticket §7 order (Task 6 form), draft-only save / no `action_post()` (Task 3), category accounts as `account.account` not a custom model (Task 2), Kiadások list reads directly off `account.move` (Task 6), all 5 out-of-scope items honored (no new dependencies added anywhere), Phase 0 spike precedes implementation (Task 1), all 5 spec Testing-section cases covered (Tasks 3, 5, 4/7), Security ACL reusing `dentari_lab` groups (Task 3), Error Handling table's 4 rows covered (Task 3 required-field/category checks, Task 7 missing-category test; attachment-upload-fails and uninstall-safety are native Odoo/ORM behavior not requiring addon code, called out here rather than a fabricated test).
- **Placeholder scan:** the only literal placeholders are the illustrative `4001`-`4011` account codes in Task 2, explicitly flagged as replaceable from Task 1's real findings — not a TBD, a concrete default with a documented override condition.
- **Type consistency:** `quick_expense_category_accounts(env)` used identically in Tasks 2-7; `action_dental_quick_expense_list` xmlid matches between Task 3's usage and Task 6's definition; `expense_category_id` name matches between Task 4's compute and Task 6/7's domain and list view.
