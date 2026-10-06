# Requirements Traceability Matrix (RTM)

Generated 2026-10-05 21:21 UTC from `scripts/validation_requirements.py` and the automated test inventory. Result columns = outcome in `docs/validation/evidence/junit.xml` (SQLite development database) and `junit-sqlserver-*.xml` (SQL Server 2022).

URS → business rule → automated test (OQ evidence) → result. Every referenced test was verified to exist by collection; the generator aborts otherwise.

## Security

| URS | Impact | Rules | Test (path::function) | SQLite | SQL Server |
|---|---|---|---|---|---|
| URS-IAM-01 | Critical | BR-SEC-002 | `tests/security/test_auth.py::test_login_logout_and_me` | PASS | PASS |
|  |  |  | `tests/security/test_auth.py::test_unknown_user_and_bad_password_give_same_generic_error` | PASS | PASS |
|  |  |  | `tests/security/test_ldap_provider.py::test_ldap_user_logs_in_with_directory_password` | PASS | PASS |
|  |  |  | `tests/security/test_ldap_provider.py::test_ldap_disabled_fails_closed` | PASS | PASS |
| URS-IAM-02 | Critical | BR-SEC-002 | `tests/security/test_auth.py::test_lockout_after_threshold_and_events_logged` | PASS | PASS |
|  |  |  | `tests/security/test_auth.py::test_idle_timeout_expires_session` | PASS | PASS |
|  |  |  | `tests/security/test_auth.py::test_must_change_password_blocks_other_endpoints` | PASS | PASS |
|  |  |  | `tests/security/test_auth.py::test_password_policy_and_history` | PASS | PASS |
|  |  |  | `tests/security/test_auth.py::test_login_rate_limit` | PASS | PASS |
| URS-IAM-03 | Critical | BR-SEC-001 | `tests/security/test_access_matrix.py::test_every_route_requires_authentication` | PASS | PASS |
|  |  |  | `tests/security/test_access_matrix.py::test_generated_role_by_route_permission_matrix` | PASS | PASS |
|  |  |  | `tests/security/test_rbac.py::test_unauthorised_user_gets_403_and_event_logged` | PASS | PASS |
|  |  |  | `tests/integration/test_master_data.py::test_role_access_matrix_phase2` | PASS | PASS |
| URS-IAM-04 | Critical | BR-SOD-001 | `tests/security/test_access_matrix.py::test_admin_roles_hold_no_gmp_approval_authority` | PASS | PASS |
|  |  |  | `tests/security/test_rbac.py::test_admin_cannot_hold_gmp_approval_role_sod09` | PASS | PASS |
|  |  |  | `tests/security/test_rbac.py::test_cannot_change_own_roles_sod10` | PASS | PASS |
|  |  |  | `tests/validation/test_critical_15.py::test_crit_11_creator_cannot_approve_own_transaction` | PASS | PASS |
| URS-IAM-05 | Critical | BR-SEC-001 | `tests/security/test_auth.py::test_csrf_required_on_state_change` | PASS | PASS |
|  |  |  | `tests/security/test_hardening.py::test_sql_injection_payloads_in_every_search_and_filter_are_inert` | PASS | PASS |
|  |  |  | `tests/security/test_hardening.py::test_status_and_system_columns_cannot_be_mass_assigned` | PASS | PASS |
|  |  |  | `tests/security/test_hardening.py::test_upload_validation_rejects_disguised_oversized_and_traversal_files` | PASS | PASS |
|  |  |  | `tests/security/test_hardening.py::test_no_credential_material_in_any_api_response` | PASS | PASS |
|  |  |  | `tests/security/test_hardening.py::test_session_cookie_flags_and_logout_invalidates_session` | PASS | PASS |
|  |  |  | `tests/security/test_hardening.py::test_state_changing_requests_without_csrf_token_are_refused_everywhere` | PASS | PASS |
|  |  |  | `tests/security/test_auth.py::test_unhandled_error_hides_internals` | PASS | PASS |

## Audit trail

| URS | Impact | Rules | Test (path::function) | SQLite | SQL Server |
|---|---|---|---|---|---|
| URS-AUD-01 | Critical | BR-AUD-002 | `tests/integration/test_audit_trail.py::test_field_level_audit_with_old_new_user_reason` | PASS | PASS |
|  |  |  | `tests/integration/test_audit_trail.py::test_audit_written_in_same_transaction_rollback_removes_both` | PASS | PASS |
|  |  |  | `tests/integration/test_audit_trail.py::test_master_update_without_reason_is_rejected_and_rolled_back` | PASS | PASS |
| URS-AUD-02 | Critical | BR-AUD-001 | `tests/validation/test_critical_15.py::test_crit_09_audit_trail_cannot_be_modified_or_deleted` | PASS | PASS |
|  |  |  | `tests/integration/test_audit_trail.py::test_audit_rows_cannot_be_modified_with_raw_sql_db_trigger` | PASS | PASS |
|  |  |  | `tests/integration/test_audit_trail.py::test_hash_chain_verifies_and_detects_tampering` | PASS | PASS |
|  |  |  | `tests/integration/test_audit_trail.py::test_hash_chain_detects_removed_tail` | PASS | PASS |
|  |  |  | `tests/integration/test_audit_trail.py::test_normal_roles_have_no_audit_write_endpoints` | PASS | PASS |
|  |  |  | `tests/workflows/test_state_and_approval.py::test_ledger_style_append_only_tables_refuse_update` | PASS | PASS |

