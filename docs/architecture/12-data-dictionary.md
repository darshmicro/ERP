# Data Dictionary

Generated from the SQLAlchemy metadata on 2026-10-05 — **109 tables**. Append-only tables are protected by database triggers (`app/audit/immutability.py`).

## Module `audit`

### `audit_chain_head`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| id | INTEGER | no | PK |  |
| lock_counter | BIGINT | no | default 0 |  |
| last_hash | VARCHAR(64) | no | default GENESIS |  |
| row_count | BIGINT | no | default 0 |  |

### `audit_trail` — **append-only**

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| occurred_at | DATETIME (UTC) | no |  |  |
| tz_name | VARCHAR(60) | no |  |  |
| module | VARCHAR(40) | no |  |  |
| entity | VARCHAR(80) | no |  |  |
| record_id | VARCHAR(60) | yes |  |  |
| action | VARCHAR(40) | no |  |  |
| field_name | VARCHAR(80) | yes |  |  |
| old_value | TEXT | yes |  |  |
| new_value | TEXT | yes |  |  |
| user_id | BIGINT | yes |  |  |
| user_name | VARCHAR(150) | no |  |  |
| role_name | VARCHAR(300) | yes |  |  |
| session_id | VARCHAR(40) | yes |  |  |
| ip_address | VARCHAR(64) | yes |  |  |
| device_info | VARCHAR(300) | yes |  |  |
| reason | VARCHAR(1000) | yes |  |  |
| signature_id | BIGINT | yes |  |  |
| correlation_id | VARCHAR(40) | yes |  |  |
| prev_hash | VARCHAR(64) | no |  |  |
| row_hash | VARCHAR(64) | no |  |  |
| id | BIGINT | no | PK |  |

### `e_signature` — **append-only**

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| user_id | BIGINT | no | FK → users.id |  |
| signed_at | DATETIME (UTC) | no |  |  |
| tz_name | VARCHAR(60) | no |  |  |
| printed_name | VARCHAR(150) | no |  |  |
| username | VARCHAR(80) | no |  |  |
| role_name | VARCHAR(300) | yes |  |  |
| meaning | VARCHAR(40) | no |  |  |
| reason | VARCHAR(1000) | yes |  |  |
| entity | VARCHAR(80) | no |  |  |
| record_id | VARCHAR(60) | no |  |  |
| record_version | VARCHAR(30) | yes |  |  |
| record_hash | VARCHAR(64) | no |  |  |
| auth_method | VARCHAR(10) | no |  |  |
| ip_address | VARCHAR(64) | yes |  |  |
| manifest_hash | VARCHAR(64) | no |  |  |
| id | BIGINT | no | PK |  |

### `error_log`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| id | BIGINT | no | PK |  |
| occurred_at | DATETIME (UTC) | no |  |  |
| correlation_id | VARCHAR(40) | yes |  |  |
| route | VARCHAR(200) | yes |  |  |
| user_id | BIGINT | yes |  |  |
| error_type | VARCHAR(120) | yes |  |  |

### `gmp_status_history` — **append-only**

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| entity | VARCHAR(80) | no |  |  |
| record_id | VARCHAR(60) | no |  |  |
| from_status | VARCHAR(40) | yes |  |  |
| to_status | VARCHAR(40) | no |  |  |
| user_id | BIGINT | yes |  |  |
| signature_id | BIGINT | yes |  |  |
| reason | VARCHAR(1000) | yes |  |  |
| occurred_at | DATETIME (UTC) | no |  |  |
| id | BIGINT | no | PK |  |

### `record_action` — **append-only**

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| entity | VARCHAR(80) | no |  |  |
| record_id | VARCHAR(60) | no |  |  |
| action_code | VARCHAR(100) | no |  |  |
| user_id | BIGINT | no |  |  |
| occurred_at | DATETIME (UTC) | no |  |  |
| id | BIGINT | no | PK |  |

### `security_event` — **append-only**

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| occurred_at | DATETIME (UTC) | no |  |  |
| event_type | VARCHAR(40) | no |  |  |
| user_id | BIGINT | yes |  |  |
| username | VARCHAR(80) | yes |  |  |
| ip_address | VARCHAR(64) | yes |  |  |
| detail | TEXT | yes |  |  |
| correlation_id | VARCHAR(40) | yes |  |  |
| id | BIGINT | no | PK |  |

## Module `dispatch`

### `dispatch`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| dispatch_no | VARCHAR(30) | no |  |  |
| dispatch_date | DATE | no |  |  |
| customer_id | BIGINT | no | FK → customer.id |  |
| invoice_no | VARCHAR(40) | yes |  |  |
| transporter | VARCHAR(100) | yes |  |  |
| vehicle_no | VARCHAR(30) | yes |  |  |
| lr_no | VARCHAR(40) | yes |  |  |
| shipping_address | TEXT | yes |  |  |
| remarks | VARCHAR(500) | yes |  |  |
| status | VARCHAR(15) | no | default DRAFT |  |
| validation_snapshot | TEXT | yes |  |  |
| created_by_user_id | BIGINT | no |  |  |
| approved_by_id | BIGINT | yes |  |  |
| approved_signature_id | BIGINT | yes | FK → e_signature.id |  |
| approved_at | DATETIME (UTC) | yes |  |  |
| dispatched_by_id | BIGINT | yes |  |  |
| dispatched_at | DATETIME (UTC) | yes |  |  |
| delivered_at | DATETIME (UTC) | yes |  |  |
| delivery_remarks | VARCHAR(300) | yes |  |  |
| cancel_reason | VARCHAR(500) | yes |  |  |
| id | BIGINT | no | PK |  |
| created_at | DATETIME (UTC) | no |  |  |
| created_by_id | BIGINT | yes |  |  |
| updated_at | DATETIME (UTC) | yes |  |  |
| updated_by_id | BIGINT | yes |  |  |
| row_version | INTEGER | no | default 1 |  |

Constraints: `UniqueConstraint: uq_dispatch_dispatch_no`; `CheckConstraint: ck_dispatch_status status IN ('DRAFT', 'VALIDATED', 'APPROVED', 'DISPATCHED', 'DELIVERED', 'CANCELLED')`

### `dispatch_line`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| dispatch_id | BIGINT | no | FK → dispatch.id |  |
| line_no | INTEGER | no |  |  |
| material_batch_id | BIGINT | no | FK → material_batch.id |  |
| location_id | BIGINT | no | FK → location.id |  |
| quantity | NUMERIC(18, 6) | no |  |  |
| unit_id | BIGINT | no | FK → unit.id |  |
| reserved | BOOLEAN | no | default False |  |
| coa_id | BIGINT | yes |  |  |
| ledger_txn_id | BIGINT | yes |  |  |
| id | BIGINT | no | PK |  |
| created_at | DATETIME (UTC) | no |  |  |
| created_by_id | BIGINT | yes |  |  |
| updated_at | DATETIME (UTC) | yes |  |  |
| updated_by_id | BIGINT | yes |  |  |
| row_version | INTEGER | no | default 1 |  |

Constraints: `UniqueConstraint: uq_dispatch_line_dispatch_id`; `CheckConstraint: ck_dispatch_line_qty quantity > 0`

## Module `iam`

### `password_history`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| id | BIGINT | no | PK |  |
| user_id | BIGINT | no | FK → users.id |  |
| password_hash | VARCHAR(300) | no |  |  |
| set_at | DATETIME (UTC) | no |  |  |

### `permission`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| id | BIGINT | no | PK |  |
| perm_code | VARCHAR(100) | no |  |  |
| module | VARCHAR(40) | no |  |  |
| resource | VARCHAR(40) | no |  |  |
| action | VARCHAR(40) | no |  |  |
| description | VARCHAR(200) | yes |  |  |

Constraints: `UniqueConstraint: uq_permission_perm_code`

### `role`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| role_code | VARCHAR(50) | no |  |  |
| name | VARCHAR(100) | no |  |  |
| description | VARCHAR(300) | yes |  |  |
| is_system | BOOLEAN | no | default False |  |
| is_admin_role | BOOLEAN | no | default False |  |
| is_active | BOOLEAN | no | default True |  |
| id | BIGINT | no | PK |  |
| created_at | DATETIME (UTC) | no |  |  |
| created_by_id | BIGINT | yes |  |  |
| updated_at | DATETIME (UTC) | yes |  |  |
| updated_by_id | BIGINT | yes |  |  |
| row_version | INTEGER | no | default 1 |  |

Constraints: `UniqueConstraint: uq_role_role_code`

### `role_permission`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| role_id | BIGINT | no | FK → role.id |  |
| permission_id | BIGINT | no | FK → permission.id |  |
| revoked_at | DATETIME (UTC) | yes |  |  |
| id | BIGINT | no | PK |  |
| created_at | DATETIME (UTC) | no |  |  |
| created_by_id | BIGINT | yes |  |  |
| updated_at | DATETIME (UTC) | yes |  |  |
| updated_by_id | BIGINT | yes |  |  |
| row_version | INTEGER | no | default 1 |  |

Constraints: `UniqueConstraint: uq_role_permission_role_id`

### `sod_rule`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| sod_id | VARCHAR(20) | no |  |  |
| action_code | VARCHAR(100) | no |  |  |
| conflicts_with_action_code | VARCHAR(100) | no |  |  |
| enforcement | VARCHAR(10) | no | default BLOCK |  |
| description | VARCHAR(300) | yes |  |  |
| is_active | BOOLEAN | no | default True |  |
| id | BIGINT | no | PK |  |
| created_at | DATETIME (UTC) | no |  |  |
| created_by_id | BIGINT | yes |  |  |
| updated_at | DATETIME (UTC) | yes |  |  |
| updated_by_id | BIGINT | yes |  |  |
| row_version | INTEGER | no | default 1 |  |

Constraints: `CheckConstraint: ck_sod_rule_enforcement enforcement IN ('BLOCK','WARN')`; `UniqueConstraint: uq_sod_rule_action_code`

### `training_record`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| user_id | BIGINT | no | FK → users.id |  |
| training_code | VARCHAR(60) | no |  |  |
| document_version | VARCHAR(20) | yes |  |  |
| trained_on | DATE | no |  |  |
| valid_until | DATE | yes |  |  |
| remarks | TEXT | yes |  |  |
| id | BIGINT | no | PK |  |
| created_at | DATETIME (UTC) | no |  |  |
| created_by_id | BIGINT | yes |  |  |
| updated_at | DATETIME (UTC) | yes |  |  |
| updated_by_id | BIGINT | yes |  |  |
| row_version | INTEGER | no | default 1 |  |

### `user_role`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| user_id | BIGINT | no | FK → users.id |  |
| role_id | BIGINT | no | FK → role.id |  |
| granted_by_id | BIGINT | yes | FK → users.id |  |
| valid_from | DATE | no |  |  |
| valid_to | DATE | yes |  |  |
| is_disabled | BOOLEAN | no | default False |  |
| revoked_at | DATETIME (UTC) | yes |  |  |
| reason | VARCHAR(500) | yes |  |  |
| id | BIGINT | no | PK |  |
| created_at | DATETIME (UTC) | no |  |  |
| created_by_id | BIGINT | yes |  |  |
| updated_at | DATETIME (UTC) | yes |  |  |
| updated_by_id | BIGINT | yes |  |  |
| row_version | INTEGER | no | default 1 |  |

Constraints: `UniqueConstraint: uq_user_role_user_id`

### `user_session`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| id | BIGINT | no | PK |  |
| user_id | BIGINT | no | FK → users.id |  |
| token_hash | VARCHAR(64) | no |  |  |
| csrf_token | VARCHAR(64) | no |  |  |
| created_at | DATETIME (UTC) | no |  |  |
| last_seen_at | DATETIME (UTC) | no |  |  |
| absolute_expires_at | DATETIME (UTC) | no |  |  |
| ip_address | VARCHAR(64) | yes |  |  |
| user_agent | VARCHAR(300) | yes |  |  |
| revoked_at | DATETIME (UTC) | yes |  |  |
| revoke_reason | VARCHAR(100) | yes |  |  |

Constraints: `UniqueConstraint: uq_user_session_token_hash`

### `users`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| username | VARCHAR(80) | no |  |  |
| full_name | VARCHAR(150) | no |  |  |
| email | VARCHAR(150) | yes |  |  |
| designation | VARCHAR(100) | yes |  |  |
| department_id | BIGINT | yes | FK → department.id |  |
| plant_id | BIGINT | yes | FK → plant.id |  |
| auth_source | VARCHAR(10) | no | default LOCAL |  |
| password_hash | VARCHAR(300) | yes |  |  |
| password_changed_at | DATETIME (UTC) | yes |  |  |
| must_change_password | BOOLEAN | no | default True |  |
| is_active | BOOLEAN | no | default True |  |
| access_expiry | DATE | yes |  |  |
| failed_attempts | INTEGER | no | default 0 |  |
| locked_until | DATETIME (UTC) | yes |  |  |
| last_login_at | DATETIME (UTC) | yes |  |  |
| id | BIGINT | no | PK |  |
| created_at | DATETIME (UTC) | no |  |  |
| created_by_id | BIGINT | yes |  |  |
| updated_at | DATETIME (UTC) | yes |  |  |
| updated_by_id | BIGINT | yes |  |  |
| row_version | INTEGER | no | default 1 |  |

Constraints: `CheckConstraint: ck_users_auth_source auth_source IN ('LOCAL','LDAP')`; `UniqueConstraint: uq_users_username`

## Module `importing`

### `import_job`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| id | BIGINT | no | PK |  |
| entity | VARCHAR(30) | no |  |  |
| status | VARCHAR(20) | no | default UPLOADED |  |
| filename | VARCHAR(260) | no |  |  |
| document_id | BIGINT | no | FK → document.id |  |
| total_rows | INTEGER | no | default 0 |  |
| error_rows | INTEGER | no | default 0 |  |
| created_by_id | BIGINT | no |  |  |
| created_at | DATETIME (UTC) | no |  |  |
| submitted_by_id | BIGINT | yes |  |  |
| approved_by_id | BIGINT | yes |  |  |
| approved_signature_id | BIGINT | yes |  |  |
| imported_at | DATETIME (UTC) | yes |  |  |
| result_summary | TEXT | yes |  |  |

