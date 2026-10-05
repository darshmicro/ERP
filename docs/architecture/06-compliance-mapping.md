# 06 — GMP Compliance Mapping (Deliverable G)

> **Reading guide.** "Software capability" = what the code provides. "Site responsibility" = what must be done by the company (validation, SOPs, infrastructure, people). **Nothing here claims the software is Part 11 "compliant" on its own.**

## 1. 21 CFR Part 11

| Clause | Requirement (summary) | Software capability | Site responsibility |
|---|---|---|---|
| 11.10(a) | Validation of systems | Validation pack, traceable tests, deterministic builds, versioned releases | Execute CSV/CSA, approve reports, maintain validated state |
| 11.10(b) | Accurate, complete copies of records | PDF/Excel/CSV exports with metadata; controlled copy numbering; hash on documents | Define copy/retrieval SOP |
| 11.10(c) | Record protection / retrieval | Soft-delete only, retention policies, archive retrieval, backup tools | Retention schedule, backup execution, restore tests |
| 11.10(d) | Limit access to authorised individuals | Unique users, RBAC, site/department scope, access expiry, lockout | User provisioning SOP, periodic access review |
| 11.10(e) | Secure, time-stamped audit trails | Immutable `audit_trail` with who/what/when/old/new/reason; DB grants + triggers + hash chain | NTP time source, audit-trail review SOP |
| 11.10(f) | Operational system checks | Status engine / workflow enforcement of sequence | — |
| 11.10(g) | Authority checks | Permission + SoD + training gate at service layer | Define authority matrix |
| 11.10(h) | Device checks | Instrument calibration status gate; input validation | Calibrate/qualify devices |
| 11.10(i) | Education/training | Training record gate for signers | Provide and record training |
| 11.10(j) | Accountability policies | Signature meanings, no shared accounts (unique ID enforced) | Written policy; user attestation |
| 11.10(k) | Documentation control | Versioned docs, change control module | SOP control |
| 11.30 | Open systems controls | TLS, encryption at rest, signature hashing | Network design (system is intended as closed) |
| 11.50 | Signature manifestations | Printed name, date/time (TZ), meaning shown on screen and PDF | — |
| 11.70 | Signature/record linking | `e_signature.record_hash` + version FK; cannot be detached/copied | — |
| 11.100 | Uniqueness, identity verification | Unique ID never reused; re-auth on sign | Identity verification at onboarding; FDA signature certification letter |
| 11.200 | Signature components | User ID + password (or AD) at every signing; lockout | Password SOP |
| 11.300 | Controls for IDs/passwords | Complexity, ageing, history, lockout, deactivation, loss management | Process for lost tokens/credentials |

## 2. EU GMP Annex 11 (computerised systems)

| Annex 11 § | Topic | Software capability | Site responsibility |
|---|---|---|---|
| 1 | Risk management | Risk-assessment module; risk rating drives validation depth | Lifecycle risk assessments |
| 2 | Personnel | Role/training gate | Qualified personnel |
| 3 | Suppliers/service providers | Vendor module, SBOM/dependency list | Supplier agreement |
| 4 | Validation | Validation pack & traceability matrix | Validation execution |
| 5 | Data (interfaces) | Validated import, checksum on file import | Interface verification |
| 6 | Accuracy checks | Range/limit checks, calculations unit-tested | Verify critical calculations |
| 7 | Data storage | Backup, DB constraints, hash on docs | Backup & restore verification |
| 8 | Printouts | Controlled PDFs showing meaning & timestamps | Printout SOP |
| 9 | Audit trails | Full audit; review tooling | Periodic review |
| 10 | Change & configuration management | Change control module; versioned configuration; migrations | Change SOP |
| 11 | Periodic evaluation | Reports: access, audit, deviations, incidents | Periodic review |
| 12 | Security | Authn, RBAC, session, security log | Physical/network security |
| 13 | Incident management | Error references, security events, deviation link | Incident SOP |
| 14 | Electronic signature | See Part 11; signature linked & timed | Equivalence to handwritten policy |
| 15 | Batch release | QA release workflow & signature; FG release gate | Qualified Person/QA authority |
| 16 | Business continuity | Backup/DR docs, RPO/RTO | DR drills |
| 17 | Archiving | Archive & retrieval design | Archive facility |

Annex 15 (qualification/validation): equipment/instrument qualification and calibration status managed in MD-EQP; validation documentation templates in Doc 08. Annex 1: environmental/sterile controls are *recorded* (IPC: sterility, endotoxin) but EM/utilities modules are out of v1 scope (G-06).

## 3. ALCOA+

| Principle | Implementation |
|---|---|
| **Attributable** | Unique user, role and (where required) e-signature on each record/audit row |
| **Legible** | Structured data, standard PDFs; no free-form overwritten values |
| **Contemporaneous** | Server-generated UTC timestamps; users cannot set transaction time; back-dated GMP entries require reason (and are flagged) |
| **Original** | Original results immutable; amendments separate; first-capture retained |
| **Accurate** | Server validation, limits, calc tests, units |
| **Complete** | Mandatory fields, no orphan records (FKs), complete audit incl. deletes attempts |
| **Consistent** | Single time-source, single sources of truth (C-03, C-05), sequence controls |
| **Enduring** | Retention policy, archival, backups |
| **Available** | Search, reports, exports, audit access for inspectors (Auditor role) |

## 4. GMP / GDP / data-integrity control mapping

| Control objective | Mechanism |
|---|---|
| Prevent use of unapproved material | BR-ISS gates, lot disposition state machine, DB trigger on status transitions |
| Prevent purchase from unqualified supplier | BR-PO-001..006 at create + approve |
| Prevent release without independent review | SoD-02/03, workflow chain |
| Prevent mix-ups | Barcode/QR labels, scan-to-verify on issue and receipt, label reconciliation (G-09), location compatibility |
| Traceability | Mandatory FK chain; genealogy views; Doc 07 BR-TRC |
| No silent data change | Immutable results/amendments, VER masters, audit triggers |
| Data availability & retention | Retention policies, backups, no audit deletion |
| Controlled change | Change control linked to master-data versions |
| Security of records | RBAC, TLS, encryption, hashing |
| Periodic review | Audit-trail review tasks, access recertification, ledger verification |