## E-signature

| URS | Impact | Rules | Test (path::function) | SQLite | SQL Server |
|---|---|---|---|---|---|
| URS-SIG-01 | Critical | BR-SIG-001 | `tests/validation/test_critical_15.py::test_crit_10_electronic_signature_required_and_bound_to_the_record` | PASS | PASS |
|  |  |  | `tests/workflows/test_state_and_approval.py::test_signature_failure_counts_toward_lockout` | PASS | PASS |
|  |  |  | `tests/workflows/test_state_and_approval.py::test_signer_without_permission_refused` | PASS | PASS |
|  |  |  | `tests/workflows/test_state_and_approval.py::test_training_gate_blocks_signing_until_trained` | PASS | PASS |
| URS-SIG-02 | Critical | BR-SEC-001 | `tests/workflows/test_state_and_approval.py::test_legal_transition_records_history_and_audit` | PASS | PASS |
|  |  |  | `tests/workflows/test_state_and_approval.py::test_illegal_transition_blocked` | PASS | PASS |
|  |  |  | `tests/workflows/test_state_and_approval.py::test_direct_status_assignment_refused_BR_SEC_001` | PASS | PASS |
|  |  |  | `tests/security/test_rbac.py::test_status_not_writable_via_api_payload` | PASS | PASS |

## Workflow

| URS | Impact | Rules | Test (path::function) | SQLite | SQL Server |
|---|---|---|---|---|---|
| URS-SIG-03 | Major | WF-001 | `tests/workflows/test_state_and_approval.py::test_two_step_chain_with_signatures_and_sod` | PASS | PASS |
|  |  |  | `tests/workflows/test_state_and_approval.py::test_initiator_cannot_approve_own_submission` | PASS | PASS |
|  |  |  | `tests/workflows/test_state_and_approval.py::test_definition_needs_qa_signature_and_sod_author_neq_approver` | PASS | PASS |
|  |  |  | `tests/workflows/test_state_and_approval.py::test_approved_definition_is_versioned_not_overwritten` | PASS | PASS |

## System

| URS | Impact | Rules | Test (path::function) | SQLite | SQL Server |
|---|---|---|---|---|---|
| URS-SYS-01 | Major |  | `tests/unit/test_numbering_and_passwords.py::test_no_duplicates_under_concurrency` | PASS | PASS |
|  |  |  | `tests/unit/test_numbering_and_passwords.py::test_rollback_does_not_burn_committed_numbers` | PASS | PASS |
|  |  |  | `tests/unit/test_numbering_and_passwords.py::test_yearly_reset` | PASS | PASS |
|  |  |  | `tests/integration/test_company_documents.py::test_numbering_config_change_audited_and_validated` | PASS | PASS |
| URS-SYS-02 | Critical | BR-AUD-001 | `tests/integration/test_migrations.py::test_alembic_upgrade_matches_models_and_installs_triggers` | PASS | not run |
|  |  |  | `tests/integration/test_migrations.py::test_ddl_generated_for_all_dialects` | PASS | not run |

## Master data

