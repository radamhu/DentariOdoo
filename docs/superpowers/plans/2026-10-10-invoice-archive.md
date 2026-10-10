# Invoice Archive Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `dentari_invoice_archive`, an Odoo 18 Community addon that pulls
invoices issued via szamlazz.hu into Odoo automatically (`ir.cron`) as draft
`account.move` (`out_invoice`) records — a legally-sufficient nyilvántartás that
is also, by construction, the exact table future Odoo-native invoicing will use.

**Architecture:** No new invoice model. A new `invoice_source` field on
`account.move` distinguishes `'szamlazz_archive'` rows from future `'odoo'` rows.
A `models/szamlazz_client.py` module owns all HTTP/XML talk to szamlazz.hu's
Agent API plus partner-matching and PDF-attachment helpers. A new, non-transient
`dentari.szamlazz.sync` model holds only sync-run metadata (never invoice data)
and exposes both the `ir.cron` target and a manual "Szinkronizálás most" button.
The szamlazz.hu Agent key lives in `ir.config_parameter`, never on a normal-ACL
model field.

**Tech Stack:** Odoo 18 Community, Python, `requests` + stdlib
`xml.etree.ElementTree` (no new pinned dependency — both ship with Odoo core),
XML views, Odoo ORM/TransactionCase tests with mocked HTTP, oec.sh SaaS hosting.

**Spec:** [docs/superpowers/specs/2026-10-10-invoice-archive-design.md](/Users/ferko/development/DentariOdoo/docs/superpowers/specs/2026-10-10-invoice-archive-design.md)

## Global Constraints

- No new invoice data model — every archived invoice is a standard
  `account.move` (`move_type='out_invoice'`), state stays `draft`, `.action_post()`
  is never called anywhere in this addon.
- `account.move.invoice_source` defaults to `'odoo'`; archive-synced rows set it to
  `'szamlazz_archive'`. This field must exist from the first migration — no later
  addition, since the whole point is zero migration work when Odoo invoicing goes live.
- Depends only on `account` and `dentari_lab` (for `group_lab_manager`) — no `hr`,
  `purchase`, `stock`, no new `res.groups` hierarchy.
- szamlazz.hu Agent API key lives in `ir.config_parameter`
  (`dentari_invoice_archive.szamlazz_agent_key`), never a field on a
  normal-ACL model, never committed to git.
- Nothing in this addon ever calls `.unlink()` on `account.move`,
  `account.move.line`, or `ir.attachment` — 8-year legal retention.
