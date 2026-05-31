# DentariOdoo — Infrastructure & Deployment Reference

**Project:** DentariOdoo  
**Last updated:** 2026-05-31

---

## Table of Contents

- [Architecture](#architecture)
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
