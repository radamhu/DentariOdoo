#!/usr/bin/env python3
"""
D5 — migrate_worksheet.py
TICKET-003: Migrate dental_work_log rows from source PostgreSQL → Odoo 18.

Usage (from docs/cutover_artifacts/):
  python migrate_worksheet.py       # dry-run: validate + show planned creates
  python migrate_worksheet.py --run # write records to Odoo

Environment variables (or .env.prod via direnv):
  RAILWAY_DATA_URL        postgresql://user:pass@host:5432/db
  RAILWAY_DATA_SCHEMA     schema name (default: myschema)
  ODOO_URL                http://192.168.0.9:8069
  ODOO_DATABASE           dentari_odoo
  ODOO_USERNAME           admin
  ODOO_PASSWORD           ...
  ODOO_MIGRATION_USER_ID  res.users.id assigned to all migrated records
                          (default: authenticated uid)
"""

import argparse
import csv
import os
import re
import sys
import unicodedata
import xmlrpc.client
from pathlib import Path

import psycopg2
import psycopg2.extras


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SRC_URL     = os.environ["RAILWAY_DATA_URL"]
SRC_SCHEMA  = os.environ.get("RAILWAY_DATA_SCHEMA", "myschema")
ODOO_URL    = os.environ["ODOO_URL"]
ODOO_DB     = os.environ["ODOO_DATABASE"]
ODOO_USER   = os.environ["ODOO_USERNAME"]
ODOO_PW     = os.environ["ODOO_PASSWORD"]

PARTNER_CSV = Path(__file__).parent / "partner_mapping.csv"
BATCH_SIZE  = 100
ODOO_MODEL  = "dental.work.log"


# ---------------------------------------------------------------------------
# Transform tables (§4 of migration plan)
# ---------------------------------------------------------------------------

# Keys are accent-stripped lowercase; values are Odoo Selection keys.
WORK_TYPE_MAP = {
    "korona":     "korona",
    "hid":        "hid",
    "implant":    "implant",
    "facet":      "facet",
    "ideiglenes": "ideiglenes",
    "javitas":    "javitas",
    "monolitikus":"monolitikus",
}

VALID_VITA = {
    "A1", "A2", "A3", "A3.5", "A4",
    "B1", "B2", "B3", "B4",
    "C1", "C2", "C3", "C4",
    "D2", "D3", "D4",
    "BL1", "BL2", "BL3", "BL4",
}


# ---------------------------------------------------------------------------
# Partner map (D3 artifact)
# ---------------------------------------------------------------------------