| URS | Impact | Rules | Test (path::function) | SQLite | SQL Server |
|---|---|---|---|---|---|
| URS-MD-01 | Major | BR-DOC-001 | `tests/integration/test_master_data.py::test_vendor_lifecycle_sod_and_signature` | PASS | PASS |
|  |  |  | `tests/integration/test_master_data.py::test_vendor_documents_review_and_integrity` | PASS | PASS |
|  |  |  | `tests/security/test_hardening.py::test_upload_validation_rejects_disguised_oversized_and_traversal_files` | PASS | PASS |
| URS-MD-02 | Major | BR-PO-004 | `tests/integration/test_master_data.py::test_material_validation_and_lifecycle` | PASS | PASS |
|  |  |  | `tests/integration/test_master_data.py::test_material_author_cannot_approve_sod14` | PASS | PASS |
| URS-MD-03 | Critical | BR-HIS-001 | `tests/workflows/test_versioned_masters.py::test_approved_version_is_immutable_and_new_version_supersedes` | PASS | PASS |
|  |  |  | `tests/workflows/test_versioned_masters.py::test_specification_flow_historical_link_and_parameter_rules` | PASS | PASS |
|  |  |  | `tests/workflows/test_versioned_masters.py::test_stp_requires_procedure_then_approve_with_signature_and_sod` | PASS | PASS |
|  |  |  | `tests/workflows/test_versioned_masters.py::test_author_cannot_approve_own_stp_sod16` | PASS | PASS |
|  |  |  | `tests/workflows/test_versioned_masters.py::test_sampling_plan_rules_and_versions` | PASS | PASS |
|  |  |  | `tests/validation/test_critical_15.py::test_crit_12_historical_gmp_records_are_never_overwritten` | PASS | PASS |
| URS-MD-04 | Major | BR-LOC-001/002 | `tests/integration/test_locations_equipment.py::test_hierarchy_rules_and_path` | PASS | PASS |
|  |  |  | `tests/integration/test_locations_equipment.py::test_storage_compatibility_checks` | PASS | PASS |
|  |  |  | `tests/integration/test_locations_equipment.py::test_incompatible_category_rule` | PASS | PASS |
|  |  |  | `tests/integration/test_locations_equipment.py::test_calibration_gate_for_testing` | PASS | PASS |
| URS-MD-05 | Major |  | `tests/integration/test_import.py::test_full_import_flow_vendor` | PASS | PASS |
|  |  |  | `tests/integration/test_import.py::test_validation_errors_block_submission_and_report` | PASS | PASS |
|  |  |  | `tests/integration/test_import.py::test_import_rows_cannot_be_executed_if_data_changed_since_validation` | PASS | PASS |
|  |  |  | `tests/integration/test_import.py::test_upload_rejects_wrong_format_and_missing_columns` | PASS | PASS |

## Purchase

| URS | Impact | Rules | Test (path::function) | SQLite | SQL Server |
|---|---|---|---|---|---|
| URS-PUR-01 | Critical | BR-VQ-001..004 | `tests/workflows/test_purchase_requests.py::test_vendor_qualification_readiness_and_sod` | PASS | PASS |
|  |  |  | `tests/workflows/test_purchase_requests.py::test_qualification_content_locked_after_submission_and_author_sod` | PASS | PASS |
|  |  |  | `tests/workflows/test_purchase_rules.py::test_expiry_job_persists_status_notifies_and_is_idempotent` | PASS | PASS |
|  |  |  | `tests/workflows/test_purchase_rules.py::test_requalification_restores_purchasing_and_keeps_history` | PASS | PASS |
|  |  |  | `tests/workflows/test_purchase_rules.py::test_suspended_and_disqualified_vendor_blocked_and_adverse_actions_are_signed` | PASS | PASS |
| URS-PUR-02 | Critical | BR-PO-001 | `tests/workflows/test_purchase_rules.py::test_crit_01_expired_vendor_cannot_create_po` | PASS | PASS |
| URS-PUR-03 | Critical | BR-PO-002 | `tests/workflows/test_purchase_rules.py::test_crit_02_unapproved_vendor_cannot_purchase` | PASS | PASS |
|  |  |  | `tests/workflows/test_purchase_rules.py::test_inactive_vendor_master_blocks_po` | PASS | PASS |
| URS-PUR-04 | Critical | BR-PO-003, BR-VM-001 | `tests/workflows/test_purchase_rules.py::test_crit_03_wrong_vendor_material_combination` | PASS | PASS |
|  |  |  | `tests/workflows/test_purchase_rules.py::test_mapping_versioning_and_sod` | PASS | PASS |
| URS-PUR-05 | Major | BR-PO-004..010 | `tests/workflows/test_purchase_rules.py::test_other_po_gate_rules_spec_material_documents` | PASS | PASS |
|  |  |  | `tests/workflows/test_purchase_rules.py::test_gate_reports_all_violations_and_warnings` | PASS | PASS |
|  |  |  | `tests/workflows/test_purchase_rules.py::test_po_material_must_be_active_and_unit_checked` | PASS | PASS |
|  |  |  | `tests/workflows/test_purchase_rules.py::test_baseline_po_is_created_with_pins_and_totals` | PASS | PASS |
| URS-PUR-06 | Major | BR-PO-007, BR-PR-001 | `tests/workflows/test_purchase_rules.py::test_po_approval_chain_signature_sod_and_gate_recheck` | PASS | PASS |
|  |  |  | `tests/workflows/test_purchase_rules.py::test_sod_creator_cannot_approve_own_po` | PASS | PASS |
|  |  |  | `tests/workflows/test_purchase_rules.py::test_po_rejection_and_cancellation` | PASS | PASS |
|  |  |  | `tests/workflows/test_purchase_rules.py::test_po_audit_trail_and_status_history` | PASS | PASS |
|  |  |  | `tests/workflows/test_purchase_requests.py::test_pr_full_flow_department_then_purchase_review_then_po` | PASS | PASS |
|  |  |  | `tests/workflows/test_purchase_requests.py::test_pr_rejection_and_cancellation` | PASS | PASS |

## Warehouse

