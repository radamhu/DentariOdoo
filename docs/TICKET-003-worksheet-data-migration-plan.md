# TICKET-003: Work Sheet Data Migration Plan
## Dentari PostgreSQL → DentariOdoo

**Scope:** `dental_work_log` table only (Work Sheet page data)
**Source:** Dentari — Streamlit + FastAPI + PostgreSQL
**Target:** DentariOdoo — Odoo 18 addon (`dentari_lab`)
**Direction:** One-way, one-time historical import

---

## 1. Overview

The migration moves all historical dental work log entries from the Dentari
PostgreSQL database into the Odoo `dental.work.log` model. No other tables are
in scope for this ticket.

**What moves:**
- All rows in `dental_work_log`

**What does NOT move:**
- `daily_routes`, `archived_routes` — different domain, separate ticket
- Users, clinics — pre-requisite setup, handled outside this ticket
- Attachments — none exist in source

---

## 2. Source Schema

**Table:** `dental_work_log` (PostgreSQL)

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `id` | INTEGER PK | NO | Source record ID |
| `date` | VARCHAR | NO | ISO string `YYYY-MM-DD` |
| `client_name` | VARCHAR | NO | Free-text clinic name |
| `patient_name` | VARCHAR | YES | |
| `tooth_position` | VARCHAR | YES | FDI notation |
| `tooth_color` | VARCHAR | YES | VITA color string |
| `work_type` | VARCHAR | YES | Free-text work category |
| `pieces` | INTEGER | NO | Default 1 |
| `price_per_piece` | FLOAT | NO | HUF |
| `total_revenue` | FLOAT | COMPUTED | pieces × price_per_piece |
| `notes` | TEXT | YES | |
| `created_by` | INTEGER FK→users | YES | SET NULL on delete |
| `created_at` | VARCHAR | NO | ISO datetime string |
| `updated_at` | VARCHAR | NO | ISO datetime string |

---

## 3. Target Schema

**Model:** `dental.work.log` (Odoo 18, addon `dentari_lab`)
**DB table:** `dental_work_log` (Odoo-managed)

| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | Integer | auto | Odoo sequence |
| `name` | Char (computed) | — | `{date} / {partner.name}` |
| `date` | Date | YES | |
| `partner_id` | Many2one → res.partner | YES | Must be `is_company=True` |
| `patient_name` | Char (100) | NO | |
| `tooth_position` | Char (50) | NO | Only `[0-9,.\-]` |
| `tooth_color` | Selection | NO | VITA scale values |
| `work_type` | Selection | NO | Predefined keys |
| `pieces` | Integer | YES | 1–100 |
| `price_per_piece` | Float | YES | 0–500,000 |
| `total_revenue` | Float (computed) | — | Read-only |
| `notes` | Text | NO | |
| `user_id` | Many2one → res.users | NO | Defaults to current user |

---

## 4. Field Mapping

### 4.1 Direct / Trivial Mappings

| Source | Target | Transform |
|---|---|---|
| `date` (string) | `date` | `datetime.strptime(val, '%Y-%m-%d').date()` |
| `patient_name` | `patient_name` | copy as-is, truncate to 100 chars |
| `tooth_position` | `tooth_position` | copy as-is, truncate to 50 chars |
| `pieces` | `pieces` | copy as-is |
| `price_per_piece` | `price_per_piece` | copy as-is (round to integer, `digits=(10,0)`) |
| `notes` | `notes` | copy as-is |
| `total_revenue` | — | skip — Odoo recomputes automatically |

### 4.2 Lookup / Resolution Mappings

#### `client_name` → `partner_id`

The source stores a free-text clinic name. Odoo requires a `res.partner` record
with `is_company=True`.

Resolution strategy (in order):
1. Exact match on `res.partner.name` (case-insensitive)
2. Fuzzy match (Levenshtein distance ≤ 2) — **human review required**
3. No match → create new `res.partner` record (company) during migration

Pre-migration step: run the audit query below, export unique `client_name`
values, and manually confirm the mapping table before the migration script runs.

