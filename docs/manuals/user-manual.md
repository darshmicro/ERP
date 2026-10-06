# User Manual

> The system *supports* GMP and 21 CFR Part 11 controls; compliance depends on your site's procedures and training. Menus show only what your role may do.

## 1. Basics
1. **Log in** with your User ID and password (AD users: your Windows password). 5 wrong passwords lock the account for 15 minutes; after 15 minutes idle you are logged out.
2. **First login:** set a new password (≥ 12 characters, upper/lower case, digit, symbol, not reused, not containing your name).
3. **Reasons:** any change to controlled data asks for a reason. It is recorded with your name, role, time and IP in the audit trail.
4. **Electronic signature:** where a record needs approval you re-enter your password and give a reason. The signature (printed name, meaning, date/time) is permanently linked to the record content.
5. **You cannot approve what you created or tested** (segregation of duties); the system tells you which rule applies. A **rule message** (e.g. *PURCHASE BLOCKED — VENDOR QUALIFICATION EXPIRED.*) means the action is not allowed — it is logged.
6. **Errors:** a reference such as `ERR-2026-000123` identifies a system fault — quote it to the administrator.
7. **Search:** the box at the top finds lots, batches, GRNs, POs, dispatches, vendors, materials, customers and pools; typing a label's QR text (`merp://lot/<no>`) opens the record's trace.
8. **Printouts:** every PDF/Excel export carries a **controlled-copy number** and is logged; a printout is a copy, the system record is the original.

## 2. Purchase (Purchase user / manager, Department head)
* **Vendor qualification:** QA qualifies vendors (date, due date, documents, audit); status Approved/Conditional/Suspended/Expired. *Approved Vendors* shows the vendor × material list.
* **Purchase request:** create → submit → department head approves → purchase review → convert to PO.
* **Purchase order:** the *rule check* shows every blocking rule before you submit (vendor qualification valid, vendor approved for the material, material active, approved specification, vendor documents). A manager (not the creator) approves with e-signature. *Purchase order (PDF)* prints the controlled order.

## 3. Warehouse
* **GRN:** choose the PO, enter vendor batch, quantity, packs, dates, CoA received; submit. A **second person** completes the checklist (critical items marked *) and verifies with e-signature; lots go to QUARANTINE with labels. A critical "No" blocks verification unless QA grants a documented exception.
* **Inventory & Lots:** stock by lot/location with status (QUARANTINE, QC testing, APPROVED, HOLD, EXPIRED, RETEST DUE); lot detail shows the **ledger** and reconciliation. Transfer/put-away follows quarantine/approved/rejected rules. **Holds** are placed by QA and released by the QA Head with signature. **Destruction** needs QA Head approval. Print **labels** (reprint needs a reason).
* **Temperature:** record readings per location; an excursion holds all lots stored there and raises a deviation.

## 4. QC / QA
* **Samples & tests:** sample (quantity ≤ available, per sampling plan) → assign tests from the specification version in force at sampling → analyst starts (calibrated equipment required) → enter results (pass/fail evaluated by the system) → submit. Submitted results cannot be edited; request an **amendment** (original kept, approval + signature).
* **OOS / OOT:** a failing result raises an OOS, holds the lot, and opens the investigation (phase I/II, retest, QA decision). OOT warnings never change disposition.
* **Release:** QC analyst submits → QC Head → QA Officer → QA Head (each signs, all different people). The lot becomes APPROVED, the **CoA** is generated, approved labels may be printed. Open deviations/holds/OOS block release.
* **Conditional release:** QA Officer requests, QA Head approves a quantity-, date- and batch-bounded use of unreleased material; the batch cannot be released until that material is finally approved.
* **Trends / Cpk:** control charts, Nelson rules, capability with explicit status codes.

## 5. Manufacturing (Production user / manager)
* **BOM:** author → submit → QA Head approves (new version for any change). **Batch:** choose the product and planned quantity; the approved BOM is pinned; requirements are scaled.
* **Issue** (warehouse): pick list shows FEFO order; only released, unexpired, unheld lots of the right material; deviating from FEFO needs a reason. **Return:** requested by production, accepted by warehouse (re-enters via quarantine rules).
* **Process:** *Line clearance & start* (signature) → record steps in order (critical steps verified by a second person with signature) → record equipment use and IPC results (a failing IPC holds the batch and raises a deviation) → *Complete production*.
* **Reconciliation:** enter consumed/sampled/waste → *Reconcile*. Out-of-tolerance lines are red; production approves, then QA Head accepts the deviation with signature before output is booked. **Output** goes to a quarantine location and into QC/QA release. *Batch record (PDF)* prints the full eBR.
* **Antisera:** register animals, record immunisations (append-only) and bleeds (minimum interval enforced), create plasma pools (genealogy kept).

## 6. Dispatch
Create a dispatch from released FG stock; *Validate* reserves stock and runs the rules (released, not held, not expired, customer authorised and licence valid, quantity available, CoA present); QA approves with signature; the dispatcher *Dispatches* (rules re-checked, ledger posted); mark *Delivered*. *Dispatch note (PDF)* prints the document.

## 7. Traceability
*Traceability* → choose the type (lot, batch, dispatch, GRN, PO, vendor, customer, pool, animal) and number → graph and table, **backward** (what is it made of / who supplied it) or **forward** (where did it go). Use for recalls and investigations.

## 8. Quality system
* **Deviation:** raise (anyone) → investigation (root cause, impact) → CAPA proposed → QA review → QA Head closes with signature (not the raiser). Linked open deviations block release and dispatch.
* **CAPA:** actions with owners/dates → effectiveness check → QA Head closes. **Change control:** assess → QA Head approves → implement (link the new draft master version) → effectiveness → close.
* **Risk (FMEA):** score S/O/D, RPN levels, mitigation and residual risk; QA Head approves. **SOPs:** read the current approved version and press *I have read and understood*. **Complaints:** record; critical ones hold the lot. **Recall:** QA Head initiates (lot held, affected customers listed), track notification and returns, close with signature.

## 9. Reports and dashboards
*Reports* lists the reports you may run (filters, preview, Excel/CSV/PDF with controlled-copy number). *Dashboards* give role views (Management, QC, QA, Warehouse). Typical reports: stock status/ledger, expiry forecast, quarantine ageing, QC pending, OOS register, batch register/reconciliation, dispatch register, deviation/CAPA registers, audit trail and e-signature log (QA/auditor).
