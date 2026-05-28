#!/usr/bin/env python3
"""
D3 — create_partners.py
Build the client_name → res.partner mapping for TICKET-003 migration.

Usage:
  python create_partners.py            # dry-run: show what would be created
  python create_partners.py --create   # create missing partners in Odoo
  python create_partners.py --create --skip Monolitikus   # skip a client

Output:
  docs/cutover_artifacts/partner_mapping.csv   (written after --create)

Reads credentials from environment (or .env.prod via direnv):
  RAILWAY_DATA_URL   postgresql://...
  RAILWAY_DATA_SCHEMA
  ODOO_URL
  ODOO_DATABASE
  ODOO_USERNAME
  ODOO_PASSWORD
"""

import argparse
import csv
import os
import sys
import xmlrpc.client
from pathlib import Path

import psycopg2
import psycopg2.extras


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SRC_URL    = os.environ["RAILWAY_DATA_URL"]
SRC_SCHEMA = os.environ.get("RAILWAY_DATA_SCHEMA", "myschema")
ODOO_URL   = os.environ["ODOO_URL"]
ODOO_DB    = os.environ["ODOO_DATABASE"]
ODOO_USER  = os.environ["ODOO_USERNAME"]
ODOO_PW    = os.environ["ODOO_PASSWORD"]

OUTPUT_CSV = Path(__file__).parent / "partner_mapping.csv"


# ---------------------------------------------------------------------------
# Source: fetch distinct client names
# ---------------------------------------------------------------------------

def fetch_source_clients():
    conn = psycopg2.connect(SRC_URL, options=f"-c search_path={SRC_SCHEMA}")
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""
            SELECT client_name, COUNT(*) AS record_count
            FROM dental_work_log
            GROUP BY client_name
            ORDER BY record_count DESC
        """)
        rows = cur.fetchall()
    conn.close()
    return rows


# ---------------------------------------------------------------------------
# Odoo: authenticate and search/create partners
# ---------------------------------------------------------------------------

def odoo_connect():
    common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common")
    uid = common.authenticate(ODOO_DB, ODOO_USER, ODOO_PW, {})
    if not uid:
        print("ERROR: Odoo authentication failed.", file=sys.stderr)
        sys.exit(1)
    models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object")
    return uid, models


def search_partner(models, uid, name):
    """Case-insensitive exact match on res.partner name (is_company=True)."""
    results = models.execute_kw(
        ODOO_DB, uid, ODOO_PW,
        "res.partner", "search_read",
        [[["name", "ilike", name], ["is_company", "=", True]]],
        {"fields": ["id", "name"], "limit": 5},
    )
    # ilike may return partial matches; filter for exact case-insensitive match
    exact = [r for r in results if r["name"].lower() == name.lower()]
    return exact[0] if exact else None


def create_partner(models, uid, name):
    """Create a new res.partner company record."""
    partner_id = models.execute_kw(
        ODOO_DB, uid, ODOO_PW,
        "res.partner", "create",
        [{"name": name, "is_company": True}],
    )
    return partner_id


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="D3 partner mapping builder")
    parser.add_argument("--create", action="store_true",
                        help="Create missing partners in Odoo (default: dry-run)")
    parser.add_argument("--skip", metavar="NAME", action="append", default=[],
                        help="Skip this client_name (can repeat). Skipped rows get partner_id=SKIP in CSV.")
    args = parser.parse_args()

    skip_set = {s.lower() for s in args.skip}

    print("Fetching source client names …")
    clients = fetch_source_clients()
    print(f"  {len(clients)} distinct client names found.\n")

    print("Connecting to Odoo …")
    uid, models = odoo_connect()
    print(f"  Authenticated as uid={uid}\n")

    rows = []
    for c in clients:
        name = c["client_name"].strip()   # remove leading/trailing whitespace from source
        count = c["record_count"]
        flagged = name.lower() in skip_set

        if flagged:
            status = "SKIP"
            partner_id = None
            action = "skipped by --skip flag"
        else:
            existing = search_partner(models, uid, name)
            if existing:
                status = "EXISTS"
                partner_id = existing["id"]
                action = f"matched existing id={partner_id}"
            else:
                status = "CREATE"
                partner_id = None
                action = "will be created" if not args.create else "…"

        rows.append({
            "client_name": name,
            "record_count": count,
            "status": status,
            "partner_id": partner_id,
            "notes": "",
        })

        flag_marker = " *** A2 ANOMALY — review before creating" if name == "Monolitikus" else ""
        print(f"  [{status:6s}] {name!r:35s} ({count:3d} records)  {action}{flag_marker}")

    if args.create:
        print("\nCreating missing partners in Odoo …")
        for row in rows:
            if row["status"] == "CREATE":
                pid = create_partner(models, uid, row["client_name"])
                row["partner_id"] = pid
                row["status"] = "CREATED"
                print(f"  Created {row['client_name']!r}  → partner_id={pid}")

        print(f"\nWriting {OUTPUT_CSV} …")
        with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=["client_name", "record_count", "status", "partner_id", "notes"],
            )
            writer.writeheader()
            writer.writerows(rows)
        print(f"  Saved {len(rows)} rows.\n")
    else:
        print("\n--- DRY RUN --- no changes made. Pass --create to apply.")

    # Summary
    print("\nSummary:")
    from collections import Counter
    counts = Counter(r["status"] for r in rows)
    for k, v in sorted(counts.items()):
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
