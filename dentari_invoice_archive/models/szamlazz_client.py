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
