import base64
from unittest.mock import MagicMock, patch

from requests.structures import CaseInsensitiveDict

from odoo.tests.common import TransactionCase, tagged

from odoo.addons.dentari_invoice_archive.models.szamlazz_client import (
    InvoiceNotFound,
    attach_pdf,
    find_or_create_partner,
    parse_query_response,
    query_invoice,
)

REQUESTS_POST = 'odoo.addons.dentari_invoice_archive.models.szamlazz_client.requests.post'

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
        self.assertEqual(base64.b64decode(attachment.datas), b'%PDF-1.4 fake content')
        self.assertIn(attachment, move.attachment_ids if hasattr(move, 'attachment_ids') else move.message_main_attachment_id | attachment)


def _fake_response(content, headers=None, status_code=200):
    resp = MagicMock()
    resp.content = content
    resp.status_code = status_code
    resp.headers = CaseInsensitiveDict(headers or {})
    return resp


@tagged('post_install', '-at_install')
class TestQueryInvoice(TransactionCase):
    """Exercises query_invoice itself (requests.post mocked), not just the
    parser -- the not-found detection lives here."""

    @patch(REQUESTS_POST)
    def test_returns_parsed_invoice_and_pdf(self, mock_post):
        mock_post.return_value = _fake_response(SAMPLE_XML, {
            'szlahu_szamlaszam': 'AE-2026-0042',
        })
        parsed, pdf = query_invoice('key', 'AE-2026-0042')
        self.assertEqual(parsed['invoice_number'], 'AE-2026-0042')
        self.assertEqual(pdf[:4], b'%PDF')
        self.assertNotIn('pdf_bytes', parsed)

    @patch(REQUESTS_POST)
    def test_error_header_raises_not_found_without_parsing(self, mock_post):
        # Body deliberately not XML: must never reach the parser.
        mock_post.return_value = _fake_response(b'nem xml', {
            'szlahu_error_code': '7',
            'szlahu_error': 'Nincs ilyen szamla',
        })
        with self.assertRaises(InvoiceNotFound) as ctx:
            query_invoice('key', 'AE-2026-0043')
        self.assertEqual(ctx.exception.invoice_number, 'AE-2026-0043')
        self.assertIn('7', str(ctx.exception))

    @patch(REQUESTS_POST)
    def test_error_header_checked_before_http_status(self, mock_post):
        resp = _fake_response(b'', {'szlahu_error_code': '7'}, status_code=400)
        resp.raise_for_status.side_effect = AssertionError('should not be reached')
        mock_post.return_value = resp
        with self.assertRaises(InvoiceNotFound):
            query_invoice('key', 'AE-2026-0043')

    @patch(REQUESTS_POST)
    def test_parseable_envelope_without_invoice_number_raises_not_found(self, mock_post):
        empty = b'<?xml version="1.0"?><szamla xmlns="http://www.szamlazz.hu/szamla"><alap/></szamla>'
        mock_post.return_value = _fake_response(empty)
        with self.assertRaises(InvoiceNotFound):
            query_invoice('key', 'AE-2026-0043')

    @patch(REQUESTS_POST)
    def test_mismatched_invoice_number_raises_not_found(self, mock_post):
        mock_post.return_value = _fake_response(SAMPLE_XML)  # AE-2026-0042
        with self.assertRaises(InvoiceNotFound):
            query_invoice('key', 'AE-2026-0099')

    @patch(REQUESTS_POST)
    def test_request_body_is_xml_escaped(self, mock_post):
        mock_post.return_value = _fake_response(SAMPLE_XML)
        query_invoice('k&<ey', 'AE-2026-0042')
        body = mock_post.call_args.kwargs['files']['action-szamla_agent_xml'][1]
        self.assertIn('<szamlaagentkulcs>k&amp;&lt;ey</szamlaagentkulcs>', body)
