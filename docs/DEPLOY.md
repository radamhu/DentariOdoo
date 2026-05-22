# AGENTS.md — DentariOdoo

> Odoo ERP for dental clinics. Docker Compose, not Kubernetes.

---

## Philosophy

> "You probably don't need Kubernetes for Odoo." — Parthiv Patel

**Docker Compose** gives us container isolation, reproducible builds, and zero-downtime deploys. A single well-configured server outruns an overbuilt Kubernetes cluster for Odoo workloads with <50 concurrent users. The **real bottleneck is PostgreSQL**, not compute orchestration.

We don't solve problems we don't have. No Helm, no ArgoCD, no K8s. Docker Compose + Traefik + pgBouncer + cron backup scripts.

---

## Infrastructure Components

| Component | Role | Tech |
|-----------|------|------|
| **Odoo** | ERP application (one container per instance) | `odoo:18` official image |
| **PostgreSQL** | Primary datastore | `postgres:16-alpine` |
| **pgBouncer** | Connection pooling (mandatory) | `edoburu/pgbouncer` |
| **Traefik** | Reverse proxy, SSL termination, routing | `traefik:v3` |
| **Redis** | Odoo session store & async jobs queue | `redis:7-alpine` |
| **SMTP Relay** | Outbound mail delivery | `namshi/smtp` or external |
| **Cron Backups** | DB + filestore automated backups | Bash + `pg_dump` + `rclone` |
| **Watchtower** | Optional auto-update of containers | `containrrr/watchtower` |

### Key design decisions

- **No Kubernetes.** Not even for staging or production. Docker Compose covers everything this project needs.
- **Always pgBouncer.** Odoo opens many connections. Without pooling, PostgreSQL chokes at ~20 workers.
- **Traefik over nginx.** Automatic Let's Encrypt, Docker-native labels, zero-config routing.
- **Filestore on named volume or bind mount.** Never inside the container. Backed up alongside the DB.
- **Redis for sessions.** Odoo's file-based session store doesn't scale across restarts.

---

## Environment Parameters

### Development

Target: 1 developer, 1 instance, local machine.

```yaml
# docker-compose.dev.yml

services:
  odoo:
    image: odoo:18
    cpu_limit: "2"
    mem_limit: "2g"
    ports:
      - "8069:8069"
    environment:
      - WORKERS=2
      - MAX_CRON_THREADS=1
      - LIMIT_MEMORY_SOFT=1g
      - LIMIT_MEMORY_HARD=2g
      - LIMIT_TIME_CPU=600
      - LIMIT_TIME_REAL=1200
      - ODOO_SESSION_REDIS=true
      - ODOO_SESSION_REDIS_HOST=redis
      - ODOO_SESSION_REDIS_PORT=6379
    volumes:
      - ./addons:/mnt/extra-addons
      - odoo-filestore:/var/lib/odoo
      - ./config/odoo.conf:/etc/odoo/odoo.conf

  db:
    image: postgres:16-alpine
    cpu_limit: "1"
    mem_limit: "512m"
    environment:
      POSTGRES_DB: dentariodo_dev
      POSTGRES_USER: odoo
      POSTGRES_PASSWORD: odoo_dev
    volumes:
      - db-dev:/var/lib/postgresql/data

  pghero:
    image: ankane/pghero
    ports:
      - "8080:8080"
    environment:
      DATABASE_URL: postgres://odoo:odoo_dev@db:5432/dentariodo_dev

  redis:
    image: redis:7-alpine
    cpu_limit: "0.5"
    mem_limit: "256m"
    volumes:
      - redis-dev:/data
```

**PostgreSQL tuning (dev):**
```
shared_buffers = 128MB
work_mem = 16MB
effective_cache_size = 384MB
random_page_cost = 1.1
max_connections = 30
```

**Development notes:**
- Source code mounted via bind mount for hot-reload (`--dev all` flag on odoo entrypoint).
- `--dev all` enables reload, debug, workers, and tests.
- pgHero included for query analysis during development.
- No SSL/Traefik needed locally.
- Addon scaffold: `python odoo-bin scaffold <module_name> addons/`

---

### Staging

Target: 1 server, 2-3 instances (UAT per client), HTTPS enabled.

