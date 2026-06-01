# TICKET-007 — Monthly Wizard Bugfix: print failure & empty log detail

| Field | Value |
|---|---|
| **Type** | Bugfix |
| **Priority** | High |
| **Milestone** | M5 — Monthly Statement (post-delivery fix) |
| **Assignee** | — |
| **Reporter** | Dentari Development Team |
| **Created** | 2026-06-01 |
| **Updated** | 2026-06-01 |
| **Status** | Done |
| **Relates to** | [TICKET-006](./TICKET-006-monthly-statement-wizard.md) |

---

## Summary

Five bugs / root-cause layers found after TICKET-006 delivery, all related to how Odoo 18 handles readonly One2many fields, TransientModel state, and the OWL client's data-loading strategy for list popups.

1. **"Összesítő nyomtatása" raised `UserError: Nincs munkalap`.** — `preview_ids` readonly in view → not sent on button click → server sees empty list.
2. **Empty popup: `log_ids` was a stored Many2many** never written before the first print.
3. **Empty popup after making `log_ids` computed**: compute read `wizard_id.period_*` from DB — stale value because the user's period change lives only in client memory until a button is clicked.
4. **Empty popup after writing real DB records in onchange**: lines had real IDs, but the popup still showed empty rows.
5. **Root cause confirmed by XML-RPC**: OWL's readonly One2many popup does **not** do a fresh `web_read` — it reuses the list-load cache which only contains the visible columns (`partner_id`, `log_count`, `total_amount`). `log_ids` is never in that cache.

---

## Root Cause — Five Layers

### Layer 1 — readonly One2many not written on button click

`preview_ids` is `readonly="1"` in the form view. Odoo excludes readonly fields from the `write()` payload on button click. Server-side `preview_ids` retains the state from initial `create()` — empty if the current month has no data.

```
Wizard opens (June 2026, no data)
  → default_get() → create() with preview_ids = []

User changes to May 2026
  → _onchange_period() → client UI updated (virtual records)
  → DB wizard: preview_ids still []

User clicks print
  → client write() — preview_ids excluded (readonly)
  → server: self.preview_ids = []  → UserError ✗
```

### Layer 2 — stored Many2many only written by action_print_summary

`log_ids` was a stored Many2many. Relation table rows were only inserted by `action_print_summary`. Before the first print: relation table empty → popup empty.

### Layer 3 — computed field read wizard period from stale DB record

Converting `log_ids` to `compute='_compute_log_ids'` with `@api.depends('wizard_id.period_year', ...)` still failed. The wizard DB record holds the **original** period (June) until the user clicks a button. For virtual onchange lines, the server computes against the stale DB period → no logs found.

### Layer 4 — virtual One2many rows have no DB ID

Writing real DB records via `self._origin.write()` in `_onchange_period` and returning those real IDs to the client made the rows clickable. But the popup was still empty.

### Layer 5 — OWL readonly One2many popup reuses list-load cache (confirmed by XML-RPC)

Live XML-RPC diagnosis on the dev instance proved:

```
web_read(line_24, spec={log_ids: {date, patient_name, ...}})
  → returns full correct log_ids data  ✓

BUT: when the main wizard form loads preview_ids, OWL issues:
  web_read(wizard_id, spec={preview_ids: {partner_id, log_count, total_amount}})
  → log_ids is NOT in this spec (not a visible list column)
  → log_ids is never loaded into the OWL cache

Clicking a row → OWL opens popup reusing cached list data
  → log_ids missing from cache → popup shows empty rows  ✗
```

This is by design in Odoo 18: readonly One2many popups do not trigger an additional `web_read` — they display only what the list already loaded. Adding `log_ids` as a `column_invisible` column or triggering a fresh read from the popup are not supported without patching OWL.

---

## Changes

### `dentari_lab/models/dental_monthly_wizard.py`

#### Fix 1 — `action_print_summary`: always re-query and rebuild `preview_ids` (Layer 1)

```python
def action_print_summary(self):
    self.ensure_one()
    partner_ids = self.partner_ids.ids if self.partner_ids else []
    logs = self._search_logs(self.period_year, int(self.period_month), partner_ids)
    if not logs:
        raise UserError(_('Nincs munkalap a kiválasztott időszakban.'))
    self.write({
        'preview_ids': [(5, 0, 0)] + self._build_preview_vals(
            logs, self.period_year, self.period_month),
    })
    return self.env.ref('dentari_lab.action_report_monthly_summary').report_action(self)
```

#### Fix 2 — `log_ids` computed field (Layer 2)

Removed stored Many2many. `log_ids` now computed — queries `dental.work.log` live. Used by the report template; not depended upon for UI popup display.

#### Fix 3 — `period_year`/`period_month` stored on line (Layer 3)

Added `period_year = fields.Integer()` and `period_month = fields.Char()` to `DentalMonthlyWizardLine`. `_build_preview_vals` embeds these in each line's vals. `_compute_log_ids` depends on line-local fields, not `wizard_id.*`.

#### Fix 4 — `_onchange_period` writes real DB records via `self._origin` (Layer 4)