Constraints: `CheckConstraint: ck_import_job_status status IN ('UPLOADED','VALIDATED','REJECTED','SUBMITTED','APPROVED','IMPORTED','FAILED')`

### `import_row`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| id | BIGINT | no | PK |  |
| job_id | BIGINT | no | FK → import_job.id |  |
| row_no | INTEGER | no |  |  |
| data_json | TEXT | no |  |  |
| status | VARCHAR(10) | no | default VALID |  |
| errors_json | TEXT | yes |  |  |

## Module `manufacturing`

### `animal`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| animal_tag | VARCHAR(30) | no |  |  |
| species | VARCHAR(40) | no | default Equine |  |
| date_of_birth | DATE | yes |  |  |
| weight_kg | NUMERIC(7, 2) | yes |  |  |
| status | VARCHAR(12) | no | default ACTIVE |  |
| health_notes | VARCHAR(500) | yes |  |  |
| min_bleed_interval_days | INTEGER | no | default 14 |  |
| id | BIGINT | no | PK |  |
| created_at | DATETIME (UTC) | no |  |  |
| created_by_id | BIGINT | yes |  |  |
| updated_at | DATETIME (UTC) | yes |  |  |
| updated_by_id | BIGINT | yes |  |  |
| row_version | INTEGER | no | default 1 |  |

Constraints: `UniqueConstraint: uq_animal_animal_tag`; `CheckConstraint: ck_animal_status status IN ('ACTIVE','QUARANTINED','RETIRED','DECEASED')`

### `batch_equipment_use`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| batch_id | BIGINT | no | FK → manufacturing_batch.id |  |
| equipment_id | BIGINT | no | FK → equipment.id |  |
| used_by_id | BIGINT | no |  |  |
| started_at | DATETIME (UTC) | no |  |  |
| ended_at | DATETIME (UTC) | yes |  |  |
| calibration_status | VARCHAR(20) | yes |  |  |
| cleaning_confirmed | BOOLEAN | no | default False |  |
| id | BIGINT | no | PK |  |
| created_at | DATETIME (UTC) | no |  |  |
| created_by_id | BIGINT | yes |  |  |
| updated_at | DATETIME (UTC) | yes |  |  |
| updated_by_id | BIGINT | yes |  |  |
| row_version | INTEGER | no | default 1 |  |

### `batch_material`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| batch_id | BIGINT | no | FK → manufacturing_batch.id |  |
| bom_line_id | BIGINT | no | FK → bom_line.id |  |
| material_id | BIGINT | no | FK → material.id |  |
| unit_id | BIGINT | no | FK → unit.id |  |
| required_qty | NUMERIC(18, 6) | no |  |  |
| reconcile | BOOLEAN | no | default True |  |
| issued_qty | NUMERIC(18, 6) | no | default 0 |  |
| returned_qty | NUMERIC(18, 6) | no | default 0 |  |
| consumed_qty | NUMERIC(18, 6) | yes |  |  |
| sample_qty | NUMERIC(18, 6) | yes |  |  |
| waste_qty | NUMERIC(18, 6) | yes |  |  |
| id | BIGINT | no | PK |  |
| created_at | DATETIME (UTC) | no |  |  |
| created_by_id | BIGINT | yes |  |  |
| updated_at | DATETIME (UTC) | yes |  |  |
| updated_by_id | BIGINT | yes |  |  |
| row_version | INTEGER | no | default 1 |  |

Constraints: `UniqueConstraint: uq_batch_material_batch_id`; `CheckConstraint: ck_batch_material_required required_qty >= 0`

### `batch_reconciliation`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| batch_id | BIGINT | no | FK → manufacturing_batch.id |  |
| status | VARCHAR(20) | no | default CALCULATED |  |
| within_tolerance | BOOLEAN | no |  |  |
| yield_ok | BOOLEAN | no | default True |  |
| tolerance_pct | NUMERIC(6, 3) | no |  |  |
| summary_json | TEXT | no |  |  |
| deviation_ref | VARCHAR(60) | yes |  |  |
| justification | VARCHAR(500) | yes |  |  |
| production_approved_by_id | BIGINT | yes |  |  |
| production_signature_id | BIGINT | yes | FK → e_signature.id |  |
| qa_approved_by_id | BIGINT | yes |  |  |
| qa_signature_id | BIGINT | yes | FK → e_signature.id |  |
| approved_at | DATETIME (UTC) | yes |  |  |
| id | BIGINT | no | PK |  |
| created_at | DATETIME (UTC) | no |  |  |
| created_by_id | BIGINT | yes |  |  |
| updated_at | DATETIME (UTC) | yes |  |  |
| updated_by_id | BIGINT | yes |  |  |
| row_version | INTEGER | no | default 1 |  |

Constraints: `CheckConstraint: ck_batch_reconciliation_status status IN ('CALCULATED','PRODUCTION_APPROVED','APPROVED')`; `UniqueConstraint: uq_batch_reconciliation_batch_id`

### `batch_step_execution`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| batch_id | BIGINT | no | FK → manufacturing_batch.id |  |
| step_no | INTEGER | no |  |  |
| instruction | VARCHAR(1000) | no |  |  |
| requires_verification | BOOLEAN | no | default True |  |
| recorded_value | VARCHAR(200) | yes |  |  |
| performed_by_id | BIGINT | yes |  |  |
| performed_at | DATETIME (UTC) | yes |  |  |
| verified_by_id | BIGINT | yes |  |  |
| verified_at | DATETIME (UTC) | yes |  |  |
| verify_signature_id | BIGINT | yes | FK → e_signature.id |  |
| remarks | VARCHAR(300) | yes |  |  |
| id | BIGINT | no | PK |  |
| created_at | DATETIME (UTC) | no |  |  |
| created_by_id | BIGINT | yes |  |  |
| updated_at | DATETIME (UTC) | yes |  |  |
| updated_by_id | BIGINT | yes |  |  |
| row_version | INTEGER | no | default 1 |  |

Constraints: `UniqueConstraint: uq_batch_step_execution_batch_id`

### `bleed_record`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| bleed_no | VARCHAR(30) | no |  |  |
| animal_id | BIGINT | no | FK → animal.id |  |
| bled_on | DATE | no |  |  |
| volume_l | NUMERIC(9, 3) | no |  |  |
| recorded_by_id | BIGINT | yes |  |  |
| remarks | VARCHAR(300) | yes |  |  |
| pool_id | BIGINT | yes |  |  |
| id | BIGINT | no | PK |  |
| created_at | DATETIME (UTC) | no |  |  |
| created_by_id | BIGINT | yes |  |  |
| updated_at | DATETIME (UTC) | yes |  |  |
| updated_by_id | BIGINT | yes |  |  |
| row_version | INTEGER | no | default 1 |  |

Constraints: `CheckConstraint: ck_bleed_record_vol volume_l > 0`; `UniqueConstraint: uq_bleed_record_bleed_no`

### `bom_header`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| bom_no | VARCHAR(40) | no |  |  |
| version_no | INTEGER | no | default 1 |  |
| product_material_id | BIGINT | no | FK → material.id |  |
| status | VARCHAR(20) | no | default DRAFT |  |
| batch_size | NUMERIC(18, 6) | no |  |  |
| unit_id | BIGINT | no | FK → unit.id |  |
| expected_yield_pct | NUMERIC(6, 2) | no | default 100 |  |
| yield_min_pct | NUMERIC(6, 2) | yes |  |  |
| yield_max_pct | NUMERIC(6, 2) | yes |  |  |
| description | VARCHAR(300) | yes |  |  |
| supersedes_id | BIGINT | yes | FK → bom_header.id |  |
| effective_from | DATETIME (UTC) | yes |  |  |
| effective_to | DATETIME (UTC) | yes |  |  |
| change_reason | VARCHAR(1000) | yes |  |  |
| approved_signature_id | BIGINT | yes | FK → e_signature.id |  |
| id | BIGINT | no | PK |  |
| created_at | DATETIME (UTC) | no |  |  |
| created_by_id | BIGINT | yes |  |  |
| updated_at | DATETIME (UTC) | yes |  |  |
| updated_by_id | BIGINT | yes |  |  |
| row_version | INTEGER | no | default 1 |  |

Constraints: `CheckConstraint: ck_bom_header_batch_size batch_size > 0`; `UniqueConstraint: uq_bom_header_bom_no`; `CheckConstraint: ck_bom_header_status status IN ('DRAFT','UNDER_REVIEW','APPROVED','SUPERSEDED')`

### `bom_line`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| bom_id | BIGINT | no | FK → bom_header.id |  |
| line_no | INTEGER | no |  |  |
| seq | INTEGER | no | default 1 |  |
| material_id | BIGINT | no | FK → material.id |  |
| quantity | NUMERIC(18, 6) | no |  |  |
| unit_id | BIGINT | no | FK → unit.id |  |
| percentage | NUMERIC(9, 4) | yes |  |  |
| process_loss_pct | NUMERIC(6, 2) | no | default 0 |  |
| overage_pct | NUMERIC(6, 2) | no | default 0 |  |
| sampling_qty | NUMERIC(18, 6) | no | default 0 |  |
| reconcile | BOOLEAN | no | default True |  |
| id | BIGINT | no | PK |  |
| created_at | DATETIME (UTC) | no |  |  |
| created_by_id | BIGINT | yes |  |  |
| updated_at | DATETIME (UTC) | yes |  |  |
| updated_by_id | BIGINT | yes |  |  |
| row_version | INTEGER | no | default 1 |  |

Constraints: `CheckConstraint: ck_bom_line_quantity quantity > 0`; `CheckConstraint: ck_bom_line_pct overage_pct >= 0 AND process_loss_pct >= 0`; `UniqueConstraint: uq_bom_line_bom_id`

### `immunisation_record` — **append-only**

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| animal_id | BIGINT | no | FK → animal.id |  |
| antigen | VARCHAR(100) | no |  |  |
| dose | VARCHAR(60) | yes |  |  |
| administered_on | DATE | no |  |  |
| administered_by_id | BIGINT | yes |  |  |
| remarks | VARCHAR(300) | yes |  |  |
| id | BIGINT | no | PK |  |

### `ipc_result` — **append-only**

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| batch_id | BIGINT | no | FK → manufacturing_batch.id |  |
| stage | VARCHAR(60) | no |  |  |
| parameter | VARCHAR(100) | no |  |  |
| value_numeric | NUMERIC(18, 6) | yes |  |  |
| value_text | VARCHAR(200) | yes |  |  |
| unit | VARCHAR(20) | yes |  |  |
| lsl | NUMERIC(18, 6) | yes |  |  |
| usl | NUMERIC(18, 6) | yes |  |  |
| pass_fail | VARCHAR(4) | no |  |  |
| equipment_id | BIGINT | yes | FK → equipment.id |  |
| analyst_id | BIGINT | yes |  |  |
| recorded_at | DATETIME (UTC) | no |  |  |
| remarks | VARCHAR(300) | yes |  |  |
| id | BIGINT | no | PK |  |

Constraints: `CheckConstraint: ck_ipc_result_pass_fail pass_fail IN ('PASS','FAIL','NA')`

### `manufacturing_batch`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| batch_no | VARCHAR(40) | no |  |  |
| batch_type | VARCHAR(3) | no |  |  |
| product_material_id | BIGINT | no | FK → material.id |  |
| bom_id | BIGINT | no | FK → bom_header.id |  |
| planned_qty | NUMERIC(18, 6) | no |  |  |
| unit_id | BIGINT | no | FK → unit.id |  |
| actual_qty | NUMERIC(18, 6) | yes |  |  |
| yield_pct | NUMERIC(7, 2) | yes |  |  |
| status | VARCHAR(20) | no | default CREATED |  |
| created_by_user_id | BIGINT | no |  |  |
| number_override_reason | VARCHAR(300) | yes |  |  |
| uses_conditional_release | BOOLEAN | no | default False |  |
| line_clearance_signature_id | BIGINT | yes | FK → e_signature.id |  |
| output_lot_id | BIGINT | yes |  |  |
| start_at | DATETIME (UTC) | yes |  |  |
| end_at | DATETIME (UTC) | yes |  |  |
| cancel_reason | VARCHAR(300) | yes |  |  |
| id | BIGINT | no | PK |  |
| created_at | DATETIME (UTC) | no |  |  |
| created_by_id | BIGINT | yes |  |  |
| updated_at | DATETIME (UTC) | yes |  |  |
| updated_by_id | BIGINT | yes |  |  |
| row_version | INTEGER | no | default 1 |  |

Constraints: `UniqueConstraint: uq_manufacturing_batch_batch_no`; `CheckConstraint: ck_manufacturing_batch_batch_type batch_type IN ('SFG','FG')`; `CheckConstraint: ck_manufacturing_batch_planned planned_qty > 0`; `CheckConstraint: ck_manufacturing_batch_status status IN ('CREATED', 'MATERIAL_ISSUED', 'IN_PROCESS', 'PRODUCTION_COMPLETE', 'RECONCILED', 'QC_QA', 'RELEASED', 'REJECTED', 'CANCELLED')`

### `material_issue` — **append-only**

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| issue_no | VARCHAR(30) | no |  |  |
| batch_id | BIGINT | no | FK → manufacturing_batch.id |  |
| batch_material_id | BIGINT | no | FK → batch_material.id |  |
| material_batch_id | BIGINT | no | FK → material_batch.id |  |
| location_id | BIGINT | no | FK → location.id |  |
| quantity | NUMERIC(18, 6) | no |  |  |
| inventory_txn_id | BIGINT | yes |  |  |
| conditional_release_id | BIGINT | yes |  |  |
| fefo_override_reason | VARCHAR(300) | yes |  |  |
| is_additional | BOOLEAN | no | default False |  |
| issued_by_id | BIGINT | yes |  |  |
| issued_at | DATETIME (UTC) | no |  |  |
| id | BIGINT | no | PK |  |

Constraints: `CheckConstraint: ck_material_issue_qty quantity > 0`; `UniqueConstraint: uq_material_issue_issue_no`

