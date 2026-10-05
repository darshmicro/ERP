# Requirements Traceability Matrix (RTM)

Generated 2026-10-05 20:23 UTC from `scripts/validation_requirements.py` and the automated test inventory. No execution evidence was supplied (run with `--junit`).

URS → business rule → automated test (OQ evidence) → result. Every referenced test was verified to exist by collection; the generator aborts otherwise.

## Security

| URS | Impact | Rules | Test (path::function) | Result |
|---|---|---|---|---|
| URS-IAM-01 | Critical | BR-SEC-002 | `tests/security/test_auth.py::test_login_logout_and_me` | not run |
|  |  |  | `tests/security/test_auth.py::test_unknown_user_and_bad_password_give_same_generic_error` | not run |
|  |  |  | `tests/security/test_ldap_provider.py::test_ldap_user_logs_in_with_directory_password` | not run |
|  |  |  | `tests/security/test_ldap_provider.py::test_ldap_disabled_fails_closed` | not run |
| URS-IAM-02 | Critical | BR-SEC-002 | `tests/security/test_auth.py::test_lockout_after_threshold_and_events_logged` | not run |
|  |  |  | `tests/security/test_auth.py::test_idle_timeout_expires_session` | not run |
|  |  |  | `tests/security/test_auth.py::test_must_change_password_blocks_other_endpoints` | not run |
|  |  |  | `tests/security/test_auth.py::test_password_policy_and_history` | not run |
|  |  |  | `tests/security/test_auth.py::test_login_rate_limit` | not run |
| URS-IAM-03 | Critical | BR-SEC-001 | `tests/security/test_access_matrix.py::test_every_route_requires_authentication` | not run |
|  |  |  | `tests/security/test_access_matrix.py::test_generated_role_by_route_permission_matrix` | not run |
|  |  |  | `tests/security/test_rbac.py::test_unauthorised_user_gets_403_and_event_logged` | not run |
|  |  |  | `tests/integration/test_master_data.py::test_role_access_matrix_phase2` | not run |
| URS-IAM-04 | Critical | BR-SOD-001 | `tests/security/test_access_matrix.py::test_admin_roles_hold_no_gmp_approval_authority` | not run |
|  |  |  | `tests/security/test_rbac.py::test_admin_cannot_hold_gmp_approval_role_sod09` | not run |
|  |  |  | `tests/security/test_rbac.py::test_cannot_change_own_roles_sod10` | not run |
|  |  |  | `tests/validation/test_critical_15.py::test_crit_11_creator_cannot_approve_own_transaction` | not run |
| URS-IAM-05 | Critical | BR-SEC-001 | `tests/security/test_auth.py::test_csrf_required_on_state_change` | not run |
|  |  |  | `tests/security/test_hardening.py::test_sql_injection_payloads_in_every_search_and_filter_are_inert` | not run |
|  |  |  | `tests/security/test_hardening.py::test_status_and_system_columns_cannot_be_mass_assigned` | not run |
|  |  |  | `tests/security/test_hardening.py::test_upload_validation_rejects_disguised_oversized_and_traversal_files` | not run |
|  |  |  | `tests/security/test_hardening.py::test_no_credential_material_in_any_api_response` | not run |
|  |  |  | `tests/security/test_hardening.py::test_session_cookie_flags_and_logout_invalidates_session` | not run |
|  |  |  | `tests/security/test_hardening.py::test_state_changing_requests_without_csrf_token_are_refused_everywhere` | not run |
|  |  |  | `tests/security/test_auth.py::test_unhandled_error_hides_internals` | not run |

## Audit trail

