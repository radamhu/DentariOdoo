"""
Smoke test — dental.monthly.email.wizard model existence and field check.

Usage:
  python tests/test_monthly_email.py

Credentials loaded from .env.dev in the repo root.
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

    def call(model, method, *args, **kwargs):
        return models.execute_kw(db, uid, password, model, method, list(args), kwargs)

    # 1. Verify model is registered
    model_ids = call("ir.model", "search", [[("model", "=", "dental.monthly.email.wizard")]])
    if not model_ids:
        fail("Model dental.monthly.email.wizard not found — upgrade module with -u dentari_lab")
    ok(f"Model dental.monthly.email.wizard registered (id={model_ids[0]})")

    # 2. Verify mail.template record exists
    try:
        _m, tmpl_id = call(
            "ir.model.data", "get_object_reference",
            "dentari_lab", "email_template_monthly_summary",
        )
    except Exception:
        fail("mail.template dentari_lab.email_template_monthly_summary not found")
    ok(f"mail.template registered (id={tmpl_id})")

    # 3. Verify expected fields exist on the model
    fields_info = call(
        "dental.monthly.email.wizard", "fields_get",
        [], attributes=["string", "type"],
    )
    for field in ("monthly_wizard_id", "subject", "body", "partner_ids"):
        if field not in fields_info:
            fail(f"Missing field '{field}' on dental.monthly.email.wizard")
        ok(f"Field '{field}' present ({fields_info[field]['type']})")

    # 4. Verify monthly wizard fields intact
    wizard_fields = call("dental.monthly.wizard", "fields_get", [], attributes=["string"])
    for field in ("period_year", "period_month", "preview_ids", "partner_ids"):
        if field not in wizard_fields:
            fail(f"Monthly wizard missing field '{field}'")
    ok("Monthly wizard fields intact")

    # 5. Verify email wizard view is registered
    try:
        _m, view_id = call(
            "ir.model.data", "get_object_reference",
            "dentari_lab", "view_dental_monthly_email_wizard_form",
        )
    except Exception:
        fail("View dentari_lab.view_dental_monthly_email_wizard_form not found")
    ok(f"Email wizard form view registered (id={view_id})")

    print("-" * 60)
    print("PASS  Email wizard smoke test completed successfully.")


if __name__ == "__main__":
    main()
