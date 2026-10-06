# Security Test Protocol

Scope: the application, its API and database access model. Automated tests run in CI (`tests/security/`, `tests/validation/`); manual items are for the site's qualification and periodic review.

## 1. Automated coverage
| Area | Controls verified | Tests |
|---|---|---|
| Authentication | generic failure message, lockout, idle timeout, forced password change, password policy/history, login rate limit, LDAP/AD provider (fail-closed), expired access | `test_auth.py`, `test_ldap_provider.py`, `test_rbac.py::test_expired_access_blocks_login` |
| Session | HttpOnly + SameSite cookie, server-side invalidation at logout, revocation on deactivation | `test_hardening.py::test_session_cookie_flags_and_logout_invalidates_session`, `test_rbac.py::test_user_deactivation_revokes_sessions` |
| CSRF | every state-changing request needs the per-session token | `test_auth.py::test_csrf_required_on_state_change`, `test_hardening.py::test_state_changing_requests_without_csrf_token_are_refused_everywhere` |
| Authorisation | **generated** role × route matrix (all routes, all roles); unauthenticated = 401 on every non-public route; admin holds no GMP authority; SoD-09/10 | `test_access_matrix.py`, `test_rbac.py` |
| Injection | SQL injection payloads in every search/filter/report parameter are inert (parameterised ORM); no stack traces/SQL in errors | `test_hardening.py::test_sql_injection_payloads_in_every_search_and_filter_are_inert`, `…::test_unknown_and_malformed_identifiers_do_not_leak_internals` |
| Mass assignment | status/system columns cannot be set via payloads (BR-SEC-001) | `test_hardening.py::test_status_and_system_columns_cannot_be_mass_assigned`, `test_rbac.py::test_status_not_writable_via_api_payload` |
| File upload | extension/magic-byte/size validation, traversal names, SVG/HTML refused, hash-verified download | `test_hardening.py::test_upload_validation_…`, `test_company_documents.py` |
| Data exposure | no credential material in any API response; audit redaction | `test_hardening.py::test_no_credential_material_in_any_api_response` |
| XSS / headers | JSON-only API, CSP `default-src 'self'`, `frame-ancestors 'none'`, nosniff, no-store | `test_hardening.py::test_stored_script_payloads_…`, `test_auth.py::test_security_headers_and_correlation_id` |
| Error handling | unhandled errors return a reference, not internals; out-of-range identifiers are 422 not 500 | `test_auth.py::test_unhandled_error_hides_internals`, `test_hardening.py::…malformed…` |
| Database | append-only triggers; least-privilege grants script | audit tests, IQ-05/06 |

## 2. Manual checks (site)
| # | Check | Expected | P/F |
|---|---|---|---|
| SEC-01 | TLS scan (e.g. `testssl.sh`) of the public endpoint | TLS ≥ 1.2, no weak ciphers, HSTS | |
| SEC-02 | Review response headers in the browser | CSP, X-Frame-Options, nosniff, Referrer-Policy present | |
| SEC-03 | Verify secrets are not in the repository, image or logs | None found | |
| SEC-04 | Dependency vulnerability scan of `sbom.md` components (`pip-audit`, `npm audit`) | No unresolved high/critical, or risk-accepted in writing | |
| SEC-05 | Attempt access to another department's PR / record by changing ids | Refused / not found | |
| SEC-06 | Role recertification: compare `reports/user-access` with the HR list | No orphaned or excessive accounts | |
| SEC-07 | Review `security_event` for the test period | All blocked actions explained | |
