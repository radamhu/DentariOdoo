"""
Smoke test — dentari_mis_reports module.

Verifies:
  1. Report template (report, style, queries, KPIs) registered
  2. Rolling 12-month instance + menu registered (Task 3)
  3. Dev-only QA test dashboard computes the expected KPI values (Task 4)

Usage:
  python tests/test_mis_report.py

Credentials are loaded from .env.dev in the repo root.
"""

import datetime
import json
import os
import sys
import urllib.request
from pathlib import Path


def jsonrpc(url: str, service: str, method: str, args: list):
    payload = {
        "jsonrpc": "2.0", "method": "call",
        "params": {"service": service, "method": method, "args": args},
        "id": 1,
    }
    req = urllib.request.Request(
        f"{url}/jsonrpc", data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        r = json.loads(resp.read())
        if "error" in r:
            raise RuntimeError(json.dumps(r["error"], indent=2))
        return r["result"]


def previous_month_range():
    today = datetime.date.today()
    first_of_this_month = today.replace(day=1)
    last_of_prev_month = first_of_this_month - datetime.timedelta(days=1)
    first_of_prev_month = last_of_prev_month.replace(day=1)
    return first_of_prev_month.isoformat(), last_of_prev_month.isoformat()


def load_env(path: Path) -> None:
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

    try:
        uid = jsonrpc(url, "common", "authenticate", [db, username, password, {}])
    except Exception as exc:
        fail(f"JSON-RPC connection error: {exc}")
    if not uid:
        fail("Login rejected — check credentials")
    ok(f"Login accepted (uid={uid})")

    def call(model: str, method: str, *args, **kwargs):
        return jsonrpc(
            url, "object", "execute_kw",
            [db, uid, password, model, method, list(args), kwargs],
        )

    def xmlid(name: str, required: bool = True) -> int | None:
        # ir.model.data.get_object_reference is not RPC-callable on this Odoo
        # instance (confirmed against a pre-existing dentari_lab xmlid too —
        # not specific to this module). ir.model.data is a regular model, so
        # search_read works the same way get_object_reference would.
        recs = call(
            "ir.model.data", "search_read",
            [("module", "=", "dentari_mis_reports"), ("name", "=", name)],
            fields=["res_id"],
        )
        if not recs:
            if required:
                fail(
                    f"External ID not found: dentari_mis_reports.{name} — "
                    "upgrade the module with '-u dentari_mis_reports' first"
                )
            return None
        return recs[0]["res_id"]

    # ------------------------------------------------------------------
    # 1. Report template registered
    # ------------------------------------------------------------------
    report_id = xmlid("mis_report_kiadas_bevetel")
    ok(f"mis.report registered (id={report_id})")

    for kpi_xmlid, expected_expr in [
        ("mis_report_kpi_netto", "exp.amount_untaxed"),
        ("mis_report_kpi_afa", "exp.amount_tax"),
        ("mis_report_kpi_brutto", "exp.amount_untaxed + exp.amount_tax"),
        ("mis_report_kpi_bevetel", "lab.total_revenue"),
        ("mis_report_kpi_eredmeny", "lab.total_revenue - exp.amount_untaxed - exp.amount_tax"),
    ]:
        kpi_id = xmlid(kpi_xmlid)
        kpi = call("mis.report.kpi", "read", [kpi_id], fields=["expression"])[0]
        if kpi["expression"] != expected_expr:
            fail(f"{kpi_xmlid} expression mismatch: {kpi['expression']!r} != {expected_expr!r}")
        ok(f"KPI {kpi_xmlid} expression OK ({expected_expr})")

    # ------------------------------------------------------------------
    # 2. Rolling 12-month instance + menu registered
    # ------------------------------------------------------------------
    instance_id = xmlid("mis_report_instance_havi")
    period_count = call(
        "mis.report.instance.period", "search_count",
        [("report_instance_id", "=", instance_id)],
    )
    if period_count != 12:
        fail(f"Expected 12 periods on the rolling instance, found {period_count}")
    ok(f"Rolling instance has {period_count} periods")

    menu_id = xmlid("menu_dentari_mis_havi")
    action_id = xmlid("action_mis_report_instance_havi")
    action = call(
        "ir.actions.act_window", "read", [action_id],
        fields=["res_model", "res_id"],
    )[0]
    if action["res_model"] != "mis.report.instance" or action["res_id"] != instance_id:
        fail(f"Menu action does not point at the rolling instance: {action}")
    ok(f"Menu {menu_id} action points at instance {instance_id}")

    # ------------------------------------------------------------------
    # 3. Dev-only QA test dashboard computes the expected KPI values
    #    (only present when this environment's database was created with
    #    demo data enabled — the 'demo' manifest key never loads otherwise,
    #    same as every other module's demo/ data on this environment)
    # ------------------------------------------------------------------
    qa_instance_id = xmlid("mis_report_instance_qa", required=False)
    if qa_instance_id is None:
        print("SKIP  QA dashboard not present — this environment's database "
              "has demo data disabled (check: any module's 'demo' field is "
              "False in ir.module.module)")
        print("-" * 60)
        print("PASS  dentari_mis_reports smoke test completed successfully "
              "(QA dashboard check skipped).")
        return

    date_from, date_to = previous_month_range()

    demo_moves = call(
        "account.move", "search_read",
        [
            ("invoice_date", ">=", date_from),
            ("invoice_date", "<=", date_to),
            ("state", "=", "posted"),
            ("move_type", "=", "in_invoice"),
            ("expense_category_id", "!=", False),
        ],
        fields=["amount_untaxed", "amount_tax"],
    )
    if not demo_moves:
        fail("No posted expense moves found in the previous month — is this the dev env with demo data enabled?")
    expected_netto = sum(m["amount_untaxed"] for m in demo_moves)
    expected_afa = sum(m["amount_tax"] for m in demo_moves)
    expected_brutto = expected_netto + expected_afa

    demo_logs = call(
        "dental.work.log", "search_read",
        [
            ("date", ">=", date_from),
            ("date", "<=", date_to),
        ],
        fields=["total_revenue"],
    )
    if not demo_logs:
        fail("No work logs found in the previous month — is this the dev env with demo data enabled?")
    expected_revenue = sum(l["total_revenue"] for l in demo_logs)
    expected_eredmeny = expected_revenue - expected_brutto

    result = call("mis.report.instance", "compute", [qa_instance_id])
    values_by_label = {
        row["label"]: row["cells"][0]["val"] for row in result["body"]
    }

    checks = [
        ("Netto", expected_netto),
        ("Áfa", expected_afa),
        ("Bruttó", expected_brutto),
        ("Bevétel (Összeg)", expected_revenue),
        ("Eredmény", expected_eredmeny),
    ]
    for label, expected in checks:
        actual = values_by_label.get(label)
        if actual != expected:
            fail(f"QA dashboard KPI '{label}': expected {expected}, got {actual}")
        ok(f"QA dashboard KPI '{label}' = {actual} Ft")

    print("-" * 60)
    print("PASS  dentari_mis_reports smoke test completed successfully.")


if __name__ == "__main__":
    main()