### `material_issue_indent`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| indent_no | VARCHAR(30) | no |  |  |
| batch_id | BIGINT | no | FK → manufacturing_batch.id |  |
| status | VARCHAR(15) | no | default OPEN |  |
| id | BIGINT | no | PK |  |
| created_at | DATETIME (UTC) | no |  |  |
| created_by_id | BIGINT | yes |  |  |
| updated_at | DATETIME (UTC) | yes |  |  |
| updated_by_id | BIGINT | yes |  |  |
| row_version | INTEGER | no | default 1 |  |

Constraints: `UniqueConstraint: uq_material_issue_indent_indent_no`; `UniqueConstraint: uq_material_issue_indent_batch_id`

### `material_return`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| return_no | VARCHAR(30) | no |  |  |
| issue_id | BIGINT | no | FK → material_issue.id |  |
| batch_id | BIGINT | no | FK → manufacturing_batch.id |  |
| batch_material_id | BIGINT | no | FK → batch_material.id |  |
| material_batch_id | BIGINT | no | FK → material_batch.id |  |
| issued_qty | NUMERIC(18, 6) | no |  |  |
| used_qty | NUMERIC(18, 6) | no |  |  |
| returned_qty | NUMERIC(18, 6) | no |  |  |
| damaged_qty | NUMERIC(18, 6) | no | default 0 |  |
| location_id | BIGINT | no | FK → location.id |  |
| reason | VARCHAR(300) | no |  |  |
| status | VARCHAR(10) | no | default REQUESTED |  |
| requested_by_id | BIGINT | no |  |  |
| accepted_by_id | BIGINT | yes |  |  |
| accepted_at | DATETIME (UTC) | yes |  |  |
| ledger_txn_id | BIGINT | yes |  |  |
| decision_comment | VARCHAR(300) | yes |  |  |
| id | BIGINT | no | PK |  |
| created_at | DATETIME (UTC) | no |  |  |
| created_by_id | BIGINT | yes |  |  |
| updated_at | DATETIME (UTC) | yes |  |  |
| updated_by_id | BIGINT | yes |  |  |
| row_version | INTEGER | no | default 1 |  |

Constraints: `CheckConstraint: ck_material_return_qty returned_qty > 0`; `UniqueConstraint: uq_material_return_return_no`; `CheckConstraint: ck_material_return_status status IN ('REQUESTED','ACCEPTED','REJECTED')`

### `mbr_step`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| bom_id | BIGINT | no | FK → bom_header.id |  |
| step_no | INTEGER | no |  |  |
| seq | INTEGER | no | default 1 |  |
| stage | VARCHAR(60) | yes |  |  |
| instruction | VARCHAR(1000) | no |  |  |
| requires_verification | BOOLEAN | no | default True |  |
| requires_value | BOOLEAN | no | default False |  |
| id | BIGINT | no | PK |  |
| created_at | DATETIME (UTC) | no |  |  |
| created_by_id | BIGINT | yes |  |  |
| updated_at | DATETIME (UTC) | yes |  |  |
| updated_by_id | BIGINT | yes |  |  |
| row_version | INTEGER | no | default 1 |  |

Constraints: `UniqueConstraint: uq_mbr_step_bom_id`

### `plasma_pool`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| pool_no | VARCHAR(30) | no |  |  |
| total_volume_l | NUMERIC(10, 3) | no |  |  |
| material_batch_id | BIGINT | yes | FK → material_batch.id |  |
| created_by_id | BIGINT | yes |  |  |
| id | BIGINT | no | PK |  |
| created_at | DATETIME (UTC) | no |  |  |
| updated_at | DATETIME (UTC) | yes |  |  |
| updated_by_id | BIGINT | yes |  |  |
| row_version | INTEGER | no | default 1 |  |

Constraints: `UniqueConstraint: uq_plasma_pool_pool_no`

## Module `master`

### `calibration`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| equipment_id | BIGINT | no | FK → equipment.id |  |
| performed_on | DATE | no |  |  |
| due_on | DATE | no |  |  |
| result | VARCHAR(4) | no |  |  |
| performed_by | VARCHAR(150) | yes |  |  |
| certificate_no | VARCHAR(80) | yes |  |  |
| certificate_document_id | BIGINT | yes | FK → document.id |  |
| remarks | VARCHAR(500) | yes |  |  |
| id | BIGINT | no | PK |  |
| created_at | DATETIME (UTC) | no |  |  |
| created_by_id | BIGINT | yes |  |  |
| updated_at | DATETIME (UTC) | yes |  |  |
| updated_by_id | BIGINT | yes |  |  |
| row_version | INTEGER | no | default 1 |  |

Constraints: `CheckConstraint: ck_calibration_result result IN ('PASS','FAIL')`; `CheckConstraint: ck_calibration_due_after_performed due_on > performed_on`

### `category`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| code | VARCHAR(30) | no |  |  |
| name | VARCHAR(100) | no |  |  |
| parent_id | BIGINT | yes | FK → category.id |  |
| is_active | BOOLEAN | no | default True |  |
| id | BIGINT | no | PK |  |
| created_at | DATETIME (UTC) | no |  |  |
| created_by_id | BIGINT | yes |  |  |
| updated_at | DATETIME (UTC) | yes |  |  |
| updated_by_id | BIGINT | yes |  |  |
| row_version | INTEGER | no | default 1 |  |

Constraints: `UniqueConstraint: uq_category_code`

### `customer`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| customer_code | VARCHAR(30) | no |  |  |
| name | VARCHAR(200) | no |  |  |
| address | TEXT | yes |  |  |
| state | VARCHAR(60) | yes |  |  |
| gst_no | VARCHAR(30) | yes |  |  |
| licence_no | VARCHAR(60) | yes |  |  |
| licence_expiry | DATE | yes |  |  |
| contact_person | VARCHAR(100) | yes |  |  |
| email | VARCHAR(150) | yes |  |  |
| phone | VARCHAR(40) | yes |  |  |
| is_authorised | BOOLEAN | no | default True |  |
| is_active | BOOLEAN | no | default True |  |
| min_remaining_shelf_life_days | INTEGER | yes |  |  |
| id | BIGINT | no | PK |  |
| created_at | DATETIME (UTC) | no |  |  |
| created_by_id | BIGINT | yes |  |  |
| updated_at | DATETIME (UTC) | yes |  |  |
| updated_by_id | BIGINT | yes |  |  |
| row_version | INTEGER | no | default 1 |  |

Constraints: `UniqueConstraint: uq_customer_customer_code`

### `equipment`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| equipment_code | VARCHAR(40) | no |  |  |
| name | VARCHAR(150) | no |  |  |
| equipment_type | VARCHAR(40) | no | default INSTRUMENT |  |
| manufacturer | VARCHAR(100) | yes |  |  |
| model | VARCHAR(100) | yes |  |  |
| serial_no | VARCHAR(100) | yes |  |  |
| location_id | BIGINT | yes | FK → location.id |  |
| qualification_status | VARCHAR(25) | no | default NOT_QUALIFIED |  |
| status | VARCHAR(20) | no | default ACTIVE |  |
| calibration_required | BOOLEAN | no | default True |  |
| calibration_due | DATE | yes |  |  |
| maintenance_due | DATE | yes |  |  |
| id | BIGINT | no | PK |  |
| created_at | DATETIME (UTC) | no |  |  |
| created_by_id | BIGINT | yes |  |  |
| updated_at | DATETIME (UTC) | yes |  |  |
| updated_by_id | BIGINT | yes |  |  |
| row_version | INTEGER | no | default 1 |  |

Constraints: `CheckConstraint: ck_equipment_qualification_status qualification_status IN ('NOT_QUALIFIED','QUALIFIED','REQUALIFICATION_DUE','DISQUALIFIED')`; `CheckConstraint: ck_equipment_status status IN ('ACTIVE','UNDER_MAINTENANCE','OUT_OF_SERVICE','RETIRED')`; `UniqueConstraint: uq_equipment_equipment_code`

### `location`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| warehouse_id | BIGINT | no | FK → warehouse.id |  |
| parent_id | BIGINT | yes | FK → location.id |  |
| location_code | VARCHAR(40) | no |  |  |
| name | VARCHAR(100) | no |  |  |
| location_type | VARCHAR(10) | no |  |  |
| storage_condition | VARCHAR(100) | yes |  |  |
| temp_min | NUMERIC(6, 2) | yes |  |  |
| temp_max | NUMERIC(6, 2) | yes |  |  |
| humidity_min | NUMERIC(5, 2) | yes |  |  |
| humidity_max | NUMERIC(5, 2) | yes |  |  |
| capacity | NUMERIC(18, 6) | yes |  |  |
| capacity_unit_id | BIGINT | yes | FK → unit.id |  |
| current_occupancy | NUMERIC(18, 6) | no | default 0 |  |
| is_quarantine | BOOLEAN | no | default False |  |
| is_rejected_area | BOOLEAN | no | default False |  |
| status | VARCHAR(10) | no | default ACTIVE |  |
| id | BIGINT | no | PK |  |
| created_at | DATETIME (UTC) | no |  |  |
| created_by_id | BIGINT | yes |  |  |
| updated_at | DATETIME (UTC) | yes |  |  |
| updated_by_id | BIGINT | yes |  |  |
| row_version | INTEGER | no | default 1 |  |

Constraints: `UniqueConstraint: uq_location_location_code`; `CheckConstraint: ck_location_location_type location_type IN ('ZONE','ROOM','RACK','SHELF','BIN')`; `CheckConstraint: ck_location_capacity capacity IS NULL OR capacity >= 0`; `CheckConstraint: ck_location_temp_range temp_max IS NULL OR temp_min IS NULL OR temp_max >= temp_min`

### `location_category`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| location_id | BIGINT | no | FK → location.id |  |
| category_id | BIGINT | no | FK → category.id |  |
| revoked_at | DATETIME (UTC) | yes |  |  |
| id | BIGINT | no | PK |  |
| created_at | DATETIME (UTC) | no |  |  |
| created_by_id | BIGINT | yes |  |  |
| updated_at | DATETIME (UTC) | yes |  |  |
| updated_by_id | BIGINT | yes |  |  |
| row_version | INTEGER | no | default 1 |  |

Constraints: `UniqueConstraint: uq_location_category_location_id`

### `location_compat_rule`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| category_a_id | BIGINT | no | FK → category.id |  |
| category_b_id | BIGINT | no | FK → category.id |  |
| allowed | BOOLEAN | no | default False |  |
| id | BIGINT | no | PK |  |
| created_at | DATETIME (UTC) | no |  |  |
| created_by_id | BIGINT | yes |  |  |
| updated_at | DATETIME (UTC) | yes |  |  |
| updated_by_id | BIGINT | yes |  |  |
| row_version | INTEGER | no | default 1 |  |

Constraints: `UniqueConstraint: uq_location_compat_rule_category_a_id`

### `material`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| material_code | VARCHAR(30) | no |  |  |
| name | VARCHAR(200) | no |  |  |
| generic_name | VARCHAR(200) | yes |  |  |
| type_id | BIGINT | no | FK → material_type.id |  |
| category_id | BIGINT | yes | FK → category.id |  |
| subcategory | VARCHAR(100) | yes |  |  |
| grade | VARCHAR(50) | yes |  |  |
| pharmacopoeial_standard | VARCHAR(100) | yes |  |  |
| manufacturer | VARCHAR(200) | yes |  |  |
| base_unit_id | BIGINT | no | FK → unit.id |  |
| pack_size | VARCHAR(60) | yes |  |  |
| storage_condition | VARCHAR(200) | yes |  |  |
| temp_min | NUMERIC(6, 2) | yes |  |  |
| temp_max | NUMERIC(6, 2) | yes |  |  |
| humidity_min | NUMERIC(5, 2) | yes |  |  |
| humidity_max | NUMERIC(5, 2) | yes |  |  |
| shelf_life_days | INTEGER | yes |  |  |
| retest_days | INTEGER | yes |  |  |
| requires_qc | BOOLEAN | no | default True |  |
| requires_qa_release | BOOLEAN | no | default True |  |
| gmp_criticality | VARCHAR(20) | no | default MAJOR |  |
| hazard_class | VARCHAR(60) | yes |  |  |
| fefo_mode | VARCHAR(4) | no | default FEFO |  |
| min_stock | NUMERIC(18, 6) | yes |  |  |
| max_stock | NUMERIC(18, 6) | yes |  |  |
| barcode | VARCHAR(60) | yes |  |  |
| master_status | VARCHAR(20) | no | default DRAFT |  |
| id | BIGINT | no | PK |  |
| created_at | DATETIME (UTC) | no |  |  |
| created_by_id | BIGINT | yes |  |  |
| updated_at | DATETIME (UTC) | yes |  |  |
| updated_by_id | BIGINT | yes |  |  |
| row_version | INTEGER | no | default 1 |  |

Constraints: `CheckConstraint: ck_material_temp_range temp_max IS NULL OR temp_min IS NULL OR temp_max >= temp_min`; `CheckConstraint: ck_material_shelf_life shelf_life_days IS NULL OR shelf_life_days > 0`; `CheckConstraint: ck_material_fefo_mode fefo_mode IN ('FEFO','FIFO')`; `UniqueConstraint: uq_material_material_code`; `CheckConstraint: ck_material_master_status master_status IN ('DRAFT','APPROVED','ACTIVE','OBSOLETE')`

### `material_type`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| code | VARCHAR(20) | no |  |  |
| name | VARCHAR(80) | no |  |  |
| is_stock_item | BOOLEAN | no | default True |  |
| is_active | BOOLEAN | no | default True |  |
| id | BIGINT | no | PK |  |
| created_at | DATETIME (UTC) | no |  |  |
| created_by_id | BIGINT | yes |  |  |
| updated_at | DATETIME (UTC) | yes |  |  |
| updated_by_id | BIGINT | yes |  |  |
| row_version | INTEGER | no | default 1 |  |

Constraints: `UniqueConstraint: uq_material_type_code`

### `unit`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| code | VARCHAR(20) | no |  |  |
| name | VARCHAR(80) | no |  |  |
| dimension | VARCHAR(20) | no | default COUNT |  |
| is_active | BOOLEAN | no | default True |  |
| id | BIGINT | no | PK |  |
| created_at | DATETIME (UTC) | no |  |  |
| created_by_id | BIGINT | yes |  |  |
| updated_at | DATETIME (UTC) | yes |  |  |
| updated_by_id | BIGINT | yes |  |  |
| row_version | INTEGER | no | default 1 |  |

