# 09 — Development Roadmap (Deliverable J)

Each phase = vertical slice (DB + Alembic → services/rules → API → UI → RBAC → audit → workflow → tests → docs → self-review per §100). **Phase gate:** all tests green, zero open critical/major defects, phase report (what/files/DB/API/UI/tests/results/limitations/next).

| Phase | Name | Scope | Exit criteria (key) | Est. relative size |
|---|---|---|---|---|
| **0** | Architecture *(this PR)* | Docs 00–09 | Your approval of Doc 00 §3 | S |
| **1** | Platform foundation | Repo scaffold, config/.env, DB base + Alembic, users/roles/permissions, local auth + LDAP provider, sessions, lockout, password policy, training gate, audit trail (+ hash chain, immutability triggers), e-signature service, numbering, status/workflow/rule engines, error handling & separate logs, company master + logo, app shell/navigation, home dashboard shell, admin console basics, Docker + Windows run docs | Audit-immutability, RBAC, e-sig, lockout, numbering concurrency tests pass | L |
| **2** | Master data | Units, material types/categories, material, vendor (+docs), specification/STP/sampling plan (versioned), locations, equipment/calibration, customers, documents (hashing), controlled Excel import | Versioning + historical-link tests; import staging tests | L |
| **3** | Purchase | Vendor qualification (+expiry job), vendor–material mapping (+CC stub), PR, PO with gate rules BR-PO-*, workflow chains | Crit tests 1,2,3,8,11 | M |
| **4** | Warehouse | GRN + configurable checklist, containers, auto-quarantine, put-away, labels (Code128/QR), inventory ledger + balance + FEFO/FIFO, holds, destruction, temperature log, expiry notifications | Crit tests 4,5,7(partial),13; ledger-balance verification | L |
| **5** | QC / LIMS | Sampling, sample master, tests/results, calibration gate, amendments, review chain, release + approved label, conditional release, OOS/OOT, stats & trending, COA (PDF/XLSX) | Crit tests 10,11,13,15; stats reference datasets | XL |
| **6** | Manufacturing | BOM (versioned), batch creation + numbering, indent, issue/return, IPC, SFG, FG, reconciliation, MBR/eBR basics | Crit tests 4,5,7,12,14; reconciliation accuracy | XL |
| **6b** | Antisera extension | Animal/donor, immunisation, bleed, plasma pool → batch genealogy (subject to your approval) | Genealogy test | M |
| **7** | FG release & dispatch | FG QC/QA release, FG stock, dispatch + validation, customer, traceability (graph + table, forward/reverse), global search, QR resolve | Crit test 6; trace completeness test | L |
| **8** | Quality system | Deviation, CAPA, change control (wired to versioned masters), risk (FMEA), SOP/document control, complaints/recall | CC→version link tests | L |
| **9** | Reports & dashboards | Report engine, all §50 reports (PDF/XLSX/CSV), dashboards (Mgmt/QC/QA/WH), retention/archival, backup status page, printed-copy control | Report permission/field-leak tests; perf test | L |
| **10** | Validation & hardening | Full CSV pack, RTM, OQ/PQ scripts, security test suite, pen-test checklist, perf/load, backup/restore qualification, demo seed data, manuals | 15 critical tests green; VSR draft | M |

## Delivery status (updated at release candidate 1.1.0-rc1)
All phases 0–11 (incl. 6b; phase 11 = environmental monitoring, stability studies, costing) are delivered on branch `claude/exciting-edison-raz1wb`; per-phase reports are in `docs/phase-reports/phase-N.md`. Remaining work is the **site's** validation (IQ/OQ/PQ execution, SOPs, training) and the roadmap items in `docs/known-defects.md`.

## Cross-phase tracks
* **Security & compliance review** at every phase gate (checklist from §100).
* **Seed/demo data** (Vendors A/B/C, NaCl, Glycine, Caprylic Acid, packaging…) is loaded only by `database/seeds/` scripts, never hard-coded in logic.
* **Documentation** grows each phase (user manual, admin manual, API docs generated from OpenAPI).
* **Delivery cadence:** each phase committed to branch `claude/exciting-edison-raz1wb` as a reviewable set; PRs only when you ask.

## Proposed immediate next step (on approval)
Phase 1 kickoff: repo scaffold + DB base + IAM + audit + e-signature + numbering, with tests, then phase report.