| URS | Impact | Rules | Test (path::function) | SQLite | SQL Server |
|---|---|---|---|---|---|
| URS-WH-01 | Critical | BR-GRN-001..005 | `tests/workflows/test_warehouse.py::test_grn_requires_approved_po_and_blocks_over_delivery_and_bad_dates` | PASS | PASS |
|  |  |  | `tests/workflows/test_warehouse.py::test_critical_checklist_failure_blocks_receipt_until_qa_exception` | PASS | PASS |
|  |  |  | `tests/workflows/test_warehouse.py::test_second_person_verification_and_incomplete_checklist` | PASS | PASS |
|  |  |  | `tests/workflows/test_warehouse.py::test_qa_can_reject_receipt` | PASS | PASS |
|  |  |  | `tests/workflows/test_warehouse.py::test_partial_receipts_and_po_status` | PASS | PASS |
| URS-WH-02 | Critical | BR-QRN-001, BR-LBL-001..003 | `tests/workflows/test_warehouse.py::test_receipt_creates_quarantine_lot_containers_ledger_and_closes_po` | PASS | PASS |
|  |  |  | `tests/workflows/test_warehouse.py::test_quarantine_location_required_and_vendor_expiry_at_receipt_places_hold` | PASS | PASS |
|  |  |  | `tests/workflows/test_warehouse.py::test_labels_are_controlled_audited_and_limited` | PASS | PASS |
| URS-WH-03 | Critical | BR-ISS-001 | `tests/workflows/test_warehouse.py::test_crit_04_quarantine_material_cannot_be_issued` | PASS | PASS |
|  |  |  | `tests/workflows/test_manufacturing.py::test_issue_gates_quarantine_rejected_expired_held` | PASS | PASS |
| URS-WH-04 | Critical | BR-ISS-002, BR-ISS-004 | `tests/workflows/test_warehouse.py::test_crit_05_rejected_and_crit_07_expired_material_cannot_be_issued` | PASS | PASS |
|  |  |  | `tests/workflows/test_manufacturing.py::test_issue_gates_quarantine_rejected_expired_held` | PASS | PASS |
| URS-WH-05 | Critical | BR-HOLD-001..004 | `tests/validation/test_critical_15.py::test_crit_08_quality_hold_blocks_issue_use_and_dispatch` | PASS | PASS |
|  |  |  | `tests/workflows/test_warehouse.py::test_quality_hold_blocks_use_and_release_needs_qa_head_signature` | PASS | PASS |
| URS-WH-06 | Critical | BR-INV-001..003 | `tests/validation/test_critical_15.py::test_crit_13_every_stock_movement_creates_an_inventory_transaction` | PASS | PASS |
|  |  |  | `tests/workflows/test_warehouse.py::test_ledger_matches_balances_and_detects_drift` | PASS | PASS |
|  |  |  | `tests/workflows/test_warehouse.py::test_ledger_is_append_only_and_lot_is_immutable` | PASS | PASS |
|  |  |  | `tests/workflows/test_warehouse.py::test_concurrent_issues_cannot_overdraw_stock` | PASS | PASS |
| URS-WH-07 | Major | BR-INV-005/006, BR-TMP-001 | `tests/workflows/test_warehouse.py::test_fefo_pick_order_and_exclusions` | PASS | PASS |
|  |  |  | `tests/workflows/test_warehouse.py::test_transfer_rules_for_quarantine_approved_and_rejected_stock` | PASS | PASS |
|  |  |  | `tests/workflows/test_warehouse.py::test_expiry_job_and_alerts` | PASS | PASS |
|  |  |  | `tests/workflows/test_warehouse.py::test_temperature_excursion_places_holds_on_stored_lots` | PASS | PASS |
|  |  |  | `tests/workflows/test_warehouse.py::test_destruction_requires_rejected_stock_and_qa_signature` | PASS | PASS |
|  |  |  | `tests/workflows/test_manufacturing.py::test_fefo_deviation_needs_reason` | PASS | PASS |

## QC / LIMS

