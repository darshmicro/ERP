# Penetration-Test Checklist (for the site's tester)

Agree scope and rules of engagement in writing; test only the validation/test environment loaded with demo data (`database/seeds/demo_data.py`). Findings are rated by CVSS and tracked as deviations.

| Category | Checks |
|---|---|
| **Authentication** | credential stuffing against the rate limiter and lockout; username enumeration (response/timing differences); weak-password acceptance; password reset/temporary-password handling; LDAP injection (if AD enabled); session fixation; token entropy; concurrent-session limit |
| **Session management** | cookie flags; logout invalidation; idle/absolute timeout; CSRF bypass attempts (missing/other-user token, GET state change, JSON content-type tricks) |
| **Authorisation** | vertical escalation (call admin routes as each role — see generated matrix); horizontal (IDOR on ids of PR/PO/GRN/lot/dispatch/document); SoD bypass (same user performing both steps through different endpoints); forced browsing of `/api/docs` in production (should be disabled or protected) |
| **Input handling** | SQL injection (all query/path/body parameters; second-order via names); stored/reflected XSS in names/descriptions (UI rendering); template/CSV injection in Excel/CSV exports (cells starting with `= + - @`); XXE/zip-bomb in `.xlsx` import; oversized/malformed JSON; Unicode normalisation of usernames |
| **File handling** | polyglot files, double extensions, MIME spoofing, path traversal in names, SVG/HTML upload, large uploads, document download access control, hash verification |
| **Business-logic abuse** | race conditions on numbering, stock issue and dispatch reservation; negative/huge quantities; decimal rounding abuse; back-dating; replaying signed requests; skipping states via direct API calls; cancelling after receipt; re-using a signature across records |
| **Data protection** | secrets in logs/errors; backups readable by non-admins; DB account privileges (`db_owner`?); audit-trail tampering with DBA rights (detection by the hash chain); document store permissions |
| **Infrastructure** | exposed ports, TLS configuration, HTTP verbs, CORS, security headers, server banners, default accounts, outdated components |
| **Denial of service (agree first)** | expensive reports/exports with large ranges, search wildcards, pagination limits, login flood against the rate limiter |

Deliverables: report with reproduction steps, severity, recommendation and retest evidence; summary appended to the VSR.

### Pre-assessed notes from the supplier's own testing
* Parameterised queries throughout; no raw SQL built from input (reports use SQLAlchemy expressions).
* Excel/CSV exports neutralise formula injection (text beginning with `=`, `+`, `-`, `@`, TAB or CR is prefixed with an apostrophe) — verified by `tests/security/test_hardening.py::test_exports_neutralise_spreadsheet_formula_injection`.
* `/api/docs` is enabled by default; disable at the reverse proxy in production.