Constraints: `UniqueConstraint: uq_unit_code`

### `unit_conversion`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| from_unit_id | BIGINT | no | FK → unit.id |  |
| to_unit_id | BIGINT | no | FK → unit.id |  |
| factor | NUMERIC(24, 10) | no |  |  |
| id | BIGINT | no | PK |  |
| created_at | DATETIME (UTC) | no |  |  |
| created_by_id | BIGINT | yes |  |  |
| updated_at | DATETIME (UTC) | yes |  |  |
| updated_by_id | BIGINT | yes |  |  |
| row_version | INTEGER | no | default 1 |  |

Constraints: `UniqueConstraint: uq_unit_conversion_from_unit_id`; `CheckConstraint: ck_unit_conversion_factor_positive factor > 0`

### `vendor`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| vendor_code | VARCHAR(30) | no |  |  |
| name | VARCHAR(200) | no |  |  |
| vendor_type | VARCHAR(40) | no | default MANUFACTURER |  |
| address | TEXT | yes |  |  |
| country | VARCHAR(60) | yes |  |  |
| state | VARCHAR(60) | yes |  |  |
| city | VARCHAR(60) | yes |  |  |
| gst_no | VARCHAR(30) | yes |  |  |
| pan_no | VARCHAR(15) | yes |  |  |
| contact_person | VARCHAR(100) | yes |  |  |
| email | VARCHAR(150) | yes |  |  |
| phone | VARCHAR(40) | yes |  |  |
| bank_name | VARCHAR(100) | yes |  |  |
| bank_account_no | VARCHAR(40) | yes |  |  |
| bank_ifsc | VARCHAR(20) | yes |  |  |
| material_categories | VARCHAR(300) | yes |  |  |
| risk_class | VARCHAR(10) | no | default MEDIUM |  |
| criticality | VARCHAR(20) | yes |  |  |
| quality_agreement_status | VARCHAR(20) | no | default NONE |  |
| vendor_audit_status | VARCHAR(20) | no | default NOT_AUDITED |  |
| approval_status | VARCHAR(20) | no | default DRAFT |  |
| id | BIGINT | no | PK |  |
| created_at | DATETIME (UTC) | no |  |  |
| created_by_id | BIGINT | yes |  |  |
| updated_at | DATETIME (UTC) | yes |  |  |
| updated_by_id | BIGINT | yes |  |  |
| row_version | INTEGER | no | default 1 |  |

Constraints: `CheckConstraint: ck_vendor_approval_status approval_status IN ('DRAFT','APPROVED','INACTIVE')`; `CheckConstraint: ck_vendor_risk_class risk_class IN ('CRITICAL','HIGH','MEDIUM','LOW')`; `UniqueConstraint: uq_vendor_vendor_code`

### `vendor_document`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| vendor_id | BIGINT | no | FK → vendor.id |  |
| document_id | BIGINT | no | FK → document.id |  |
| doc_type | VARCHAR(40) | no |  |  |
| doc_no | VARCHAR(60) | yes |  |  |
| version | VARCHAR(20) | no | default 1 |  |
| issue_date | DATE | yes |  |  |
| expiry_date | DATE | yes |  |  |
| review_status | VARCHAR(20) | no | default PENDING |  |
| reviewed_by_id | BIGINT | yes |  |  |
| reviewed_at | DATETIME (UTC) | yes |  |  |
| review_comment | VARCHAR(500) | yes |  |  |
| is_current | BOOLEAN | no | default True |  |
| id | BIGINT | no | PK |  |
| created_at | DATETIME (UTC) | no |  |  |
| created_by_id | BIGINT | yes |  |  |
| updated_at | DATETIME (UTC) | yes |  |  |
| updated_by_id | BIGINT | yes |  |  |
| row_version | INTEGER | no | default 1 |  |

Constraints: `CheckConstraint: ck_vendor_document_review_status review_status IN ('PENDING','APPROVED','REJECTED')`

### `warehouse`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| plant_id | BIGINT | no | FK → plant.id |  |
| warehouse_code | VARCHAR(20) | no |  |  |
| name | VARCHAR(100) | no |  |  |
| storage_condition | VARCHAR(100) | yes |  |  |
| is_active | BOOLEAN | no | default True |  |
| id | BIGINT | no | PK |  |
| created_at | DATETIME (UTC) | no |  |  |
| created_by_id | BIGINT | yes |  |  |
| updated_at | DATETIME (UTC) | yes |  |  |
| updated_by_id | BIGINT | yes |  |  |
| row_version | INTEGER | no | default 1 |  |

Constraints: `UniqueConstraint: uq_warehouse_warehouse_code`

## Module `org`

### `company`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| name | VARCHAR(200) | no |  |  |
| app_display_name | VARCHAR(100) | no | default GMP Material & Manufacturing ERP |  |
| address | TEXT | yes |  |  |
| gst_no | VARCHAR(30) | yes |  |  |
| manufacturing_licence_no | VARCHAR(60) | yes |  |  |
| drug_licence_no | VARCHAR(60) | yes |  |  |
| contact_person | VARCHAR(100) | yes |  |  |
| email | VARCHAR(150) | yes |  |  |
| phone | VARCHAR(40) | yes |  |  |
| website | VARCHAR(150) | yes |  |  |
| logo_document_id | BIGINT | yes | FK → document.id |  |
| document_header | TEXT | yes |  |  |
| document_footer | TEXT | yes |  |  |
| report_format | VARCHAR(50) | yes |  |  |
| label_format | VARCHAR(50) | yes |  |  |
| date_format | VARCHAR(30) | no | default DD-MMM-YYYY |  |
| time_format | VARCHAR(30) | no | default HH:mm |  |
| id | BIGINT | no | PK |  |
| created_at | DATETIME (UTC) | no |  |  |
| created_by_id | BIGINT | yes |  |  |
| updated_at | DATETIME (UTC) | yes |  |  |
| updated_by_id | BIGINT | yes |  |  |
| row_version | INTEGER | no | default 1 |  |

### `department`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| plant_id | BIGINT | no | FK → plant.id |  |
| code | VARCHAR(20) | no |  |  |
| name | VARCHAR(100) | no |  |  |
| is_active | BOOLEAN | no | default True |  |
| id | BIGINT | no | PK |  |
| created_at | DATETIME (UTC) | no |  |  |
| created_by_id | BIGINT | yes |  |  |
| updated_at | DATETIME (UTC) | yes |  |  |
| updated_by_id | BIGINT | yes |  |  |
| row_version | INTEGER | no | default 1 |  |

Constraints: `UniqueConstraint: uq_department_plant_id`

### `plant`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| company_id | BIGINT | no | FK → company.id |  |
| plant_code | VARCHAR(20) | no |  |  |
| name | VARCHAR(150) | no |  |  |
| site_name | VARCHAR(150) | yes |  |  |
| timezone | VARCHAR(60) | no | default Asia/Kolkata |  |
| is_active | BOOLEAN | no | default True |  |
| id | BIGINT | no | PK |  |
| created_at | DATETIME (UTC) | no |  |  |
| created_by_id | BIGINT | yes |  |  |
| updated_at | DATETIME (UTC) | yes |  |  |
| updated_by_id | BIGINT | yes |  |  |
| row_version | INTEGER | no | default 1 |  |

Constraints: `UniqueConstraint: uq_plant_plant_code`

## Module `platform`

### `doc_link`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| id | BIGINT | no | PK |  |
| document_id | BIGINT | no | FK → document.id |  |
| entity | VARCHAR(80) | no |  |  |
| record_id | VARCHAR(60) | no |  |  |
| linked_by_id | BIGINT | yes |  |  |
| linked_at | DATETIME (UTC) | no |  |  |

Constraints: `UniqueConstraint: uq_doc_link_document_id`

### `document`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| id | BIGINT | no | PK |  |
| doc_no | VARCHAR(60) | yes |  |  |
| version | VARCHAR(20) | no | default 1 |  |
| effective_date | DATE | yes |  |  |
| expiry_date | DATE | yes |  |  |
| original_name | VARCHAR(260) | no |  |  |
| mime_type | VARCHAR(100) | no |  |  |
| size_bytes | BIGINT | no |  |  |
| sha256 | VARCHAR(64) | no |  |  |
| storage_key | VARCHAR(200) | no |  |  |
| status | VARCHAR(20) | no | default ACTIVE |  |
| supersedes_id | BIGINT | yes | FK → document.id |  |
| uploaded_by_id | BIGINT | yes |  |  |
| uploaded_at | DATETIME (UTC) | no |  |  |

### `notification`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| id | BIGINT | no | PK |  |
| user_id | BIGINT | no | FK → users.id |  |
| category | VARCHAR(40) | no |  |  |
| title | VARCHAR(200) | no |  |  |
| body | TEXT | yes |  |  |
| ref_entity | VARCHAR(80) | yes |  |  |
| ref_id | VARCHAR(60) | yes |  |  |
| created_at | DATETIME (UTC) | no |  |  |
| read_at | DATETIME (UTC) | yes |  |  |
| emailed_at | DATETIME (UTC) | yes |  |  |

### `number_registry`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| plant_id | BIGINT | no | FK → plant.id |  |
| doc_type | VARCHAR(30) | no |  |  |
| prefix | VARCHAR(20) | no |  |  |
| format | VARCHAR(100) | no | default {prefix}-{year}-{seq:06d} |  |
| reset_policy | VARCHAR(10) | no | default YEARLY |  |
| id | BIGINT | no | PK |  |
| created_at | DATETIME (UTC) | no |  |  |
| created_by_id | BIGINT | yes |  |  |
| updated_at | DATETIME (UTC) | yes |  |  |
| updated_by_id | BIGINT | yes |  |  |
| row_version | INTEGER | no | default 1 |  |

Constraints: `UniqueConstraint: uq_number_registry_plant_id`; `CheckConstraint: ck_number_registry_reset_policy reset_policy IN ('YEARLY','NEVER')`

### `number_sequence`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| id | BIGINT | no | PK |  |
| plant_id | BIGINT | no | FK → plant.id |  |
| doc_type | VARCHAR(30) | no |  |  |
| period_key | VARCHAR(10) | no |  |  |
| current_value | BIGINT | no | default 0 |  |

Constraints: `UniqueConstraint: uq_number_sequence_plant_id`

### `system_configuration`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| config_key | VARCHAR(100) | no |  |  |
| value | TEXT | no |  |  |
| description | VARCHAR(300) | yes |  |  |
| id | BIGINT | no | PK |  |
| created_at | DATETIME (UTC) | no |  |  |
| created_by_id | BIGINT | yes |  |  |
| updated_at | DATETIME (UTC) | yes |  |  |
| updated_by_id | BIGINT | yes |  |  |
| row_version | INTEGER | no | default 1 |  |

Constraints: `UniqueConstraint: uq_system_configuration_config_key`

### `workflow_definition`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| process_code | VARCHAR(60) | no |  |  |
| version_no | INTEGER | no |  |  |
| name | VARCHAR(150) | no |  |  |
| status | VARCHAR(20) | no | default DRAFT |  |
| effective_from | DATETIME (UTC) | yes |  |  |
| approved_signature_id | BIGINT | yes | FK → e_signature.id |  |
| id | BIGINT | no | PK |  |
| created_at | DATETIME (UTC) | no |  |  |
| created_by_id | BIGINT | yes |  |  |
| updated_at | DATETIME (UTC) | yes |  |  |
| updated_by_id | BIGINT | yes |  |  |
| row_version | INTEGER | no | default 1 |  |

Constraints: `CheckConstraint: ck_workflow_definition_status status IN ('DRAFT','APPROVED','SUPERSEDED')`; `UniqueConstraint: uq_workflow_definition_process_code`

### `workflow_instance`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| id | BIGINT | no | PK |  |
| definition_id | BIGINT | no | FK → workflow_definition.id |  |
| process_code | VARCHAR(60) | no |  |  |
| entity | VARCHAR(80) | no |  |  |
| record_id | VARCHAR(60) | no |  |  |
| status | VARCHAR(20) | no | default IN_PROGRESS |  |
| current_seq | INTEGER | no |  |  |
| initiated_by_id | BIGINT | no | FK → users.id |  |
| started_at | DATETIME (UTC) | no |  |  |
| step_started_at | DATETIME (UTC) | no |  |  |
| completed_at | DATETIME (UTC) | yes |  |  |

Constraints: `CheckConstraint: ck_workflow_instance_status status IN ('IN_PROGRESS','APPROVED','REJECTED','CANCELLED')`

### `workflow_step`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| id | BIGINT | no | PK |  |
| definition_id | BIGINT | no | FK → workflow_definition.id |  |
| seq | INTEGER | no |  |  |
| name | VARCHAR(100) | no |  |  |
| role_id | BIGINT | no | FK → role.id |  |
| min_approvals | INTEGER | no | default 1 |  |
| esig_required | BOOLEAN | no | default True |  |
| meaning | VARCHAR(40) | no | default APPROVED_BY |  |
| sla_hours | INTEGER | yes |  |  |
| escalate_role_id | BIGINT | yes | FK → role.id |  |
| reject_to_seq | INTEGER | yes |  |  |

Constraints: `CheckConstraint: ck_workflow_step_min_approvals min_approvals >= 1`; `UniqueConstraint: uq_workflow_step_definition_id`

### `workflow_transaction` — **append-only**

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| instance_id | BIGINT | no | FK → workflow_instance.id |  |
| seq | INTEGER | no |  |  |
| actor_id | BIGINT | no | FK → users.id |  |
| decision | VARCHAR(20) | no |  |  |
| signature_id | BIGINT | yes | FK → e_signature.id |  |
| comment | VARCHAR(1000) | yes |  |  |
| occurred_at | DATETIME (UTC) | no |  |  |
| id | BIGINT | no | PK |  |

## Module `purchase`