| URS | Impact | Rules | Test (path::function) | SQLite | SQL Server |
|---|---|---|---|---|---|
| URS-QC-01 | Critical | BR-SMP-001/002, BR-QC-001 | `tests/workflows/test_qc.py::test_sampling_plan_ledger_and_state` | PASS | PASS |
|  |  |  | `tests/workflows/test_qc.py::test_tests_follow_pinned_specification_even_after_spec_revision` | PASS | PASS |
| URS-QC-02 | Critical | BR-QC-004/005 | `tests/workflows/test_qc.py::test_result_entry_evaluation_rounding_and_immutability` | PASS | PASS |
|  |  |  | `tests/workflows/test_qc.py::test_assigned_test_is_restricted_to_its_analyst_and_boundaries_are_inclusive` | PASS | PASS |
|  |  |  | `tests/workflows/test_qc.py::test_result_amendment_workflow_retains_original` | PASS | PASS |
| URS-QC-03 | Critical | BR-QC-002 | `tests/workflows/test_qc.py::test_calibration_gate_blocks_testing_and_override_is_controlled` | PASS | PASS |
| URS-QC-04 | Critical | BR-QC-007, BR-STAT-002 | `tests/workflows/test_qc.py::test_failing_result_raises_oos_and_places_hold` | PASS | PASS |
|  |  |  | `tests/workflows/test_qc.py::test_oos_invalidated_allows_retest_and_release_path` | PASS | PASS |
|  |  |  | `tests/workflows/test_qc.py::test_oos_confirmed_rejects_lot` | PASS | PASS |
|  |  |  | `tests/workflows/test_qc.py::test_oot_alert_limit_flags_but_never_changes_disposition` | PASS | PASS |
| URS-QC-05 | Critical | BR-REL-001..004, BR-QC-006 | `tests/workflows/test_qc.py::test_full_release_chain_to_approved_coa_and_issuable_lot` | PASS | PASS |
|  |  |  | `tests/workflows/test_qc.py::test_release_chain_enforces_order_roles_and_separation_of_duties` | PASS | PASS |
|  |  |  | `tests/workflows/test_qc.py::test_one_person_cannot_hold_two_release_steps_sod03` | PASS | PASS |
|  |  |  | `tests/workflows/test_qc.py::test_analyst_who_tested_cannot_review_even_with_reviewer_role` | PASS | PASS |
|  |  |  | `tests/workflows/test_qc.py::test_release_rejection_makes_lot_unissuable_crit_05` | PASS | PASS |
|  |  |  | `tests/workflows/test_qc.py::test_release_blocked_by_missing_coa_hold_or_open_oos` | PASS | PASS |
|  |  |  | `tests/workflows/test_qc.py::test_coa_requires_release_and_reissue_creates_new_version` | PASS | PASS |
| URS-QC-06 | Critical | BR-CRL-001..004 | `tests/workflows/test_qc.py::test_conditional_release_is_a_controlled_exception` | PASS | PASS |
|  |  |  | `tests/workflows/test_manufacturing.py::test_conditional_material_blocks_batch_release` | PASS | PASS |
| URS-QC-07 | Major | BR-STAT-001 | `tests/workflows/test_qc.py::test_stats_reference_values_and_status_codes` | PASS | PASS |
|  |  |  | `tests/workflows/test_qc.py::test_nelson_rules_and_control_limits` | PASS | PASS |
|  |  |  | `tests/workflows/test_qc.py::test_trend_endpoint_groups_and_capability_status` | PASS | PASS |
|  |  |  | `tests/workflows/test_qc.py::test_sample_retention_and_disposal` | PASS | PASS |

## Manufacturing

| URS | Impact | Rules | Test (path::function) | SQLite | SQL Server |
|---|---|---|---|---|---|
| URS-MFG-01 | Critical | BR-BOM-001/002 | `tests/workflows/test_manufacturing.py::test_bom_lifecycle_and_immutability` | PASS | PASS |
|  |  |  | `tests/workflows/test_manufacturing.py::test_bom_validation` | PASS | PASS |
|  |  |  | `tests/workflows/test_manufacturing.py::test_batch_requires_approved_bom_and_scales_requirements` | PASS | PASS |
| URS-MFG-02 | Critical | BR-BAT-001/002 | `tests/workflows/test_manufacturing.py::test_duplicate_batch_number_prevented_and_override_controlled` | PASS | PASS |
| URS-MFG-03 | Critical | BR-ISS-001..007, BR-TRC-001 | `tests/validation/test_critical_15.py::test_crit_14_issued_material_is_always_linked_to_lot_and_production_batch` | PASS | PASS |
|  |  |  | `tests/workflows/test_manufacturing.py::test_issue_links_lot_and_batch_and_posts_ledger` | PASS | PASS |
|  |  |  | `tests/workflows/test_manufacturing.py::test_issue_is_audited_and_traceable` | PASS | PASS |
| URS-MFG-04 | Major | BR-RET-001 | `tests/workflows/test_manufacturing.py::test_return_workflow_and_sod` | PASS | PASS |
| URS-MFG-05 | Critical | BR-MFG-001..004 | `tests/workflows/test_manufacturing.py::test_process_execution_controls` | PASS | PASS |
|  |  |  | `tests/workflows/test_manufacturing.py::test_ipc_failure_places_batch_on_hold_and_blocks_completion` | PASS | PASS |
|  |  |  | `tests/workflows/test_manufacturing.py::test_equipment_gate` | PASS | PASS |
| URS-MFG-06 | Critical | BR-REC-001 | `tests/validation/test_critical_15.py::test_crit_15_reconciliation_discrepancy_is_highlighted_and_blocks_progress` | PASS | PASS |
|  |  |  | `tests/workflows/test_manufacturing.py::test_reconciliation_within_tolerance` | PASS | PASS |
|  |  |  | `tests/workflows/test_manufacturing.py::test_reconciliation_discrepancy_blocks_until_qa_deviation` | PASS | PASS |
| URS-MFG-07 | Major | BR-ANM-001..003 | `tests/workflows/test_manufacturing.py::test_output_lot_flows_into_qc_and_release_marks_batch` | PASS | PASS |
|  |  |  | `tests/workflows/test_manufacturing.py::test_antisera_animal_bleed_pool_genealogy` | PASS | PASS |

