# Odoo 18.0 → 19.0 Upgrade (Staging) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate a full data mirror of `dentari-prod-3040` (Odoo 18.0) to Odoo
19.0 on a new oec.sh staging environment, using OCA OpenUpgrade for the
schema/data transform and manual porting of the three custom addons, until a
signed-off staging environment proves the upgrade is safe to take to
production. Production cutover itself is a separate follow-up plan.

**Architecture:** New branch `upgrade/odoo-19` off `main`. Bump the `Dentari`
oec.sh project's `odoo_version` to `19.0`, then create one new `staging`
environment on that branch (new environments pick up the project's current
`odoo_version`; existing ones don't change). Restore a fresh prod backup onto
that environment's VM over SSH, run `OCA/OpenUpgrade` (`19.0` branch) +
`openupgradelib` against it to transform the database in place, then boot
Odoo 19.0 against the migrated DB with the ported custom addons.

**Tech Stack:** Odoo 19.0 Community, PostgreSQL, OCA OpenUpgrade (`19.0`
branch), `openupgradelib`, oec.sh (MCP tools for project/environment/backup
ops, root SSH for the actual migration run), `mis_builder` (`OCA/reporting-engine`,
`19.0` branch).

**Spec:** [docs/superpowers/specs/2026-10-10-odoo-19-upgrade-design.md](../specs/2026-10-10-odoo-19-upgrade-design.md)

## Global Constraints

- Production environment id `0a12797b-38d0-48a4-8fdc-78929a003fd2`
  (`dentari-prod-3040`) is **never** passed to a write-type `oecsh_*` tool
  anywhere in this plan. Read-only calls against it are fine.
- oec.sh auto-deploy is disabled org-wide — a `git push` alone never updates a
  running environment. Every code change to `upgrade/odoo-19` is followed by an
  explicit `oecsh_deploy_environment` or `oecsh_quick_update_environment` call.
- `oecsh_update_project`'s `odoo_version` field only affects environments
  created *after* the change — order matters: bump the project, then create
  the staging environment, not the other way round.
- Project id: `c271fb8c-4208-4486-bc29-5474455e8332`. Server id:
  `1bf4ace1-9eea-4da9-a6b0-8497f6877c9a`.
- The actual `pg_restore` and `odoo-bin` OpenUpgrade invocation run over root
  SSH on the staging VM — no `oecsh_*` tool executes arbitrary shell commands.
  Steps that say "SSH in" are manual CLI, documented here as exact commands to
  run, not something an agent can call through MCP.
- Module names stay `dental_quick_expense`, `dentari_lab`, `dentari_mis_reports`.
  Version strings bump from `18.0.x.y.z` to `19.0.x.y.z` (reset `x.y.z` to
  `1.0.0` per OCA convention for a new series — do not try to preserve the old
  18.0 patch number into the new series).
- `requirements.txt`'s `mis_builder` pin moves from
  `odoo-addon-mis-builder==18.0.1.10.0.1` to whatever `19.0` branch version
  `OCA/reporting-engine` publishes — look up the real version at Task 6 time,
  don't guess it now.
- Nothing in this plan deletes or expires the pre-upgrade baseline backup
  (`retention_type: permanent`).

## Review Focus

- OpenUpgrade's `--update=all` can finish with exit code 0 while silently
  leaving a custom addon's data 18.0-shaped if that addon wasn't on the addons
  path at migration time — covered by Task 8's per-model record-count diff.
- `mis_builder` 19.0 changing KPI computation semantics without erroring —
  covered by Task 8's before/after KPI value diff, not just a "report renders"
  check.
- The 19.0 base image reproducing (or not) the 18.0 `pyOpenSSL` dependency gap
  — covered by Task 7's plain deploy-and-watch-the-log step, done before
  assuming the existing pin is still correct.
- A push to `upgrade/odoo-19` being mistaken for a live update on staging
  because auto-deploy used to work on older environments — covered by every
  task that touches code pairing the push with an explicit deploy/update call
  and checking the resulting task status.
- Restoring the backup onto staging silently restoring into the *wrong*
  Postgres database name (oec.sh assigns a DB name per environment, not
  necessarily `odoo_production`) — covered by Task 3's explicit check of the
  staging environment's actual DB name before running `pg_restore`.

---

### Task 1: Baseline backup and upgrade branch

**Files:**
- Modify: none yet (branch creation + a backup, no code changes).

**Interfaces:**
- Produces: the backup id and its `notes` string, referenced by Task 9's
  rollback section; the branch name `upgrade/odoo-19`, used by every later task.

- [ ] **Step 1: Take the pre-upgrade baseline backup of production**

Call `oecsh_create_backup` with:
```json
{
  "environment_id": "0a12797b-38d0-48a4-8fdc-78929a003fd2",
  "include_filestore": true,
  "retention_type": "permanent",
  "notes": "pre-19.0-upgrade baseline — do not expire, do not restore over prod"
}
```
Follow the returned `task_id` with `oecsh_wait_for_task` until `status` is
`completed`.

- [ ] **Step 2: Verify the backup**

Call `oecsh_list_backups` with `environment_id: "0a12797b-38d0-48a4-8fdc-78929a003fd2"`.
Expected: the new backup appears first, `status: "completed"`, `backup_type: "manual"`,
with a non-zero `size` field for both DB and filestore.

- [ ] **Step 3: Create the upgrade branch**

```bash
cd /Users/ferko/development/DentariOdoo
git checkout main
git pull origin main
git checkout -b upgrade/odoo-19
git push -u origin upgrade/odoo-19
```

- [ ] **Step 4: Commit nothing yet — this task has no code change**

No commit here; Task 1 only produces the backup and the branch. Proceed to
Task 2.

---

### Task 2: Bump project Odoo version and create the staging environment

**Files:**
- None (oec.sh resource changes only).

**Interfaces:**
- Consumes: branch `upgrade/odoo-19` from Task 1.
- Produces: the new staging environment's `environment_id`, referenced by
  every remaining task as `<STAGING_ENV_ID>`.

- [ ] **Step 1: Bump the project's Odoo version**

Call `oecsh_update_project`:
```json
{
  "project_id": "c271fb8c-4208-4486-bc29-5474455e8332",
  "odoo_version": "19.0"
}
```
Expected: response confirms `odoo_version: "19.0"`. This does **not** touch
`dentari-prod-3040` or `dentari-dev-4673` — confirm by calling
`oecsh_get_environment` on both afterward and checking `odoo_version` is
unchanged (still `"18.0"`).

- [ ] **Step 2: Create the staging environment**

Call `oecsh_create_environment`:
```json
{
  "project_id": "c271fb8c-4208-4486-bc29-5474455e8332",
  "name": "dentari-upg19-stg",
  "branch": "upgrade/odoo-19",
  "environment_type": "staging",
  "with_demo_data": false,
  "cpu_cores": 2,
  "ram_mb": 2048,
  "disk_gb": 10
}
```
(Sizing matches current prod — adjust if prod has grown since this plan was
written.) Follow the returned task with `oecsh_wait_for_task` until
`completed`. Record the environment's `id` as `<STAGING_ENV_ID>`.

- [ ] **Step 3: Verify it came up on 19.0**

Call `oecsh_get_environment` with `<STAGING_ENV_ID>`. Expected: `status: "running"`,
`odoo_version: "19.0"`, `branch: "upgrade/odoo-19"`.

- [ ] **Step 4: Note the SSH target**

Record the staging environment's host/connection details from the oec.sh
dashboard (the MCP tools don't expose raw SSH connection strings). This is
needed for every SSH step from Task 3 onward.

---

### Task 3: Restore the production mirror onto staging

**Files:**
- None (data operation on the staging VM).

**Interfaces:**
- Consumes: `<STAGING_ENV_ID>` from Task 2, the baseline backup from Task 1.

- [ ] **Step 1: Download the baseline backup**

Call `oecsh_get_backup` with the backup id from Task 1 to get its current
download/reference info. Pull the DB dump and filestore archive to a local
machine or directly onto the staging VM (whichever the oec.sh backup storage
supports — check the `oecsh_get_backup` response for a direct URL first).

- [ ] **Step 2: SSH into the staging VM and confirm the real DB name**

```bash
ssh root@<staging-host>
sudo -u postgres psql -l
```
Expected: one database matching the staging environment (its name is
oec.sh-assigned, not necessarily `odoo_production` — note the exact name,
call it `<STAGING_DB>` below). Do **not** assume it matches the oec.sh guide's
example name.

- [ ] **Step 3: Stop Odoo on staging before restoring**

```bash
sudo systemctl stop odoo
```

- [ ] **Step 4: Restore the DB dump**

```bash
sudo -u postgres dropdb <STAGING_DB>
sudo -u postgres createdb <STAGING_DB>
sudo -u postgres pg_restore -d <STAGING_DB> --no-owner /path/to/production_backup.dump
```

- [ ] **Step 5: Restore the filestore**

```bash
sudo tar -xzf /path/to/filestore_backup.tar.gz -C /opt/odoo/.local/share/Odoo/filestore/
sudo chown -R odoo:odoo /opt/odoo/.local/share/Odoo/filestore/
```
(Adjust the filestore path to whatever oec.sh's 19.0 base image actually uses
— confirm with `find / -iname "filestore" -maxdepth 6 2>/dev/null` on the VM
before assuming the 18.0-era path still applies.)

- [ ] **Step 6: Do not start Odoo yet**

Leave `odoo` stopped. The database is now an 18.0-shaped database sitting
under what is otherwise a 19.0 install — starting Odoo normally here would be
wrong (mismatched code/schema). Task 5 runs the actual migration first.

---

### Task 4: Install OpenUpgrade and openupgradelib on staging

**Files:**
- None (VM-level install, not repo code).

**Interfaces:**
- Consumes: SSH access to the staging VM from Task 2/3.

- [ ] **Step 1: Install openupgradelib**

```bash
ssh root@<staging-host>
source /opt/odoo/venv/bin/activate   # adjust to the actual venv path on the 19.0 image
pip install openupgradelib
```

- [ ] **Step 2: Clone OpenUpgrade 19.0**

```bash
cd /opt/odoo/addons-extra   # adjust to wherever the 19.0 image expects extra addons
git clone https://github.com/OCA/OpenUpgrade.git -b 19.0 openupgrade
```

- [ ] **Step 3: Confirm the addons path includes OpenUpgrade**

```bash
grep addons_path /etc/odoo/odoo.conf
```
Expected: the printed `addons_path` includes the `openupgrade` clone's
directory alongside the existing custom-addons path and core `odoo/addons`.
If it doesn't, add it and save the config file before continuing.

- [ ] **Step 4: Nothing to commit — VM-level step**

---

### Task 5: Run the OpenUpgrade migration

**Files:**
- None (one-shot migration run against the restored database).

**Interfaces:**
- Consumes: `<STAGING_DB>` restored in Task 3, OpenUpgrade installed in Task 4.
- Produces: `<STAGING_DB>` transformed in place to a 19.0-shaped schema —
  every later task reads/writes this same database.

- [ ] **Step 1: Run the migration**

```bash
sudo -u odoo /opt/odoo/venv/bin/python /opt/odoo/odoo-bin \
  -d <STAGING_DB> \
  --addons-path=/opt/odoo/addons-extra/openupgrade,/opt/odoo/custom-addons,/opt/odoo/odoo/addons \
  --load=base,web,openupgrade_framework \
  --update=all \
  --stop-after-init \
  2>&1 | tee /tmp/openupgrade-run.log
```
(Adjust `--addons-path` to the real paths from Task 4 Step 3's `odoo.conf`.)

- [ ] **Step 2: Check the log for errors**

```bash
grep -iE "error|traceback|critical" /tmp/openupgrade-run.log
```
Expected: no matches, or only known/expected warnings. Any traceback here
means the migration did not complete cleanly — stop and diagnose before
proceeding; do not start Odoo against a half-migrated database.

- [ ] **Step 3: Confirm the DB reports itself as 19.0**

```bash
sudo -u postgres psql -d <STAGING_DB> -c "SELECT latest_version FROM ir_module_module WHERE name='base';"
```
Expected: a `19.0.x.y.z` version string.

---

### Task 6: Port the custom addons to 19.0

**Files:**
- Modify: `dental_quick_expense/__manifest__.py`
- Modify: `dentari_lab/__manifest__.py`
- Modify: `dentari_mis_reports/__manifest__.py`
- Modify: `requirements.txt`

**Interfaces:**
- Produces: the ported addon code that Task 7 deploys and Task 8 verifies.

- [ ] **Step 1: Look up the real `mis_builder` 19.0 version**

```bash
curl -sS "https://api.github.com/repos/OCA/reporting-engine/contents/setup/mis_builder?ref=19.0" \
  | grep -i version
```
Or check `OCA/reporting-engine`'s `19.0` branch `mis_builder/__manifest__.py`
directly. Use the exact version string found, not a guess.

- [ ] **Step 2: Update `requirements.txt`**

Change:
```
odoo-addon-mis-builder==18.0.1.10.0.1
```
to the 19.0 version found in Step 1, e.g.:
```
odoo-addon-mis-builder==19.0.1.0.0
```
Re-read the `pyOpenSSL` pin's comment in the same file — it documents a known
18.0 base-image gap. Leave the pin in place for now; Task 7 Step 2 is the
actual test of whether it's still needed on 19.0. Don't remove it speculatively.

- [ ] **Step 3: Bump manifest versions**

In each of `dental_quick_expense/__manifest__.py`, `dentari_lab/__manifest__.py`,
`dentari_mis_reports/__manifest__.py`, change:
```python
'version': '18.0.1.0.0',   # or 18.0.1.3.0 for dentari_lab
```
to:
```python
'version': '19.0.1.0.0',
```

- [ ] **Step 4: Check for Odoo 19.0 API breakage**

None of the three addons ship JS/OWL assets (confirmed: no `static/` dirs), so
the surface area is Python ORM + QWeb/XML views only. For each addon:
```bash
grep -rn "tree\b" dentari_lab/views dental_quick_expense/views dentari_mis_reports 2>/dev/null
```
`<tree>` view tags were already renamed to `<list>` in the 17.0/18.0 era, so
this should return nothing — if it does, fix those view tags now. Also check
for any use of API removed by 19.0 (consult the official Odoo 19.0 "New
features" / changelog for Python API removals) — at the time this plan was
written, this repo's addons use only `account`, `mail`, `digest`, `mis_builder`
as dependencies, all stable, high-traffic OCA/core modules unlikely to have
breaking renames, but this must be verified against the actual 19.0 changelog,
not assumed.

- [ ] **Step 5: Commit**

```bash
git add dental_quick_expense/__manifest__.py dentari_lab/__manifest__.py \
  dentari_mis_reports/__manifest__.py requirements.txt
git commit -m "chore: port custom addons and mis_builder pin to Odoo 19.0

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
git push
```

---

### Task 7: Deploy the ported addons to staging and verify boot

**Files:**
- None (deploy operation; code already committed in Task 6).

**Interfaces:**
- Consumes: `<STAGING_ENV_ID>` from Task 2, the migrated `<STAGING_DB>` from
  Task 5, the ported code from Task 6.

- [ ] **Step 1: Start Odoo on staging against the migrated DB**

```bash
ssh root@<staging-host>
sudo systemctl start odoo
sudo systemctl status odoo
```
Expected: `active (running)`, no immediate crash-loop.

- [ ] **Step 2: Deploy the Task 6 commit and upgrade all three custom modules**

Call `oecsh_deploy_environment`:
```json
{
  "environment_id": "<STAGING_ENV_ID>",
  "update_modules": ["dentari_lab", "dental_quick_expense", "dentari_mis_reports"]
}
```
Follow with `oecsh_wait_for_task` until `completed`.

- [ ] **Step 3: Check the runtime log for the pyOpenSSL gap and any other dependency error**

Call `oecsh_get_runtime_logs` with `<STAGING_ENV_ID>`.
Expected: no `ModuleNotFoundError`, no `No module named`. If the `pyOpenSSL`
gap reproduces on 19.0, it's already pinned in `requirements.txt` from Task 6
— if it still fails, the 19.0 base image needs a different fix than 18.0 did;
diagnose from the actual traceback, don't reapply the 18.0 fix blind.

- [ ] **Step 4: Confirm all three modules show as installed**

```bash
sudo -u postgres psql -d <STAGING_DB> -c \
  "SELECT name, state, latest_version FROM ir_module_module WHERE name IN ('dentari_lab','dental_quick_expense','dentari_mis_reports');"
```
Expected: all three `state = 'installed'`, `latest_version` starting `19.0.`.

---

### Task 8: Verify data integrity and functional correctness

**Files:**
- Modify: `.env.dev` is not touched — point test scripts at staging via a
  temporary local override instead, so the repo's dev config stays untouched.

**Interfaces:**
- Consumes: the staging environment's URL and admin credentials (same admin
  login as prod, since this is a data mirror).

- [ ] **Step 1: Snapshot pre-migration counts from the baseline backup**

Before this task can mean anything, you need the *pre-migration* counts to
diff against. If not already captured when Task 1's backup was taken, restore
that backup to a disposable scratch DB (or query the still-running
`dentari-prod-3040` directly, read-only, via its own admin UI/XML-RPC) for:
```sql
SELECT count(*) FROM dental_work_log;
SELECT count(*) FROM dental_quick_expense;
SELECT count(*) FROM mis_report_instance;
```
Record these three numbers.

- [ ] **Step 2: Compare against staging's post-migration counts**

```bash
sudo -u postgres psql -d <STAGING_DB> -c \
  "SELECT count(*) FROM dental_work_log;"
sudo -u postgres psql -d <STAGING_DB> -c \
  "SELECT count(*) FROM dental_quick_expense;"
sudo -u postgres psql -d <STAGING_DB> -c \
  "SELECT count(*) FROM mis_report_instance;"
```
Expected: every count matches Step 1 exactly. A mismatch means Task 5's
migration or Task 7's module upgrade dropped or duplicated rows — stop and
diagnose before continuing; do not proceed to a prod cutover plan with this
unresolved.

- [ ] **Step 3: Run the repo's smoke tests against staging**

```bash
cd /Users/ferko/development/DentariOdoo
ODOO_URL=https://<staging-url> \
ODOO_DB=<STAGING_DB> \
python tests/smoke_dev.py
python tests/test_mis_report.py
python tests/test_monthly_email.py
```
(Check each script's actual env-var names in its `load_env`/credential-loading
code before running — override whatever `.env.dev` would otherwise supply,
pointed at the staging URL/DB instead of the dev environment.)
Expected: all three print `PASS` / exit 0.

- [ ] **Step 4: Diff MIS report KPI values, not just "it renders"**

Open the MIS report on staging (Kiadás/Bevétel rolling report) for a period
that also exists in the pre-migration backup. Compare the actual KPI numbers
(net expense, net revenue, profitability) against the same period viewed on
`dentari-prod-3040` (read-only — just open the UI, no writes). Expected:
numbers match exactly. A silent mismatch here is the `mis_builder` 19.0
semantics-change risk flagged in the spec's Review Focus — catch it here, not
after prod cutover.

- [ ] **Step 5: Manual click-through of each custom addon's primary flow**

- `dentari_lab`: create a `dental.work.log` entry, run the monthly invoice
  wizard, confirm the digest view still renders.
- `dental_quick_expense`: create a quick expense, confirm it posts a vendor
  bill correctly.
- `dentari_mis_reports`: open the rolling 12-month report, confirm the
  colorized Kiadás/Bevétel rows and date-range labels (from the recent commits
  `1702225` and `72bf925`) still render correctly on 19.0's updated web client.

---

### Task 9: Sign-off and handoff to the production-cutover plan

**Files:**
- Create: nothing yet — Step 2 below only *names* the follow-up plan file; it
  is written separately, after sign-off, since its content depends on what
  this plan's QA pass found.

**Interfaces:**
- Consumes: every prior task's pass/fail result.

- [ ] **Step 1: Compile the sign-off checklist**

Confirm, in writing (e.g. a comment on the tracking ticket, or a short note
appended to this plan file): Task 5 migration log clean, Task 7 all three
modules installed on 19.0, Task 8 record counts match exactly, all three
smoke tests pass, MIS KPI numbers match, manual click-through clean. Any
unresolved item blocks moving to a production-cutover plan.

- [ ] **Step 2: Leave the staging environment running**

Do not delete `dentari-upg19-stg` after sign-off — it stays as the reference
environment for writing the production-cutover plan (maintenance window,
downtime budget, DNS/URL cutover, rollback-to-18.0 window), which is written
as its own plan once this one is fully signed off, not as a task here.

- [ ] **Step 3: Commit the sign-off note**

```bash
cd /Users/ferko/development/DentariOdoo
git add docs/superpowers/plans/2026-10-10-odoo-19-upgrade.md
git commit -m "docs: record Odoo 19.0 staging upgrade sign-off

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
git push
```
