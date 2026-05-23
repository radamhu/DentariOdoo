# DentariOdoo

> **Odoo 18 ERP for dental laboratory operations.**  
> Replaces a bespoke Streamlit + FastAPI stack with a production-grade, self-hosted ERP — invoice-ready, multi-clinic, audit-logged, and deployed via Docker Compose.

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Module: dentari\_lab](#module-dentari_lab)
  - [Data Model](#data-model)
  - [Security & Roles](#security--roles)
  - [UI](#ui)
- [Infrastructure Stack](#infrastructure-stack)
- [Getting Started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Development](#development)
  - [Staging](#staging)
  - [Production](#production)
- [Configuration](#configuration)
- [Backups](#backups)
- [Monitoring](#monitoring)
- [Roadmap](#roadmap)
- [Project Structure](#project-structure)
- [Docs](#docs)

---

## Overview

DentariOdoo replaces a bespoke **Streamlit + FastAPI** application used by a dental laboratory to:

- Track daily work output (work sheets / munkalapok)
- Manage courier deliveries to dental clinics
- Produce monthly revenue reports

The migration to **Odoo 18** brings:

| Before | After |
|--------|-------|
| Custom API + Streamlit UI | Odoo native web client |
| Hand-rolled auth | Role-based access, audit log |
| Ad-hoc reports | Built-in grouping, filters, future account.move invoicing |
| Single-tenant | Multi-clinic (one Compose stack per lab) |

**Current status:** Milestone 1 complete — `dentari_lab` module is fully implemented and installable.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Dental Laboratory                       │
│                                                             │
│   Lab Technician   Lab Manager      Courier                 │
│         │               │              │                    │
│         └───────────────┴──────────────┘                    │
│                          │                                   │
│               HTTPS (Traefik v3 + Let's Encrypt)            │
│                          │                                   │
│            ┌─────────────▼──────────────┐                   │
│            │       Odoo 18 Web UI        │                   │
│            │   dentari_lab module        │                   │
│            └─────────────┬──────────────┘                   │
│                          │ ORM / RPC                        │
│            ┌─────────────▼──────────────┐                   │
│            │  pgBouncer (tx pool)        │                   │
│            └─────────────┬──────────────┘                   │
│            ┌─────────────▼──────────────┐                   │
│            │     PostgreSQL 16           │                   │
│            └────────────────────────────┘                   │
│                                                             │
│   Redis (sessions)    node_exporter (metrics)               │
│   backup (pg_dump + rclone → S3)                            │
└─────────────────────────────────────────────────────────────┘
```

**Design philosophy:** Docker Compose, not Kubernetes. This workload (<50 concurrent users) does not require orchestration overhead. The real bottleneck is PostgreSQL — pgBouncer handles connection pooling so Odoo workers don't exhaust it.

---

## Module: dentari\_lab

**Module ID:** `dentari_lab`  
**Odoo version:** 18.0.1.0.0  
**Dependencies:** `base`, `mail`  
**Category:** Dental / Laboratory

```
addons/dentari_lab/
├── __manifest__.py
├── __init__.py
├── models/
│   ├── __init__.py
│   └── dental_work_log.py      # core model + business logic
├── views/
│   ├── dental_work_log_views.xml
│   └── menus.xml
├── security/
│   ├── groups.xml
│   ├── ir.model.access.csv
│   └── record_rules.xml
└── data/
```

### Data Model

Core entity: `dental.work.log` → table `dental_work_log`

| Field | Type | Notes |
|-------|------|-------|
| `date` | Date | Required, default today, indexed |
| `partner_id` | Many2one → res.partner | Clinic, required, companies only |
| `patient_name` | Char(100) | Optional |
| `tooth_position` | Char(50) | FDI notation, validated (digits/comma/dot/hyphen) |
| `tooth_color` | Selection | VITA scale — A1–A4, B1–B4, C1–C4, D2–D4, BL1–BL4 |
| `work_type` | Selection | Korona, Híd, Implant, Facet, Ideiglenes, Javítás, Monolitikus, Egyéb |
| `pieces` | Integer | Required, 1–100, default 1 |
| `price_per_piece` | Float (HUF) | Required, 0–500 000, default 5 000 Ft |
| `total_revenue` | Float (computed) | `pieces × price_per_piece`, stored |
| `notes` | Text | Optional |
| `user_id` | Many2one → res.users | Who created the entry |

**Mixins:** `mail.thread` (chatter + field tracking) · `mail.activity.mixin`  
**Tracked fields:** `date`, `partner_id`, `work_type`, `pieces`, `price_per_piece`

### Security & Roles

```
base.group_user
    └── group_lab_technician    — create/read/write own records
            └── group_lab_manager   — full CRUD on all records
```

| Permission | Lab Technician | Lab Manager |
|------------|:--------------:|:-----------:|
| Read own records | ✓ | ✓ |
| Read all records | — | ✓ |
| Create | ✓ | ✓ |
| Edit | ✓ (own) | ✓ |
| Delete | — | ✓ |

Record rule: technicians are domain-restricted to `user_id = uid`.

### UI

**Menu:**
```
Dentari Lab
├── Munkalapok     → all records, full search
└── Mai munkák     → today's records
```

**List view columns:** Date · Clinic · Patient · Work Type · Pieces · Unit Price · Total  
**Column sums** on Pieces and Total Revenue.

**Search:** predefined filters (Today / This Week / This Month), group-by (Clinic / Work Type / Date), free-text on clinic, patient, notes.

---

## Infrastructure Stack

| Layer | Component | Version |
|-------|-----------|---------|
| Application | Odoo | 18 (official image) |
| Database | PostgreSQL | 16-alpine |
| Connection pool | pgBouncer | edoburu/pgbouncer |
| Reverse proxy | Traefik | v3 (auto Let's Encrypt) |
| Session store | Redis | 7-alpine |
| Monitoring | node_exporter | latest |
| Backups | alpine + pg_dump + rclone | — |

### Environment comparison

| Parameter | Dev | Staging | Production |
|-----------|-----|---------|------------|
| Odoo workers | 2 | 4 | 8 |
| DB RAM | 512 MB | 2 GB | 8 GB |
| pgBouncer pool | — | 20 | 25 |
| SSL / Traefik | No | Yes | Yes |
| Addons mount | bind (hot-reload) | bind | read-only bind |
| pgHero | Yes (:8080) | Yes | No |

---

## Getting Started

### Prerequisites

- Docker ≥ 24 + Docker Compose v2
- `.env` file (copy from `.env.dev` for local development)

```bash
git clone <repo-url>
cd DentariOdoo
cp .env.dev .env          # review and adjust values
```

### Development

```bash
docker compose -f docker-compose.dev.yml up -d
```

- Odoo UI: http://localhost:8069
- pgHero: http://localhost:8080
- Addons are bind-mounted — changes reload without rebuilding the image.

**Scaffold a new module:**
```bash
docker compose -f docker-compose.dev.yml exec odoo \
  odoo scaffold my_module /mnt/extra-addons
```

**Odoo shell:**
```bash
docker compose -f docker-compose.dev.yml exec odoo odoo shell
```

**Enable `pg_stat_statements` for query analysis:**
```bash
docker compose -f docker-compose.dev.yml exec db \
  psql -U odoo -c "CREATE EXTENSION IF NOT EXISTS pg_stat_statements;"
```

### Staging

```bash
docker compose -f docker-compose.staging.yml pull
docker compose -f docker-compose.staging.yml up -d
```

Requires `STAGING_DOMAIN`, `DB_PASSWORD`, and `LETSENCRYPT_EMAIL` in `.env`.

### Production

```bash
# Build and push custom image
docker build -t dentariodo:$(date +%Y-%m-%d) .
docker push registry.example.com/dentariodo:$(date +%Y-%m-%d)

# Deploy
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d
```

**Rollback:**
```bash
# Update image tag in docker-compose.prod.yml to previous date tag, then:
docker compose -f docker-compose.prod.yml up -d odoo-prod
```

**View logs:**
```bash
docker compose -f docker-compose.prod.yml logs -f --tail=100 odoo-prod
```

---

## Configuration

All secrets and environment-specific values live in `.env` — never commit this file.

| Variable | Description |
|----------|-------------|
| `DB_PASSWORD` | PostgreSQL + pgBouncer password |
| `DB_NAME` | Database name (default: `dentariodo`) |
| `ODOMAIN` | Production hostname |
| `STAGING_DOMAIN` | Staging hostname |
| `LETSENCRYPT_EMAIL` | Let's Encrypt contact email |
| `RCLONE_REMOTE` | rclone remote for backups (e.g. `s3:dentariodo-backups`) |
| `INSTANCE` | Instance label used in Traefik router names |

Key files:
- `config/odoo.conf` — Odoo server settings
- `config/postgresql.conf` — PostgreSQL tuning (per environment)
- `config/pgbouncer.ini` — pgBouncer pool settings
- `config/rclone.conf` — backup remote config

---

## Backups

GFS rotation — runs automatically inside the `backup` container:

| Tier | Schedule | Retention |
|------|----------|-----------|
| Daily | 02:00 nightly | 7 days |
| Weekly | Sunday 03:00 | 4 weeks |
| Monthly | 1st of month 04:00 | 3 months |

Each backup includes a PostgreSQL dump (`pg_dump -Fc`) and the Odoo filestore (`tar czf`). Uploaded via `rclone` to any S3-compatible storage (Backblaze B2, Cloudflare R2, MinIO, DigitalOcean Spaces).

**Trigger a manual backup:**
```bash
docker compose -f docker-compose.prod.yml exec backup /backup.sh daily
```

**Restore:**
```bash
docker compose -f docker-compose.prod.yml exec db \
  pg_restore -U odoo -d dentariodo /backups/daily/backup_YYYYMMDD.dump

tar xzf /backups/daily/filestore_YYYYMMDD.tar.gz -C /var/lib/odoo/filestore/
```

> A backup that has never been restored is not a backup. Test restores monthly.

---

## Monitoring

| Metric | Tool | Alert threshold |
|--------|------|----------------|
| PostgreSQL slow queries (>500 ms) | pgHero / pg_stat_statements | >5 in 5 min |
| PostgreSQL connections | pgHero | >80% of max_connections |
| HTTP response time | Traefik metrics / Prometheus | P95 > 2 s |
| Disk usage | node_exporter | >80% |
| Memory usage | node_exporter | >90% for 5 min |
| Backup success | Cron exit code | Any non-zero exit |
| SSL certificate expiry | Traefik auto-renewal | <7 days |

node_exporter runs in `network_mode: host` and exposes metrics for Prometheus scraping.

---

## Roadmap

| Milestone | Scope | Status |
|-----------|-------|--------|
| **M1 — Work Log CRUD** | `dental.work.log` model, form/list/search views, security groups, record rules | **Done** |
| **M2 — Statistics & Import** | Dashboard KPIs (today/week/month), Excel/CSV import wizard with Hungarian column mapping | Planned |
| **M3 — Courier Module** | Delivery assignment model, route tracking, courier-facing view | Planned |
| **M4 — Invoicing Bridge** | Generate `account.move` draft invoices from grouped work logs | Planned |
| **M5 — PDF Reports** | Monthly lab report, per-client breakdown, Pareto analysis | Planned |

---

## Project Structure

```
DentariOdoo/
├── README.md
├── addons/
│   └── dentari_lab/            # custom Odoo module (M1)
├── config/
│   ├── odoo.conf
│   ├── postgresql.conf
│   ├── pgbouncer.ini
│   └── rclone.conf
├── scripts/
│   ├── backup.sh
│   ├── restore.sh
│   └── deploy.sh
├── docker-compose.dev.yml
├── docker-compose.staging.yml
├── docker-compose.prod.yml
├── Dockerfile
├── .env.dev                    # template — copy to .env
└── docs/
    ├── DESIGN.md               # full system design document
    ├── DEPLOY.md               # infrastructure & deployment reference
    └── TICKET-001-dentari-lab-module.md
```

---

## Docs

| Document | Purpose |
|----------|---------|
| [docs/DESIGN.md](docs/DESIGN.md) | Full system design — data model, security, views, infrastructure, decisions log |
| [docs/DEPLOY.md](docs/DEPLOY.md) | Infrastructure deep-dive — Docker Compose configs, PostgreSQL tuning, backup strategy, CI/CD pipeline |
| [docs/TICKET-001-dentari-lab-module.md](docs/TICKET-001-dentari-lab-module.md) | M1 acceptance criteria and Odoo 18 implementation notes |