## Dispatch

| URS | Impact | Rules | Test (path::function) | SQLite | SQL Server |
|---|---|---|---|---|---|
| URS-DSP-01 | Critical | BR-DSP-001..006 | `tests/workflows/test_dispatch.py::test_crit_06_unreleased_fg_cannot_be_dispatched` | PASS | PASS |
|  |  |  | `tests/workflows/test_dispatch.py::test_hold_expiry_customer_and_oos_blocks` | PASS | PASS |
|  |  |  | `tests/workflows/test_dispatch.py::test_rm_and_wrong_type_cannot_be_dispatched` | PASS | PASS |
| URS-DSP-02 | Critical | BR-DSP-003/006 | `tests/workflows/test_dispatch.py::test_released_fg_full_dispatch_flow` | PASS | PASS |
|  |  |  | `tests/workflows/test_dispatch.py::test_sod_creator_cannot_approve` | PASS | PASS |
|  |  |  | `tests/workflows/test_dispatch.py::test_hold_after_validation_blocks_approval_and_dispatch_and_cancel_releases_stock` | PASS | PASS |
|  |  |  | `tests/workflows/test_dispatch.py::test_dispatch_is_audited_and_permissioned` | PASS | PASS |

## Traceability

| URS | Impact | Rules | Test (path::function) | SQLite | SQL Server |
|---|---|---|---|---|---|
| URS-TRC-01 | Critical | BR-TRC-001 | `tests/workflows/test_dispatch.py::test_traceability_backward_and_forward_are_complete` | PASS | PASS |
|  |  |  | `tests/workflows/test_dispatch.py::test_trace_excludes_undispatched_and_antisera_genealogy` | PASS | PASS |
|  |  |  | `tests/workflows/test_dispatch.py::test_global_search_respects_permissions_and_qr_resolve` | PASS | PASS |
| URS-TRC-02 | Critical | BR-ISS-001, BR-TRC-001 | `tests/workflows/test_multilevel_genealogy.py::test_fg_batch_consumes_a_released_sfg_lot_and_trace_spans_both_levels` | PASS | PASS |

## Quality system

| URS | Impact | Rules | Test (path::function) | SQLite | SQL Server |
|---|---|---|---|---|---|
| URS-QS-01 | Critical | BR-DEV-001..003 | `tests/workflows/test_quality_system.py::test_open_deviation_blocks_release_until_closed_with_independent_qa_signature` | PASS | PASS |
|  |  |  | `tests/workflows/test_quality_system.py::test_deviation_raiser_cannot_close_and_non_blocking_flag` | PASS | PASS |
|  |  |  | `tests/workflows/test_quality_system.py::test_temperature_excursion_raises_deviation_and_hold` | PASS | PASS |
|  |  |  | `tests/workflows/test_quality_system.py::test_ipc_failure_raises_deviation_on_batch` | PASS | PASS |
|  |  |  | `tests/workflows/test_quality_system.py::test_reconciliation_deviation_blocks_output_lot_release` | PASS | PASS |
| URS-QS-02 | Major | BR-CAPA-001/002 | `tests/workflows/test_quality_system.py::test_capa_lifecycle_effectiveness_and_sod` | PASS | PASS |
|  |  |  | `tests/workflows/test_quality_system.py::test_capa_creator_cannot_close_own_capa` | PASS | PASS |
| URS-QS-03 | Critical | BR-CC-001..003, BR-BOM-002, BR-VM-001 | `tests/workflows/test_quality_system.py::test_change_control_gates_new_master_versions` | PASS | PASS |
|  |  |  | `tests/workflows/test_quality_system.py::test_change_control_requester_cannot_approve_and_rejection` | PASS | PASS |
| URS-QS-04 | Major | BR-RSK-001 | `tests/workflows/test_quality_system.py::test_fmea_rpn_levels_and_approval_rules` | PASS | PASS |
| URS-QS-05 | Major | BR-SOP-001/002 | `tests/workflows/test_quality_system.py::test_sop_versioning_acknowledgement_and_review_due` | PASS | PASS |
| URS-QS-06 | Critical | BR-CMP-001, BR-RCL-001..004 | `tests/workflows/test_quality_system.py::test_critical_complaint_holds_lot_and_needs_closed_deviation` | PASS | PASS |
|  |  |  | `tests/workflows/test_quality_system.py::test_recall_derives_affected_customers_and_reconciles_returns` | PASS | PASS |
|  |  |  | `tests/workflows/test_quality_system.py::test_quality_endpoints_are_permissioned_and_listed` | PASS | PASS |

## Reports

