# DentariOdoo — Project Analysis and Realistic 2026 Budget

**Assessment date:** October 11, 2026

**Target:** Odoo 18 Community

**Status:** Working project; this document is a planning estimate, not a vendor quotation

**Exchange-rate convention:** €1 = 365 HUF, rounded for planning

---

## Executive Summary

DentariOdoo is a small, focused Odoo module suite for one dental laboratory, not a large ERP implementation. The previous estimate of roughly 1,000 development hours and €23,500–€59,620 treated the project as a continuously staffed agency engagement. That model is not faithful to the repository, the size of the business, or the development model described by the owner.

The repository currently contains **four Odoo 18 add-ons and about 4,225 lines across implementation, XML, security data, demo data, and tests**. The code already covers work logs, dashboards, draft invoice generation, monthly PDF/email summaries, quick expenses, MIS profitability reporting, and Számlázz.hu archive synchronization. The earlier document still described most of those capabilities as future milestones.

### Recommended planning figures

| Question | Realistic range | HUF equivalent | Meaning |
|---|---:|---:|---|
| **Cash needed to production-harden what already exists** | **€1,200–€3,400** | **0.44–1.24M HUF** | AI tools, targeted outside review, first-year hosting/backups, and a small contingency; owner development time is not invoiced |
| **Cash including the two still-optional features** | **€1,700–€4,900** | **0.62–1.79M HUF** | Adds CSV migration/import and courier workflow, assuming owner + AI implementation |
| **Full economic cost from scratch** | **€5,300–€17,000** | **1.93–6.21M HUF** | Includes 128–208 hours of owner opportunity cost at an explicit €30–€60/hour, plus external cash costs |
| **Solo contractor replacement price** | **€7,000–€14,000** | **2.56–5.11M HUF** | What an accountable independent developer might quote, including discovery, handover, and risk |
| **Agency procurement range** | **€15,000–€30,000** | **5.48–10.95M HUF** | Commercial delivery with project management, QA, warranty, and support; not the recommended model here |

**Recommendation:** budget this as an **owner-built, AI-assisted internal system**, with paid expert review only at the accounting, security, data-migration, and production-release boundaries. For this company, the operative budget is the first or second row—not a two-person agency team for 16–20 weeks.

These ranges are deliberately not presented as precise market facts. The two Reddit discussions are useful evidence of changing buyer and developer behavior, but they are anecdotes rather than a rate survey.

---

## 1. Business and Delivery Context

- One Hungarian dental laboratory
- Approximately 3–5 technicians and one manager
- Odoo 18 Community, self-hosted
- A technically capable owner/developer with strong Python, cloud, and DevOps experience
- Odoo-specific knowledge is developing, but implementation is accelerated by Codex/Claude-class agents
- Work can be delivered part-time over weekends
- A normal module-sized change is assumed to take **2–3 focused development days**, before business acceptance and production hardening

That last distinction matters. Development time is not the same as elapsed project time, and neither is the same as a commercial quotation. An agency sells availability, discovery, meetings, acceptance management, warranty, and continuity in addition to code. An owner-builder pays mainly with personal time and accepts more delivery risk.

---

## 2. Repository-Based Current Status

The module manifests identify Odoo **18.0**. The following status comes from the current repository rather than the obsolete five-milestone plan.

| Add-on | Current capability | Evidence in repository | Status |
|---|---|---|---|
| `dentari_lab` | Work logs, security rules, graph/pivot/dashboard views, draft customer invoice wizard, monthly PDF and email summary, digest integration | Manifest `18.0.1.3.0`; models, views, reports, security, and tests | Implemented |
| `dental_quick_expense` | Fast expense wizard creating draft vendor bills; expense categories and list views | Manifest `18.0.1.0.0`; 302-line test module | Implemented |
| `dentari_mis_reports` | Rolling 12-month revenue/expense profitability report using OCA `mis_builder` | Manifest `18.0.1.0.0`; report definitions and tests | Implemented |
| `dentari_invoice_archive` | Scheduled/manual Számlázz.hu invoice archive synchronization into draft `account.move` records, with mocked tests | Manifest `18.0.1.0.0`; client, sync model, cron, views, and tests | Implemented; live API behavior still deserves release verification |

