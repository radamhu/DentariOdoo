# Havi Összesítő — Email Küldés Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an "Email küldése" button to the Havi Összesítő wizard that opens a compose dialog (pre-filled subject/body, partner recipient tags) and sends one email per partner with their individual PDF attached.

**Architecture:** A new `dental.monthly.email.wizard` TransientModel opens as a dialog from `dental.monthly.wizard`. Default subject/body come from a `mail.template` record (Jinja2 rendered once at open time). `action_send()` iterates `partner_ids`, renders the existing QWeb PDF per partner, and sends one `mail.mail` per partner. The logged-in user is added as CC on every email.

**Tech Stack:** Odoo 18, Python, `mail.mail`, `mail.template`, `ir.attachment`, QWeb PDF rendering via `_render_qweb_pdf`, XML-RPC smoke testing.

---

## File Map

| Action | File | Responsibility |
|---|---|---|
| Modify | `dentari_lab/security/ir.model.access.csv` | Add read/write/create/unlink for `dental.monthly.email.wizard` |
| Create | `dentari_lab/data/email_templates.xml` | `mail.template` record with default subject/body |
| Modify | `dentari_lab/__manifest__.py` | Register `data/email_templates.xml` |
| Create | `dentari_lab/models/dental_monthly_email_wizard.py` | New TransientModel + `action_send()` |
| Modify | `dentari_lab/models/__init__.py` | Import new model |
| Modify | `dentari_lab/models/dental_monthly_wizard.py` | Add `action_open_email_wizard()` |
| Modify | `dentari_lab/views/wizard_monthly_views.xml` | "Email küldése" button + new compose form view |
| Create | `tests/test_monthly_email.py` | XML-RPC smoke test for the email wizard |

---

## Task 1: Security — access rule for the new model

**Files:**
- Modify: `dentari_lab/security/ir.model.access.csv`

- [ ] **Step 1: Add the access rule line**

  Open `dentari_lab/security/ir.model.access.csv` and append this line at the end:

  ```
  access_monthly_email_wizard_manager,monthly email wizard manager,model_dental_monthly_email_wizard,dentari_lab.group_lab_manager,1,1,1,1
  ```

  The file should now end with these two lines (existing + new):
  ```
  access_monthly_wizard_line_manager,monthly wizard line manager,model_dental_monthly_wizard_line,dentari_lab.group_lab_manager,1,1,1,1
  access_monthly_email_wizard_manager,monthly email wizard manager,model_dental_monthly_email_wizard,dentari_lab.group_lab_manager,1,1,1,1
  ```

- [ ] **Step 2: Commit**

  ```bash
  git add dentari_lab/security/ir.model.access.csv
  git commit -m "security: add access rule for dental.monthly.email.wizard"
  ```

---

## Task 2: Mail template data file

**Files:**
- Create: `dentari_lab/data/email_templates.xml`
- Modify: `dentari_lab/__manifest__.py`

- [ ] **Step 1: Create the template file**

  Create `dentari_lab/data/email_templates.xml`:

  ```xml
  <?xml version="1.0" encoding="utf-8"?>
  <odoo>
      <record id="email_template_monthly_summary" model="mail.template">
          <field name="name">Havi Összesítő – Email sablon</field>
          <field name="model_id" ref="dentari_lab.model_dental_monthly_wizard"/>
          <field name="subject">Havi elszámolás – {{ object.period_label }}</field>
          <field name="body_html"><![CDATA[<p>Tisztelt {partner_name}!</p>
  <p>Mellékletben küldjük a {{ object.period_label }} havi elszámolást.</p>
  <p>Üdvözlettel,<br/>{{ user.name }}</p>]]></field>
      </record>
  </odoo>
  ```

  Note on placeholders:
  - `{{ object.period_label }}` and `{{ user.name }}` → Jinja2, rendered by Odoo when the compose dialog opens
  - `{partner_name}` → literal Python-style placeholder, replaced by `action_send()` per partner at send time

- [ ] **Step 2: Register in manifest**

  In `dentari_lab/__manifest__.py`, add `'data/email_templates.xml'` to the `data` list, **before** the views (templates must load before views that reference them):

  ```python
  'data': [
      'security/groups.xml',
      'security/ir.model.access.csv',
      'security/record_rules.xml',
      'data/invoice_data.xml',
      'data/email_templates.xml',       # ← add this line
      'report/report_monthly_summary.xml',
      'views/dental_work_log_views.xml',
      'views/wizard_invoice_views.xml',
      'views/wizard_monthly_views.xml',
      'views/menus.xml',
  ],
  ```

