# Administrator Manual (Phase 1)

**Principle:** the System Administrator manages access and technical configuration; it holds **no GMP approval authority** (SOD-09 prevents combining it with approval roles).

## Users
* *Users → New user*: unique User ID (never reused), name, source (Local or AD/LDAP), a **reason**. Local users get a one-time temporary password and must change it at first login.
* Open a user to assign/remove roles (reason required; you cannot change your own roles), deactivate/activate (sessions are revoked), unlock, reset password.
* Access expiry (`access_expiry`) and role validity (`valid_to`) end access automatically.

## Roles & permissions
Permissions are `module.resource.action`. Edit a role's permission set (reason required, audited). Administrator roles cannot be given approve/release/reject/sign permissions.

## Company
Company name/logo/licences/header/footer/date-time formats; every change needs a reason and is audited. The logo and name appear on the login page, dashboard and (later phases) all GMP documents.

## Numbering & configuration
Change prefix/format/reset per document type; counters never go backwards and numbers are never re-issued.

## Workflows
Create a workflow version (steps with role, min approvals, e-signature meaning, SLA). A **QA role must approve it with an electronic signature** before it takes effect; the author cannot approve their own definition (SOD-12). Approved versions are immutable.

## Audit & security
*Audit Trail* (search, filter, export CSV — exports are themselves audited). QA roles can **Verify integrity** (re-computes the HMAC hash chain). *Security Events*: failed logins, lockouts, authorisation denials, SoD violations, CSRF rejects.

## Backup & recovery (Phase 1 guidance)
Back up the database (full nightly, differential, log 15 min) **and** the document store together; verify with `RESTORE VERIFYONLY` + `/audit-trail/verify` after every test restore. Proposed RPO ≤ 15 min / RTO ≤ 4 h (agree per site). An administrator backup-status screen follows in Phase 9.
