# Dental Quick Expense — Phase 0 Spike Findings

Date: 2026-09-02. Ran against `dentari-dev-8780` (`https://dentari-dev-8780.apps.oec.sh`,
Odoo server version `18.0-20260817`) via `scripts/spike_quick_expense.py` (throwaway,
deleted after Task 1, as intended).

1. **Minimal fields for a valid Draft Vendor Bill:** `move_type='in_invoice'`,
   `partner_id`, `invoice_date`, and one `invoice_line_ids` tuple
   (`account_id`, `name`, `quantity`, `price_unit`, `tax_ids`) — **confirmed**.
   `account.move.create()` with exactly this field set returned a new move
   (`id=4`) in `state='draft'` with no additional fields required and no
   validation errors. No `journal_id`, no `partner_id.property_account_payable_id`
   override, and no explicit sequence/name were needed.

2. **`journal_id` / payable account defaulting:** Odoo auto-picked journal
   **id 9, "Vendor Bills"** — the standard, single purchase journal on this
   database (not one scoped to a partner or product). Because it's the one
   shared journal every vendor bill on this instance lands in regardless of
   category, filtering the addon's expense list by journal would show *all*
   vendor bills, not just this addon's. This confirms
   `expense_category_id != False` (i.e. filtering on the category compute
   field derived from the line's `account_id`, per the design doc) is the
   correct and *sufficient* list-domain filter — it doesn't depend on, and
   isn't undermined by, journal identity. No additional journal-based filter
   is needed.

3. **Expense account codes already in use.** *Superseded by `data/expense_categories.xml` —
   the actual category names used are the ticket's own list (Fogtechnikai anyag,
   Futár/szállítás, …), not the placeholder names below, which were used only to test
   code-collision during the spike.*

   40 `account.account` records
   with `account_type='expense'` were returned, all in the Hungarian
   class-8 "other expenses" range **851000–876200** (e.g. `851000 Sales and
   distribution costs`, `852000 Administrative expenses`, …
   `876200 Foreign exchange losses on assets and liabilities denominated in
   foreign currencies`). A direct check also confirmed no `account.account`
   record of *any* type currently uses codes `899001`–`899011`, and the
   highest code on the instance is `999999`. 11 codes chosen for
   `data/expense_categories.xml` (clear of the 851000–876200 block and of
   every other account on the instance):
   - `899001` — Anyagköltség (fogászati anyagok) / Dental materials
   - `899002` — Laborköltség / Lab costs
   - `899003` — Bérleti díj / Rent
   - `899004` — Közüzemi díjak (víz, gáz, villany) / Utilities
   - `899005` — Telefon, internet / Phone & internet
   - `899006` — Iroda- és adminisztrációs költség / Office & admin
   - `899007` — Szállítási költség / Shipping & delivery
   - `899008` — Javítás, karbantartás / Repair & maintenance
   - `899009` — Szakmai díjak (könyvelő, tanácsadó) / Professional fees
   - `899010` — Biztosítás / Insurance
   - `899011` — Egyéb működési költség / Other operating expense

4. **Tax computation on a single-line bill:** with one purchase tax id
   applied via `tax_ids=[(6,0,[tax_id])]` on the line (`price_unit=1000`),
   the created move showed `amount_untaxed=1000.0`, `amount_tax=270.0`,
   `amount_total=1270.0` (a 27% purchase tax, consistent with Hungarian VAT)
   — confirms the `(6,0,[tax_id])` command computes the total correctly with
   no extra fields needed.

5. **Attachment relink pattern:** confirmed. Creating an `ir.attachment`
   against `res_model='dental.quick.expense', res_id=0` and then calling
   `ir.attachment.write({'res_model': 'account.move', 'res_id': <move_id>})`
   succeeded with no error; a follow-up `read` showed
   `{'res_model': 'account.move', 'res_id': 4}`. Additionally observed: once
   the linked `account.move` was unlinked during cleanup, the relinked
   attachment was cascade-deleted by Odoo (the attachment's own `unlink`
   call then correctly raised "Record does not exist or has been deleted");
   a follow-up `search` confirmed both the move and the attachment were
   gone, so cleanup left no orphan records. This confirms the relink pattern
   is safe and that attachment lifecycle correctly follows the move's.

## Note on the spike script's own argument-shape bug

The spike script's `call()` helper (matching the pattern already used in
`tests/test_monthly_email.py`) builds the XML-RPC `execute_kw` args list via
`list(args)` from `call()`'s own `*args`. The task brief's script text wraps
domains/ids/options in an *extra* list layer on top of that (e.g.
`call(model, "search", [[(field, op, val)]])` and
`call(model, "read", [ids], {"fields": [...]})` as a positional dict), which
double-wraps the domain and passes options as a stray positional argument
instead of a keyword argument. Run as originally transcribed, every
domain-based call (even `search([])`) failed identically with:

```
xmlrpc.client.Fault: <Fault 1: '...
  File ".../odoo/models.py", line 5814, in _search
    if expression.is_false(self, domain):
  File ".../odoo/osv/expression.py", line 261, in is_false
    elif token[1] == 'in' and not (isinstance(token[2], Query) or token[2]):
IndexError: tuple index out of range
'>
```

This reproduced identically against the pre-existing, already-committed
`tests/test_monthly_email.py` (same fault, same line), confirming it's a
scripting-convention bug — not a dev-instance issue. The script was corrected
locally (domains/ids passed unwrapped, options passed as real `**kwargs` to
`call()`) to obtain the results above; the dev instance itself behaved
correctly throughout. Later tasks writing addon Python code are unaffected —
this only concerns the shape of ad hoc XML-RPC test/spike scripts using this
`call()` helper convention.
