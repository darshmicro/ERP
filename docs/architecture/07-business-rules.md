# 07 — Business Rules Catalogue (Deliverable H)

Types: **B** = hard block · **A** = requires approval/signature · **W** = warning · **N** = notification.
Every rule has a stable ID, a unit test, and logs violations to the security/GMP log (rule ID + user + record).

## 1. The 15 critical rules (§92)

| § | Rule | Enforced by IDs |
|---|---|---|
| 1 | Expired vendor qualification → block PO | BR-PO-001 |
| 2 | Unapproved vendor → block PO | BR-PO-002 |
| 3 | Vendor not approved for material → block PO | BR-PO-003 |
| 4 | Quarantine material cannot be issued | BR-ISS-001 |
| 5 | Rejected material cannot be issued | BR-ISS-002 |
| 6 | Unreleased FG cannot be dispatched | BR-DSP-001 |
| 7 | Expired material cannot be issued/used | BR-ISS-004 |
| 8 | Quality hold blocks issue/use/dispatch | BR-HOLD-001..003 |
| 9 | Audit trail cannot be modified/deleted | BR-AUD-001 |
| 10 | E-signature required for configured actions | BR-SIG-001 |
| 11 | Creator cannot approve own transaction | BR-SOD-001 |
| 12 | Historical GMP records never overwritten | BR-HIS-001 |
| 13 | Every movement creates inventory txn | BR-INV-001 |
| 14 | Issued material linked to mfg batch | BR-TRC-001 |
| 15 | Reconciliation discrepancy highlighted | BR-REC-001 |

## 2. Purchase / vendor

| ID | Rule | Type |
|---|---|---|
| BR-PO-001 | PO create **and** approve: vendor qualification effective row must have status Approved/Conditional and `today ≤ requalification_due_date` (or conditional expiry). Message: *"PURCHASE BLOCKED — VENDOR QUALIFICATION EXPIRED."* | B |
| BR-PO-002 | Vendor approval_status = Approved and not Suspended/Disqualified | B |
| BR-PO-003 | Active `vendor_material` (approved, in date) must exist for each line's material + vendor | B |
| BR-PO-004 | Material `master_status = Active` | B |
| BR-PO-005 | Approved, effective specification exists for the material | B |
| BR-PO-006 | Required vendor documents present and not expired (per vendor risk class; configurable doc set) | B |
| BR-PO-007 | User holds `po.order.create`; approver ≠ creator | B |
| BR-PO-008 | PO values (qty>0, rate≥0, tax valid, delivery ≥ PO date) | B |
| BR-PO-009 | Rule results snapshot stored on PO (`validation_snapshot_json`) | – |
| BR-PO-010 | Vendor qualification due in ≤ 60 days at PO time | W |
| BR-PR-001 | PR cannot convert to PO unless Approved | B |
| BR-VQ-001 | Only QA roles may change qualification status; signed with reason | A |
| BR-VQ-002 | Requalification creates a **new version**; old retained | B |
| BR-VQ-003 | Critical vendors require quality agreement + audit report to be Approved | B |
| BR-VQ-004 | Nightly job expires qualifications past due; notifies at 90/60/30/7 d | N |
| BR-VM-001 | Vendor–material mapping change only via change control | A |

## 3. Receipt / quarantine / storage

| ID | Rule | Type |
|---|---|---|
| BR-GRN-001 | GRN requires an approved PO line; received qty ≤ ordered + over-delivery tolerance | B (tolerance cfg) |
| BR-GRN-002 | Vendor on GRN must equal PO vendor | B |
| BR-GRN-003 | Mfg date ≤ expiry; expiry in the future; retest ≤ expiry | B |
| BR-GRN-004 | Any **critical** checklist item = "No" blocks Verify (QA exception path with deviation) | B/A |
| BR-GRN-005 | Vendor still qualified at receipt time (else receipt flagged, goes HOLD) | W→HOLD |
| BR-QRN-001 | GRN Verified → lot auto `QUARANTINE`; location must be a quarantine-type location | auto |
| BR-LOC-001 | Location must allow material category and storage condition; incompatibility rule check | B |
| BR-LOC-002 | Capacity not exceeded | B/W |
| BR-LBL-001 | Quarantine label generated on lot creation; label numbering/versioned template | auto |
| BR-LBL-002 | Every print/reprint audited; reprint requires reason; approved labels only for APPROVED lots | B |
| BR-LBL-003 | Copies limit configurable (default 1–10) | B |
| BR-TMP-001 | Temperature excursion logged ⇒ auto HOLD + deviation prompt | B |

## 4. QC / release

