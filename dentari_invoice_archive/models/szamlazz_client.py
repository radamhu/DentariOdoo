"""
szamlazz.hu Agent API client: HTTP/XML plumbing, partner matching, PDF
attachment. Schema confirmed live against account invoice AE-2026-37 --
see docs/invoice-archive-spike-findings.md. `is_cancelled` is the one
unconfirmed field (no storno sample was available) and always reads False.
"""
import base64
import logging
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape as xml_escape

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

# szamlazz.hu's Agent API reports failures through these response headers
# (the success path carries szlahu_szamlaszam etc. -- confirmed in the
# Phase 0 spike). The specific error code for "no such invoice number" was
# NOT confirmed live, so any error header is treated as "not found".
_ERROR_HEADERS = ('szlahu_error_code', 'szlahu_error')


class InvoiceNotFound(Exception):
    """szamlazz.hu has no invoice with this number (yet). The sync cron
    treats this as the normal "caught up" signal when probing past the
    newest issued number, not as a failure."""

    def __init__(self, invoice_number, detail=None):
        self.invoice_number = invoice_number
        self.detail = detail
        message = f'Számla nem található: {invoice_number}'
        if detail:
            message += f' ({detail})'
        super().__init__(message)


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
    first agent spike wrongly assumed a 'szlahu_pdf' header existed.

    Raises InvoiceNotFound when szamlazz.hu signals an error via its
    szlahu_error/szlahu_error_code headers, or when the body parses but does
    not describe the requested invoice number (defense in depth, in case the
    error-header convention is ever wrong -- an empty/foreign envelope must
    never be archived as if it were a real invoice). Raises
    requests.RequestException on network/HTTP failure and ET.ParseError on
    an unparseable body without error headers -- callers are responsible for
    catching these.
    """
    xml_body = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<xmlszamlaxml xmlns="http://www.szamlazz.hu/xmlszamlaxml">'
        f'<szamlaagentkulcs>{xml_escape(agent_key or "")}</szamlaagentkulcs>'
        f'<szamlaszam>{xml_escape(invoice_number or "")}</szamlaszam>'
        '<pdf>true</pdf>'
        '</xmlszamlaxml>'
    )
    resp = requests.post(
        AGENT_ENDPOINT,
        files={'action-szamla_agent_xml': ('request.xml', xml_body, 'text/xml')},
        timeout=timeout,
    )
    # Checked before raise_for_status(): szamlazz.hu may pair its error
    # headers with a non-2xx status, and the "not found" case must not be
    # reported as an HTTP failure on every normal "caught up" cron run.
    error_code = resp.headers.get('szlahu_error_code')
    error_text = resp.headers.get('szlahu_error')
    if error_code or error_text:
        detail = f'szlahu_error_code={error_code}: {error_text}'
        _logger.info('szamlazz.hu error for %s: %s', invoice_number, detail)
        raise InvoiceNotFound(invoice_number, detail)
    resp.raise_for_status()
    parsed = parse_query_response(resp.content)
    returned_number = (parsed.get('invoice_number') or '').strip()
    if not returned_number or returned_number != (invoice_number or '').strip():
        raise InvoiceNotFound(
            invoice_number,
            f'a válasz sorszáma: {returned_number or "üres"}',
        )
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
