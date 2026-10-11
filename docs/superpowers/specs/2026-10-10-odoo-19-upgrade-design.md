---
title: Odoo 18.0 → 19.0 Manual Upgrade via OpenUpgrade on an oec.sh Staging Mirror
date: 2026-10-10
status: draft
---

# Odoo 18.0 → 19.0 Manual Upgrade via OpenUpgrade on an oec.sh Staging Mirror

## Summary

Move the **Dentari** project (oec.sh project id `c271fb8c-4208-4486-bc29-5474455e8332`)
from Odoo Community 18.0 to 19.0 using the OCA **OpenUpgrade** project, executed by
hand on an isolated oec.sh **staging** environment that is a full data mirror of
`dentari-prod-3040`. Production is never touched until the staging migration is
verified end-to-end. This does not cover the **adaminfo** project — the same
playbook applies there later, as a separate pass, once this one is proven.

OpenUpgrade transforms a live database in place (schema + data) from one Odoo
series to the next; it does not touch custom addon code. The three custom addons
in this repo (`dentari_lab`, `dental_quick_expense`, `dentari_mis_reports`) and the
one OCA addon dependency (`mis_builder`, from `OCA/reporting-engine`) must be
ported to 19.0 separately, in parallel with the OpenUpgrade run.

Confirmed before writing this plan:
- `OCA/OpenUpgrade` has a `19.0` branch (`git clone -b 19.0`).
- `OCA/reporting-engine` (source of `mis_builder`) has a `19.0` branch.
- oec.sh: `odoo_version` lives on the **project**, not the environment, and
  changing it only affects environments created *after* the change
  (`oecsh_update_project`, field `odoo_version`). Existing running environments
  keep whatever version they were deployed with. So getting a 19.0 base image
  means bumping the project's `odoo_version` and then creating a **new**
  environment — not upgrading `dentari-dev-4673` or `dentari-prod-3040` in place.
- oec.sh auto-deploy is disabled org-wide ([[oecsh-autodeploy-disabled]] memory) —
  every deploy/module-update step below is an explicit `oecsh_deploy_environment`
  or `oecsh_quick_update_environment` call, never a bare `git push`.
- oec.sh's Odoo 18.0 base image is missing `pyOpenSSL` as a direct dependency
  ([[oecsh-odoo18-pyopenssl-gap]] memory) — `requirements.txt` already pins it
  explicitly for 18.0. Re-verify whether the 19.0 base image has the same gap;
  do not assume the pin is still necessary or still sufficient.
- oec.sh gives full root SSH access to the VM backing an environment. The actual
  `pg_restore` and OpenUpgrade `odoo-bin` invocation happen over that SSH session —
  no oec.sh MCP tool runs arbitrary shell commands, so this part of the work is
  manual CLI, not scriptable through `oecsh_*` tools.
- Org quota: starter plan, `max_environments: 10`, 4 currently running. One more
  staging environment fits with room to spare.

## Requirements

- **No data loss.** Staging starts from a real backup of `dentari-prod-3040`, not
  from scratch and not from demo data.
- **Staging first, always.** The OpenUpgrade run, the ported addons, and the full
  QA pass all happen on the new staging environment before any production
  environment is created or touched.
- **Rollback path kept open.** `dentari-prod-3040` (18.0) stays running and
  untouched throughout. Nothing about this plan stops or modifies it. Production
  cutover is explicitly out of scope for this plan — it is a follow-up plan,
  written after staging sign-off, because its content (maintenance window,
  downtime budget, DNS/URL cutover) depends on what the staging run finds.
- **Addon parity.** All three custom addons install cleanly on Odoo 19.0 against
  the OpenUpgrade-migrated database, with no manifest, view, or ORM API breakage.
- **Dependency parity.** `mis_builder` pin in `requirements.txt` moves to the
  `19.0` branch version; the `pyOpenSSL` pin is re-validated, not blindly kept.
- **Verifiable correctness, not just "it boots."** Post-migration, staging must
  match baseline on: per-model record counts for the three custom addons' models
  (`dental.work.log`, `dental.quick.expense`, `mis.report.instance` data), and
  the existing repo test scripts
  (`tests/smoke_dev.py`, `tests/test_mis_report.py`, `tests/test_monthly_email.py`)
  passing against the staging URL.
