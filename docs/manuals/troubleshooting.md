# Troubleshooting Guide

| Symptom | Likely cause | What to do |
|---|---|---|
| "Session expired" / sent to login | 15 min idle or absolute 8 h limit; session revoked by an administrator | Log in again |
| "Account locked" | 5 wrong passwords | Wait the lockout time or ask the administrator to unlock |
| "You are not authorised…" (403) | Role lacks the permission | Ask the administrator; the denial is in Security Events |
| "CSRF token missing or invalid" | Browser kept an old tab after logout/login | Reload the page |
| Message with a **rule id** (BR-…, SOD-…) | Business rule or segregation-of-duties block | Read the message; fix the condition (e.g. renew vendor qualification, release the lot, ask a different approver) |
| "This record was changed by another user" (409) | Concurrent edit | Reload and repeat the action |
| "The transaction conflicts with existing data" (409) | Duplicate number/code or constraint | Check for an existing record; contact support with the `ERR-` reference if unexpected |
| `ERR-yyyy-nnnnnn` reference | Unhandled application error | Give the reference to the administrator → *Error log*; correlation id is in the logs |
| PDF/Excel export is slow | Very large range | Narrow the dates; exports are capped (50 000 rows) |
| Requests time out under load, log shows `QueuePool limit … reached` | Connection pool smaller than worker threads | Increase `MERP_DB_POOL_SIZE`/`MERP_DB_MAX_OVERFLOW`; add workers |
| Application refuses to start in production | Weak/missing `SECRET_KEY`/`AUDIT_HMAC_KEY`, insecure cookies, debug | Fix configuration (see `configuration.md`) |
| "Verify chain" reports `ok: false` | Audit rows were altered/removed outside the application, wrong HMAC key, or a partial restore | Stop; preserve evidence; compare with the last verified backup; raise a data-integrity deviation |
| Backup page red | Backup record older than limit / no restore test | Run the backup/restore test and record it |
| Labels do not print | Browser pop-up blocker for the PDF window | Allow pop-ups for the site |
| Jobs did not run | Scheduler not enabled / cron missing | Enable on one instance or schedule `scripts/run_jobs.py`; run manually from *System* |
| `database is locked` (SQLite) | Development database with concurrent writers | Use SQL Server for anything but single-user development |
| Cannot sign: "Signature authentication failed" | Wrong password (counts toward lockout) | Re-enter carefully; AD users use the Windows password |
