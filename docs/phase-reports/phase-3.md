# Phase 3 Report — Purchase

## What was implemented
* **Vendor qualification (§10)** — versioned qualification per vendor (Draft → Under review → Approved / Conditional → Suspended / Expired / Disqualified / Superseded). Submission requires qualification date, a future requalification due date, required documents (by risk class, configurable) approved and unexpired, and for *Critical* vendors a signed quality agreement and an audit. QA Head approves/conditionally approves/suspends/disqualifies **with e-signature + reason**, author ≠ approver (SOD-21); approved rows are immutable; **requalification = new version** that supersedes the previous. Live standing evaluation (does not depend on a job having run). Daily job (system actor, idempotent) persists `EXPIRED` and sends alerts at 90/60/30/7 days; in-process scheduler (`MERP_SCHEDULER_ENABLED`) or `scripts/run_jobs.py`. Expiry report + Excel export. Vendor detail shows qualification standing.
* **Vendor–material mapping (§12, decision C-03)** — versioned, QA-approved with e-signature (SOD-20), withdrawable, `approved_to` date, pinned on PO lines.
* **Purchase request (§16)** — Draft → Submitted → Department approved → Approved → Converted (+ Rejected/Cancelled), ACTIVE materials only, department-scoped first approval (new `DEPARTMENT_HEAD` role), purchase review with e-signature, draft-only editing, locked afterwards.
* **Purchase order (§17, §92 rules 1-3)** — the **gate** (BR-PO-001…010) evaluated at **create, submit and approve**; hard blocks with the exact messages (`PURCHASE BLOCKED — VENDOR QUALIFICATION EXPIRED.` etc.), warnings (due ≤ 60 days, conditional), every block logged as a security event, dry-run `validate` endpoint listing all violations. PO pins vendor qualification version, specification version and mapping version per line. Approval chain (configurable; baseline PR: Dept Head → Purchase Manager; PO: Purchase Manager) with e-signature, creator ≠ approver (SOD-01), gate re-run at approval, locked after submission, cancellation (reason; e-signature when approved; refused after receipt), PR→PO conversion with line tracking.
* **Platform:** generalized immutability hook (any status-controlled record can declare editable statuses and mutable fields; child-rows lock with parent — used by PR/PO/lines/qualification/mapping), baseline workflow definitions seeded as configuration, notifications service, scheduler/job runner, departments CRUD, PO/PR/vendor-qualification/mapping lists + Excel exports, dashboard cards (open POs, open PRs, vendor qualification due, pending approvals), `approvals/pending`.
* **Frontend:** Purchase Requests, Purchase Orders (rule check preview with red BLOCK banner, approval chain, e-sign dialogs), Vendor Qualification (+expiry report), Approved Vendors; browser smoke confirmed the block banner appears when the qualification date passes. Fixed a lookup-URL bug found by the smoke test.

## Database
Migration `0003`: `vendor_qualification`, `vendor_material`, `purchase_request`, `purchase_request_line`, `purchase_order`, `purchase_order_line`. 

## API (+39 paths, 150 total)
`/vendor-qualifications*` (create, update, submit, return, approve [conditional], suspend, disqualify, expiry-report[/export]), `/vendors/{id}/purchase-status`, `/jobs/vendor-qualification-expiry`, `/vendor-materials*`, `/purchase-requests*`, `/purchase-orders*` (+`validate`, `from-pr`, `decision`, `cancel`), `/approvals/pending`, `/departments`.

## Tests
* **SQLite: 117 passed.** New: 26 purchase tests covering critical tests 1, 2, 3, 8 and rule 11, gate re-check at approval, immutability of submitted/approved PO/PR/qualification, requalification, job + system-actor audit, SoD for qualification/mapping/PO, PR department scoping, conversion, cancellation, dashboard.
* **SQL Server 2022:** **115 passed** (full suite, 18 min; the 2 SQLite-subprocess migration tests deselected). Migrations `0001→0003` upgrade/downgrade/upgrade verified on a clean SQL Server database (55 tables). No new SQL Server-specific defects this phase.
* Frontend `tsc` + build pass; Playwright smoke: purchase-rule preview OK → BLOCKED after expiry.

## Self-review (§100)
| Question | Result |
|---|---|
| Can expired/unapproved vendors or wrong vendor-material pairs be used? | No — gate at create/submit/approve; tests for each, incl. while a PO waits for approval; no override path exists |
| Can a PO/PR be silently changed after submission? | No — content locked (hook), only controlled fields mutable (workflow ids, received qty) |
| Is the approval independent? | Creator ≠ approver (engine SoD), role + permission, e-signature, approval gate re-run |
| Is there an audit trail of blocked purchases? | `PO_BLOCKED` security events with rule ids; status history; audit |
| Concurrency/atomicity | One transaction per action; numbering atomic; pins resolved inside the transaction |

## Known limitations
1. PO **amendment/revision** is not implemented (cancel and re-issue); receipts/closing arrive with GRN (Phase 4: `received_quantity`, PARTIALLY_RECEIVED/CLOSED transitions are modelled but unused).
2. Required-document rules and thresholds are configuration keys (`po.required_docs.<RISK>`, `vq.alert_days`, …) editable via System configuration; the vendor-document *type* list is fixed in code.
3. Notifications are in-app only (no email sender yet); alerts are generated by the job, delivered to QA/Purchase roles.
4. `DEPARTMENT_HEAD` approval is by role + user department; delegation / substitutes and SLA **escalation** (overdue detection exists, no escalation action) are not built.
5. Vendor *audit scheduling*, supplier scorecards (G-10) and quality-agreement document workflow are deferred; quality-agreement and audit status are vendor-master fields.
6. Per-line PO delivery schedules, multi-currency conversion, and PO printing (PDF with company header) arrive with the report engine (Phase 9). A bare PO export to Excel exists.
7. The in-process scheduler must run in one instance only (no leader election); prefer cron/Task Scheduler for production.
8. SQL Server test runs are slow (~30–60 s per world-building test); consider fixtures with a pre-seeded template database in CI.

## Next: Phase 4 — Warehouse
GRN + configurable checklist (critical-fail block), containers/lots, auto-quarantine, put-away with location compatibility, controlled labels (Code128/QR, print audit), inventory ledger + balances (FEFO/FIFO), quality hold, destruction, temperature log and expiry/retest alerts — wiring PO `received_quantity` and the BR-GRN/BR-QRN/BR-LBL/BR-INV rules.
