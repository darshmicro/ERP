# Phase 10 Report — Validation and hardening

## What was implemented
* **The 15 mandatory critical tests (§77)** — explicit, mapped one-to-one in `tests/validation/test_critical_15.py` (08–15) and the existing `test_crit_01…07` (purchase, warehouse, dispatch); misleading legacy test names were corrected so the numbering is unambiguous.
* **Generated access-control protocol** (`tests/security/test_access_matrix.py`) — walks the *live route table*: every non-public route must answer `401` unauthenticated (public endpoints are an explicit reviewed list of five), and every seeded role × every route with declared permissions must answer `403` when it lacks a permission and not `401/403` when it holds all (≈ 5 000 checks); administrators carry no GMP approval authority.
* **Security hardening tests** — SQL-injection payloads against every list/search/report parameter, mass assignment of status/system columns, disguised/oversized/traversal uploads, credential exposure scan, stored-XSS inertness + CSP, cookie flags + server-side logout invalidation, malformed identifiers, CSRF everywhere, spreadsheet **formula-injection neutralisation** in XLSX/CSV exports.
* **Validation tooling** — `scripts/gen_validation_docs.py` generates from the code: URS (59 requirements, from `scripts/validation_requirements.py`), **RTM** (every mapped test verified to exist; results from JUnit evidence), configuration specification, access-control matrix, **data dictionary (110 tables)**, **ER diagrams**, SBOM, committed OpenAPI contract (397 operations).
* **Protocols and plans** — Validation Plan, FS, DS, FMEA risk assessment (25 risks, RPN before/after), ALCOA+ data-integrity assessment, IQ (20 checks), OQ (automated + 17 manual scripts), PQ (end-to-end scenario, volume, resilience), audit-trail, security and penetration-test protocols, backup/restore qualification, performance notes, SOP requirements list, VSR draft.
* **Operational tooling with SQL Server evidence** — `scripts/restore_test.py` (backup CHECKSUM → VERIFYONLY → restore to scratch → row counts → **audit hash chain verified on the restored copy** → RTO), `scripts/load_test.py` + Locust profile, `database/seeds/demo_data.py` (demo/training data through the real API: users per role, Vendors A/B/C, materials, specs, a released lot, a quarantined lot, an in-process batch, deviation, CAPA).
* **Manuals** — user manual (all modules), administrator manual (backup, jobs, retention, tuning, upgrading), troubleshooting guide, release notes, known defects.

## Defects found by this phase's testing (all fixed)
| # | Found by | Defect | Fix |
|---|---|---|---|
| 1 | SQL Server load test | Concurrent logins of one account → 409 `CONCURRENT_MODIFICATION` | Login bookkeeping via core `UPDATE`; regression test |
| 2 | SQL Server load test | Connection pool exhausted at 50 users → 60 s time-outs | Configurable pool, larger defaults, tuning guidance |
| 3 | Hardening tests | `/lots/99999999999999999999` → 500 | `OverflowError`/`DataError` → 422 |
| 4 | Hardening tests | Excel/CSV formula injection possible through exported text | Prefix neutralisation + test |
| 5 | Review of grants script | `database/mssql/01_logins_and_grants.sql` listed only the 6 Phase-1 append-only tables | Generated from `APPEND_ONLY_TABLES` (17) |
| 6 | Generated matrix test | (control) public endpoint list had to be made explicit | Five reviewed public endpoints |

## Evidence
* SQLite: full suite green (see VSR draft for counts). SQL Server 2022: full suite run, migrations 0001→0009 up/down/up (110 tables, 17 `INSTEAD OF` triggers), restore test (`evidence/restore-test-sqlserver.json`), load test (`evidence/load-test-sqlserver.txt`), JUnit (`evidence/junit-sqlserver.xml`).
* UI smoke (Playwright/Chromium, demo data): 44 page loads across four roles with no page or console errors.

## Known limitations
See `docs/known-defects.md` (KD-01…KD-14). Validation of the system for use is **the site's** responsibility; this package supplies supplier-side evidence and protocols, not a statement of compliance.
