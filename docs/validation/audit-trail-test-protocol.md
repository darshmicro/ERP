# Audit-Trail Test Protocol

Verifies that every audited event records who/what/when/old/new/reason, that audit records cannot be altered, and that tampering is detectable (21 CFR 11.10(e), Annex 11 §9).

## Automated evidence
| Check | Test |
|---|---|
| Field-level audit with old/new value, user, role, IP, reason | `tests/integration/test_audit_trail.py::test_field_level_audit_with_old_new_user_reason` |
| A change without a reason is refused and rolled back | `…::test_master_update_without_reason_is_rejected_and_rolled_back` |
| Business change and audit row share one transaction | `…::test_audit_written_in_same_transaction_rollback_removes_both` |
| Passwords never appear | `…::test_password_hash_is_redacted_in_audit`, `tests/security/test_hardening.py::test_no_credential_material_in_any_api_response` |
| ORM refuses UPDATE/DELETE of audit rows | `…::test_audit_rows_cannot_be_updated_or_deleted_via_orm` |
| Database triggers refuse raw UPDATE/DELETE | `…::test_audit_rows_cannot_be_modified_with_raw_sql_db_trigger`, `tests/validation/test_critical_15.py::test_crit_09_…` |
| No API verb modifies the audit trail | `…::test_normal_roles_have_no_audit_write_endpoints` |
| HMAC hash chain verifies and detects an altered or removed row | `…::test_hash_chain_verifies_and_detects_tampering`, `…::test_hash_chain_detects_removed_tail`, `test_crit_09` (privileged tamper) |
| Physical delete of audited masters refused | `…::test_physical_delete_of_audited_record_refused` |
| Append-only evidence tables (ledger, signatures, status history, security events, report runs, backups, …) | `tests/workflows/test_state_and_approval.py::test_ledger_style_append_only_tables_refuse_update`, `test_reports.py` |

## Manual verification (site)
| # | Step | Expected | P/F |
|---|---|---|---|
| AT-01 | Create, edit (with reason) and attempt to delete a vendor; open *Audit Trail* filtered on the record | CREATE and field-level UPDATE rows with old/new, your user, role, IP, reason; delete refused and logged | |
| AT-02 | Perform an e-signature (e.g. vendor approval) | Audit row `STATUS_CHANGE` linked to the signature id; `/esignatures` shows name, meaning, time | |
| AT-03 | Export the audit trail (Excel) | Header with filters, user, time; export itself audited | |
| AT-04 | Run **Verify chain** (QA Head) | `ok: true`, row count shown | |
| AT-05 | **Tamper simulation on the validation database only:** as DBA disable the trigger on `audit_trail`, change one `new_value`, run Verify chain, then restore the trigger from the migration script | Verification reports `ok: false` and the first bad audit id; document, then restore the database from backup | |
| AT-06 | Review audit rows for a failed login, a lockout, an RBAC denial and a blocked PO | Present in audit trail / security events with rule ids | |
| AT-07 | Attempt UPDATE/DELETE on `audit_trail` as `merp_app` in SQL Server Management Studio | Permission denied / trigger error | |