### `purchase_order`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| po_no | VARCHAR(30) | no |  |  |
| po_date | DATE | no |  |  |
| vendor_id | BIGINT | no | FK → vendor.id |  |
| vendor_qualification_id | BIGINT | yes | FK → vendor_qualification.id |  |
| pr_id | BIGINT | yes | FK → purchase_request.id |  |
| currency | VARCHAR(3) | no | default INR |  |
| payment_terms | VARCHAR(200) | yes |  |  |
| delivery_date | DATE | yes |  |  |
| purchase_conditions | TEXT | yes |  |  |
| quality_requirements | TEXT | yes |  |  |
| status | VARCHAR(25) | no | default DRAFT |  |
| workflow_instance_id | BIGINT | yes | FK → workflow_instance.id |  |
| validation_snapshot | TEXT | yes |  |  |
| cancel_reason | VARCHAR(500) | yes |  |  |
| id | BIGINT | no | PK |  |
| created_at | DATETIME (UTC) | no |  |  |
| created_by_id | BIGINT | yes |  |  |
| updated_at | DATETIME (UTC) | yes |  |  |
| updated_by_id | BIGINT | yes |  |  |
| row_version | INTEGER | no | default 1 |  |

Constraints: `UniqueConstraint: uq_purchase_order_po_no`; `CheckConstraint: ck_purchase_order_status status IN ('DRAFT','PENDING_APPROVAL','APPROVED','PARTIALLY_RECEIVED','CLOSED','CANCELLED','REJECTED')`

### `purchase_order_line`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| po_id | BIGINT | no | FK → purchase_order.id |  |
| line_no | INTEGER | no |  |  |
| material_id | BIGINT | no | FK → material.id |  |
| specification_id | BIGINT | no | FK → specification.id |  |
| vendor_material_id | BIGINT | no | FK → vendor_material.id |  |
| pr_line_id | BIGINT | yes |  |  |
| quantity | NUMERIC(18, 6) | no |  |  |
| unit_id | BIGINT | no | FK → unit.id |  |
| rate | NUMERIC(18, 4) | no |  |  |
| tax_pct | NUMERIC(5, 2) | no | default 0 |  |
| delivery_date | DATE | yes |  |  |
| received_quantity | NUMERIC(18, 6) | no | default 0 |  |
| remarks | VARCHAR(300) | yes |  |  |
| id | BIGINT | no | PK |  |
| created_at | DATETIME (UTC) | no |  |  |
| created_by_id | BIGINT | yes |  |  |
| updated_at | DATETIME (UTC) | yes |  |  |
| updated_by_id | BIGINT | yes |  |  |
| row_version | INTEGER | no | default 1 |  |

Constraints: `CheckConstraint: ck_purchase_order_line_quantity quantity > 0`; `CheckConstraint: ck_purchase_order_line_rate rate >= 0`; `UniqueConstraint: uq_purchase_order_line_po_id`; `CheckConstraint: ck_purchase_order_line_tax tax_pct >= 0 AND tax_pct <= 100`

### `purchase_request`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| pr_no | VARCHAR(30) | no |  |  |
| request_date | DATE | no |  |  |
| department_id | BIGINT | no | FK → department.id |  |
| requested_by_id | BIGINT | no | FK → users.id |  |
| purpose | VARCHAR(500) | yes |  |  |
| priority | VARCHAR(10) | no | default NORMAL |  |
| remarks | VARCHAR(500) | yes |  |  |
| status | VARCHAR(25) | no | default DRAFT |  |
| workflow_instance_id | BIGINT | yes | FK → workflow_instance.id |  |
| id | BIGINT | no | PK |  |
| created_at | DATETIME (UTC) | no |  |  |
| created_by_id | BIGINT | yes |  |  |
| updated_at | DATETIME (UTC) | yes |  |  |
| updated_by_id | BIGINT | yes |  |  |
| row_version | INTEGER | no | default 1 |  |

Constraints: `UniqueConstraint: uq_purchase_request_pr_no`; `CheckConstraint: ck_purchase_request_priority priority IN ('LOW','NORMAL','HIGH','URGENT')`; `CheckConstraint: ck_purchase_request_status status IN ('DRAFT','SUBMITTED','DEPARTMENT_APPROVED','APPROVED','CONVERTED','REJECTED','CANCELLED')`

### `purchase_request_line`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| pr_id | BIGINT | no | FK → purchase_request.id |  |
| line_no | INTEGER | no |  |  |
| material_id | BIGINT | no | FK → material.id |  |
| quantity | NUMERIC(18, 6) | no |  |  |
| unit_id | BIGINT | no | FK → unit.id |  |
| required_date | DATE | yes |  |  |
| preferred_vendor_id | BIGINT | yes | FK → vendor.id |  |
| remarks | VARCHAR(300) | yes |  |  |
| po_line_id | BIGINT | yes |  |  |
| id | BIGINT | no | PK |  |
| created_at | DATETIME (UTC) | no |  |  |
| created_by_id | BIGINT | yes |  |  |
| updated_at | DATETIME (UTC) | yes |  |  |
| updated_by_id | BIGINT | yes |  |  |
| row_version | INTEGER | no | default 1 |  |

Constraints: `UniqueConstraint: uq_purchase_request_line_pr_id`; `CheckConstraint: ck_purchase_request_line_quantity quantity > 0`

### `vendor_material`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| vendor_id | BIGINT | no | FK → vendor.id |  |
| material_id | BIGINT | no | FK → material.id |  |
| version_no | INTEGER | no | default 1 |  |
| status | VARCHAR(20) | no | default DRAFT |  |
| is_primary | BOOLEAN | no | default False |  |
| manufacturer_site | VARCHAR(200) | yes |  |  |
| change_control_ref | VARCHAR(60) | yes |  |  |
| supersedes_id | BIGINT | yes | FK → vendor_material.id |  |
| effective_from | DATETIME (UTC) | yes |  |  |
| effective_to | DATETIME (UTC) | yes |  |  |
| approved_to | DATE | yes |  |  |
| status_reason | VARCHAR(1000) | yes |  |  |
| change_reason | VARCHAR(1000) | yes |  |  |
| approved_signature_id | BIGINT | yes | FK → e_signature.id |  |
| id | BIGINT | no | PK |  |
| created_at | DATETIME (UTC) | no |  |  |
| created_by_id | BIGINT | yes |  |  |
| updated_at | DATETIME (UTC) | yes |  |  |
| updated_by_id | BIGINT | yes |  |  |
| row_version | INTEGER | no | default 1 |  |

Constraints: `CheckConstraint: ck_vendor_material_status status IN ('DRAFT','UNDER_REVIEW','APPROVED','SUPERSEDED','WITHDRAWN')`; `UniqueConstraint: uq_vendor_material_vendor_id`

### `vendor_qualification`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| vendor_id | BIGINT | no | FK → vendor.id |  |
| qualification_no | VARCHAR(40) | no |  |  |
| version_no | INTEGER | no | default 1 |  |
| status | VARCHAR(20) | no | default DRAFT |  |
| risk_class | VARCHAR(10) | no |  |  |
| qualified_on | DATE | yes |  |  |
| requalification_due_date | DATE | yes |  |  |
| basis | TEXT | yes |  |  |
| audit_report_ref | VARCHAR(100) | yes |  |  |
| supersedes_id | BIGINT | yes | FK → vendor_qualification.id |  |
| effective_from | DATETIME (UTC) | yes |  |  |
| effective_to | DATETIME (UTC) | yes |  |  |
| status_reason | VARCHAR(1000) | yes |  |  |
| change_reason | VARCHAR(1000) | yes |  |  |
| approved_signature_id | BIGINT | yes | FK → e_signature.id |  |
| id | BIGINT | no | PK |  |
| created_at | DATETIME (UTC) | no |  |  |
| created_by_id | BIGINT | yes |  |  |
| updated_at | DATETIME (UTC) | yes |  |  |
| updated_by_id | BIGINT | yes |  |  |
| row_version | INTEGER | no | default 1 |  |

Constraints: `CheckConstraint: ck_vendor_qualification_status status IN ('DRAFT', 'UNDER_REVIEW', 'APPROVED', 'CONDITIONAL', 'SUSPENDED', 'EXPIRED', 'DISQUALIFIED', 'SUPERSEDED')`; `UniqueConstraint: uq_vendor_qualification_vendor_id`; `CheckConstraint: ck_vendor_qualification_risk_class risk_class IN ('CRITICAL','HIGH','MEDIUM','LOW')`

## Module `qc`

### `coa` — **append-only**

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| coa_no | VARCHAR(30) | no |  |  |
| version_no | INTEGER | no | default 1 |  |
| material_batch_id | BIGINT | yes | FK → material_batch.id |  |
| mfg_batch_id | BIGINT | yes |  |  |
| pdf_document_id | BIGINT | no | FK → document.id |  |
| xlsx_document_id | BIGINT | no | FK → document.id |  |
| conclusion | VARCHAR(20) | no |  |  |
| reason | VARCHAR(300) | yes |  |  |
| generated_by_id | BIGINT | yes |  |  |
| signature_id | BIGINT | yes |  |  |
| generated_at | DATETIME (UTC) | no |  |  |
| id | BIGINT | no | PK |  |

Constraints: `UniqueConstraint: uq_coa_coa_no`

### `conditional_release`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| cr_no | VARCHAR(30) | no |  |  |
| material_batch_id | BIGINT | no | FK → material_batch.id |  |
| quantity_authorised | NUMERIC(18, 6) | no |  |  |
| quantity_used | NUMERIC(18, 6) | no | default 0 |  |
| intended_batch_ref | VARCHAR(60) | no |  |  |
| mfg_batch_id | BIGINT | yes |  |  |
| justification | VARCHAR(1000) | no |  |  |
| risk_assessment_ref | VARCHAR(60) | no |  |  |
| identity_confirmed | BOOLEAN | no | default False |  |
| expires_at | DATE | no |  |  |
| status | VARCHAR(10) | no | default REQUESTED |  |
| requested_by_id | BIGINT | no |  |  |
| approved_by_id | BIGINT | yes |  |  |
| approved_signature_id | BIGINT | yes | FK → e_signature.id |  |
| decided_at | DATETIME (UTC) | yes |  |  |
| decision_comment | VARCHAR(500) | yes |  |  |
| id | BIGINT | no | PK |  |
| created_at | DATETIME (UTC) | no |  |  |
| created_by_id | BIGINT | yes |  |  |
| updated_at | DATETIME (UTC) | yes |  |  |
| updated_by_id | BIGINT | yes |  |  |
| row_version | INTEGER | no | default 1 |  |

Constraints: `CheckConstraint: ck_conditional_release_qty quantity_authorised > 0`; `CheckConstraint: ck_conditional_release_status status IN ('REQUESTED','APPROVED','REJECTED','CLOSED','EXPIRED')`; `UniqueConstraint: uq_conditional_release_cr_no`

### `oos_investigation`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| oos_no | VARCHAR(30) | no |  |  |
| qc_result_id | BIGINT | no | FK → qc_result.id |  |
| qc_test_id | BIGINT | no | FK → qc_test.id |  |
| sample_id | BIGINT | no | FK → sample.id |  |
| material_batch_id | BIGINT | yes | FK → material_batch.id |  |
| description | VARCHAR(500) | no |  |  |
| status | VARCHAR(10) | no | default RAISED |  |
| phase1_findings | TEXT | yes |  |  |
| phase2_findings | TEXT | yes |  |  |
| root_cause | TEXT | yes |  |  |
| capa_ref | VARCHAR(60) | yes |  |  |
| decision | VARCHAR(20) | yes |  |  |
| decision_reason | VARCHAR(500) | yes |  |  |
| decided_by_id | BIGINT | yes |  |  |
| decision_signature_id | BIGINT | yes | FK → e_signature.id |  |
| hold_id | BIGINT | yes |  |  |
| raised_at | DATETIME (UTC) | no |  |  |
| closed_at | DATETIME (UTC) | yes |  |  |
| id | BIGINT | no | PK |  |
| created_at | DATETIME (UTC) | no |  |  |
| created_by_id | BIGINT | yes |  |  |
| updated_at | DATETIME (UTC) | yes |  |  |
| updated_by_id | BIGINT | yes |  |  |
| row_version | INTEGER | no | default 1 |  |

Constraints: `UniqueConstraint: uq_oos_investigation_oos_no`; `CheckConstraint: ck_oos_investigation_status status IN ('RAISED','PHASE1','PHASE2','DECIDED','CLOSED')`

### `oot_event`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| oot_no | VARCHAR(30) | no |  |  |
| qc_result_id | BIGINT | no | FK → qc_result.id |  |
| material_id | BIGINT | no | FK → material.id |  |
| test_name | VARCHAR(150) | no |  |  |
| rule | VARCHAR(30) | no |  |  |
| detail | VARCHAR(500) | yes |  |  |
| status | VARCHAR(10) | no | default OPEN |  |
| reviewed_by_id | BIGINT | yes |  |  |
| review_comment | VARCHAR(500) | yes |  |  |
| id | BIGINT | no | PK |  |
| created_at | DATETIME (UTC) | no |  |  |
| created_by_id | BIGINT | yes |  |  |
| updated_at | DATETIME (UTC) | yes |  |  |
| updated_by_id | BIGINT | yes |  |  |
| row_version | INTEGER | no | default 1 |  |

Constraints: `UniqueConstraint: uq_oot_event_oot_no`

### `qc_result`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| test_id | BIGINT | no | FK → qc_test.id |  |
| spec_type | VARCHAR(10) | no |  |  |
| value_numeric | NUMERIC(18, 6) | yes |  |  |
| rounded_value | NUMERIC(18, 6) | yes |  |  |
| value_text | VARCHAR(300) | yes |  |  |
| unit | VARCHAR(20) | yes |  |  |
| lsl | NUMERIC(18, 6) | yes |  |  |
| usl | NUMERIC(18, 6) | yes |  |  |
| target | NUMERIC(18, 6) | yes |  |  |
| decimal_places | INTEGER | yes |  |  |
| acceptance_criteria | VARCHAR(300) | yes |  |  |
| pass_fail | VARCHAR(4) | no |  |  |
| remarks | VARCHAR(500) | yes |  |  |
| status | VARCHAR(10) | no | default DRAFT |  |
| entered_by_id | BIGINT | no |  |  |
| entered_at | DATETIME (UTC) | no |  |  |
| id | BIGINT | no | PK |  |
| created_at | DATETIME (UTC) | no |  |  |
| created_by_id | BIGINT | yes |  |  |
| updated_at | DATETIME (UTC) | yes |  |  |
| updated_by_id | BIGINT | yes |  |  |
| row_version | INTEGER | no | default 1 |  |

