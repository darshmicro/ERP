# Requirements Traceability (Phase 1 seed)

| Req (prompt §) | Control | Test(s) |
|---|---|---|
| 3 Auth: local/LDAP, lockout, session, policy | `auth_service`, `providers`, `passwords` | tests/security/test_auth.py, test_ldap_provider.py |
| 6 E-signature | `services/esign.py` | tests/workflows/test_state_and_approval.py (signature, training gate, lockout, linkage) |
| 7 / 92-R9 Audit trail immutable | `audit/*`, triggers | tests/integration/test_audit_trail.py |
| 8 RBAC, SoD / 92-R11 | `security/permissions.py`, `services/sod.py`, `user_service` | tests/security/test_rbac.py, workflow tests |
| 54/55 Workflow & status engine / BR-SEC-001 | `workflows/*` | tests/workflows/* |
| 61 Numbering | `services/numbering.py` | tests/unit/test_numbering_and_passwords.py |
| 62 Error handling | `api/errors.py` | test_unhandled_error_hides_internals |
| 4 Company master/logo | `api/v1/org.py`, `services/documents.py` | tests/integration/test_company_documents.py |
| 60 / 92-R12 No overwrite of approved versions | workflow definition versioning | test_approved_definition_is_versioned_not_overwritten |