| URS | Impact | Rules | Test (path::function) | Result |
|---|---|---|---|---|
| URS-AUD-01 | Critical | BR-AUD-002 | `tests/integration/test_audit_trail.py::test_field_level_audit_with_old_new_user_reason` | not run |
|  |  |  | `tests/integration/test_audit_trail.py::test_audit_written_in_same_transaction_rollback_removes_both` | not run |
|  |  |  | `tests/integration/test_audit_trail.py::test_master_update_without_reason_is_rejected_and_rolled_back` | not run |
| URS-AUD-02 | Critical | BR-AUD-001 | `tests/validation/test_critical_15.py::test_crit_09_audit_trail_cannot_be_modified_or_deleted` | not run |
|  |  |  | `tests/integration/test_audit_trail.py::test_audit_rows_cannot_be_modified_with_raw_sql_db_trigger` | not run |
|  |  |  | `tests/integration/test_audit_trail.py::test_hash_chain_verifies_and_detects_tampering` | not run |
|  |  |  | `tests/integration/test_audit_trail.py::test_hash_chain_detects_removed_tail` | not run |
|  |  |  | `tests/integration/test_audit_trail.py::test_normal_roles_have_no_audit_write_endpoints` | not run |
|  |  |  | `tests/workflows/test_state_and_approval.py::test_ledger_style_append_only_tables_refuse_update` | not run |

## E-signature

| URS | Impact | Rules | Test (path::function) | Result |
|---|---|---|---|---|
| URS-SIG-01 | Critical | BR-SIG-001 | `tests/validation/test_critical_15.py::test_crit_10_electronic_signature_required_and_bound_to_the_record` | not run |
|  |  |  | `tests/workflows/test_state_and_approval.py::test_signature_failure_counts_toward_lockout` | not run |
|  |  |  | `tests/workflows/test_state_and_approval.py::test_signer_without_permission_refused` | not run |
|  |  |  | `tests/workflows/test_state_and_approval.py::test_training_gate_blocks_signing_until_trained` | not run |
| URS-SIG-02 | Critical | BR-SEC-001 | `tests/workflows/test_state_and_approval.py::test_legal_transition_records_history_and_audit` | not run |
|  |  |  | `tests/workflows/test_state_and_approval.py::test_illegal_transition_blocked` | not run |
|  |  |  | `tests/workflows/test_state_and_approval.py::test_direct_status_assignment_refused_BR_SEC_001` | not run |
|  |  |  | `tests/security/test_rbac.py::test_status_not_writable_via_api_payload` | not run |

## Workflow

| URS | Impact | Rules | Test (path::function) | Result |
|---|---|---|---|---|
| URS-SIG-03 | Major | WF-001 | `tests/workflows/test_state_and_approval.py::test_two_step_chain_with_signatures_and_sod` | not run |
|  |  |  | `tests/workflows/test_state_and_approval.py::test_initiator_cannot_approve_own_submission` | not run |
|  |  |  | `tests/workflows/test_state_and_approval.py::test_definition_needs_qa_signature_and_sod_author_neq_approver` | not run |
|  |  |  | `tests/workflows/test_state_and_approval.py::test_approved_definition_is_versioned_not_overwritten` | not run |

## System

| URS | Impact | Rules | Test (path::function) | Result |
|---|---|---|---|---|
| URS-SYS-01 | Major |  | `tests/unit/test_numbering_and_passwords.py::test_no_duplicates_under_concurrency` | not run |
|  |  |  | `tests/unit/test_numbering_and_passwords.py::test_rollback_does_not_burn_committed_numbers` | not run |
|  |  |  | `tests/unit/test_numbering_and_passwords.py::test_yearly_reset` | not run |
|  |  |  | `tests/integration/test_company_documents.py::test_numbering_config_change_audited_and_validated` | not run |
| URS-SYS-02 | Critical | BR-AUD-001 | `tests/integration/test_migrations.py::test_alembic_upgrade_matches_models_and_installs_triggers` | not run |
|  |  |  | `tests/integration/test_migrations.py::test_ddl_generated_for_all_dialects` | not run |

## Master data