```yaml
# docker-compose.staging.yml

services:
  traefik:
    image: traefik:v3
    cpu_limit: "0.5"
    mem_limit: "256m"
    command:
      - "--providers.docker=true"
      - "--providers.docker.exposedByDefault=false"
      - "--entrypoints.web.address=:80"
      - "--entrypoints.websecure.address=:443"
      - "--certificatesresolvers.letsencrypt.acme.tlschallenge=true"
      - "--certificatesresolvers.letsencrypt.acme.email=${LETSENCRYPT_EMAIL}"
      - "--certificatesresolvers.letsencrypt.acme.storage=/letsencrypt/acme.json"
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - traefik-certs:/letsencrypt

  odoo-staging:
    image: odoo:18
    cpu_limit: "2"
    mem_limit: "2g"
    environment:
      - WORKERS=4
      - MAX_CRON_THREADS=2
      - LIMIT_MEMORY_SOFT=2g
      - LIMIT_MEMORY_HARD=3g
      - LIMIT_TIME_CPU=600
      - LIMIT_TIME_REAL=1200
      - ODOO_SESSION_REDIS=true
      - ODOO_SESSION_REDIS_HOST=redis
      - ODOO_SESSION_REDIS_PORT=6379
    volumes:
      - ./addons:/mnt/extra-addons
      - odoo-staging-filestore:/var/lib/odoo
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.odoo-staging.rule=Host(`${STAGING_DOMAIN}`)"
      - "traefik.http.routers.odoo-staging.entrypoints=websecure"
      - "traefik.http.routers.odoo-staging.tls.certresolver=letsencrypt"

  pgbouncer:
    image: edoburu/pgbouncer
    cpu_limit: "0.5"
    mem_limit: "256m"
    environment:
      DB_HOST: db
      DB_USER: odoo
      DB_PASSWORD: ${DB_PASSWORD}
      POOL_MODE: transaction
      DEFAULT_POOL_SIZE: 20
      MAX_CLIENT_CONN: 100

  db:
    image: postgres:16-alpine
    cpu_limit: "2"
    mem_limit: "2g"
    environment:
      POSTGRES_DB: dentariodo_staging
      POSTGRES_USER: odoo
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - db-staging:/var/lib/postgresql/data
      - ./config/postgresql.conf:/etc/postgresql/postgresql.conf

  redis:
    image: redis:7-alpine
    cpu_limit: "0.5"
    mem_limit: "512m"
    volumes:
      - redis-staging:/data

  backups:
    image: alpine
    cpu_limit: "0.5"
    mem_limit: "256m"
    volumes:
      - db-staging:/tmp/db:ro
      - odoo-staging-filestore:/tmp/filestore:ro
      - ./backups:/backups
    entrypoint: |
      /bin/sh -c "
      apk add --no-cache postgresql-client rclone &&
      echo '0 2 * * * /backup.sh daily' > /etc/crontabs/root &&
      crond -f
      "
```

**PostgreSQL tuning (staging):**
```
shared_buffers = 512MB
work_mem = 64MB
effective_cache_size = 1.5GB
random_page_cost = 1.1
max_connections = 20
```

**Staging server spec:**
| Resource | Value |
|----------|-------|
| Provider | Hetzner CX22 or equivalent |
| vCPU | 2-4 |
| RAM | 4 GB |
| SSD | 40 GB |
| OS | Ubuntu 22.04 LTS |
| Cost | ~$8-15/month |

---

### Production

Target: 1 server, 5-10 instances, business-critical workload.

