# GMP-MERP — GMP Material & Manufacturing ERP

Web-based ERP for GMP-regulated biological/antisera manufacturing: Vendor → Purchase → Receipt/GRN → Quarantine → QC/QA release → Inventory → Manufacturing → FG release → Dispatch, with full traceability.

> **Regulatory position.** This software is designed to *support* 21 CFR Part 11, EU GMP Annex 11 and ALCOA+ through technical controls (unique users, RBAC, segregation of duties, immutable audit trail, electronic signatures, controlled workflows). It is **not** "certified" or "compliant" by itself: compliance requires site validation (CSV/CSA), SOPs, trained users, qualified infrastructure and periodic review. See `docs/architecture/06-compliance-mapping.md`.

## Status
| Phase | Scope | State |
|---|---|---|
| 0 | Architecture, DB design, RBAC, workflows, validation strategy | ✅ `docs/architecture/` |
| 1 | Platform foundation (IAM, audit trail, e-signature, numbering, status/workflow engines, company master, app shell) | ✅ this release — see `docs/phase-reports/phase-1.md` |
| 2 | Master data: vendor, material, versioned specs/STPs/sampling plans, locations, equipment, customers, Excel import/export | ✅ `docs/phase-reports/phase-2.md` (SQL Server-verified: `docs/validation/sqlserver-verification.md`) |
| 3 | Purchase: vendor qualification, vendor–material approval, PR, PO with expiry/approval gates | ✅ `docs/phase-reports/phase-3.md` |
| 4 | Warehouse: GRN + checklist, lots/containers, quarantine, inventory ledger, FEFO/FIFO, holds, labels, temperature, destruction | ✅ `docs/phase-reports/phase-4.md` |
| 5 | QC/LIMS: sampling, tests/results, amendments, OOS/OOT, release chain, CoA, conditional release, statistics | ✅ `docs/phase-reports/phase-5.md` |
| 6 / 6b | Manufacturing: BOM, batches, issue/return, IPC, reconciliation, output; antisera donors/bleeds/pools | ✅ `docs/phase-reports/phase-6.md` |
| 7 | FG dispatch with release gates, traceability graph (forward/backward), global search, QR resolve | ✅ `docs/phase-reports/phase-7.md` |
| 8 | Quality system: deviation, CAPA, change control (linked to versioned masters), FMEA, SOP control, complaints, recall | ✅ `docs/phase-reports/phase-8.md` |
| 9 | Reports (43), dashboards, controlled printouts, retention/archive, backup evidence | ✅ `docs/phase-reports/phase-9.md` |
| 10 | Validation & hardening: 15 critical tests, generated access matrix, security tests, URS/RTM/IQ/OQ/PQ package, restore/load tooling, demo data, manuals | ✅ `docs/phase-reports/phase-10.md` — release candidate **1.0.0-rc1** |
| 11 | Environmental monitoring (versioned alert/action limits, results, excursions → deviations, trending), stability studies (protocols, ledger-booked studies, pull schedule, append-only results, ICH Q1E-style evaluation, signed conclusion), costing (rate cards, lot/batch cost, variance, valuation) | ✅ `docs/phase-reports/phase-11.md` — release candidate **1.1.0-rc1** |

## Layout
```
backend/app/{api,core,models,schemas,services,repositories,workflows,security,audit,reports,integrations,utils}
frontend/src/{components,pages,layouts,services,hooks,utils,styles}
database/{migrations,seeds,mssql}   tests/{unit,integration,security,workflows,validation,performance}
docs/{architecture,validation,manuals,phase-reports,samples,api}   scripts/   docker/
```

## Quick start (development, SQLite)
```bash
cp .env.example .env                    # set MERP_SECRET_KEY, MERP_AUDIT_HMAC_KEY; MERP_DATABASE_URL=sqlite:///./merp_dev.db; MERP_COOKIE_SECURE=false
pip install -r backend/requirements-dev.txt
(cd backend && PYTHONPATH=. alembic upgrade head)
MERP_BOOTSTRAP_ADMIN_USERNAME=sysadmin MERP_BOOTSTRAP_ADMIN_PASSWORD='<strong password>' python scripts/bootstrap_admin.py
(cd frontend && npm install && npm run build)
scripts/run_dev.sh                      # http://localhost:8000  (API docs: /api/docs)
```
Production: SQL Server 2022 + reverse proxy + TLS — see `docs/manuals/installation.md`.

## Demo / training data
```bash
python database/seeds/demo_data.py      # users per role, Vendors A/B/C, materials, a released lot, a batch in process … (never on production)
```

## Tests
```bash
pip install -r backend/requirements-dev.txt
python -m pytest                                    # ~250 tests: unit, integration, security (incl. generated role×route matrix), workflows, 15 critical tests
MERP_TEST_DATABASE_URL='mssql+pyodbc://…/MERP_TEST?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes' python -m pytest   # same suite on SQL Server
cd frontend && npm run build                        # type-check + bundle
python scripts/gen_validation_docs.py --junit docs/validation/evidence/junit.xml   # regenerate URS/RTM/CS/data dictionary/SBOM/OpenAPI
python scripts/load_test.py --base http://localhost:8000 --users 50 --seconds 120 # load test (needs demo data)
python scripts/restore_test.py                                                       # backup/restore qualification helper
```

## Documentation map
| Area | Where |
|---|---|
| Architecture, design decisions, workflows, rules, RBAC, compliance mapping, data dictionary, ER | `docs/architecture/` |
| Validation package (VP, URS, FS, DS, CS, FMEA, ALCOA+, IQ/OQ/PQ, RTM, protocols, VSR draft, evidence) | `docs/validation/` |
| Phase reports (what, files, DB, API, UI, tests, limitations) | `docs/phase-reports/` |
| Manuals (installation, configuration, administrator, user, master data, purchase, troubleshooting) | `docs/manuals/` |
| Sample outputs (labels, CoA, PO, GRN, batch record, reports) | `docs/samples/` |
| API contract (OpenAPI) | `docs/api/` |
| Release notes, known defects | `docs/release-notes.md`, `docs/known-defects.md` |
