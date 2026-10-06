# User Requirements Specification (URS)

> Derived from the master requirements (prompt §1–§100) and the architecture pack (`docs/architecture/`). GMP impact: **Critical** = direct effect on product quality, patient safety or data integrity; **Major**; **Minor**.
> Generated from `scripts/validation_requirements.py` — edit that file, not this one.

Total requirements: **71** (47 critical, 22 major, 2 minor).

## Security

| ID | Requirement | GMP impact | Business rules |
|---|---|---|---|
| URS-IAM-01 | Unique user IDs with local or directory (LDAP/AD) authentication; failed attempts are indistinguishable between unknown user and bad password. | Critical | BR-SEC-002 |
| URS-IAM-02 | Account lockout after repeated failures, idle session timeout, forced password change, password policy and history. | Critical | BR-SEC-002 |
| URS-IAM-03 | Role-based access control with least privilege; every endpoint authenticated; permission checked per role (generated matrix). | Critical | BR-SEC-001 |
| URS-IAM-04 | Segregation of duties: administrators hold no GMP authority; users cannot change their own roles; creators cannot approve own records. | Critical | BR-SOD-001 |
| URS-IAM-05 | Session/CSRF protection, secure headers, no credential exposure, injection and upload hardening. | Critical | BR-SEC-001 |

## Audit trail

| ID | Requirement | GMP impact | Business rules |
|---|---|---|---|
| URS-AUD-01 | Secure, time-stamped, field-level audit trail (who/what/when/old/new/reason) written in the same transaction as the change. | Critical | BR-AUD-002 |
| URS-AUD-02 | The audit trail cannot be modified or deleted (ORM, database, API); tampering is detectable through the hash chain. | Critical | BR-AUD-001 |

## E-signature

| ID | Requirement | GMP impact | Business rules |
|---|---|---|---|
| URS-SIG-01 | Electronic signatures require re-authentication, carry printed name/meaning/time, are bound to the record content hash and cannot be edited. | Critical | BR-SIG-001 |
| URS-SIG-02 | Controlled status engine: only legal transitions, permission-gated, history recorded; status columns cannot be written from payloads. | Critical | BR-SEC-001 |

## Workflow

| ID | Requirement | GMP impact | Business rules |
|---|---|---|---|
| URS-SIG-03 | Configurable approval chains with SoD, QA-approved definitions, rejection with reason and versioned definitions. | Major | WF-001 |

## System

| ID | Requirement | GMP impact | Business rules |
|---|---|---|---|
| URS-SYS-01 | Duplicate-free configurable document numbering (concurrency-safe, no reuse). | Major | — |
| URS-SYS-02 | Database schema deploys by versioned migrations (up/down) with append-only protections installed on all supported dialects. | Critical | BR-AUD-001 |

## Master data

| ID | Requirement | GMP impact | Business rules |
|---|---|---|---|
| URS-MD-01 | Vendor master with approval, documents (hash-verified, write-once) and reviewed expiry. | Major | BR-DOC-001 |
| URS-MD-02 | Material master (types, categories, units, shelf life, FEFO mode) with approval and lifecycle. | Major | BR-PO-004 |
| URS-MD-03 | Versioned STP, specification and sampling plan: draft-only editing, QA e-signature approval, supersede, point-in-time lookup. | Critical | BR-HIS-001 |
| URS-MD-04 | Locations with hierarchy, storage compatibility and capacity; equipment with qualification and calibration status. | Major | BR-LOC-001/002 |
| URS-MD-05 | Controlled Excel import with staging, validation and execution only of unchanged validated data. | Major | — |

## Purchase

| ID | Requirement | GMP impact | Business rules |
|---|---|---|---|
| URS-PUR-01 | Vendor qualification (versioned, signed) with expiry job and alerts; requalification keeps history. | Critical | BR-VQ-001..004 |
| URS-PUR-02 | PO is blocked for an expired vendor qualification (critical rule 1). | Critical | BR-PO-001 |
| URS-PUR-03 | PO is blocked for an unapproved / suspended / inactive vendor (critical rule 2). | Critical | BR-PO-002 |
| URS-PUR-04 | PO is blocked for a vendor not approved for the material; mapping is versioned and QA-approved (critical rule 3). | Critical | BR-PO-003, BR-VM-001 |
| URS-PUR-05 | Further PO gates (spec, documents, active material, units, values) evaluated at create, submit and approve with a full violation report. | Major | BR-PO-004..010 |
| URS-PUR-06 | PR and PO approval chains with e-signature, SoD, rejection/cancellation and locked content after submission. | Major | BR-PO-007, BR-PR-001 |

## Warehouse

