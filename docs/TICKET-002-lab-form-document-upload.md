# TICKET-002 — Document & Photo Upload on `dental.work.log` Form View

| Field                | Value                                         |
| -------------------- | --------------------------------------------- |
| **Type**       | Feature                                       |
| **Priority**   | Medium                                        |
| **Milestone**  | M2 — Attachments                             |
| **Assignee**   | —                                            |
| **Reporter**   | Dentari Development Team                      |
| **Created**    | 2026-05-22                                    |
| **Status**     | Open                                          |
| **Depends on** | [TICKET-001](./TICKET-001-dentari-lab-module.md) |

---

## Summary

Add a document/photo upload section to the `dental.work.log` form view. Lab technicians must be able to attach PDFs and images (including photos taken directly from a mobile phone camera) to a work log record. Images are displayed as an inline thumbnail grid within the form; other file types appear as downloadable links.

---

## Background

Lab technicians often photograph finished dental work (crowns, bridges) before dispatch. Currently there is no structured place to attach these — they go to WhatsApp or are lost. This ticket adds a native Odoo attachment field, which on mobile browsers automatically surfaces a "Take Photo / Choose from Gallery" OS picker, requiring no app or custom camera integration.

---

## Approach & Design Decisions

### Why `ir.attachment` many2many (not `image_1920` on the model)

| Option                                      | Pros                                                | Cons                                                     |
| ------------------------------------------- | --------------------------------------------------- | -------------------------------------------------------- |
| `fields.Binary` / `image_1920` on model | Single image, simple                                | One photo per record; not a gallery                      |
| `ir.attachment` many2many                 | Unlimited files, PDF + image, standard Odoo pattern | Slightly more model boilerplate                          |
| Chatter paperclip only                      | Zero code                                           | Hidden in chatter, not prominent enough for lab workflow |

**Decision:** `ir.attachment` many2many. Standard pattern, supports mixed file types, and Odoo's `many2many_binary` widget handles the upload UI including mobile camera trigger with no custom JS.

### Mobile camera — how it works

The `many2many_binary` widget renders an `<input type="file">` element. On iOS Safari and Android Chrome, tapping it presents the native OS sheet: **Take Photo**, **Photo Library**, **Browse Files**. No custom widget needed for upload. Inline image preview (thumbnail grid) requires a small custom OWL component — scoped to this ticket as Phase 2 (see Out of Scope).

### Phase delivered by this ticket (Phase 1)

- Upload button in the form (PDF, images, any file)
- Mobile camera / gallery picker works out of the box
- Files listed with name + download link
- File count stat button in the `button_box` header

Phase 2 (inline thumbnail grid) is a separate ticket.

---

## Acceptance Criteria

### AC-1 Model — `attachment_ids` field

- [ ] Add to `DentalWorkLog`:
  ```python
  attachment_ids: object = fields.Many2many(
      'ir.attachment',
      'dental_work_log_attachment_rel',
      'log_id',
      'attachment_id',
      string='Dokumentumok / Képek',
  )
  ```
- [ ] The explicit relation table name `dental_work_log_attachment_rel` and column names prevent Odoo from auto-generating a conflicting name.
- [ ] No `required=True` — attachments are optional.

### AC-2 Model — `attachment_count` computed field

- [ ] Add:
  ```python
  attachment_count: int = fields.Integer(
      compute='_compute_attachment_count',
      string='Mellékletek',
  )

  @api.depends('attachment_ids')
  def _compute_attachment_count(self):
      for rec in self:
          rec.attachment_count = len(rec.attachment_ids)
  ```

### AC-3 Form view — stat button

- [ ] Add a stat button to `<div class="oe_button_box" name="button_box">` (currently empty):
  ```xml
  <button
      name="action_open_attachments"
      type="object"
      class="oe_stat_button"
      icon="fa-paperclip">
      <field name="attachment_count" widget="statinfo" string="Melléklet"/>
  </button>
  ```
- [ ] Clicking the button opens the attachment list (see AC-6).

### AC-4 Form view — upload section

- [ ] Add a new section below the `notes` field and above the chatter:
  ```xml
  <group string="Dokumentumok / Képek">
      <field
          name="attachment_ids"
          widget="many2many_binary"
          nolabel="1"
          string="Fájl feltöltése"
      />
  </group>
  ```
- [ ] `widget="many2many_binary"` is the correct Odoo 18 widget — do **not** use `widget="many2many_tags"` (text-only) or a custom widget.
- [ ] On mobile, the file input accepts any file type; the OS presents camera and gallery options automatically.