```sql
-- Extract unique client names from source
SELECT DISTINCT client_name, COUNT(*) AS record_count
FROM dental_work_log
GROUP BY client_name
ORDER BY record_count DESC;
```

#### `created_by` (users.id) → `user_id` (res.users)

The source `created_by` is an integer FK to the local `users` table.

Resolution strategy:
1. Join source `users` table on `id` to get `username` / `email`
2. Match against `res.users.login` (email) or `res.users.name`
3. If no match → set `user_id` to the migration service account

Pre-migration step: run the user mapping audit below.

```sql
-- Source users linked to work logs
SELECT DISTINCT u.id, u.username, u.email, u.name, COUNT(w.id) AS log_count
FROM users u
JOIN dental_work_log w ON w.created_by = u.id
GROUP BY u.id, u.username, u.email, u.name
ORDER BY log_count DESC;
```

### 4.3 Value Transformation Mappings

#### `work_type` (free-text → Selection key)

| Source value (examples) | Target key |
|---|---|
| `Korona`, `korona`, `KORONA` | `korona` |
| `Híd`, `hid`, `HÍD` | `hid` |
| `Implant`, `implant` | `implant` |
| `Facet`, `facet` | `facet` |
| `Ideiglenes`, `ideiglenes` | `ideiglenes` |
| `Javítás`, `javitas`, `javítás` | `javitas` |
| `Monolitikus`, `monolitikus` | `monolitikus` |
| *(anything else)* | `egyeb` |
| `NULL` / empty | `NULL` (field not required) |

Normalization: lowercase + strip accents + strip whitespace, then match.

#### `tooth_color` (string → Selection key)

VITA selection values in target: `A1 A2 A3 A3.5 A4 B1 B2 B3 B4 C1 C2 C3 C4 D2 D3 D4 BL1 BL2 BL3 BL4`

| Source value | Target key | Notes |
|---|---|---|
| Exact VITA code (e.g., `A2`) | same value | direct match |
| `A3,5` (comma decimal) | `A3.5` | normalize decimal separator |
| Unrecognized value | `NULL` | log warning, store original in `notes` |
| `NULL` / empty | `NULL` | |

---

## 5. Data Quality Audit (Pre-Migration)

Run these queries against the source PostgreSQL database **before** writing any
migration scripts. Fix or document findings before proceeding.

```sql
-- 5.1 Row count baseline
SELECT COUNT(*) AS total_rows FROM dental_work_log;

-- 5.2 Date range of data
SELECT MIN(date) AS earliest, MAX(date) AS latest FROM dental_work_log;

-- 5.3 NULL / empty required fields
SELECT
    SUM(CASE WHEN date IS NULL OR date = '' THEN 1 ELSE 0 END)         AS null_date,
    SUM(CASE WHEN client_name IS NULL OR client_name = '' THEN 1 ELSE 0 END) AS null_client,
    SUM(CASE WHEN pieces IS NULL THEN 1 ELSE 0 END)                    AS null_pieces,
    SUM(CASE WHEN price_per_piece IS NULL THEN 1 ELSE 0 END)           AS null_price
FROM dental_work_log;

-- 5.4 Pieces out of Odoo range (1-100)
SELECT id, pieces FROM dental_work_log WHERE pieces < 1 OR pieces > 100;

-- 5.5 Price out of Odoo range (0-500000)
SELECT id, price_per_piece FROM dental_work_log
WHERE price_per_piece < 0 OR price_per_piece > 500000;

-- 5.6 Invalid tooth_position characters (must match [0-9,.\-])
SELECT id, tooth_position FROM dental_work_log
WHERE tooth_position IS NOT NULL
  AND tooth_position !~ '^[0-9,.\-]+$';

-- 5.7 Unknown work_type values
SELECT work_type, COUNT(*) AS cnt FROM dental_work_log
GROUP BY work_type ORDER BY cnt DESC;

-- 5.8 Unknown tooth_color values
SELECT tooth_color, COUNT(*) AS cnt FROM dental_work_log
GROUP BY tooth_color ORDER BY cnt DESC;

-- 5.9 client_name uniqueness
SELECT DISTINCT client_name FROM dental_work_log ORDER BY client_name;

-- 5.10 Records with NULL created_by (orphaned)
SELECT COUNT(*) FROM dental_work_log WHERE created_by IS NULL;
```