- Dedup is enforced by searching `szamlazz_invoice_number` before create, not by
  trusting the sync cursor alone (Review Focus #1).
- The cron method must never let an exception escape — catch, write
  `last_run_status='error'` + `last_run_message`, return normally (Review Focus #2).
- Module name `dentari_invoice_archive`, version starts `18.0.1.0.0`, license `LGPL-3`.
- Dev environment: oec.sh `dentari-dev-8780` (see `.env.dev`); auto-deploy on push
  is disabled — every deploy needs an explicit trigger + module upgrade step (see
  `odoo-oecsh-ticket-deploy` skill).
- Task 1 (Phase 0 spike) requires a **real** szamlazz.hu Agent API key and at
  least one real invoice number from the live account to run — this cannot be
  executed blind; get the key into `.env.dev` as `SZAMLAZZ_AGENT_KEY` before
  starting Task 1.

## Review Focus

- Re-run after partial failure creates a duplicate archived invoice — covered by
  Task 4's dedup test.
- szamlazz.hu API error/timeout crashes the cron silently — covered by Task 4's
  error-path test.
- Unmatched customer on an invoice crashes instead of creating a new partner —
  covered by Task 3's partner-matching tests.
- Storno/cancelled invoice archived as if it were a normal valid invoice —
  covered by Task 4's cancelled-invoice test (exact detection logic pinned to
  Task 1 findings).
- PDF download failure loses the whole invoice sync instead of just the
  attachment — covered by Task 4's PDF-failure test.

---

## File Structure

```
dentari_invoice_archive/
├── __init__.py
├── __manifest__.py
├── models/
│   ├── __init__.py
│   ├── account_move.py           # invoice_source, szamlazz_invoice_number fields (Task 2)
│   ├── szamlazz_client.py        # query/parse/partner-match/PDF-attach helpers (Task 3)
│   └── szamlazz_sync.py          # dentari.szamlazz.sync: cron target + manual run (Task 4)
├── data/
│   └── ir_cron.xml               # scheduled sync job (Task 5)
├── views/
│   ├── szamlazz_sync_views.xml   # config/run-log form + manual button (Task 5)
│   ├── invoice_archive_views.xml # account.move list, scoped view (Task 6)
│   └── menus.xml                 # Számla archívum root menu (Task 6)
├── security/
│   └── ir.model.access.csv       # ACL for dentari.szamlazz.sync (Task 5)
└── tests/
    ├── __init__.py
    ├── test_account_move.py      # Task 2
    ├── test_szamlazz_client.py   # Task 3
    └── test_szamlazz_sync.py     # Task 4

Root-level, throwaway except the findings doc:

scripts/spike_szamlazz_agent.py            # Phase 0 spike script, removed after Task 1
docs/invoice-archive-spike-findings.md     # committed — gates Tasks 3-4
```

---

### Task 1: Phase 0 Spike — confirm szamlazz.hu Agent API behavior live

**Files:**
- Create: `scripts/spike_szamlazz_agent.py` (throwaway, removed at end of task)
- Create: `docs/invoice-archive-spike-findings.md` (committed)
- Modify: `.env.example` — add `SZAMLAZZ_AGENT_KEY=`

**Interfaces:**
- Consumes: `SZAMLAZZ_AGENT_KEY` env var (loaded the same way `scripts/spike_quick_expense.py` loaded `.env.dev`), plus a real invoice number typed in at runtime.
- Produces: `docs/invoice-archive-spike-findings.md`, answering the 5 questions in the spec's "Phase 0 Spike" section. Tasks 3 and 4 are gated on this file, not on this task's code.

This spike's job is to find out **whether** the Agent API can see web-UI-issued
invoices at all (spec question 1) — that answer decides if Task 4 is a pure API
poller or needs a CSV-import fallback. The script fires real requests and dumps
everything raw; it does not assume a parsed response shape, because that shape
is exactly what's unconfirmed.

- [ ] **Step 1: Add the env var placeholder**

```bash
# .env.example — append
# szamlazz.hu Agent API key (Beállítások > Agentbeállítások on szamlazz.hu)
SZAMLAZZ_AGENT_KEY=
```

- [ ] **Step 2: Write the spike script**

```python
"""
Phase 0 spike -- dentari_invoice_archive.
Answers the 5 questions in
docs/superpowers/specs/2026-10-10-invoice-archive-design.md
("Phase 0 Spike" section) against the real szamlazz.hu account.

Usage:
  SZAMLAZZ_AGENT_KEY=xxx python scripts/spike_szamlazz_agent.py <ismert_szamlaszam>

Prints the raw HTTP status, headers, and body for both the number-query
action and the PDF-fetch action, so a human can read the actual response
shape rather than trust any assumed schema.
"""
import os
import sys

import requests

ENDPOINT = 'https://www.szamlazz.hu/szamla/'


def load_env_file(path='.env.dev'):
    if not os.path.exists(path):
        return
    with open(path, encoding='utf-8') as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, _, value = line.partition('=')
            os.environ.setdefault(key.strip(), value.strip())


def query_by_number(agent_key, invoice_number):
    xml_body = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<xmlszamlaxml xmlns="http://www.szamlazz.hu/xmlszamlaxml"'
        ' xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"'
        ' xsi:schemaLocation="http://www.szamlazz.hu/xmlszamlaxml'
        ' http://www.szamlazz.hu/docs/xsds/agentxml/xmlszamlaxml.xsd">'
        f'<szamlaagentkulcs>{agent_key}</szamlaagentkulcs>'
        f'<szamlaszam>{invoice_number}</szamlaszam>'
        '<pdf>true</pdf>'
        '</xmlszamlaxml>'
    )
    resp = requests.post(
        ENDPOINT,
        files={'action-szamla_agent_xml': ('request.xml', xml_body, 'text/xml')},
        timeout=30,
    )
    return resp


def main():
    if len(sys.argv) < 2:
        print('Usage: spike_szamlazz_agent.py <ismert_szamlaszam>')
        sys.exit(1)
    load_env_file()
    agent_key = os.environ.get('SZAMLAZZ_AGENT_KEY')
    if not agent_key:
        print('SZAMLAZZ_AGENT_KEY not set (env or .env.dev)')
        sys.exit(1)

    invoice_number = sys.argv[1]
    resp = query_by_number(agent_key, invoice_number)

    print('--- STATUS ---')
    print(resp.status_code)
    print('--- HEADERS ---')
    for k, v in resp.headers.items():
        print(f'{k}: {v}')
    print('--- BODY (first 2000 bytes, raw) ---')
    print(resp.content[:2000])
    print('--- BODY LENGTH ---')
    print(len(resp.content))

    with open('spike_response_raw.bin', 'wb') as fh:
        fh.write(resp.content)
    print("\nFull raw body written to spike_response_raw.bin for inspection.")


if __name__ == '__main__':
    main()
```

- [ ] **Step 3: Run it against a real, known invoice number**

Run: `SZAMLAZZ_AGENT_KEY=<real key> python scripts/spike_szamlazz_agent.py <real invoice number issued through the web UI>`

Read the raw output. Specifically check:
- Does the response contain actual invoice data (not an auth/permission error)? → answers question 1.
- What is the root element and field structure of the XML (if the body is XML)? → answers question 3.
- Is text encoded as UTF-8 or `windows-1250`? Check the `Content-Type` header's `charset` and whether Hungarian accented characters in the body round-trip correctly. → answers question 3.
- Repeat with a known **storno/cancelled** invoice number if one exists on the account → answers question 4.
- Try 2-3 sequential numbers around a known one (e.g. if a real invoice is `E-2026-0042`, also try `E-2026-0041` and `E-2026-0043`) to see if the numbering is a plain incrementing sequence → feeds question 2.

- [ ] **Step 4: Write the findings doc**

```markdown
# Invoice Archive — Phase 0 Spike Findings

Date: <fill in run date>
Account tested against: <szamlazz.hu account, redact the actual key>

## Q1: Does number-query see web-UI-issued invoices?
<yes/no + evidence (status code, whether invoice data came back)>

## Q2: Numbering pattern
<e.g. "E-2026-NNNN, strictly sequential per calendar year" or "not sequential, can't probe">

## Q3: Request/response shape
- Working request body (exact XML used): <paste>
- Response Content-Type / charset: <paste>
- Response root element / key fields and their actual tag names: <paste>
- Encoding issues observed: <yes/no + detail>

## Q4: Storno representation
<exact field/value that marks a cancelled invoice, or "not tested — no storno invoice available yet">

## Q5: Rate limits
<anything observed or documented; if untested, note "not stress-tested, default to once-daily cron">

## Decision for Task 4
<"Agent API polling viable, use sequential-number probing from last_synced_number"
 OR "Agent API cannot discover web-UI invoices — Task 4 must instead import a
 periodically-exported CSV from szamlazz.hu's own export feature" — pick one,
 this gates how Task 4 is actually written.>
```

Fill in every section from the real run before continuing — this file, not the
script, is what Tasks 3 and 4 are built against.

- [ ] **Step 5: Remove the throwaway script, keep the findings doc, commit**

```bash
rm scripts/spike_szamlazz_agent.py spike_response_raw.bin
git add docs/invoice-archive-spike-findings.md .env.example
git commit -m "docs: record szamlazz.hu Agent API spike findings"
```

---

### Task 2: `account.move` extension — `invoice_source` + `szamlazz_invoice_number`

**Files:**
- Create: `dentari_invoice_archive/__init__.py`
- Create: `dentari_invoice_archive/__manifest__.py`
- Create: `dentari_invoice_archive/models/__init__.py`
- Create: `dentari_invoice_archive/models/account_move.py`
- Create: `dentari_invoice_archive/tests/__init__.py`
- Test: `dentari_invoice_archive/tests/test_account_move.py`

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: `account.move.invoice_source` (Selection, default `'odoo'`),
  `account.move.szamlazz_invoice_number` (Char, indexed). Tasks 3 and 4 both
  read/write these two fields by exact name.

- [ ] **Step 1: Scaffold the module**

```python
# dentari_invoice_archive/__init__.py
from . import models
```

```python
# dentari_invoice_archive/__manifest__.py
{
    'name': 'Dentari Invoice Archive',
    'version': '18.0.1.0.0',
    'category': 'Dental / Accounting',
    'summary': 'Archives szamlazz.hu-issued invoices into Odoo as draft account.move records',
    'depends': ['account', 'dentari_lab'],
    # Empty at Task 2 -- account.move field additions need no new security/view
    # file (account.move's own ACL already covers it). Tasks 5 and 6 each
    # append their own new file(s) here as they're created -- never reference
    # a data file in this list before the task that creates it exists, or
    # every `odoo -u` run until then fails with a missing-file error.
    'data': [],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
```

```python
# dentari_invoice_archive/models/__init__.py
from . import account_move
```

```python
# dentari_invoice_archive/tests/__init__.py
from . import test_account_move
```

- [ ] **Step 2: Write the failing test**

```python
# dentari_invoice_archive/tests/test_account_move.py
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestAccountMoveInvoiceSource(TransactionCase):

    def test_new_move_defaults_to_odoo_source(self):
        partner = self.env['res.partner'].create({'name': 'Teszt Ügyfél'})
        move = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': partner.id,
        })
        self.assertEqual(move.invoice_source, 'odoo')
        self.assertFalse(move.szamlazz_invoice_number)

    def test_archive_source_and_number_round_trip(self):
        partner = self.env['res.partner'].create({'name': 'Teszt Ügyfél 2'})
        move = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': partner.id,
            'invoice_source': 'szamlazz_archive',
            'szamlazz_invoice_number': 'E-2026-0042',
        })
        self.assertEqual(move.invoice_source, 'szamlazz_archive')
        self.assertEqual(move.szamlazz_invoice_number, 'E-2026-0042')

    def test_dedup_lookup_finds_existing_archived_invoice(self):
        partner = self.env['res.partner'].create({'name': 'Teszt Ügyfél 3'})
        self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': partner.id,
            'invoice_source': 'szamlazz_archive',
            'szamlazz_invoice_number': 'E-2026-0099',
        })
        found = self.env['account.move'].search([
            ('szamlazz_invoice_number', '=', 'E-2026-0099'),
        ])
        self.assertEqual(len(found), 1)
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `odoo -d <dev_db> -i dentari_invoice_archive --test-enable --stop-after-init --test-tags dentari_invoice_archive`
Expected: FAIL / module fails to load — `account_move.py` doesn't exist with these fields yet.

- [ ] **Step 4: Implement the fields**

```python
# dentari_invoice_archive/models/account_move.py
from odoo import fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    invoice_source = fields.Selection(
        [('odoo', 'Odoo'), ('szamlazz_archive', 'Számlázz.hu archívum')],
        string='Számla forrása',
        default='odoo',
        required=True,
    )
    szamlazz_invoice_number = fields.Char(
        string='Számlázz.hu sorszám',
        copy=False,
        index=True,
    )
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `odoo -d <dev_db> -u dentari_invoice_archive --test-enable --stop-after-init --test-tags dentari_invoice_archive`
Expected: PASS, 3 tests.

- [ ] **Step 6: Commit**

```bash
git add dentari_invoice_archive
git commit -m "feat: add dentari_invoice_archive module with account.move invoice_source field"
```

---

### Task 3: szamlazz.hu client helpers — parse, partner match, PDF attach

**Files:**
- Create: `dentari_invoice_archive/models/szamlazz_client.py`
- Test: `dentari_invoice_archive/tests/test_szamlazz_client.py`
- Modify: `dentari_invoice_archive/tests/__init__.py`

**Interfaces:**
- Consumes: `docs/invoice-archive-spike-findings.md` (Task 1 — already run
  live against account invoice `AE-2026-37`). The code below is written
  directly against those confirmed findings, not guessed — root element
  `<szamla>`, customer data under `<vevo>` (not `<elado>` — that was an
  earlier wrong guess; `<szallito>` is the *issuing* business, never the
  partner), totals under `<osszegek><totalossz>`, per-rate VAT under
  `<osszegek><afakulcsossz>`, dates under `<alap><kelt>`/`<alap><telj>`,
  currency as the literal string `"Ft"` (not ISO `"HUF"`), and the PDF as
  base64 text inside a `<pdf>` element in the *same* response body — not a
  response header. `is_cancelled` detection is an **open gap**: no cancelled
  invoice was available to test against, so it's hardcoded `False` for now
  (see findings doc Q4) rather than guessed at a tag name.
- Produces: `parse_query_response(xml_bytes) -> dict` (keys: `invoice_number`,
  `issue_date`, `fulfillment_date`, `net_total`, `vat_total`, `gross_total`,
  `vat_rate` (the real `afakulcs` percentage from the invoice's first/only
  rate group, e.g. `0.0` for this account's usual VAT-exempt case or `27.0`
  — Task 4 looks this up directly rather than re-deriving a ratio), `currency`
  (normalized to ISO, e.g. `'HUF'` — raw XML says `'Ft'`), `partner_name`,
  `partner_tax_number`, `partner_zip`, `partner_city`, `partner_address`,
  `is_cancelled` (always `False` for now — see gap above)),
  `find_or_create_partner(env, parsed) -> res.partner recordset`,
  `attach_pdf(env, move, pdf_bytes, filename) -> ir.attachment recordset`.
  Task 4 calls all three by these exact names.

- [ ] **Step 1: Write the failing tests**

```python
# dentari_invoice_archive/tests/test_szamlazz_client.py
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.dentari_invoice_archive.models.szamlazz_client import (
    attach_pdf,
    find_or_create_partner,
    parse_query_response,
)

# Real shape, confirmed live against account invoice AE-2026-37 (see
# docs/invoice-archive-spike-findings.md) -- a 27%-rate example here, since
# the real sample invoice happened to be VAT-exempt (afakulcs=0.0) and a
# non-zero case needs its own coverage.
SAMPLE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<szamla xmlns="http://www.szamlazz.hu/szamla">
  <szallito>
    <nev>Kiállító Egyéni Vállalkozó</nev>
  </szallito>
  <alap>
    <szamlaszam>AE-2026-0042</szamlaszam>
    <kelt>2026-10-01</kelt>
    <telj>2026-10-01</telj>
    <devizanem>Ft</devizanem>
  </alap>
  <vevo>
    <nev>Teszt Ügyfél Kft</nev>
    <adoszam>12345678-1-42</adoszam>
    <cim>
      <irsz>1111</irsz>
      <telepules>Budapest</telepules>
      <cim>Teszt utca 1.</cim>
    </cim>
  </vevo>
  <osszegek>
    <afakulcsossz>
      <afatipus>27</afatipus>
      <afakulcs>27.0</afakulcs>
      <netto>10000</netto>
      <afa>2700</afa>
      <brutto>12700</brutto>
    </afakulcsossz>
    <totalossz>
      <netto>10000</netto>
      <afa>2700</afa>
      <brutto>12700</brutto>
    </totalossz>
  </osszegek>
  <pdf>JVBERi0xLjQgZmFrZQ==</pdf>
</szamla>
""".encode('utf-8')

# Real sample: VAT-exempt (AAM), net == gross -- this account's common case.
SAMPLE_XML_EXEMPT = SAMPLE_XML.replace(
    b'<afatipus>27</afatipus>\n      <afakulcs>27.0</afakulcs>\n      <netto>10000</netto>\n      <afa>2700</afa>\n      <brutto>12700</brutto>',
    b'<afatipus>AAM</afatipus>\n      <afakulcs>0.0</afakulcs>\n      <netto>10000</netto>\n      <afa>0</afa>\n      <brutto>10000</brutto>',
).replace(
    b'<netto>10000</netto>\n      <afa>2700</afa>\n      <brutto>12700</brutto>\n    </totalossz>',
    b'<netto>10000</netto>\n      <afa>0</afa>\n      <brutto>10000</brutto>\n    </totalossz>',
)


@tagged('post_install', '-at_install')
class TestParseQueryResponse(TransactionCase):

    def test_parses_all_fields(self):
        parsed = parse_query_response(SAMPLE_XML)
        self.assertEqual(parsed['invoice_number'], 'AE-2026-0042')
        self.assertEqual(parsed['issue_date'], '2026-10-01')
        self.assertEqual(parsed['fulfillment_date'], '2026-10-01')
        self.assertEqual(parsed['net_total'], 10000.0)
        self.assertEqual(parsed['vat_total'], 2700.0)
        self.assertEqual(parsed['gross_total'], 12700.0)
        self.assertEqual(parsed['vat_rate'], 27.0)
        self.assertEqual(parsed['currency'], 'HUF')  # normalized from raw 'Ft'
        self.assertEqual(parsed['partner_name'], 'Teszt Ügyfél Kft')
        self.assertEqual(parsed['partner_tax_number'], '12345678-1-42')
        self.assertEqual(parsed['partner_city'], 'Budapest')

    def test_parses_vat_exempt_invoice(self):
        parsed = parse_query_response(SAMPLE_XML_EXEMPT)
        self.assertEqual(parsed['vat_rate'], 0.0)
        self.assertEqual(parsed['vat_total'], 0.0)
        self.assertEqual(parsed['net_total'], parsed['gross_total'])

    def test_extracts_embedded_pdf(self):
        parsed = parse_query_response(SAMPLE_XML)
        self.assertEqual(parsed['pdf_bytes'][:4], b'%PDF')

    def test_is_cancelled_defaults_false_pending_confirmation(self):
        # No real storno invoice was available during the Phase 0 spike --
        # see docs/invoice-archive-spike-findings.md Q4. This always reads
        # False until a confirmed tag/value is found; it is not a claim that
        # cancelled invoices are correctly detected yet.
        parsed = parse_query_response(SAMPLE_XML)
        self.assertFalse(parsed['is_cancelled'])


@tagged('post_install', '-at_install')
class TestFindOrCreatePartner(TransactionCase):

    def test_creates_new_partner_when_no_match(self):
        parsed = {
            'partner_name': 'Új Ügyfél Bt',
            'partner_tax_number': '99988877-1-42',
            'partner_zip': '2000',
            'partner_city': 'Szentendre',
            'partner_address': 'Fő tér 2.',
        }
        partner = find_or_create_partner(self.env, parsed)
        self.assertTrue(partner)
        self.assertEqual(partner.name, 'Új Ügyfél Bt')
        self.assertEqual(partner.vat, '99988877-1-42')

    def test_matches_existing_partner_by_tax_number(self):
        existing = self.env['res.partner'].create({
            'name': 'Meglévő Ügyfél Kft',
            'vat': '11122233-1-42',
        })
        parsed = {
            'partner_name': 'Meglévő Ügyfél Kft (más néven)',
            'partner_tax_number': '11122233-1-42',
            'partner_zip': '1000',
            'partner_city': 'Budapest',
            'partner_address': 'Más cím 9.',
        }
        partner = find_or_create_partner(self.env, parsed)
        self.assertEqual(partner, existing)

    def test_no_duplicate_partner_created_on_repeat_call(self):
        parsed = {
            'partner_name': 'Ismétlődés Kft',
            'partner_tax_number': '55566677-1-42',
            'partner_zip': '3000',
            'partner_city': 'Eger',
            'partner_address': 'Teszt köz 3.',
        }
        first = find_or_create_partner(self.env, parsed)
        second = find_or_create_partner(self.env, parsed)
        self.assertEqual(first, second)


@tagged('post_install', '-at_install')
class TestAttachPdf(TransactionCase):

    def test_attaches_pdf_to_move(self):
        partner = self.env['res.partner'].create({'name': 'Teszt Ügyfél 4'})
        move = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': partner.id,
        })
        attachment = attach_pdf(self.env, move, b'%PDF-1.4 fake content', 'E-2026-0042.pdf')
        self.assertEqual(attachment.res_model, 'account.move')
        self.assertEqual(attachment.res_id, move.id)
        self.assertEqual(attachment.name, 'E-2026-0042.pdf')
        self.assertIn(attachment, move.attachment_ids if hasattr(move, 'attachment_ids') else move.message_main_attachment_id | attachment)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `odoo -d <dev_db> -i dentari_invoice_archive --test-enable --stop-after-init --test-tags dentari_invoice_archive`
Expected: FAIL — `szamlazz_client` module doesn't exist yet.

- [ ] **Step 3: Implement the client helpers**

```python
# dentari_invoice_archive/models/szamlazz_client.py
"""
szamlazz.hu Agent API client: HTTP/XML plumbing, partner matching, PDF
attachment. Schema confirmed live against account invoice AE-2026-37 --
see docs/invoice-archive-spike-findings.md. `is_cancelled` is the one
unconfirmed field (no storno sample was available) and always reads False.
"""
import base64
import logging
from xml.etree import ElementTree as ET

import requests

_logger = logging.getLogger(__name__)

AGENT_ENDPOINT = 'https://www.szamlazz.hu/szamla/'

# Namespace-stripped tag paths -- parse_query_response() strips namespaces
# before searching, so these don't need the xmlns prefix. Confirmed against
# the real <szamla> response (not the earlier guessed <xmlszamlavalasz>
# shape) -- szallito is the ISSUING business, never the partner; vevo is
# the customer. amounts live under osszegek/totalossz, not a flat vegosszeg.
FIELD_PATHS = {
    'invoice_number': './alap/szamlaszam',
    'issue_date': './alap/kelt',
    'fulfillment_date': './alap/telj',
    'currency_raw': './alap/devizanem',
    'net_total': './osszegek/totalossz/netto',
    'vat_total': './osszegek/totalossz/afa',
    'gross_total': './osszegek/totalossz/brutto',
    'vat_rate': './osszegek/afakulcsossz/afakulcs',
    'partner_name': './vevo/nev',
    'partner_tax_number': './vevo/adoszam',
    'partner_zip': './vevo/cim/irsz',
    'partner_city': './vevo/cim/telepules',
    'partner_address': './vevo/cim/cim',
}

_NUMERIC_FIELDS = {'net_total', 'vat_total', 'gross_total', 'vat_rate'}

# szamlazz.hu's XML uses the literal Hungarian currency symbol, not ISO 4217.
_CURRENCY_MAP = {'Ft': 'HUF'}


def _strip_namespace(elem):
    for e in elem.iter():
        if '}' in e.tag:
            e.tag = e.tag.split('}', 1)[1]
    return elem


def parse_query_response(xml_bytes):
    """Parse an action-szamla_agent_xml query response into a plain dict."""
    root = _strip_namespace(ET.fromstring(xml_bytes))
    result = {}
    for key, path in FIELD_PATHS.items():
        node = root.find(path)
        text = node.text if node is not None else None
        if key in _NUMERIC_FIELDS:
            result[key] = float(text) if text else 0.0
        else:
            result[key] = text

    raw_currency = result.pop('currency_raw')
    result['currency'] = _CURRENCY_MAP.get(raw_currency, raw_currency)

    pdf_node = root.find('./pdf')
    result['pdf_bytes'] = (
        base64.b64decode(pdf_node.text) if pdf_node is not None and pdf_node.text else None
    )

    # Not derivable from any confirmed field yet -- see spec Phase 0 Q4 /
    # findings doc. Always False until a real storno sample is tested.
    result['is_cancelled'] = False

    return result


def query_invoice(agent_key, invoice_number, timeout=30):
    """Fetch one invoice's data + embedded PDF from szamlazz.hu by number.

    Returns (parsed_dict, pdf_bytes_or_none) -- the PDF comes from inside
    the XML body itself (parsed['pdf_bytes']), not a response header; the
    first agent spike wrongly assumed a 'szlahu_pdf' header existed. Raises
    requests.RequestException on network failure -- callers (Task 4) are
    responsible for catching this.
    """
    xml_body = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<xmlszamlaxml xmlns="http://www.szamlazz.hu/xmlszamlaxml">'
        f'<szamlaagentkulcs>{agent_key}</szamlaagentkulcs>'
        f'<szamlaszam>{invoice_number}</szamlaszam>'
        '<pdf>true</pdf>'
        '</xmlszamlaxml>'
    )
    resp = requests.post(
        AGENT_ENDPOINT,
        files={'action-szamla_agent_xml': ('request.xml', xml_body, 'text/xml')},
        timeout=timeout,
    )
    resp.raise_for_status()
    parsed = parse_query_response(resp.content)
    return parsed, parsed.pop('pdf_bytes')


