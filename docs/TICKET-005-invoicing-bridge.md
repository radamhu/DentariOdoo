# TICKET-005 — Invoicing Bridge (M4)

| Field | Value |
|---|---|
| **Type** | Feature |
| **Priority** | High |
| **Milestone** | M4 — Invoicing Bridge |
| **Assignee** | — |
| **Reporter** | Dentari Development Team |
| **Created** | 2026-05-31 |
| **Updated** | 2026-05-31 |
| **Status** | Open |
| **Design ref** | [DESIGN.md §4](./DESIGN.md#4-milestone-roadmap) |
| **Depends on** | TICKET-001 (M1 — `dental.work.log` model), Odoo `account` (Invoicing) module installed |

---

## Summary

Add the ability to generate **draft customer invoices** (`account.move`) from selected, uninvoiced `dental.work.log` records. A Lab Manager selects work logs in the list view, triggers a wizard, and one `account.move` per clinic (partner) is created — each work log becomes a separate invoice line for full traceability. Work logs are marked as invoiced to prevent double-billing.

---

## Background

The Odoo `account` (Invoicing) module is now installed on the instance. `dental.work.log` records represent billable work items: each has a clinic (`partner_id`), a quantity (`pieces`), and a unit price (`price_per_piece`). Today, invoices must be created manually in Odoo Invoicing without any link to work log data. This ticket builds the bridge: work logs drive invoice generation, and each invoice line traces back to its source work log.

The bridge uses the existing `res.partner` foreign key on `dental.work.log` — this was the rationale for choosing `res.partner` over a custom model at project inception (Decision #1 in DESIGN.md §5).

---

## Scope

### In scope

- `invoice_id` Many2one field on `dental.work.log` → `account.move`
- `dental.invoice.wizard` TransientModel — groups selected logs by partner, creates one draft invoice per partner
- Server action wired to the list view toolbar (Manager only)
- Search filters: "Számlázatlan" / "Számlázott"
- List view: invoice status column
- Generic "Fogászati munka" service product in module data (used as product on invoice lines)
- `account` added to `__manifest__.py` dependencies
- Access rules: invoice wizard restricted to `group_lab_manager`

### Out of scope

- Automatic periodic invoicing (scheduled action) — M5
- Invoice posting (confirming) — done manually in Odoo Invoicing after review
- Payment registration — handled natively in Odoo Invoicing after posting
- PDF invoice templates / custom report layout — M5
- Credit notes / cancellation flow — handled natively after invoice is posted
- Courier integration (M3 not yet built)

---

## Data Model Changes

### 3.2.4  `dental.work.log` — new fields

| Field | Odoo type | Notes |
|---|---|---|
| `invoice_id` | `Many2one('account.move')` | Nullable. Set when a wizard creates the invoice line containing this log. `ondelete='set null'` so deleting a draft invoice clears the link without deleting the log. |
| `invoice_state` | `Char`, computed, not stored | Returns `invoice_id.state` if set, else `''`. Used only for display in list view — not a stored field, not searchable. |

**Python sketch:**

```python
invoice_id = fields.Many2one(
    'account.move',
    string='Számla',
    readonly=True,
    ondelete='set null',
    copy=False,
    index=True,
)
invoice_state = fields.Char(
    string='Számla állapota',
    compute='_compute_invoice_state',
)

@api.depends('invoice_id', 'invoice_id.state')
def _compute_invoice_state(self):
    state_labels = {
        'draft': 'Piszkozat',
        'posted': 'Könyvelve',
        'cancel': 'Sztornózva',
    }
    for rec in self:
        if rec.invoice_id:
            rec.invoice_state = state_labels.get(rec.invoice_id.state, rec.invoice_id.state)
        else:
            rec.invoice_state = 'Nincs számla'
```

### 3.2.5  `dental.invoice.wizard` (new TransientModel)

Handles the multi-record invoice generation flow.

| Field | Odoo type | Notes |
|---|---|---|
| `work_log_ids` | `Many2many('dental.work.log')` | Pre-populated from `active_ids` in context |
| `invoice_date` | `Date` | Defaults to today. Applied to all generated invoices. |
| `partner_summary_ids` | `One2many('dental.invoice.wizard.line', ...)` | Read-only summary — one row per partner found in `work_log_ids` |

**`dental.invoice.wizard.line`** (TransientModel, child):

| Field | Type | Notes |
|---|---|---|
| `wizard_id` | `Many2one('dental.invoice.wizard')` | Parent |
| `partner_id` | `Many2one('res.partner')` | Clinic |
| `log_count` | `Integer` | Number of work logs for this partner |
| `total_amount` | `Float` | `SUM(total_revenue)` preview |

**`create_invoices()` method logic:**

```python
def create_invoices(self):
    uninvoiced = self.work_log_ids.filtered(lambda r: not r.invoice_id)
    if not uninvoiced:
        raise UserError('A kijelölt munkalapok mind már számlázva vannak.')

    product = self.env.ref('dentari_lab.product_dental_work')
    invoices_by_partner = {}

    for log in uninvoiced:
        partner = log.partner_id
        if partner not in invoices_by_partner:
            invoices_by_partner[partner] = []
        invoices_by_partner[partner].append(log)

    created = self.env['account.move']
    for partner, logs in invoices_by_partner.items():
        lines = []
        for log in logs:
            label_parts = [log.work_type and dict(WORK_TYPES).get(log.work_type, log.work_type) or 'Egyéb munka']
            if log.patient_name:
                label_parts.append(log.patient_name)
            label_parts.append(log.date.strftime('%Y-%m-%d'))
            lines.append((0, 0, {
                'product_id': product.id,
                'name': ' – '.join(label_parts),
                'quantity': log.pieces,
                'price_unit': log.price_per_piece,
            }))
        move = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': partner.id,
            'invoice_date': self.invoice_date,
            'invoice_line_ids': lines,
        })
        logs.write({'invoice_id': move.id})
        created |= move

    return {
        'type': 'ir.actions.act_window',
        'res_model': 'account.move',
        'view_mode': 'list,form',
        'domain': [('id', 'in', created.ids)],
        'name': 'Létrehozott számlák',
    }
```

---

## Module Data

### Generic dental work product (`data/invoice_data.xml`)

A `product.template` record is created at module install time and used as the product on all generated invoice lines. Using a product lets Odoo resolve the correct income account automatically from the product category, without manual setup.

```xml
<record id="product_dental_work" model="product.template">
    <field name="name">Fogászati munka</field>
    <field name="type">service</field>
    <field name="list_price">0.0</field>
    <field name="sale_ok" eval="False"/>
    <field name="purchase_ok" eval="False"/>
</record>
```

> `invoice_policy` is a `sale` module field and must **not** be set here — the `sale` module is not a dependency.

---

## View Changes

### `views/dental_work_log_views.xml`

**List view** — add two optional columns after `total_revenue`:

```xml
<field name="invoice_id" string="Számla" optional="show" readonly="1"/>
<field name="invoice_state" string="Számla állapota" optional="show" readonly="1"/>
```

**Search view** — add two filters:

```xml
<filter name="uninvoiced" string="Számlázatlan"
        domain="[('invoice_id', '=', False)]"/>
<filter name="invoiced" string="Számlázott"
        domain="[('invoice_id', '!=', False)]"/>
```

Add a separator between date filters and the new invoice filters.

### `views/wizard_invoice_views.xml` (new file)

Form view for the wizard dialog:

```xml
<record id="view_dental_invoice_wizard_form" model="ir.ui.view">
    <field name="name">dental.invoice.wizard.form</field>
    <field name="model">dental.invoice.wizard</field>
    <field name="arch" type="xml">
        <form string="Számlák generálása">
            <group>
                <field name="invoice_date" required="1"/>
            </group>
            <group string="Érintett megrendelők">
                <field name="partner_summary_ids" nolabel="1" readonly="1">
                    <list>
                        <field name="partner_id"/>
                        <field name="log_count" string="Munkalapok"/>
                        <field name="total_amount" string="Összeg (Ft)"
                               widget="monetary" options="{'currency_field': False}"/>
                    </list>
                </field>
            </group>
            <footer>
                <button name="create_invoices" type="object"
                        string="Számlák létrehozása" class="btn-primary"/>
                <button string="Mégse" class="btn-secondary" special="cancel"/>
            </footer>
        </form>
    </field>
</record>
```

### Server action (list toolbar button)

```xml
<record id="action_dental_generate_invoices" model="ir.actions.server">
    <field name="name">Számlák generálása</field>
    <field name="model_id" ref="model_dental_work_log"/>
    <field name="binding_model_id" ref="model_dental_work_log"/>
    <field name="binding_view_types">list</field>
    <field name="groups_id" eval="[(4, ref('dentari_lab.group_lab_manager'))]"/>
    <field name="state">code</field>
    <field name="code">
action = env['dental.invoice.wizard'].with_context(active_ids=records.ids).create({}).action_open_wizard()
    </field>
</record>
```

> `binding_model_id` makes this action appear in the "Action" dropdown in the list view toolbar. `binding_view_types='list'` restricts it to list context only (multi-select required).

---

## `__manifest__.py` Changes

```python
'depends': ['base', 'mail', 'account'],
'data': [
    ...
    'data/invoice_data.xml',
    'views/wizard_invoice_views.xml',
    ...
    'security/ir.model.access.csv',   # add wizard model entries
],
```

---

## Security

### `security/ir.model.access.csv` — new rows

```
access_invoice_wizard_manager,invoice wizard manager,model_dental_invoice_wizard,dentari_lab.group_lab_manager,1,1,1,1
access_invoice_wizard_line_manager,invoice wizard line manager,model_dental_invoice_wizard_line,dentari_lab.group_lab_manager,1,1,1,1
```

Technicians have no access to the wizard model — they cannot see the "Számlák generálása" action (it has `groups_id` set) and cannot access the TransientModel directly.

---

## Acceptance Criteria

### AC-1 Module dependency

- [ ] `account` is listed in `dentari_lab/__manifest__.py` `depends`.
- [ ] Module upgrades cleanly (`-u dentari_lab`) on an instance with the `account` module installed.

### AC-2 `invoice_id` field on `dental.work.log`

- [ ] `invoice_id` Many2one field exists on `dental.work.log` pointing to `account.move`.
- [ ] Field is `readonly=True` in all views (set only by wizard).
- [ ] `ondelete='set null'`: deleting a draft invoice sets `invoice_id = False` on linked logs (does not delete the logs).
- [ ] Field is indexed (`index=True`).

### AC-3 Wizard — launch

- [ ] "Számlák generálása" appears in the list view Action menu for Lab Managers only.
- [ ] Action is not visible to Lab Technicians.
- [ ] Selecting one or more work logs and clicking the action opens the `dental.invoice.wizard` dialog.
- [ ] The wizard pre-populates `work_log_ids` from `active_ids` in context.
- [ ] The `partner_summary_ids` section shows one row per distinct `partner_id` found in the selected logs, with correct counts and summed totals.

### AC-4 Wizard — invoice creation

- [ ] Clicking "Számlák létrehozása" creates one `account.move` (`move_type='out_invoice'`) per distinct `partner_id` in the selection.
- [ ] Each work log in the selection produces one `account.move.line` on the corresponding partner's invoice.
- [ ] Invoice line description format: `{work_type_label} – {patient_name} – {date}` (patient_name omitted if blank, date always present).
- [ ] Invoice line `quantity` = `log.pieces`, `price_unit` = `log.price_per_piece`.
- [ ] Created invoices are in **draft** state (not auto-posted).
- [ ] `invoice_date` on all created invoices equals the date entered in the wizard.
- [ ] After creation, each processed log's `invoice_id` is set to the created `account.move`.

### AC-5 Wizard — already-invoiced records

- [ ] If all selected logs already have `invoice_id` set, the wizard raises `UserError('A kijelölt munkalapok mind már számlázva vannak.')` and creates no invoices.
- [ ] If the selection contains a mix of invoiced and uninvoiced logs, only the uninvoiced ones are processed; invoiced ones are silently skipped.

### AC-6 Wizard — redirect after creation

- [ ] After successful creation the wizard closes and the user is redirected to a list view of the newly created `account.move` records filtered to the just-created IDs.

### AC-7 List view — invoice columns

- [ ] `invoice_id` column appears in the list view as an optional column (default shown), displaying the invoice reference number (e.g. `INV/2026/00001`) as a clickable link.
- [ ] `invoice_state` column appears as an optional column (default shown), displaying the Hungarian label (Piszkozat / Könyvelve / Sztornózva / Nincs számla).

### AC-8 Search view — invoice filters

- [ ] "Számlázatlan" filter: `[('invoice_id', '=', False)]` — returns all work logs with no linked invoice.
- [ ] "Számlázott" filter: `[('invoice_id', '!=', False)]` — returns all work logs with a linked invoice.
- [ ] Filters appear in the search bar dropdown under a "Számlázás" separator.

### AC-9 Generic product

- [ ] `dentari_lab.product_dental_work` product record exists after module install.
- [ ] Product `type` = `service`.
- [ ] `env.ref('dentari_lab.product_dental_work')` resolves without error.

### AC-10 Odoo 18 compatibility

- [ ] No `attrs=` XML attributes in any new or modified XML.
- [ ] No Enterprise-only view types used.
- [ ] All new view records added to the appropriate XML files listed in `__manifest__.py`.
- [ ] Module installs cleanly on a fresh database with the Invoicing (`account`) module installed (CE — no `sale`, no `purchase`, no full accounting required).

---

## Files to Create or Modify

| File | Change |
|---|---|
| `addons/dentari_lab/__manifest__.py` | Add `'account'` to `depends`; add new data/view files to `data` list |
| `addons/dentari_lab/models/__init__.py` | Import `dental_invoice_wizard` |
| `addons/dentari_lab/models/dental_work_log.py` | Add `invoice_id`, `invoice_state` fields |
| `addons/dentari_lab/models/dental_invoice_wizard.py` | New file — `dental.invoice.wizard` and `dental.invoice.wizard.line` TransientModels |
| `addons/dentari_lab/views/dental_work_log_views.xml` | Add `invoice_id`, `invoice_state` list columns; add invoice search filters |
| `addons/dentari_lab/views/wizard_invoice_views.xml` | New file — wizard form view + server action |
| `addons/dentari_lab/data/invoice_data.xml` | New file — `product_dental_work` record |
| `addons/dentari_lab/security/ir.model.access.csv` | Add rows for wizard and wizard line models |

---

## Definition of Done

- [ ] All acceptance criteria above are checked.
- [ ] Lab Manager can select work logs in the list view, open the wizard, review the partner summary, and generate draft invoices.
- [ ] Generated invoices appear in Odoo Invoicing → Customer Invoices in Draft state.
- [ ] Each invoice line shows the correct description, quantity, and unit price.
- [ ] Work logs display the linked invoice reference after generation.
- [ ] Attempting to re-invoice already-invoiced logs raises the correct error.
- [ ] "Számlázatlan" filter returns only un-billed logs.
- [ ] Lab Technician cannot see or use the "Számlák generálása" action.
- [ ] Module upgrades cleanly with `-u dentari_lab` without errors.
- [ ] Smoke test (`tests/smoke_dev.py`) still passes after upgrade.
- [ ] Code reviewed and merged to `develop` branch.
