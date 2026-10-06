# Purchase Guide (Phase 3)

## The purchase gate — what blocks a PO
A purchase order can be **created, submitted and approved** only if *all* of these hold. They are evaluated at each of those three moments (a vendor that expires while a PO waits for approval blocks the approval).

| Rule | Condition | Block message |
|---|---|---|
| BR-PO-001 | Vendor's current qualification is not past its **requalification due date** (checked live against today's date — does not wait for the nightly job) | **PURCHASE BLOCKED — VENDOR QUALIFICATION EXPIRED.** |
| BR-PO-002 | Vendor master is APPROVED *and* the current qualification is APPROVED or CONDITIONAL (not none / suspended / disqualified / draft) | PURCHASE BLOCKED — VENDOR NOT APPROVED / NOT QUALIFIED |
| BR-PO-003 | An **APPROVED** vendor-material mapping exists for each line (draft/under-review/withdrawn do not count) | PURCHASE BLOCKED — VENDOR NOT APPROVED FOR MATERIAL *code* |
| BR-PO-004 | Each material is **ACTIVE** | |
| BR-PO-005 | An approved, currently effective specification exists for each material | |
| BR-PO-006 | Required vendor documents (by risk class) are approved, current and unexpired | |
| BR-PO-007 | User holds the permission; the PO's creator cannot approve it (SOD-01) | |
| BR-PO-008 | Quantities/rates/tax valid; base unit; no duplicate material; delivery ≥ PO date | |
| BR-PO-010 | *Warning only:* qualification due within 60 days, or CONDITIONAL status | |

There is **no override at PO level.** If a vendor is blocked, QA's route is a controlled **requalification** (a new, signed version with a new due date), or a **conditional** approval with an expiry — both audited and e-signed.
Every blocked attempt is recorded in the security log (`PO_BLOCKED`). Use **Check purchase rules** in the PO form to see all blockers at once without saving.

## Vendor qualification
Draft → Under review → Approved / Conditional → (Suspended / Expired / Disqualified). To submit: qualification date and a future due date, documents required for the risk class approved & unexpired, and for **Critical** vendors a signed quality agreement and an audit. QA Head approves with e-signature (author ≠ approver, SOD-21). Approved qualifications are immutable: *requalify* creates version N+1; approving it supersedes N. Expired qualifications are persisted by the daily job (`scripts/run_jobs.py` or the in-process scheduler `MERP_SCHEDULER_ENABLED=true`, **one instance only**) with alerts at 90/60/30/7 days (configurable `vq.alert_days`). The **Expiry report** lists every vendor with due dates and blocked status (Excel export).

## Approved vendors per material
The *only* source of "which vendors may supply which material". Proposed by Purchase, **approved by QA Head with e-signature** (SOD-20), versioned (new version supersedes), withdrawable with signature + reason. The mapping version used on each PO line is pinned on the line.

## Purchase request → purchase order
PR: Draft → Submitted → *Department approval* (head of the requesting department) → *Purchase review* (Purchase Manager, e-signature) → Approved → Converted. Only ACTIVE materials can be requested. Submitted requests are locked. PO: Draft → Pending approval → Approved → Partially received → Closed (Cancelled/Rejected). Approved POs are locked except for received quantities (updated by GRN). Cancelling an approved PO needs reason + e-signature and is refused once material was received. Each PO line pins the specification version and vendor-material mapping that applied; the header pins the vendor qualification version.
Approval chains are configurable data (Workflows screen); baseline: PR = Department Head → Purchase Manager; PO = Purchase Manager.
