# GMP-MERP — Phase 0 Architecture Package

**Application name (configurable):** GMP-MERP — *GMP Manufacturing & Material ERP*
**Status:** DRAFT for approval · **Phase:** 0 · **Date:** 2026-10-05

| # | Document |
|---|----------|
| 00 | This file — index, critical design conflicts, assumptions, open questions |
| 01 | System architecture (A) |
| 02 | Module list (B) |
| 03 | Database ER diagrams and table list (C, D) |
| 04 | RBAC matrix and segregation of duties (E) |
| 05 | Workflows and state machines (F) |
| 06 | GMP compliance mapping (G) |
| 07 | Business rules catalogue (H) |
| 08 | Validation strategy (I) |
| 09 | Development roadmap (J) |

> **Regulatory position.** The software is designed to *support* 21 CFR Part 11 / EU Annex 11 / ALCOA+ through technical controls. It is **not** "certified" or "compliant" by itself. Compliance additionally requires site validation (CSV/CSA), SOPs, trained users, qualified infrastructure, and periodic review. Doc 06 separates *software capability* from *site responsibility* row by row.

---

## 1. Critical design conflicts and how this design resolves them

Each item is a place where the requirements, as written, conflict with each other, with a regulation, or with a platform constraint. **Resolution** is the proposed decision; please confirm or override.

