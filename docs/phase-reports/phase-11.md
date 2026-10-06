# Phase 11 Report — Environmental monitoring, stability studies and costing

Requested after release candidate 1.0.0-rc1 ("include environmental monitoring, stability studies and costing as per GMP requirements"). These three areas were deliberately outside v1; they are now built on the same controls as the rest of the system. Regulatory references used as *design inputs only*: EU GMP Annex 1 (cleanroom grades and monitoring), ICH Q1A(R2)/Q1E (stability conditions and evaluation), EU GMP Chapter 6 (stability programme, OOS), Chapter 4 (records). The documents say the system *supports* compliance when implemented with appropriate site procedures and validated; nothing here is a statement of compliance.

## What was implemented

### Environmental monitoring (EM)
* **Locations and plans.** Monitoring points with grade A/B/C/D/NC; plans (location × sample type × state × frequency) with a due/overdue schedule (`GET /em/schedule`, report, dashboard card, daily-job notification).
* **Controlled limits.** `em_limit_set` + `em_limit` are a *versioned master*: DRAFT → UNDER_REVIEW → APPROVED (QA Head e-signature, author ≠ approver SOD-36) → SUPERSEDED. Limits are alert/action, high/low, per grade × sample type (viable air, settle plate, contact plate, glove print, 0.5/5 µm particles, differential pressure, temperature, humidity) × state (at rest / operational). `Load reference limits` creates a **draft** from Annex 1-style reference values that the site must verify; nothing is judged until a set is approved (BR-EM-001).
* **Samples and results.** Sampling (optional batch link, optional instrument — calibration/qualification gate BR-QC-002) → result entry → QA review. The limits in force are **snapshotted on the sample**, so a later revision never re-judges history. Outcome WITHIN / ALERT / ACTION. **ACTION raises a deviation automatically** (critical for grades A/B, otherwise major; it blocks release of a linked batch); ALERT notifies the configured roles (`em.alert_notify_roles`). Review without the deviation is refused (BR-EM-003).
* **Data integrity.** A result is entered once; corrections are *amendments* in an append-only table (old/new value and outcome, reason, user); QA review is e-signed, locks the result and cannot be done by the person who entered it (SOD-37). Organisms (name, Gram, CFU, method) are recorded before review.
* **Trend and excursions.** Per location/type series with descriptive statistics, individuals-chart limits and Nelson-rule signals (reusing `services/stats.py`, flagged "indicative" because count data are not normal); 90-day excursion list.

### Stability studies
* **Protocol** (versioned, e-signed, SOD-38): product, APPROVED specification (its parameters are the tests), container-closure, storage conditions (long-term / intermediate / accelerated / stress / refrigerated / frozen with °C and %RH), time points (months), pull window. Submission requires an approved spec of the same material, ≥1 condition, ≥1 time point and a long-term-type condition.
* **Study** (creator ≠ conclusion signer, SOD-40): pinned to the exact protocol version and a lot. **Starting** books `units_per_pull × conditions × time points` out of the lot with a `SAMPLE` ledger transaction (`ref STABILITY`), and schedules one pull per condition × time point (due = start + n months, month-end safe).
* **Pulls and results.** SCHEDULED → PULLED → TESTED → REVIEWED (or MISSED / SKIPPED with reason). A pull outside its window needs remarks and raises a minor deviation. Results (`stability_result`) are **append-only**: one current row per parameter, corrections insert a superseding row with a reason; they are evaluated by the same rounding/PASS-FAIL rules as QC (`qc.evaluate`) and the instrument gate applies. A FAIL raises **one deviation per pull, linked to the lot** (blocks release/dispatch like any open deviation — BR-DEV-001); review is e-signed by someone other than the analyst (SOD-39) and refused for a failing pull without a deviation. The daily job marks pulls whose window has closed as MISSED with a deviation (idempotent).
* **Evaluation and conclusion.** Per condition × numeric parameter regression on current results with a one-sided 95 % confidence bound against the specification limit and capped extrapolation (min of 2× observed and observed + 12 months), explicitly *decision support*. A study is completed only when no pull is open; QA Head signs the shelf-life conclusion after linked deviations are closed. The system never changes a lot's expiry itself (use change control).

### Costing
* **Rate card** (versioned, e-signed, SOD-41): labour/hour, machine/hour, overhead % of conversion cost, currency. **Standard cost** per material (audited, reason required).
* **Lot cost** (`lot_cost`, append-only; latest row wins): purchased lots take the PO line rate (tax excluded unless `costing.include_tax`), manufactured lots take their *approved batch cost*, anything else needs a manual cost with a reason. A lot with no basis is **reported and blocks costing — never valued at zero** (BR-COST-001/002).
* **Batch cost.** Derived from the immutable `material_issue` rows minus accepted returns at each lot's cost, plus labour and machine hours (the only inputs) at the approved card and overhead; output quantity from the batch; unit cost; variance and % to standard. DRAFT can be recalculated; approval is e-signed by someone other than the calculator (SOD-42), locks the cost and writes the output lot's cost so **SFG → FG costs roll up** through the genealogy. `inventory valuation` = on-hand × current lot cost, with uncosted lots listed.
* **Visibility.** New roles *Costing Analyst* and *Finance Head*; Management and Auditor are read-only; production, warehouse, QA, QC and administrators see no cost data.

