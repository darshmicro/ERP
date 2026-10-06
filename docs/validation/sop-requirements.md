# SOP Requirements List

Procedures the site needs (not supplied as final text — content depends on site organisation). Each row names the system function it governs and the evidence to retain.

| # | SOP | Covers | System functions / records |
|---|---|---|---|
| 1 | System administration & user management | Account creation, role assignment (reason mandatory), deactivation, periodic access recertification, no shared accounts, admin ≠ GMP approver | Users, Roles, `reports/user-access`, SoD-09/10 |
| 2 | Electronic signature policy | Equivalence to handwritten signature; user attestation; meanings; lost/compromised credentials | e-signature, training gate |
| 3 | Audit-trail review | Frequency, scope (critical data), who reviews, documentation, escalation | Audit trail, Verify chain, security events |
| 4 | Backup, restore and disaster recovery | Schedule, CHECKSUM, off-site copy, restore test (≥ every 180 days), RPO/RTO, DR drill | Backup status page, `scripts/restore_test.py` |
| 5 | Change control for the computerised system | Software releases, configuration changes (numbering, workflows, thresholds, retention), enabling `cc.required_for_master_changes` | Change control module, release notes |
| 6 | Incident and deviation management | Application errors (`ERR-` refs), security incidents, data-integrity events | Deviation, error log, security events |
| 7 | Periodic review of the validated state | Annual: audit trail, access, deviations, backups, vulnerabilities, regression run | Reports, RTM |
| 8 | Data retention, archival and legal hold | Retention periods per record type, archive packages, legal hold approvals | Retention page |
| 9 | Vendor qualification and approved vendor list | Qualification criteria, requalification, adverse actions | Vendor qualification, AVL |
| 10 | Receipt, quarantine, sampling and storage of materials | GRN checklist, quarantine, labelling, put-away, temperature excursions, destruction | GRN, labels, locations |
| 11 | QC testing, OOS/OOT and release | Analyst competence, calibration, result entry/amendment, OOS phases, release chain | QC module |
| 12 | Conditional release | Criteria, risk assessment, QA approval | Conditional release |
| 13 | Material issue, return and batch manufacturing | FEFO, line clearance, MBR execution, IPC, reconciliation tolerance | Manufacturing module |
| 14 | FG release and dispatch | Release authority, shipping documents, customer licence checks | Dispatch module |
| 15 | Traceability and recall | Mock recall frequency, notification, reconciliation | Trace, Recall |
| 16 | Complaint handling | Intake, investigation, linkage to deviation/CAPA | Complaint module |
| 17 | Document control (SOPs) | Authoring, review, approval, effective dates, acknowledgement, periodic review | SOP control |
| 18 | Printouts and controlled copies | Use of PDF/XLSX copies, copy numbers, verification | Reports, `reports-verify` |
| 19 | Time synchronisation | NTP source, drift monitoring | IQ-02 |
| 20 | Excel import / master-data migration | Templates, validation, approval, reconciliation to source | Import module |
| 21 | Training | Role-based training before access; training records feed the e-signature gate when enabled | Training records |
| 22 | Supplier / software maintenance | Vulnerability and patch management, dependency review (SBOM) | `sbom.md` |
| 23 | Environmental monitoring | Contamination-control strategy, grades and limits (verify the reference values), sampling plan and frequencies, excursion handling and investigation, organism identification and trending | EM module |
| 24 | Stability programme | Protocol design, commitment studies, pull and testing procedure, OOS/out-of-trend handling, shelf-life evaluation and assignment | Stability module |
| 25 | Product costing | Rate-card review, standard-cost setting, batch-cost approval, valuation review, handling of uncosted lots | Costing module |