| ID | Rule | Type |
|---|---|---|
| BR-SMP-001 | Sampling quantity ≤ available qty of the lot; creates SAMPLE ledger txn | B |
| BR-SMP-002 | Sampling plan version pinned to sample | – |
| BR-QC-001 | Test uses specification version pinned at sample creation | B |
| BR-QC-002 | Equipment calibration valid at test completion; else block or QA override (C-14) | B/A |
| BR-QC-003 | STP version must be effective on test date | B |
| BR-QC-004 | Results auto Pass/Fail computed server-side vs. limits (with decimals/rounding rule) | auto |
| BR-QC-005 | SUBMITTED result immutable; correction via amendment w/ reason + approval + signature | B |
| BR-QC-006 | Analyst ≠ reviewer ≠ QA releaser (SoD-02/03) | B |
| BR-QC-007 | Failing result auto-creates OOS record and sets lot HOLD/UNDER_INVESTIGATION flag | auto |
| BR-REL-001 | Release requires all required tests Submitted + Passed + QC reviewed | B |
| BR-REL-002 | Release requires all required GRN documents (COA etc.) verified | B |
| BR-REL-003 | QA release requires signature (meaning *QA Released*); generates QA release no. | A |
| BR-REL-004 | REJECTED lots can never go to APPROVED without OOS/Investigation reversal approved by QA Head | A |
| BR-STAT-001 | Cpk only if n ≥ min_n, spec limits exist, σ > 0; else explicit status | B |
| BR-STAT-002 | OOT/alert does not change disposition unless configured rule says so | – |
| BR-CRL-001 | Conditional release: QA approval, justification, risk-assessment ref, identity confirmation, qty, intended mfg batch, expiry/retest check, signature | A |
| BR-CRL-002 | Not allowed for REJECTED/HOLD/UNDER_INVESTIGATION/expired lots | B |
| BR-CRL-003 | Consumption limited to authorised qty and mfg batch; mark batch "USED UNDER QA-AUTHORIZED CONDITIONAL RELEASE" | auto |
| BR-CRL-004 | FG batch release blocked until conditional material final disposition = Approved | B |

## 5. Inventory / hold

| ID | Rule | Type |
|---|---|---|
| BR-INV-001 | Any quantity or location change is an `inventory_transaction`; no direct balance edit | B |
| BR-INV-002 | No negative stock | B |
| BR-INV-003 | Ledger and balance reconcile nightly; drift raises alert | N |
| BR-INV-004 | Corrections by REVERSAL/ADJUST with reason + signature, original untouched | A |
| BR-INV-005 | FEFO default for expiry-bearing materials (FIFO configurable per material) | W/B (cfg) |
| BR-INV-006 | Near-expiry/retest-due/expired alerts (default 90/60/30 d) | N |
| BR-HOLD-001 | Held lot/batch cannot be issued | B |
| BR-HOLD-002 | Held batch cannot be used in production | B |
| BR-HOLD-003 | Held FG cannot be dispatched | B |
| BR-HOLD-004 | Only QA can place/release hold; release signed | A |

## 6. Manufacturing

| ID | Rule | Type |
|---|---|---|
| BR-BOM-001 | Only Approved & effective BOM version can start a batch; pinned to batch | B |
| BR-BOM-002 | BOM change via change control; new version | A |
| BR-BAT-001 | Batch number unique per site; override permission + reason | B |
| BR-BAT-002 | Voided numbers retained, never reused | B |
| BR-ISS-001 | Lot disposition QUARANTINE/QC_TESTING/QA_REVIEW → not issuable (except BR-CRL) | B |
| BR-ISS-002 | REJECTED not issuable | B |
| BR-ISS-003 | Material of lot = material required by BOM line; location holds stock; qty ≤ available | B |
| BR-ISS-004 | Expired or retest-expired lot not issuable | B |
| BR-ISS-005 | FEFO/FIFO deviation requires reason (signed if configured) | A |
| BR-ISS-006 | Issued qty ≤ required + overage unless approved additional issue | B/A |
| BR-ISS-007 | Issue irreversible; only via Return/Reversal workflow | B |
| BR-TRC-001 | `material_issue` must reference both `material_batch` and `manufacturing_batch` (NOT NULL FKs) | B |
| BR-MFG-001 | Equipment used must be calibrated/qualified and clean (status) | B |
| BR-MFG-002 | Line clearance signed before processing | A |
| BR-MFG-003 | IPC out-of-limit raises OOS/deviation | auto |
| BR-REC-001 | Reconciliation required; variance > tolerance ⇒ highlight, block QA review until deviation approved | B |
| BR-RET-001 | Return qty ≤ issued − used; returned stock re-enters as QUARANTINE (or per policy) | B |

## 7. FG / dispatch

| ID | Rule | Type |
|---|---|---|
| BR-FGR-001 | FG available only after QC review + QA release (signature) | B |
| BR-FGR-002 | COA generated only after QA release; versioned | auto |
| BR-DSP-001 | Batch released (QA) | B |
| BR-DSP-002 | Not expired (and sufficient remaining shelf-life per customer policy) | B/W |
| BR-DSP-003 | Qty ≤ available FG stock | B |
| BR-DSP-004 | No quality hold, no open OOS/deviation blocking | B |
| BR-DSP-005 | Customer active & authorised for product where licensing applies | B |
| BR-DSP-006 | Dispatch creates ledger txn; links customer/invoice/COA | auto |

## 8. System / platform

| ID | Rule | Type |
|---|---|---|
| BR-AUD-001 | No UPDATE/DELETE on audit; app role has no such grant | B |
| BR-AUD-002 | Business change and audit write share one transaction | B |
| BR-SIG-001 | Configured actions require fresh re-auth signature; wrong password counts as failed login | B |
| BR-SOD-001 | Creator ≠ approver (see Doc 04 SoD table) | B |
| BR-HIS-001 | Approved versioned records immutable; transactions FK to the exact version | B |
| BR-SEC-001 | Status columns not writable from API payloads | B |
| BR-SEC-002 | Lockout after N failures; session timeout; no shared accounts | B |
| BR-DOC-001 | Documents write-once; replacement creates new version; hash verified on download | B |
| BR-RET-001/002 | No deletion of GMP records without approved retention policy; legal hold | B |