Constraints: `CheckConstraint: ck_qc_result_status status IN ('DRAFT','SUBMITTED')`; `CheckConstraint: ck_qc_result_pass_fail pass_fail IN ('PASS','FAIL','NA')`; `UniqueConstraint: uq_qc_result_test_id`

### `qc_result_amendment`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| result_id | BIGINT | no | FK → qc_result.id |  |
| original_value | VARCHAR(300) | yes |  |  |
| new_value | VARCHAR(300) | no |  |  |
| new_pass_fail | VARCHAR(4) | no |  |  |
| reason | VARCHAR(500) | no |  |  |
| status | VARCHAR(10) | no | default REQUESTED |  |
| requested_by_id | BIGINT | no |  |  |
| approved_by_id | BIGINT | yes |  |  |
| approved_signature_id | BIGINT | yes | FK → e_signature.id |  |
| decided_at | DATETIME (UTC) | yes |  |  |
| decision_comment | VARCHAR(500) | yes |  |  |
| id | BIGINT | no | PK |  |
| created_at | DATETIME (UTC) | no |  |  |
| created_by_id | BIGINT | yes |  |  |
| updated_at | DATETIME (UTC) | yes |  |  |
| updated_by_id | BIGINT | yes |  |  |
| row_version | INTEGER | no | default 1 |  |

Constraints: `CheckConstraint: ck_qc_result_amendment_status status IN ('REQUESTED','APPROVED','REJECTED')`

### `qc_test`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| sample_id | BIGINT | no | FK → sample.id |  |
| spec_parameter_id | BIGINT | yes | FK → specification_parameter.id |  |
| test_name | VARCHAR(150) | no |  |  |
| stp_id | BIGINT | yes | FK → stp.id |  |
| analyst_id | BIGINT | yes |  |  |
| equipment_id | BIGINT | yes | FK → equipment.id |  |
| calibration_status | VARCHAR(20) | yes |  |  |
| calibration_override_signature_id | BIGINT | yes | FK → e_signature.id |  |
| status | VARCHAR(12) | no | default ASSIGNED |  |
| retest_of_id | BIGINT | yes |  |  |
| started_at | DATETIME (UTC) | yes |  |  |
| completed_at | DATETIME (UTC) | yes |  |  |
| id | BIGINT | no | PK |  |
| created_at | DATETIME (UTC) | no |  |  |
| created_by_id | BIGINT | yes |  |  |
| updated_at | DATETIME (UTC) | yes |  |  |
| updated_by_id | BIGINT | yes |  |  |
| row_version | INTEGER | no | default 1 |  |

Constraints: `CheckConstraint: ck_qc_test_status status IN ('ASSIGNED','STARTED','SUBMITTED','INVALIDATED')`

### `sample`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| sample_no | VARCHAR(30) | no |  |  |
| sample_type | VARCHAR(15) | no | default RM_SAMPLE |  |
| material_batch_id | BIGINT | yes | FK → material_batch.id |  |
| mfg_batch_id | BIGINT | yes |  |  |
| specification_id | BIGINT | yes | FK → specification.id |  |
| sampling_plan_id | BIGINT | yes | FK → sampling_plan.id |  |
| quantity_received | NUMERIC(18, 6) | yes |  |  |
| quantity_sampled | NUMERIC(18, 6) | no |  |  |
| unit_id | BIGINT | no | FK → unit.id |  |
| containers_sampled | INTEGER | no | default 1 |  |
| sampling_location_id | BIGINT | yes | FK → location.id |  |
| sampled_by_id | BIGINT | no |  |  |
| sampled_at | DATETIME (UTC) | no |  |  |
| stage | VARCHAR(60) | yes |  |  |
| remarks | VARCHAR(500) | yes |  |  |
| status | VARCHAR(12) | no | default CREATED |  |
| retention_until | DATE | yes |  |  |
| disposal_approved_by_id | BIGINT | yes |  |  |
| disposal_signature_id | BIGINT | yes |  |  |
| disposed_at | DATETIME (UTC) | yes |  |  |
| id | BIGINT | no | PK |  |
| created_at | DATETIME (UTC) | no |  |  |
| created_by_id | BIGINT | yes |  |  |
| updated_at | DATETIME (UTC) | yes |  |  |
| updated_by_id | BIGINT | yes |  |  |
| row_version | INTEGER | no | default 1 |  |

Constraints: `CheckConstraint: ck_sample_sample_type sample_type IN ('RM_SAMPLE', 'PM_SAMPLE', 'IN_PROCESS', 'SFG', 'FG', 'STABILITY', 'RETENTION', 'VENDOR', 'INVESTIGATION')`; `UniqueConstraint: uq_sample_sample_no`; `CheckConstraint: ck_sample_qty quantity_sampled > 0`; `CheckConstraint: ck_sample_status status IN ('CREATED','TESTING','COMPLETED','RETAINED','DISPOSED')`

## Module `quality`

### `capa`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| capa_no | VARCHAR(30) | no |  |  |
| title | VARCHAR(200) | no |  |  |
| description | TEXT | no |  |  |
| capa_type | VARCHAR(12) | no | default CORRECTIVE |  |
| source | VARCHAR(15) | no | default DEVIATION |  |
| source_ref | VARCHAR(60) | yes |  |  |
| owner_id | BIGINT | no |  |  |
| due_date | DATE | no |  |  |
| effectiveness_due | DATE | yes |  |  |
| status | VARCHAR(20) | no | default OPEN |  |
| effectiveness_result | VARCHAR(15) | yes |  |  |
| effectiveness_comment | VARCHAR(500) | yes |  |  |
| closed_by_id | BIGINT | yes |  |  |
| closed_at | DATETIME (UTC) | yes |  |  |
| close_signature_id | BIGINT | yes | FK → e_signature.id |  |
| cancel_reason | VARCHAR(300) | yes |  |  |
| created_by_user_id | BIGINT | yes |  |  |
| id | BIGINT | no | PK |  |
| created_at | DATETIME (UTC) | no |  |  |
| created_by_id | BIGINT | yes |  |  |
| updated_at | DATETIME (UTC) | yes |  |  |
| updated_by_id | BIGINT | yes |  |  |
| row_version | INTEGER | no | default 1 |  |

Constraints: `UniqueConstraint: uq_capa_capa_no`; `CheckConstraint: ck_capa_status status IN ('OPEN', 'IN_PROGRESS', 'EFFECTIVENESS_CHECK', 'CLOSED', 'CANCELLED')`

### `capa_action`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| capa_id | BIGINT | no | FK → capa.id |  |
| seq | INTEGER | no |  |  |
| description | VARCHAR(500) | no |  |  |
| owner_id | BIGINT | no |  |  |
| due_date | DATE | no |  |  |
| status | VARCHAR(8) | no | default OPEN |  |
| completed_at | DATETIME (UTC) | yes |  |  |
| completion_notes | VARCHAR(500) | yes |  |  |
| id | BIGINT | no | PK |  |
| created_at | DATETIME (UTC) | no |  |  |
| created_by_id | BIGINT | yes |  |  |
| updated_at | DATETIME (UTC) | yes |  |  |
| updated_by_id | BIGINT | yes |  |  |
| row_version | INTEGER | no | default 1 |  |

### `change_control`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| cc_no | VARCHAR(30) | no |  |  |
| title | VARCHAR(200) | no |  |  |
| description | TEXT | no |  |  |
| change_type | VARCHAR(15) | no | default MASTER_DATA |  |
| risk_level | VARCHAR(8) | yes |  |  |
| impact_assessment | TEXT | yes |  |  |
| regulatory_impact | BOOLEAN | no | default False |  |
| status | VARCHAR(15) | no | default DRAFT |  |
| requested_by_id | BIGINT | no |  |  |
| approved_by_id | BIGINT | yes |  |  |
| approved_signature_id | BIGINT | yes | FK → e_signature.id |  |
| approved_at | DATETIME (UTC) | yes |  |  |
| decision_comment | VARCHAR(500) | yes |  |  |
| implementation_notes | TEXT | yes |  |  |
| effectiveness_notes | TEXT | yes |  |  |
| closed_by_id | BIGINT | yes |  |  |
| closed_at | DATETIME (UTC) | yes |  |  |
| close_signature_id | BIGINT | yes | FK → e_signature.id |  |
| id | BIGINT | no | PK |  |
| created_at | DATETIME (UTC) | no |  |  |
| created_by_id | BIGINT | yes |  |  |
| updated_at | DATETIME (UTC) | yes |  |  |
| updated_by_id | BIGINT | yes |  |  |
| row_version | INTEGER | no | default 1 |  |

Constraints: `UniqueConstraint: uq_change_control_cc_no`; `CheckConstraint: ck_change_control_status status IN ('DRAFT', 'ASSESSMENT', 'APPROVAL', 'IMPLEMENTATION', 'EFFECTIVENESS', 'CLOSED', 'REJECTED', 'CANCELLED')`

### `change_control_link`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| cc_id | BIGINT | no | FK → change_control.id |  |
| entity | VARCHAR(40) | no |  |  |
| record_id | BIGINT | no |  |  |
| id | BIGINT | no | PK |  |
| created_at | DATETIME (UTC) | no |  |  |
| created_by_id | BIGINT | yes |  |  |
| updated_at | DATETIME (UTC) | yes |  |  |
| updated_by_id | BIGINT | yes |  |  |
| row_version | INTEGER | no | default 1 |  |

Constraints: `UniqueConstraint: uq_change_control_link_cc_id`

### `complaint`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| complaint_no | VARCHAR(30) | no |  |  |
| received_on | DATE | no |  |  |
| customer_id | BIGINT | yes | FK → customer.id |  |
| material_batch_id | BIGINT | yes | FK → material_batch.id |  |
| dispatch_id | BIGINT | yes | FK → dispatch.id |  |
| category | VARCHAR(20) | no | default QUALITY |  |
| severity | VARCHAR(10) | no | default MINOR |  |
| description | TEXT | no |  |  |
| status | VARCHAR(15) | no | default RECEIVED |  |
| investigation | TEXT | yes |  |  |
| conclusion | TEXT | yes |  |  |
| deviation_id | BIGINT | yes |  |  |
| hold_id | BIGINT | yes |  |  |
| created_by_user_id | BIGINT | yes |  |  |
| closed_by_id | BIGINT | yes |  |  |
| closed_at | DATETIME (UTC) | yes |  |  |
| close_signature_id | BIGINT | yes | FK → e_signature.id |  |
| id | BIGINT | no | PK |  |
| created_at | DATETIME (UTC) | no |  |  |
| created_by_id | BIGINT | yes |  |  |
| updated_at | DATETIME (UTC) | yes |  |  |
| updated_by_id | BIGINT | yes |  |  |
| row_version | INTEGER | no | default 1 |  |

Constraints: `UniqueConstraint: uq_complaint_complaint_no`; `CheckConstraint: ck_complaint_severity severity IN ('MINOR','MAJOR','CRITICAL')`; `CheckConstraint: ck_complaint_status status IN ('RECEIVED','INVESTIGATION','CLOSED','CANCELLED')`

### `deviation`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| dev_no | VARCHAR(30) | no |  |  |
| title | VARCHAR(200) | no |  |  |
| description | TEXT | no |  |  |
| category | VARCHAR(20) | no | default PROCESS |  |
| severity | VARCHAR(10) | no | default MINOR |  |
| source | VARCHAR(15) | no | default MANUAL |  |
| entity_type | VARCHAR(20) | yes |  |  |
| record_id | BIGINT | yes |  |  |
| blocks_release | BOOLEAN | no | default True |  |
| status | VARCHAR(15) | no | default OPEN |  |
| raised_by_id | BIGINT | yes |  |  |
| containment | TEXT | yes |  |  |
| root_cause | TEXT | yes |  |  |
| impact_assessment | TEXT | yes |  |  |
| no_capa_justification | VARCHAR(500) | yes |  |  |
| capa_id | BIGINT | yes |  |  |
| closed_by_id | BIGINT | yes |  |  |
| closed_at | DATETIME (UTC) | yes |  |  |
| close_signature_id | BIGINT | yes | FK → e_signature.id |  |
| close_comment | VARCHAR(500) | yes |  |  |
| cancel_reason | VARCHAR(300) | yes |  |  |
| id | BIGINT | no | PK |  |
| created_at | DATETIME (UTC) | no |  |  |
| created_by_id | BIGINT | yes |  |  |
| updated_at | DATETIME (UTC) | yes |  |  |
| updated_by_id | BIGINT | yes |  |  |
| row_version | INTEGER | no | default 1 |  |

Constraints: `CheckConstraint: ck_deviation_severity severity IN ('MINOR','MAJOR','CRITICAL')`; `UniqueConstraint: uq_deviation_dev_no`; `CheckConstraint: ck_deviation_status status IN ('OPEN', 'INVESTIGATION', 'CAPA_PROPOSED', 'QA_REVIEW', 'CLOSED', 'CANCELLED')`

### `recall`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| recall_no | VARCHAR(30) | no |  |  |
| material_batch_id | BIGINT | no | FK → material_batch.id |  |
| recall_class | VARCHAR(3) | no | default II |  |
| reason | VARCHAR(1000) | no |  |  |
| complaint_id | BIGINT | yes |  |  |
| status | VARCHAR(12) | no | default INITIATED |  |
| initiated_by_id | BIGINT | yes |  |  |
| initiated_signature_id | BIGINT | yes | FK → e_signature.id |  |
| hold_id | BIGINT | yes |  |  |
| closure_summary | VARCHAR(1000) | yes |  |  |
| closed_by_id | BIGINT | yes |  |  |
| closed_at | DATETIME (UTC) | yes |  |  |
| close_signature_id | BIGINT | yes | FK → e_signature.id |  |
| id | BIGINT | no | PK |  |
| created_at | DATETIME (UTC) | no |  |  |
| created_by_id | BIGINT | yes |  |  |
| updated_at | DATETIME (UTC) | yes |  |  |
| updated_by_id | BIGINT | yes |  |  |
| row_version | INTEGER | no | default 1 |  |

