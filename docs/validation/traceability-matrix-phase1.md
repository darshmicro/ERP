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

## Phase 2–3 additions
| Req | Control | Test(s) |
|---|---|---|
| Crit 1 Expired vendor cannot create PO (§77/§92-R1) | `vendor_qualification.standing`, `purchasing.evaluate_po` BR-PO-001 | tests/workflows/test_purchase_rules.py::test_crit_01_expired_vendor_cannot_create_po (+ job, requalification tests) |
| Crit 2 Unapproved vendor cannot purchase (R2) | BR-PO-002 | ::test_crit_02_unapproved_vendor_cannot_purchase, suspended/disqualified/inactive tests |
| Crit 3 Wrong vendor-material (R3) | BR-PO-003, `vendor_materials` | ::test_crit_03_wrong_vendor_material_combination, mapping versioning |
| Crit 8 No approval without permission | `require()` + service checks | ::test_po_approval_chain_signature_sod_and_gate_recheck |
| Crit 13 Historical specification stays linked | `versioning.version_in_force`, PO line pins | tests/workflows/test_versioned_masters.py::test_specification_flow_historical_link…, ::test_baseline_po_is_created_with_pins |
| R11 Creator cannot approve own transaction | `sod`, workflow engine | ::test_sod_creator_cannot_approve_own_po, SOD tests for vendor/material/spec/STP/mapping/qualification |
| R12 Historical data never overwritten | VersionedMixin hook; locked PO/PR/qualification | immutability tests across versioned masters, PO, qualification |
| R10 E-signature for configured approvals | `esign`, `sign_and_transition` | all approval tests assert signature records |
| §16/17 PR/PO lifecycle & audit | `purchasing`, `approval` | tests/workflows/test_purchase_requests.py |
