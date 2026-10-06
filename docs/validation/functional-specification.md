# Functional Specification (FS)

Describes *what* the system does per module and links each function to URS items, business rules and the detailed phase reports. The architecture pack (`docs/architecture/`) holds the authoritative workflows (05), rules (07), RBAC (04) and compliance mapping (06).

| Module | Functions (summary) | URS | Detailed description |
|---|---|---|---|
| **Platform / IAM** | Local + LDAP/AD login, lockout, idle timeout, password policy/history, RBAC with SoD, role assignment with reason, user lifecycle, training records, access expiry; error references; secure headers | IAM, SYS | phase-1 |
| **Audit trail & e-signature** | Field-level audit in the same transaction, HMAC hash chain with verify, DB triggers on append-only tables, reason enforcement; re-authenticated e-signatures bound to a record hash and manifest | AUD, SIG | phase-1, `10-audit-trail-spec`, `11-electronic-signature-spec` |
| **Workflow & status engine** | Legal-transition state machines, approval chains (role, e-signature, SLA), versioned definitions with QA approval | SIG-02/03 | phase-1 |
| **Master data** | Units, material types/categories, materials, vendors (+documents), locations/warehouses, equipment/calibration, customers, controlled Excel import, documents (hash-verified, write-once), versioned STP / specification / sampling plan / BOM / vendor–material / SOP | MD | phase-2 |
| **Purchase** | Vendor qualification (versioned, expiry job and alerts), vendor–material approval, PR (department approval), PO with gate rules at create/submit/approve, pins of specification/qualification/mapping | PUR | phase-3 |
| **Warehouse** | GRN with configurable checklist and QA exceptions, lots and containers, quarantine, put-away/transfer rules, append-only inventory ledger and balances, FEFO/FIFO, quality holds, labels (Code128/QR), temperature log, destruction, expiry jobs | WH | phase-4 |
| **QC / LIMS** | Sampling per plan, pinned specification, tests and results (server-side evaluation), amendments, calibration gate, OOS/OOT, statistics, release chain, CoA (PDF/XLSX), conditional release, sample retention | QC | phase-5 |
| **Manufacturing** | BOM + MBR, batches (numbering/override), indent, issue/return with gates, line clearance, step execution/verification, equipment, IPC, reconciliation, output to quarantine; antisera donor/bleed/pool | MFG | phase-6 |
| **Dispatch & traceability** | Dispatch lifecycle with reservation and gates, customer rules, CoA link; forward/backward genealogy graph, global search, QR resolve | DSP, TRC | phase-7 |
| **Quality system** | Deviation, CAPA, change control wired to versioned masters, FMEA, SOP control with acknowledgement, complaints, recall | QS | phase-8 |
| **Reports & compliance** | 37 reports (JSON/XLSX/CSV/PDF), controlled copies, business PDFs, dashboards, retention/legal hold/archive, backup evidence | RPT, DI | phase-9 |
| **Validation tooling** | Generated RTM/URS/CS/data dictionary/access matrix, demo data, load and restore scripts | — | phase-10 |

## Interfaces
* **Browser UI** (React/TypeScript/Bootstrap) over HTTPS; **REST API** `/api/v1` (OpenAPI at `/api/openapi.json`; export committed as `docs/api/openapi.json` on release).
* **Database:** SQL Server (primary), PostgreSQL (best effort), SQLite (development/test only).
* **Directory:** LDAP/AD optional (LDAPS), fail-closed.
* **Files:** document store on the application server (hash-verified); Excel (openpyxl) import/export; PDF (reportlab).
* No instrument or ERP/finance interfaces in v1.

## Roles
Defined in `access-control-matrix.md` (generated from the seed) and `docs/architecture/04-rbac-matrix.md`.
