"""
Smoke test — DentariOdoo development environment.

Verifies:
  1. Login via Odoo XML-RPC (admin credentials)
  2. Dashboard views and actions registered
  3. Create one dental.work.log record
  4. Read it back to confirm persistence
  5. read_group aggregation (graph + pivot mechanics)
  6. Delete it (cleanup)

Usage:
  python tests/smoke_dev.py

Credentials are loaded from .env.dev in the repo root.
Override any variable with environment exports before running.
"""

import os
import sys
import xmlrpc.client
from pathlib import Path
from datetime import date


def load_env(path: Path) -> None:
    """Load KEY=VALUE pairs from an .env file into os.environ (no overwrite)."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def fail(msg: str) -> None:
    print(f"FAIL  {msg}", file=sys.stderr)
    sys.exit(1)


def ok(msg: str) -> None:
    print(f"OK    {msg}")


def main() -> None:
    repo_root = Path(__file__).parent.parent
    load_env(repo_root / ".env.dev")

    url = os.environ.get("ODOO_URL", "").rstrip("/")
    db = os.environ.get("ODOO_DATABASE", "")
    username = os.environ.get("ODOO_USERNAME", "admin")
    password = os.environ.get("ODOO_PASSWORD", "")

    if not url or not db or not password:
        fail("ODOO_URL, ODOO_DATABASE, ODOO_PASSWORD must be set (check .env.dev)")

    print(f"Target: {url}  db={db}  user={username}")
    print("-" * 60)

    # ------------------------------------------------------------------
    # 1. Authenticate
    # ------------------------------------------------------------------
    common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common")
    try:
        uid = common.authenticate(db, username, password, {})
    except Exception as exc:
        fail(f"XML-RPC connection error: {exc}")

    if not uid:
        fail("Login rejected — check ODOO_USERNAME / ODOO_PASSWORD")

    ok(f"Login accepted  (uid={uid})")

    models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object")

    def call(model: str, method: str, *args, **kwargs):
        return models.execute_kw(db, uid, password, model, method, list(args), kwargs)

    # ------------------------------------------------------------------
    # 2. Dashboard views and actions registered
    # ------------------------------------------------------------------
    expected_views = [
        "dental.work.log.graph.bar",
        "dental.work.log.graph.pie",
        "dental.work.log.pivot",
        "dental.work.log.dashboard",
    ]
    for view_name in expected_views:
        ids = call("ir.ui.view", "search", [[("name", "=", view_name)]])
        if not ids:
            fail(f"View not found: '{view_name}' — was the module upgraded after adding dashboard views?")
        ok(f"View registered  '{view_name}'")

    expected_actions = [
        "Irányítópult",
        "Bevétel trend",
        "Pivot táblázat",
        "Munkatípus megoszlás",
    ]
    for action_name in expected_actions:
        ids = call(
            "ir.actions.act_window",
            "search",
            [[("name", "=", action_name), ("res_model", "=", "dental.work.log")]],
        )
        if not ids:
            fail(f"Action not found: '{action_name}'")
        ok(f"Action registered '{action_name}'")

    # ------------------------------------------------------------------
    # 3. Find a company partner to use as the clinic (existing)
    # ------------------------------------------------------------------
    partner_ids = call(
        "res.partner",
        "search",
        [[("is_company", "=", True)]],
        limit=1,
    )
    if not partner_ids:
        fail("No company partner found — install base demo data or create one first")

    partner_id = partner_ids[0]
    partner_name = call("res.partner", "read", [partner_id], fields=["name"])[0]["name"]
    ok(f"Partner found   (id={partner_id}, name='{partner_name}')")

    # ------------------------------------------------------------------
    # 3. Create a dental.work.log record
    # ------------------------------------------------------------------
    today = date.today().isoformat()
    new_id = call(
        "dental.work.log",
        "create",
        {
            "date": today,
            "partner_id": partner_id,
            "patient_name": "Smoke Test Patient",
            "tooth_position": "11",
            "tooth_color": "A1",
            "work_type": "korona",
            "pieces": 1,
            "price_per_piece": 5000,
            "notes": "[smoke test] auto-created, safe to delete",
        },
    )
    if not new_id:
        fail("dental.work.log create returned no ID")

    ok(f"Record created  (id={new_id})")

    # ------------------------------------------------------------------
    # 4. Read back to confirm persistence
    # ------------------------------------------------------------------
    records = call(
        "dental.work.log",
        "read",
        [new_id],
        fields=["name", "date", "partner_id", "pieces", "total_revenue"],
    )
    if not records:
        fail(f"Could not read back record id={new_id}")

    rec = records[0]
    assert rec["pieces"] == 1, f"Expected pieces=1, got {rec['pieces']}"
    assert rec["total_revenue"] == 5000, f"Expected total_revenue=5000, got {rec['total_revenue']}"

    ok(f"Record verified (name='{rec['name']}', total={rec['total_revenue']} Ft)")

    # ------------------------------------------------------------------
    # 5. read_group aggregation (graph + pivot mechanics)
    # ------------------------------------------------------------------
    # Simulate graph bar view: GROUP BY date:month, SUM total_revenue
    monthly = call(
        "dental.work.log",
        "read_group",
        [[("id", "=", new_id)]],
        ["total_revenue", "pieces"],
        ["date:month"],
    )
    if not monthly:
        fail("read_group by date:month returned no rows")
    monthly_rev = monthly[0].get("total_revenue", 0)
    if monthly_rev != 5000:
        fail(f"Monthly revenue aggregate expected 5000, got {monthly_rev}")
    ok(f"read_group date:month  total_revenue={monthly_rev} Ft")

    # Simulate pivot / pie view: GROUP BY work_type, SUM total_revenue
    by_type = call(
        "dental.work.log",
        "read_group",
        [[("id", "=", new_id)]],
        ["total_revenue", "pieces"],
        ["work_type"],
    )
    if not by_type:
        fail("read_group by work_type returned no rows")
    type_rev = by_type[0].get("total_revenue", 0)
    type_key = by_type[0].get("work_type")
    if type_rev != 5000:
        fail(f"Work-type revenue aggregate expected 5000, got {type_rev}")
    ok(f"read_group work_type   work_type={type_key}, total_revenue={type_rev} Ft")

    # ------------------------------------------------------------------
    # 6. Cleanup
    # ------------------------------------------------------------------
    call("dental.work.log", "unlink", [new_id])
    ok(f"Record deleted  (id={new_id})")

    print("-" * 60)
    print("PASS  Smoke test completed successfully.")


if __name__ == "__main__":
    main()
