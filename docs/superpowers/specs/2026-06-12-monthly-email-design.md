---
title: Havi Összesítő — Email Küldés
date: 2026-06-12
status: approved
---

# Havi Összesítő — Email Küldési Funkció

## Summary

Extend the existing "Havi Összesítő" monthly summary wizard with the ability to email each partner their individual PDF summary, in addition to the existing ZIP download.

## Requirements

- One email per partner (each partner receives only their own PDF — no privacy leakage)
- A compose step: user reviews/edits subject and body before sending
- Recipients per email: the partner's email address (optional, user can remove) + the logged-in user (always added silently as a copy recipient)
- Subject and body pre-filled from a `mail.template` record, fully editable in the composer
- The existing print/ZIP download is unchanged

## Architecture

### New pieces

| Artifact | Type | Purpose |
|---|---|---|
| `dental.monthly.email.wizard` | TransientModel | Compose dialog: subject, body, partner tags |
| `data/email_templates.xml` | XML data file | `mail.template` record with default subject/body |
| View record in `wizard_monthly_views.xml` | Form view | UI for the compose dialog |
| `action_open_email_wizard()` on `dental.monthly.wizard` | Method | Opens the compose dialog pre-filled |
| `action_send()` on `dental.monthly.email.wizard` | Method | Renders PDFs and sends `mail.mail` per partner |

### Unchanged

- `action_print_summary` and ZIP generation
- `report_monthly_summary` QWeb template
- `dental.monthly.wizard.line` model

## Data Flow

1. User configures period + optional partner filter on `dental.monthly.wizard`, preview loads
2. User clicks **"Email küldése"** → `action_open_email_wizard()` fires
3. Python resolves the `mail.template`, renders subject/body against the current wizard record (substituting `period_label`, `user.name`), filters `preview_ids` to partners with a non-empty `email` field
4. Creates a `dental.monthly.email.wizard` record pre-populated with subject, body, and filtered `partner_ids`
5. Returns `target: 'new'` action opening the compose dialog
6. User edits subject/body/recipients as needed, clicks **"Küldés"**
7. `action_send()` iterates `partner_ids`:
   - Finds the matching `dental.monthly.wizard.line` for that partner
   - Renders PDF via `action_report_monthly_summary`
   - Creates `mail.mail` with `email_to` = partner email + logged-in user email (if set)
   - Attaches the PDF
   - Calls `.send()`
8. Dialog closes with a success notification

## Model: `dental.monthly.email.wizard`

```
_name = 'dental.monthly.email.wizard'
_description = 'Havi Összesítő – Email Küldés'

monthly_wizard_id  Many2one → dental.monthly.wizard  required, ondelete='cascade'
subject            Char                               required
body               Html                               required
partner_ids        Many2many → res.partner            pre-filled, user-editable
```

No line model needed. The logged-in user is not a stored field — added to each `mail.mail` at send time via `self.env.user.email`.

## Mail Template (`mail.template`)

```
name:       Havi Összesítő – Email sablon
model_id:   dental.monthly.wizard
subject:    Havi elszámolás – {{ object.period_label }}
body_html:
  Tisztelt {{ partner.name }}!

  Mellékletben küldjük a {{ object.period_label }} havi elszámolást.

  Üdvözlettel,
  {{ user.name }}
```

The template is rendered once when the compose dialog opens. Its output is stored as plain editable text in the wizard's `subject`/`body` fields. The template engine is not involved at send time.

Note: `{{ partner.name }}` in the body is a placeholder label visible in the composer — at send time Python substitutes each partner's actual name when constructing each `mail.mail`.

## View Changes

**`wizard_monthly_views.xml` — existing monthly wizard footer:**

Add after "Összesítő nyomtatása":
```xml
<button name="action_open_email_wizard" type="object"
        string="Email küldése" class="btn-secondary"/>
```

**New form view for `dental.monthly.email.wizard`:**

```xml
<form string="Email küldése">
    <group>
        <field name="subject"/>
        <field name="body" widget="html"/>
        <field name="partner_ids" widget="many2many_tags"
               options="{'no_create': True}"/>
    </group>
    <div class="text-muted small">
        A küldő minden emailhez másolatot kap.
    </div>
    <footer>
        <button name="action_send" type="object"
                string="Küldés" class="btn-primary"/>
        <button string="Mégse" class="btn-secondary" special="cancel"/>
    </footer>
</form>
```

## Security

No new access rules needed. `dental.monthly.email.wizard` is a TransientModel accessible only via the monthly wizard action, which is already restricted to `group_lab_manager`.

Add one line to `security/ir.model.access.csv`:
```
access_dental_monthly_email_wizard,dental.monthly.email.wizard,model_dental_monthly_email_wizard,dentari_lab.group_lab_manager,1,1,1,1
```

## Error Handling

| Situation | Behaviour |
|---|---|
| No partners in preview have an email | `UserError`: *"Egy megrendelőnek sincs megadva email cím."* — dialog does not open |
| Partners without email | Silently excluded from `partner_ids` pre-fill |
| User removes all partner tags, clicks Küldés | `UserError`: *"Nincs kijelölt címzett."* |
| Logged-in user has no email set | User silently omitted from recipients; send continues |
| Partner's wizard line not found (defensive) | Skip that partner, collect names, raise single `UserError` after loop listing skipped |
| PDF rendering failure | Native Odoo exception propagates (same as print button) |
| Partial send failure mid-loop | Earlier emails already sent — no rollback (standard Odoo batch email behaviour) |

## Future Compatibility

This wizard is self-contained. When the invoicing (`account.move`), CRM (`crm.lead`), or Sales (`sale.order`) modules are enabled later, they bring their own email infrastructure and do not interact with this wizard. Using `mail.template` for the default content is consistent with how those modules manage email templates.