def find_or_create_partner(env, parsed):
    """Match an existing res.partner by tax number, or create a new one."""
    Partner = env['res.partner']
    tax_number = parsed.get('partner_tax_number')
    if tax_number:
        existing = Partner.search([('vat', '=', tax_number)], limit=1)
        if existing:
            return existing
    return Partner.create({
        'name': parsed.get('partner_name') or 'Ismeretlen ügyfél',
        'vat': tax_number,
        'zip': parsed.get('partner_zip'),
        'city': parsed.get('partner_city'),
        'street': parsed.get('partner_address'),
    })


def attach_pdf(env, move, pdf_bytes, filename):
    """Attach a PDF to an account.move, return the ir.attachment record."""
    return env['ir.attachment'].create({
        'name': filename,
        'datas': base64.b64encode(pdf_bytes),
        'res_model': 'account.move',
        'res_id': move.id,
        'mimetype': 'application/pdf',
    })
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `odoo -d <dev_db> -u dentari_invoice_archive --test-enable --stop-after-init --test-tags dentari_invoice_archive`
Expected: PASS, 8 tests (4 in `TestParseQueryResponse`, 3 in
`TestFindOrCreatePartner`, 1 in `TestAttachPdf`). (Note: the attachment
`assertIn` line in the test file's last assertion is deliberately defensive
about Odoo version field naming — if it fails on your instance, confirm via
`ir.attachment.search([('res_model','=','account.move'),('res_id','=', move.id)])`
instead and simplify that one assertion.)