Constraints: `CheckConstraint: ck_recall_status status IN ('INITIATED','IN_PROGRESS','CLOSED')`; `UniqueConstraint: uq_recall_recall_no`; `CheckConstraint: ck_recall_class recall_class IN ('I','II','III')`

### `recall_line`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| recall_id | BIGINT | no | FK → recall.id |  |
| dispatch_id | BIGINT | no | FK → dispatch.id |  |
| customer_id | BIGINT | no | FK → customer.id |  |
| quantity_dispatched | NUMERIC(18, 6) | no |  |  |
| notified_at | DATETIME (UTC) | yes |  |  |
| response | VARCHAR(300) | yes |  |  |
| quantity_returned | NUMERIC(18, 6) | no | default 0 |  |
| quantity_consumed_or_unrecoverable | NUMERIC(18, 6) | no | default 0 |  |
| id | BIGINT | no | PK |  |
| created_at | DATETIME (UTC) | no |  |  |
| created_by_id | BIGINT | yes |  |  |
| updated_at | DATETIME (UTC) | yes |  |  |
| updated_by_id | BIGINT | yes |  |  |
| row_version | INTEGER | no | default 1 |  |

Constraints: `UniqueConstraint: uq_recall_line_recall_id`

### `risk_assessment`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| ra_no | VARCHAR(30) | no |  |  |
| title | VARCHAR(200) | no |  |  |
| scope | TEXT | yes |  |  |
| ref_type | VARCHAR(20) | yes |  |  |
| ref_no | VARCHAR(40) | yes |  |  |
| status | VARCHAR(10) | no | default DRAFT |  |
| created_by_user_id | BIGINT | yes |  |  |
| approved_by_id | BIGINT | yes |  |  |
| approved_signature_id | BIGINT | yes | FK → e_signature.id |  |
| approved_at | DATETIME (UTC) | yes |  |  |
| id | BIGINT | no | PK |  |
| created_at | DATETIME (UTC) | no |  |  |
| created_by_id | BIGINT | yes |  |  |
| updated_at | DATETIME (UTC) | yes |  |  |
| updated_by_id | BIGINT | yes |  |  |
| row_version | INTEGER | no | default 1 |  |

Constraints: `CheckConstraint: ck_risk_assessment_status status IN ('DRAFT','APPROVED','OBSOLETE')`; `UniqueConstraint: uq_risk_assessment_ra_no`

### `risk_item`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| ra_id | BIGINT | no | FK → risk_assessment.id |  |
| seq | INTEGER | no |  |  |
| function_step | VARCHAR(200) | no |  |  |
| failure_mode | VARCHAR(300) | no |  |  |
| effect | VARCHAR(300) | yes |  |  |
| cause | VARCHAR(300) | yes |  |  |
| controls | VARCHAR(300) | yes |  |  |
| severity | INTEGER | no |  |  |
| occurrence | INTEGER | no |  |  |
| detection | INTEGER | no |  |  |
| rpn | INTEGER | no |  |  |
| risk_level | VARCHAR(8) | no |  |  |
| mitigation | VARCHAR(500) | yes |  |  |
| residual_severity | INTEGER | yes |  |  |
| residual_occurrence | INTEGER | yes |  |  |
| residual_detection | INTEGER | yes |  |  |
| residual_rpn | INTEGER | yes |  |  |
| residual_level | VARCHAR(8) | yes |  |  |
| id | BIGINT | no | PK |  |
| created_at | DATETIME (UTC) | no |  |  |
| created_by_id | BIGINT | yes |  |  |
| updated_at | DATETIME (UTC) | yes |  |  |
| updated_by_id | BIGINT | yes |  |  |
| row_version | INTEGER | no | default 1 |  |

Constraints: `CheckConstraint: ck_risk_item_scores severity BETWEEN 1 AND 10 AND occurrence BETWEEN 1 AND 10 AND detection BETWEEN 1 AND 10`; `UniqueConstraint: uq_risk_item_ra_id`

### `sop`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| sop_no | VARCHAR(40) | no |  |  |
| version_no | INTEGER | no | default 1 |  |
| title | VARCHAR(200) | no |  |  |
| department_id | BIGINT | yes | FK → department.id |  |
| owner_id | BIGINT | yes |  |  |
| document_id | BIGINT | yes | FK → document.id |  |
| review_period_months | INTEGER | no | default 24 |  |
| review_due_date | DATE | yes |  |  |
| status | VARCHAR(15) | no | default DRAFT |  |
| supersedes_id | BIGINT | yes | FK → sop.id |  |
| effective_from | DATETIME (UTC) | yes |  |  |
| effective_to | DATETIME (UTC) | yes |  |  |
| change_reason | VARCHAR(1000) | yes |  |  |
| approved_signature_id | BIGINT | yes | FK → e_signature.id |  |
| id | BIGINT | no | PK |  |
| created_at | DATETIME (UTC) | no |  |  |
| created_by_id | BIGINT | yes |  |  |
| updated_at | DATETIME (UTC) | yes |  |  |
| updated_by_id | BIGINT | yes |  |  |
| row_version | INTEGER | no | default 1 |  |

Constraints: `CheckConstraint: ck_sop_status status IN ('DRAFT','UNDER_REVIEW','APPROVED','SUPERSEDED')`; `UniqueConstraint: uq_sop_sop_no`

### `sop_acknowledgement` — **append-only**

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| sop_id | BIGINT | no | FK → sop.id |  |
| user_id | BIGINT | no |  |  |
| acknowledged_at | DATETIME (UTC) | no |  |  |
| id | BIGINT | no | PK |  |

Constraints: `UniqueConstraint: uq_sop_acknowledgement_sop_id`

## Module `reporting`

### `archive_batch` — **append-only**

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| archive_no | VARCHAR(30) | no |  |  |
| record_type | VARCHAR(40) | no |  |  |
| cutoff_date | DATE | no |  |  |
| row_count | INTEGER | no |  |  |
| from_id | BIGINT | no |  |  |
| to_id | BIGINT | no |  |  |
| document_id | BIGINT | no | FK → document.id |  |
| sha256 | VARCHAR(64) | no |  |  |
| created_by_id | BIGINT | yes |  |  |
| created_at | DATETIME (UTC) | no |  |  |
| id | BIGINT | no | PK |  |

Constraints: `UniqueConstraint: uq_archive_batch_archive_no`

### `backup_record` — **append-only**

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| backup_type | VARCHAR(15) | no |  |  |
| performed_at | DATETIME (UTC) | no |  |  |
| result | VARCHAR(8) | no | default SUCCESS |  |
| location | VARCHAR(300) | yes |  |  |
| size_mb | INTEGER | yes |  |  |
| sha256 | VARCHAR(64) | yes |  |  |
| tool | VARCHAR(100) | yes |  |  |
| notes | VARCHAR(500) | yes |  |  |
| audit_chain_verified | BOOLEAN | yes |  |  |
| rto_minutes | INTEGER | yes |  |  |
| recorded_by_id | BIGINT | yes |  |  |
| recorded_at | DATETIME (UTC) | no |  |  |
| id | BIGINT | no | PK |  |

Constraints: `CheckConstraint: ck_backup_record_type backup_type IN ('FULL','DIFFERENTIAL','LOG','DOCUMENTS','RESTORE_TEST')`; `CheckConstraint: ck_backup_record_result result IN ('SUCCESS','FAILED')`

### `report_run` — **append-only**

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| copy_no | VARCHAR(30) | no |  |  |
| report_code | VARCHAR(60) | no |  |  |
| title | VARCHAR(200) | no |  |  |
| params_json | TEXT | yes |  |  |
| output_format | VARCHAR(8) | no |  |  |
| row_count | INTEGER | yes |  |  |
| sha256 | VARCHAR(64) | no |  |  |
| user_id | BIGINT | no |  |  |
| username | VARCHAR(80) | no |  |  |
| run_at | DATETIME (UTC) | no |  |  |
| ref_entity | VARCHAR(40) | yes |  |  |
| ref_id | VARCHAR(40) | yes |  |  |
| id | BIGINT | no | PK |  |

Constraints: `UniqueConstraint: uq_report_run_copy_no`

### `retention_policy`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| record_type | VARCHAR(40) | no |  |  |
| retention_years | INTEGER | no |  |  |
| legal_hold | BOOLEAN | no | default False |  |
| legal_hold_reason | VARCHAR(500) | yes |  |  |
| basis | VARCHAR(300) | yes |  |  |
| last_archived_cutoff | DATE | yes |  |  |
| id | BIGINT | no | PK |  |
| created_at | DATETIME (UTC) | no |  |  |
| created_by_id | BIGINT | yes |  |  |
| updated_at | DATETIME (UTC) | yes |  |  |
| updated_by_id | BIGINT | yes |  |  |
| row_version | INTEGER | no | default 1 |  |

Constraints: `CheckConstraint: ck_retention_policy_years retention_years >= 1`; `UniqueConstraint: uq_retention_policy_record_type`

## Module `spec`

### `sampling_plan`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| plan_no | VARCHAR(40) | no |  |  |
| material_id | BIGINT | no | FK → material.id |  |
| supersedes_id | BIGINT | yes | FK → sampling_plan.id |  |
| sampling_rule | VARCHAR(15) | no | default SQRT_N_PLUS_1 |  |
| fixed_qty | NUMERIC(18, 6) | yes |  |  |
| percent | NUMERIC(7, 3) | yes |  |  |
| unit_id | BIGINT | yes | FK → unit.id |  |
| container_rule | VARCHAR(200) | yes |  |  |
| remarks | VARCHAR(500) | yes |  |  |
| version_no | INTEGER | no | default 1 |  |
| status | VARCHAR(20) | no | default DRAFT |  |
| effective_from | DATETIME (UTC) | yes |  |  |
| effective_to | DATETIME (UTC) | yes |  |  |
| change_reason | VARCHAR(1000) | yes |  |  |
| approved_signature_id | BIGINT | yes | FK → e_signature.id |  |
| id | BIGINT | no | PK |  |
| created_at | DATETIME (UTC) | no |  |  |
| created_by_id | BIGINT | yes |  |  |
| updated_at | DATETIME (UTC) | yes |  |  |
| updated_by_id | BIGINT | yes |  |  |
| row_version | INTEGER | no | default 1 |  |

Constraints: `UniqueConstraint: uq_sampling_plan_plan_no`; `CheckConstraint: ck_sampling_plan_status status IN ('DRAFT','UNDER_REVIEW','APPROVED','SUPERSEDED')`; `CheckConstraint: ck_sampling_plan_sampling_rule sampling_rule IN ('FIXED','SQRT_N_PLUS_1','PERCENT','ALL')`

### `specification`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| spec_no | VARCHAR(40) | no |  |  |
| material_id | BIGINT | no | FK → material.id |  |
| title | VARCHAR(200) | yes |  |  |
| supersedes_id | BIGINT | yes | FK → specification.id |  |
| pharmacopoeial_reference | VARCHAR(100) | yes |  |  |
| version_no | INTEGER | no | default 1 |  |
| status | VARCHAR(20) | no | default DRAFT |  |
| effective_from | DATETIME (UTC) | yes |  |  |
| effective_to | DATETIME (UTC) | yes |  |  |
| change_reason | VARCHAR(1000) | yes |  |  |
| approved_signature_id | BIGINT | yes | FK → e_signature.id |  |
| id | BIGINT | no | PK |  |
| created_at | DATETIME (UTC) | no |  |  |
| created_by_id | BIGINT | yes |  |  |
| updated_at | DATETIME (UTC) | yes |  |  |
| updated_by_id | BIGINT | yes |  |  |
| row_version | INTEGER | no | default 1 |  |

Constraints: `UniqueConstraint: uq_specification_spec_no`; `CheckConstraint: ck_specification_status status IN ('DRAFT','UNDER_REVIEW','APPROVED','SUPERSEDED')`

### `specification_parameter`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| specification_id | BIGINT | no | FK → specification.id |  |
| seq | INTEGER | no |  |  |
| test_name | VARCHAR(150) | no |  |  |
| test_method | VARCHAR(150) | yes |  |  |
| stp_id | BIGINT | yes | FK → stp.id |  |
| spec_type | VARCHAR(10) | no | default NUMERIC |  |
| lsl | NUMERIC(18, 6) | yes |  |  |
| usl | NUMERIC(18, 6) | yes |  |  |
| target | NUMERIC(18, 6) | yes |  |  |
| unit | VARCHAR(20) | yes |  |  |
| decimal_places | INTEGER | yes |  |  |
| acceptance_criteria | VARCHAR(300) | yes |  |  |
| pharmacopoeial_reference | VARCHAR(100) | yes |  |  |
| frequency | VARCHAR(60) | yes |  |  |
| criticality | VARCHAR(10) | no | default MAJOR |  |
| alert_low | NUMERIC(18, 6) | yes |  |  |
| alert_high | NUMERIC(18, 6) | yes |  |  |
| action_low | NUMERIC(18, 6) | yes |  |  |
| action_high | NUMERIC(18, 6) | yes |  |  |
| id | BIGINT | no | PK |  |
| created_at | DATETIME (UTC) | no |  |  |
| created_by_id | BIGINT | yes |  |  |
| updated_at | DATETIME (UTC) | yes |  |  |
| updated_by_id | BIGINT | yes |  |  |
| row_version | INTEGER | no | default 1 |  |

Constraints: `CheckConstraint: ck_specification_parameter_usl_ge_lsl usl IS NULL OR lsl IS NULL OR usl >= lsl`; `CheckConstraint: ck_specification_parameter_criticality criticality IN ('CRITICAL','MAJOR','MINOR')`; `CheckConstraint: ck_specification_parameter_spec_type spec_type IN ('NUMERIC','RANGE','TEXT','PASS_FAIL')`; `UniqueConstraint: uq_specification_parameter_specification_id`