| URS | Impact | Rules | Test (path::function) | SQLite | SQL Server |
|---|---|---|---|---|---|
| URS-RPT-01 | Major |  | `tests/workflows/test_reports.py::test_catalogue_size_and_every_report_runs_with_data` | PASS | PASS |
|  |  |  | `tests/workflows/test_reports.py::test_report_permissions_params_and_no_field_leak` | PASS | PASS |
|  |  |  | `tests/integration/test_master_data.py::test_exports_have_report_header_and_are_audited` | PASS | PASS |
| URS-RPT-02 | Critical | BR-DOC-001 | `tests/workflows/test_reports.py::test_exports_are_controlled_copies_with_hash_verification` | PASS | PASS |
|  |  |  | `tests/workflows/test_reports.py::test_controlled_business_documents_pdf` | PASS | PASS |
| URS-RPT-03 | Minor |  | `tests/workflows/test_reports.py::test_dashboards_are_role_gated_and_populated` | PASS | PASS |
|  |  |  | `tests/workflows/test_reports.py::test_report_performance_with_large_ledger` | PASS | PASS |
|  |  |  | `tests/integration/test_company_documents.py::test_dashboard_cards` | PASS | PASS |

## Data integrity

| URS | Impact | Rules | Test (path::function) | SQLite | SQL Server |
|---|---|---|---|---|---|
| URS-DI-01 | Critical | BR-RET-001/002 | `tests/workflows/test_reports.py::test_retention_policies_archive_and_legal_hold` | PASS | PASS |
|  |  |  | `tests/integration/test_audit_trail.py::test_physical_delete_of_audited_record_refused` | PASS | PASS |
| URS-DI-02 | Major |  | `tests/workflows/test_reports.py::test_backup_status_and_restore_evidence` | PASS | PASS |

## Summary

* Requirements: **59**; all have at least one automated test: **True**
* Mapped test references: **190** (distinct tests: **188**)
* Results of mapped tests (SQLite): PASS: 190; SQL Server: {'PASS': 188, 'not run': 2}
* SQL Server column: the two `tests/integration/test_migrations.py` tests spawn SQLite subprocesses and are deselected there; the migration chain is verified on SQL Server separately (`docs/validation/sqlserver-verification.md`: 0001→0009 up/down/up, 110 tables, 17 triggers).
* Collected automated tests in total: **232**; not referenced by a requirement (supporting/unit tests): **44**

### The 15 mandatory critical tests (prompt §77)

| # | Rule | Test |
|---|---|---|
| 1 | Expired vendor qualification blocks PO | `tests/workflows/test_purchase_rules.py::test_crit_01_expired_vendor_cannot_create_po` — SQLite: PASS; SQL Server: PASS |
| 2 | Unapproved vendor blocks PO | `tests/workflows/test_purchase_rules.py::test_crit_02_unapproved_vendor_cannot_purchase` — SQLite: PASS; SQL Server: PASS |
| 3 | Vendor not approved for material blocks PO | `tests/workflows/test_purchase_rules.py::test_crit_03_wrong_vendor_material_combination` — SQLite: PASS; SQL Server: PASS |
| 4 | Quarantine material cannot be issued | `tests/workflows/test_warehouse.py::test_crit_04_quarantine_material_cannot_be_issued` — SQLite: PASS; SQL Server: PASS |
| 5 | Rejected material cannot be issued | `tests/workflows/test_warehouse.py::test_crit_05_rejected_and_crit_07_expired_material_cannot_be_issued` — SQLite: PASS; SQL Server: PASS |
| 6 | Unreleased FG cannot be dispatched | `tests/workflows/test_dispatch.py::test_crit_06_unreleased_fg_cannot_be_dispatched` — SQLite: PASS; SQL Server: PASS |
| 7 | Expired material cannot be issued | `tests/workflows/test_warehouse.py::test_crit_05_rejected_and_crit_07_expired_material_cannot_be_issued` — SQLite: PASS; SQL Server: PASS |
| 8 | Quality hold blocks issue/use/dispatch | `tests/validation/test_critical_15.py::test_crit_08_quality_hold_blocks_issue_use_and_dispatch` — SQLite: PASS; SQL Server: PASS |
| 9 | Audit trail cannot be modified/deleted | `tests/validation/test_critical_15.py::test_crit_09_audit_trail_cannot_be_modified_or_deleted` — SQLite: PASS; SQL Server: PASS |
| 10 | E-signature required for configured actions | `tests/validation/test_critical_15.py::test_crit_10_electronic_signature_required_and_bound_to_the_record` — SQLite: PASS; SQL Server: PASS |
| 11 | Creator cannot approve own transaction | `tests/validation/test_critical_15.py::test_crit_11_creator_cannot_approve_own_transaction` — SQLite: PASS; SQL Server: PASS |
| 12 | Historical GMP records never overwritten | `tests/validation/test_critical_15.py::test_crit_12_historical_gmp_records_are_never_overwritten` — SQLite: PASS; SQL Server: PASS |
| 13 | Every movement creates an inventory transaction | `tests/validation/test_critical_15.py::test_crit_13_every_stock_movement_creates_an_inventory_transaction` — SQLite: PASS; SQL Server: PASS |
| 14 | Issued material linked to production batch | `tests/validation/test_critical_15.py::test_crit_14_issued_material_is_always_linked_to_lot_and_production_batch` — SQLite: PASS; SQL Server: PASS |
| 15 | Reconciliation discrepancy highlighted | `tests/validation/test_critical_15.py::test_crit_15_reconciliation_discrepancy_is_highlighted_and_blocks_progress` — SQLite: PASS; SQL Server: PASS |