- **No surprise auto-deploys.** Every code push to the upgrade branch during this
  work is followed by an explicit module-update call; pushing code alone must
  never be assumed to have updated the running staging environment.

## Out of scope for this plan

- Production cutover itself (separate follow-up plan, written after this one's
  sign-off checklist passes).
- The `adaminfo` project.
- Any Odoo Enterprise migration path (this repo is Community only — no
  `odoo.sh`/Enterprise upgrade service involved).
- Re-architecting the custom addons beyond what 19.0 compatibility requires.

## Architecture

**New git branch:** `upgrade/odoo-19` off `main`. All manifest version bumps and
any 19.0 compatibility fixes land here. Never force-merged into `main` until
after production cutover succeeds.

**New oec.sh resources:**
- `Dentari` project's `odoo_version` bumped `18.0` → `19.0` via
  `oecsh_update_project` (affects future environment creates only).
- New environment, type `staging`, e.g. `dentari-upg19-stg`, branch
  `upgrade/odoo-19`, no demo data — created *after* the version bump so it gets
  a 19.0 base image.
- A fresh **manual, permanent-retention** backup of `dentari-prod-3040`
  (`oecsh_create_backup`, `notes: "pre-19.0-upgrade baseline"`) taken before
  anything else, as the untouchable rollback point and the source of staging's
  data.

**Migration mechanics (on the staging VM, over SSH):**
1. Restore the prod backup's DB dump + filestore onto the staging VM, replacing
   whatever empty/demo DB the fresh environment booted with.
2. `pip install openupgradelib` in the venv.
3. Clone `OCA/OpenUpgrade` (`-b 19.0`) onto the staging VM's addons path,
   alongside `odoo/addons` (core) and this repo's custom addons.
4. Run the 19.0 `odoo-bin` against the restored (still 18.0-shaped) database with
   `--load=base,web,openupgrade_framework --update=all --stop-after-init`. This
   is the actual schema+data transform; it reads 18.0 data and leaves a 19.0
   database behind.
5. Start Odoo 19.0 normally against that now-migrated database and verify boot.

**Verification:** per-model record-count diff (pre-restore baseline vs.
post-migration), the three `tests/*.py` smoke scripts pointed at the staging URL,
and a manual click-through of each custom addon's main flows.

## Review Focus

- OpenUpgrade's `--update=all` silently skips a custom addon that isn't on the
  addons path yet (wrong path, module not yet ported) — the migration finishes
  "successfully" but the addon's tables/fields are stale 18.0-shaped. Caught by
  the per-model record-count diff and by `tests/test_mis_report.py` actually
  exercising `mis_builder`-dependent computations, not just checking the module
  is listed as installed.
- `mis_builder` 19.0's report/KPI computation API changed in a way that produces
  different *numbers*, not an error. Caught only by comparing actual KPI values
  (not just "report renders") against a pre-migration snapshot — this is why
  `test_mis_report.py` needs to run against both the pre- and post-migration
  state and diff the numbers, not just pass/fail on install.
- `pyOpenSSL` pin removed or left stale against a 19.0 base image that handles
  the dependency differently, reproducing the exact deploy failure in
  [[oecsh-odoo18-pyopenssl-gap]] but on 19.0 — caught by a plain `oecsh_deploy_environment`
  on the new staging environment before assuming the pin is correct either way.
- Auto-deploy being disabled means a code push to `upgrade/odoo-19` after the
  initial environment create does **nothing** until a module-update step is run
  explicitly — easy to assume a push took effect when it didn't, and QA a stale
  build. Every task below pairs a push with its explicit deploy/update call.
- `dentari-prod-3040` getting touched by accident (wrong environment_id passed to
  an oec.sh write tool) — mitigated by never calling a write tool against
  `0a12797b-38d0-48a4-8fdc-78929a003fd2` (prod's environment id) anywhere in this
  plan; only the new staging environment's id is used for writes.