### `stp`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| stp_no | VARCHAR(40) | no |  |  |
| title | VARCHAR(200) | no |  |  |
| supersedes_id | BIGINT | yes | FK → stp.id |  |
| test_method | VARCHAR(200) | yes |  |  |
| equipment_required | TEXT | yes |  |  |
| reagents_required | TEXT | yes |  |  |
| reference_standards | TEXT | yes |  |  |
| procedure | TEXT | yes |  |  |
| calculation | TEXT | yes |  |  |
| acceptance_criteria | TEXT | yes |  |  |
| safety_precautions | TEXT | yes |  |  |
| version_no | INTEGER | no | default 1 |  |
| status | VARCHAR(20) | no | default DRAFT |  |
| effective_from | DATETIME (UTC) | yes |  |  |
| effective_to | DATETIME (UTC) | yes |  |  |
| change_reason | VARCHAR(1000) | yes |  |  |
| approved_signature_id | BIGINT | yes | FK → e_signature.id |  |
| id | BIGINT | no | PK |  |
| created_at | DATETIME (UTC) | no |  |  |
| created_by_id | BIGINT | yes |  |  |
| updated_at | DATETIME (UTC) | yes |  |  |
| updated_by_id | BIGINT | yes |  |  |
| row_version | INTEGER | no | default 1 |  |

Constraints: `CheckConstraint: ck_stp_status status IN ('DRAFT','UNDER_REVIEW','APPROVED','SUPERSEDED')`; `UniqueConstraint: uq_stp_stp_no`

## Module `warehouse`

### `checklist_item`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| code | VARCHAR(40) | no |  |  |
| text | VARCHAR(200) | no |  |  |
| is_critical | BOOLEAN | no | default False |  |
| is_active | BOOLEAN | no | default True |  |
| seq | INTEGER | no | default 100 |  |
| id | BIGINT | no | PK |  |
| created_at | DATETIME (UTC) | no |  |  |
| created_by_id | BIGINT | yes |  |  |
| updated_at | DATETIME (UTC) | yes |  |  |
| updated_by_id | BIGINT | yes |  |  |
| row_version | INTEGER | no | default 1 |  |

Constraints: `UniqueConstraint: uq_checklist_item_code`

### `destruction_record`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| destruction_no | VARCHAR(30) | no |  |  |
| material_batch_id | BIGINT | no | FK → material_batch.id |  |
| location_id | BIGINT | no | FK → location.id |  |
| quantity | NUMERIC(18, 6) | no |  |  |
| method | VARCHAR(100) | no |  |  |
| reason | VARCHAR(300) | no |  |  |
| status | VARCHAR(10) | no | default REQUESTED |  |
| requested_by_id | BIGINT | no |  |  |
| approved_by_id | BIGINT | yes |  |  |
| approved_signature_id | BIGINT | yes |  |  |
| executed_at | DATETIME (UTC) | yes |  |  |
| ledger_txn_id | BIGINT | yes |  |  |
| id | BIGINT | no | PK |  |
| created_at | DATETIME (UTC) | no |  |  |
| created_by_id | BIGINT | yes |  |  |
| updated_at | DATETIME (UTC) | yes |  |  |
| updated_by_id | BIGINT | yes |  |  |
| row_version | INTEGER | no | default 1 |  |

Constraints: `CheckConstraint: ck_destruction_record_qty quantity > 0`; `UniqueConstraint: uq_destruction_record_destruction_no`; `CheckConstraint: ck_destruction_record_status status IN ('REQUESTED','APPROVED','REJECTED','EXECUTED')`

### `grn`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| grn_no | VARCHAR(30) | no |  |  |
| grn_date | DATE | no |  |  |
| po_id | BIGINT | no | FK → purchase_order.id |  |
| vendor_id | BIGINT | no | FK → vendor.id |  |
| invoice_no | VARCHAR(60) | yes |  |  |
| invoice_date | DATE | yes |  |  |
| vehicle_no | VARCHAR(30) | yes |  |  |
| transporter | VARCHAR(100) | yes |  |  |
| transport_details | VARCHAR(300) | yes |  |  |
| remarks | VARCHAR(500) | yes |  |  |
| received_by_id | BIGINT | no |  |  |
| status | VARCHAR(20) | no | default DRAFT |  |
| checklist_passed | BOOLEAN | yes |  |  |
| quarantine_location_id | BIGINT | yes | FK → location.id |  |
| verified_by_id | BIGINT | yes |  |  |
| reject_reason | VARCHAR(500) | yes |  |  |
| id | BIGINT | no | PK |  |
| created_at | DATETIME (UTC) | no |  |  |
| created_by_id | BIGINT | yes |  |  |
| updated_at | DATETIME (UTC) | yes |  |  |
| updated_by_id | BIGINT | yes |  |  |
| row_version | INTEGER | no | default 1 |  |

Constraints: `UniqueConstraint: uq_grn_grn_no`; `CheckConstraint: ck_grn_status status IN ('DRAFT','SUBMITTED','VERIFIED','QUARANTINE','REJECTED','CANCELLED')`

### `grn_checklist`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| grn_id | BIGINT | no | FK → grn.id |  |
| item_id | BIGINT | no | FK → checklist_item.id |  |
| answer | VARCHAR(3) | no |  |  |
| comment | VARCHAR(300) | yes |  |  |
| exception_ref | VARCHAR(100) | yes |  |  |
| exception_signature_id | BIGINT | yes | FK → e_signature.id |  |
| id | BIGINT | no | PK |  |
| created_at | DATETIME (UTC) | no |  |  |
| created_by_id | BIGINT | yes |  |  |
| updated_at | DATETIME (UTC) | yes |  |  |
| updated_by_id | BIGINT | yes |  |  |
| row_version | INTEGER | no | default 1 |  |

Constraints: `CheckConstraint: ck_grn_checklist_answer answer IN ('YES','NO','NA')`; `UniqueConstraint: uq_grn_checklist_grn_id`

### `grn_line`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| grn_id | BIGINT | no | FK → grn.id |  |
| line_no | INTEGER | no |  |  |
| po_line_id | BIGINT | no | FK → purchase_order_line.id |  |
| material_id | BIGINT | no | FK → material.id |  |
| vendor_batch_no | VARCHAR(60) | no |  |  |
| quantity_received | NUMERIC(18, 6) | no |  |  |
| unit_id | BIGINT | no | FK → unit.id |  |
| pack_count | INTEGER | no | default 1 |  |
| mfg_date | DATE | yes |  |  |
| expiry_date | DATE | yes |  |  |
| retest_date | DATE | yes |  |  |
| coa_received | BOOLEAN | no | default False |  |
| container_condition | VARCHAR(100) | yes |  |  |
| seal_condition | VARCHAR(100) | yes |  |  |
| packaging_condition | VARCHAR(100) | yes |  |  |
| temperature_condition | VARCHAR(100) | yes |  |  |
| other_documents | VARCHAR(300) | yes |  |  |
| material_batch_id | BIGINT | yes |  |  |
| id | BIGINT | no | PK |  |
| created_at | DATETIME (UTC) | no |  |  |
| created_by_id | BIGINT | yes |  |  |
| updated_at | DATETIME (UTC) | yes |  |  |
| updated_by_id | BIGINT | yes |  |  |
| row_version | INTEGER | no | default 1 |  |

Constraints: `CheckConstraint: ck_grn_line_qty quantity_received > 0`; `UniqueConstraint: uq_grn_line_grn_id`; `CheckConstraint: ck_grn_line_dates expiry_date IS NULL OR mfg_date IS NULL OR expiry_date >= mfg_date`

### `inventory_balance`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| id | BIGINT | no | PK |  |
| material_batch_id | BIGINT | no | FK → material_batch.id |  |
| location_id | BIGINT | no | FK → location.id |  |
| qty_on_hand | NUMERIC(18, 6) | no | default 0 |  |
| qty_reserved | NUMERIC(18, 6) | no | default 0 |  |

Constraints: `CheckConstraint: ck_inventory_balance_reserved qty_reserved >= 0`; `CheckConstraint: ck_inventory_balance_reserved_le_on_hand qty_reserved <= qty_on_hand`; `CheckConstraint: ck_inventory_balance_on_hand qty_on_hand >= 0`; `UniqueConstraint: uq_inventory_balance_material_batch_id`

### `inventory_transaction` — **append-only**

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| material_batch_id | BIGINT | no | FK → material_batch.id |  |
| txn_type | VARCHAR(15) | no |  |  |
| from_location_id | BIGINT | yes | FK → location.id |  |
| to_location_id | BIGINT | yes | FK → location.id |  |
| quantity | NUMERIC(18, 6) | no |  |  |
| unit_id | BIGINT | no | FK → unit.id |  |
| ref_doc_type | VARCHAR(30) | yes |  |  |
| ref_doc_id | VARCHAR(40) | yes |  |  |
| reverses_txn_id | BIGINT | yes |  |  |
| reason | VARCHAR(500) | yes |  |  |
| signature_id | BIGINT | yes |  |  |
| user_id | BIGINT | yes |  |  |
| txn_ts | DATETIME (UTC) | no |  |  |
| id | BIGINT | no | PK |  |

Constraints: `CheckConstraint: ck_inventory_transaction_txn_type txn_type IN ('RECEIPT','TRANSFER','SAMPLE','ISSUE','RETURN','REJECT_MOVE','DESTROY','ADJUST_IN','ADJUST_OUT','DISPATCH','OUTPUT')`; `CheckConstraint: ck_inventory_transaction_qty_positive quantity > 0`

### `material_batch`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| lot_no | VARCHAR(40) | no |  |  |
| material_id | BIGINT | no | FK → material.id |  |
| source_type | VARCHAR(10) | no | default GRN |  |
| grn_line_id | BIGINT | yes |  |  |
| manufacturing_batch_id | BIGINT | yes |  |  |
| vendor_id | BIGINT | yes | FK → vendor.id |  |
| vendor_batch_no | VARCHAR(60) | yes |  |  |
| mfg_date | DATE | yes |  |  |
| expiry_date | DATE | yes |  |  |
| retest_date | DATE | yes |  |  |
| quantity | NUMERIC(18, 6) | no |  |  |
| unit_id | BIGINT | no | FK → unit.id |  |
| disposition | VARCHAR(15) | no | default QUARANTINE |  |
| qc_no | VARCHAR(40) | yes |  |  |
| qa_release_no | VARCHAR(40) | yes |  |  |
| released_at | DATETIME (UTC) | yes |  |  |
| release_signature_id | BIGINT | yes |  |  |
| specification_id | BIGINT | yes | FK → specification.id |  |
| sampling_plan_id | BIGINT | yes | FK → sampling_plan.id |  |
| id | BIGINT | no | PK |  |
| created_at | DATETIME (UTC) | no |  |  |
| created_by_id | BIGINT | yes |  |  |
| updated_at | DATETIME (UTC) | yes |  |  |
| updated_by_id | BIGINT | yes |  |  |
| row_version | INTEGER | no | default 1 |  |

Constraints: `CheckConstraint: ck_material_batch_disposition disposition IN ('QUARANTINE', 'QC_TESTING', 'QC_APPROVED', 'QA_REVIEW', 'APPROVED', 'REJECTED', 'EXPIRED', 'RETURNED', 'DESTROYED')`; `UniqueConstraint: uq_material_batch_lot_no`

### `material_container`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| batch_id | BIGINT | no | FK → material_batch.id |  |
| container_no | INTEGER | no |  |  |
| quantity | NUMERIC(18, 6) | no |  |  |
| id | BIGINT | no | PK |  |
| created_at | DATETIME (UTC) | no |  |  |
| created_by_id | BIGINT | yes |  |  |
| updated_at | DATETIME (UTC) | yes |  |  |
| updated_by_id | BIGINT | yes |  |  |
| row_version | INTEGER | no | default 1 |  |

Constraints: `UniqueConstraint: uq_material_container_batch_id`

### `material_label` — **append-only**

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| label_no | VARCHAR(30) | no |  |  |
| label_type | VARCHAR(15) | no |  |  |
| material_batch_id | BIGINT | yes | FK → material_batch.id |  |
| ref_type | VARCHAR(30) | yes |  |  |
| ref_id | VARCHAR(40) | yes |  |  |
| template_version | VARCHAR(10) | no | default 1 |  |
| copies | INTEGER | no | default 1 |  |
| reprint_reason | VARCHAR(300) | yes |  |  |
| printed_by_id | BIGINT | yes |  |  |
| printed_at | DATETIME (UTC) | no |  |  |
| id | BIGINT | no | PK |  |

Constraints: `UniqueConstraint: uq_material_label_label_no`

### `quality_hold`

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| hold_no | VARCHAR(30) | no |  |  |
| entity_type | VARCHAR(15) | no |  |  |
| record_id | BIGINT | no |  |  |
| status | VARCHAR(10) | no | default OPEN |  |
| source | VARCHAR(15) | no | default MANUAL |  |
| reason | VARCHAR(500) | no |  |  |
| ref | VARCHAR(60) | yes |  |  |
| placed_by_id | BIGINT | yes |  |  |
| placed_at | DATETIME (UTC) | no |  |  |
| released_by_id | BIGINT | yes |  |  |
| released_at | DATETIME (UTC) | yes |  |  |
| release_reason | VARCHAR(500) | yes |  |  |
| release_signature_id | BIGINT | yes |  |  |
| id | BIGINT | no | PK |  |
| created_at | DATETIME (UTC) | no |  |  |
| created_by_id | BIGINT | yes |  |  |
| updated_at | DATETIME (UTC) | yes |  |  |
| updated_by_id | BIGINT | yes |  |  |
| row_version | INTEGER | no | default 1 |  |

Constraints: `CheckConstraint: ck_quality_hold_entity_type entity_type IN ('MATERIAL_BATCH','MFG_BATCH')`; `CheckConstraint: ck_quality_hold_status status IN ('OPEN','RELEASED')`

### `storage_temperature_log` — **append-only**

| Column | Type | Null | Key / default | Notes |
|---|---|---|---|---|
| location_id | BIGINT | no | FK → location.id |  |
| reading | NUMERIC(6, 2) | no |  |  |
| recorded_at | DATETIME (UTC) | no |  |  |
| recorded_by_id | BIGINT | yes |  |  |
| excursion | BOOLEAN | no | default False |  |
| remarks | VARCHAR(300) | yes |  |  |
| id | BIGINT | no | PK |  |
