# Phase 5 Report — QC / LIMS

## What was implemented
* **Sampling (§23)** — sampling rules `SQRT_N_PLUS_1` / `FIXED` / `PERCENT` / `ALL` from the sampling plan in force (version pinned to the sample, BR-SMP-002); sample creation posts a `SAMPLE` ledger transaction (BR-SMP-001) and moves the lot to QC_TESTING; sample labels.
* **Tests & results (§24–26)** — tests are assigned from the **specification version pinned at sampling** (later spec revisions do not change in-flight tests, BR-QC-001). Starting a test requires an approved/effective STP (BR-QC-003) and a valid equipment calibration (BR-QC-002; QA-signed override is a controlled, audited exception). Pass/fail is computed server-side with `ROUND_HALF_UP` and inclusive limits (BR-QC-004). Submitted results are **immutable**; corrections go through **amendments** (request → approval with e-signature; original retained and the effective value is derived, BR-QC-005).
* **OOS / OOT (§27)** — failing results raise an OOS with an automatic quality hold; phase I/II investigation, invalidation → retest, QA Head decision with e-signature. OOT detection by alert/action limits and Nelson rules; OOT never changes disposition (BR-STAT-002).
* **Release workflow (§28)** — QC Analyst submits → QC Head → QA Officer → QA Head (distinct approvers, SOD-02/03/24), each with e-signature; readiness checks (all tests submitted and passed, no open OOS/hold, vendor CoA received, not expired); `QC` and `QA-release` numbers; lot APPROVED.
* **CoA** — PDF + XLSX generated at QA release, versioned, append-only; printed with signature manifest.
* **Conditional release (§29, BR-CRL-001…003)** — QA Officer requests, QA Head approves with e-signature; quantity-bounded, expiry-bounded, batch-bound authorisation.
* **Statistics (C-12)** — descriptive stats, Cp/Cpk (σ within = MR̄/1.128), Pp/Ppk, explicit status codes, I-MR control limits, Nelson rules; trend endpoint + SVG chart.
* **Frontend** — Samples & Tests, Release queue, OOS/OOT, Conditional release, Trends.

## Database
Migration `0005`: `sample`, `qc_test`, `qc_result`, `qc_result_amendment`, `oos_investigation`, `oot_event`, `coa`*, `conditional_release` (* append-only).

## Tests
`tests/workflows/test_qc.py` — **22 passed** (critical tests 10, 11, 13, 15; stats reference datasets; pinned spec; calibration gate/override; amendments; OOS→retest; release chain and SoD; CoA; conditional release). Full SQLite suite after Phase 5: **160 passed**.

## Known limitations
Instrument integration is manual entry; sample retention/disposal is basic; non-normality is a warning code only (no normality test); CoA template is a fixed layout; stability studies are out of scope.
