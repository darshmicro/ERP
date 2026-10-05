# Operational Qualification (OQ) Protocol

**Purpose:** demonstrate that GMP-MERP operates as specified across its operating ranges and that every GMP-critical control works.
**Evidence has two parts:** (A) the automated regression suite — executable, timestamped evidence run in the *site's* environment; (B) scripted manual tests for things automation cannot judge (print layouts, labels, usability).

## Part A — Automated OQ (run on the target database dialect)

Run from the release package:
```
MERP_TEST_DATABASE_URL='mssql+pyodbc://<admin>:<pw>@<server>:1433/MERP_OQ?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=no' \
  python -m pytest tests -p no:cacheprovider --junitxml=docs/validation/evidence/junit.xml
python scripts/gen_validation_docs.py        # regenerates rtm.md with the results
```
(The fixture drops and recreates the schema of the **scratch** database named in the URL — never point it at a live database.)

| Item | Acceptance criterion | Actual |
|---|---|---|
| Collected tests | ≥ the count in the release notes | |
| Failures / errors | 0 | |
| Skipped | 0, or each justified (SQLite-only tests are skipped on SQL Server; the concurrency test is skipped on SQLite) | |
| The 15 critical tests (RTM §"mandatory critical tests") | all pass | |
| Generated role × route access matrix (`tests/security/test_access_matrix.py`) | passes: every route requires authentication; every role/permission combination answers 403/not-403 as the catalogue states | |
| Security tests (`tests/security`) | pass | |
| RTM completeness | every URS has ≥ 1 passing test; generator exits 0 | |

## Part B — Scripted manual tests
Use the demo/PQ data (`database/seeds/demo_data.py`) on a TEST system. Roles are in `access-control-matrix.md`. For each step record Pass/Fail and attach a screenshot or printout.

| # | Function (URS) | Steps | Expected result | Pass/Fail | Evidence |
|---|---|---|---|---|---|
| OQ-M01 | Login, lockout (URS-IAM-01/02) | Enter a wrong password 5 times for a test user | Account locked for the configured period; security event `ACCOUNT_LOCKED`; generic message | | |
| OQ-M02 | Password policy | Change password to `Password1!` then to a compliant new one | Policy message shown; compliant one accepted; reuse refused | | |
| OQ-M03 | Idle timeout | Leave the session idle for the configured time | Redirected to login; action not possible | | |
| OQ-M04 | E-signature (URS-SIG-01) | Approve a vendor with a wrong, then the correct password | Wrong → refused and counted; correct → signature manifest (name, meaning, time) visible; second signature on the same record by the same user refused where SoD applies | | |
| OQ-M05 | PO gate (URS-PUR-02..04) | Change a vendor's requalification due date into the past (DBA) / create a PO | Red banner `PURCHASE BLOCKED — VENDOR QUALIFICATION EXPIRED.`; no PO created | | |
| OQ-M06 | GRN + checklist (URS-WH-01/02) | Receive a PO line; answer a critical checklist item "No" | Verification blocked until QA exception; on verification the lot is in QUARANTINE with label printed | | |
| OQ-M07 | Labels | Print the quarantine and approved labels | Code128 + QR scan to the lot (`/qr/resolve`); status banner correct; every print audited; reprint asks a reason | | |
| OQ-M08 | Issue gates (URS-WH-03..05, MFG-03) | Try to issue a QUARANTINE lot, a REJECTED lot, an expired lot, a held lot | Each refused with the specific rule message; ledger unchanged | | |
| OQ-M09 | QC and release (URS-QC-01..05) | Sample, test (include an OOS result), release chain with 4 different users | OOS raises hold + investigation; release requires all signatures in order; CoA PDF generated after QA release only; approved label | | |
| OQ-M10 | Manufacturing (URS-MFG-01..07) | Create BOM → approve → batch → issue → start → steps → IPC (one failing) → reconcile (one discrepancy) | Gates as specified; failing IPC holds batch and raises deviation; discrepancy highlighted red and blocks until QA accepts | | |
| OQ-M11 | Dispatch (URS-DSP-01/02) | Dispatch released FG; try unreleased/held/expired/over-quantity | Allowed only for released stock; each block explained; dispatch note PDF printed with controlled-copy number | | |
| OQ-M12 | Traceability (URS-TRC-01) | Trace a customer shipment back to the vendor and a vendor lot forward to customers | Complete graph and table; counts match | | |
| OQ-M13 | Quality system (URS-QS-01..06) | Raise deviation/CAPA/change control; initiate a mock recall | Workflows enforce signatures and independence; recall lists affected customers | | |
| OQ-M14 | Reports (URS-RPT-01/02) | Run and export five reports in each format; verify a copy with `/reports-verify` | Content correct; unique copy numbers; verification matches | | |
| OQ-M15 | Audit trail (URS-AUD-01/02) | Review the audit trail of the records created above; run "Verify chain" | Who/what/when/old/new/reason present; chain valid | | |
| OQ-M16 | Retention & backup page | View policies; record a backup and restore test | Evidence appended; alerts clear | | |
| OQ-M17 | Usability & localisation | Walk through role home pages, filters, exports | Menus show only permitted functions; messages are understandable | | |

## Deviations / conclusion
Record as for IQ. OQ acceptable / not acceptable: ______ Signature / QA review: ______
