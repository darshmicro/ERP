# Installation Qualification (IQ) Protocol

**Purpose:** document that GMP-MERP and its supporting infrastructure are installed according to the approved specification (`design-specification.md`, `installation.md`).
**Executed by the site.** Record actual values, tester, date and evidence reference; deviations go to the VSR.

| Field | Entry |
|---|---|
| System / release version | |
| Environment (PROD / TEST) | |
| Protocol executed by / date | |
| Reviewed by / date | |

## 1. Prerequisites
Approved VP and URS; infrastructure change approved; installation SOP available; service accounts created by the DBA.

## 2. Test steps
| # | Check | Acceptance criterion | Actual | Pass/Fail | Evidence |
|---|---|---|---|---|---|
| IQ-01 | Server OS and patch level | Supported OS (Windows Server 2019+/Linux), vendor-supported, patched per site policy | | | |
| IQ-02 | Time synchronisation | NTP/domain time source configured; clock offset < 1 s (`w32tm /query /status` or `chronyc tracking`) | | | |
| IQ-03 | SQL Server version | SQL Server 2019/2022, collation `SQL_Latin1_General_CP1_CI_AS` or site standard; PostgreSQL only if approved | | | |
| IQ-04 | ODBC driver | Microsoft ODBC Driver 18 for SQL Server installed | | | |
| IQ-05 | Database accounts | `merp_migrator` (DDL, deployment only), `merp_app` (runtime DML), `merp_report_ro` per `database/mssql/01_logins_and_grants.sql`; **no application account is `db_owner`** | | | |
| IQ-06 | Least privilege | As `merp_app`: `INSERT INTO audit_trail` succeeds; `UPDATE/DELETE audit_trail`, `CREATE TABLE` fail with *permission denied* (repeat for all 20 append-only tables) | | | |
| IQ-07 | Software package integrity | Release package SHA-256 equals the value in the release notes; `pip freeze`/`npm ls` match `sbom.md` | | | |
| IQ-08 | Python / Node runtime | Python 3.11+, backend dependencies installed from the pinned list; frontend built (`npm run build`) | | | |
| IQ-09 | Configuration | `.env` created from `.env.example`; `MERP_ENVIRONMENT=production`; strong `MERP_SECRET_KEY` and `MERP_AUDIT_HMAC_KEY` (≥ 32 random chars, stored in the secret store, backed up); cookie secure; debug off. The application refuses to start with weak/missing production settings | | | |
| IQ-10 | TLS | Reverse proxy (Caddy/IIS/nginx) serves HTTPS with a valid certificate; HTTP redirects; TLS ≥ 1.2; HSTS header present | | | |
| IQ-11 | Database migration | `alembic upgrade head` completes as `merp_migrator`; `alembic current` = release head (0010); 127 tables; 20 `INSTEAD OF` triggers present (`SELECT name FROM sys.triggers`) | | | |
| IQ-12 | Baseline seed | `scripts/bootstrap_admin.py` creates the first administrator; roles, permissions, SoD rules, workflows, numbering and retention defaults exist (compare with `configuration-specification.md`) | | | |
| IQ-13 | Services | Application service starts automatically, runs under a non-privileged account; `/api/v1/health/ready` returns `ready` | | | |
| IQ-14 | Scheduler | Exactly one of: in-process scheduler enabled on one instance **or** `scripts/run_jobs.py` scheduled (Task Scheduler/cron) daily | | | |
| IQ-15 | Logging | `logs/` contains application, security and error logs; log directory protected and monitored; rotation configured | | | |
| IQ-16 | Backup configuration | Database full + log (or differential) backups scheduled with CHECKSUM; document-store backup scheduled; backup account rights verified; retention per site policy | | | |
| IQ-17 | Document store | `MERP_DOCUMENT_DIR` exists, writable only by the service account, included in backup | | | |
| IQ-18 | Network | Only the reverse proxy port is reachable from user networks; DB port reachable only from the application server; LDAP/AD (if used) reachable over LDAPS | | | |
| IQ-19 | Antivirus / hardening | Site baseline applied; exclusions documented for DB and document store | | | |
| IQ-20 | Browser | Supported browsers (Edge/Chrome current) load the UI; Part 11 banner/footer visible | | | |

## 3. Deviations
| # | Description | Impact | Resolution | Closed by/date |
|---|---|---|---|---|

## 4. Conclusion
IQ acceptable / not acceptable: ______  Signature (name, role, date): ______  Reviewer (QA): ______