### Supporting tests not mapped to a specific requirement

<details><summary>show list</summary>

* `tests/integration/test_audit_trail.py::test_audit_export_and_verify_endpoints_for_qa`
* `tests/integration/test_audit_trail.py::test_audit_keyset_pagination`
* `tests/integration/test_audit_trail.py::test_audit_rows_cannot_be_updated_or_deleted_via_orm`
* `tests/integration/test_audit_trail.py::test_password_hash_is_redacted_in_audit`
* `tests/integration/test_company_documents.py::test_branding_is_public_and_logo_upload_validated`
* `tests/integration/test_company_documents.py::test_system_config_requires_reason`
* `tests/integration/test_import.py::test_material_location_stp_and_spec_imports`
* `tests/integration/test_import.py::test_template_download_has_columns_and_instructions`
* `tests/integration/test_master_data.py::test_admin_manages_lookups_with_reason_and_others_cannot`
* `tests/integration/test_master_data.py::test_seed_upgrade_only_grants_new_permissions_and_never_undoes_admin_changes`
* `tests/security/test_auth.py::test_concurrent_logins_of_the_same_account_do_not_conflict`
* `tests/security/test_auth.py::test_failed_login_is_audited`
* `tests/security/test_auth.py::test_inactive_user_cannot_login`
* `tests/security/test_auth.py::test_security_headers_and_correlation_id`
* `tests/security/test_hardening.py::test_exports_neutralise_spreadsheet_formula_injection`
* `tests/security/test_hardening.py::test_pdf_output_treats_user_text_as_text_not_markup`
* `tests/security/test_hardening.py::test_stored_script_payloads_are_returned_as_inert_json_with_csp`
* `tests/security/test_hardening.py::test_unknown_and_malformed_identifiers_do_not_leak_internals`
* `tests/security/test_ldap_provider.py::test_ldap_wrong_password_and_empty_password_rejected`
* `tests/security/test_rbac.py::test_admin_creates_user_and_assigns_role_with_reason`
* `tests/security/test_rbac.py::test_admin_role_cannot_receive_approve_permission`
* `tests/security/test_rbac.py::test_cannot_deactivate_self`
* `tests/security/test_rbac.py::test_duplicate_username_rejected_case_insensitive`
* `tests/security/test_rbac.py::test_expired_access_blocks_login`
* `tests/security/test_rbac.py::test_role_permission_change_takes_effect_and_is_audited`
* `tests/security/test_rbac.py::test_unauthenticated_is_401`
* `tests/security/test_rbac.py::test_user_deactivation_revokes_sessions`
* `tests/unit/test_numbering_and_passwords.py::test_format_and_sequence`
* `tests/unit/test_numbering_and_passwords.py::test_hash_verify_roundtrip`
* `tests/unit/test_numbering_and_passwords.py::test_password_policy`
* `tests/unit/test_numbering_and_passwords.py::test_unknown_doc_type`
* `tests/workflows/test_purchase_requests.py::test_conditional_qualification_allows_purchase_with_warning`
* `tests/workflows/test_purchase_requests.py::test_dashboard_purchase_cards`
* `tests/workflows/test_purchase_requests.py::test_pr_listing_filters_and_export`
* `tests/workflows/test_purchase_requests.py::test_pr_rejects_inactive_material_missing_department_and_duplicates`
* `tests/workflows/test_purchase_rules.py::test_po_with_receipts_cannot_be_cancelled`
* `tests/workflows/test_purchase_rules.py::test_scheduler_run_acts_as_system_user`
* `tests/workflows/test_state_and_approval.py::test_missing_permission_blocks_transition`
* `tests/workflows/test_state_and_approval.py::test_rejection_is_terminal_and_requires_reason`
* `tests/workflows/test_state_and_approval.py::test_workflow_definition_api_end_to_end`
* `tests/workflows/test_versioned_masters.py::test_draft_parameter_delete_is_audited_and_spec_requires_approved_stp`
* `tests/workflows/test_versioned_masters.py::test_return_to_draft_needs_reason`
* `tests/workflows/test_warehouse.py::test_roles_cannot_do_warehouse_actions_they_do_not_hold`
* `tests/workflows/test_warehouse.py::test_stock_report_and_export`

</details>