- [ ] **Step 3: Commit**

  ```bash
  git add dentari_lab/data/email_templates.xml dentari_lab/__manifest__.py
  git commit -m "data: add mail.template for monthly summary email"
  ```

---

## Task 3: Email wizard model

**Files:**
- Create: `dentari_lab/models/dental_monthly_email_wizard.py`
- Modify: `dentari_lab/models/__init__.py`

- [ ] **Step 1: Write the failing test**

  Create `tests/test_monthly_email.py`:

  ```python
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

      print("-" * 60)
      print("PASS  Email wizard smoke test completed successfully.")


  if __name__ == "__main__":
      main()
  ```

- [ ] **Step 2: Run the test to confirm it fails**

  ```bash
  python tests/test_monthly_email.py
  ```

  Expected output: `FAIL  Model dental.monthly.email.wizard not found`

- [ ] **Step 3: Create the model file**

  Create `dentari_lab/models/dental_monthly_email_wizard.py`:

  ```python
  import base64
  import re
  import unicodedata

  from odoo import fields, models, _
  from odoo.exceptions import UserError


  class DentalMonthlyEmailWizard(models.TransientModel):
      _name = 'dental.monthly.email.wizard'
      _description = 'Havi Összesítő – Email Küldés'

      monthly_wizard_id = fields.Many2one(
          'dental.monthly.wizard',
          required=True,
          ondelete='cascade',
      )
      subject = fields.Char(required=True)
      body = fields.Html(required=True)
      partner_ids = fields.Many2many(
          'res.partner',
          string='Címzettek',
      )

      def action_send(self):
          self.ensure_one()
          if not self.partner_ids:
              raise UserError(_('Nincs kijelölt címzett.'))

          wizard = self.monthly_wizard_id
          report = self.env.ref('dentari_lab.action_report_monthly_summary')
          skipped = []

          for partner in self.partner_ids:
              line = wizard.preview_ids.filtered(lambda l: l.partner_id == partner)
              if not line:
                  skipped.append(partner.name or '?')
                  continue
              line = line[0]

              pdf_content, _ = report._render_qweb_pdf(report.id, [line.id])

              nfkd = unicodedata.normalize('NFKD', partner.name or 'partner')
              safe_name = re.sub(
                  r'[^A-Za-z0-9_\-]', '_',
                  nfkd.encode('ASCII', 'ignore').decode('ASCII'),
              )
              filename = (
                  f'Havi_Osszesito_{wizard.period_year}'
                  f'_{wizard.period_month}_{safe_name}.pdf'
              )

              attachment = self.env['ir.attachment'].create({
                  'name': filename,
                  'type': 'binary',
                  'datas': base64.b64encode(pdf_content),
                  'res_model': self._name,
                  'res_id': self.id,
              })

              body = self.body.replace('{partner_name}', partner.name or 'Megrendelő')

              mail_vals = {
                  'subject': self.subject,
                  'body_html': body,
                  'attachment_ids': [(4, attachment.id)],
              }
              if partner.email:
                  mail_vals['email_to'] = partner.email
              user_email = self.env.user.email
              if user_email:
                  mail_vals['email_cc'] = user_email

              if not mail_vals.get('email_to'):
                  skipped.append(partner.name or '?')
                  continue

              self.env['mail.mail'].create(mail_vals).send()

          if skipped:
              raise UserError(
                  _('A következő partnereknek nem sikerült elküldeni: %s')
                  % ', '.join(skipped)
              )

          return {'type': 'ir.actions.act_window_close'}
  ```

- [ ] **Step 4: Register the import in `__init__.py`**

  Open `dentari_lab/models/__init__.py` and add the import:

  ```python
  from . import dental_work_log
  from . import dental_invoice_wizard
  from . import dental_monthly_wizard
  from . import dental_monthly_email_wizard
  ```

- [ ] **Step 5: Upgrade the module**

  ```bash
  # In your Odoo shell / restart Odoo with:
  odoo -u dentari_lab -d <your_db> --stop-after-init
  ```

- [ ] **Step 6: Run the test to confirm it passes**

  ```bash
  python tests/test_monthly_email.py
  ```

  Expected output:
  ```
  OK    Login accepted (uid=2)
  OK    Model dental.monthly.email.wizard registered (id=...)
  OK    mail.template registered (id=...)
  OK    Field 'monthly_wizard_id' present (many2one)
  OK    Field 'subject' present (char)
  OK    Field 'body' present (html)
  OK    Field 'partner_ids' present (many2many)
  ---
  PASS  Email wizard smoke test completed successfully.
  ```

