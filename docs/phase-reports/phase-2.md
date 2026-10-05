# Phase 2 Report — Master Data

## What was implemented
* **Lookups:** units (+conversions), material types, categories — admin-managed, audited, reason required.
* **Vendor master** (all §9 fields; bank account redacted in audit/exports/API), approval lifecycle (Draft→Approved→Inactive) with e-signature and SOD-13, **vendor documents** (20 configurable types; number/version/issue/expiry; QA review; uploader≠reviewer SOD-19; hash-verified write-once storage; expiry flag).
* **Material master** (all §11 fields; generated code + barcode value; temperature/humidity/shelf-life/retest validation), lifecycle Draft→Approved→Active→Obsolete with QA e-signature and SOD-14; Obsolete is frozen; status/code not patchable.
* **Versioned quality masters:** STP, Specification (+test parameters with LSL/USL/target/limits/alert & action limits, STP pinned by version), Sampling plan. Draft→Under review→Approved→Superseded, QA e-signature, SOD-15/16/17, **approved versions immutable (ORM-hook enforced)**, new-version copies content forward, history, point-in-time `specification-in-force`.
* **Warehouse/location hierarchy** (Zone>Room>Rack>Shelf>Bin), temperature/humidity/capacity, quarantine/rejected flags, allowed categories, incompatible-category rules, `storage-check`.
* **Equipment & calibration:** status, qualification, calibration history; `usable_for_testing` gate (status + qualification + calibration validity); FAIL → out of service.
* **Customers** (licence/authorisation), **documents** attach/download (audited, SHA-256 verified), **Excel export** with report header and audit, **controlled Excel import** (vendor, material, location, STP, specification): staging → validation → preview → error report → submit → QA e-sign approval → uploader executes → records created as DRAFT; re-validated at execution.
* **Platform additions:** `VersionedMixin`/`VersionChildMixin` + hook (BR-HIS-001), master numbering (non-resetting `VEN-00001` style), additive permission/role seeding that never undoes admin changes, `crud_router` factory.
* **Frontend:** Materials, Vendors (+documents), Specs/STPs/Sampling plans (versions, parameters, e-sign), Warehouses/Locations, Equipment (+calibration), Customers, Units/Types/Categories, Excel Import; all with search, filters, pagination, Excel export, reason/e-signature dialogs. Browser smoke: QA Head approves a material with e-signature end-to-end.

## Database changes
Migration `0002`: 21 tables — unit, unit_conversion, material_type, category, vendor, vendor_document, material, customer, warehouse, location, location_category, location_compat_rule, equipment, calibration, stp, specification, specification_parameter, sampling_plan, doc_link, import_job, import_row. (+ 0001 amendments: `DATETIME2(6)` on SQL Server, `audit_chain_head.id` non-identity.)

## API (+75 paths, 111 total)
`units`, `unit-conversions`, `material-types`, `categories`, `customers`, `warehouses`, `locations` (+`storage-check`, `export`), `location-compat-rules`, `equipment` (+`status`, `calibrations`), `vendors` (+`approve`, `deactivate`, `documents`, `export`), `vendor-documents/{id}/review`, `materials` (+`approve|activate|obsolete`, `export`, `specification-in-force`), `stps|specifications|sampling-plans` (+`submit|return|approve|new-version`, parameters), `imports` (+templates, preview, error-report, submit, decision, execute), `documents`.

## Tests
* **SQLite: 91 passed. SQL Server 2022 (Docker): 89 passed** (full suite incl. versioning, import, audit chain, RBAC). Alembic up/down/up and least-privilege grants verified manually on SQL Server — see `docs/validation/sqlserver-verification.md`.
* Frontend `tsc` + build pass; Playwright smoke (login → materials → e-signature approval) passed.
* **SQL Server verification found and fixed 4 real defects** (boolean predicates, reserved word `rule`, DATETIME rounding breaking audit hash verification, identity on chain head) — evidence that the earlier "authored but not run" caveat was worth closing.

## Self-review (§100)
| Question | Result |
|---|---|
| Records silently changed? | Approved versions immutable (tests: PATCH → 409 BR-HIS-001; parameters add/edit/delete blocked); edits need reasons and are audited old→new |
| Approvals bypassable? | Author≠approver for vendor/material/STP/spec/plan/import/vendor-document; e-sign re-auth; permission per action; statuses not writable via payload |
| Unauthorised data access? | Admin has no business-data read; roles per Doc 04; sensitive fields excluded from API/exports |
| Import bypass? | Staging only; QA approval; uploader-only execute; re-validation; all-or-nothing |
| Referential integrity | FKs + friendly FK/unique pre-checks; unique codes and (number, version) |
| Usability | List/search/filter/export on every master; lookup dropdowns in forms |

## Known limitations
1. **No Material-to-Vendor mapping, vendor qualification, or purchase rules yet** (Phase 3). Material "approved vendors" will be the versioned `vendor_material` table (design decision C-03).
2. Change control for approved *non-versioned* masters (material critical fields, vendor) is reason+audit only; the Change Control module (Phase 8) will gate these. Material/vendor are not version-rows (they keep a full field-level audit history instead).
3. Sample master & sample types (§15) are deferred to Phase 5 with the QC module. Product master and BOM import arrive with BOM (Phase 6). UI shows type/unit as ids in the material detail pane.
4. Excel import covers 5 entities; location import requires parents earlier in the file; specification import creates one draft per material.
5. `current_occupancy` on locations is informational until inventory (Phase 4). Location capacity/compatibility checks are advisory functions now and become blocking in GRN put-away.
6. PostgreSQL still untested. Lock behaviour under concurrent load on SQL Server not yet load-tested (Phase 10). Test suite is slow on SQL Server (~6 s/test).
7. Equipment `usable_for_testing` is computed but not yet enforced anywhere (enforced in QC/manufacturing phases).

## Next: Phase 3 — Purchase
Vendor qualification (documents, risk class, status machine, requalification with new versions, nightly expiry job), vendor–material mapping (versioned, change-controlled), purchase request and purchase order with the blocking rules BR-PO-001…010 re-checked at create and approve, workflow chains and tests for critical cases 1, 2, 3, 8, 11.