| URS | Impact | Rules | Test (path::function) | Result |
|---|---|---|---|---|
| URS-MD-01 | Major | BR-DOC-001 | `tests/integration/test_master_data.py::test_vendor_lifecycle_sod_and_signature` | not run |
|  |  |  | `tests/integration/test_master_data.py::test_vendor_documents_review_and_integrity` | not run |
|  |  |  | `tests/security/test_hardening.py::test_upload_validation_rejects_disguised_oversized_and_traversal_files` | not run |
| URS-MD-02 | Major | BR-PO-004 | `tests/integration/test_master_data.py::test_material_validation_and_lifecycle` | not run |
|  |  |  | `tests/integration/test_master_data.py::test_material_author_cannot_approve_sod14` | not run |
| URS-MD-03 | Critical | BR-HIS-001 | `tests/workflows/test_versioned_masters.py::test_approved_version_is_immutable_and_new_version_supersedes` | not run |
|  |  |  | `tests/workflows/test_versioned_masters.py::test_specification_flow_historical_link_and_parameter_rules` | not run |
|  |  |  | `tests/workflows/test_versioned_masters.py::test_stp_requires_procedure_then_approve_with_signature_and_sod` | not run |
|  |  |  | `tests/workflows/test_versioned_masters.py::test_author_cannot_approve_own_stp_sod16` | not run |
|  |  |  | `tests/workflows/test_versioned_masters.py::test_sampling_plan_rules_and_versions` | not run |
|  |  |  | `tests/validation/test_critical_15.py::test_crit_12_historical_gmp_records_are_never_overwritten` | not run |
| URS-MD-04 | Major | BR-LOC-001/002 | `tests/integration/test_locations_equipment.py::test_hierarchy_rules_and_path` | not run |
|  |  |  | `tests/integration/test_locations_equipment.py::test_storage_compatibility_checks` | not run |
|  |  |  | `tests/integration/test_locations_equipment.py::test_incompatible_category_rule` | not run |
|  |  |  | `tests/integration/test_locations_equipment.py::test_calibration_gate_for_testing` | not run |
| URS-MD-05 | Major |  | `tests/integration/test_import.py::test_full_import_flow_vendor` | not run |
|  |  |  | `tests/integration/test_import.py::test_validation_errors_block_submission_and_report` | not run |
|  |  |  | `tests/integration/test_import.py::test_import_rows_cannot_be_executed_if_data_changed_since_validation` | not run |
|  |  |  | `tests/integration/test_import.py::test_upload_rejects_wrong_format_and_missing_columns` | not run |

## Purchase