- [ ] **Step 7: Commit**

  ```bash
  git add dentari_lab/models/dental_monthly_email_wizard.py \
          dentari_lab/models/__init__.py \
          tests/test_monthly_email.py
  git commit -m "feat: add dental.monthly.email.wizard model with action_send"
  ```

---

## Task 4: `action_open_email_wizard()` on the monthly wizard

**Files:**
- Modify: `dentari_lab/models/dental_monthly_wizard.py`

- [ ] **Step 1: Add the method**

  In `dental_monthly_wizard.py`, add `action_open_email_wizard()` to the `DentalMonthlyWizard` class, after `action_print_summary`:

  ```python
  def action_open_email_wizard(self):
      self.ensure_one()
      partners_with_email = self.preview_ids.mapped('partner_id').filtered(
          lambda p: p.email
      )
      if not partners_with_email:
          raise UserError(_('Egy megrendelőnek sincs megadva email cím.'))

      template = self.env.ref('dentari_lab.email_template_monthly_summary')
      subject = template._render_field('subject', [self.id])[self.id]
      body = template._render_field('body_html', [self.id])[self.id]

      email_wizard = self.env['dental.monthly.email.wizard'].create({
          'monthly_wizard_id': self.id,
          'subject': subject,
          'body': body,
          'partner_ids': [(6, 0, partners_with_email.ids)],
      })
      return {
          'type': 'ir.actions.act_window',
          'res_model': 'dental.monthly.email.wizard',
          'res_id': email_wizard.id,
          'view_mode': 'form',
          'target': 'new',
      }
  ```

  Also ensure `UserError` and `_` are imported — they are already at the top of the file:
  ```python
  from odoo.exceptions import UserError
  from odoo import api, fields, models, _
  ```

- [ ] **Step 2: Upgrade the module**

  ```bash
  odoo -u dentari_lab -d <your_db> --stop-after-init
  ```

- [ ] **Step 3: Verify via XML-RPC**

  Add this block to `tests/test_monthly_email.py` inside `main()`, before the final PASS print:

  ```python
  # 4. Verify action_open_email_wizard method exists on dental.monthly.wizard
  methods = call("dental.monthly.wizard", "fields_get", [], attributes=["string"])
  # Can't list methods via RPC directly, but we can verify the model responds
  # by checking it has the expected monthly wizard fields
  wizard_fields = call("dental.monthly.wizard", "fields_get", [], attributes=["string"])
  for field in ("period_year", "period_month", "preview_ids", "partner_ids"):
      if field not in wizard_fields:
          fail(f"Monthly wizard missing field '{field}'")
  ok("Monthly wizard fields intact after modification")
  ```

  Run:
  ```bash
  python tests/test_monthly_email.py
  ```
  Expected: PASS

- [ ] **Step 4: Commit**

  ```bash
  git add dentari_lab/models/dental_monthly_wizard.py tests/test_monthly_email.py
  git commit -m "feat: add action_open_email_wizard to dental.monthly.wizard"
  ```

---

## Task 5: Views — compose form + footer button

**Files:**
- Modify: `dentari_lab/views/wizard_monthly_views.xml`

- [ ] **Step 1: Add the email wizard form view**

  In `wizard_monthly_views.xml`, add a new `<record>` after the existing `view_dental_monthly_wizard_form` record and before the `ir.actions.act_window` record:

  ```xml
  <record id="view_dental_monthly_email_wizard_form" model="ir.ui.view">
      <field name="name">dental.monthly.email.wizard.form</field>
      <field name="model">dental.monthly.email.wizard</field>
      <field name="arch" type="xml">
          <form string="Email küldése">
              <group>
                  <field name="subject" string="Tárgy"/>
                  <field name="body" widget="html" string="Levél szövege" nolabel="1"/>
                  <field name="partner_ids" widget="many2many_tags"
                         string="Címzett partnerek"
                         options="{'no_create': True}"/>
              </group>
              <div class="text-muted small ms-2">
                  A bejelentkezett felhasználó minden emailhez másolatot kap.
              </div>
              <footer>
                  <button name="action_send" type="object"
                          string="Küldés" class="btn-primary"/>
                  <button string="Mégse" class="btn-secondary" special="cancel"/>
              </footer>
          </form>
      </field>
  </record>
  ```

