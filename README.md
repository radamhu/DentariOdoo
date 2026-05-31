# DentariOdoo

> **Custom Odoo 18 module suite for dental laboratory operations.**  
> Invoice-ready, multi-clinic, audit-logged — self-hosted via Docker Compose.

---

## Overview

DentariOdoo is a custom **Odoo 18** module development project for a dental laboratory. It extends Odoo with domain-specific functionality to:

- Track daily work output (work sheets / munkalapok)
- Manage courier deliveries to dental clinics
- Produce monthly revenue reports and invoices

| Capability | How |
|------------|-----|
| Work sheet management | `dentari_lab` module — `dental.work.log` model |
| Role-based access | Lab Technician / Lab Manager security groups |
| Audit trail | `mail.thread` field-level change tracking |
| Invoicing | `account.move` bridge (M4) |
| Multi-clinic | Partner-based clinic separation |

**Current status:** M1 complete (`dentari_lab` installable), M4 invoicing bridge in progress.

---

## Docs

| Document | Purpose |
|----------|---------|
| [docs/DESIGN.md](docs/DESIGN.md) | Full system design — data model, security, views, decisions log |
| [docs/DEPLOY.md](docs/DEPLOY.md) | Infrastructure & deployment reference — Docker Compose, backups, monitoring |
| [docs/TICKET-001-dentari-lab-module.md](docs/TICKET-001-dentari-lab-module.md) | M1 acceptance criteria and Odoo 18 implementation notes |