Document all anomalies found. Decide per-anomaly: fix in source, transform in
script, or skip row.

---

## 6. Pre-Migration Prerequisites

These must be completed **before** the migration script runs:

| # | Task | Owner | Notes |
|---|---|---|---|
| P1 | All source clinics exist as `res.partner` (companies) in Odoo | Admin | Use client_name list from §5 |
| P2 | All source users mapped to `res.users` in Odoo | Admin | Use user audit from §4.2 |
| P3 | Migration service account created in Odoo | Admin | Used for unmapped `created_by` |
| P4 | Odoo `dentari_lab` addon installed and `dental.work.log` accessible | Admin | |
| P5 | Full PostgreSQL backup taken | Admin | Before any read |
| P6 | Odoo database snapshot taken | Admin | Before migration run |
| P7 | Data quality audit completed (§5) and anomalies documented | Dev | |
| P8 | `client_name → partner_id` mapping table approved | Business | See §4.2 |

---

## 7. Migration Script Design

### 7.1 Technology

- Language: Python 3.11+
- Source access: `psycopg2` directly against source PostgreSQL
- Target access: Odoo XML-RPC (`xmlrpc.client`) — no direct DB writes
- Script location (suggested): `docs/cutover_artifacts/migrate_worksheet.py`

### 7.2 Script Structure

```
migrate_worksheet.py
├── config        — DB URLs, Odoo URL/credentials from env vars
├── extract()     — SELECT all rows from dental_work_log
├── transform()   — apply all mappings from §4
│   ├── resolve_partner(client_name) → partner_id
│   ├── resolve_user(created_by)     → user_id
│   ├── map_work_type(val)           → selection key or None
│   └── map_tooth_color(val)         → selection key or None
├── validate()    — enforce Odoo constraints before write
└── load()        — create records via Odoo XML-RPC in batches
```

### 7.3 Batch Loading

- Batch size: 100 records per `execute_kw` call (`model_create_multi`)
- On error: log row ID + error message, continue with next batch
- Progress: print running totals every 500 records

### 7.4 Environment Variables Required

```bash
SRC_DB_URL=postgresql://user:pass@host:5432/dentari_db
ODOO_URL=http://192.168.0.9:8069
ODOO_DB=dentari_odoo
ODOO_USER=admin
ODOO_PASSWORD=...
ODOO_MIGRATION_USER_ID=...  # fallback res.users.id for unmapped users
```

### 7.5 Idempotency

The script does not delete existing Odoo records. If re-run:
- Duplicate records will be created unless guarded
- Guard: before each batch, search Odoo for existing records with same
  `date` + `partner_id` + `pieces` + `price_per_piece` + `patient_name` —
  skip if found

---

## 8. Field-Level Transform Logic (Pseudocode)

```python
WORK_TYPE_MAP = {
    'korona': 'korona', 'híd': 'hid', 'hid': 'hid',
    'implant': 'implant', 'facet': 'facet',
    'ideiglenes': 'ideiglenes', 'javítás': 'javitas', 'javitas': 'javitas',
    'monolitikus': 'monolitikus',
}
VALID_VITA = {
    'A1','A2','A3','A3.5','A4','B1','B2','B3','B4',
    'C1','C2','C3','C4','D2','D3','D4','BL1','BL2','BL3','BL4',
}

def transform_row(row, partner_map, user_map, fallback_user_id):
    notes = row['notes'] or ''

    # tooth_color
    color_raw = (row['tooth_color'] or '').strip().replace(',', '.')
    tooth_color = color_raw if color_raw in VALID_VITA else None
    if color_raw and not tooth_color:
        notes = f"[migráció] fogszín: {color_raw}\n" + notes

    # work_type
    wt_raw = (row['work_type'] or '').strip().lower()
    wt_raw = unicodedata.normalize('NFD', wt_raw).encode('ascii', 'ignore').decode()
    work_type = WORK_TYPE_MAP.get(wt_raw) or ('egyeb' if wt_raw else None)

    return {
        'date': row['date'],                         # already YYYY-MM-DD
        'partner_id': partner_map[row['client_name']],
        'patient_name': (row['patient_name'] or '')[:100] or False,
        'tooth_position': (row['tooth_position'] or '')[:50] or False,
        'tooth_color': tooth_color or False,
        'work_type': work_type or False,
        'pieces': row['pieces'],
        'price_per_piece': round(row['price_per_piece']),
        'notes': notes.strip() or False,
        'user_id': user_map.get(row['created_by'], fallback_user_id),
    }
```

