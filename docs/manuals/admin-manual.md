# Administrator Manual

**Principle:** the System Administrator manages access and technical configuration; it holds **no GMP approval authority** (SOD-09 prevents combining it with approval roles).

## Users
* *Users → New user*: unique User ID (never reused), name, source (Local or AD/LDAP), a **reason**. Local users get a one-time temporary password and must change it at first login.
* Open a user to assign/remove roles (reason required; you cannot change your own roles), deactivate/activate (sessions are revoked), unlock, reset password.
* Access expiry (`access_expiry`) and role validity (`valid_to`) end access automatically.

## Roles & permissions
Permissions are `module.resource.action`. Edit a role's permission set (reason required, audited). Administrator roles cannot be given approve/release/reject/sign permissions. Phase 11 added the roles **Costing Analyst** and **Finance Head**; environmental monitoring and stability permissions sit on the QC and QA roles, and administrators hold no costing, EM or stability rights.

## Company
Company name/logo/licences/header/footer/date-time formats; every change needs a reason and is audited. The logo and name appear on the login page, dashboard and (later phases) all GMP documents.

## Numbering & configuration
Change prefix/format/reset per document type; counters never go backwards and numbers are never re-issued.

## Workflows
Create a workflow version (steps with role, min approvals, e-signature meaning, SLA). A **QA role must approve it with an electronic signature** before it takes effect; the author cannot approve their own definition (SOD-12). Approved versions are immutable.

## Audit & security
*Audit Trail* (search, filter, export CSV — exports are themselves audited). QA roles can **Verify integrity** (re-computes the HMAC hash chain). *Security Events*: failed logins, lockouts, authorisation denials, SoD violations, CSRF rejects.

## Backup, restore and the backup status page (Retention & Backup → *Backup status*)
1. **Schedule** (SQL Server Agent / Task Scheduler): full backup nightly with `CHECKSUM`, differential every 4–6 h or log backups every 15 min, document store backup (the files must be restorable together with the database). Keep copies off-site/immutable per site policy. Proposed targets RPO ≤ 15 min / RTO ≤ 4 h (agree per site).
2. **Record evidence** after each backup job (or let your backup script call the API): *Record backup / restore test* (type FULL / DIFFERENTIAL / LOG / DOCUMENTS / RESTORE_TEST, result, location, size, SHA-256, tool). Records are append-only. Needs `backup.status.record` (System Administrator, QA Head).
3. **Alerts:** the page turns red when the newest successful database backup is older than `backup.max_age_hours` (default 26) or no restore test was recorded within `backup.restore_test_days` (default 180).
4. **Restore test (quarterly or per SOP):** `python scripts/restore_test.py` (uses an administrative login, never the application login) backs the database up with CHECKSUM, runs `RESTORE VERIFYONLY`, restores into a scratch database, compares every table's row count, **verifies the audit-trail hash chain on the restored copy**, measures the elapsed time (RTO evidence) and drops the scratch database. Add `--record-url … --user … --password …` to record the result automatically.
5. After any real restore, run **Audit Trail → Verify integrity**; re-enable the daily jobs; the audit HMAC key must be the one that was in force when the rows were written.

## Daily jobs
Vendor-qualification expiry and alerts, lot expiry/retest alerts, overdue CAPA and SOP-review alerts, overdue environmental-monitoring points, stability pull due alerts and closing of missed stability pulls (with a deviation), run as the audited user `SYSTEM`. Enable the in-process scheduler (`MERP_SCHEDULER_ENABLED=true`) on **one** instance, or schedule `python scripts/run_jobs.py` daily (Task Scheduler/cron). Jobs are idempotent. Manual run: *System → Run jobs* (`config.job.run`).

## Retention and archive (Retention & Backup → *Retention & archive*)
* Ten record types have a retention period (years) and a regulatory basis shown on the page. Periods can only be **extended** here; shortening needs a change control and DBA action.
* **Legal hold** (reason required) freezes a type — it cannot be archived.
* **Archive** (QA Head): produces a hashed XLSX package of the records older than the cut-off and stores it as a write-once controlled document; download re-verifies the hash. The application **never deletes** GMP records. Removing archived rows from the live database is a separate DBA activity under change control after the archive is verified.

## Performance tuning
`MERP_DB_POOL_SIZE` / `MERP_DB_MAX_OVERFLOW` (per worker; default 25/35). Keep `pool_size + overflow ≥ worker threads (40)`. Run several uvicorn/gunicorn workers behind the reverse proxy; sessions are database-backed so any worker can serve any user. Qualify with `scripts/load_test.py`.

## Controlled copies
Every export/print is logged (Retention & Backup → *Controlled copies*) with a copy number and SHA-256; use *Verify a printout* to check a file presented in an audit.

## Reports and dashboards access
Reports are permission-gated individually (each report requires the read permission of the data it shows plus `reports.export.run` to export). Dashboards need `dashboard.<management|qc|qa|warehouse>.read`. Grant through *Roles & permissions* (reason required).

## Upgrading
Stop the application → full backup → `alembic upgrade head` as `merp_migrator` → restart → run the automated regression (`pytest`) on a copy first → regenerate `docs/validation/rtm.md` → release record. Migrations 0001–0009 are verified up/down/up on SQL Server. Re-run `scripts/bootstrap_admin.py` (idempotent) after an upgrade so newly introduced permissions, SoD rules, workflows, numbering and retention defaults are seeded; existing role customisations are never undone.
