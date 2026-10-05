# Performance Qualification (PQ) Protocol

**Purpose:** demonstrate that the configured system performs reliably in the production-like business process, with real users, production-like data and volumes, and within the site's availability and recovery targets.
**Executed by the site** in the validation environment after IQ and OQ.

## 1. Prerequisites
IQ/OQ closed; SOPs effective; users trained and assigned the roles in `access-control-matrix.md`; master data loaded through the controlled import module (or the PQ demo data `database/seeds/demo_data.py` for a dry run); backups configured.

## 2. End-to-end process scenario (production-like data)
Run the complete chain with at least two different qualified users for each signature step. Record each document number.

| Step | Activity | Expected result / acceptance | Doc no. | Pass/Fail |
|---|---|---|---|---|
| 1 | Vendor A (qualified), Vendor B (qualification expiring), Vendor C (not approved for the material) | PO to A allowed; to C blocked (BR-PO-003); B allowed with warning | | |
| 2 | Material and specification approved; PR → PO approved | Approval chain and e-signatures recorded | | |
| 3 | Receive NaCl, glycine, caprylic acid, packing materials (GRN, checklist, labels) | Lots in QUARANTINE, ledger receipts | | |
| 4 | Sampling, testing, one OOS with investigation and retest, QA release | Lot APPROVED, CoA generated; the rejected lot cannot be issued | | |
| 5 | Put-away to approved location | Compatibility and capacity rules applied | | |
| 6 | BOM approved; SFG batch created; indent; issue with FEFO | Issue gates; lot↔batch link | | |
| 7 | Line clearance; processing steps with second-person verification; IPC; one failing IPC (hold → deviation) | Hold/deviation workflow works | | |
| 8 | Reconciliation within and outside tolerance | Discrepancy flagged; QA acceptance required | | |
| 9 | SFG QC/QA release; FG batch from SFG + packaging; yield; reconciliation | FG in QUARANTINE until released | | |
| 10 | FG QC → QC review → QA release; CoA | FG available | | |
| 11 | Dispatch to customer (validated, approved, dispatched); dispatch note | Ledger DISPATCH; reservation consumed | | |
| 12 | Complaint → deviation → CAPA; mock recall of the dispatched batch | Affected customers derived; hold applied | | |
| 13 | Trace in both directions for the FG batch | Complete, consistent with records | | |
| 14 | Reports: stock, ledger, batch, dispatch, deviation, audit-trail, e-signature log | Match the transactions entered | | |

## 3. Volume and performance
Data volume: ≥ 100 000 ledger/audit rows (generate with the import or `scripts` volume option) and 50 concurrent users.

| Test | How | Acceptance (site may tighten) | Actual |
|---|---|---|---|
| PQ-P1 | `python scripts/load_test.py --users 50 --seconds 600` against the validation server | Error rate < 1 %; p95 of list/dashboard/search requests < 3 s; no pool/lock timeouts | |
| PQ-P2 | Stock-ledger report export (XLSX) with ≥ 100 000 rows | Completes < 60 s | |
| PQ-P3 | Dashboard and global search at volume | p95 < 3 s | |
| PQ-P4 | Nightly jobs (expiry, qualification, alerts) at volume | Complete < 5 min; idempotent when re-run | |

## 4. Resilience and recovery
| Test | Procedure | Acceptance | Actual |
|---|---|---|---|
| PQ-R1 | Backup/restore qualification (`backup-restore-qualification.md`) | Restored copy verified, audit chain valid, RTO ≤ site target | |
| PQ-R2 | Application restart during user activity | No partial transactions; users re-authenticate | |
| PQ-R3 | Database restart / failover (if applicable) | Application reconnects; no data loss beyond RPO | |
| PQ-R4 | Disaster-recovery rehearsal per site DR plan | Service restored within RTO | |

## 5. Conclusion
PQ acceptable / not acceptable: ______ Signature / QA approval: ______