| URS | Impact | Rules | Test (path::function) | Result |
|---|---|---|---|---|
| URS-PUR-01 | Critical | BR-VQ-001..004 | `tests/workflows/test_purchase_requests.py::test_vendor_qualification_readiness_and_sod` | not run |
|  |  |  | `tests/workflows/test_purchase_requests.py::test_qualification_content_locked_after_submission_and_author_sod` | not run |
|  |  |  | `tests/workflows/test_purchase_rules.py::test_expiry_job_persists_status_notifies_and_is_idempotent` | not run |
|  |  |  | `tests/workflows/test_purchase_rules.py::test_requalification_restores_purchasing_and_keeps_history` | not run |
|  |  |  | `tests/workflows/test_purchase_rules.py::test_suspended_and_disqualified_vendor_blocked_and_adverse_actions_are_signed` | not run |
| URS-PUR-02 | Critical | BR-PO-001 | `tests/workflows/test_purchase_rules.py::test_crit_01_expired_vendor_cannot_create_po` | not run |
| URS-PUR-03 | Critical | BR-PO-002 | `tests/workflows/test_purchase_rules.py::test_crit_02_unapproved_vendor_cannot_purchase` | not run |
|  |  |  | `tests/workflows/test_purchase_rules.py::test_inactive_vendor_master_blocks_po` | not run |
| URS-PUR-04 | Critical | BR-PO-003, BR-VM-001 | `tests/workflows/test_purchase_rules.py::test_crit_03_wrong_vendor_material_combination` | not run |
|  |  |  | `tests/workflows/test_purchase_rules.py::test_mapping_versioning_and_sod` | not run |
| URS-PUR-05 | Major | BR-PO-004..010 | `tests/workflows/test_purchase_rules.py::test_other_po_gate_rules_spec_material_documents` | not run |
|  |  |  | `tests/workflows/test_purchase_rules.py::test_gate_reports_all_violations_and_warnings` | not run |
|  |  |  | `tests/workflows/test_purchase_rules.py::test_po_material_must_be_active_and_unit_checked` | not run |
|  |  |  | `tests/workflows/test_purchase_rules.py::test_baseline_po_is_created_with_pins_and_totals` | not run |
| URS-PUR-06 | Major | BR-PO-007, BR-PR-001 | `tests/workflows/test_purchase_rules.py::test_po_approval_chain_signature_sod_and_gate_recheck` | not run |
|  |  |  | `tests/workflows/test_purchase_rules.py::test_sod_creator_cannot_approve_own_po` | not run |
|  |  |  | `tests/workflows/test_purchase_rules.py::test_po_rejection_and_cancellation` | not run |
|  |  |  | `tests/workflows/test_purchase_rules.py::test_po_audit_trail_and_status_history` | not run |
|  |  |  | `tests/workflows/test_purchase_requests.py::test_pr_full_flow_department_then_purchase_review_then_po` | not run |
|  |  |  | `tests/workflows/test_purchase_requests.py::test_pr_rejection_and_cancellation` | not run |

## Warehouse

| URS | Impact | Rules | Test (path::function) | Result |
|---|---|---|---|---|
| URS-WH-01 | Critical | BR-GRN-001..005 | `tests/workflows/test_warehouse.py::test_grn_requires_approved_po_and_blocks_over_delivery_and_bad_dates` | not run |
|  |  |  | `tests/workflows/test_warehouse.py::test_critical_checklist_failure_blocks_receipt_until_qa_exception` | not run |
|  |  |  | `tests/workflows/test_warehouse.py::test_second_person_verification_and_incomplete_checklist` | not run |
|  |  |  | `tests/workflows/test_warehouse.py::test_qa_can_reject_receipt` | not run |
|  |  |  | `tests/workflows/test_warehouse.py::test_partial_receipts_and_po_status` | not run |
| URS-WH-02 | Critical | BR-QRN-001, BR-LBL-001..003 | `tests/workflows/test_warehouse.py::test_receipt_creates_quarantine_lot_containers_ledger_and_closes_po` | not run |
|  |  |  | `tests/workflows/test_warehouse.py::test_quarantine_location_required_and_vendor_expiry_at_receipt_places_hold` | not run |
|  |  |  | `tests/workflows/test_warehouse.py::test_labels_are_controlled_audited_and_limited` | not run |
| URS-WH-03 | Critical | BR-ISS-001 | `tests/workflows/test_warehouse.py::test_crit_04_quarantine_material_cannot_be_issued` | not run |
|  |  |  | `tests/workflows/test_manufacturing.py::test_issue_gates_quarantine_rejected_expired_held` | not run |
| URS-WH-04 | Critical | BR-ISS-002, BR-ISS-004 | `tests/workflows/test_warehouse.py::test_crit_05_rejected_and_crit_07_expired_material_cannot_be_issued` | not run |
|  |  |  | `tests/workflows/test_manufacturing.py::test_issue_gates_quarantine_rejected_expired_held` | not run |
| URS-WH-05 | Critical | BR-HOLD-001..004 | `tests/validation/test_critical_15.py::test_crit_08_quality_hold_blocks_issue_use_and_dispatch` | not run |
|  |  |  | `tests/workflows/test_warehouse.py::test_quality_hold_blocks_use_and_release_needs_qa_head_signature` | not run |
| URS-WH-06 | Critical | BR-INV-001..003 | `tests/validation/test_critical_15.py::test_crit_13_every_stock_movement_creates_an_inventory_transaction` | not run |
|  |  |  | `tests/workflows/test_warehouse.py::test_ledger_matches_balances_and_detects_drift` | not run |
|  |  |  | `tests/workflows/test_warehouse.py::test_ledger_is_append_only_and_lot_is_immutable` | not run |
|  |  |  | `tests/workflows/test_warehouse.py::test_concurrent_issues_cannot_overdraw_stock` | not run |
| URS-WH-07 | Major | BR-INV-005/006, BR-TMP-001 | `tests/workflows/test_warehouse.py::test_fefo_pick_order_and_exclusions` | not run |
|  |  |  | `tests/workflows/test_warehouse.py::test_transfer_rules_for_quarantine_approved_and_rejected_stock` | not run |
|  |  |  | `tests/workflows/test_warehouse.py::test_expiry_job_and_alerts` | not run |
|  |  |  | `tests/workflows/test_warehouse.py::test_temperature_excursion_places_holds_on_stored_lots` | not run |
|  |  |  | `tests/workflows/test_warehouse.py::test_destruction_requires_rejected_stock_and_qa_signature` | not run |
|  |  |  | `tests/workflows/test_manufacturing.py::test_fefo_deviation_needs_reason` | not run |