| ID | Conflict / gap | Proposed resolution |
|----|----------------|---------------------|
| **C-01** | §10 says an expired vendor *must block PO*, and also says QA may *override* with reason/signature. These contradict if "override" means creating a PO. | **No PO-level override exists.** QA's only path is a **controlled Vendor Requalification** (signed, audited, with a new approved due date or `CONDITIONAL` status with an expiry). PO creation checks the vendor's *current* effective qualification. Rule 1 stays absolute. |
| **C-02** | §30 "use before final release" vs Rules 4/5 (quarantine/rejected cannot be issued). | Conditional Release is a **separate, QA-signed, batch-and-quantity-specific authorization** (risk assessment ref mandatory). It can apply only to `QUARANTINE`/`QC TESTING`/`QA REVIEW` lots. **Never to `REJECTED`, `HOLD`, `UNDER INVESTIGATION`, or expired lots.** Issue transactions record `conditional_release_id`; the consuming batch is flagged "USED UNDER QA-AUTHORIZED CONDITIONAL RELEASE" and cannot be released to FG until the material's final disposition is recorded. |
| **C-03** | Material "approved vendors" appear in both Material Master (§11) and Vendor-Material mapping (§12). Two sources = drift. | **Single source of truth: `vendor_material`** (versioned, change-controlled). Material Master displays it read-only. |
| **C-04** | Statuses: Material master (Draft→Approved→Active→Obsolete) vs. material *lot* status (Quarantine→…→Approved) vs. inventory statuses (§31) overlap in naming. | Three distinct state machines: **Master status** (on `material`), **Lot disposition** (on `material_batch`), **Stock status** (derived on `inventory_balance` from lot disposition + holds + expiry). Docs 05/07 define each. |
| **C-05** | §69 says never update stock without history, but §31 needs fast real-time stock. | **Append-only `inventory_transaction` ledger is authoritative.** `inventory_balance` is a materialized projection updated **in the same DB transaction** as the ledger insert, with a nightly + on-demand **ledger-vs-balance verification job** that raises an alert on any drift. Negative stock blocked by CHECK constraint. |
| **C-06** | §7 "audit trail immutable" while the app DB account performs the writes. A compromised app account could alter audit rows. | Defense in depth: (1) app account has **INSERT/SELECT only** on `audit_trail`/`e_signature` (no UPDATE/DELETE grant); (2) DB triggers `RAISE` on UPDATE/DELETE; (3) **hash chain** (`row_hash = SHA-256(prev_hash ‖ canonical row)`) with a verification endpoint; (4) optional SQL Server **Ledger tables** (2022+) where licensed; (5) retention via an approved-policy archive procedure only (§85). |
| **C-07** | §6 e-signature "username/password or configured authentication" with LDAP users — the app cannot verify an AD password without a bind. | Signature = **fresh re-authentication** (LDAP bind or local hash verify) at action time, never session reuse; binds `meaning + record id + record content hash + user + role + UTC timestamp` into a **signature manifest**, stored in `e_signature` and hash-linked to the record version. Two-component rule: user ID + password every signing (not only first in a session — stricter than Part 11.200(a)(1)(ii) minimum; configurable). |
| **C-08** | §3 "SQL Server preferred, PostgreSQL possible" vs §3/§7/§57 using RLS, ledger tables, triggers. | **Portable core:** SQLAlchemy 2.x + Alembic with dialect-neutral types. **Dialect-specific** items (immutability triggers, RLS, ledger, row-versioning) isolated in `database/migrations/dialect/{mssql,postgres}/`. MSSQL is the tested target in v1; PostgreSQL parity is *best-effort, tested in CI* (Postgres container) but not validated. |
| **C-09** | §82 targets **Windows 11 Pro** + "50 concurrent users, 100k+ records" + GMP. Windows 11 is a client OS; SQL Server **Express** caps at 10 GB/DB and 1.4 GB buffer — audit trail + ledger will exceed this. | Dev/pilot/UAT on Win 11 is supported. **Production recommendation:** Windows Server (or Linux VM) + SQL Server Standard (or PostgreSQL). Documented in Doc 01 §9 & deployment guide. Gunicorn does not run on Windows → Windows uses **Uvicorn under a service wrapper (NSSM / WinSW) behind IIS-ARR or Caddy/nginx**; Linux/Docker uses Gunicorn+Uvicorn workers. |
| **C-10** | §16 PR workflow is fixed (Draft→Submitted→Dept Approval→Purchase Review→Approved→PO) but §54 demands *configurable* workflows. | **Workflow engine** holds approval *steps, roles, signature requirement, SLA* as configuration (versioned, change-controlled). **State machines (allowed statuses/transitions) stay in code** per §55 ("never arbitrary status changes"). Config selects *who/how many/what signature*, never *which states exist*. |
| **C-11** | §39 reconciliation formula is dimensionally ambiguous. | Defined precisely in Doc 05 §6: `Issued + Additional = Consumed + Sampled + Waste/Loss + Returned + Closing(Unaccounted)`; discrepancy = `Issued + Additional − (Consumed + Sampled + Waste + Returned)`; tolerance % per material class, configurable; breach → mandatory deviation. |
| **C-12** | §26 Cp/Cpk/Pp/Ppk: Cp/Cpk use *within-subgroup* σ, Pp/Ppk use *overall* σ. Prompt formula uses a single σ. | **Cp/Cpk** σ_within estimated by moving-range (MR̄/1.128) (individual values) or R̄/d2 (subgroups); **Pp/Ppk** use overall sample σ (n−1). Minimum N configurable (default **25** for capability, 10 for descriptive); one-sided specs compute only the applicable index; normality check flag. Insufficient-data states returned explicitly. |
| **C-13** | §35 batch-number override vs "duplicates never allowed" and numbering gaps. | Override allowed only at batch *creation*, permission `batch.number.override`, reason + audit; DB `UNIQUE(site_id, batch_no)`; numbers from a **gapless-by-design, transactionally allocated** sequence; unused/voided numbers are retained as `VOID` rows (never reissued). |
| **C-14** | §47 "QA override" for expired calibration vs §92 absolute rules. | Not a Phase-1 absolute rule, so: default **block**; override is a configurable policy (`calibration.override_allowed`), requires QA signature + deviation reference, and the QC result is permanently flagged "tested on instrument with expired calibration under QA override". |
| **C-15** | §2/§98: user asked for "Do NOT start coding until architecture presented". | Honoured: this PR contains **only documents**. Implementation starts after your approval of Doc 00 §3 decisions. |
| **C-16** | **Scope realism.** 100 sections ≈ a multi-year ERP. | Delivered strictly in the 10 phases of §94, each *vertical-slice complete* (DB→API→UI→audit→tests→docs), with a phase gate (no unresolved critical defects). Nothing is dropped; ordering is in Doc 09. |

---

## 2. Missing functions identified (not in the prompt, needed for an antisera/biological plant)

Classified **M** = must add before go-live, **S** = should add, **F** = future.

