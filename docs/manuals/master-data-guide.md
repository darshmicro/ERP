# Master Data Guide (Phase 2)

## Principles
* **Codes are system-generated** (configurable numbering, e.g. `VEN-00001`, `MAT-00001`, `STP-00001`) and never change.
* **Nothing is deleted.** Records are made inactive/obsolete; approved quality masters are *versioned*.
* **Two-person rule.** The author of a vendor, material, STP, specification or sampling plan cannot approve it (SOD-13…17). Approval needs a fresh e-signature.
* **Reason for every change.** All edits ask for a reason; old and new values are written to the audit trail.

## Lifecycles
| Record | States | Who approves |
|---|---|---|
| Vendor (master record) | Draft → Approved → Inactive (→ Approved) | Purchase Manager / QA Head (e-sign). *Qualification status and re-qualification dates arrive in Phase 3.* |
| Material | Draft → Approved → Active → Obsolete | QA Head (e-sign). Only **Active** materials can be purchased/received (enforced from Phase 3/4). Obsolete = frozen. |
| STP / Specification / Sampling plan | Draft → Under review → Approved → Superseded | QA Head (e-sign). |
| Location, warehouse, equipment, customer, units, types, categories | Active/inactive (audited, reason required) | — |

## Versioned masters (STP, specification, sampling plan)
1. Author creates a **Draft** (number auto-generated), adds parameters, **submits**.
2. QA Head **approves with e-signature**; the version becomes effective *now* and the previous approved version is **superseded** (kept, read-only).
3. An approved version can never be edited. To change it: **Create new version** (reason mandatory) → edit draft → submit → approve. A specification's tests copy forward automatically.
4. Specification test parameters pin the **exact STP version**; an STP referenced by a specification must be Approved.
5. Historical lookups: `GET /materials/{id}/specification-in-force?on=<timestamp>` returns the version that applied at that time (used by sampling/QC so results stay linked to the version they were tested against).

## Vendors & documents
Upload documents per type (GMP certificate, licences, declarations, quality agreement …) with number, version, issue/expiry date. Files are hash-checked (SHA-256), type/size/content validated, stored write-once. A QA reviewer approves/rejects each document (not the uploader). Expired documents are flagged. Replacing a document = uploading a new one; older approved ones stay on record as *not current*.

## Locations
Hierarchy Warehouse → Zone → Room → Rack → Shelf → Bin (a child must be deeper than its parent, in the same warehouse; a node with children cannot be restructured). Per location: temperature/humidity range, capacity, quarantine / rejected-area flags, allowed material categories, and **incompatible category pairs**. `storage-check` reports why a material may not be stored in a location (used by GRN put-away in Phase 4).

## Equipment & calibration
Equipment is *usable for testing/manufacturing* only if Active **and** Qualified **and** calibration is valid (a calibration record with due date ≥ today). A FAIL calibration automatically puts the instrument Out of Service. Calibration history is append-only in practice (records are never edited).

## Controlled Excel import
1. Download the template (includes an *Instructions* sheet) → fill → **Upload & validate**. Nothing is written to master tables.
2. Review the preview/error report (row numbers match Excel). Files with errors cannot be submitted.
3. Uploader **submits**; a QA user with approval authority **approves with e-signature** (never the uploader).
4. Uploader **executes**; the data is re-validated and created all-or-nothing as **Draft** records (still subject to normal approval).
Available: vendor, material, location, STP, specification (BOM import arrives with Phase 6).

## Excel/PDF exports
Master lists export to Excel with report title, generated date/time, filters, user and record count. Sensitive fields (bank account, hashes) are excluded. Every export is audited.
