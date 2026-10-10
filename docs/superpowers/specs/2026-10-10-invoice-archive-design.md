---
title: Invoice Archive — szamlazz.hu Sync into Odoo
date: 2026-10-10
status: approved
jira: KAN-23
---

# Invoice Archive — szamlazz.hu Sync into Odoo

## Summary

New standalone Odoo 18 Community addon, `dentari_invoice_archive`, that automatically
pulls invoices issued through szamlazz.hu (NAV-hitelesített számlázó, currently the
only invoicing channel the sole trader uses) into Odoo as a legally-sufficient
nyilvántartás (record-keeping store). Hungarian law places no format requirement on
how a sole trader stores issued-invoice records — only that the core financial data
(szám, dátum, teljesítés, partner, nettó/ÁFA/bruttó, pénznem) is retained, for 8 years.

The addon has **no new invoice model** — every synced invoice is a standard
`account.move` (`move_type='out_invoice'`), kept in **draft** (never posted). This
mirrors the architecture principle already used twice in this codebase:
`dental_invoice_wizard` (`dentari_lab`) and `dental_quick_expense` both write to
`account.move` rather than a shadow model. The reason here is sharper than "consistency"
— it is the whole point of the ticket: Odoo-native invoicing for this business is a
planned *future* step, and when that switch happens, there must be nothing to migrate.
Archive-synced records and future Odoo-issued records live in the exact same table
from day one; only an `invoice_source` field distinguishes them.

## Requirements (from KAN-23 discussion)

- Pull invoices issued via szamlazz.hu automatically on a schedule (`ir.cron`), no
  manual export/import step for routine operation.
- Store, per invoice: szám (`szamlazz_invoice_number`), kiállítás dátum, teljesítés
  dátum, partner, nettó, ÁFA kulcs + összeg, bruttó, pénznem, PDF melléklet.
- Dedup: re-running the sync must never create a second record for an invoice
  already archived.
- Storage must be the same model future Odoo-issued invoices will use
  (`account.move`), distinguished only by an `invoice_source` marker — no separate
  migration step planned or needed later.
- Archive records stay `draft` — never posted, never touch real accounting entries,
  journals, or payables (this business's actual books of record remain whatever they
  are today; this addon is a read-oriented archive, not a parallel accounting system).
- List/filter view scoped to archived invoices, for partner/period/ÁFA overview.
- 8-year retention: nothing in this addon ever deletes an `account.move`,
  `account.move.line`, or `ir.attachment` record.
- Out of scope for v1: posting/accounting integration, NAV Online Számla
  data-reporting (szamlazz.hu already does this on its own), multi-currency
  conversion logic beyond storing the invoice's own currency, editing archived
  invoices from Odoo, two-way sync (Odoo never pushes anything back to szamlazz.hu).