## QC / LIMS

| URS | Impact | Rules | Test (path::function) | Result |
|---|---|---|---|---|
| URS-QC-01 | Critical | BR-SMP-001/002, BR-QC-001 | `tests/workflows/test_qc.py::test_sampling_plan_ledger_and_state` | not run |
|  |  |  | `tests/workflows/test_qc.py::test_tests_follow_pinned_specification_even_after_spec_revision` | not run |
| URS-QC-02 | Critical | BR-QC-004/005 | `tests/workflows/test_qc.py::test_result_entry_evaluation_rounding_and_immutability` | not run |
|  |  |  | `tests/workflows/test_qc.py::test_assigned_test_is_restricted_to_its_analyst_and_boundaries_are_inclusive` | not run |
|  |  |  | `tests/workflows/test_qc.py::test_result_amendment_workflow_retains_original` | not run |
| URS-QC-03 | Critical | BR-QC-002 | `tests/workflows/test_qc.py::test_calibration_gate_blocks_testing_and_override_is_controlled` | not run |
| URS-QC-04 | Critical | BR-QC-007, BR-STAT-002 | `tests/workflows/test_qc.py::test_failing_result_raises_oos_and_places_hold` | not run |
|  |  |  | `tests/workflows/test_qc.py::test_oos_invalidated_allows_retest_and_release_path` | not run |
|  |  |  | `tests/workflows/test_qc.py::test_oos_confirmed_rejects_lot` | not run |
|  |  |  | `tests/workflows/test_qc.py::test_oot_alert_limit_flags_but_never_changes_disposition` | not run |
| URS-QC-05 | Critical | BR-REL-001..004, BR-QC-006 | `tests/workflows/test_qc.py::test_full_release_chain_to_approved_coa_and_issuable_lot` | not run |
|  |  |  | `tests/workflows/test_qc.py::test_release_chain_enforces_order_roles_and_separation_of_duties` | not run |
|  |  |  | `tests/workflows/test_qc.py::test_one_person_cannot_hold_two_release_steps_sod03` | not run |
|  |  |  | `tests/workflows/test_qc.py::test_analyst_who_tested_cannot_review_even_with_reviewer_role` | not run |
|  |  |  | `tests/workflows/test_qc.py::test_release_rejection_makes_lot_unissuable_crit_05` | not run |
|  |  |  | `tests/workflows/test_qc.py::test_release_blocked_by_missing_coa_hold_or_open_oos` | not run |
|  |  |  | `tests/workflows/test_qc.py::test_coa_requires_release_and_reissue_creates_new_version` | not run |
| URS-QC-06 | Critical | BR-CRL-001..004 | `tests/workflows/test_qc.py::test_conditional_release_is_a_controlled_exception` | not run |
|  |  |  | `tests/workflows/test_manufacturing.py::test_conditional_material_blocks_batch_release` | not run |
| URS-QC-07 | Major | BR-STAT-001 | `tests/workflows/test_qc.py::test_stats_reference_values_and_status_codes` | not run |
|  |  |  | `tests/workflows/test_qc.py::test_nelson_rules_and_control_limits` | not run |
|  |  |  | `tests/workflows/test_qc.py::test_trend_endpoint_groups_and_capability_status` | not run |
|  |  |  | `tests/workflows/test_qc.py::test_sample_retention_and_disposal` | not run |