## Files
* **Models:** `app/models/em.py` (7 tables), `stability.py` (6), `costing.py` (4). **Services:** `services/em.py`, `stability.py`, `costing.py`; `versioning.py` (new kinds + submission validators); `numbering.py`, `config_service.py`, `retention.py`, `seed.py`, `dashboards.py`, `jobs/runner.py`.
* **API:** `api/v1/em.py`, `stability.py`, `costing.py` (registered in `api/v1/__init__.py`). **Reports:** 6 new in `reports/catalog.py`.
* **Frontend:** `pages/Monitoring.tsx`, `Stability.tsx`, `Costing.tsx` (+ routes and 11 nav entries); `Quality.tsx` exports its generic dialogs.
* **Migration:** `database/migrations/versions/0010_phase11_em_stability_costing.py`; `database/mssql/01_logins_and_grants.sql` (3 more DENY lines).
* **Tests:** `tests/workflows/test_phase11_{em,stability,costing,reports}.py`.
* **Docs:** this report, URS-EM/STB/COST (12 requirements) in `scripts/validation_requirements.py` → regenerated `urs.md`/`rtm.md`/data dictionary/ER/OpenAPI/access matrix, FMEA #26–#32, functional/design/IQ/validation-plan updates, user + admin manuals, release notes, known defects KD-16…19, SOP list (#23–#25).

## DB changes
Migration `0010`: 17 tables (`em_limit_set`, `em_limit`, `em_location`, `em_plan`, `em_sample`, `em_isolate`, `em_result_amendment`, `stability_protocol`, `stability_condition`, `stability_timepoint`, `stability_study`, `stability_pull`, `stability_result`, `cost_rate_card`, `standard_cost`, `lot_cost`, `batch_cost`). **127 tables; 20 append-only** (new: `em_result_amendment`, `stability_result`, `lot_cost`, with DB triggers and grants DENY). Numbering types EMLIM, EMLOC, EMSAMPLE, STABPROT, STUDY, COSTCARD; config keys `costing.include_tax`, `em.alert_notify_roles`; retention sources for EM samples, stability results, batch costs.

## API changes
+69 operations (466 total): `/em/*` (locations, plans, limit sets + submit/approve/new-version/load-reference, samples + result/amend/isolates/review/cancel, schedule, trend, excursions), `/stability/*` (protocols, studies, pulls, results/corrections, review, evaluation, due, check-missed), `/costing/*` (rate cards, standards, lot cost, batch cost calculate/approve, valuation). 42 new permissions (298), SoD SOD-36…42.

## UI changes
EM Overview, EM Samples, EM Locations, EM Limits; Stability Protocols, Studies (pull/results/review/evaluate/conclude), Pulls Due; Cost Rate Cards, Batch Costs, Standard Costs, Inventory Valuation; two new dashboards (Monitoring & stability, Costing).

## Defects found by this phase's testing (all fixed)
| # | Found by | Defect | Fix |
|---|---|---|---|
| 1 | Stability OOS test | Setting `deviation_id` on an already-inserted append-only result was refused | Deviation raised *before* the result row is created |
| 2 | Stability OOS design review | An out-of-window deviation on a pull would have been reused for a later OOS (non-blocking) | Separate `oos_deviation_id` |
| 3 | Regression helper test | Limit-crossing search started at the last observed point and could not report an earlier crossing | Search starts at month 0 |
| 4 | SQL Server migration | Two unique constraints on one table got the same generated name (`uq_em_limit_limit_set_id`, `uq_stability_timepoint_protocol_id`) — error 8168 | Explicit constraint names (SQLite did not show it) |
| 5 | Review of design | A sample taken before limit approval would have been judged against "limits at sampling time" | Judged against the limits in force at result entry, snapshotted |

## Tests and evidence
* **SQLite:** 259 tests collected (the full run began before the last 2 tests were added); full run 255 passed, 1 skipped (server-database-only test), 1 failed — an old dashboard-list assertion that did not expect the new `monitoring` dashboard for the QA Head; the assertion was updated and re-run (pass). Targeted re-runs are in `evidence/junit-sqlite-phase11-*.xml`.
* **SQL Server 2022:** four parallel partitions, 254 passed, 2 deselected (SQLite-subprocess migration tests), the same single dashboard assertion failed and passed on re-run (`junit-sqlserver-5.xml`). Migrations `0001→0010` up/down/up on SQL Server: 127 tables, 20 `INSTEAD OF` triggers (the three new ones verified present).
* Not repeated for Phase 11: restore and load tests (evidence predates it), UI smoke of the 11 new pages, least-privilege grants run for the 3 new DENY lines.

## Known limitations
KD-16…KD-19 in `docs/known-defects.md`: EM has no BMS/continuous-monitoring interface or incubation workflow; stability evaluation has no ICH Q1E pooling tests, chamber mapping or per-container tracking, and OOS is handled as a deviation, not the QC OOS form; costing is standard/actual only (no GL, multi-currency, landed cost, WIP).

## Next phase
None is planned in the build plan. Suggested follow-ups: reuse the QC OOS investigation for stability, QMS audit management, instrument/BMS interfaces, finance posting.
