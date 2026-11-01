# DentariOdoo

Odoo 18 addon suite for a dental lab. Each top-level folder is one addon; repo root is the `addons_path`.

## Layout

- `dentari_lab/` work sheets (`dental.work.log`), monthly invoicing + email digest
- `dental_quick_expense/` expense wizard over Vendor Bills
- `dentari_mis_reports/` Kiadás/Bevétel report on OCA `mis_builder`
- `dentari_invoice_archive/` szamlazz.hu invoices archived as draft `account.move`
- Tests live per module in `<module>/tests/`
- `docs/superpowers/{specs,plans}/` design specs and implementation plans
- `scripts/` helper/spike scripts
- `.agents/`, `SKILL.md`, `skills-lock.json` vendored odoo-development-skill, don't edit

## Build / test / deploy

- No local Odoo. Tests run inside an Odoo instance on oec.sh (dev env).
- `pip install -r requirements.txt` first (pyOpenSSL, `odoo-addon-mis-builder`). Skipping breaks deploy.
- Deploys are manual. Push to `main`/`develop` does NOT deploy. Trigger deploy via the `oecsh` MCP tools, then run module upgrade/install for what changed.
- Branches: `develop` and `main`, kept in sync.
- Quick syntax check: `python3 -m py_compile <file>`.

## Don'ts

- Never commit `.env.*` (real keys, e.g. `SZAMLAZZ_AGENT_KEY`). Only `.env.example` is tracked.
- Don't hardcode secrets. szamlazz agent key is the `dentari_invoice_archive.szamlazz_agent_key` system parameter.
- Follow OCA conventions and the odoo-development-skill; check Odoo version (18) before applying patterns.
- Conventional Commits.
