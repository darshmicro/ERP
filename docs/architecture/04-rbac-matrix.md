# 04 — RBAC Matrix & Segregation of Duties (Deliverable E)

## 1. Permission model
`permission_code = <module>.<resource>.<action>`; actions: **C**reate, **R**ead, **U**pdate, **D**eactivate (never physical delete of GMP data), **A**pprove, **L** Release, **J** Reject, **E**xport, **P**rint, **S**ign.
Roles are composable; users may hold multiple roles, each with `valid_from/valid_to`, `is_disabled`, site & department scope. Effective permission = union of active roles **minus** SoD conflicts at action time. Admin roles have **no GMP approval permissions** by default (§8).

Cell legend: `CRUD…` letters granted · `—` none · `r` read-only (own dept/site) · `*` plus sign (e-signature) required.
Columns follow §98-E; the "Purchase / QC / QA / Production" columns show **User/Manager-or-Head** where levels differ. Extra roles from §8 (Dispatch, Auditor) added.

| Module | Admin | Purchase (User / Mgr) | Warehouse | QC (Analyst / Head) | QA (Officer / Head) | Production (User / Mgr) | Dispatch | Management | Auditor |
|---|---|---|---|---|---|---|---|---|---|
| Users, roles, permissions, config | CRUDE | — | — | — | r | — | — | — | R |
| Company / numbering / workflow config | CRU (config changes via change control) | — | — | — | A* (workflow CC) | — | — | r | R |
| Audit trail | R E (technical) | — | — | — | R E / R E | — | — | R | R E |
| Backup status / system health | R | — | — | — | — | — | — | — | — |
| Vendor master | — | CRU / CRUA* | r | r | CR / CRUA* | — | — | R | R |
| Vendor qualification | — | R / R | — | — | CRU / **A* L*** (approve, suspend, requalify) | — | — | R | R |
| Vendor–material mapping | — | CR / R | r | R | CRU / A* (via CC) | — | — | R | R |
| Material master | — | r / r | r | CR / CRUA* (QC fields) | CR / A* | r / r | — | R | R |
| Specification, STP, sampling plan | — | r / r | — | CRU / A* (QC review) | CRU / **A*** | — | — | R | R |
| Locations / warehouse master | — | — | CRU | r | R / A* | r | — | R | R |
| Equipment & calibration | — | — | — | CRU / A* | R / A* | r | — | R | R |
| Customer master | — | — | — | — | R / A* | — | CRU | R | R |
| Master data import | CR | CR / A* | CR | CR / A* | CR / A* | CR / A* | CR | — | R |
| Purchase request | — | CRUS* / A* | C | — | — | C (own dept) / A* (dept approval) | — | R | R |
| Purchase order | — | CRU S* / A* S* | R | R | R / R | R | — | R | R |
| GRN / receipt / checklist | — | R | CRU S* | R | R / A* | R | — | R | R |
| Quarantine & storage moves | — | — | CRU | R | R / R | R | — | R | R |
| Labels (print / reprint) | — | — | P (reprint w/ reason) | P | P / P | P | P | — | R |
| Inventory (view, ledger) | — | R | CR (ledger via txns) | R | R / R | R | R | R E | R E |
| Quality hold | — | — | R | CR (propose) / CR | **CJ* / L*** | R | R | R | R |
| Sampling | — | — | R | CRU S* / A* | R / R | C (IPC samples) | — | R | R |
| QC testing / results | — | — | — | CRU S* (own tests) / A* review | R / R | R | — | R | R |
| QC result amendment | — | — | — | C / A* | A* / A* | — | — | — | R |
| Material release (QC→QA) | — | — | R | S* / A* (QC approval) | A* / **A* L* J*** | — | — | R | R |
| Conditional release | — | — | R | R / R | CR / **A* L*** | R (request) / R | — | R | R |
| OOS / OOT | — | — | — | CRU / A* | CRU / **A*** | R | — | R | R |
| BOM | — | — | R | R | R / **A*** | CRU / A* (prod approve) | — | R | R |
| Batch creation / MBR | — | — | R | R | R / A* | CRU S* / A* S* | — | R | R |
| Material indent | — | — | R | — | R | CRS* | — | R | R |
| Material issue | — | — | **C S*** | — | R | R | — | R | R |
| Material return / reversal | — | — | CRS* | — | A* | CR / A* | — | R | R |
| Reconciliation | — | — | R | — | R / A* | CRU S* / A* S* | — | R | R |
| FG release (QC→QA) | — | — | R | S* / A* | A* / **A* L*** | R | R | R | R |
| COA generate / issue | — | — | — | CRP / A* | A* / **L*** | R | R | R | R |
| Dispatch | — | — | R | — | R / A* (exceptions) | R | **CRU S*** / A* (supervisor) | R | R |
| Traceability | — | R | R | R | R | R | R | R | R |
| Deviation | — | C | C | C | CRU / **A*** | C / A* (dept) | C | R | R |
| CAPA | — | C | C | C | CRU / **A*** | C | C | R | R |
| Change control | — | C | C | C | CRU / **A*** | C / A* | — | R | R |
| Risk assessment | — | C | C | C | CRU / A* | C | — | R | R |
| Reports (E/P) | — | E P | E P | E P | E P | E P | E P | E P | E P (read) |
| Dashboards | — | own | WH dash | QC dash | QA dash | own | own | **Mgmt dash** | R |
| Notifications config | CR | — | — | — | CR | — | — | — | — |

The seeded matrix is *data*, editable by Admin (with audit); the table above is the **default seed** and is the basis of access-control OQ tests (Doc 08).

## 2. Segregation-of-duties (SoD) rules (enforced in code + `sod_rule`)

| ID | Rule | Scope | Default |
|---|---|---|---|
| SOD-01 | Creator of a PR/PO cannot approve the same record | record | Block |
| SOD-02 | Analyst who entered a QC result cannot review/approve it | test | Block |
| SOD-03 | QC reviewer ≠ QA releaser for the same lot | lot | Block |
| SOD-04 | Person who raised a deviation/CAPA cannot be sole QA approver | record | Block |
| SOD-05 | Vendor qualification author ≠ approver | record | Block |
| SOD-06 | Requester of conditional release ≠ approver | record | Block |
| SOD-07 | Warehouse issuer ≠ the person who approved the indent (where Production approves) | indent | Block |
| SOD-08 | Requester of QC result amendment ≠ approver | amendment | Block |
| SOD-09 | System Admin cannot hold GMP approve/release permissions *and* user-admin simultaneously (design check at role assignment) | user | Warn + block unless QA-signed exception |
| SOD-10 | User cannot approve own access/role change | user | Block |
| SOD-11 | Batch-number override ≠ batch releaser | batch | Warn |

Each SoD violation attempt writes a `security_event` and a user-facing explanation.

## 3. Access lifecycle controls
* Role assignment requires reason; revocation immediate; **temporary access** with auto-expiry; **quarterly recertification** report for QA.
* Signing requires valid training record for the current SOP version when `training.gate = on` (G-04).
* Failed authorisation attempts are logged (security log) and visible to QA/Admin.