## Manufacturing

| URS | Impact | Rules | Test (path::function) | Result |
|---|---|---|---|---|
| URS-MFG-01 | Critical | BR-BOM-001/002 | `tests/workflows/test_manufacturing.py::test_bom_lifecycle_and_immutability` | not run |
|  |  |  | `tests/workflows/test_manufacturing.py::test_bom_validation` | not run |
|  |  |  | `tests/workflows/test_manufacturing.py::test_batch_requires_approved_bom_and_scales_requirements` | not run |
| URS-MFG-02 | Critical | BR-BAT-001/002 | `tests/workflows/test_manufacturing.py::test_duplicate_batch_number_prevented_and_override_controlled` | not run |
| URS-MFG-03 | Critical | BR-ISS-001..007, BR-TRC-001 | `tests/validation/test_critical_15.py::test_crit_14_issued_material_is_always_linked_to_lot_and_production_batch` | not run |
|  |  |  | `tests/workflows/test_manufacturing.py::test_issue_links_lot_and_batch_and_posts_ledger` | not run |
|  |  |  | `tests/workflows/test_manufacturing.py::test_issue_is_audited_and_traceable` | not run |
| URS-MFG-04 | Major | BR-RET-001 | `tests/workflows/test_manufacturing.py::test_return_workflow_and_sod` | not run |
| URS-MFG-05 | Critical | BR-MFG-001..004 | `tests/workflows/test_manufacturing.py::test_process_execution_controls` | not run |
|  |  |  | `tests/workflows/test_manufacturing.py::test_ipc_failure_places_batch_on_hold_and_blocks_completion` | not run |
|  |  |  | `tests/workflows/test_manufacturing.py::test_equipment_gate` | not run |
| URS-MFG-06 | Critical | BR-REC-001 | `tests/validation/test_critical_15.py::test_crit_15_reconciliation_discrepancy_is_highlighted_and_blocks_progress` | not run |
|  |  |  | `tests/workflows/test_manufacturing.py::test_reconciliation_within_tolerance` | not run |
|  |  |  | `tests/workflows/test_manufacturing.py::test_reconciliation_discrepancy_blocks_until_qa_deviation` | not run |
| URS-MFG-07 | Major | BR-ANM-001..003 | `tests/workflows/test_manufacturing.py::test_output_lot_flows_into_qc_and_release_marks_batch` | not run |
|  |  |  | `tests/workflows/test_manufacturing.py::test_antisera_animal_bleed_pool_genealogy` | not run |

## Dispatch

| URS | Impact | Rules | Test (path::function) | Result |
|---|---|---|---|---|
| URS-DSP-01 | Critical | BR-DSP-001..006 | `tests/workflows/test_dispatch.py::test_crit_06_unreleased_fg_cannot_be_dispatched` | not run |
|  |  |  | `tests/workflows/test_dispatch.py::test_hold_expiry_customer_and_oos_blocks` | not run |
|  |  |  | `tests/workflows/test_dispatch.py::test_rm_and_wrong_type_cannot_be_dispatched` | not run |
| URS-DSP-02 | Critical | BR-DSP-003/006 | `tests/workflows/test_dispatch.py::test_released_fg_full_dispatch_flow` | not run |
|  |  |  | `tests/workflows/test_dispatch.py::test_sod_creator_cannot_approve` | not run |
|  |  |  | `tests/workflows/test_dispatch.py::test_hold_after_validation_blocks_approval_and_dispatch_and_cancel_releases_stock` | not run |
|  |  |  | `tests/workflows/test_dispatch.py::test_dispatch_is_audited_and_permissioned` | not run |

