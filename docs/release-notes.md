# Release Notes — GMP-MERP 1.0.0-rc1

Feature-complete release candidate covering Phases 1–10 of the build plan. **Not validated for any site** — see `docs/validation/` for the supplier evidence and the activities the site must perform.

## Highlights
* **Platform:** local + LDAP/AD authentication, RBAC (256 permissions, 14 roles), SoD rules SOD-01…35, HMAC-chained audit trail with DB triggers, re-authenticated e-signatures, status and approval engines, controlled numbering.
* **Master data:** vendors, materials, versioned STP/specification/sampling plan/BOM/vendor–material/SOP, locations, equipment, customers, controlled Excel import, hashed documents.
* **Purchase → Warehouse → QC → Manufacturing → Dispatch** with all 15 critical controls, append-only inventory ledger, FEFO, holds, labels, OOS/OOT, statistics, CoA, conditional release, reconciliation, antisera genealogy, dispatch gates, traceability graph, global search/QR.
* **Quality system:** deviation, CAPA, change control wired to masters, FMEA, SOP control, complaints, recall.
* **Reports:** 37 permissioned reports (JSON/XLSX/CSV/PDF) with controlled-copy log, business PDFs, four dashboards, retention/legal hold/archive, backup evidence.
* **Validation package:** URS (59), generated RTM (all mapped tests verified), configuration specification, access-control matrix, data dictionary, ER diagrams, IQ/OQ/PQ protocols, FMEA, ALCOA+ assessment, security/pen-test protocols, restore and load tooling, demo data.

## Database
Migrations `0001`–`0009` (110 tables, 17 append-only). Verified up/down/up on SQL Server 2022.

## Fixes found by validation work in this release
* Simultaneous logins of one account returned 409 (optimistic version on the user row) — login bookkeeping now uses core updates (found by the SQL Server load test).
* Database connection pool was too small for the thread pool under 50 concurrent users — pool is configurable and defaults raised.
* Out-of-range numeric identifiers in URLs returned 500 — now 422.
* Spreadsheet formula injection via exported text neutralised.
* Append-only grants script now lists all 17 protected tables.

## Upgrade notes
Run `alembic upgrade head`; re-run `scripts/bootstrap_admin.py` to seed new permissions/roles/retention defaults; configure `MERP_DB_POOL_SIZE` for your worker count; schedule the daily jobs; record a backup and a restore test.

## Known defects and limitations
See `docs/known-defects.md`.