```yaml
# docker-compose.prod.yml

services:
  traefik:
    image: traefik:v3
    cpu_limit: "1"
    mem_limit: "512m"
    restart: always
    command:
      - "--providers.docker=true"
      - "--providers.docker.exposedByDefault=false"
      - "--entrypoints.web.address=:80"
      - "--entrypoints.websecure.address=:443"
      - "--entrypoints.websecure.http.tls.certresolver=letsencrypt"
      - "--certificatesresolvers.letsencrypt.acme.tlschallenge=true"
      - "--certificatesresolvers.letsencrypt.acme.email=${LETSENCRYPT_EMAIL:-ops@dentariodo.local}"
      - "--certificatesresolvers.letsencrypt.acme.storage=/letsencrypt/acme.json"
      - "--metrics.prometheus=true"
      - "--api.dashboard=false"
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - traefik-certs:/letsencrypt
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"

  odoo-prod:
    image: odoo:18
    cpu_limit: "4"
    mem_limit: "4g"
    restart: always
    environment:
      - WORKERS=8
      - MAX_CRON_THREADS=2
      - LIMIT_MEMORY_SOFT=3g
      - LIMIT_MEMORY_HARD=4g
      - LIMIT_TIME_CPU=600
      - LIMIT_TIME_REAL=1200
      - DB_FILTER=${DB_NAME:-dentariodo}
      - ODOO_SESSION_REDIS=true
      - ODOO_SESSION_REDIS_HOST=redis
      - ODOO_SESSION_REDIS_PORT=6379
      - ODOO_SESSION_REDIS_DB=0
      - PROXY_MODE=true
      - WITHOUT_DEMO=True
    volumes:
      - ./addons:/mnt/extra-addons:ro
      - odoo-prod-filestore:/var/lib/odoo
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.${INSTANCE}-odoo.rule=Host(`${ODOMAIN:-erp.dentariodo.local}`)"
      - "traefik.http.routers.${INSTANCE}-odoo.entrypoints=websecure"
      - "traefik.http.routers.${INSTANCE}-odoo.tls.certresolver=letsencrypt"
      - "traefik.http.services.${INSTANCE}-odoo.loadbalancer.server.port=8069"
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "5"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8069/web/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  pgbouncer:
    image: edoburu/pgbouncer
    cpu_limit: "1"
    mem_limit: "512m"
    restart: always
    environment:
      DB_HOST: db
      DB_USER: odoo
      DB_PASSWORD: ${DB_PASSWORD}
      POOL_MODE: transaction
      DEFAULT_POOL_SIZE: 25
      MAX_CLIENT_CONN: 200
      ADMIN_USERS: postgres,odoo
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"

  db:
    image: postgres:16-alpine
    cpu_limit: "4"
    mem_limit: "8g"
    restart: always
    environment:
      POSTGRES_DB: ${DB_NAME:-dentariodo}
      POSTGRES_USER: odoo
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - db-prod:/var/lib/postgresql/data
      - ./config/postgresql.conf:/etc/postgresql/postgresql.conf:ro
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "5"
    healthcheck:
      test: ["CMD", "pg_isready", "-U", "odoo"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    cpu_limit: "1"
    mem_limit: "1g"
    restart: always
    command: redis-server --appendonly yes --maxmemory 512mb --maxmemory-policy allkeys-lru
    volumes:
      - redis-prod:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 3s
      retries: 5

  backup:
    image: alpine:3.20
    cpu_limit: "0.5"
    mem_limit: "512m"
    restart: always
    environment:
      DB_HOST: db
      DB_USER: odoo
      DB_PASSWORD: ${DB_PASSWORD}
      DB_NAME: ${DB_NAME:-dentariodo}
      BACKUP_RETENTION_DAYS: 7
      BACKUP_RETENTION_WEEKS: 4
      BACKUP_RETENTION_MONTHS: 3
      RCLONE_REMOTE: ${RCLONE_REMOTE:-s3:dentariodo-backups}
    volumes:
      - db-prod:/tmp/db:ro
      - odoo-prod-filestore:/tmp/filestore:ro
      - ./scripts/backup.sh:/backup.sh:ro
      - ./config/rclone.conf:/root/.config/rclone/rclone.conf:ro
    entrypoint: |
      /bin/sh -c '
      apk add --no-cache postgresql17-client rclone bash &&
      echo "0 2 * * * /backup.sh daily"  > /etc/crontabs/root &&
      echo "0 3 * * 0 /backup.sh weekly" >> /etc/crontabs/root &&
      echo "0 4 1 * * /backup.sh monthly" >> /etc/crontabs/root &&
      crond -f -l 2
      '

  nodeexporter:
    image: prom/node-exporter
    restart: always
    pid: host
    network_mode: host
    volumes:
      - /proc:/host/proc:ro
      - /sys:/host/sys:ro
      - /:/rootfs:ro
    command:
      - "--path.procfs=/host/proc"
      - "--path.sysfs=/host/sys"
      - "--collector.filesystem.mount-points-exclude=^/(sys|proc|dev|host|etc)($$|/)"
```