## Traceability

| URS | Impact | Rules | Test (path::function) | Result |
|---|---|---|---|---|
| URS-TRC-01 | Critical | BR-TRC-001 | `tests/workflows/test_dispatch.py::test_traceability_backward_and_forward_are_complete` | not run |
|  |  |  | `tests/workflows/test_dispatch.py::test_trace_excludes_undispatched_and_antisera_genealogy` | not run |
|  |  |  | `tests/workflows/test_dispatch.py::test_global_search_respects_permissions_and_qr_resolve` | not run |

## Quality system

| URS | Impact | Rules | Test (path::function) | Result |
|---|---|---|---|---|
| URS-QS-01 | Critical | BR-DEV-001..003 | `tests/workflows/test_quality_system.py::test_open_deviation_blocks_release_until_closed_with_independent_qa_signature` | not run |
|  |  |  | `tests/workflows/test_quality_system.py::test_deviation_raiser_cannot_close_and_non_blocking_flag` | not run |
|  |  |  | `tests/workflows/test_quality_system.py::test_temperature_excursion_raises_deviation_and_hold` | not run |
|  |  |  | `tests/workflows/test_quality_system.py::test_ipc_failure_raises_deviation_on_batch` | not run |
|  |  |  | `tests/workflows/test_quality_system.py::test_reconciliation_deviation_blocks_output_lot_release` | not run |
| URS-QS-02 | Major | BR-CAPA-001/002 | `tests/workflows/test_quality_system.py::test_capa_lifecycle_effectiveness_and_sod` | not run |
|  |  |  | `tests/workflows/test_quality_system.py::test_capa_creator_cannot_close_own_capa` | not run |
| URS-QS-03 | Critical | BR-CC-001..003, BR-BOM-002, BR-VM-001 | `tests/workflows/test_quality_system.py::test_change_control_gates_new_master_versions` | not run |
|  |  |  | `tests/workflows/test_quality_system.py::test_change_control_requester_cannot_approve_and_rejection` | not run |
| URS-QS-04 | Major | BR-RSK-001 | `tests/workflows/test_quality_system.py::test_fmea_rpn_levels_and_approval_rules` | not run |
| URS-QS-05 | Major | BR-SOP-001/002 | `tests/workflows/test_quality_system.py::test_sop_versioning_acknowledgement_and_review_due` | not run |
| URS-QS-06 | Critical | BR-CMP-001, BR-RCL-001..004 | `tests/workflows/test_quality_system.py::test_critical_complaint_holds_lot_and_needs_closed_deviation` | not run |
|  |  |  | `tests/workflows/test_quality_system.py::test_recall_derives_affected_customers_and_reconciles_returns` | not run |
|  |  |  | `tests/workflows/test_quality_system.py::test_quality_endpoints_are_permissioned_and_listed` | not run |

## Reports

| URS | Impact | Rules | Test (path::function) | Result |
|---|---|---|---|---|
| URS-RPT-01 | Major |  | `tests/workflows/test_reports.py::test_catalogue_size_and_every_report_runs_with_data` | not run |
|  |  |  | `tests/workflows/test_reports.py::test_report_permissions_params_and_no_field_leak` | not run |
|  |  |  | `tests/integration/test_master_data.py::test_exports_have_report_header_and_are_audited` | not run |
| URS-RPT-02 | Critical | BR-DOC-001 | `tests/workflows/test_reports.py::test_exports_are_controlled_copies_with_hash_verification` | not run |
|  |  |  | `tests/workflows/test_reports.py::test_controlled_business_documents_pdf` | not run |
| URS-RPT-03 | Minor |  | `tests/workflows/test_reports.py::test_dashboards_are_role_gated_and_populated` | not run |
|  |  |  | `tests/workflows/test_reports.py::test_report_performance_with_large_ledger` | not run |
|  |  |  | `tests/integration/test_company_documents.py::test_dashboard_cards` | not run |

