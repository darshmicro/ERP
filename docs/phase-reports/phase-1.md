# Phase 1 Report — Platform Foundation

## What was implemented
* **Identity & access:** users (unique, never-reused IDs), roles, 40 permissions (`module.resource.action`), role assignment with validity/disable/revoke (reason mandatory), access expiry, temporary disable, local auth (Argon2id, policy, history, ageing, forced first-login change), AD/LDAP provider (`ldap3`, fails closed, refuses empty password), server-side sessions (idle + absolute timeout, concurrent-session cap, revoke on password change/deactivation), lockout, login rate limit, CSRF token, security headers.
* **Segregation of duties:** data-driven `sod_rule` + `record_action` history; SOD-10 (no self role/deactivation), SOD-09 (admin roles cannot hold approve/release/reject/sign), SOD-12 (workflow author ≠ approver) enforced; seeded rules for later modules (PO, QC, QA, vendor, CAPA…).
* **Audit trail:** field-level old/new capture via ORM hooks, same-transaction write, reason enforcement, redaction, append-only (ORM + DB triggers + DENY grants), HMAC hash chain + head anchor, verify/export/search APIs. Details: `docs/architecture/10-audit-trail-spec.md`.
* **Electronic signatures:** re-authentication per signature, permission + training gate, meanings, record hash/manifest, append-only. `docs/architecture/11-electronic-signature-spec.md`.
* **Status engine:** `StateMachine`/`transition()`; direct writes to status columns refused (BR-SEC-001); `gmp_status_history`.
* **Approval workflow engine:** versioned definitions (QA e-signature to approve, supersede, immutable), instances pinned to version, min-approvals, role checks, SoD, reject routes, SLA overdue detection, completion hooks.
* **Numbering:** configurable prefix/format/yearly reset, atomic allocation, no duplicates under concurrency.
* **Company master** (name, licences, header/footer, formats, validated logo upload), write-once hashed document store, notifications model/API, dashboard cards (10 required cards; later-phase cards shown as unavailable), error handling with `ERR-YYYY-NNNNNN` references, separated application/security logs, health endpoints.
* **Frontend (React+TS+Bootstrap):** login, forced password change, sidebar layout with permission-aware menu and company branding, dashboard, users, roles/permissions, audit trail (filters, keyset paging, verify, export), security events, company, numbering & config, workflows with e-signature dialog, reason dialogs everywhere.
* **Ops:** Alembic baseline migration (incl. immutability triggers), bootstrap-admin script (no default/hidden accounts), `.env.example`, Dockerfile/compose/Caddy, MSSQL least-privilege script, Windows/Docker install, configuration, admin and user guides.

## Files (principal)
`backend/app/{core,models,audit,security,services,workflows,api}/…` · `backend/alembic.ini` · `database/migrations/versions/0001_phase1_baseline.py` · `database/mssql/01_logins_and_grants.sql` · `frontend/src/**` · `tests/**` · `docker/**` · `docs/{manuals,architecture/10-11,phase-reports}` · `scripts/*`.

## Database changes
28 tables: company, plant, department, users, role, permission, role_permission, user_role, user_session, password_history, training_record, sod_rule, audit_trail, audit_chain_head, e_signature, security_event, gmp_status_history, record_action, error_log, number_registry, number_sequence, system_configuration, notification, document, workflow_definition/step/instance/transaction. Migration `0001`.

## API (all under `/api/v1`, OpenAPI at `/api/docs`; 36 paths)
`auth/*`, `users*`, `roles*`, `permissions`, `training-records`, `audit-trail[/export|/verify]`, `security-events`, `esignatures`, `company[/branding|/logo]`, `plants`, `numbering*`, `config*`, `workflows/definitions*`, `dashboard/summary`, `notifications*`, `health/*`.

## Tests performed / results
`python -m pytest` → **66 passed** (SQLite): authentication/lockout/session/CSRF/rate-limit, RBAC & SoD, reason enforcement, audit capture/immutability/hash-chain tamper detection (row edit & tail deletion), e-signature (wrong password, lockout, permission, training gate, linkage), status engine, approval chains, numbering concurrency (6 threads × 5), Alembic up/down/up + trigger presence, LDAP provider (stub), upload validation, error masking. Frontend: `tsc` + `vite build` pass; manual Playwright smoke (login → forced password change → dashboard → audit → users) passed.

## Self-review (spec §100)
| Question | Result |
|---|---|
| Can users bypass controls? | Permission enforced per route; status columns not writable from payloads or ORM; SoD enforced in service layer |
| Records silently changed? | No: audit same-transaction, UPDATE needs reason on masters, audit/signature/history append-only at ORM+DB |
| Audit complete / old values retained / signatures linked? | Yes for Phase 1 entities; signature id stored in audit & status history |
| Another user's data / permission bypass? | No IDOR surface yet (no per-user data besides notifications, which check owner) |
| FKs / duplicates / atomicity? | Unique business keys, FKs, single-transaction units of work |
| Usability | Reasons/signature prompts are explicit; no UI usability test yet |
Fixes made during review: self-service password change no longer demands a reason; circular FK DDL removed (actor ids are plain ints); SPA fallback made test-independent.

## Known limitations / assumptions
1. Built and tested on **Python 3.11 + SQLite**. SQL Server/PostgreSQL trigger DDL, the grants script, Alembic on MSSQL, ODBC, Docker images and IIS steps are **authored but not executed**; they must be verified in IQ/CI with an MSSQL container.
2. LDAP/AD verified only against a stub; needs a real directory test.
3. Row-level security / site scoping, multi-site UI, and repositories layer are not yet used (services query directly; `site_id` to be added with Phase 2 transactional tables).
4. Email delivery, notification producers, session-management screens (`iam.session.*` permissions exist, endpoints not yet), access-recertification report, training-record UI, backup-status screen and retention policies are deferred (Phases 4/9).
5. SOD-09 exception path (QA-signed exception) not implemented — hard block.
6. Audit chain-head locking serialises audit commits (short window); acceptable for 50 users, to be load-tested in Phase 10.
7. `/api/docs` is unauthenticated — restrict at the proxy in production. Rate limiter is per-process (use proxy limiter with multiple workers).
8. Audit timestamps stored UTC; UI shows browser-local time with zone; site-timezone rendering for printed documents arrives with the report engine.
9. Chain HMAC key rotation requires a documented anchor procedure (SOP pending).

## Next: Phase 2 — Master data
Units, material types/categories, material master, vendor master + documents, versioned specification/STP/sampling plan, warehouse/location hierarchy, equipment & calibration, customers, controlled Excel import, document attachments — each with change-control/version rules and RBAC/audit.