---

## 9. Rollback Plan

| Situation | Rollback Action |
|---|---|
| Migration aborted mid-run | Restore Odoo DB from pre-migration snapshot (§P6) |
| Migration completed with errors | Review error log; restore snapshot if error rate > 5% |
| Wrong data loaded | Restore Odoo DB snapshot; fix script; re-run |
| Source data untouched | No rollback needed — source is read-only |

The source PostgreSQL database is **never modified** by this migration.

---

## 10. Validation (Post-Migration)

Run after migration completes.

### 10.1 Row Count Check

```sql
-- Source count
SELECT COUNT(*) FROM dental_work_log;
```

```python
# Odoo count via XML-RPC
odoo.execute_kw('dental.work.log', 'search_count', [[]])
```

Expected: counts match (minus intentionally skipped rows).

### 10.2 Revenue Spot-Check

Pick 10 random source records. Verify in Odoo:
- `total_revenue == pieces × price_per_piece`
- `partner_id.name` matches source `client_name`
- `date` is correct

### 10.3 Work Type Coverage

```python
# All work_type values in Odoo after migration
odoo.execute_kw('dental.work.log', 'read_group',
    [[]], ['work_type'], ['work_type'])
```

Confirm no unexpected `egyeb` spikes (would indicate mapping gaps).

### 10.4 Null Partner Check

```python
# Should return 0 — partner_id is required in Odoo
odoo.execute_kw('dental.work.log', 'search_count',
    [[('partner_id', '=', False)]])
```

---

## 11. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| `client_name` does not match any `res.partner` | High | High | Run §5.9 audit; create partners in P1 |
| `work_type` free-text has unlisted values | Medium | Low | Map to `egyeb`; review post-migration |
| `tooth_color` has non-VITA values | Low | Low | Preserve original in `notes` |
| `pieces` > 100 (Odoo constraint violation) | Low | Medium | Identify in §5.4; clamp or skip |
| `price_per_piece` > 500,000 (constraint) | Low | Medium | Identify in §5.5; review before run |
| Odoo XML-RPC timeout on large batch | Medium | Low | Reduce batch size to 50; add retry |
| Duplicate records if script re-run | Medium | Medium | Idempotency guard in §7.5 |

---

## 12. Deliverables

| # | Artifact | Status |
|---|---|---|
| D1 | This migration plan | Done |
| D2 | Data quality audit results (from §5) | TODO |
| D3 | `client_name → partner_id` mapping table | TODO |
| D4 | `users → res.users` mapping table | TODO |
| D5 | Migration script `migrate_worksheet.py` | TODO |
| D6 | Post-migration validation report | TODO |

---

## 13. Execution Order Summary

```
1. Run data quality audit (§5)           → document findings
2. Fix anomalies in source or plan transforms
3. Complete prerequisites P1–P8 (§6)
4. Test script on Odoo staging environment
5. Take Odoo production snapshot
6. Run migration script against production Odoo
7. Run post-migration validation (§10)
8. Business sign-off on spot-check results
9. Decommission source data access (separate ticket)
```

---

*Plan version: 1.0 — 2026-05-23*
*Author: migration planning session*
