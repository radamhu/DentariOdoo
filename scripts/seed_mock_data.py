#!/usr/bin/env python3
"""Seed mock data into Dentari dev Odoo instance via XML-RPC.

Usage:
    python scripts/seed_mock_data.py

Reads connection details from .env.dev in the project root.
Idempotent: skips partners/work-logs that already exist.
"""

import base64
import os
import sys
import urllib.request
import xmlrpc.client
from pathlib import Path

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

ENV_FILE = Path(__file__).parent.parent / ".env.dev"


def load_env(path: Path) -> dict:
    env = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip()
    return env


def connect(url: str, db: str, username: str, password: str):
    common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common")
    uid = common.authenticate(db, username, password, {})
    if not uid:
        print("ERROR: Authentication failed — check credentials in .env.dev", file=sys.stderr)
        sys.exit(1)
    models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object")
    return uid, models


# ---------------------------------------------------------------------------
# Partners
# ---------------------------------------------------------------------------

PARTNERS = [
    {
        "name": "Dr. Kiss Fogászat Kft.",
        "city": "Budapest",
        "phone": "+36 1 234 5678",
        "initials": "DK",
        "color": "2E86AB",
    },
    {
        "name": "Péter Dental Bt.",
        "city": "Debrecen",
        "phone": "+36 52 345 678",
        "initials": "PD",
        "color": "E84855",
    },
    {
        "name": "Mosolygó Fogászati Rendelő",
        "city": "Győr",
        "phone": "+36 96 456 789",
        "initials": "MF",
        "color": "3BB273",
    },
    {
        "name": "DrSmile Klinika Kft.",
        "city": "Miskolc",
        "phone": "+36 46 567 890",
        "initials": "DS",
        "color": "F18F01",
    },
    {
        "name": "Fehér Fogász Centrum",
        "city": "Pécs",
        "phone": "+36 72 678 901",
        "initials": "FF",
        "color": "7B2D8B",
    },
]


def fetch_avatar(initials: str, color: str) -> str:
    """Generate a simple SVG avatar locally and return it as base64."""
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128">'
        f'<rect width="128" height="128" rx="16" fill="#{color}"/>'
        f'<text x="64" y="64" dy=".35em" text-anchor="middle" '
        f'font-family="Arial,sans-serif" font-weight="bold" font-size="48" fill="#ffffff">'
        f'{initials}</text>'
        f'</svg>'
    )
    return base64.b64encode(svg.encode()).decode()


def seed_partners(url, db, uid, models) -> dict:
    """Returns mapping of partner name → partner id."""
    print("\n── Partners ──────────────────────────────────────")
    name_to_id = {}

    for p in PARTNERS:
        existing = models.execute_kw(
            db, uid, _password,
            "res.partner", "search",
            [[["name", "=", p["name"]], ["is_company", "=", True]]],
        )
        if existing:
            name_to_id[p["name"]] = existing[0]
            print(f"  SKIP  {p['name']} (id={existing[0]})")
            continue

        print(f"  FETCH icon for {p['name']} …", end=" ", flush=True)
        try:
            avatar = fetch_avatar(p["initials"], p["color"])
            print("ok")
        except Exception as exc:
            print(f"failed ({exc}) — creating without icon")
            avatar = False

        vals = {
            "name": p["name"],
            "is_company": True,
            "city": p["city"],
            "phone": p["phone"],
            "customer_rank": 1,
        }
        if avatar:
            vals["image_1920"] = avatar

        new_id = models.execute_kw(db, uid, _password, "res.partner", "create", [vals])
        name_to_id[p["name"]] = new_id
        print(f"  CREATE {p['name']} (id={new_id})")

    return name_to_id


# ---------------------------------------------------------------------------
# Work logs
# ---------------------------------------------------------------------------

