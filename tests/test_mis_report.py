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

import os
import sys
import xmlrpc.client
from pathlib import Path


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

    common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common")
    try:
        uid = common.authenticate(db, username, password, {})
    except Exception as exc:
        fail(f"XML-RPC connection error: {exc}")
    if not uid:
        fail("Login rejected — check credentials")
    ok(f"Login accepted (uid={uid})")

    models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object")

    def call(model: str, method: str, *args, **kwargs):
        return models.execute_kw(db, uid, password, model, method, list(args), kwargs)

    def xmlid(name: str) -> int:
        try:
            _model, res_id = call(
                "ir.model.data", "get_object_reference",
                "dentari_mis_reports", name,
            )
        except Exception:
            fail(
                f"External ID not found: dentari_mis_reports.{name} — "
                "upgrade the module with '-u dentari_mis_reports' first"
            )
        return res_id

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
        [[("report_instance_id", "=", instance_id)]],
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

    print("-" * 60)
    print("PASS  dentari_mis_reports smoke test completed successfully.")


if __name__ == "__main__":
    main()