### Capabilities no longer correctly described as “planned”

- Revenue dashboards and pivot/graph analysis
- Draft invoice generation from work logs
- PDF monthly reporting
- Monthly email delivery
- Expense entry and categorization
- Profitability reporting
- External invoice archive synchronization

### Remaining or optional scope

| Work item | Practical effort | Notes |
|---|---:|---|
| Fresh-database installation and upgrade test | 1–2 days | Verify all four modules and OCA dependencies together |
| Production security/accounting review | 1–2 days | Targeted review; a permanent architect allocation is unnecessary |
| Backup restore, rollback, monitoring, and release checklist | 1–2 days | DevOps competence reduces implementation time, but the recovery test must actually be run |
| Business UAT and fixes | 2–4 days | Calendar time depends on user feedback, not coding speed |
| Historical CSV import, if still required | 2–3 days | Prefer Odoo's import facilities before writing a custom wizard |
| Courier workflow, if still required | 2–3 days | One compact model/workflow unless route optimization is added |
| Odoo 19 upgrade | Separate project | Design documents exist, but it is outside this Odoo 18 estimate |

**Production close-out:** approximately **5–10 person-days** for the current scope.

**Optional CSV + courier additions:** approximately **4–6 person-days**.

This is consistent with the owner's 2–3-day-per-module experience. The buffer is concentrated in cross-module testing, real data, external APIs, and UAT rather than boilerplate coding.

---

## 3. What the Two Reddit Discussions Actually Say

Sources checked on October 11, 2026:

1. [For all of us Odoo developers: the future is (almost) here, are we ready?](https://www.reddit.com/r/Odoo/comments/1r1ys7y/for_all_of_us_odoo_developers_the_future_is/)
2. [My company wants to migrate from Odoo Enterprise to Community to avoid licensing fees. Is this realistic?](https://www.reddit.com/r/Odoo/comments/1x1pkbd/my_company_wants_to_migrate_from_odoo_enterprise/)

The second thread was only minutes old when checked and contained two visible replies. It must be treated as an early snapshot, not community consensus. Earlier versions of this document attributed a €50,000 saving, a manufacturer case study, and several warnings to that thread; those comments were not present in the supplied source and have been removed.

### 3.1 AI-forward developers and owner-builders

- One developer reports that AI fixed a troubled Odoo 16→18 migration in one day after a slow support process.
- Another reports producing a working drag-and-drop builder prototype in one evening after an agent estimated weeks.
- An Odoo.sh user says their team is implementing internal apps and UI changes faster than with an external team, despite limited in-house Python experience.
- A commenter summarizes the near-term effect as developers becoming roughly two or three times more efficient, with new graduates and routine work under the most pressure.

**Pricing effect:** routine CRUD, XML, tests, refactors, documentation, and framework discovery should no longer be estimated with pre-agent productivity. For a capable Python/DevOps developer, billing hundreds of hours for each small module is not credible.

### 3.2 Cautious Odoo developers

- The recurring objection is not that agents are useless; it is that a non-expert may miss the dangerous minority of errors.
- The thread specifically identifies silent ERP failures in accounting, inventory, and business logic as the high-risk area.
- Another commenter separates internal, non-customer-facing improvements from DevOps, noting that operations remains a different problem.
- Several participants argue that AI changes how developers work but does not eliminate the person who must turn business needs into a correct system.

**Pricing effect:** keep small, bounded review budgets for security, accounting semantics, migrations, backups, and go-live. Do not translate that warning into a full-time architect for five months.

### 3.3 Business-side teams reacting to licensing and control

The newer thread describes a 190-employee company exploring Community because Enterprise licensing became too expensive. The two visible replies support a Community-first direction in principle:

- One recommends AI-assisted deployment and self-hosting, but says unclear requirements are the critical failure point.
- The other believes Community can replace Enterprise for some businesses by using established free accounting add-ons, while explicitly acknowledging the ongoing maintenance budget.

**Pricing effect:** buyers compare recurring licence fees with ownership and maintenance—not only with an agency's theoretical replacement cost. A company with an in-house technical owner has a credible build option and therefore a much lower willingness to pay for commodity implementation.

### 3.4 Balanced conclusion for DentariOdoo

The comments support neither “AI makes ERP free” nor “expert rates and old hour counts stay unchanged.” The defensible conclusion is:

1. AI sharply reduces implementation hours for this project's ordinary module work.
2. Existing Python/DevOps competence removes much of the infrastructure learning curve.
3. Odoo expertise is purchased selectively for review and difficult edge cases.
4. Business clarification, live data, accounting validation, and recovery testing remain human bottlenecks.
5. Agency pricing can still be valid as a procurement product, but it is not the project's intrinsic development cost.

---

## 4. Effort Model

### 4.1 Rebuild-equivalent effort

This is a sanity check on the codebase's scale, not a proposal to rebuild it.

| Work package | AI-assisted effort |
|---|---:|
| `dentari_lab` core, dashboards, invoice and monthly-report workflows | 4–7 days |
| `dental_quick_expense` | 2–3 days |
| `dentari_mis_reports` using existing OCA `mis_builder` | 2–3 days |
| `dentari_invoice_archive` and external API handling | 3–5 days |
| Cross-module tests, deployment, UAT, documentation, and fixes | 5–8 days |
| **Total** | **16–26 days / 128–208 hours** |

The pure feature-code portion remains close to the owner's **2–3 days per module** rule. The larger total includes work that cannot honestly be assigned to a single module: discovery, real-account API checks, data validation, access testing, restore drills, and user acceptance.

### 4.2 Why the old 1,000-hour estimate fails

- It multiplied weekly allocations by a long calendar instead of estimating deliverables.
- It assumed two continuously occupied developers for a system used by roughly six people.
- It counted capabilities as future work even though the repository already implements them.
- It treated a small suite of four focused add-ons as a “large ERP” with ten or more modules.
- It did not separate coding, elapsed time, internal opportunity cost, and vendor risk premium.
- Its headline estimate (€23,500–€28,000) contradicted its own detailed scenarios (€36,850–€59,620).

---

## 5. Revised Budget Scenarios

### 5.1 Recommended: owner + AI + targeted review

#### Existing scope to production

| Cash item | Range |
|---|---:|
| AI development tools during close-out | €100–€400 |
| 6–15 hours of targeted Odoo/accounting/security review | €500–€1,500 |
| First-year server, backups, and monitoring | €400–€1,000 |
| Release contingency | €200–€500 |
| **First-year cash requirement** | **€1,200–€3,400** |

Owner time: **40–80 hours**, mainly installation verification, UAT fixes, release operations, and documentation. This time is real, but it is not an external invoice.

#### With CSV import and courier workflow

Add approximately **32–48 owner hours** and **€500–€1,500** for extra review, tooling, and contingency. The resulting first-year cash range is **€1,700–€4,900**.

### 5.2 Internal economic cost

Management may still want the cost of the owner's time for prioritization. Use the company's actual loaded opportunity cost; do not invent an Odoo-consulting rate.

For a from-scratch equivalent of 128–208 hours:

| Owner opportunity cost | Time value | Plus cash costs | Total economic cost |
|---:|---:|---:|---:|
| €30/hour | €3,840–€6,240 | €1,500–€4,500 | **€5,340–€10,740** |
| €60/hour | €7,680–€12,480 | €1,500–€4,500 | **€9,180–€16,980** |

This is an internal decision metric, not an amount the company should pay to itself.

### 5.3 Solo contractor

A competent independent developer taking responsibility for requirements, code, deployment, and handover may reasonably quote **€7,000–€14,000**. This exceeds raw implementation cost because the contractor carries discovery, schedule, warranty, communication, and continuity risk.

Use this route if the owner does not want to spend weekends on the project or needs a clearly accountable supplier.

### 5.4 Agency delivery

An agency price of **€15,000–€30,000** can be commercially understandable when it includes project management, formal QA, documentation, service levels, and post-launch support. It is still poor value for this specific business unless those procurement guarantees are required.

The previous €36,850–€59,620 scenarios are removed as the recommended baseline. They price an organizational delivery model that this project neither needs nor uses.

---

## 6. Timeline

### Current scope

| Phase | Focused effort | Likely elapsed time for weekend work |
|---|---:|---:|
| Integrated install/upgrade verification | 1–2 days | 1 weekend |
| Security, accounting, and external API review | 1–2 days | 1–2 weeks including reviewer availability |
| UAT and fixes | 2–4 days | 2–4 weeks depending on feedback |
| Production release and recovery test | 1–2 days | 1 weekend |
| **Total** | **5–10 days** | **3–6 weekends** |

### Optional additions

- CSV migration/import: one 2–3-day module-sized iteration
- Courier workflow: one 2–3-day module-sized iteration

A 16–20-week full-time project plan is unnecessary. Elapsed time may still stretch over several months when development is deliberately part-time, but that does not imply hundreds of billable hours.

---

## 7. Risk-Based Review Boundaries

Spend review money where an error could be silent or expensive:

| Boundary | Minimum evidence before release |
|---|---|
| Access control | Tests with technician and manager users; verify record rules and menu visibility |
| Draft invoices/vendor bills | Accountant validates tax, account, journal, rounding, posting, and cancellation behavior |
| Számlázz.hu sync | Live sandbox/account test, idempotency check, timeout/retry behavior, and duplicate prevention |
| Historical import | Reconciliation totals before/after import and a reversible dry run |
| Backups | Successful restore into a clean environment, not merely a scheduled backup job |
| Upgrade | Fresh install plus upgrade of every custom and OCA dependency |

AI-generated code should pass the same checks as human-generated code. The control is evidence—tests, reconciliation, and restore—not the seniority label attached to every implementation hour.

---

## 8. Decision

For DentariOdoo, approve an initial **€1,200–€3,400 first-year cash envelope** to production-harden the existing system. Raise it to **€1,700–€4,900** only if the historical import and courier workflow remain required.

Track owner time separately. If weekend work becomes undesirable or progress stalls, compare a bounded **€7,000–€14,000 solo-contractor handover** against the owner's remaining opportunity cost. Do not default to an agency team unless the business consciously chooses formal accountability, SLA, and continuity over the lower-cost owner-builder model.

---

## Sources and Limitations

- [Reddit: Odoo developers discussing AI's impact](https://www.reddit.com/r/Odoo/comments/1r1ys7y/for_all_of_us_odoo_developers_the_future_is/)
- [Reddit: Enterprise-to-Community migration discussion](https://www.reddit.com/r/Odoo/comments/1x1pkbd/my_company_wants_to_migrate_from_odoo_enterprise/)
- [Odoo 18 documentation: customer invoices](https://www.odoo.com/documentation/18.0/applications/finance/accounting/customer_invoices.html)
- [OCA `mis_builder`](https://github.com/OCA/mis-builder)
- [Magyar Nemzeti Bank: official exchange rates](https://www.mnb.hu/en/statistics/statistical-data-and-information/statistical-time-series/exchange-rates)

Reddit comments are self-reported experiences, not audited benchmarks. Rate ranges in this document are scenario assumptions for decision-making. Before signing an external contract, request quotes against the repository and a written acceptance checklist.

---

**Document version:** 2.0

**Last updated:** October 11, 2026

**Next review:** after integrated production-readiness testing or a material scope change