WORK_LOGS = [
    # (date, partner_name, patient_name, work_type, tooth_position, tooth_color, pieces, price_per_piece)
    ("2026-04-02", "Dr. Kiss Fogászat Kft.",       "Kovács Péter",   "korona",     "16",       "A2",  1, 38000),
    ("2026-04-05", "Péter Dental Bt.",              "Nagy Mária",     "hid",        "11-21",    "B1",  3, 35000),
    ("2026-04-08", "Mosolygó Fogászati Rendelő",    "Tóth Gábor",     "implant",    "36",       "A3",  1, 45000),
    ("2026-04-10", "DrSmile Klinika Kft.",          "Szabó Anna",     "facet",      "11,12,21,22","BL1", 4, 42000),
    ("2026-04-14", "Fehér Fogász Centrum",          "Horváth László", "korona",     "26",       "C2",  1, 38000),
    ("2026-04-17", "Dr. Kiss Fogászat Kft.",        "Varga Éva",      "monolitikus","46",       "A2",  1, 28000),
    ("2026-04-21", "Péter Dental Bt.",              "Kiss Zoltán",    "ideiglenes", "14,15",    "A1",  2, 12000),
    ("2026-04-24", "DrSmile Klinika Kft.",          "Farkas Ildikó",  "korona",     "37",       "A3",  1, 38000),
    ("2026-04-28", "Mosolygó Fogászati Rendelő",    "Balogh Csaba",   "javitas",    "24",       "B2",  1,  8000),
    ("2026-05-02", "Fehér Fogász Centrum",          "Simon Réka",     "hid",        "34-36",    "A2",  3, 35000),
    ("2026-05-05", "Dr. Kiss Fogászat Kft.",        "Molnár Tibor",   "implant",    "45",       "A3",  1, 45000),
    ("2026-05-08", "Péter Dental Bt.",              "Oláh Judit",     "facet",      "13,12,11", "BL2", 3, 42000),
    ("2026-05-12", "DrSmile Klinika Kft.",          "Papp Béla",      "monolitikus","47",       "A2",  1, 28000),
    ("2026-05-15", "Mosolygó Fogászati Rendelő",    "Fekete Noémi",   "korona",     "15",       "A1",  1, 38000),
    ("2026-05-19", "Dr. Kiss Fogászat Kft.",        "Takács Péter",   "hid",        "12-14",    "B1",  3, 35000),
    ("2026-05-21", "Fehér Fogász Centrum",          "Szőcs Andrea",   "javitas",    "11",       "A2",  1,  8000),
    ("2026-05-23", "Péter Dental Bt.",              "Gál Dániel",     "korona",     "27",       "A3",  1, 38000),
    ("2026-05-26", "Mosolygó Fogászati Rendelő",    "Vincze Katalin", "ideiglenes", "21,22",    "A1",  2, 12000),
    ("2026-05-28", "DrSmile Klinika Kft.",          "Magyar Attila",  "implant",    "16",       "A2",  1, 45000),
    ("2026-05-30", "Dr. Kiss Fogászat Kft.",        "Bíró Zsuzsa",    "facet",      "11,21",    "BL1", 2, 42000),
]


def seed_work_logs(url, db, uid, models, name_to_id: dict):
    print("\n── Work Logs ─────────────────────────────────────")
    created = skipped = 0

    for date, partner_name, patient, work_type, tooth_pos, tooth_color, pieces, price in WORK_LOGS:
        partner_id = name_to_id.get(partner_name)
        if not partner_id:
            print(f"  WARN  partner not found: {partner_name} — skipping log for {patient}")
            continue

        existing = models.execute_kw(
            db, uid, _password,
            "dental.work.log", "search",
            [[
                ["date", "=", date],
                ["partner_id", "=", partner_id],
                ["patient_name", "=", patient],
            ]],
        )
        if existing:
            print(f"  SKIP  {date} | {partner_name[:20]:<20} | {patient}")
            skipped += 1
            continue

        vals = {
            "date": date,
            "partner_id": partner_id,
            "patient_name": patient,
            "work_type": work_type,
            "tooth_position": tooth_pos,
            "tooth_color": tooth_color,
            "pieces": pieces,
            "price_per_piece": price,
        }
        new_id = models.execute_kw(db, uid, _password, "dental.work.log", "create", [vals])
        total = pieces * price
        print(f"  CREATE {date} | {partner_name[:20]:<20} | {patient:<18} | {work_type:<12} | {total:>9,} Ft  (id={new_id})")
        created += 1

    return created, skipped


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

_password = None  # module-level so helpers can reach it without threading ctx


def main():
    global _password

    if not ENV_FILE.exists():
        print(f"ERROR: {ENV_FILE} not found", file=sys.stderr)
        sys.exit(1)

    env = load_env(ENV_FILE)
    url = env["ODOO_URL"]
    db = env["ODOO_DATABASE"]
    username = env["ODOO_USERNAME"]
    _password = env["ODOO_PASSWORD"]

    print(f"Connecting to {url} …")
    uid, models = connect(url, db, username, _password)
    print(f"Authenticated as uid={uid}")

    name_to_id = seed_partners(url, db, uid, models)
    created_logs, skipped_logs = seed_work_logs(url, db, uid, models, name_to_id)

    total_revenue = sum(pcs * price for *_, pcs, price in WORK_LOGS)
    print(f"\n── Summary ───────────────────────────────────────")
    print(f"  Partners : {len(name_to_id)} total ({sum(1 for p in PARTNERS if p['name'] in name_to_id)} resolved)")
    print(f"  Work logs: {created_logs} created, {skipped_logs} skipped")
    print(f"  Expected total revenue: {total_revenue:,} Ft")
    print("Done.")


if __name__ == "__main__":
    main()
