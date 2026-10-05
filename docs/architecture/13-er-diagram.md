# ER Diagrams

Foreign-key relationships per module (Mermaid). Cross-module references are shown as dashed groups by naming the foreign table.

## audit

```mermaid
erDiagram
  users ||--o{ e_signature : "user_id"
  audit_chain_head { int id }
  audit_trail { int id }
  error_log { int id }
  gmp_status_history { int id }
  record_action { int id }
  security_event { int id }
```

## dispatch

```mermaid
erDiagram
  customer ||--o{ dispatch : "customer_id"
  e_signature ||--o{ dispatch : "approved_signature_id"
  dispatch ||--o{ dispatch_line : "dispatch_id"
  material_batch ||--o{ dispatch_line : "material_batch_id"
  location ||--o{ dispatch_line : "location_id"
  unit ||--o{ dispatch_line : "unit_id"
```

## iam

```mermaid
erDiagram
  users ||--o{ password_history : "user_id"
  role ||--o{ role_permission : "role_id"
  permission ||--o{ role_permission : "permission_id"
  users ||--o{ training_record : "user_id"
  users ||--o{ user_role : "user_id"
  role ||--o{ user_role : "role_id"
  users ||--o{ user_role : "granted_by_id"
  users ||--o{ user_session : "user_id"
  department ||--o{ users : "department_id"
  plant ||--o{ users : "plant_id"
  sod_rule { int id }
```

## importing

```mermaid
erDiagram
  document ||--o{ import_job : "document_id"
  import_job ||--o{ import_row : "job_id"
```

## manufacturing

```mermaid
erDiagram
  manufacturing_batch ||--o{ batch_equipment_use : "batch_id"
  equipment ||--o{ batch_equipment_use : "equipment_id"
  manufacturing_batch ||--o{ batch_material : "batch_id"
  bom_line ||--o{ batch_material : "bom_line_id"
  material ||--o{ batch_material : "material_id"
  unit ||--o{ batch_material : "unit_id"
  manufacturing_batch ||--o{ batch_reconciliation : "batch_id"
  e_signature ||--o{ batch_reconciliation : "production_signature_id"
  e_signature ||--o{ batch_reconciliation : "qa_signature_id"
  manufacturing_batch ||--o{ batch_step_execution : "batch_id"
  e_signature ||--o{ batch_step_execution : "verify_signature_id"
  animal ||--o{ bleed_record : "animal_id"
  material ||--o{ bom_header : "product_material_id"
  unit ||--o{ bom_header : "unit_id"
  bom_header ||--o{ bom_header : "supersedes_id"
  e_signature ||--o{ bom_header : "approved_signature_id"
  bom_header ||--o{ bom_line : "bom_id"
  material ||--o{ bom_line : "material_id"
  unit ||--o{ bom_line : "unit_id"
  animal ||--o{ immunisation_record : "animal_id"
  manufacturing_batch ||--o{ ipc_result : "batch_id"
  equipment ||--o{ ipc_result : "equipment_id"
  material ||--o{ manufacturing_batch : "product_material_id"
  bom_header ||--o{ manufacturing_batch : "bom_id"
  unit ||--o{ manufacturing_batch : "unit_id"
  e_signature ||--o{ manufacturing_batch : "line_clearance_signature_id"
  manufacturing_batch ||--o{ material_issue : "batch_id"
  batch_material ||--o{ material_issue : "batch_material_id"
  material_batch ||--o{ material_issue : "material_batch_id"
  location ||--o{ material_issue : "location_id"
  manufacturing_batch ||--o{ material_issue_indent : "batch_id"
  material_issue ||--o{ material_return : "issue_id"
  manufacturing_batch ||--o{ material_return : "batch_id"
  batch_material ||--o{ material_return : "batch_material_id"
  material_batch ||--o{ material_return : "material_batch_id"
  location ||--o{ material_return : "location_id"
  bom_header ||--o{ mbr_step : "bom_id"
  material_batch ||--o{ plasma_pool : "material_batch_id"
```

## master

