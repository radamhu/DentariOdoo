# Testing Strategy — DentariOdoo

Odoo 18, `dentari_lab` custom module.

---

## Overview

Three testing tiers, ordered by cost and coverage:

| Tier | Tool | When to run | What it catches |
|------|------|-------------|-----------------|
| **Smoke** | `tests/smoke_dev.py` (Python + XML-RPC) | After any deploy | Login broken, model missing, DB down |
| **Unit** | Odoo test runner (`--test-enable`) | Pre-merge / CI | Field logic, constraints, computed fields |
| **Manual / E2E** | Browser | Before UAT sign-off | UI flows, view regressions |

---

## Smoke Tests

### `tests/smoke_dev.py`

Targets the **development** environment (`https://dentari-dev-8780.apps.oec.sh`).

**What it tests:**
1. XML-RPC login with admin credentials
2. Creates one `dental.work.log` record (with a real company partner)
3. Reads it back and asserts `pieces` and `total_revenue`
4. Deletes the record (cleanup)

**How to run:**
```bash
# From the repo root — credentials loaded automatically from .env.dev
python tests/smoke_dev.py
```

**Override credentials inline:**
```bash
ODOO_URL=https://... ODOO_DATABASE=... ODOO_USERNAME=admin ODOO_PASSWORD=... \
  python tests/smoke_dev.py
```

**Expected output:**
```
Target: https://dentari-dev-8780.apps.oec.sh  db=1a918a02...  user=admin
------------------------------------------------------------
OK    Login accepted  (uid=2)
OK    Partner found   (id=7, name='...')
OK    Record created  (id=42)
OK    Record verified (name='2026-05-23 / ...', total=5000 Ft)
OK    Record deleted  (id=42)
------------------------------------------------------------
PASS  Smoke test completed successfully.
```

**Exit codes:** `0` = pass, `1` = fail (message printed to stderr).

**Dependencies:** Python standard library only (`xmlrpc.client`). No pip install needed.

---

## Unit Tests (Odoo Test Runner)

Odoo's built-in test runner via `--test-enable` flag.

**File location:** `dentari_lab/tests/` (to be created as the module grows).

**Run against dev Docker container:**
```bash
docker compose exec odoo odoo \
  -d dentariodo_dev \
  --test-enable \
  --stop-after-init \
  -i dentari_lab
```

**What to cover per model:**
- Required field constraints (`ValidationError` raised for invalid input)
- Computed field values (`_compute_total_revenue`, `_compute_name`)
- `_check_pieces` / `_check_price` / `_check_tooth_position` constraint methods
- `create` / `write` / `unlink` basic CRUD

**Naming convention:** `dentari_lab/tests/test_dental_work_log.py`

---

## Manual / E2E Checklist

Run in-browser before any UAT sign-off or production deploy.

| Area | Steps | Pass criteria |
|------|-------|---------------|
| Login | Log in as admin | Dashboard loads, no error |
| Create work log | Dentari Lab → New → fill all fields → Save | Record appears in list, `name` computed correctly |
| Constraint check | Set pieces = 0 → Save | ValidationError shown |
| Constraint check | Set tooth_position = `abc!` → Save | ValidationError shown |
| Attachment upload | Open record → upload a PDF | Attachment count increments |
| Access control | Log in as lab user → try to open Admin menu | Blocked / hidden |

---

## Environment Matrix

| Environment | URL | Credentials |
|-------------|-----|-------------|
| Dev (oec.sh) | `https://dentari-dev-8780.apps.oec.sh` | `.env.dev` |
| Production | TBD | `.env.prod` (never commit) |

Credentials are stored in `.env.dev` (git-ignored). Never commit passwords.

---

## CI Integration

Add to the deployment workflow after a successful container start:

```yaml
- name: Smoke test
  run: python tests/smoke_dev.py
  env:
    ODOO_URL: ${{ secrets.DEV_ODOO_URL }}
    ODOO_DATABASE: ${{ secrets.DEV_ODOO_DATABASE }}
    ODOO_USERNAME: admin
    ODOO_PASSWORD: ${{ secrets.DEV_ODOO_PASSWORD }}
```

A non-zero exit code fails the deployment job before any production promote.

---

## When Tests Are Not Enough

Odoo XML-RPC smoke tests do **not** cover:

- UI rendering (views, widgets, OWL components)
- Access rights edge cases (record rules, field-level security)
- Cron job execution
- Report rendering (QWeb PDF)
- Performance / N+1 queries

For those, use the manual checklist or Odoo's internal `--test-enable` suite with `tagged` decorators.