## Data integrity

| URS | Impact | Rules | Test (path::function) | Result |
|---|---|---|---|---|
| URS-DI-01 | Critical | BR-RET-001/002 | `tests/workflows/test_reports.py::test_retention_policies_archive_and_legal_hold` | not run |
|  |  |  | `tests/integration/test_audit_trail.py::test_physical_delete_of_audited_record_refused` | not run |
| URS-DI-02 | Major |  | `tests/workflows/test_reports.py::test_backup_status_and_restore_evidence` | not run |

## Summary

* Requirements: **58**; all have at least one automated test: **True**
* Mapped test references: **189** (distinct tests: **187**)
* Results of mapped tests: not run: 189
* Collected automated tests in total: **230**; not referenced by a requirement (supporting/unit tests): **43**

### The 15 mandatory critical tests (prompt §77)

| # | Rule | Test |
|---|---|---|
| 1 | Expired vendor qualification blocks PO | `tests/workflows/test_purchase_rules.py::test_crit_01_expired_vendor_cannot_create_po` — not run |
| 2 | Unapproved vendor blocks PO | `tests/workflows/test_purchase_rules.py::test_crit_02_unapproved_vendor_cannot_purchase` — not run |
| 3 | Vendor not approved for material blocks PO | `tests/workflows/test_purchase_rules.py::test_crit_03_wrong_vendor_material_combination` — not run |
| 4 | Quarantine material cannot be issued | `tests/workflows/test_warehouse.py::test_crit_04_quarantine_material_cannot_be_issued` — not run |
| 5 | Rejected material cannot be issued | `tests/workflows/test_warehouse.py::test_crit_05_rejected_and_crit_07_expired_material_cannot_be_issued` — not run |
| 6 | Unreleased FG cannot be dispatched | `tests/workflows/test_dispatch.py::test_crit_06_unreleased_fg_cannot_be_dispatched` — not run |
| 7 | Expired material cannot be issued | `tests/workflows/test_warehouse.py::test_crit_05_rejected_and_crit_07_expired_material_cannot_be_issued` — not run |
| 8 | Quality hold blocks issue/use/dispatch | `tests/validation/test_critical_15.py::test_crit_08_quality_hold_blocks_issue_use_and_dispatch` — not run |
| 9 | Audit trail cannot be modified/deleted | `tests/validation/test_critical_15.py::test_crit_09_audit_trail_cannot_be_modified_or_deleted` — not run |
| 10 | E-signature required for configured actions | `tests/validation/test_critical_15.py::test_crit_10_electronic_signature_required_and_bound_to_the_record` — not run |
| 11 | Creator cannot approve own transaction | `tests/validation/test_critical_15.py::test_crit_11_creator_cannot_approve_own_transaction` — not run |
| 12 | Historical GMP records never overwritten | `tests/validation/test_critical_15.py::test_crit_12_historical_gmp_records_are_never_overwritten` — not run |
| 13 | Every movement creates an inventory transaction | `tests/validation/test_critical_15.py::test_crit_13_every_stock_movement_creates_an_inventory_transaction` — not run |
| 14 | Issued material linked to production batch | `tests/validation/test_critical_15.py::test_crit_14_issued_material_is_always_linked_to_lot_and_production_batch` — not run |
| 15 | Reconciliation discrepancy highlighted | `tests/validation/test_critical_15.py::test_crit_15_reconciliation_discrepancy_is_highlighted_and_blocks_progress` — not run |

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