```python
@api.onchange('period_year', 'period_month', 'partner_ids')
def _onchange_period(self):
    if not self.period_month:
        if self._origin.id:
            self._origin.sudo().write({'preview_ids': [(5, 0, 0)]})
        self.preview_ids = [(5, 0, 0)]
        return
    partner_ids = self.partner_ids.ids if self.partner_ids else []
    logs = self._search_logs(self.period_year, int(self.period_month), partner_ids)
    new_vals = self._build_preview_vals(logs, self.period_year, self.period_month)
    if self._origin.id:
        self._origin.sudo().write({'preview_ids': [(5, 0, 0)] + new_vals})
        lines = self.env['dental.monthly.wizard.line'].search(
            [('wizard_id', '=', self._origin.id)], order='id',
        )
        self.preview_ids = lines
    else:
        self.preview_ids = new_vals
```

#### Fix 5 — `action_open_logs`: explicit button action (Layer 5 — definitive fix)

Row-click popup bypassed entirely. A dedicated server method opens a filtered `dental.work.log` list action using the line's own `period_year`/`period_month` fields (always correct in DB after Fix 4).

```python
def action_open_logs(self):
    self.ensure_one()
    date_from = date(self.period_year, int(self.period_month), 1)
    date_to = date_from + relativedelta(months=1) - timedelta(days=1)
    month_names = dict(MONTHS)
    period_label = f"{self.period_year}. {month_names.get(self.period_month, '').lower()}"
    return {
        'type': 'ir.actions.act_window',
        'name': f'{self.partner_id.name} — {period_label}',
        'res_model': 'dental.work.log',
        'view_mode': 'list,form',
        'domain': [
            ('partner_id', '=', self.partner_id.id),
            ('date', '>=', date_from),
            ('date', '<=', date_to),
        ],
        'target': 'new',
    }
```

### `dentari_lab/views/wizard_monthly_views.xml`

Three changes:

1. Added `view_dental_monthly_wizard_line_form` — explicit form view for `dental.monthly.wizard.line` with `log_ids` readonly list and invisible `period_year`/`period_month` fields (used by the report template path; does not fix the popup issue).
2. Added `period_year` and `period_month` as `invisible="1"` in the line popup form view.
3. Added **"Részletek" button** to the `preview_ids` list — calls `action_open_logs`, opens a `dental.work.log` dialog filtered to the partner + period.

```xml
<field name="preview_ids" nolabel="1" readonly="1">
    <list>
        <field name="partner_id"/>
        <field name="log_count" string="Munkalapok"/>
        <field name="total_amount" string="Összeg (Ft)"/>
        <button name="action_open_logs" type="object"
                icon="fa-list" title="Munkalapok megtekintése"
                string="Részletek"/>
    </list>
</field>
```

---

## Files Changed

| File | Change |
|---|---|
| `dentari_lab/models/dental_monthly_wizard.py` | `action_print_summary` rewritten; `log_ids` computed; `period_year`/`period_month` on line; `_onchange_period` writes via `_origin`; `action_open_logs` added |
| `dentari_lab/views/wizard_monthly_views.xml` | Line form view added; invisible period fields; "Részletek" button in list |

---

## Diagnosis Method

The definitive root cause (Layer 5) was identified via live **Odoo XML-RPC API** calls against the dev instance:

```python
# web_read proves the backend is correct
web_read(line_24, {log_ids: {date, patient_name, ...}})
→ [{'id': 13, 'date': '2026-05-05', 'patient_name': 'Molnár Tibor', ...}, ...]  ✓

# onchange proves the DB lines are real and period_year/period_month are stored
onchange(wizard_7, {period_month: '5'}, ['period_month'], ...)
→ preview_ids: [[4, 24, {...period_year: 2026, period_month: '5'...}], ...]  ✓

# DB state after onchange confirms _origin.write() works
read(wizard_7, ['preview_ids'])
→ [24, 25, 26, 27, 28, 29]  — real IDs  ✓
```

Since `web_read` returned correct data but the popup showed empty rows, the issue was in the OWL client's list-load caching, not the backend.

---

## Acceptance Criteria

- [x] "Összesítő nyomtatása" generates the PDF correctly after a period change.
- [x] "Részletek" button on each partner row opens the correct work log list.
- [x] Work logs are visible **without printing first**.
- [x] If no logs exist for the selected period, `UserError` is raised with the correct message.
- [x] Module upgrades cleanly with `-u dentari_lab`.

---

## Design Notes

### Why a "Részletek" button instead of fixing the row-click popup?

The OWL readonly One2many popup reuses the list-load cache and does not issue a fresh `web_read` for the line record. Since `log_ids` is not a visible list column, it is never in the cache. This is OWL framework behavior — it cannot be changed from the module's Python/XML layer without patching the OWL source. The button approach bypasses this entirely: it calls a server method on a real DB record and returns a new window action, which has no dependency on the OWL cache.

### Why write to DB in `_onchange_period` instead of relying on virtual records?

Odoo's popup mechanism for a One2many row looks up the record server-side by ID. Virtual records (negative IDs from onchange) don't exist in the DB — the lookup fails silently. `self._origin` in the onchange context is the actual DB wizard record (created by the initial `create()` call), so writing to it is safe and immediate within the same transaction.

### Why copy period onto the line instead of reading from wizard?

Reading `wizard_id.period_*` queries the DB wizard record, which holds the original period until a button is clicked. Line-local `period_year`/`period_month` fields (populated by `_build_preview_vals`) are always correct in both virtual and persisted line records.