### AC-5 Security — attachment access

- [ ] `ir.attachment` records linked via `dental_work_log_attachment_rel` must follow the same visibility rules as the parent `dental.work.log` record — Odoo enforces this automatically because `ir.attachment` access is governed by the linked record's access rights (via `res_model` / `res_id`). No additional security rules are needed.
- [ ] Confirm: Lab Technician can upload and download attachments on their own records. Lab Manager can access attachments on all records.

### AC-6 Server action — `action_open_attachments`

- [ ] Add method to `DentalWorkLog`:
  ```python
  def action_open_attachments(self):
      self.ensure_one()
      return {
          'type': 'ir.actions.act_window',
          'name': 'Mellékletek',
          'res_model': 'ir.attachment',
          'view_mode': 'list,form',
          'domain': [('id', 'in', self.attachment_ids.ids)],
          'context': {'default_res_model': self._name, 'default_res_id': self.id},
      }
  ```

### AC-7 Manifest update

- [ ] No new XML data files are required (the field and view changes are in existing files `dental_work_log.py` and `dental_work_log_views.xml`).
- [ ] Bump `version` in `__manifest__.py` from `'18.0.1.0.0'` to `'18.0.1.1.0'`.

---

## Technical Specification

### Files changed

| File                                | Change                                                                    |
| ----------------------------------- | ------------------------------------------------------------------------- |
| `models/dental_work_log.py`       | Add `attachment_ids`, `attachment_count`, `action_open_attachments` |
| `views/dental_work_log_views.xml` | Add stat button and upload section to form view                           |
| `__manifest__.py`                 | Bump version                                                              |

### Form view layout after this ticket

```
┌─────────────────────────────────────────────────┐
│  [📎 Melléklet: N]  │  [Összeg: X Ft]           │  ← button_box
├─────────────────────────────────────────────────┤
│  Dátum            │  Megrendelő                 │
├──────────────────────┬──────────────────────────┤
│ Páciens adatok       │ Munka részletei           │
│  Páciens neve        │  Fogszín                  │
│  Fogpozíció          │  Munka típusa             │
│                      │  Darabszám                │
│                      │  Egységár                 │
├─────────────────────────────────────────────────┤
│  Megjegyzések (textarea)                         │
├─────────────────────────────────────────────────┤
│  Dokumentumok / Képek                            │
│  [ Fájl feltöltése ▲ ]  file1.jpg  file2.pdf    │  ← many2many_binary
├─────────────────────────────────────────────────┤
│  Chatter                                         │
└─────────────────────────────────────────────────┘
```

### Mobile upload flow

1. Technician opens record on phone browser.
2. Taps "Fájl feltöltése" button.
3. OS sheet appears: **Fénykép készítése** / **Fotótár** / **Fájlok tallózása**.
4. Photo is taken or selected, uploaded as `ir.attachment`, linked to record.
5. File name appears in the attachment list; stat button count increments.

### Odoo 18 widget reference

| Widget name          | Behaviour                                                                                                                 |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| `many2many_binary` | File upload button + list of files with download links. Accepts all MIME types. Renders `<input type="file" multiple>`. |
| `many2many_tags`   | Tag pills (text only) —**wrong for files**                                                                         |
| `image`            | Single binary image field —**wrong for gallery**                                                                   |

---

## Out of Scope (future ticket)

- **Inline thumbnail grid** — displaying uploaded images as a visual gallery directly in the form. Requires a custom OWL widget (`FileGallery`) that iterates `attachment_ids`, filters by MIME type `image/*`, and renders `<img>` tags via `/web/image/<id>`. Deferred because it is a pure UI enhancement with no functional impact.
- PDF viewer inline (deferred).
- File size or type validation (e.g., reject files > 10 MB) — deferred, can be added as `@api.constrains` on `attachment_ids` later.
- Automatic photo compression on upload — deferred.

---

## Definition of Done

- [ ] All acceptance criteria checked.
- [ ] Module upgrades cleanly on existing Odoo 18 database (`-u dentari_lab`).
- [ ] Lab Technician can upload a JPG photo from desktop browser.
- [ ] Lab Technician on mobile (iOS Safari or Android Chrome) can take a photo with the camera and attach it to the record.
- [ ] Lab Technician can upload a PDF from desktop browser.
- [ ] Stat button shows correct count after upload.
- [ ] Lab Technician cannot see attachments on records belonging to another technician.
- [ ] Lab Manager can see all attachments.
- [ ] Code reviewed and merged to `dev` branch.
- [ ] Smoke test passes in the CI pipeline (login + create one record).
