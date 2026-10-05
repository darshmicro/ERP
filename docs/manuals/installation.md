# Installation & Deployment Guide (Phase 1)

> Written for the validated-environment workflow DEV → TEST/UAT → PROD. SQL Server/ODBC/IIS/Docker steps below were **authored but not executed** in the Phase 1 build environment (SQLite + Linux only); verify them in your IQ.

## 1. Prerequisites
| Item | Recommendation |
|---|---|
| OS | Windows Server 2022 (production); Windows 11 Pro acceptable for dev/pilot |
| Python | 3.11+ (3.12 recommended) |
| Database | SQL Server 2022 **Standard** (Express's 10 GB cap is not suitable for production audit/ledger volumes); PostgreSQL support is best-effort |
| ODBC | Microsoft ODBC Driver 18 for SQL Server |
| Proxy/TLS | IIS + ARR, Caddy or nginx; certificate from your CA |
| Time | NTP/AD time sync on all servers (ALCOA "contemporaneous") |
| Node | 20+ only to build the frontend |

## 2. Database (SQL Server)
1. Create database `MERP`; collation `SQL_Latin1_General_CP1_CI_AS`; enable TDE/BitLocker per policy.
2. Run `database/mssql/01_logins_and_grants.sql` sections (create logins/users) – set secrets from your vault.
3. Set `MERP_MIGRATION_DATABASE_URL` (merp_migrator) and run `alembic upgrade head` from `backend/` (`PYTHONPATH=.`).
4. Run the GRANT/DENY section of the script (append-only tables, no DDL for the app login).
5. Set `MERP_DATABASE_URL` to the **merp_app** login.

## 3. Application (Windows, no Docker)
```powershell
py -3.12 -m venv .venv ; .\.venv\Scripts\activate
pip install -r backend\requirements.txt
copy .env.example .env      # edit; NEVER commit .env
cd frontend ; npm ci ; npm run build ; cd ..
$env:MERP_BOOTSTRAP_ADMIN_USERNAME="<id>"; $env:MERP_BOOTSTRAP_ADMIN_PASSWORD="<strong>"; python scripts\bootstrap_admin.py
```
Run as a service (NSSM/WinSW): `uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000 --workers 4` with working dir `backend`, `PYTHONPATH=.`. Put IIS-ARR/Caddy on 443 → 127.0.0.1:8000 and set `MERP_ENVIRONMENT=production`, `MERP_COOKIE_SECURE=true`. Gunicorn is for Linux/Docker only.

## 4. Docker (Linux containers)
`cp .env.example .env` (add `MSSQL_SA_PASSWORD`, `MERP_HOSTNAME`), then `docker compose -f docker/docker-compose.yml up -d --build`. After the DB is healthy, run migrations and bootstrap inside the `api` container:
`docker compose exec api sh -c "cd backend && alembic -c alembic.ini upgrade head"` and `docker compose exec -e MERP_BOOTSTRAP_ADMIN_USERNAME=... -e MERP_BOOTSTRAP_ADMIN_PASSWORD=... api python scripts/bootstrap_admin.py`.

## 5. Post-install checks (IQ seeds)
`/api/v1/health/ready` = ready · login as bootstrap admin forces password change · `/api/docs` reachable only on the internal network · audit trail shows LOGIN · `scripts`: confirm `merp_app` cannot `UPDATE audit_trail` (expect permission error).