- [ ] **Step 2: Add "Email küldése" button to the monthly wizard footer**

  In the existing `view_dental_monthly_wizard_form` record, find the `<footer>` block:

  ```xml
  <footer>
      <button name="action_print_summary" type="object"
              string="Összesítő nyomtatása" class="btn-primary"/>
      <button name="action_query" type="object"
              string="Frissítés" class="btn-secondary"/>
      <button string="Mégse" class="btn-secondary" special="cancel"/>
  </footer>
  ```

  Replace it with:

  ```xml
  <footer>
      <button name="action_print_summary" type="object"
              string="Összesítő nyomtatása" class="btn-primary"/>
      <button name="action_open_email_wizard" type="object"
              string="Email küldése" class="btn-secondary"/>
      <button name="action_query" type="object"
              string="Frissítés" class="btn-secondary"/>
      <button string="Mégse" class="btn-secondary" special="cancel"/>
  </footer>
  ```

- [ ] **Step 3: Upgrade the module**

  ```bash
  odoo -u dentari_lab -d <your_db> --stop-after-init
  ```

- [ ] **Step 4: Verify views are registered via XML-RPC**

  Add this block to `tests/test_monthly_email.py` inside `main()` before the final PASS print:

  ```python
  # 5. Verify email wizard view is registered
  try:
      _m, view_id = call(
          "ir.model.data", "get_object_reference",
          "dentari_lab", "view_dental_monthly_email_wizard_form",
      )
  except Exception:
      fail("View dentari_lab.view_dental_monthly_email_wizard_form not found")
  ok(f"Email wizard form view registered (id={view_id})")
  ```

  Run:
  ```bash
  python tests/test_monthly_email.py
  ```
  Expected: PASS

- [ ] **Step 5: Commit**

  ```bash
  git add dentari_lab/views/wizard_monthly_views.xml tests/test_monthly_email.py
  git commit -m "feat: add email compose form view and Email küldése button"
  ```

---

## Task 6: Manual end-to-end verification

This task cannot be automated via XML-RPC (email sending requires a live mail server and UI interaction). Perform manually in the Odoo UI.

- [ ] **Step 1: Open Havi Összesítő**

  Navigate to the Dentari Lab menu → Havi Összesítő. Select a year/month that has work logs with at least one partner who has an email address set on their `res.partner` record.

- [ ] **Step 2: Verify "Email küldése" button appears**

  The wizard footer should now show three buttons: "Összesítő nyomtatása", "Email küldése", "Frissítés".

- [ ] **Step 3: Open the compose dialog**

  Click "Email küldése". Confirm:
  - Dialog opens with pre-filled subject (e.g., "Havi elszámolás – 2026. május")
  - Body is pre-filled with the template (contains `{partner_name}`, the period, and your user name)
  - Partner tags show only partners that have an email address (no email = not shown)

- [ ] **Step 4: Test the no-email-address guard**

  If you have a partner with no email, confirm they are not pre-populated in the tags. If ALL partners have no email, clicking "Email küldése" should show: `"Egy megrendelőnek sincs megadva email cím."`

- [ ] **Step 5: Test send (with outgoing mail server configured)**

  Click "Küldés". Confirm:
  - Dialog closes
  - Each partner received a separate email with their own PDF
  - The logged-in user received CC copies

- [ ] **Step 6: Test empty-recipients guard**

  Remove all tags from the partner field, click "Küldés". Expected: `"Nincs kijelölt címzett."`

- [ ] **Step 7: Verify ZIP download still works**

  Click "Összesítő nyomtatása". Confirm the ZIP download is unchanged.

- [ ] **Step 8: Final commit**

  ```bash
  git add tests/test_monthly_email.py
  git commit -m "test: add smoke test for dental.monthly.email.wizard"
  ```

---

## Self-review notes

- Task 1 adds the access rule before the model exists — Odoo will log a warning on upgrade if the model CSV line appears before the model is registered, but since `ir.model.access.csv` is loaded at install time and the model file is compiled into Python at startup, this is fine.
- The `_render_field` method on `mail.template` is the standard Odoo 16/17/18 API for rendering template fields against a record. It returns a `{res_id: value}` dict. If this method is unavailable on the installed Odoo version, fall back to reading `template.subject` and `template.body_html` as raw strings and doing a manual `.replace()` for `{{ object.period_label }}` → `self.period_label`.
- `email_cc` on `mail.mail` is a comma-separated string of email addresses. A single address works fine.
- The `{partner_name}` placeholder in the body is replaced by `self.body.replace('{partner_name}', partner.name or 'Megrendelő')` in `action_send()`. The Html field stores sanitized HTML — Odoo does not strip `{partner_name}` since it is plain text inside an HTML tag.
