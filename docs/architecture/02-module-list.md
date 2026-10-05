# 02 — Module List (Deliverable B)

Legend: **P#** = roadmap phase (see Doc 09). Prompt § = originating requirement.

| Code | Module | Key capabilities | Prompt § | Phase |
|------|--------|------------------|----------|-------|
| **CORE** | Platform core | Config, numbering, status engine, workflow engine, rule engine, event bus, error/logging, i18n, time/TZ | 54,55,61,62,63 | 1 |
| **IAM** | Identity & Access | Users, roles, permissions, department/designation/site, access expiry, temp-disable, AD/LDAP + local, sessions, lockout, password policy, training gate, access recertification | 3,8,56 | 1 |
| **ORG** | Company/Organization | Company, site/plant, logo, headers/footers, licences, formats, label/report formats | 4 | 1 |
| **AUD** | Audit trail | Immutable audit, search/filter/export, hash-chain verify, audit review | 7 | 1 |
| **ESIG** | Electronic signatures | Re-auth signing, meanings, manifest, linking | 6 | 1 |
| **DASH** | Dashboards & home | Management, QC, QA, Warehouse, role home | 49,90 | 1 (shell) → 9 |
| **MD-VEN** | Vendor master | Vendor CRUD (versioned), risk, criticality | 9 | 2 |
| **MD-MAT** | Material master | Types/categories/units, material, storage conditions, QR | 11 | 2 |
| **MD-SPEC** | Specification & STP & Sampling plan | Versioned specs/params, STP, sampling plans | 13,14,60 | 2 |
| **MD-LOC** | Warehouse & locations | Plant→…→Bin hierarchy, compatibility rules, occupancy | 21 | 2 |
| **MD-EQP** | Equipment & calibration | Equipment, calibration/qualification/maintenance status | 47 | 2 |
| **MD-CUS** | Customer master | Customers, authorisations | 44 | 2 |
| **IMP** | Controlled master import | Upload→validate→preview→error report→approve→import | 87 | 2 |
| **VQ** | Vendor qualification | Documents, questionnaire, risk class, status machine, requalification, expiry job | 10 | 3 |
| **VM** | Vendor–material mapping | Approved vendor per material, versioned, change-controlled | 12,59 | 3 |
| **PR** | Purchase request | Draft→…→Approved→PO | 16 | 3 |
| **PO** | Purchase order | Validation gate (vendor/material/spec/docs), approval | 17,92 | 3 |
| **GRN** | Receipt & GRN | Receipt, checklist (configurable), critical-fail block, containers | 18,19 | 4 |
| **QRN** | Quarantine & storage | Auto-quarantine lot, location assignment, compatibility | 20,21 | 4 |
| **LBL** | Label engine | Quarantine/Approved/Sample/Location/FG labels; templates versioned; print audit; reprint control | 22,29,52 | 4 |
| **INV** | Inventory & ledger | Ledger, balances, FEFO/FIFO, reservations, expiry/retest alerts, stock reconciliation, destruction | 31,32,68,69 | 4 |
| **HOLD** | Quality hold | Hold/unhold for material, batch, SFG, FG | 70 | 4 |
| **SMP** | Sampling & sample management | Sampling record, sample master, retention/stability, disposal | 15,23,46 | 5 |
| **QC** | QC / LIMS | Test assignment, results, analyst→QC→QA review, calibration gate, amendments | 24,25,47 | 5 |
| **STAT** | Statistics & trending | Descriptive stats, Cp/Cpk/Pp/Ppk, control charts, Nelson rules, OOT | 26,27 | 5 |
| **REL** | Material release | Disposition workflow, approved label, rejection | 28,29 | 5 |
| **CRL** | Conditional release | QA-authorised use-before-release | 30 | 5 |
| **OOS** | OOS / OOT | Phase I/II investigations, root cause, CAPA link, disposition | 71 | 5 |
| **COA** | Certificate of analysis | Versioned PDF/Excel COA | 43 | 5 |
| **BOM** | Bill of materials | Versioned BOM (RM/PM/SFG/FG), overages, yields | 33,60 | 6 |
| **MBR** | Master/Electronic batch record | Step templates, execution, verification, line clearance | **G-01** | 6 |
| **MFG** | Manufacturing (SFG & FG) | Batch creation, numbering, equipment/operator capture, IPC, yield | 34,35,40,41 | 6 |
| **ISS** | Material issue / return | Indent, issue with lot validation, return, reversal | 36,37,38 | 6 |
| **REC** | Production reconciliation | Reconciliation engine + tolerance + report | 39,68 | 6 |
| **FGR** | FG release | QC→QA release, FG stock | 42 | 7 |
| **DSP** | Dispatch | Dispatch validation, documents, customer | 44 | 7 |
| **TRC** | Traceability | Forward/backward, graphical + tabular | 45,67 | 7 |
| **ANI** | Animal/donor & plasma (antisera) | Herds, immunisation, bleed, plasma pool | G-02 | 6b |
| **DEV** | Deviation | Lifecycle | 72 | 8 |
| **CAPA** | CAPA | Lifecycle, effectiveness | 72 | 8 |
| **CC** | Change control | Versioned master change workflow | 59,72 | 8 |
| **RSK** | Risk management | FMEA | 73 | 8 |
| **DOC** | Document management | Controlled attachments, hashing, versions | 48 | 2 (core) / 8 (SOP) |
| **NTF** | Notifications | In-app + email, rule-based | 53 | 4→9 |
| **SRCH** | Global search + QR resolve | Cross-entity search, permission-filtered QR landing | 51,52 | 7 |
| **RPT** | Reporting engine | PDF/Excel/CSV, parametrised, header/footer, authorised fields only | 50,65,66 | 9 |
| **ADM** | Admin console | User/role/permission/workflow/numbering/company/email/backup/logs/data dictionary/integrations | 86 | 1+ |
| **BKP** | Backup & health | Backup status, DB health, restore doc | 58 | 1/9 |
| **RET** | Retention | Policies, archival, legal hold, no audit deletion | 85 | 9 |
| **VAL** | Validation pack | URS/FS/DS/RA/DI/IQ/OQ/PQ/RTM templates, scripts | 78 | 10 |

## Dependency order (build graph)
```
CORE → IAM/ORG/AUD/ESIG → MD-* → (VQ,VM) → PR → PO → GRN → QRN/LBL/INV → SMP → QC/STAT → REL/CRL/OOS/COA
     → BOM → MFG/MBR/ISS/REC → FGR → DSP → TRC → DEV/CAPA/CC/RSK → RPT/DASH → VAL
```