- [ ] **Step 5: Commit**

```bash
git add dentari_invoice_archive
git commit -m "feat: add szamlazz.hu client parsing, partner matching, PDF attach helpers"
```

---

### Task 4: `dentari.szamlazz.sync` model — cron target, manual run, error handling

**Files:**
- Create: `dentari_invoice_archive/models/szamlazz_sync.py`
- Modify: `dentari_invoice_archive/models/__init__.py`
- Test: `dentari_invoice_archive/tests/test_szamlazz_sync.py`
- Modify: `dentari_invoice_archive/tests/__init__.py`

**Interfaces:**
- Consumes: `szamlazz_client.query_invoice`, `find_or_create_partner`,
  `attach_pdf` (Task 3); `account.move.invoice_source` /
  `szamlazz_invoice_number` (Task 2).
- Produces: `dentari.szamlazz.sync._cron_sync_invoices()` (cron entry point,
  no args beyond `self`), `dentari.szamlazz.sync.action_run_sync()` (button
  entry point). Task 5's `ir.cron` record and button view call these by name.

Numbering/discovery strategy (sequential probe from `last_synced_number`) is
written here assuming Task 1 found that approach viable. If Task 1's decision
was "CSV import instead," this task's `_cron_sync_invoices` body changes to
read an imported file list instead of probing — the dedup, partner-matching,
PDF-attach, and error-handling logic below stays identical either way, since
all of it operates on one already-fetched `parsed` dict at a time.

