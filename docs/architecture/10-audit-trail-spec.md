# Audit Trail Specification (implemented in Phase 1)

**Table `audit_trail` (append-only):** `id, occurred_at (UTC), tz_name, module, entity, record_id, action, field_name, old_value, new_value, user_id, user_name, role_name, session_id, ip_address, device_info, reason, signature_id, correlation_id, prev_hash, row_hash`.

| Mechanism | Detail |
|---|---|
| Capture | ORM hooks (`app/audit/hooks.py`) on models using `AuditedMixin`: INSERT → one `CREATE` row (field `*`, JSON snapshot); UPDATE → one row per changed field with old/new; explicit events for LOGIN, LOGOUT, LOGIN_FAILED, E_SIGNATURE, STATUS_CHANGE, EXPORT, UPLOAD, DOWNLOAD, PASSWORD_CHANGE/RESET, WORKFLOW_* |
| Atomicity | Entries are written in the **same DB transaction** (`before_commit`); failure of audit writing rolls back the business change (BR-AUD-002). Exceptions: failed-login/security events are written in an independent transaction so they persist after rejection |
| Reason | `__reason_required__` models (users, roles, company, config, numbering, workflow definitions…) reject UPDATE without reason (`X-Change-Reason` header or body `reason`) |
| Redaction | `__audit_sensitive__` fields (e.g. `password_hash`) are audited as `[REDACTED]` |
| Immutability | (1) ORM refuses UPDATE/DELETE of audit/AO objects; (2) DB triggers (SQLite/PostgreSQL/SQL Server) raise on UPDATE/DELETE; (3) `merp_app` has DENY UPDATE/DELETE; (4) HMAC-SHA256 hash chain keyed by `MERP_AUDIT_HMAC_KEY` — `row_hash = HMAC(key, prev_hash ‖ canonical(row))`; chain head row records last hash and row count so deletion of tail rows is detected |
| Verification | `GET /api/v1/audit-trail/verify` (permission `audit.trail.verify`) recomputes the chain |
| Concurrency | Writers first `UPDATE audit_chain_head` (row lock) so the chain is linear; lock is held only for the short commit window |
| Access | `audit.trail.read/export` (QA, Admin, Auditor, Management-read). No write API exists |
| Delete | No delete function. Retention/archival is a Phase 9 approved-policy procedure |
| Not audited by field | Volatile security counters (`failed_attempts`, `locked_until`, `last_login_at`) → recorded as security events |
**Known limits:** a DBA with DDL rights can drop triggers and re-compute a chain only if they also hold the HMAC key — keep the key outside the DB host; periodic off-box export of `(row_count,last_hash)` anchors is recommended (SOP).