```mermaid
erDiagram
  equipment ||--o{ calibration : "equipment_id"
  document ||--o{ calibration : "certificate_document_id"
  category ||--o{ category : "parent_id"
  location ||--o{ equipment : "location_id"
  warehouse ||--o{ location : "warehouse_id"
  location ||--o{ location : "parent_id"
  unit ||--o{ location : "capacity_unit_id"
  location ||--o{ location_category : "location_id"
  category ||--o{ location_category : "category_id"
  category ||--o{ location_compat_rule : "category_a_id"
  category ||--o{ location_compat_rule : "category_b_id"
  material_type ||--o{ material : "type_id"
  category ||--o{ material : "category_id"
  unit ||--o{ material : "base_unit_id"
  unit ||--o{ unit_conversion : "from_unit_id"
  unit ||--o{ unit_conversion : "to_unit_id"
  vendor ||--o{ vendor_document : "vendor_id"
  document ||--o{ vendor_document : "document_id"
  plant ||--o{ warehouse : "plant_id"
  customer { int id }
```

## org

```mermaid
erDiagram
  document ||--o{ company : "logo_document_id"
  plant ||--o{ department : "plant_id"
  company ||--o{ plant : "company_id"
```

## platform

```mermaid
erDiagram
  document ||--o{ doc_link : "document_id"
  document ||--o{ document : "supersedes_id"
  users ||--o{ notification : "user_id"
  plant ||--o{ number_registry : "plant_id"
  plant ||--o{ number_sequence : "plant_id"
  e_signature ||--o{ workflow_definition : "approved_signature_id"
  workflow_definition ||--o{ workflow_instance : "definition_id"
  users ||--o{ workflow_instance : "initiated_by_id"
  workflow_definition ||--o{ workflow_step : "definition_id"
  role ||--o{ workflow_step : "role_id"
  role ||--o{ workflow_step : "escalate_role_id"
  workflow_instance ||--o{ workflow_transaction : "instance_id"
  users ||--o{ workflow_transaction : "actor_id"
  e_signature ||--o{ workflow_transaction : "signature_id"
  system_configuration { int id }
```

## purchase

```mermaid
erDiagram
  vendor ||--o{ purchase_order : "vendor_id"
  vendor_qualification ||--o{ purchase_order : "vendor_qualification_id"
  purchase_request ||--o{ purchase_order : "pr_id"
  workflow_instance ||--o{ purchase_order : "workflow_instance_id"
  purchase_order ||--o{ purchase_order_line : "po_id"
  material ||--o{ purchase_order_line : "material_id"
  specification ||--o{ purchase_order_line : "specification_id"
  vendor_material ||--o{ purchase_order_line : "vendor_material_id"
  unit ||--o{ purchase_order_line : "unit_id"
  department ||--o{ purchase_request : "department_id"
  users ||--o{ purchase_request : "requested_by_id"
  workflow_instance ||--o{ purchase_request : "workflow_instance_id"
  purchase_request ||--o{ purchase_request_line : "pr_id"
  material ||--o{ purchase_request_line : "material_id"
  unit ||--o{ purchase_request_line : "unit_id"
  vendor ||--o{ purchase_request_line : "preferred_vendor_id"
  vendor ||--o{ vendor_material : "vendor_id"
  material ||--o{ vendor_material : "material_id"
  vendor_material ||--o{ vendor_material : "supersedes_id"
  e_signature ||--o{ vendor_material : "approved_signature_id"
  vendor ||--o{ vendor_qualification : "vendor_id"
  vendor_qualification ||--o{ vendor_qualification : "supersedes_id"
  e_signature ||--o{ vendor_qualification : "approved_signature_id"
```

## qc

```mermaid
erDiagram
  material_batch ||--o{ coa : "material_batch_id"
  document ||--o{ coa : "pdf_document_id"
  document ||--o{ coa : "xlsx_document_id"
  material_batch ||--o{ conditional_release : "material_batch_id"
  e_signature ||--o{ conditional_release : "approved_signature_id"
  qc_result ||--o{ oos_investigation : "qc_result_id"
  qc_test ||--o{ oos_investigation : "qc_test_id"
  sample ||--o{ oos_investigation : "sample_id"
  material_batch ||--o{ oos_investigation : "material_batch_id"
  e_signature ||--o{ oos_investigation : "decision_signature_id"
  qc_result ||--o{ oot_event : "qc_result_id"
  material ||--o{ oot_event : "material_id"
  qc_test ||--o{ qc_result : "test_id"
  qc_result ||--o{ qc_result_amendment : "result_id"
  e_signature ||--o{ qc_result_amendment : "approved_signature_id"
  sample ||--o{ qc_test : "sample_id"
  specification_parameter ||--o{ qc_test : "spec_parameter_id"
  stp ||--o{ qc_test : "stp_id"
  equipment ||--o{ qc_test : "equipment_id"
  e_signature ||--o{ qc_test : "calibration_override_signature_id"
  material_batch ||--o{ sample : "material_batch_id"
  specification ||--o{ sample : "specification_id"
  sampling_plan ||--o{ sample : "sampling_plan_id"
  unit ||--o{ sample : "unit_id"
  location ||--o{ sample : "sampling_location_id"
```

