# 08 — Validation Strategy (Deliverable I)

> The software is a **configurable commercial-style (GAMP 5 Category 4/5 hybrid, custom-developed) GxP system**. Validation is the **site's** responsibility; this project supplies the evidence, documents and tooling that make a risk-based CSV/CSA effort efficient.

## 1. Approach
* Lifecycle per **GAMP 5 (2nd ed.)** with **CSA risk-based assurance** emphasis: unscripted/exploratory testing for low-risk, scripted for high-risk (GMP-critical: release, issue, PO gating, audit, e-signature, calculations).
* **Supplier (developer) activities** — produced by this project: URS-to-test traceability, unit/integration/security/workflow tests run in CI, code review, static analysis, dependency list (SBOM), release notes, known-defect list, data dictionary.
* **User-site activities** — IQ/OQ/PQ in the site's environment, SOPs, training, periodic review.

## 2. Deliverables & templates (in `docs/validation/`, Phase 10; skeletons earlier)
| Doc | Content |
|---|---|
| Validation Plan (VP) | Scope, roles, strategy, acceptance criteria, deviations handling |
| URS | Derived from the master requirements (each with ID `URS-xxx`, GMP-impact class) |
| Functional Spec (FS) | Per module behaviours, workflows, rules (this architecture pack is the seed) |
| Technical/Design Spec (DS) | Architecture, DB, security, interfaces |
| Configuration Spec (CS) | Roles, workflows, numbering, thresholds, tolerances as configured |
| Risk Assessment (RA) | FMEA per function: severity (patient/product/data integrity) × probability × detectability → test depth |
| Data Integrity Assessment | ALCOA+ per data flow, mitigation, residual risk |
| IQ | Server, OS, DB, ODBC, TLS, accounts/least privilege, versions, hashes, backup config, NTP |
| OQ | Functional tests of every GMP-critical rule (BR-IDs), security, audit, e-sig, SoD, workflows, calculations, error handling |
| PQ | End-to-end process: vendor→…→dispatch with production-like data, volume (50 users / 100k records) and DR/restore |
| Requirements Traceability Matrix (RTM) | URS ↔ FS ↔ DS ↔ Test ↔ Result |
| Test scripts | Step, expected result, actual, pass/fail, tester, reviewer, evidence |
| Validation Summary Report (VSR) | Conclusion, deviations, residual risk, release statement |
| Backup/Restore qualification | Backup, restore to scratch DB, hash-chain verify, RPO/RTO measurement |
| Access-control test protocol | Role×function matrix tests (generated from Doc 04 seed) |
| Audit-trail test protocol | Every audited event emits correct who/what/when/old/new; tamper attempts fail |
| SOP requirements list | Admin, user mgmt, backup/restore, change control, incident, periodic review, e-sig policy |

## 3. Automated test strategy (supports OQ; run in CI)
| Level | Tooling | Coverage focus |
|---|---|---|
| Unit | pytest | Rules (each BR-ID), stats (Cp/Cpk verified against reference datasets), numbering, hashing, state machines (all allowed/forbidden transitions) |
| Database | pytest + testcontainers (MSSQL; PG best-effort) | Constraints, uniqueness, triggers (audit immutability), migrations up/down, ledger/balance integrity |
| API | httpx | Auth, permissions matrix (generated), validation, error format, pagination |
| Authorization/security | pytest | RBAC matrix, SoD, IDOR, CSRF, lockout, session expiry, upload validation, rate limits |
| Workflow | pytest | End-to-end chains incl. rejection/retest/hold |
| Audit | pytest | Every mutation yields audit rows; tamper detection |
| Integration/E2E | pytest + Playwright | Vendor→…→Dispatch; traceability both directions |
| Non-functional | locust | 50 concurrent users, 100k+ ledger/audit rows |

The 15 mandatory tests of §77 are explicit named tests `test_crit_01…15`, mapped in the RTM.

## 4. Maintaining the validated state
* Semantic versioning; every release = package + checksum + release notes + impact assessment + regression run.
* Config changes via change control (the system's own CC module); DB migrations versioned (Alembic) and included in release.
* Periodic review (annual): audit-trail review, access recertification, incident/deviation trend, backup restore evidence, patching/vulnerability review.
* Data migration/import validated via controlled import module (Doc 02 IMP).

## 5. What the project will *not* assert
No statement of "compliant", "certified" or "validated" appears in the product or documents. Documents say **"supports compliance with … when implemented with appropriate site procedures and validated"**.