| ID | Requirement | GMP impact | Business rules |
|---|---|---|---|
| URS-WH-01 | GRN against an approved PO with configurable checklist; critical failure blocks verification unless QA grants a signed exception; second-person verification. | Critical | BR-GRN-001..005 |
| URS-WH-02 | Verified receipt creates a quarantine lot with containers and a ledger receipt; labels (Code128/QR) are controlled and audited. | Critical | BR-QRN-001, BR-LBL-001..003 |
| URS-WH-03 | Quarantine material cannot be issued (critical rule 4). | Critical | BR-ISS-001 |
| URS-WH-04 | Rejected material (critical rule 5) and expired / retest-expired material (critical rule 7) cannot be issued. | Critical | BR-ISS-002, BR-ISS-004 |
| URS-WH-05 | Quality hold blocks issue, use and dispatch; only QA places/releases with e-signature (critical rule 8). | Critical | BR-HOLD-001..004 |
| URS-WH-06 | Authoritative append-only inventory ledger; balances reconcile; no negative stock; concurrency-safe (critical rule 13). | Critical | BR-INV-001..003 |
| URS-WH-07 | FEFO/FIFO pick order, put-away/transfer rules for quarantine/approved/rejected stock, expiry alerts, temperature excursions and controlled destruction. | Major | BR-INV-005/006, BR-TMP-001 |

## QC / LIMS

| ID | Requirement | GMP impact | Business rules |
|---|---|---|---|
| URS-QC-01 | Sampling per plan with ledger sample transaction; tests follow the specification version pinned at sampling. | Critical | BR-SMP-001/002, BR-QC-001 |
| URS-QC-02 | Results evaluated server-side (rounding, inclusive limits), immutable once submitted; amendments retain originals with approval. | Critical | BR-QC-004/005 |
| URS-QC-03 | Instrument calibration gate with controlled QA override. | Critical | BR-QC-002 |
| URS-QC-04 | OOS investigation workflow with automatic hold, retest, QA decision; OOT detection never changes disposition. | Critical | BR-QC-007, BR-STAT-002 |
| URS-QC-05 | Release chain QC → QA with distinct signers, readiness checks, QC/QA numbers, CoA issued only after release. | Critical | BR-REL-001..004, BR-QC-006 |
| URS-QC-06 | Conditional release is a quantity- and batch-bounded QA exception; a batch using it cannot be released until the material is finally approved. | Critical | BR-CRL-001..004 |
| URS-QC-07 | Statistics (Cp/Cpk/Pp/Ppk with explicit status codes, I-MR limits, Nelson rules), trending and sample retention. | Major | BR-STAT-001 |

## Manufacturing

| ID | Requirement | GMP impact | Business rules |
|---|---|---|---|
| URS-MFG-01 | Versioned BOM with MBR steps, QA e-signature approval; only an approved in-force BOM can start a batch and is pinned to it. | Critical | BR-BOM-001/002 |
| URS-MFG-02 | Unique batch numbers with controlled override; cancelled numbers are never reused. | Critical | BR-BAT-001/002 |
| URS-MFG-03 | Material issue only of released, unexpired, unheld, BOM-correct lots; FEFO deviation needs a reason; every issue links lot and batch (critical rule 14). | Critical | BR-ISS-001..007, BR-TRC-001 |
| URS-MFG-04 | Returns require independent acceptance and re-enter stock through the ledger. | Major | BR-RET-001 |
| URS-MFG-05 | Process execution: line clearance signature, ordered steps, second-person verification, equipment gate, IPC failure holds the batch. | Critical | BR-MFG-001..004 |
| URS-MFG-06 | Reconciliation discrepancy is highlighted, raises a deviation and blocks progress until QA accepts it (critical rule 15). | Critical | BR-REC-001 |
| URS-MFG-07 | Output is booked into quarantine and released through the QC/QA chain; antisera donor → bleed → pool genealogy. | Major | BR-ANM-001..003 |

## Dispatch

| ID | Requirement | GMP impact | Business rules |
|---|---|---|---|
| URS-DSP-01 | Unreleased FG cannot be dispatched (critical rule 6); dispatch validated at validate/approve/dispatch with customer and shelf-life rules. | Critical | BR-DSP-001..006 |
| URS-DSP-02 | Dispatch flow with stock reservation, QA e-signature approval (creator ≠ approver), ledger transaction and CoA link. | Critical | BR-DSP-003/006 |

## Traceability

| ID | Requirement | GMP impact | Business rules |
|---|---|---|---|
| URS-TRC-01 | Complete forward and backward genealogy (vendor ↔ PO ↔ GRN ↔ lot ↔ batch ↔ FG ↔ dispatch ↔ customer; animal ↔ pool), global search and QR resolution. | Critical | BR-TRC-001 |
| URS-TRC-02 | Two-level production: only a released SFG lot can feed an FG batch (BR-ISS-001) and the genealogy spans FG batch → SFG batch → raw-material lot → GRN → PO → vendor. | Critical | BR-ISS-001, BR-TRC-001 |

## Quality system