## quality

```mermaid
erDiagram
  e_signature ||--o{ capa : "close_signature_id"
  capa ||--o{ capa_action : "capa_id"
  e_signature ||--o{ change_control : "approved_signature_id"
  e_signature ||--o{ change_control : "close_signature_id"
  change_control ||--o{ change_control_link : "cc_id"
  customer ||--o{ complaint : "customer_id"
  material_batch ||--o{ complaint : "material_batch_id"
  dispatch ||--o{ complaint : "dispatch_id"
  e_signature ||--o{ complaint : "close_signature_id"
  e_signature ||--o{ deviation : "close_signature_id"
  material_batch ||--o{ recall : "material_batch_id"
  e_signature ||--o{ recall : "initiated_signature_id"
  e_signature ||--o{ recall : "close_signature_id"
  recall ||--o{ recall_line : "recall_id"
  dispatch ||--o{ recall_line : "dispatch_id"
  customer ||--o{ recall_line : "customer_id"
  e_signature ||--o{ risk_assessment : "approved_signature_id"
  risk_assessment ||--o{ risk_item : "ra_id"
  department ||--o{ sop : "department_id"
  document ||--o{ sop : "document_id"
  sop ||--o{ sop : "supersedes_id"
  e_signature ||--o{ sop : "approved_signature_id"
  sop ||--o{ sop_acknowledgement : "sop_id"
```

## reporting

```mermaid
erDiagram
  document ||--o{ archive_batch : "document_id"
  backup_record { int id }
  report_run { int id }
  retention_policy { int id }
```

## spec

```mermaid
erDiagram
  material ||--o{ sampling_plan : "material_id"
  sampling_plan ||--o{ sampling_plan : "supersedes_id"
  unit ||--o{ sampling_plan : "unit_id"
  e_signature ||--o{ sampling_plan : "approved_signature_id"
  material ||--o{ specification : "material_id"
  specification ||--o{ specification : "supersedes_id"
  e_signature ||--o{ specification : "approved_signature_id"
  specification ||--o{ specification_parameter : "specification_id"
  stp ||--o{ specification_parameter : "stp_id"
  stp ||--o{ stp : "supersedes_id"
  e_signature ||--o{ stp : "approved_signature_id"
```

## warehouse

```mermaid
erDiagram
  material_batch ||--o{ destruction_record : "material_batch_id"
  location ||--o{ destruction_record : "location_id"
  purchase_order ||--o{ grn : "po_id"
  vendor ||--o{ grn : "vendor_id"
  location ||--o{ grn : "quarantine_location_id"
  grn ||--o{ grn_checklist : "grn_id"
  checklist_item ||--o{ grn_checklist : "item_id"
  e_signature ||--o{ grn_checklist : "exception_signature_id"
  grn ||--o{ grn_line : "grn_id"
  purchase_order_line ||--o{ grn_line : "po_line_id"
  material ||--o{ grn_line : "material_id"
  unit ||--o{ grn_line : "unit_id"
  material_batch ||--o{ inventory_balance : "material_batch_id"
  location ||--o{ inventory_balance : "location_id"
  material_batch ||--o{ inventory_transaction : "material_batch_id"
  location ||--o{ inventory_transaction : "from_location_id"
  location ||--o{ inventory_transaction : "to_location_id"
  unit ||--o{ inventory_transaction : "unit_id"
  material ||--o{ material_batch : "material_id"
  vendor ||--o{ material_batch : "vendor_id"
  unit ||--o{ material_batch : "unit_id"
  specification ||--o{ material_batch : "specification_id"
  sampling_plan ||--o{ material_batch : "sampling_plan_id"
  material_batch ||--o{ material_container : "batch_id"
  material_batch ||--o{ material_label : "material_batch_id"
  location ||--o{ storage_temperature_log : "location_id"
  quality_hold { int id }
```