**PostgreSQL tuning (production):**
```
shared_buffers = 2GB                  # 25% of DB RAM (8 GB total)
work_mem = 128MB                      # per-operation sort memory
maintenance_work_mem = 512MB
effective_cache_size = 6GB            # 75% of available RAM
random_page_cost = 1.1                # SSD
effective_io_concurrency = 200        # SSD
wal_buffers = 64MB
min_wal_size = 1GB
max_wal_size = 4GB
max_worker_processes = 4
max_parallel_workers_per_gather = 2
max_parallel_workers = 4
max_parallel_maintenance_workers = 2
default_statistics_target = 100
autovacuum_max_workers = 3
autovacuum_naptime = 30s
max_connections = 10                  # pgBouncer handles the rest
```

**Production server spec:**
| Resource | Tier 1 (light) | Tier 2 (standard) | Tier 3 (heavy) |
|----------|-----------|----------------|-----------|
| Provider | Hetzner CX32 | Hetzner CX42 | Dedicated / AWS t3.xlarge |
| vCPU | 4 | 8 | 16 |
| RAM | 8 GB | 16 GB | 32 GB |
| SSD | 80 GB | 160 GB | 320 GB + filestore volume |
| OS | Ubuntu 22.04 LTS | Ubuntu 22.04 LTS | Ubuntu 22.04 LTS |
| Instances | 1-3 | 4-7 | 8-15 |
| Cost | ~$25/month | ~$50/month | ~$100-150/month |

---

## PostgreSQL: The Real Bottleneck

### pgBouncer is mandatory

Odoo opens one PostgreSQL connection per worker. At 8 workers × 3 instances, that's 24 direct connections hitting a database with `max_connections=10`. Without pgBouncer, either:
- You set `max_connections` high and PostgreSQL memory balloons.
- You set it low and Odoo fails to connect.

**Fix:** pgBouncer in `transaction` pool mode. Every Odoo connection goes through it. 8 workers → 3 actual DB connections.

### pgHero for query analysis

```bash
docker compose exec db psql -U odoo -c "CREATE EXTENSION pg_stat_statements;"
```

Run pgHero on staging to catch slow queries before production. Odoo's ORM generates a lot of them — missing indexes on custom models, `search_read` on unindexed fields, and N+1 queries in computed fields are the most common.

### Read replicas for reports

If a client runs heavy reports (inventory valuation, P&L, aged receivables), point those report queries at a read replica. Set `ODOO_REPORT_DB = replica_host` in environment.

---

## Backup Strategy

**GFS rotation** (Grandfather-Father-Son):

| Type | Frequency | Retention |
|------|-----------|-----------|
| Daily | Every night at 2 AM | 7 days |
| Weekly | Sunday at 3 AM | 4 weeks |
| Monthly | 1st of month at 4 AM | 3 months |

**What gets backed up:**
1. PostgreSQL dump: `pg_dump -Fc -U odoo dentariodo > backup_$(date +%Y%m%d).dump`
2. Filestore: `tar czf filestore_$(date +%Y%m%d).tar.gz /var/lib/odoo/filestore`

**Storage providers** (via rclone):
- S3-compatible (Backblaze B2, Cloudflare R2, MinIO, DigitalOcean Spaces) — recommended
- SFTP to a remote server
- Local (mounted to a separate volume — minimum viable)

**Restore test schedule:** Monthly. A backup that has never been restored is not a backup.

```bash
# restore example
docker compose exec db pg_restore -U odoo -d dentariodo /backups/daily/backup_20250201.dump
tar xzf /backups/daily/filestore_20250201.tar.gz -C /var/lib/odoo/filestore/
```

---

## Deployment Workflow

### Git-driven CI/CD (no Kubernetes ceremony)

```
git push origin main → webhook → docker compose pull && docker compose up -d
```

**Step by step:**

1. **Develop** on a feature branch. Test locally with `docker compose -f docker-compose.dev.yml up`.
2. **PR to `main`** triggers a test build on CI (GitHub Actions / GitLab CI).
3. **Merge to `main`** triggers:
   - Build custom Odoo image with addons baked in: `docker build -t dentariodo:latest .`
   - Push image to registry: `docker push registry.example.com/dentariodo:latest`
   - SSH into staging server: `docker compose -f docker-compose.staging.yml pull && docker compose -f docker-compose.staging.yml up -d`
4. **Smoke tests** on staging: log in, run a report, check slow query log.
5. **Deploy to production:** tag the image (`dentariodo:2025-02-01`), pull on prod server, restart. Keep the previous image tag for instant rollback.

