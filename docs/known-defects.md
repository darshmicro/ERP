# Known Defects and Limitations (release 1.0.0-rc1)

No open **critical** or **major** defect is known. The items below are accepted limitations / minor defects; each is also listed in the relevant phase report.

| ID | Area | Description | Impact | Mitigation / plan |
|---|---|---|---|---|
| KD-01 | Platform | In-process scheduler has no leader election; two instances would both run the (idempotent) jobs | Duplicate notifications are suppressed, work is repeated | Enable on one instance or use cron (documented) |
| KD-02 | Notifications | In-app only; no email/SMS sender | Alerts need the user to look | Planned integration; SOPs may require daily review |
| KD-03 | Purchase | PO amendment/revision not implemented (cancel and re-issue); no multi-currency conversion | Process workaround | Roadmap |
| KD-04 | Warehouse | No put-away location *suggestion*; no cycle-count UI (ledger adjustments exist as types) | Manual choice | Roadmap |
| KD-05 | QC | Instrument interfaces absent (manual entry); non-normality is a warning only; stability studies out of scope | Manual transcription controls apply | Site SOP; roadmap |
| KD-06 | Manufacturing | MBR steps are free text with an optional value (limits only in IPC); no routing/work-order scheduling; additional issue needs a permission, not a separate signed record | Process fit | Roadmap |
| KD-07 | Dispatch | No customer-specific product authorisation list or ship-to master; no cold-chain transport record | Customer-level licence/authorisation only | Roadmap |
| KD-08 | Quality | No audit/inspection management or supplier-audit scheduling; training matrix not auto-driven by SOP effectivity; recall regulatory timelines not modelled | Manual procedures | Roadmap |
| KD-09 | Reports | On-demand only; no scheduled/emailed or ad-hoc report builder; archive packages are XLSX (not WORM storage) | Site storage controls | Roadmap |
| KD-10 | Backup | The page records evidence; it cannot run or verify backups | Needs site tooling/SOP | `scripts/restore_test.py` |
| KD-11 | Security | `/api/docs` enabled by default | Information exposure | Disable at the reverse proxy in production |
| KD-12 | Test | The concurrency regression for simultaneous same-account logins runs only on a server database (skipped on SQLite) | Coverage on SQLite | Executed in the SQL Server run |
| KD-13 | Performance | Load measured with 50 virtual users on a single test host (shared with the database); production sizing must be confirmed in PQ | Capacity assumptions | PQ-P1 |
| KD-14 | UI | English only; no accessibility audit | — | Roadmap |