def load_partner_map():
    """Load client_name → partner_id from the canonical D3 CSV."""
    partner_map = {}
    with open(PARTNER_CSV, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["status"] not in ("SKIP", ""):
                partner_map[row["client_name"]] = int(row["partner_id"])
    return partner_map


# ---------------------------------------------------------------------------
# Odoo connection
# ---------------------------------------------------------------------------

def odoo_connect():
    common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common")
    uid = common.authenticate(ODOO_DB, ODOO_USER, ODOO_PW, {})
    if not uid:
        print("ERROR: Odoo authentication failed.", file=sys.stderr)
        sys.exit(1)
    models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object")
    return uid, models


# ---------------------------------------------------------------------------
# Extract
# ---------------------------------------------------------------------------

def extract():
    """Fetch all rows from source dental_work_log, ordered by id."""
    conn = psycopg2.connect(SRC_URL, options=f"-c search_path={SRC_SCHEMA}")
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""
            SELECT id, date, client_name, patient_name, tooth_position,
                   tooth_color, work_type, pieces, price_per_piece, notes,
                   created_by
            FROM dental_work_log
            ORDER BY id
        """)
        rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


# ---------------------------------------------------------------------------
# Transform helpers
# ---------------------------------------------------------------------------

def _strip_accents(val):
    return unicodedata.normalize("NFD", val).encode("ascii", "ignore").decode()


def map_work_type(val):
    """Free-text → Selection key.  Unknown non-empty values → 'egyeb'."""
    if not val:
        return False
    key = _strip_accents(val.strip().lower())
    mapped = WORK_TYPE_MAP.get(key)
    if mapped:
        return mapped
    return "egyeb" if key else False


def map_tooth_color(val):
    """Returns (selection_key_or_False, unrecognised_original_or_None)."""
    if not val:
        return False, None
    normalized = val.strip().replace(",", ".")  # handle comma decimal separator
    if normalized in VALID_VITA:
        return normalized, None
    return False, normalized


def transform_row(row, partner_map, migration_user_id):
    color_key, color_unknown = map_tooth_color(row["tooth_color"])

    notes = (row["notes"] or "").strip()
    if color_unknown:
        # Preserve unrecognised VITA value so no data is silently lost
        notes = f"[migráció] fogszín: {color_unknown}\n{notes}".strip()

    # A1: strip whitespace from tooth_position before the [0-9,.\\-] constraint
    tp = re.sub(r"\s+", "", row["tooth_position"] or "")

    return {
        "date":            str(row["date"]),                          # VARCHAR YYYY-MM-DD
        "partner_id":      partner_map[row["client_name"].strip()],   # A3: strip trailing spaces
        "patient_name":    (row["patient_name"] or "")[:100] or False,
        "tooth_position":  tp[:50] or False,
        "tooth_color":     color_key,
        "work_type":       map_work_type(row["work_type"]),
        "pieces":          int(row["pieces"]),
        "price_per_piece": float(round(row["price_per_piece"])),
        "notes":           notes or False,
        "user_id":         migration_user_id,
        "_source_id":      int(row["id"]),   # internal — stripped before Odoo write
    }


# ---------------------------------------------------------------------------
# Validate
# ---------------------------------------------------------------------------

def validate_rows(transformed):
    """Re-check all Odoo model constraints client-side before writing.

    Returns a list of error strings (empty list = all good).
    """
    errors = []
    for vals in transformed:
        sid = vals["_source_id"]
        if not vals.get("partner_id"):
            errors.append(f"  row {sid}: partner_id missing")
        pieces = vals.get("pieces", 0)
        if not (1 <= pieces <= 100):
            errors.append(f"  row {sid}: pieces={pieces} out of range [1, 100]")
        price = vals.get("price_per_piece", -1)
        if not (0 <= price <= 500_000):
            errors.append(f"  row {sid}: price_per_piece={price} out of range [0, 500 000]")
        tp = vals.get("tooth_position") or ""
        if tp and not re.match(r"^[\d,.\-]+$", tp):
            errors.append(f"  row {sid}: tooth_position={tp!r} contains invalid characters")
    return errors


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------

def _fetch_existing_keys(models, uid):
    """Return a set of dedup tuples for all existing dental.work.log records."""
    records = models.execute_kw(
        ODOO_DB, uid, ODOO_PW,
        ODOO_MODEL, "search_read", [[]],
        {"fields": ["date", "partner_id", "pieces", "price_per_piece", "patient_name"]},
    )
    keys = set()
    for r in records:
        keys.add((
            str(r["date"]),
            r["partner_id"][0] if r["partner_id"] else 0,
            r["pieces"],
            float(r["price_per_piece"]),
            r["patient_name"] or False,
        ))
    return keys


def _dedup_key(vals):
    return (
        str(vals["date"]),
        vals["partner_id"],
        vals["pieces"],
        float(vals["price_per_piece"]),
        vals["patient_name"],
    )


def _batches(seq, size):
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


def _odoo_vals(row):
    """Strip internal _* keys before sending to Odoo."""
    return {k: v for k, v in row.items() if not k.startswith("_")}


def load(models, uid, transformed, dry_run):
    """Write transformed rows to Odoo in batches.

    Returns (created, skipped, errors).
    """
    existing = _fetch_existing_keys(models, uid)
    print(f"  {len(existing)} existing record(s) in Odoo — will skip duplicates.\n")

    created = skipped = errors = 0

    for batch in _batches(transformed, BATCH_SIZE):
        new_rows = []
        for vals in batch:
            if _dedup_key(vals) in existing:
                print(f"  SKIP (exists): source_id={vals['_source_id']}  date={vals['date']}")
                skipped += 1
            else:
                new_rows.append(vals)

        if not new_rows:
            continue

        if dry_run:
            for v in new_rows:
                print(
                    f"  DRY RUN create:"
                    f"  source_id={v['_source_id']}"
                    f"  date={v['date']}"
                    f"  partner_id={v['partner_id']}"
                    f"  work_type={v['work_type'] or '—'}"
                    f"  pieces={v['pieces']}"
                    f"  price={int(v['price_per_piece'])} Ft"
                )
            created += len(new_rows)
            continue

        odoo_batch = [_odoo_vals(r) for r in new_rows]

        # Attempt batch create; fall back to row-by-row on failure
        try:
            new_ids = models.execute_kw(
                ODOO_DB, uid, ODOO_PW,
                ODOO_MODEL, "create", [odoo_batch],
            )
            n = len(new_ids) if isinstance(new_ids, list) else 1
            for r in new_rows:
                existing.add(_dedup_key(r))
            created += n
            print(f"  Batch OK: created {n} record(s).  Running total: {created}")
        except Exception as e:
            src_ids = [r["_source_id"] for r in new_rows]
            print(
                f"  WARN: batch {src_ids} failed ({e}). Retrying row-by-row …",
                file=sys.stderr,
            )
            for row_vals, src_row in zip(odoo_batch, new_rows):
                try:
                    models.execute_kw(
                        ODOO_DB, uid, ODOO_PW,
                        ODOO_MODEL, "create", [row_vals],
                    )
                    existing.add(_dedup_key(src_row))
                    created += 1
                except Exception as row_e:
                    print(
                        f"  ERROR source_id={src_row['_source_id']}: {row_e}",
                        file=sys.stderr,
                    )
                    errors += 1

    return created, skipped, errors


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="D5 — migrate dental_work_log to Odoo 18 (TICKET-003)"
    )
    parser.add_argument(
        "--run",
        action="store_true",
        help="Write records to Odoo (default: dry-run)",
    )
    args = parser.parse_args()
    dry_run = not args.run

    print("=== TICKET-003  migrate_worksheet.py ===")
    print(f"Mode: {'DRY RUN' if dry_run else 'LIVE — writing to Odoo'}\n")

    # Partner mapping (D3 artifact)
    partner_map = load_partner_map()
    print(f"Partner map loaded: {len(partner_map)} client(s) from {PARTNER_CSV.name}")

    # Odoo connection
    print("Connecting to Odoo …")
    uid, models = odoo_connect()
    print(f"  Authenticated as uid={uid}")

    migration_user_id = int(os.environ.get("ODOO_MIGRATION_USER_ID", uid))
    print(f"  Migration user_id: {migration_user_id}\n")

    # Extract
    print("Extracting source rows …")
    source_rows = extract()
    print(f"  {len(source_rows)} rows fetched from source.\n")

    # Transform
    print("Transforming rows …")
    transformed = []
    transform_errors = []
    for row in source_rows:
        try:
            transformed.append(transform_row(row, partner_map, migration_user_id))
        except KeyError as e:
            transform_errors.append(f"  source_id={row['id']}: unknown client_name {e}")

    if transform_errors:
        print(f"\n{len(transform_errors)} transform error(s):")
        for err in transform_errors:
            print(err)
        print("\nAborting — update partner_mapping.csv and retry.", file=sys.stderr)
        sys.exit(1)

    print(f"  {len(transformed)} rows transformed.\n")

    # Validate
    print("Validating against Odoo constraints …")
    val_errors = validate_rows(transformed)
    if val_errors:
        print(f"\n{len(val_errors)} validation error(s):")
        for err in val_errors:
            print(err)
        print("\nAborting — fix source data or transform logic.", file=sys.stderr)
        sys.exit(1)
    print("  All rows pass validation.\n")

    # Load
    print("Loading into Odoo …")
    created, skipped, errors = load(models, uid, transformed, dry_run)

    # Summary
    print("\n=== Summary ===")
    if dry_run:
        print(f"  DRY RUN — {created} record(s) would be created, {skipped} already exist.")
        print("\n  Re-run with --run to apply.")
    else:
        print(f"  Created : {created}")
        print(f"  Skipped : {skipped}")
        print(f"  Errors  : {errors}")
        if errors:
            print(f"\n  WARNING: {errors} row(s) failed. Review stderr output above.")
            sys.exit(1)
        else:
            print("\n  Migration complete — run post-migration validation (D6) now.")
            print(f"  Expected: 173 records, 1 105 pieces, 5 663 000 Ft total revenue.")


if __name__ == "__main__":
    main()