| ID | Function | Why it matters | Class | Planned phase |
|----|----------|----------------|-------|---------------|
| G-01 | **Master Batch Record / Electronic Batch Record (MBR/eBR)** with step-wise execution, double verification, line clearance | Prompt has BOM + batch but no process instructions/records; GMP core | M | 6 |
| G-02 | **Animal / donor management** (horse herd, health, immunization schedule, bleeding records, plasma pooling) | Antisera starting material is animal plasma; full donor→pool→batch traceability | M | 6b (extension of 6) |
| G-03 | **Cold chain / temperature monitoring** (storage + transport excursion handling) | Biologicals; excursion triggers hold + deviation | M | 4 |
| G-04 | **Training records & role-gating** (user can only sign if trained on SOP version) | Part 11.10(i), Annex 11 §2 | M | 1 |
| G-05 | **Controlled document (SOP) management** with versioning, periodic review | Annex 11/GMP Ch.4. Prompt only covers attachments (§48) | S | 8 |
| G-06 | **Environmental monitoring & utilities (WFI, HVAC)** | Annex 1 sterile fill | S | F |
| G-07 | **Stability program** (protocols, pull schedule, results) | Sample type exists in §15, no module | S | F |
| G-08 | **Complaints, returns, recall** with reverse-trace trigger | GDP; uses §45 reverse trace | M | 7/8 |
| G-09 | **Label reconciliation / label stock control** | Mix-up control | S | 6 |
| G-10 | **Vendor & customer audit scheduling, supplier scorecards** | §10 partial | S | 3 |
| G-11 | **Destruction / disposal records** for rejected/expired | Closes lifecycle; §68 "Destroyed" needs it | M | 4 |
| G-12 | **Periodic review of access rights** (quarterly user-role recertification) | Annex 11 §12 | S | 1 |
| G-13 | **Time synchronization & timezone policy** | ALCOA "contemporaneous"; all timestamps stored UTC, shown in site TZ | M | 1 |
| G-14 | **Data archival & legacy retrieval** | Annex 11 §17 | S | 9 |
| G-15 | **Printed-copy control** (controlled copy numbering, "uncontrolled when printed") | Part 11.10(b) copies | S | 9 |
| G-16 | **Regulatory-India specifics** (Drugs & Cosmetics Rules licences, GST e-invoice/e-way bill hooks) | Site is India-style (GST, drug licence). Hooks only; no accounting. | F | 7 |
| G-17 | **Finance/costing** | Out of scope (no GL). Integration point defined. | F | — |
| G-18 | **Sterile/aseptic fill & lyophilisation process records** | Process-specific | F | 6b |

---

## 3. Decisions requested from you (approval gate)

Reasonable defaults are proposed; if you simply say **"approved"**, defaults are used.

1. **Frontend approach** — Default: **React + TypeScript + Vite + Bootstrap 5**, TanStack Table, ECharts. Alternative: server-rendered Jinja2 + HTMX (simpler to validate, less rich UX). *Default: React SPA.*
2. **Production DB** — Default: **SQL Server 2022 Standard** (dev: Developer/Docker Linux image; Express only for demos). PostgreSQL best-effort.
3. **Auth** — Default: **Local auth first (Phase 1), LDAP/AD via `ldap3`** behind an `AuthProvider` interface in Phase 1 too; AD test needs an AD server — if none is available I will build against a mock LDAP and flag it as "not site-verified".
4. **PDF/Excel libs** — Default: **WeasyPrint** (HTML→PDF; Windows needs GTK runtime; fallback **ReportLab**), **openpyxl**/XlsxWriter.
5. **Antisera-specific scope (G-02, G-01)** — Include in baseline roadmap as Phase 6b? *Default: yes.*
6. **Sample-data locale** — Default: INR, IST (Asia/Kolkata), DD-MMM-YYYY, 24h.
7. **e-signature strictness** — Default: re-enter password on every signature.
8. **Site topology** — single plant now, `site_id` on all transactional tables so multi-site can be added without redesign. *Default: yes.*

---

## 4. Assumptions (documented per §"ambiguous requirements")

* A-01 Single legal entity; multi-plant capable via `site_id`.
* A-02 All times stored UTC (`datetimeoffset`/`timestamptz`); displayed in configured site timezone with zone label.
* A-03 Quantities use `DECIMAL(18,6)`; unit conversions via `unit_conversion` table; no floating point for stock.
* A-04 "Delete" is **soft-deactivate only** for master data and **never** for GMP transactions/audit/signatures.
* A-05 Lot = `material_batch` (one GRN line → one internal lot, N containers).
* A-06 Language: English UI; i18n-ready strings.
* A-07 Scanners: keyboard-wedge barcode/QR scanners and device cameras; no proprietary SDK.
* A-08 Email via SMTP only; no external cloud services required (air-gapped LAN deployable).
