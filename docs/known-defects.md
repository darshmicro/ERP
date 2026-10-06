# Known Defects and Limitations (release 1.1.0-rc1)

No open **critical** or **major** defect is known. The items below are accepted limitations / minor defects; each is also listed in the relevant phase report.

| ID | Area | Description | Impact | Mitigation / plan |
|---|---|---|---|---|
| KD-01 | Platform | In-process scheduler has no leader election; two instances would both run the (idempotent) jobs | Duplicate notifications are suppressed, work is repeated | Enable on one instance or use cron (documented) |
| KD-02 | Notifications | In-app only; no email/SMS sender | Alerts need the user to look | Planned integration; SOPs may require daily review |
| KD-03 | Purchase | PO amendment/revision not implemented (cancel and re-issue); no multi-currency conversion | Process workaround | Roadmap |
| KD-04 | Warehouse | No put-away location *suggestion*; no cycle-count UI (ledger adjustments exist as types) | Manual choice | Roadmap |
| KD-05 | QC | Instrument interfaces absent (manual entry); non-normality is a warning only; (stability studies: see KD-16..18) | Manual transcription controls apply | Site SOP; roadmap |
| KD-06 | Manufacturing | MBR steps are free text with an optional value (limits only in IPC); no routing/work-order scheduling; additional issue needs a permission, not a separate signed record | Process fit | Roadmap |
| KD-07 | Dispatch | No customer-specific product authorisation list or ship-to master; no cold-chain transport record | Customer-level licence/authorisation only | Roadmap |
| KD-08 | Quality | No audit/inspection management or supplier-audit scheduling; training matrix not auto-driven by SOP effectivity; recall regulatory timelines not modelled | Manual procedures | Roadmap |
| KD-09 | Reports | On-demand only; no scheduled/emailed or ad-hoc report builder; archive packages are XLSX (not WORM storage) | Site storage controls | Roadmap |
| KD-10 | Backup | The page records evidence; it cannot run or verify backups | Needs site tooling/SOP | `scripts/restore_test.py` |
| KD-11 | Security | `/api/docs` enabled by default | Information exposure | Disable at the reverse proxy in production |
| KD-12 | Test | The concurrency regression for simultaneous same-account logins runs only on a server database (skipped on SQLite) | Coverage on SQLite | Executed in the SQL Server run |
| KD-13 | Performance | Load measured with 50 virtual users on a single test host (shared with the database); production sizing must be confirmed in PQ | Capacity assumptions | PQ-P1 |
| KD-14 | UI | English only; no accessibility audit | — | Roadmap |
| KD-15 | Import | The Excel import module covers vendor, material, specification, STP, equipment and customer; BOMs, locations' compatibility rules and historical stock/lot balances are not importable (opening stock must be entered through GRN/adjustments under a controlled procedure) | Data migration effort | Roadmap; site migration SOP |
| KD-16 | Environmental monitoring | Shipped Annex 1 style limit values are *reference data only* and cover viable and non-viable limits, not the site's contamination-control strategy; no continuous-monitoring/BMS interface (manual entry); no personnel-qualification (aseptic) link; no incubation/plate-reading workflow; organism identification is free text (no library); trending is indicative (Nelson rules on count data) | Site must verify/approve limits, trend per its procedure | Roadmap |
| KD-17 | Stability | Evaluation is per batch, per condition and per numeric parameter (no ICH Q1E pooling/poolability tests); no chamber-mapping/chamber-excursion record; stability samples are booked out of the lot (no per-container tracking in the chamber); no automatic change of lot expiry/shelf life (QA decision + change control); no bracketing/matrixing designs | Statistician/QA judgement required | Roadmap |
| KD-18 | Stability | OOS in a stability result raises a deviation (linked to the lot) instead of the QC OOS investigation form | Investigation is run under the deviation/CAPA process | Roadmap: reuse OOS module |
| KD-19 | Costing | Standard/actual costing only: no general ledger, tax, multi-currency conversion, landed-cost/freight allocation, scrap/by-product costing, work-in-progress valuation or period-end close; purchased lots are costed at the PO rate in the PO unit (a lot unit that differs needs a manual cost); labour and machine hours are entered, not derived from step timings; standard cost changes are audited but not approval-controlled | Finance integration/ERP posting is out of scope | Roadmap |

