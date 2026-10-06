# Configuration Guide

All settings are environment variables prefixed `MERP_` (see `.env.example`). Secrets only via environment/secret store.

| Variable | Default | Meaning |
|---|---|---|
| `DATABASE_URL` | sqlite dev | SQLAlchemy URL for the **app** login |
| `MIGRATION_DATABASE_URL` | – | DDL login used by Alembic only |
| `SECRET_KEY`, `AUDIT_HMAC_KEY` | required (≥16 chars) | `AUDIT_HMAC_KEY` keys the audit hash chain. **Changing it invalidates verification of existing rows** — rotate only under change control with a documented chain-anchor |
| `COOKIE_SECURE` | true | Must be true behind HTTPS |
| `SESSION_IDLE_MINUTES` / `SESSION_ABSOLUTE_HOURS` | 15 / 8 | Automatic logout |
| `MAX_CONCURRENT_SESSIONS` | 0 (unlimited) | Oldest sessions revoked above this |
| `PASSWORD_MIN_LENGTH`, `PASSWORD_HISTORY`, `PASSWORD_MAX_AGE_DAYS` | 12, 12, 90 | Local password policy |
| `LOCKOUT_THRESHOLD`, `LOCKOUT_MINUTES` | 5, 15 | Account lockout |
| `LDAP_ENABLED`, `LDAP_SERVER_URI`, `LDAP_BIND_FORMAT` | off | AD/LDAP; users with `auth_source=LDAP` bind as `LDAP_BIND_FORMAT.format(username)` (e.g. `{username}@corp.local`). Use `ldaps://` |
| `FILE_STORAGE_PATH`, `MAX_UPLOAD_MB` | ./storage/documents, 10 | Write-once document store (put on an encrypted, backed-up volume) |

**Database-held configuration (change-controlled, reason required, audited):** `system_configuration` (e.g. `training.gate`), `number_registry` (prefix/format/reset per document type), company master, workflow definitions.
Numbering format fields: `{prefix} {year} {yy} {seq:06d}` e.g. `PO-2026-000001`.
