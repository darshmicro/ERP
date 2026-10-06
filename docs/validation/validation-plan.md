# Validation Plan (VP) — GMP-MERP

> **Status: DRAFT supplier-side package.** Computerised-system validation is the **site's** responsibility (21 CFR Part 11, EU GMP Annex 11, GAMP 5). This plan describes the evidence the supplier provides and the activities the site must perform. Nothing in this package states that the software is "compliant", "certified" or "validated"; it states that the system *supports* compliance when implemented with appropriate procedures and qualified infrastructure.

## 1. Purpose and scope
Validate GMP-MERP (material, manufacturing, quality and dispatch ERP for antisera/biologicals manufacture) for its intended use: Vendor → Qualification → Material → PR → PO → GRN → Quarantine → Sampling → QC → QA release → Inventory → Issue → SFG → FG → QC/QA → Dispatch → Traceability → Reports, including the quality system (deviation, CAPA, change control, risk, SOP, complaints, recall).
Out of scope (v1): environmental monitoring, utilities, stability studies, LIMS instrument integration, payroll/finance (see *Known limitations* in each phase report).

## 2. System classification
GAMP 5 category 4/5 hybrid (configurable, custom-developed). GxP impact: **high** (release, issue, dispatch, audit trail, e-signature, calculations). Open/closed system: intended as a **closed** system behind TLS.

## 3. Lifecycle and responsibilities
| Activity | Supplier (this project) | Site |
|---|---|---|
| URS | Draft derived from the master requirements (`urs.md`, 59 requirements with GMP impact) | Review, adapt, approve |
| Risk assessment | FMEA draft (`risk-assessment.md`) | Adopt / extend with site processes |
| Design/FS/CS | `docs/architecture/`, `functional-specification.md`, `design-specification.md`, `configuration-specification.md` (generated) | Review, record site configuration |
| Code review / unit & integration tests | Automated suite (~250 tests) run per release; static analysis; dependency inventory (SBOM) | Review evidence; optional code audit |
| IQ | Protocol (`iq-protocol.md`) | **Execute** on the production infrastructure |
| OQ | Protocol (`oq-protocol.md`) + automated evidence (`rtm.md`, `evidence/junit.xml`) | Execute / witness the scripted manual tests; review automated results |
| PQ | Protocol (`pq-protocol.md`) + demo/PQ data loader | **Execute** with production-like data, volume and users |
| Traceability | `rtm.md` (generated; fails if a mapped test is missing) | Maintain for site-specific requirements |
| Backup/restore qualification | `backup-restore-qualification.md` + `scripts/restore_test.py` | Execute on site infrastructure; record RPO/RTO |
| Security qualification | `security-test-protocol.md`, `penetration-test-checklist.md` + automated tests | Execute pen-test per site policy |
| Reporting | `validation-summary-report-draft.md` | Complete, sign, approve |
| Maintaining the validated state | Release notes, regression suite, change-impact guidance | Change control (the system's own module), periodic review |

## 4. Approach (risk-based, CSA-aligned)
* **Scripted testing** for GMP-critical functions (release, issue, dispatch, PO gate, audit trail, e-signature, calculations, SoD, retention) — automated where possible (executable evidence with timestamped JUnit results) and manual UI scripts where human judgement is needed (labels, print layouts, usability).
* **Unscripted / exploratory testing** for low-risk functions (list filters, cosmetic issues), recorded as a session note.
* **Risk ranking** (FMEA) drives depth: RPN ≥ 200 = scripted + independent review; 100–199 = scripted; < 100 = exploratory.
* Every URS item maps to ≥ 1 test (`rtm.md`); the 15 mandatory critical tests are explicit.

## 5. Deliverables (this folder)
`validation-plan.md` · `urs.md` · `functional-specification.md` · `design-specification.md` · `configuration-specification.md` · `risk-assessment.md` · `data-integrity-assessment.md` · `iq-protocol.md` · `oq-protocol.md` · `pq-protocol.md` · `rtm.md` · `access-control-matrix.md` · `audit-trail-test-protocol.md` · `security-test-protocol.md` · `penetration-test-checklist.md` · `backup-restore-qualification.md` · `performance-and-load.md` · `sop-requirements.md` · `sbom.md` · `validation-summary-report-draft.md` · `sqlserver-verification.md` · `evidence/`. Architecture pack: `docs/architecture/00–13` (incl. generated data dictionary and ER diagrams).

## 6. Acceptance criteria
1. All automated tests pass on the target database dialect (SQL Server) with zero failures; skipped tests are justified.
2. All 15 critical tests pass; no open critical/major defect.
3. IQ/OQ/PQ protocols executed, deviations documented and closed; RTM complete.
4. Backup restored to a scratch database, audit-trail hash chain verified on the copy, RTO/RPO within the site's targets.
5. Security protocol executed; high/critical findings resolved.
6. SOPs listed in `sop-requirements.md` approved and users trained before go-live.

## 7. Deviation handling
Any test failure or unexpected behaviour during IQ/OQ/PQ is logged on the protocol, assessed (impact, root cause), corrected under change control, and re-tested; the VSR lists all deviations and their disposition.

## 8. Maintaining the validated state
Semantic versioning; each release = package + checksum + release notes + impact assessment + regression run (`pytest`) + regenerated `rtm.md`. Database migrations are versioned (Alembic) and verified up/down/up on SQL Server (`sqlserver-verification.md`). Annual periodic review: audit-trail review, access recertification (`reports/user-access`), deviation/CAPA trend, backup-restore evidence, vulnerability/dependency review.