- [ ] **Step 1: Write the failing tests**

```python
# dentari_invoice_archive/tests/test_szamlazz_sync.py
from unittest.mock import patch

from odoo.tests.common import TransactionCase, tagged

PARSED_OK = {
    'invoice_number': 'E-2026-0042',
    'issue_date': '2026-10-01',
    'fulfillment_date': '2026-10-01',
    'net_total': 10000.0,
    'vat_total': 2700.0,
    'gross_total': 12700.0,
    'vat_rate': 27.0,
    'currency': 'HUF',
    'is_cancelled': False,
    'partner_name': 'Teszt Ügyfél Kft',
    'partner_tax_number': '12345678-1-42',
    'partner_zip': '1111',
    'partner_city': 'Budapest',
    'partner_address': 'Teszt utca 1.',
}


@tagged('post_install', '-at_install')
class TestSzamlazzSync(TransactionCase):

    def setUp(self):
        super().setUp()
        self.env['ir.config_parameter'].sudo().set_param(
            'dentari_invoice_archive.szamlazz_agent_key', 'fake-key-for-tests',
        )
        self.sync = self.env['dentari.szamlazz.sync'].create({})
        # PARSED_OK is net=10000, vat=2700 -- a 27% sale tax (standard HU
        # ÁFA rate) must exist for _sync_one to find and apply it; an income
        # account must exist for the line's required account_id. Neither is
        # guaranteed present on a bare test database, so create them
        # explicitly rather than assume demo Chart of Accounts data.
        self.sale_tax = self.env['account.tax'].search([
            ('type_tax_use', '=', 'sale'), ('amount', '=', 27),
        ], limit=1) or self.env['account.tax'].create({
            'name': 'Teszt ÁFA 27%',
            'amount': 27,
            'type_tax_use': 'sale',
        })
        self.income_account = self.env['account.account'].search([
            ('account_type', '=', 'income'),
        ], limit=1) or self.env['account.account'].create({
            'name': 'Teszt árbevétel',
            'code': 'DIA9999',
            'account_type': 'income',
        })

    @patch('odoo.addons.dentari_invoice_archive.models.szamlazz_sync.query_invoice')
    def test_sync_creates_draft_archived_move(self, mock_query):
        mock_query.return_value = (PARSED_OK, b'%PDF-1.4 fake')
        self.sync._sync_one('E-2026-0042')

        move = self.env['account.move'].search([
            ('szamlazz_invoice_number', '=', 'E-2026-0042'),
        ])
        self.assertEqual(len(move), 1)
        self.assertEqual(move.state, 'draft')
        self.assertEqual(move.invoice_source, 'szamlazz_archive')
        self.assertEqual(move.amount_total, 12700.0)

    @patch('odoo.addons.dentari_invoice_archive.models.szamlazz_sync.query_invoice')
    def test_sync_is_idempotent(self, mock_query):
        mock_query.return_value = (PARSED_OK, b'%PDF-1.4 fake')
        self.sync._sync_one('E-2026-0042')
        self.sync._sync_one('E-2026-0042')

        count = self.env['account.move'].search_count([
            ('szamlazz_invoice_number', '=', 'E-2026-0042'),
        ])
        self.assertEqual(count, 1)

    @patch('odoo.addons.dentari_invoice_archive.models.szamlazz_sync.query_invoice')
    def test_cancelled_invoice_marked_not_active_draft(self, mock_query):
        cancelled = dict(PARSED_OK, is_cancelled=True, invoice_number='E-2026-0043')
        mock_query.return_value = (cancelled, b'%PDF-1.4 fake')
        self.sync._sync_one('E-2026-0043')

        move = self.env['account.move'].search([
            ('szamlazz_invoice_number', '=', 'E-2026-0043'),
        ])
        self.assertEqual(move.state, 'cancel')

    @patch('odoo.addons.dentari_invoice_archive.models.szamlazz_sync.query_invoice')
    def test_pdf_failure_still_creates_move(self, mock_query):
        mock_query.return_value = (PARSED_OK, None)
        self.sync._sync_one('E-2026-0042')

        move = self.env['account.move'].search([
            ('szamlazz_invoice_number', '=', 'E-2026-0042'),
        ])
        self.assertEqual(len(move), 1)

    @patch('odoo.addons.dentari_invoice_archive.models.szamlazz_sync.query_invoice')
    def test_api_error_sets_error_status_without_raising(self, mock_query):
        import requests
        mock_query.side_effect = requests.exceptions.Timeout('boom')

        self.sync._cron_sync_invoices()  # must not raise

        self.assertEqual(self.sync.last_run_status, 'error')
        self.assertIn('boom', self.sync.last_run_message or '')

    @patch('odoo.addons.dentari_invoice_archive.models.szamlazz_sync.query_invoice')
    def test_missing_income_account_sets_error_status(self, mock_query):
        self.env['account.account'].search([
            ('account_type', '=', 'income'),
            ('company_id', '=', self.env.company.id),
        ]).write({'account_type': 'income_other'})
        mock_query.return_value = (PARSED_OK, b'%PDF-1.4 fake')

        self.sync._cron_sync_invoices()  # must not raise

        self.assertEqual(self.sync.last_run_status, 'error')
        self.assertIn('bevétel', self.sync.last_run_message or '')
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `odoo -d <dev_db> -i dentari_invoice_archive --test-enable --stop-after-init --test-tags dentari_invoice_archive`
Expected: FAIL — `dentari.szamlazz.sync` model doesn't exist yet.

- [ ] **Step 3: Implement the sync model**

```python
# dentari_invoice_archive/models/szamlazz_sync.py
import logging
import re

