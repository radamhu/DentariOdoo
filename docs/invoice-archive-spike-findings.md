# Invoice Archive — Phase 0 Spike Findings

Date: 2026-10-10
Account tested against: szamlazz.hu account (agent key redacted), live invoice `AE-2026-37`

## Q1: Does number-query see web-UI-issued invoices?

**Yes.** `AE-2026-37` was issued through szamlazz.hu's own web UI (not the Agent
API), and `action-szamla_agent_xml` with `<szamlaszam>AE-2026-37</szamlaszam>`
returned HTTP 200 with the full invoice data. No CSV-import fallback needed —
pure API-poller design (Task 4 as planned) is viable.

## Q2: Numbering pattern

`AE-2026-37` — prefix `AE` + year + a **plain running number, not
zero-padded** (`37`, not `0037`). `_increment_number`'s regex approach
(prefix + trailing digits, re-padded to the same digit width) still works
mechanically here since there's no padding to preserve, but don't assume a
fixed-width number elsewhere.

## Q3: Request/response shape

**This differs substantially from the guessed schema in the original spec/plan.**

- `Content-Type` on the response: `application/octet-stream`, not an XML
  content type — don't branch on that header; always treat the body as XML.
- `Content-Encoding: gzip`, auto-decompressed by `requests`.
- Response is **always the full invoice XML body**, not just headers +
  optional PDF. The `szlahu_*` response **headers** carry only a short
  summary (`szlahu_szamlaszam`, `szlahu_nettovegosszeg`,
  `szlahu_bruttovegosszeg`, `szlahu_kintlevoseg`, `szlahu_id`,
  `szlahu_vevoifiokurl`) — no VAT total header at all. Use the XML body for
  everything, not the headers.
- **The PDF is embedded as base64 text inside a `<pdf>` element in the same
  XML body** (confirmed: base64-decodes to a real PDF, magic bytes `%PDF-1.5`)
  — **not** delivered via a `szlahu_pdf` response header as originally
  guessed. `query_invoice` must extract and decode `<pdf>`, not look at headers.
- Real root element and structure (namespace `http://www.szamlazz.hu/szamla`):

  ```
  <szamla>
    <szallito>           <!-- the ISSUING business itself -- NOT the customer -->
      <nev>, <cim>, <adoszam>, <bank>...
    <alap>
      <szamlaszam>, <kelt>        (issue date)
      <telj>                       (fulfillment date)
      <devizanem>                  currency as literal "Ft", not ISO "HUF"
    <vevo>                        <!-- the CUSTOMER -- this is the partner to match/create -->
      <nev>, <cim><irsz>/<telepules>/<cim>, <adoszam>, <email>
    <tetelek><tetel>              line items: <netto>,<afatipus>,<afakulcs>,<afa>,<brutto>
    <osszegek>
      <afakulcsossz>              per-VAT-rate-group subtotal (can repeat)
        <afatipus>, <afakulcs>, <netto>, <afa>, <brutto>
      <totalossz>                 grand total: <netto>, <afa>, <brutto>
    <pdf>                          base64 PDF, inline in this same response
  ```

  **My original guess had seller/buyer backwards** (`elado` for customer data
  — wrong; `vevo` is the customer, `szallito` is the issuing business) and
  guessed flat tag names (`szamlaszam`, `vegosszeg/nettoVegosszeg`) that don't
  exist at all. Task 3's `FIELD_PATHS`/`parse_query_response` must be rewritten
  against the structure above, not patched.

- **This specific account is VAT-exempt** (`afatipus` = `AAM` = *alanyi
  adómentes*, `afakulcs` = `0.0`, `netto == brutto` on this invoice). Task 4's
  original plan ("compute a percentage ratio from net/vat totals, search a
  matching `account.tax`") is fragile and unnecessary — the real `afakulcs`
  value is given directly in the XML (per rate-group, under
  `osszegek/afakulcsossz`), so look that up directly instead of back-deriving
  a ratio. Must handle the `AAM` exempt case as the common case for this
  account, not as an edge case.
- Encoding: UTF-8 declared and correct; accented characters arrive as
  numeric XML entities (`&#225;` etc.) rather than raw UTF-8 bytes, but
  `ElementTree` decodes these transparently — no special handling needed.

## Q4: Storno representation

**Not tested — no cancelled invoice available on this account to query.**
`<alap><tipus>` reads `SZ` for this (normal, non-cancelled) invoice; the
value for a storno invoice is unconfirmed. Task 4's cancelled-invoice
handling stays speculative until a real storno invoice number is available to
test against — flag this as a known gap, not a confirmed behavior.

## Q5: Rate limits

Not stress-tested (single call made). No rate-limit response observed. Default
to once-daily cron as planned; revisit if szamlazz.hu throttles or complains.

## Decision for Task 4

**Agent API polling is viable** (per Q1) — sequential-number probing from
`last_synced_number` stays the right approach, no CSV-import fallback needed.
However, Task 3's parsing code and Task 4's tax-matching code must be
rewritten against the real schema above before either task is considered
correct — the versions already drafted in the plan (guessed `FIELD_PATHS`,
ratio-based tax matching, header-based PDF extraction) do not match reality
and would not work against this account.

## Addendum (2026-10-11): real error-signaling mechanism, resolving Q4's sibling gap

The final-review fix wave shipped a guess that szamlazz.hu signals errors via
`szlahu_error`/`szlahu_error_code` response headers — untested at the time,
flagged as a go-live risk (a bad agent key or outage would be silently
reported as "caught up, 0 synced"). Ran two live probes to settle it:

1. **Unknown invoice number** (`AE-9999-999999`, real key): HTTP 200, **no
   `szlahu_*` headers at all**. Body is a different envelope entirely —
   root `<xmlszamlavalasz>`, not `<szamla>`:
   ```xml
   <xmlszamlavalasz>
     <sikeres>false</sikeres>
     <hibakod><![CDATA[7]]></hibakod>
     <hibauzenet><![CDATA[Hiányzó adat: számla xml (ismeretlen számlaszám,
       rendelésszám vagy külső azonosító).]]></hibauzenet>
   </xmlszamlavalasz>
   ```
2. **Bad agent key** (deliberately garbage key, real invoice number): same
   envelope shape, different code:
   ```xml
   <xmlszamlavalasz><sikeres>false</sikeres>
     <hibakod><![CDATA[3]]></hibakod>
     <hibauzenet><![CDATA[Sikertelen bejelentkezés.]]></hibauzenet>
   </xmlszamlavalasz>
   ```

**Conclusion:** the header-based guess was wrong — szamlazz.hu never sends
`szlahu_error*` headers on failure. The real signal is this `hibakod`
envelope, confirmed to arrive at HTTP 200. `hibakod=7` means "no such
invoice number" (the normal cron "caught up" case); `hibakod=3` means a
bad/revoked agent key (a real failure, must never be treated as caught up).
Other hibakod values are unconfirmed but are now handled correctly by
construction: `szamlazz_client.py`'s `query_invoice` raises `InvoiceNotFound`
only for `hibakod == '7'`, and `SzamlazzApiError` for anything else —
closing the go-live gap this addendum was written to resolve.
