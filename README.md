# GMP-MERP — GMP Material & Manufacturing ERP

Web-based ERP for GMP-regulated biological/antisera manufacturing: Vendor → Purchase → Receipt/GRN → Quarantine → QC/QA release → Inventory → Manufacturing → FG release → Dispatch, with full traceability.

> **Regulatory position.** This software is designed to *support* 21 CFR Part 11, EU GMP Annex 11 and ALCOA+ through technical controls (unique users, RBAC, segregation of duties, immutable audit trail, electronic signatures, controlled workflows). It is **not** "certified" or "compliant" by itself: compliance requires site validation (CSV/CSA), SOPs, trained users, qualified infrastructure and periodic review. See `docs/architecture/06-compliance-mapping.md`.

## Status
| Phase | Scope | State |
|---|---|---|
| 0 | Architecture, DB design, RBAC, workflows, validation strategy | ✅ `docs/architecture/` |
| 1 | Platform foundation (IAM, audit trail, e-signature, numbering, status/workflow engines, company master, app shell) | ✅ this release — see `docs/phase-reports/phase-1.md` |
| 2–10 | Master data → Purchase → Warehouse → QC/LIMS → Manufacturing → Dispatch → Quality → Reports → Validation | planned (`docs/architecture/09-development-roadmap.md`) |

## Layout
```
backend/app/{api,core,models,schemas,services,repositories,workflows,security,audit,reports,integrations,utils}
frontend/src/{components,pages,layouts,services,hooks,utils,styles}
database/{migrations,seeds,mssql}   tests/{unit,integration,security,workflows}
docs/{architecture,URS,validation,SOP,manuals,phase-reports}   scripts/   docker/
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

## Tests
```bash
pip install -r backend/requirements-dev.txt
python -m pytest            # unit, integration, security, workflow tests
cd frontend && npm run build   # type-check + bundle
```