- A Phase 0 spike precedes implementation to confirm the szamlazz.hu Agent XML API's
  actual query/listing behavior against the real account — see below. This is a
  harder unknown than past Phase-0 spikes in this repo: past spikes confirmed exact
  field requirements of a *known* API (Odoo's own). This one must first establish
  *whether a given operation is possible at all*, because szamlazz.hu's public Agent
  API is invoice-centric (create / query-by-number / PDF-by-number), not a generic
  "list invoices since date X" endpoint, and because all existing invoices were
  issued through szamlazz.hu's own web UI, not through the Agent API.

## Architecture

```
dentari_invoice_archive/
├── __init__.py
├── __manifest__.py
├── models/
│   ├── __init__.py
│   ├── account_move.py           # invoice_source, szamlazz_invoice_number fields
│   ├── szamlazz_client.py        # HTTP/XML plumbing: query, parse, partner match, PDF attach
│   └── szamlazz_sync.py          # dentari.szamlazz.sync model: cron target + manual run + run log
├── data/
│   └── ir_cron.xml               # scheduled sync job
├── views/
│   ├── szamlazz_sync_views.xml   # config/run-log form (manual "Szinkronizálás most" button)
│   ├── invoice_archive_views.xml # account.move list view, scoped to invoice_source='szamlazz_archive'
│   └── menus.xml                 # Számla archívum root menu
├── security/
│   └── ir.model.access.csv       # ACL for dentari.szamlazz.sync (reuses dentari_lab groups)
└── tests/
    ├── __init__.py
    └── test_szamlazz_sync.py     # mocked HTTP — no real network calls in CI
```

**Dependencies:** `account`, `dentari_lab` (for `group_lab_manager` — this is
financial/admin data, scoped to the owner/manager role only, no new group
hierarchy). Explicitly avoided: `hr`, `hr_expense`, `purchase`, `stock`, `l10n_hu`
specific accounting flows — this addon never posts anything.

**Why `dentari.szamlazz.sync` as a real (non-transient) model, when the invoice
data itself has no shadow model:** it holds *sync operation metadata* (last
synced number, last run timestamp/status/count), not invoice data — same
distinction `dental_quick_expense`'s `expense_category_id` compute makes between
"a convenience field on the real record" and "a shadow copy of the record." A
singleton-ish record (first one found/created on install) backs a simple config
form with a manual "Szinkronizálás most" button, for early testing and failure
recovery, in addition to the cron.

**Where the szamlazz.hu Agent key lives:** `ir.config_parameter`
(`dentari_invoice_archive.szamlazz_agent_key`), set via Settings → Technical →
System Parameters. Not a field on any normal-ACL model — avoids exposing an API
credential through a model any `group_lab_manager` user can read via the ORM/API,
and matches how this repo already handles instance credentials (`.env.*`, never
committed, loaded by deploy tooling rather than stored as application data).

## Data Model

No new persisted invoice model. Two standard models carry the data, plus one new
lightweight operational model:

| Model | Role |
|---|---|
| `account.move` (`move_type='out_invoice'`) | The invoice record itself (draft, never posted) |
| `account.move.line` | Invoice line(s) — net amount, tax |
| `ir.attachment` | The PDF pulled from szamlazz.hu, linked to the move |
| `dentari.szamlazz.sync` (new) | Sync run metadata + manual trigger — **not** invoice data |

### `account.move` extension (`models/account_move.py`)

```python
invoice_source = fields.Selection(
    [('odoo', 'Odoo'), ('szamlazz_archive', 'Számlázz.hu archívum')],
    string='Számla forrása', default='odoo', required=True,
)
szamlazz_invoice_number = fields.Char(
    string='Számlázz.hu sorszám', copy=False, index=True,
)
```

`szamlazz_invoice_number` has no `required=True` and no custom uniqueness
constraint beyond a plain `index=True` plus a dedup *search* before create in
sync code — Postgres `UNIQUE` would work too (NULLs don't collide), but a
plain indexed lookup is enough here and avoids a migration surprise if a
future Odoo-issued invoice ever legitimately needs the field blank, which is
the normal case (`invoice_source='odoo'` rows never set it).

Every future Odoo-issued invoice simply defaults to `invoice_source='odoo'` and
leaves `szamlazz_invoice_number` empty — no code anywhere needs to change when
that switch happens; the field already exists on every `account.move` row.

### `dentari.szamlazz.sync` (new, regular Model — not Transient)

```python
_name = 'dentari.szamlazz.sync'
_description = 'Számlázz.hu szinkronizálás'

last_synced_number = fields.Char(string='Utolsó szinkronizált sorszám')
last_run = fields.Datetime(string='Utolsó futás')
last_run_status = fields.Selection(
    [('ok', 'Sikeres'), ('error', 'Hiba'), ('never', 'Még nem futott')],
    default='never', string='Állapot',
)
last_run_message = fields.Text(string='Üzenet')
last_run_count = fields.Integer(string='Szinkronizált számlák száma (utolsó futás)')
```

One record expected to exist (created on module install via `data/`, or
lazily by `action_run_sync`/cron if missing) — not enforced as a hard
singleton, since nothing breaks if a second one is ever created by hand; the
cron and the manual button both just operate on `search([], limit=1)`.

## Phase 0 Spike — open questions

The spike (Task 1 of the implementation plan) must answer these against the
**real** szamlazz.hu account, using a real Agent API key, before Task 4's sync
logic is finalized:

1. **Does `action-szamla_agent_xml` (number/order query) return data for invoices
   created through szamlazz.hu's own web UI**, or only for invoices originally
   created via the Agent API? (All current invoices are web-UI-issued.) If it
   does not, the Agent API cannot discover existing invoices at all, and v1 of
   this addon must fall back to a one-time/periodic **CSV export import** from
   szamlazz.hu's own "Kimenő számlák" export instead of a pure API pull — this
   would change Task 4's design and must be decided before writing it.
2. **What is this account's actual invoice numbering pattern** (e.g.
   `E-2026-123`, sequential per year)? If query-by-number works (per #1), the
   sync needs a way to discover *which* numbers exist — either sequential
   probing from `last_synced_number` upward, or (if available) a real listing
   call. Confirm which mechanism the account actually supports.
3. **Exact request/response shape** for the query and PDF-fetch actions: field
   names, required headers/auth (API key placement), response encoding
   (the Agent API has historically returned `windows-1250`-encoded XML/headers
   for Hungarian text — confirm so partner names/addresses don't get mangled).
4. **Storno (cancelled) invoice representation**: does a cancelled invoice
   still answer a number query, and if so, how is "cancelled" signaled in the
   response? (Review Focus #4 below depends on this.)
5. **Rate limits / minimum polling interval** the API enforces or szamlazz.hu's
   terms require, to set the `ir.cron` interval safely.

Findings get written to a committed `docs/invoice-archive-spike-findings.md`.
No later task's code guesses at these values — Task 4 is written against
whatever this file says, which may mean Task 4's actual sync mechanism differs
from the "most likely" shape assumed in this document's examples.

## Review Focus (failure modes the spec implies)

1. **Re-running the sync after a partial failure** must not create a second
   `account.move` for an invoice already archived — dedup on
   `szamlazz_invoice_number` before create, not just "trust the cursor."
2. **szamlazz.hu API error (bad key, timeout, rate limit, HTTP 5xx)** must be
   caught, logged to `last_run_status='error'` / `last_run_message`, and must
   **not** raise out of the cron method — an uncaught exception in one `ir.cron`
   job's method does not disable other scheduled jobs in Odoo, but it does spam
   the server log on every run and leaves no readable status for a human
   checking the sync's health, which is the whole point of `last_run_*`.
3. **A customer on the invoice with no matching `res.partner`** (new customer,
   or an existing one whose name/tax-number doesn't exactly match) must result
   in a newly created `res.partner`, not a crash and not a silent merge into an
   unrelated existing partner with a similar name.
4. **A storno/cancelled invoice** must not sit in the archive looking like a
   normal valid issued invoice — needs a visible cancelled marker (exact
   representation depends on spike finding #4), so the ÁFA/revenue overview
   view doesn't silently overcount.
5. **PDF download fails for an otherwise-successfully-parsed invoice** (network
   blip, szamlazz.hu transient error) must not lose the whole invoice for that
   run — the `account.move` with its financial data should still be created,
   with the attachment attempt retried on a later run rather than blocking
   archival of the legally-required financial fields.

## Phase 0 Spike — Resolved (2026-10-10)

Run live against real invoice `AE-2026-37`. Full results:
[docs/invoice-archive-spike-findings.md](/Users/ferko/development/DentariOdoo/docs/invoice-archive-spike-findings.md).
Headline: Q1 confirmed yes (number-query sees web-UI invoices, no CSV
fallback needed); the guessed XML schema above (Q3) was wrong in several
ways corrected in the findings doc and in the plan's Task 3/4 code — notably
seller/buyer were reversed, amounts live under `osszegek/totalossz` not a
flat `vegosszeg`, the PDF arrives inline in the same XML body rather than a
response header, and this account's invoices are VAT-exempt (AAM) by
default rather than carrying a normal percentage rate. Q4 (storno
representation) remains **unconfirmed** — no cancelled invoice was
available to test against.
