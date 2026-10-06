# Validation Summary Report (VSR) — DRAFT

> **Status:** supplier-side draft for release **1.0.0-rc1**. The site completes the sections marked **[SITE]**, executes IQ/OQ/PQ, signs and approves. This draft contains supplier development evidence only; it contains **no statement that the system is compliant, certified or validated** for the site's intended use.

| Field | Entry |
|---|---|
| System | GMP-MERP (material & manufacturing ERP for antisera/biologicals) |
| Release / package checksum | 1.0.0-rc1 / **[SITE: SHA-256 of the delivered package]** |
| Validation Plan | `validation-plan.md` |
| Environment validated | **[SITE]** |
| Prepared by / date | **[SITE]** |

## 1. Summary of activities
| Activity | Document | Status |
|---|---|---|
| User requirements | `urs.md` — 59 requirements (critical/major/minor) | Drafted by supplier; **[SITE] review/approval** |
| Risk assessment | `risk-assessment.md` — 25 risks; all inherent HIGH risks reduced below RPN 100 by implemented controls | Drafted; **[SITE] adoption** |
| Specifications | `functional-specification.md`, `design-specification.md`, `configuration-specification.md` (generated), `docs/architecture/` | Delivered |
| Data integrity | `data-integrity-assessment.md` (ALCOA+) | Drafted; **[SITE] open points 1–5** |
| IQ | `iq-protocol.md` (20 checks) | **[SITE] to execute** |
| OQ — automated | Regression suite (see §2); RTM `rtm.md` | Supplier evidence below; **[SITE] re-run on target** |
| OQ — manual | `oq-protocol.md` Part B (17 scripts) | **[SITE] to execute** |
| PQ | `pq-protocol.md` | **[SITE] to execute** |
| Security | `security-test-protocol.md`, `penetration-test-checklist.md`, automated tests | Automated evidence below; **[SITE] pen-test** |
| Backup/restore | `backup-restore-qualification.md`; `evidence/restore-test-sqlserver.json` | Supplier evidence; **[SITE] to execute** |
| Performance | `performance-and-load.md`; `evidence/load-test-sqlserver.txt` | Supplier evidence; **[SITE] PQ-P1…P4** |
| SOPs | `sop-requirements.md` (22 procedures) | **[SITE] to author/approve** |

## 2. Supplier test evidence (development environment, 2026-10-05)
| Database / run | Result |
|---|---|
| **SQLite** (development) — full suite, `evidence/junit.xml` (+ `junit-sqlite-extra.xml`) | **232 collected: 231 passed**, 1 skipped (the same-account concurrent-login test needs a multi-writer database); 0 failed |
| **SQL Server 2022** (Linux container, ODBC Driver 18) — full suite in four parallel partitions, `evidence/junit-sqlserver-1…4.xml` | **230 passed**, 0 failed, 2 deselected (the two Alembic tests that spawn SQLite subprocesses; migrations are verified separately below). Includes the same-account concurrent-login regression test |
| Migrations `0001 → 0009` up / down / up on a clean SQL Server database | Pass — 110 tables, 17 `INSTEAD OF` append-only triggers, final `alembic current` = `0009` |
| Least-privilege grants script (`database/mssql/01_logins_and_grants.sql`) executed as `sa`; then as `merp_app` | `UPDATE`/`DELETE` on **all 17** append-only tables → *permission denied*; `CREATE TABLE` → *permission denied*; `SELECT` works |
| Backup / restore (`scripts/restore_test.py`, `evidence/restore-test-sqlserver.json`) | SUCCESS — backup with CHECKSUM, `RESTORE VERIFYONLY` OK, restore to scratch DB in 0.7 s (2.7 s end-to-end), 110 tables / 5 010 rows identical, **audit hash chain verified on the restored copy (1 898 rows)** |
| Load (`scripts/load_test.py`, `evidence/load-test-sqlserver.txt`) | 50 virtual users, 120 s, 4 786 requests, 39.6 req/s, **0 errors**, p95 < 2.3 s (single shared host) |
| UI smoke (Playwright/Chromium on demo data) | 44 page loads across QA Head, Warehouse, Production and Auditor roles: no page or console errors |
| Generated protocols | Access matrix: every route authenticated; ≈ 5 000 role × route checks pass on both databases. 15 mandatory critical tests: all pass on both databases |


## 3. Traceability
`rtm.md`: every one of the 59 URS items is traced to business rules and to at least one automated test; the generator aborts if a referenced test does not exist. The 15 mandatory critical tests are explicit (§"mandatory critical tests" in the RTM).

## 4. Deviations and defects found during supplier testing
| # | Description | Impact | Disposition |
|---|---|---|---|
| D-01 | Simultaneous logins of one account returned 409 (optimistic row version on `users`) — found by the SQL Server load test | Availability for users with several devices | **Fixed**; regression test (server DBs) |
| D-02 | Connection-pool starvation at 50 users | Time-outs under load | **Fixed** (configurable pool, guidance) |
| D-03 | Out-of-range ids returned 500 | Error handling | **Fixed** (422) |
| D-04 | Spreadsheet formula injection through exported text | Security | **Fixed** (neutralisation + test) |
| D-05 | Append-only grants script covered 6 of 17 tables | Defence in depth | **Fixed** (generated list) |
| D-06 | PDF output interpreted user text as markup | Output integrity | **Fixed** (escaped) + test |
Earlier phase defects (SQL-Server specific predicates, reserved word, DATETIME rounding vs. hash chain, identity on chain head, lock ordering) are recorded in `sqlserver-verification.md` and the phase reports.
**No open critical or major defects.** Open limitations: `docs/known-defects.md` (KD-01…KD-14).

## 5. Residual risk
Per `risk-assessment.md` the residual items for the site are: backup execution and restore testing (#16), time source (#20), change-control SOP adoption (#23), label inspection at PQ (#25), plus the DBA/administrator access controls noted in the ALCOA+ assessment.

## 6. Conclusion **[SITE]**
The system is / is not released for GMP use in the validated state. Conditions: ______
Quality Assurance approval: name / role / signature / date: ______
System owner: ______   IT/CSV: ______

## 7. Attachments
RTM · URS · protocols with executed results · IQ/OQ/PQ deviation logs · evidence folder · SOP list with approval status · training records.