**Rollback:**
```bash
docker compose stop odoo
# update image tag in docker-compose.prod.yml to previous version
docker compose -f docker-compose.prod.yml up -d odoo
```

No Helm. No ArgoCD. No `kubectl rollout undo`. Just docker compose.

---

## Monitoring

| Metric | Tool | Alert threshold |
|--------|------|----------------|
| PostgreSQL slow queries (>500ms) | pgHero / pg_stat_statements | >5 in 5 minutes |
| PostgreSQL connection count | pgHero | >80% of max_connections |
| Odoo HTTP response time | Traefik metrics / Prometheus | P95 > 2s |
| Disk usage (filestore + DB) | node_exporter | >80% |
| Memory usage | node_exporter | >90% for 5 min |
| Backup success | Cron exit code | Any non-zero exit |
| SSL certificate expiry | Traefik auto-renewal | <7 days |

---

## Security Checklist

- [ ] All traffic goes through Traefik with HTTPS only (HTTP → 301 redirect)
- [ ] PostgreSQL not exposed to any network interface (`127.0.0.1` only or Docker internal network)
- [ ] pgBouncer auth_file uses bcrypt/scram-sha-256 (not md5)
- [ ] Environment variables in `.env` file, never committed to git
- [ ] `W/server_environment` module or `ir.config_parameter` for secrets (not hardcoded)
- [ ] SSH root login disabled; key-only auth on the server
- [ ] UFW firewall: only 80, 443, and SSH port open
- [ ] Fail2ban on SSH
- [ ] Automatic security updates: `unattended-upgrades` on Ubuntu
- [ ] Docker socket protected (rootless mode or access-controlled)
- [ ] Backup encryption: `rclone crypt` remote or `gpg` before upload

---

## Directory Structure

```
DentariOdoo/
├── AGENTS.md                  # This file
├── README.md
├── docker-compose.dev.yml
├── docker-compose.staging.yml
├── docker-compose.prod.yml
├── .env.example
├── Dockerfile                 # Custom Odoo image with addons
├── addons/                    # Custom Odoo modules
│   ├── dentari_erp/
│   ├── dentari_appointments/
│   └── ...
├── config/
│   ├── odoo.conf
│   ├── postgresql.conf
│   ├── pgbouncer.ini
│   └── rclone.conf
├── scripts/
│   ├── backup.sh
│   ├── restore.sh
│   ├── deploy.sh
│   └── entrypoint.sh
├── tests/
│   └── ...
└── .github/
    └── workflows/
        └── deploy.yml
```

---

## Quick Reference: Ports

| Service | Internal Port | Exposed | Notes |
|---------|--------------|---------|-------|
| Odoo | 8069 | Dev only | Production: only via Traefik |
| PostgreSQL | 5432 | Never | Internal Docker network only |
| pgBouncer | 6432 | Never | Odoo connects here, not directly to PG |
| Traefik HTTP | 80 | Always | Redirects to 443 |
| Traefik HTTPS | 443 | Always | TLS via Let's Encrypt |
| Redis | 6379 | Never | Internal Docker network only |
| pgHero | 8080 | Staging | Query analysis dashboard |

---

## Commands Cheat Sheet

```bash
# Development
docker compose -f docker-compose.dev.yml up -d
docker compose -f docker-compose.dev.yml logs -f odoo
docker compose -f docker-compose.dev.yml exec odoo odoo scaffold my_module /mnt/extra-addons

# Staging deploy
docker compose -f docker-compose.staging.yml pull
docker compose -f docker-compose.staging.yml up -d

# Production deploy
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d

# View logs
docker compose -f docker-compose.prod.yml logs -f --tail=100 odoo

# Backup manually
docker compose -f docker-compose.prod.yml exec backup /backup.sh daily

# Restore
docker compose -f docker-compose.prod.yml exec db pg_restore -U odoo -d dentariodo /path/to/backup.dump

# Database shell
docker compose -f docker-compose.prod.yml exec pgbouncer sh -c "psql -h db -U odoo dentariodo"

# Check slow queries
docker compose -f docker-compose.prod.yml exec db psql -U odoo -c "
  SELECT query, calls, mean_exec_time
  FROM pg_stat_statements
  WHERE mean_exec_time > 500
  ORDER BY mean_exec_time DESC
  LIMIT 10;
"

# Odoo shell
docker compose exec odoo odoo shell
```
