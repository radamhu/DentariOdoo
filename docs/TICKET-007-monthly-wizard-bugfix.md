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

Three bugs found after TICKET-006 delivery — all rooted in how Odoo handles readonly One2many fields and TransientModel state:

1. **"Összesítő nyomtatása" raised `UserError: Nincs munkalap a kiválasztott időszakban.`** even when the partner preview correctly showed data.
2. **Clicking a partner row opened an empty detail popup** — `log_ids` was missing entirely (no form view, stored Many2many never written).
3. **After making `log_ids` computed, the popup was still empty before the first print** — the compute depended on `wizard_id.period_*` which was stale in the DB (user had changed the period via onchange but the wizard DB record hadn't been updated yet).

---

## Root Cause — Three Layers

### Layer 1 — readonly One2many not written on button click

`preview_ids` is `readonly="1"` in the form view. Odoo excludes readonly fields from the `write()` payload sent to the server on button click. The server-side wizard record therefore retains whatever `preview_ids` state existed at initial `create()` time (which may be empty if the current month has no data).

```
Wizard opens (June 2026, no data)
  → default_get() → create() with preview_ids = []   ← DB EMPTY

User changes to May 2026
  → _onchange_period() → client UI updated (virtual records)
  → DB wizard: preview_ids still []

User clicks "Összesítő nyomtatása"
  → client write() — preview_ids excluded (readonly)
  → server: self.preview_ids = []  → UserError ✗
```

### Layer 2 — stored Many2many only written by action_print_summary

`log_ids` was a stored Many2many backed by `dental_monthly_wizard_line_log_rel`. Data was only inserted when `action_print_summary` called `self.write(...)`. Before the first print, the relation table had no rows — the detail popup was always empty.

### Layer 3 — computed field read wizard period from DB, not from current client state

After converting `log_ids` to a computed field with `@api.depends('wizard_id.period_year', 'wizard_id.period_month', 'partner_id')`, the popup was still empty before printing. Reason: when the popup opens for a virtual line (from onchange), the server computes `log_ids` by reading `line.wizard_id.period_year` from the **DB** — which still holds the original period (e.g. June 2026), not the changed one (e.g. May 2026). The write that updates `period_year`/`period_month` on the wizard only happens when the user clicks a button — not when changing fields in the form.

```
User changes period to May 2026 (onchange — DB wizard not updated)
  → virtual lines created with correct partner/count/amount

User clicks partner row
  → popup opens for virtual line
  → server runs _compute_log_ids
  → reads wizard_id.period_year from DB → June 2026 (stale!)
  → no logs found → log_ids empty ✗

User clicks "Összesítő nyomtatása"
  → client write() sends period_year=2026, period_month='5' to server
  → wizard DB record updated with correct period
  → action_print_summary rebuilds preview_ids in DB
  → popup now reads correct period from DB → works ✓
```

---

## Changes

### `dentari_lab/models/dental_monthly_wizard.py`

#### 1. `action_print_summary` — always re-query and rebuild `preview_ids`

Fixes Layer 1. Validity check via `_search_logs()` (uses non-readonly `period_year`/`period_month`). Rebuilds `preview_ids` unconditionally before passing `self` to the report action.

```python
def action_print_summary(self):
    self.ensure_one()
    partner_ids = self.partner_ids.ids if self.partner_ids else []
    logs = self._search_logs(self.period_year, int(self.period_month), partner_ids)
    if not logs:
        raise UserError(_('Nincs munkalap a kiválasztott időszakban.'))
    self.write({
        'preview_ids': [(5, 0, 0)] + self._build_preview_vals(
            logs, self.period_year, self.period_month
        ),
    })
    return self.env.ref('dentari_lab.action_report_monthly_summary').report_action(self)
```

#### 2. `log_ids` → computed field (fixes Layer 2)

Removed the stored Many2many. `log_ids` is now computed — queries `dental.work.log` live. The `dental_monthly_wizard_line_log_rel` relation table is no longer used.

#### 3. `period_year` / `period_month` copied onto the line (fixes Layer 3)

Added `period_year = fields.Integer()` and `period_month = fields.Char()` to `DentalMonthlyWizardLine`. `_build_preview_vals` now accepts and includes these values in each line's `(0, 0, vals)` command. `_compute_log_ids` depends on these line-level fields instead of `wizard_id.period_*`.

Because `_onchange_period` returns virtual line records with `period_year`/`period_month` embedded in the vals, those values are available in the client cache for the virtual records. When the popup opens and Odoo computes `log_ids`, it has the correct period from the line's own data — no DB read of the wizard required.

```python
# DentalMonthlyWizardLine
period_year = fields.Integer()
period_month = fields.Char()
log_ids = fields.Many2many('dental.work.log', compute='_compute_log_ids')

@api.depends('period_year', 'period_month', 'partner_id')
def _compute_log_ids(self):
    for line in self:
        if not line.period_month or not line.partner_id:
            line.log_ids = self.env['dental.work.log']
            continue
        date_from = date(line.period_year, int(line.period_month), 1)
        date_to = date_from + relativedelta(months=1) - timedelta(days=1)
        line.log_ids = self.env['dental.work.log'].search([
            ('date', '>=', date_from),
            ('date', '<=', date_to),
            ('partner_id', '=', line.partner_id.id),
        ], order='date, id')
```

```python
# DentalMonthlyWizard
@api.model
def _build_preview_vals(self, logs, year, month):
    summary = {}
    for log in logs:
        pid = log.partner_id.id
        if pid not in summary:
            summary[pid] = {
                'partner_id': pid,
                'log_count': 0,
                'total_amount': 0.0,
                'period_year': year,
                'period_month': str(month),
            }
        summary[pid]['log_count'] += 1
        summary[pid]['total_amount'] += log.total_revenue
    return [(0, 0, vals) for vals in summary.values()]
```

### `dentari_lab/views/wizard_monthly_views.xml`

Two changes:

1. Added explicit form view for `dental.monthly.wizard.line` with `log_ids` displayed as a readonly list (date, patient, work type, pieces, unit price, total). Replaces Odoo's auto-generated form.

2. Added `period_year` and `period_month` as `invisible="1"` fields in that form view. This ensures Odoo includes them in the onchange payload when the popup opens for a virtual line — making them available to `_compute_log_ids` on the server.

```xml
<form string="Munkalapok – részletek">
    <field name="period_year" invisible="1"/>
    <field name="period_month" invisible="1"/>
    ...
</form>
```

---

## Files Changed

| File | Change |
|---|---|
| `dentari_lab/models/dental_monthly_wizard.py` | `action_print_summary` rewritten; `log_ids` computed; `period_year`/`period_month` added to line; `_build_preview_vals` updated |
| `dentari_lab/views/wizard_monthly_views.xml` | Line form view added with `log_ids` list and invisible period fields |

---

## Acceptance Criteria

- [x] "Összesítő nyomtatása" generates the PDF correctly after a period change.
- [x] Clicking a partner row shows the correct work log lines in the popup **without printing first**.
- [x] Popup shows correct lines even after changing the period (before any print).
- [x] If no logs exist for the selected period, `UserError` is raised with the correct message.
- [x] Module upgrades cleanly with `-u dentari_lab`.

---

## Design Notes

### Why not remove `readonly="1"` from `preview_ids`?

Making `preview_ids` editable would include it in the `write()` payload, removing Layer 1. But it would make the list visually editable (accidental deletions) and the onchange flow already handles population. Rebuilding server-side on print is safer.

### Why copy period onto the line instead of reading from wizard?

Reading `wizard_id.period_year`/`wizard_id.period_month` works only after the wizard DB record has been updated (i.e. after the user clicks a button). For virtual onchange lines (before any button click), the wizard DB record still holds the original period. Copying `period_year`/`period_month` into each line's vals during `_build_preview_vals` makes the compute self-contained — it uses line-local data that is correctly populated in both virtual and persisted line records.

### Why `invisible="1"` instead of omitting the period fields from the popup view?

Odoo includes fields in the onchange payload only if they appear in the active form view (even as invisible). Without them in the view, `_compute_log_ids` would receive `period_year=0` and `period_month=False` for virtual lines, producing an empty result.
