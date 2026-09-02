---
title: Dental Quick Expense — Lightweight Expense Recording Addon
date: 2026-09-02
status: approved
jira: KAN-27
---

# Dental Quick Expense

## Summary

New standalone Odoo 18 Community addon, `dental_quick_expense`, giving a dental
technician a very simple UI to record a business expense in a few fields. The
addon has **no expense model of its own** — every saved expense is a standard
`account.move` (draft Vendor Bill). Odoo Accounting remains the sole source of
truth; the addon is a thin, removable UX layer over it. This mirrors the
architecture principle already used by the `dental_invoice_wizard` in
`dentari_lab` (wizard → `account.move`, no shadow model).

## Requirements (from KAN-27)

- Menu **Kiadások** with sub-items **Kiadások** (list) and **Új kiadás** (wizard)
- New-expense wizard fields: Dátum, Szállító, Kategória, Leírás, Nettó összeg,
  ÁFA, Bizonylatszám, Bizonylat (attachment) — minimum required fields
- Save creates a **draft** `account.move` (`move_type='in_invoice'`) with one
  `account.move.line`, correct expense account, correct tax, and the uploaded
  attachment linked to the move — no auto-posting
- Expense categories are standard `account.account` (expense type) records,
  not a custom model; wizard shows only the relevant ones
- Kiadások list reads directly off `account.move` — no second data store
- Out of scope for v1 (ticket §13): HR Expense, employees, approval workflow,
  budgets, PO/Inventory/Project/MRP, timesheets, analytic accounting, OCR,
  dashboards, custom payment/accounting logic
- A short Odoo 18 Community spike precedes implementation (ticket §17) to
  confirm minimal fields for a valid Draft Vendor Bill, journal/payable
  defaulting, expense-account domain filtering, tax handling, and safe
  attachment linking

## Architecture

```
dental_quick_expense/
├── __init__.py
├── __manifest__.py
├── data/
│   └── expense_categories.xml     # 11 seeded expense account.account records
├── models/
│   ├── __init__.py
│   └── account_move.py            # display-only computed fields (see below)
├── wizard/
│   ├── __init__.py
│   └── quick_expense.py           # dental.quick.expense TransientModel
├── views/
│   ├── quick_expense_views.xml    # wizard form
│   ├── expense_list_views.xml     # account.move list, relabeled/filtered
│   └── menus.xml                  # Kiadások > Kiadások / Új kiadás
├── security/
│   └── ir.model.access.csv
└── tests/
    ├── __init__.py
    └── test_quick_expense.py
```

**Dependencies:** `account`, `dentari_lab` (for the existing
`group_lab_technician` / `group_lab_manager` security groups — avoids
defining a parallel group hierarchy for what is effectively the same one or
two users). Explicitly avoided per ticket §3: `hr`, `hr_expense`, `purchase`,
`stock`, `project`, `mrp`.

**Why depend on `dentari_lab` and not stay fully standalone:** the ticket's
"avoid dependency" list is about accounting-adjacent Odoo apps (hr/purchase/
stock/etc.), not about this project's own security model. Reusing
`dentari_lab`'s groups avoids a second, redundant group hierarchy for the
same one or two people who already have Lab Technician/Manager roles.

## Data Model

No new persisted business model. Three standard models carry the data:

| Model | Role |
|---|---|
| `account.move` (`move_type='in_invoice'`) | The expense record itself (draft Vendor Bill) |
| `account.move.line` | The single expense line (category account, description, amount, tax) |
| `ir.attachment` | The uploaded bizonylat, linked to the move |

### `dental.quick.expense` (new, TransientModel)

Data-entry only; never a source of truth; deleting it causes no data loss
(ticket §16, Definition of Done).

```
_name = 'dental.quick.expense'
_description = 'Gyors kiadás rögzítése'

date                  Date          required, default=today
partner_id            Many2one(res.partner)   required
category_account_id   Many2one(account.account)  required
                       domain: account_type='expense' AND
                               id in <the 11 seeded xmlids>
description            Char          required
net_amount             Monetary      required
tax_id                 Many2one(account.tax)  required
ref                     Char          optional (bizonylatszám)
attachment_ids          Many2many(ir.attachment)  optional
```

Exact domain expression for `category_account_id` and the exact required
field set for `account.move`/`account.move.line` are confirmed by the Phase 0
spike (see below) rather than guessed here.

### `account.move` extension (`models/account_move.py`)

Display-only, additive, no monkey-patching of core behavior:

```
expense_category_id   Many2one(account.account, compute, store=True)
                       — pulled from the move's single invoice line
                       (present only when the move belongs to the
                       Kiadások journal/domain)
```

This exists solely so the Kiadások list can show a "Kategória" column without
the user opening each bill. `amount_untaxed` / `amount_tax` / `amount_total`
are already native `account.move` fields and need no extension.

If the addon is uninstalled, this field is dropped; the underlying
`account.move` records and their lines are untouched — no data loss.

### Categories (`data/expense_categories.xml`)

Creates 11 `account.account` records (type `expense`) at install, each with a
`dental_quick_expense.` xmlid, matching ticket §9:

Fogtechnikai anyag, Futár / szállítás, Üzemanyag, Gép / eszköz,
Gépkarbantartás, Telefon / internet, Rezsi, Könyvelés, Szoftver, Oktatás,
Egyéb.

