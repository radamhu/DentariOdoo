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

Three bugs found after TICKET-006 delivery:

1. **"Összesítő nyomtatása" raised `UserError: Nincs munkalap a kiválasztott időszakban.`** even when the partner preview correctly showed data.
2. **Clicking a partner row opened an empty detail popup** — `log_ids` was missing.
3. **`log_ids` only appeared in the popup after the PDF had been generated at least once** — before the first print, the detail popup was always empty.

All three stem from the same root cause.

---

## Root Cause

**Odoo does not send readonly field values back to the server when a button is clicked**, and **onchange-produced One2many records are virtual (client-only) until explicitly written to the database.**

### Detailed trace

```
Wizard opens (current month = June 2026, no data)
  → default_get() → _search_logs() returns []
  → create() stores wizard with preview_ids = []   ← DB is EMPTY

User changes period to May 2026
  → _onchange_period() fires
  → Client UI shows partner rows (virtual, not persisted to DB)
  → DB wizard record still has preview_ids = []

User clicks on a partner row
  → Popup opens for the virtual line record
  → log_ids not in client cache (not in the One2many <list> view columns)
  → Popup shows empty log list  ✗

User clicks "Összesítő nyomtatása"
  → Client sends write() — preview_ids is readonly="1" → NOT included
  → Server-side self.preview_ids is still []
  → action_print_summary() checks `if not self.preview_ids` → UserError  ✗

  — After the first print (action_print_summary ran write()) —

User clicks on a partner row
  → Line records now exist in DB with log_ids populated
  → Popup fetches from DB → works  ✓  (but only because print ran first)
```

The secondary cause for bug 2/3: `log_ids` was a **stored Many2many** with a relation table. Its data was only written when `action_print_summary` called `self.write(...)`. The detail popup depended on that DB state, so it was empty until after the first print.

---

## Changes

### `dentari_lab/models/dental_monthly_wizard.py` — two changes

#### 1. `action_print_summary` — always re-query and rebuild `preview_ids`

Before:
```python
def action_print_summary(self):
    self.ensure_one()
    if not self.preview_ids:
        raise UserError(_('Nincs munkalap a kiválasztott időszakban.'))
    return self.env.ref('dentari_lab.action_report_monthly_summary').report_action(self)
```

After:
```python
def action_print_summary(self):
    self.ensure_one()
    partner_ids = self.partner_ids.ids if self.partner_ids else []
    logs = self._search_logs(self.period_year, int(self.period_month), partner_ids)
    if not logs:
        raise UserError(_('Nincs munkalap a kiválasztott időszakban.'))
    # preview_ids is readonly in the view so it is not sent back on button click;
    # always rebuild from the current period to ensure the report template has correct data.
    self.write({'preview_ids': [(5, 0, 0)] + self._build_preview_vals(logs)})
    return self.env.ref('dentari_lab.action_report_monthly_summary').report_action(self)
```

Validity check uses `_search_logs()` (queries by `period_year`/`period_month`, which are not readonly and are correctly in the DB). `(5, 0, 0)` clears stale lines before inserting fresh ones.

#### 2. `log_ids` → computed field; `_build_preview_vals` simplified

`log_ids` was a stored Many2many backed by a relation table (`dental_monthly_wizard_line_log_rel`). It was only populated when `action_print_summary` wrote to the DB, making the detail popup empty before the first print.

**Now computed:**

```python
log_ids = fields.Many2many(
    'dental.work.log',
    string='Munkalapok',
    compute='_compute_log_ids',
)

@api.depends('wizard_id.period_year', 'wizard_id.period_month', 'partner_id')
def _compute_log_ids(self):
    for line in self:
        wizard = line.wizard_id
        if not wizard.period_month or not line.partner_id:
            line.log_ids = self.env['dental.work.log']
            continue
        date_from = date(wizard.period_year, int(wizard.period_month), 1)
        date_to = date_from + relativedelta(months=1) - timedelta(days=1)
        line.log_ids = self.env['dental.work.log'].search([
            ('date', '>=', date_from),
            ('date', '<=', date_to),
            ('partner_id', '=', line.partner_id.id),
        ], order='date, id')
```

`_build_preview_vals` no longer tracks `log_ids` at all — it only aggregates `log_count` and `total_amount`. The report template's `line.log_ids` call triggers `_compute_log_ids` at render time.

### `dentari_lab/views/wizard_monthly_views.xml`

Added `view_dental_monthly_wizard_line_form` — explicit form view for `dental.monthly.wizard.line`. Replaces Odoo's auto-generated form with a layout that shows `log_ids` as a proper readonly list (date, patient, work type, pieces, unit price, total).

---

## Files Changed

| File | Change |
|---|---|
| `dentari_lab/models/dental_monthly_wizard.py` | `action_print_summary` rewritten; `log_ids` made computed; `_build_preview_vals` simplified |
| `dentari_lab/views/wizard_monthly_views.xml` | Added form view for `dental.monthly.wizard.line` with `log_ids` list |

---

## Acceptance Criteria

- [x] "Összesítő nyomtatása" generates the PDF correctly after a period change.
- [x] Clicking a partner row shows the correct work log lines in the popup **without printing first**.
- [x] If no logs exist for the selected period, `UserError` is raised with the correct message.
- [x] Module upgrades cleanly with `-u dentari_lab`.

---

## Design Notes

### Why not remove `readonly="1"` from `preview_ids`?

Making `preview_ids` editable would include it in the `write()` payload on button click, removing the stale-data problem. But it would make the list visually editable (accidental row deletion), and the `_onchange_period` flow already handles population. Keeping it readonly and rebuilding server-side on print is safer.

### Why make `log_ids` computed instead of stored?

A stored Many2many is only written to the DB when `write()` is called explicitly (here: from `action_print_summary`). The detail popup needed DB state that didn't exist until after the first print. A computed field has no DB state — it queries `dental.work.log` live whenever read, so the popup always has correct data regardless of whether the user has printed yet. The `dental_monthly_wizard_line_log_rel` table is no longer used (can be dropped from the DB, causes no harm if left).