from odoo import fields, models

from .szamlazz_client import attach_pdf, find_or_create_partner, query_invoice

_logger = logging.getLogger(__name__)


class SzamlazzSync(models.Model):
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

    def _get_agent_key(self):
        return self.env['ir.config_parameter'].sudo().get_param(
            'dentari_invoice_archive.szamlazz_agent_key',
        )

    def _batch_size(self):
        return int(self.env['ir.config_parameter'].sudo().get_param(
            'dentari_invoice_archive.sync_batch_size', default='20',
        ))

    def _sync_one(self, invoice_number):
        """Fetch, parse, and archive one invoice by number. Idempotent:
        returns the existing move untouched if already archived."""
        self.ensure_one()
        existing = self.env['account.move'].search([
            ('szamlazz_invoice_number', '=', invoice_number),
        ], limit=1)
        if existing:
            return existing

        agent_key = self._get_agent_key()
        parsed, pdf_bytes = query_invoice(agent_key, invoice_number)

        partner = find_or_create_partner(self.env, parsed)
        income_account = self._archive_income_account()
        tax = self._matching_sale_tax(parsed)
        move = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': partner.id,
            'invoice_source': 'szamlazz_archive',
            'szamlazz_invoice_number': parsed['invoice_number'],
            'invoice_date': parsed.get('issue_date'),
            'currency_id': self._currency_id(parsed.get('currency')),
            'invoice_line_ids': [(0, 0, {
                'name': f"Számlázz.hu archívum — {parsed['invoice_number']}",
                'account_id': income_account.id,
                'quantity': 1,
                'price_unit': parsed.get('net_total', 0.0),
                'tax_ids': [(6, 0, tax.ids)] if tax else False,
            })],
        })

        if parsed.get('is_cancelled'):
            move.button_cancel()

        if pdf_bytes:
            attach_pdf(self.env, move, pdf_bytes, f"{parsed['invoice_number']}.pdf")

        return move

    def _currency_id(self, currency_code):
        if not currency_code:
            return self.env.company.currency_id.id
        currency = self.env['res.currency'].search([('name', '=', currency_code)], limit=1)
        return currency.id if currency else self.env.company.currency_id.id

    def _archive_income_account(self):
        """account.move.line.account_id is required -- pick any income
        account for this company. Which one is cosmetic: these moves are
        never posted, so no real ledger is affected by the choice."""
        account = self.env['account.account'].search([
            ('account_type', '=', 'income'),
            ('company_id', '=', self.env.company.id),
        ], limit=1)
        if not account:
            from odoo.exceptions import UserError
            raise UserError(
                'Nincs elérhető bevétel főkönyvi számla (account_type=income) '
                'az archívum sorokhoz -- vegyél fel legalább egyet.'
            )
        return account

    def _matching_sale_tax(self, parsed):
        """Find a sale tax matching the invoice's real afakulcs rate
        (parsed['vat_rate'], confirmed live in the Phase 0 spike -- not a
        ratio derived from totals, which szamlazz.hu already gives us
        directly). For this account's common case (AAM/VAT-exempt,
        vat_rate=0.0), no tax should apply at all -- an explicit 0% sale
        tax, if one exists, is still used so the line shows *something*
        rather than looking untaxed by omission; if none exists, the line
        is created with no tax, which for a 0% rate changes nothing about
        amount_tax (it's correctly 0 either way)."""
        rate = parsed.get('vat_rate')
        if rate is None:
            return self.env['account.tax']
        return self.env['account.tax'].search([
            ('type_tax_use', '=', 'sale'),
            ('amount', '=', rate),
            ('company_id', '=', self.env.company.id),
        ], limit=1)

    def _next_candidate_number(self):
        self.ensure_one()
        if self.last_synced_number:
            return self._increment_number(self.last_synced_number)
        return self.env['ir.config_parameter'].sudo().get_param(
            'dentari_invoice_archive.first_invoice_number', default='',
        )

    def _increment_number(self, invoice_number):
        """Increment the trailing numeric part of an invoice number string,
        e.g. 'E-2026-0042' -> 'E-2026-0043'. Only valid if Task 1 confirmed
        sequential numbering (spec Phase 0 Q2) -- otherwise this whole
        probing approach is replaced by the CSV-import path noted there."""
        match = re.match(r'^(.*?)(\d+)$', invoice_number)
        if not match:
            return invoice_number
        prefix, digits = match.groups()
        return f'{prefix}{str(int(digits) + 1).zfill(len(digits))}'

    def _cron_sync_invoices(self):
        """ir.cron entry point. Never lets an exception escape -- any
        failure (API error, auth failure, or -- until Task 1's findings
        make "not found" distinguishable from "real error" -- the normal
        end of the available sequence) aborts the current run and is
        recorded on this record rather than raised, so a human can see it
        in the sync config form instead of only in the server log."""
        sync = self.search([], limit=1) or self.create({})
        synced_count = 0
        try:
            agent_key = sync._get_agent_key()
            if not agent_key:
                raise ValueError(
                    'SZAMLAZZ_AGENT_KEY nincs beállítva '
                    '(ir.config_parameter: dentari_invoice_archive.szamlazz_agent_key)'
                )

            next_number = sync._next_candidate_number()
            for _ in range(sync._batch_size()):
                move = sync._sync_one(next_number)
                if move:
                    synced_count += 1
                    sync.last_synced_number = next_number
                next_number = sync._increment_number(next_number)

            sync.write({
                'last_run': fields.Datetime.now(),
                'last_run_status': 'ok',
                'last_run_message': f'{synced_count} számla szinkronizálva.',
                'last_run_count': synced_count,
            })
        except Exception as exc:  # noqa: BLE001 -- cron must never raise
            _logger.exception('szamlazz sync failed')
            sync.write({
                'last_run': fields.Datetime.now(),
                'last_run_status': 'error',
                'last_run_message': str(exc),
                'last_run_count': synced_count,
            })

    def action_run_sync(self):
        self.ensure_one()
        self._cron_sync_invoices()