Exact account codes/numbering follow whatever convention the live chart of
accounts already uses (confirmed in the spike) so these don't collide with
existing entries.

## UI

**Menu:** `Kiadások` (top-level)
- `Kiadások` → list view (see below)
- `Új kiadás` → opens the wizard (`target: 'new'`)

**Wizard form** (ticket §7 field order): Dátum, Szállító, Kategória, Leírás,
Nettó összeg, ÁFA, Bizonylatszám, Bizonylat, then **Mentés** / **Mégse**.
No Odoo accounting terminology (Journal Entry, Move, Payable Account,
Reconciliation) appears anywhere in the UI.

**Kiadások list:** a custom `ir.actions.act_window` on `account.move`,
domain-restricted to this addon's journal (confirmed in spike) and
`move_type='in_invoice'`, with a dedicated tree view showing: Dátum
(`invoice_date`), Szállító (`partner_id`), Leírás (line name), Kategória
(`expense_category_id`), Nettó (`amount_untaxed`), ÁFA (`amount_tax` or the
tax rate label), Státusz (`state`, relabeled Draft/Posted in Hungarian via
selection widget). No second data store — this is a filtered/relabeled view
directly over `account.move`.

## Data Flow (Save)

1. User opens **Új kiadás**, fills the wizard fields, optionally attaches a
   file, clicks **Mentés**.
2. `action_save()` on `dental.quick.expense`:
   a. Validates required fields (native Odoo required-field checks).
   b. Creates `account.move`: `move_type='in_invoice'`, `partner_id`,
      `invoice_date=date`, `ref=ref`, one `invoice_line_ids` entry
      (`account_id=category_account_id`, `name=description`,
      `price_unit=net_amount`, `tax_ids=[(6,0,[tax_id])]`).
   c. Journal/payable-account selection is left to Odoo's own `account.move`
      defaulting logic — the spike confirms the minimal field set that
      triggers correct defaulting rather than setting `journal_id` by hand.
   d. Does **not** call `.action_post()` — record stays `draft`, per ticket §8.
   e. Re-links any wizard `attachment_ids` to the new move
      (`res_model='account.move'`, `res_id=move.id`) rather than leaving them
      attached to the transient wizard record.
   f. Returns an `ir.actions.act_window` opening the Kiadások list, domain
      narrowed to the just-created move.

## Security

- `security/ir.model.access.csv`: grants `dental.quick.expense` create/read/
  write/unlink to `dentari_lab.group_lab_technician` and
  `dentari_lab.group_lab_manager`.
- No new `res.groups`, no `ir.rule` — this reuses `dentari_lab`'s existing
  security groups and Odoo's standard `account.move` access is already
  scoped by those groups' implied accounting permissions.
- Kiadások list access follows the same two groups via the menu's `groups`
  attribute (belt-and-braces alongside the model ACL).

## Error Handling

| Situation | Behavior |
|---|---|
| Missing required wizard field (date, partner, category, net amount, tax) | Native Odoo required-field validation blocks save |
| Category account missing/removed (partial upgrade) | `UserError` before `account.move` creation: *"A kiadás kategória nem található."* |
| Attachment upload fails | Native Odoo error; wizard stays open, no partial move created |
| Uninstall of the addon | `account.move`/`account.move.line`/`ir.attachment` records are untouched (standard Odoo Accounting data); only the wizard, list view, menu, and the computed `expense_category_id` field disappear — no accounting data loss (ticket §16) |

## Testing

Odoo test framework (`tests/test_quick_expense.py`), covering:

1. Saving the wizard with valid input creates exactly one `account.move` with
   `move_type='in_invoice'`, `state='draft'`, one invoice line with the
   correct account/amount/tax.
2. An uploaded attachment ends up linked to the created `account.move`
   (`res_model`/`res_id`), not left on the transient wizard.
3. `category_account_id`'s domain excludes non-expense accounts (e.g. a
   revenue or bank account is not selectable).
4. The Kiadások list domain shows only this addon's expense moves, not
   unrelated vendor bills already in the system (e.g. ones from
   `dentari_lab` or manually entered).
5. Missing a required field (e.g. no `net_amount`) blocks save with a
   validation error, and no `account.move` is created.

## Phase 0 Spike (precedes implementation, ticket §17)

Throwaway investigation against the real Odoo 18 Community instance (via
oec.sh) to answer, before writing the addon:

1. Minimal field set required to create a valid Draft Vendor Bill via
   `account.move.create()`.
2. How Odoo resolves `journal_id` / payable `account_id` when not set
   explicitly — confirm the addon can rely on defaults rather than hard-coding
   a journal.
3. A safe domain to filter `category_account_id` to only this addon's 11
   seeded expense accounts (avoiding collision with the existing chart of
   accounts).
4. Correct way to set `account.tax` on the invoice line so the tax total
   computes correctly on a single-line bill.
5. Safe pattern for relinking an `ir.attachment` created against the
   transient wizard onto the final `account.move` record.

Findings from this spike are a prerequisite input to Phase 1 (addon
implementation) in the implementation plan — the plan's first phase.

## Future Compatibility

Self-contained: if HR Expense, Purchase, or other Odoo apps are enabled
later, they bring their own workflows and don't interact with this addon.
Because every persisted record is a standard `account.move`, later migration
to a fuller expense system (should one ever be needed) starts from clean,
standard Accounting data rather than a bespoke schema.
