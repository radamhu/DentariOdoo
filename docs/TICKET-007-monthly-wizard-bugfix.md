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

Two bugs found after TICKET-006 delivery that rendered the Monthly Statement Wizard ("Havi Összesítő") non-functional:

1. **"Összesítő nyomtatása" raised `UserError: Nincs munkalap a kiválasztott időszakban.`** even when the partner preview correctly showed data.
2. **Clicking a partner row opened an empty detail popup** — the associated work log lines (`log_ids`) were missing.

---

## Root Cause

Both bugs share the same root cause: **Odoo does not send readonly field values back to the server when a button is clicked**.

### Detailed trace

```
Wizard opens (current month = June 2026, no data yet)
  → default_get() called
  → _search_logs() returns empty list
  → create() stores wizard with preview_ids = []   ← DB has EMPTY preview_ids

User changes period to May 2026
  → _onchange_period() fires
  → Client UI updated with partner rows (virtual, not persisted)
  → DB wizard record still has preview_ids = []

User clicks "Összesítő nyomtatása"
  → Client sends write() to server
  → preview_ids is readonly="1" in the form → NOT included in write payload
  → Server-side self.preview_ids is still []
  → action_print_summary() checks `if not self.preview_ids` → raises UserError  ✗
```

The same mechanism caused `log_ids` to be empty in the detail popup: the line records either did not exist in the DB (virtual onchange records) or had no `log_ids` because the current month had no data at wizard creation time.

Additionally, no explicit form view existed for `dental.monthly.wizard.line`, so Odoo's auto-generated form did not display `log_ids` in a useful list layout.

---

## Changes

### `dentari_lab/models/dental_monthly_wizard.py`

**`action_print_summary` — always re-query and rebuild `preview_ids`**

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

Key decisions:
- Check period validity via `_search_logs()` (uses `period_year`/`period_month` which ARE written, as they are not readonly).
- Rebuild `preview_ids` — including `log_ids` Many2many — in the same request before passing `self` to the report action.
- `(5, 0, 0)` deletes any stale lines from the initial `create()` before inserting fresh ones.

### `dentari_lab/views/wizard_monthly_views.xml`

**New explicit form view for `dental.monthly.wizard.line`**

Added `view_dental_monthly_wizard_line_form` before the existing wizard form. The popup shows:
- Partner, log count, total amount (summary header)
- `log_ids` as a readonly list: date, patient name, work type, pieces, unit price, line total

This replaces Odoo's auto-generated form (which rendered `log_ids` without a useful list layout).

---

## Files Changed

| File | Change |
|---|---|
| `dentari_lab/models/dental_monthly_wizard.py` | `action_print_summary` rewritten — re-queries logs, rebuilds preview_ids |
| `dentari_lab/views/wizard_monthly_views.xml` | Added form view for `dental.monthly.wizard.line` with `log_ids` list |

---

## Acceptance Criteria

- [x] "Összesítő nyomtatása" generates the PDF correctly after a period change.
- [x] Clicking a partner row shows the correct work log detail lines in the popup.
- [x] If no logs exist for the selected period, `UserError` is raised with the correct message.
- [x] Module upgrades cleanly with `-u dentari_lab`.

---

## Design Notes

### Why not remove `readonly="1"` from `preview_ids`?

Making `preview_ids` editable would allow Odoo to include it in the `write()` payload on button click, which would fix the stale-data problem. However, it would also make the list visually editable (users could accidentally delete rows), and the `_build_preview_vals` / `_onchange_period` logic already handles population. Keeping it readonly and rebuilding server-side on print is the safer approach.

### Why not store `log_ids` on `dental.monthly.wizard.line` at all?

The report template (`report_monthly_summary.xml`) iterates `line.log_ids` directly. Removing `log_ids` from the line model would require passing the period parameters into the report template or using a custom rendering method — a larger refactor. The current fix rebuilds `log_ids` in the same transaction as the print action, which is sufficient.