| ID | Requirement | GMP impact | Business rules |
|---|---|---|---|
| URS-QS-01 | Deviation workflow; open deviations block release/dispatch; independent QA closure; automatic deviations from IPC, temperature and reconciliation. | Critical | BR-DEV-001..003 |
| URS-QS-02 | CAPA with actions, effectiveness check, ineffective loop, independent closure. | Major | BR-CAPA-001/002 |
| URS-QS-03 | Change control linked to versioned masters; approval required for new master versions when enabled; SoD. | Critical | BR-CC-001..003, BR-BOM-002, BR-VM-001 |
| URS-QS-04 | FMEA risk assessment with RPN, mitigation/residual risk and signed approval. | Major | BR-RSK-001 |
| URS-QS-05 | SOP control: versions, hashed document, effective dates, periodic review and read-and-understood acknowledgement. | Major | BR-SOP-001/002 |
| URS-QS-06 | Complaints hold critical lots; recall derives affected customers from the dispatch ledger, reconciles returns and requires signed closure. | Critical | BR-CMP-001, BR-RCL-001..004 |

## Reports

| ID | Requirement | GMP impact | Business rules |
|---|---|---|---|
| URS-RPT-01 | Permissioned reports (37) in JSON/XLSX/CSV/PDF with parameter validation and no field leakage. | Major | — |
| URS-RPT-02 | Controlled copies: numbered, hash-logged (append-only), verifiable printouts; controlled business PDFs. | Critical | BR-DOC-001 |
| URS-RPT-03 | Role dashboards and report performance on large ledgers. | Minor | — |
| URS-RPT-04 | Reports, exports and dashboards for environmental monitoring, stability and costing, permission-gated. | Minor | — |

## Data integrity

| ID | Requirement | GMP impact | Business rules |
|---|---|---|---|
| URS-DI-01 | Retention policies (extend-only), legal hold, non-destructive hashed archive packages; records never deleted by the application. | Critical | BR-RET-001/002 |
| URS-DI-02 | Backup and restore evidence with alerts for stale backups / missing restore tests. | Major | — |

## Environmental monitoring

| ID | Requirement | GMP impact | Business rules |
|---|---|---|---|
| URS-EM-01 | Alert/action limits are a controlled, versioned, e-signed master (author cannot approve); reference Annex 1 style values load only as an unapproved draft; no result is judged without an approved limit set. | Critical | BR-EM-001, BR-HIS-001 |
| URS-EM-02 | Each result is judged against the limits in force and the limits are snapshotted on the sample; an action-limit result automatically raises a deviation (critical for grades A/B); alert results notify QA. | Critical | BR-EM-002, BR-DEV-001 |
| URS-EM-03 | Corrections keep the original value (append-only amendment); QA review is e-signed, locks the result and cannot be done by the person who entered it. | Critical | BR-EM-002, SOD-37 |
| URS-EM-04 | Monitoring programme with due/overdue schedule, trending with Nelson-rule signals, excursion listing; only authorised roles can enter results or manage limits. | Major | — |

## Stability

| ID | Requirement | GMP impact | Business rules |
|---|---|---|---|
| URS-STB-01 | Stability protocols (conditions, time points, approved specification) are versioned, e-signed masters; a study can only start from an approved protocol and incomplete protocols cannot be submitted. | Critical | BR-STB-001, BR-HIS-001, SOD-38 |
| URS-STB-02 | Starting a study books the stability sample quantity out of the lot through the inventory ledger and schedules every pull; pulls outside the window need remarks and raise a deviation; missed pulls are marked with a deviation. | Critical | BR-STB-002/003 |
| URS-STB-03 | Results are append-only with superseding corrections; a failing result raises a deviation linked to the lot and blocks the lot like any open deviation; results are reviewed with e-signature by someone other than the analyst. | Critical | BR-STB-004..007, SOD-39 |
| URS-STB-04 | ICH Q1E-style trend evaluation (one-sided 95 % bound, capped extrapolation) supports the QA conclusion; the shelf-life conclusion is e-signed by someone other than the study creator after all pulls close. | Major | BR-STB-008/009, SOD-40 |

## Costing

| ID | Requirement | GMP impact | Business rules |
|---|---|---|---|
| URS-COST-01 | Conversion rates are a controlled, versioned, e-signed rate card; no batch can be costed without an approved card; cost data is visible only to costing/finance, management and audit roles. | Major | BR-COST-003, SOD-41 |
| URS-COST-02 | Actual batch cost is derived from immutable issue/return records at the lot cost (PO rate or approved batch cost), plus labour, machine and overhead; variance to standard is reported; approval is e-signed by someone other than the calculator and locks the cost; the output lot takes the batch cost. | Major | BR-COST-001..005, SOD-42 |
| URS-COST-03 | Lots without a cost basis block costing and are reported (never valued at zero); lot cost history is append-only. | Major | BR-COST-001 |