```

```python
# dentari_invoice_archive/models/__init__.py — update
from . import account_move
from . import szamlazz_client
from . import szamlazz_sync
```

```python
# dentari_invoice_archive/tests/__init__.py — update
from . import test_account_move
from . import test_szamlazz_client
from . import test_szamlazz_sync
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `odoo -d <dev_db> -u dentari_invoice_archive --test-enable --stop-after-init --test-tags dentari_invoice_archive`
Expected: PASS, 6 tests.

- [ ] **Step 5: Commit**

```bash
git add dentari_invoice_archive
git commit -m "feat: add dentari.szamlazz.sync model with cron-safe error handling"
```

---

### Task 5: Cron wiring, security, and the manual sync config form

**Files:**
- Create: `dentari_invoice_archive/data/ir_cron.xml`
- Create: `dentari_invoice_archive/security/ir.model.access.csv`
- Create: `dentari_invoice_archive/views/szamlazz_sync_views.xml`
- Modify: `dentari_invoice_archive/views/menus.xml` (created fully in Task 6; stub it here if Task 6 hasn't run yet)
- Test: extend `dentari_invoice_archive/tests/test_szamlazz_sync.py`

**Interfaces:**
- Consumes: `dentari.szamlazz.sync` model, `action_run_sync()`, `_cron_sync_invoices()` (Task 4).
- Produces: the installed `ir.cron` record (`dentari_invoice_archive.ir_cron_szamlazz_sync`) and the `dentari.szamlazz.sync` form action (`dentari_invoice_archive.action_szamlazz_sync`) — Task 6's menu links to this action by its external ID.

- [ ] **Step 1: Write the failing test**

```python
# append to dentari_invoice_archive/tests/test_szamlazz_sync.py

@tagged('post_install', '-at_install')
class TestSzamlazzSyncSetup(TransactionCase):

    def test_cron_job_registered(self):
        cron = self.env.ref('dentari_invoice_archive.ir_cron_szamlazz_sync')
        self.assertEqual(cron.model_id.model, 'dentari.szamlazz.sync')
        self.assertTrue(cron.active)

    def test_sync_action_registered(self):
        action = self.env.ref('dentari_invoice_archive.action_szamlazz_sync')
        self.assertEqual(action.res_model, 'dentari.szamlazz.sync')
```

- [ ] **Step 2: Run to verify it fails**

Run: `odoo -d <dev_db> -i dentari_invoice_archive --test-enable --stop-after-init --test-tags dentari_invoice_archive`
Expected: FAIL — xmlids don't exist yet.

- [ ] **Step 3: Add security, cron, and the config form**

```csv
# dentari_invoice_archive/security/ir.model.access.csv
id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink
access_dentari_szamlazz_sync_manager,dentari.szamlazz.sync.manager,model_dentari_szamlazz_sync,dentari_lab.group_lab_manager,1,1,1,0
```

```xml
<!-- dentari_invoice_archive/data/ir_cron.xml -->
<odoo>
    <data noupdate="1">
        <record id="ir_cron_szamlazz_sync" model="ir.cron">
            <field name="name">Számlázz.hu archívum szinkronizálás</field>
            <field name="model_id" ref="model_dentari_szamlazz_sync"/>
            <field name="state">code</field>
            <field name="code">model._cron_sync_invoices()</field>
            <field name="interval_number">1</field>
            <field name="interval_type">days</field>
            <field name="numbercall">-1</field>
            <field name="active">True</field>
        </record>
    </data>
</odoo>
```

```xml
<!-- dentari_invoice_archive/views/szamlazz_sync_views.xml -->
<odoo>
    <record id="view_szamlazz_sync_form" model="ir.ui.view">
        <field name="name">dentari.szamlazz.sync.form</field>
        <field name="model">dentari.szamlazz.sync</field>
        <field name="arch" type="xml">
            <form>
                <header>
                    <button name="action_run_sync" type="object"
                            string="Szinkronizálás most" class="btn-primary"/>
                </header>
                <sheet>
                    <group>
                        <field name="last_run"/>
                        <field name="last_run_status"/>
                        <field name="last_synced_number"/>
                        <field name="last_run_count"/>
                        <field name="last_run_message"/>
                    </group>
                </sheet>
            </form>
        </field>
    </record>

    <record id="action_szamlazz_sync" model="ir.actions.act_window">
        <field name="name">Számlázz.hu szinkronizálás</field>
        <field name="res_model">dentari.szamlazz.sync</field>
        <field name="view_mode">form</field>
        <field name="target">current</field>
    </record>
</odoo>
```

- [ ] **Step 4: Register the three new files in the manifest**

```python
# dentari_invoice_archive/__manifest__.py — 'data' key, was []
'data': [
    'security/ir.model.access.csv',
    'data/ir_cron.xml',
    'views/szamlazz_sync_views.xml',
],
```

- [ ] **Step 5: Run to verify it passes**

Run: `odoo -d <dev_db> -u dentari_invoice_archive --test-enable --stop-after-init --test-tags dentari_invoice_archive`
Expected: PASS, 2 tests.

- [ ] **Step 6: Commit**

```bash
git add dentari_invoice_archive
git commit -m "feat: wire szamlazz sync cron, security, and manual-run form"
```

---

### Task 6: Archive list view and menu

**Files:**
- Create: `dentari_invoice_archive/views/invoice_archive_views.xml`
- Create: `dentari_invoice_archive/views/menus.xml` (final version — supersedes Task 5's stub if one was added)
- Test: `dentari_invoice_archive/tests/test_account_move.py` (extend)

**Interfaces:**
- Consumes: `account.move.invoice_source` (Task 2), `action_szamlazz_sync` (Task 5).
- Produces: `dentari_invoice_archive.action_invoice_archive_list`,
  `dentari_invoice_archive.menu_invoice_archive_root` — terminal task, nothing
  later depends on these.

- [ ] **Step 1: Write the failing test**

```python
# append to dentari_invoice_archive/tests/test_account_move.py

class TestInvoiceArchiveView(TransactionCase):

    def test_archive_list_action_registered_and_scoped(self):
        action = self.env.ref('dentari_invoice_archive.action_invoice_archive_list')
        self.assertEqual(action.res_model, 'account.move')
        import ast
        domain = ast.literal_eval(action.domain)
        partner = self.env['res.partner'].create({'name': 'Teszt Ügyfél 5'})
        archived = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': partner.id,
            'invoice_source': 'szamlazz_archive',
            'szamlazz_invoice_number': 'E-2026-0077',
        })
        odoo_native = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': partner.id,
        })
        found = self.env['account.move'].search(domain)
        self.assertIn(archived, found)
        self.assertNotIn(odoo_native, found)

    def test_menu_registered(self):
        self.assertTrue(self.env.ref('dentari_invoice_archive.menu_invoice_archive_root'))
```

- [ ] **Step 2: Run to verify it fails**

Run: `odoo -d <dev_db> -i dentari_invoice_archive --test-enable --stop-after-init --test-tags dentari_invoice_archive`
Expected: FAIL — action/menu xmlids don't exist yet.

- [ ] **Step 3: Add the list view, action, and menu**

```xml
<!-- dentari_invoice_archive/views/invoice_archive_views.xml -->
<odoo>
    <record id="view_invoice_archive_list" model="ir.ui.view">
        <field name="name">account.move.invoice.archive.list</field>
        <field name="model">account.move</field>
        <field name="arch" type="xml">
            <list string="Számla archívum" create="false" delete="false">
                <field name="szamlazz_invoice_number"/>
                <field name="partner_id"/>
                <field name="invoice_date"/>
                <field name="amount_untaxed" string="Nettó" sum="Nettó összesen"/>
                <field name="amount_tax" string="ÁFA" sum="ÁFA összesen"/>
                <field name="amount_total" string="Bruttó" sum="Bruttó összesen"/>
                <field name="currency_id"/>
                <field name="state"/>
            </list>
        </field>
    </record>

    <record id="action_invoice_archive_list" model="ir.actions.act_window">
        <field name="name">Számla archívum</field>
        <field name="res_model">account.move</field>
        <field name="view_mode">list,form</field>
        <field name="domain">[('invoice_source', '=', 'szamlazz_archive')]</field>
        <field name="context">{'create': False}</field>
    </record>
</odoo>
```

```xml
<!-- dentari_invoice_archive/views/menus.xml -->
<odoo>
    <menuitem id="menu_invoice_archive_root"
              name="Számla archívum"
              groups="dentari_lab.group_lab_manager"
              sequence="40"/>

    <menuitem id="menu_invoice_archive_list"
              name="Kiadott számlák (archívum)"
              parent="menu_invoice_archive_root"
              action="action_invoice_archive_list"
              sequence="10"/>

    <menuitem id="menu_invoice_archive_sync"
              name="Szinkronizálás beállításai"
              parent="menu_invoice_archive_root"
              action="action_szamlazz_sync"
              sequence="20"/>
</odoo>
```

- [ ] **Step 4: Register the two new files in the manifest**

```python
# dentari_invoice_archive/__manifest__.py — append to 'data' key
'data': [
    'security/ir.model.access.csv',
    'data/ir_cron.xml',
    'views/szamlazz_sync_views.xml',
    'views/invoice_archive_views.xml',
    'views/menus.xml',
],
```

- [ ] **Step 5: Run to verify it passes**

Run: `odoo -d <dev_db> -u dentari_invoice_archive --test-enable --stop-after-init --test-tags dentari_invoice_archive`
Expected: PASS, 2 tests. Full suite for the module should now be green end to end.

- [ ] **Step 6: Commit**

```bash
git add dentari_invoice_archive
git commit -m "feat: add invoice archive list view and menu"
```

---

## Self-Review Notes

- **Spec coverage:** every "Requirements" bullet maps to a task — automatic
  pull (Task 4+5), stored fields (Task 2+4), dedup (Task 4 test 2), same model
  as future Odoo invoicing (Task 2), draft-only/no posting (Task 4 — no
  `action_post()` call anywhere), list/filter view (Task 6), no-delete
  retention (no `.unlink()` anywhere in the module), Phase 0 spike (Task 1).
- **Placeholder scan:** the only intentionally-provisional content is
  `FIELD_PATHS` (Task 3) and the sequential-probe/batch-abort logic (Task 4),
  both explicitly flagged as pending Task 1's real findings, with a concrete
  correction step (Task 3 Step 5) rather than left unresolved.
- **Type consistency:** `_sync_one`, `_cron_sync_invoices`, `action_run_sync`,
  `query_invoice`, `find_or_create_partner`, `attach_pdf`, `parse_query_response`
  are named and called identically across Tasks 3-6.
- **Review Focus:** all 5 items have an owning test (Task 4 tests 2, 5, 3, 4;
  Task 3 partner tests cover item 3 at the helper level too).

## Odoo-Skill Review Pass (2026-10-10)

Checked against this repo's own live Odoo 18 conventions
(`dental_quick_expense`) and the `odoo-development-skill`'s v18 module/
security/cron pattern files. Two real defects found and fixed in this
document:

1. **Manifest referenced data files before the tasks that create them**
   (Task 2's `__manifest__.py` originally listed `data/ir_cron.xml` and all
   three view files up front) — every `odoo -u` run in Tasks 2-4 would have
   hard-failed on a missing file. Fixed: `'data': []` at Task 2, each file
   added to the manifest by the task that creates it (Task 5 Step 4, Task 6
   Step 4).
2. **The archived invoice line had no `account_id` and no `tax_ids`** —
   `account.move.line.account_id` is required (confirmed by this repo's own
   `dental_quick_expense` test hitting the exact `IntegrityError` for a
   missing required field on that same model), so `_sync_one`'s `create()`
   would have failed outright; and without a tax, `amount_tax` would stay 0
   regardless of what szamlazz.hu reported, silently dropping the ÁFA figure
   the whole addon exists to preserve. Fixed: `_archive_income_account()` and
   `_matching_sale_tax()` helpers added to `dentari.szamlazz.sync`, wired into
   the line's `account_id`/`tax_ids`, with a new test for the no-income-
   account failure path (Task 4 now has 6 tests, not 5).

Confirmed correct as originally written (no change needed): `<list>` tag for
list views (not `<tree>` — matches this repo's live Odoo 18 behavior, where
the skill's generic v18 template still shows `<tree>`), `ir.model.access.csv`
group-ref format, `ir.cron` field set (`state='code'`, `interval_type`,
`numbercall`), `menuitem groups=` security pattern.
