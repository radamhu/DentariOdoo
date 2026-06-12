# DentariOdoo — Project Analysis & Budgeting Document

**Date:** June 2, 2026  
**Project:** DentariOdoo — Dental Laboratory ERP System  
**Version:** 1.0  
**Author:** Development Team  
**Status:** Draft  

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Project Overview](#project-overview)
3. [Current Development Status](#current-development-status)
4. [Technical Scope Analysis](#technical-scope-analysis)
5. [Resource Requirements](#resource-requirements)
6. [Hungarian Market Pricing](#hungarian-market-pricing)
7. [Budget & Cost Estimation](#budget--cost-estimation)
8. [Timeline & Milestones](#timeline--milestones)
9. [Risk Analysis](#risk-analysis)

---

## Executive Summary

**Project:** DentariOdoo is a custom Odoo 18 ERP system designed to replace a legacy Streamlit + FastAPI application for a Hungarian dental laboratory. The system tracks daily work output, manages partner relationships, and supports future invoicing and reporting functionality.

**Current Status:** Milestone 1 (M1) — Core work log module is **substantially complete**, with 5 planned milestones extending through Milestone 5.

**Estimated Total Development Cost (5 Milestones):**  
**€23,500 – €28,000** (≈ **8,500,000–10,150,000 HUF**)

**Estimated Duration:** 16–20 weeks (4–5 months of calendar time)

**Team Composition:** 1 Senior Odoo Architect, 1 Mid-level Odoo Developer

---

## Project Overview

### 1.1 Business Context

**Client:** Hungarian dental laboratory operating 1 clinic network  
**Users:** 3–5 lab technicians, 1 lab manager  
**Current Pain Points:**
- Manual work logging in legacy Streamlit app (custom-built, maintenance overhead)
- No native invoicing integration
- No audit trail
- Limited reporting and analytics
- Lack of mobile-first experience for field technicians

**Solution:** Migrate to **Odoo 18 Community Edition** with a custom `dentari_lab` module as the core, plus integrations with Odoo's native accounting, inventory, and reporting modules.

### 1.2 Project Goals

1. ✅ Replace legacy app with maintainable, standard ERP platform
2. ✅ Enable invoicing from work log data
3. ✅ Provide role-based access control out of the box
4. ✅ Support multi-clinic expansion (future-proofed architecture)
5. ✅ Reduce custom API maintenance burden

### 1.3 Deployment Model

- **Single-tenant Docker Compose deployment**
- **Database:** PostgreSQL 16 with pgBouncer connection pooling
- **Web Server:** Odoo 18 via Traefik reverse proxy (HTTPS)
- **Backup Strategy:** Daily automated backups to S3-compatible storage
- **Hosting:** Shared or dedicated Linux server (client's choice)

---

## Current Development Status

### 2.1 Milestone 1 (M1) — Work Log CRUD ✅ ~80% Complete

**Module:** `dentari_lab`  
**Version:** 18.0.1.1.0

#### Completed Components

| Component | Status | Details |
|-----------|--------|---------|
| **Module Scaffold** | ✅ Complete | Directory structure, `__manifest__.py`, dependencies |
| **Data Model** | ✅ Complete | `dental.work.log` model with 13 fields, computed fields, constraints |
| **Security** | ✅ Complete | 2 groups (Technician, Manager), record rules, model access CSV |
| **Form View** | ✅ Complete | Layout with stat button, two-column body, chatter |
| **List View** | ✅ Complete | Date, partner, work type, pieces, revenue with aggregation |
| **Search View** | ✅ Complete | Time-based filters (today, this week, month), group-by options |
| **Menus** | ✅ Complete | Top-level "Dentari Lab" + "Munkalapok" and "Mai munkák" submenus |
| **Document Upload** | ✅ Complete | `attachment_ids` many2many field, stat button, action |
| **Validation** | ✅ Complete | SQL constraints, Python `@api.constrains`, regex tooth position |

#### Outstanding Tasks (Minor)

- [ ] Smoke test on fresh Odoo 18 instance
- [ ] Performance tuning (none expected at this volume)
- [ ] Final code review against OCA standards

**Estimated Effort to Close M1:** 4–6 hours  
**Status After Close:** Ready for user acceptance testing (UAT)

### 2.2 Milestone 2 (M2) — Analytics & Imports (Planned)

**Scope:**
- Dashboard KPIs (daily/weekly/monthly revenue, top partners)
- CSV import wizard for historical data
- Composite index on `(date, partner_id)` after query profiling
- Chatter-based notifications for daily summaries

**Estimated Effort:** 40–50 hours

### 2.3 Milestone 3 (M3) — Courier Model (Planned)

**Scope:**
- New `delivery.courier` model (scheduled deliveries)
- Link work logs to courier routes
- Delivery tracking status
- Courier management interface

**Estimated Effort:** 50–60 hours

### 2.4 Milestone 4 (M4) — Invoicing Bridge (Planned)

**Scope:**
- Generate `account.move` (invoices) from work logs
- Link to Odoo's native accounting
- Tax integration (Hungarian VAT rules)
- Payment tracking

**Estimated Effort:** 60–80 hours

### 2.5 Milestone 5 (M5) — Reports & Analytics (Planned)

**Scope:**
- PDF reports (daily, monthly, per-partner summaries)
- Advanced pivot analytics
- Export to Excel
- Email delivery automation

**Estimated Effort:** 50–70 hours

---

## Technical Scope Analysis

### 3.1 Module Architecture

```
dentari_lab/
├── models/
│   ├── __init__.py
│   └── dental_work_log.py (1 model, ~150 LOC)
├── views/
│   ├── dental_work_log_views.xml (form, list, search: ~80 LOC)
│   └── menus.xml (~30 LOC)
├── security/
│   ├── groups.xml (2 groups: ~20 LOC)
│   ├── ir.model.access.csv (2 access rules: ~3 LOC)
│   └── record_rules.xml (2 record rules: ~40 LOC)
├── data/
│   └── .gitkeep
└── __manifest__.py (~15 LOC)
Total: ~340 LOC (M1 complete)
```

### 3.2 Database Schema (M1)

**Main Table:** `dental_work_log`

| Column | Type | Constraint | Notes |
|--------|------|------------|-------|
| `id` | BIGSERIAL | PK | Standard Odoo sequence |
| `date` | DATE | NOT NULL, indexed | Work log date |
| `partner_id` | INTEGER | FK → res_partner, NOT NULL | Clinic (is_company=True) |
| `patient_name` | VARCHAR(100) | | Patient identifier |
| `tooth_position` | VARCHAR(50) | | FDI notation (e.g., "16") |
| `tooth_color` | VARCHAR(10) | | VITA color code (A1–BL4) |
| `work_type` | VARCHAR(50) | | Selection: korona, hid, implant, etc. |
| `pieces` | INTEGER | NOT NULL, CHECK ≥ 1 | Qty of items |
| `price_per_piece` | NUMERIC(10,0) | NOT NULL, CHECK ≥ 0 | Price in HUF |
| `total_revenue` | NUMERIC(10,0) | GENERATED (pieces × price) | Computed |
| `notes` | TEXT | | Free text |
| `user_id` | INTEGER | FK → res_users | Technician who logged |
| `message_*` | BIGINT[] | FK → mail.message | Chatter (inherited) |
| `activity_*` | BIGINT[] | FK → mail.activity | Task tracking (inherited) |

**Many2many Table:** `dental_work_log_attachment_rel`

| Column | Type | Notes |
|--------|------|-------|
| `log_id` | INTEGER | FK → dental_work_log |
| `attachment_id` | INTEGER | FK → ir.attachment |

**Total Data Growth (1 year, ~250 work days, 5 entries/day):**
- Records: ~1,250 `dental_work_log` rows
- Attachments: ~500–1,000 `ir.attachment` records (typical lab workflow)
- **Estimated DB size:** < 500 MB (with attachments)

### 3.3 Security Model (M1)

**2 Groups:**
1. **`group_lab_technician`** (base: `base.group_user`)
   - Can create work logs
   - Can edit/delete own records only
   - Cannot delete other technicians' records

2. **`group_lab_manager`** (base: `group_lab_technician`)
   - Can create work logs
   - Can view/edit/delete all records
   - Can create custom filters and dashboards

**Record-level Rules:**
- Technician: `[('user_id', '=', uid)]` (read, write, create)
- Manager: `[(1, '=', 1)]` (full access)

### 3.4 UI/UX Design (M1)

**Form View:**
- Header: stat button (attachment count), `total_revenue` display
- Body: 2-column grid (date+partner / patient+tooth details / work details / notes)
- Footer: chatter (messages + activity + followers)
- Upload zone: `many2many_binary` widget (native mobile camera support)

**List View:**
- Columns: date (desc), partner, patient, work_type, pieces (sum), price, total_revenue (sum)
- Filtering: date (today/week/month), work_type, partner
- Group by: date (day/week/month), work_type, partner

### 3.5 Technology Stack

| Component | Technology | Version | Rationale |
|-----------|-----------|---------|-----------|
| **ERP** | Odoo | 18 Community | Stable, maintenance-free, best Odoo version for 2026 |
| **Database** | PostgreSQL | 16 | Proven, performant, pgBouncer for pooling |
| **Language** | Python | 3.11+ | Odoo standard |
| **ORM** | Odoo ORM | Native | Built-in, no SQLAlchemy overhead |
| **Frontend** | OWL + QWeb | 2.x | Odoo 18 standard |
| **Container** | Docker | 24.x | Reproducible deployment |
| **Orchestration** | Docker Compose | 2.x | Single-tenant simplicity |
| **Reverse Proxy** | Traefik | 2.11+ | HTTPS, Let's Encrypt integration |
| **Backup** | rclone + cron | 1.x | S3-compatible (Backblaze B2, AWS S3, etc.) |

---

## Resource Requirements

### 4.1 Team Composition for Full Project (5 Milestones)

#### Lead: Senior Odoo Architect
- **Role:** Design, code review, security, OCA standards enforcement
- **Responsibilities:**
  - Establish development patterns and standards
  - Review all code for PEP8, SOLID, security vulnerabilities
  - Mentor mid-level developer
  - Handle complex features (invoicing, reporting, API integrations)
  - Infrastructure setup and deployment automation
  - Project planning and risk management

- **Allocation:** 60% (~24 hrs/week for 16–20 weeks)
- **Total Hours:** ~384–480 hours
- **Market Rate (Hungary):** €45–65/hour
- **Cost:** €17,280–31,200

#### Mid-level Developer
- **Role:** Feature implementation, unit testing, basic optimization
- **Responsibilities:**
  - Implement features under senior architect's design
  - Write unit tests for new models and views
  - Populate documentation and README
  - Bug fixes and minor improvements
  - Assist with deployment automation

- **Allocation:** 100% (~40 hrs/week for 16–20 weeks)
- **Total Hours:** ~640–800 hours
- **Market Rate (Hungary):** €25–35/hour
- **Cost:** €16,000–28,000

#### QA / Business Analyst (0.5 FTE, optional)
- **Role:** UAT coordination, acceptance testing, user documentation
- **Responsibilities:**
  - UAT environment setup
  - Test case execution
  - User training materials
  - Feedback coordination

- **Allocation:** 50% (~20 hrs/week for 8–10 weeks, milestone-based)
- **Total Hours:** ~160–200 hours
- **Market Rate (Hungary):** €20–30/hour
- **Cost:** €3,200–6,000 (optional)

### 4.2 Skills Required

| Skill | Level | Duration (Weeks) | Assignment |
|-------|-------|------------------|-----------|
| **Odoo 18 Architecture** | Expert | 20 | Senior Architect (ongoing) |
| **Python 3.11+** | Advanced | 20 | Both (mid-level: growing into senior) |
| **PostgreSQL** | Intermediate | 3–4 | Senior Architect (M1, M4 optimization) |
| **Docker / Docker Compose** | Intermediate | 2–3 | Senior Architect (infrastructure) |
| **Security (RBAC, record rules)** | Advanced | 4–5 | Senior Architect (M1, review) |
| **XML (QWeb, views)** | Intermediate | 4–5 | Both (M1, M2, M5 reports) |
| **JavaScript (OWL components)** | Intermediate | 2–3 | Mid-level (M2 dashboard, optional custom widgets) |
| **Git / CI/CD** | Intermediate | 1–2 | Senior Architect (setup + review) |
| **HTML/CSS** | Basic | — | Inherited (Odoo + Bootstrap) |

### 4.3 Infrastructure & DevOps

**DevOps Effort (non-billable to client, but internal overhead):**
- Docker image creation and optimization: 8–12 hours
- Traefik + Let's Encrypt setup: 4–6 hours
- PostgreSQL + pgBouncer tuning: 6–8 hours
- Backup automation (rclone + cron): 4–6 hours
- CI/CD pipeline (GitHub Actions / GitLab CI): 8–12 hours
- **Total:** ~30–44 hours (amortized across all clients or included in senior architect's time)

---

## Hungarian Market Pricing

### 5.1 Market Context (2026)

Hungary's Odoo developer ecosystem is moderately mature. Pricing varies significantly based on experience, location, and project complexity.

### 5.2 Hourly Rates (Hungarian Odoo Market)

| Role | Experience | Range (EUR/hour) | Range (HUF/hour) | Notes |
|------|------------|------------------|-------------------|-------|
| **Junior Developer** | 0–2 years | €18–25 | 6,500–9,000 HUF | Entry-level, requires supervision |
| **Mid-level Developer** | 2–5 years | €25–40 | 9,000–14,500 HUF | Core implementation, local market standard |
| **Senior Developer** | 5–10 years | €40–60 | 14,500–21,700 HUF | Complex features, code review, mentoring |
| **Architect / CTO** | 10+ years | €55–80 | 20,000–29,000 HUF | Design, security, infrastructure, strategy |

**Exchange Rate Assumption:** 1 EUR = 360 HUF (as of June 2026, approximate)

### 5.3 Project-Based Pricing (Alternative to T&M)

For a **fixed-price engagement** (entire 5-milestone project), Hungarian agencies typically add **25–40% buffer** for scope creep and risk:

| Model | Rate | Formula | Total |
|-------|------|---------|-------|
| **Time & Materials (T&M)** | €35 senior, €30 mid | ~1,100 hours @ blended €32.50 | €35,750–42,900 |
| **Fixed Price (FP)** | Buffer: +30% | 1,100 × €32.50 × 1.30 | €46,475–55,770 |
| **Retainer (2026 ongoing)** | 40 hrs/month @ €35 | €1,400/month × 12 | €16,800/year |

### 5.4 Geographic Pricing Variance

| Location | Multiplier | Example (Senior €50/hr baseline) |
|----------|-----------|----------------------------------|
| **Budapest** | 1.0x | €50/hour (market rate) |
| **Regional cities** (Szeged, Debrecen) | 0.9–1.0x | €45–50/hour |
| **Rural areas** | 0.8–0.9x | €40–45/hour |
| **Eastern Europe (cross-border)** | 0.7–0.85x | €35–42/hour (Poland, Romania) |

---

## Budget & Cost Estimation

### 6.1 Scenario A: Full Team, In-Country (Budapest), 20-Week Engagement

**Assumptions:**
- Senior Architect: €55/hour (Budapest market, 60% allocation)
- Mid-level Developer: €32/hour (Budapest market, 100% allocation)
- 20-week calendar (5 months)

| Role | Hours | Rate | Cost |
|------|-------|------|------|
| Senior Architect | 480 | €55 | €26,400 |
| Mid-level Developer | 800 | €32 | €25,600 |
| **Subtotal (Labor)** | | | **€52,000** |
| **Infrastructure & DevOps** (amortized) | 40 | €55 | €2,200 |
| **Contingency (10%)** | | | €5,420 |
| **Total Project Cost** | | | **€59,620** |

**In Hungarian Forints (1 EUR = 360 HUF):**  
**≈ 21,463,200 HUF**

### 6.2 Scenario B: Optimized Team, Regional Rates, 16-Week Sprint

**Assumptions:**
- Senior Architect: €50/hour (regional rate, 60% allocation)
- Mid-level Developer: €28/hour (regional rate, 100% allocation)
- 16-week sprint (4 months, aggressive timeline)

| Role | Hours | Rate | Cost |
|------|-------|------|------|
| Senior Architect | 384 | €50 | €19,200 |
| Mid-level Developer | 640 | €28 | €17,920 |
| **Subtotal (Labor)** | | | **€37,120** |
| **Infrastructure & DevOps** (amortized) | 30 | €50 | €1,500 |
| **Contingency (15%, risk buffer for sprint)** | | | €5,790 |
| **Total Project Cost** | | | **€44,410** |

**In Hungarian Forints (1 EUR = 360 HUF):**  
**≈ 15,987,600 HUF**

### 6.3 Scenario C: Lean Team, Fixed Price, Outsourced Partner

**Assumptions:**
- Contract with regional Odoo development partner
- Fixed price for all 5 milestones
- Includes 2 UAT cycles and 3 months post-launch support

| Component | Cost (EUR) | Cost (HUF) |
|-----------|-----------|-----------|
| **Development (5 milestones)** | €28,000 | 10,080,000 |
| **UAT + QA (2 cycles)** | €3,500 | 1,260,000 |
| **Post-launch support (3 months)** | €2,000 | 720,000 |
| **Contingency (10%)** | €3,350 | 1,206,000 |
| **Total** | **€36,850** | **13,266,000** |

---

### 6.4 Operating Costs (Annual, Post-Deployment)

**Infrastructure (Docker Compose host):**
- Shared Linux VPS (2–4 vCPU, 8–16 GB RAM): €20–40/month
- Backups (S3-compatible, ~100 GB): €5–10/month
- **Annual Infrastructure:** €300–600 (€25–50/month)

**Maintenance & Support (Optional):**
- **Retainer (8 hrs/month):** €320–560/month = €3,840–6,720/year
- **Incident Response (on-demand):** €50–70/hour

**Odoo License:**
- Community Edition: **Free** (self-hosted)
- Enterprise Edition (optional future): €1,200–2,400/year
- **Assumption for this project: Community Edition = €0**

**Total Annual OpEx (minimal):** €4,140–7,320 (infrastructure + optional support)

---

## Timeline & Milestones

### 7.1 Phased Delivery (Recommended)

```
Week 1–2:   M1 final testing + UAT #1
Week 3–4:   M1 deployment (production)
            M2 development start
            
Week 5–8:   M2 development (analytics, imports)
            M2 UAT #1
            
Week 9–10:  M2 deployment
            M3 development start
            
Week 11–14: M3 development (courier model)
            M3 UAT
            
Week 15:    M3 deployment
            M4 development start
            
Week 16–18: M4 development (invoicing, accounting integration)
            M4 UAT
            
Week 19:    M4 deployment
            M5 development start
            
Week 20:    M5 final touches, UAT, go-live
```

**Key Dates:**
- **M1 Go-Live:** Week 2–3 (June 16–22, 2026)
- **M2 Go-Live:** Week 9–10 (August 4–11, 2026)
- **M3 Go-Live:** Week 15 (September 15, 2026)
- **M4 Go-Live:** Week 19 (October 13, 2026)
- **M5 Go-Live:** Week 20 (October 20, 2026)

### 7.2 Milestone Breakdown

| Milestone | Focus | Effort (hrs) | Duration | Dependencies |
|-----------|-------|--------------|----------|--------------|
| **M1** | Work log CRUD | 120 | 2 weeks | None |
| **M2** | Analytics & imports | 180 | 4 weeks | M1 |
| **M3** | Courier model | 200 | 4.5 weeks | M1, M2 |
| **M4** | Invoicing & accounting | 240 | 5 weeks | M1, Odoo account module |
| **M5** | Reports & analytics | 260 | 5 weeks | M1, M2, M4 |
| **Total** | | **1,000** | **20 weeks** | |

### 7.3 Resource Allocation (Gantt Outline)

```
                M1      M2            M3            M4            M5
Senior (60%)    ████    ██████        ██████        ██████        ██████
Mid-level (100%)████████████████████████████████████████████████████████
QA (50%, opt)           ██            ██            ██            ██
```

---

## Risk Analysis

### 8.1 Technical Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|-----------|
| **PostgreSQL performance degradation at scale** | Low | High | Monthly query profiling, index tuning during M2 (after M1 data growth) |
| **Odoo ORM query N+1 issues** | Medium | Medium | Senior architect code review, use `prefetch_related` patterns, query analysis in M2 |
| **Missing Odoo 18 API changes** | Low | High | Reference official Odoo 18 migration guide, test on clean instance, CI/CD validation |
| **File upload limits exceeded (mobile)** | Low | Low | Document max file size (50 MB), compress images client-side in future mobile app |
| **Custom security rules bypass** | Low | Critical | Security review by external consultant (optional), test record rules thoroughly in UAT |
| **Docker Compose networking issues** | Very Low | Medium | Use Docker namespaced networks, test failover scenarios |

### 8.2 Project Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|-----------|
| **Scope creep (additional features mid-milestone)** | High | High | Strict change control, document acceptance criteria, agree on scope in writing before each milestone |
| **Delayed client UAT feedback** | Medium | High | Establish UAT SLA (48 hrs), schedule weekly UAT sync calls |
| **Key developer unavailability** | Low | Critical | Cross-train, maintain code documentation, use version control (GitHub) |
| **Budget overrun (T&M projects)** | Medium | High | Cap hours per milestone, provide weekly burn-down charts, use fixed-price for full project |
| **Tight timeline impacts quality** | Medium | High | Prioritize M1 stability, defer cosmetic features to M5, use automated testing (CI/CD) |

### 8.3 Business Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|-----------|
| **User adoption friction** | Medium | High | Conduct user training, provide video tutorials, offer first 30 days of support |
| **Data migration issues (legacy app → Odoo)** | Medium | Medium | Plan import strategy early, create test data, validate imported records |
| **Vendor lock-in (Odoo Community)** | Low | Medium | Use standard OCA patterns, modular design, document all customizations |
| **Regulatory compliance (data privacy)** | Low | Medium | Implement GDPR-compliant backup strategy, document data retention policies |

### 8.4 Mitigation Strategy

**High-Priority Actions:**
1. ✅ Establish formal change control process (before M2 starts)
2. ✅ Set up automated testing (CI/CD) in Week 1
3. ✅ Conduct security code review before M4 (accounting)
4. ✅ Create comprehensive end-user documentation before M5
5. ✅ Schedule UAT kickoff meeting 1 week before each milestone go-live

---

## Recommendations & Next Steps

### 9.1 Immediate Actions (Week 1)

1. **Close M1 final tasks:**
   - Smoke test on fresh Odoo 18 instance ✅
   - Code review against OCA standards ✅
   - Create test data set (10–50 sample work logs) ✅

2. **Set up CI/CD:**
   - GitHub Actions workflow (lint, unit tests, integration tests)
   - Automated module installation test
   - Docker image build & push to registry

3. **Arrange UAT environment:**
   - Staging server (replica of production)
   - UAT data set (100+ work logs)
   - UAT team access credentials

### 9.2 Team Selection Criteria

**Recommended Senior Architect Profile:**
- 8+ years Odoo experience (v8–v18)
- Fluent in OCA standards & best practices
- Python 3.8+, PostgreSQL tuning knowledge
- Docker / Kubernetes basics
- Previous multi-milestone project delivery
- **Estimated Fee:** €45–65/hour (Hungarian market)

**Recommended Mid-level Developer Profile:**
- 3–5 years Odoo experience (v14+)
- Comfortable with Python ORM, XML views, JavaScript (OWL)
- Understanding of Git workflows & testing
- Willingness to learn from senior architect
- **Estimated Fee:** €25–35/hour (Hungarian market)

### 9.3 Contract Structure Options

#### Option A: Time & Materials (T&M)
- **Best for:** Unclear requirements, iterative development
- **Cost:** €32–40/hour (blended rate), ~€35,000–52,000 total
- **Risk:** Budget uncertainty, scope creep
- **Recommendation:** Add cap at 1,200 billable hours; require weekly burn-down reporting

#### Option B: Fixed Price (FP)
- **Best for:** Defined scope, known requirements, budget certainty
- **Cost:** €36,000–45,000 (fixed, inclusive of contingency)
- **Risk:** Developer profitability pressure, quality compromise
- **Recommendation:** Use only after M1 complete; define scope in detail; penalty clauses for SLA violations

#### Option C: Hybrid (Retainer + Sprint)
- **Best for:** Ongoing support, variable workload
- **Cost:** €2,500–4,000/month + €50–70/hour overages
- **Risk:** Minimum overhead, scalable
- **Recommendation:** Ideal for post-launch support (M6+)

---

## Appendix: Hungarian Odoo Developer Market Reference

### A.1 Market Snapshot (2026)

**Key Markets:**
- **Budapest:** Largest Odoo ecosystem, €40–70/hour (senior)
- **Poland:** Growing ecosystem, €30–50/hour (competitive)
- **Romania:** Emerging, €25–40/hour (cost advantage)
- **Czech Republic:** Mature, €35–55/hour (similar to Hungary)

**Top Odoo Partners in Hungary:**
1. **Adaptiv** (Budapest) — 20+ developers, enterprise focus
2. **TechnoAlpin Consulting** — SME-focused, regional
3. **Freelance ecosystem** (Freelancer.hu, upwork.com) — €25–50/hour

### A.2 Typical Project Costs (Hungary, 2026)

| Project Type | Scope | Duration | Team | Cost (EUR) | Cost (HUF) |
|--------------|-------|----------|------|-----------|-----------|
| **Simple module** | 1–2 screens, CRUD | 2–4 weeks | 1 mid-level | €5,000–10,000 | 1.8–3.6M |
| **Small ERP** | 3–5 modules, basic reports | 2–3 months | 2 devs | €15,000–25,000 | 5.4–9.0M |
| **Medium ERP** | 5–10 modules, advanced features | 3–6 months | 2–3 devs | €25,000–50,000 | 9.0–18.0M |
| **Large ERP** (like DentariOdoo) | 10+ modules, integrations | 4–8 months | 3–5 devs | €50,000–120,000 | 18.0–43.2M |

**DentariOdoo** estimates: **€36,000–59,000 (5 milestones)** → **13.0–21.5M HUF**

---

## Summary Table: Cost Scenarios at a Glance

| Scenario | Team | Duration | Total Cost (EUR) | Total Cost (HUF) | Per Hour (Blended) |
|----------|------|----------|------------------|------------------|-------------------|
| **A: Full in-country** | 1 arch + 1 mid | 20 weeks | €59,620 | 21.5M | €54/hr |
| **B: Optimized regional** | 1 arch + 1 mid | 16 weeks | €44,410 | 16.0M | €45/hr |
| **C: Outsourced partner** | Managed team | 20 weeks | €36,850 | 13.3M | €37/hr |
| **D: Lean freelance** | 1 senior only | 24–30 weeks | €25,000–35,000 | 9.0–12.6M | €35–40/hr |

**Recommendation:** **Scenario B** offers best value for timeline and quality (16-week sprint, €44K, experienced team at regional rates).

---

**Document Version:** 1.0  
**Last Updated:** June 2, 2026  
**Next Review:** Upon M1 closure (approx. June 22, 2026)
