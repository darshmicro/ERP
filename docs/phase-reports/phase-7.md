# Phase 7 Report — FG release, dispatch and traceability

## What was implemented
* **FG release** reuses the Phase 5 release engine: a lot of an FG product follows the seeded `fg.release` chain (QC Head → QA Officer → QA Head, e-signatures, distinct approvers); CoA is generated at QA release (BR-FGR-001/002). FG stock = APPROVED, unexpired, unheld lots with a positive balance (`GET /fg/available`).
* **Dispatch (§44–47)** — Draft → **Validated** (rules run, stock *reserved*) → **Approved** (QA e-signature, creator ≠ approver SOD-29) → **Dispatched** (rules re-run, reservation consumed, `DISPATCH` ledger transaction per line, CoA linked) → Delivered; Cancel (reason; releases reservation). Content is locked once validated (hook); a controlled *re-open* returns to Draft.
  * BR-DSP-001 (not released ⇒ `DISPATCH BLOCKED — batch … is …; QA release is required.`, **critical rule 6**), BR-DSP-002 (expired / customer minimum remaining shelf life / retest passed; warning ≤ 30 days), BR-DSP-003 (quantity ≤ unreserved stock at the location, aggregated per lot/location), BR-DSP-004 / BR-HOLD-003 (quality hold, open OOS — extension point `LOT_BLOCKERS` for Phase 8 deviations/complaints), BR-DSP-005 (customer active, authorised, licence unexpired), BR-DSP-006 (ledger + customer/invoice/CoA linkage), BR-FGR-001 (FG products only), BR-FGR-002 (CoA must exist). Blocks are logged as `DISPATCH_BLOCKED` security events; `GET /dispatches/{id}/check` is a dry run listing every violation.
* **Traceability (§48)** — generic graph over VENDOR → PO → GRN → LOT → (issue) BATCH → (output) LOT → DISPATCH → CUSTOMER and ANIMAL → BLEED → POOL → LOT. `GET /trace/{type}/{number}?direction=forward|backward|both` returns nodes, edges (with quantities) and a flat table. Typical uses: *recall* (forward from a vendor/RM lot to customers) and *genealogy* (backward from a dispatch to vendor / animal).
* **Global search and QR (§53/54)** — `GET /search?q=` across lots, batches, dispatches, GRNs, POs, samples, vendors, materials, customers and pools, **filtered by the caller's read permissions**; `GET /qr/resolve?code=merp://lot/<no>` (also sample/location/batch/dispatch or a bare number) resolving label QR payloads.
* **Dashboard** — QC pending, QA pending, active production batches, FG batches available, dispatch pending are now real cards.
* **Customer master** gains `min_remaining_shelf_life_days` (customer policy).
* **Frontend** — Dispatch (create from released FG, rule check with BLOCK/WARN banners, approve with e-signature, dispatch, deliver, cancel), Traceability page (SVG flow graph + table, direction selector, deep links from lots/dispatch lines), header global search with QR-payload entry.

## Database
Migration `0007`: `dispatch`, `dispatch_line`; `customer.min_remaining_shelf_life_days`.

## API
`/dispatches*` (CRUD, `check`, `validate`, `reopen`, `approve`, `dispatch`, `deliver`, `cancel`), `/fg/available`, `/trace/{type}/{ref}`, `/search`, `/qr/resolve`.

## Tests
`tests/workflows/test_dispatch.py` — **10 passed** on top of a real end-to-end world (vendor → qualified PO → GRN → QC release of the raw-material lot → BOM → batch → issue → process → reconciliation → output → QC/QA release of the FG lot → dispatch): critical test 6, full flow with reservation/ledger/CoA, creator≠approver, hold/expiry/customer/shelf-life rules, hold appearing after validation (gate re-run at approval; cancel frees stock), RM cannot be dispatched, permissions, **trace completeness** (dispatch → vendor backward; vendor → customer forward; RM lot → customer; customer → vendor; antisera pool → animal), search permission filtering, QR resolve.

## Known limitations
1. No dispatch *note / delivery challan* PDF yet (Phase 9 report engine); CoA PDF is available per lot.
2. No customer-specific product authorisation list (only the customer-level authorised flag and licence expiry); no consignee/ship-to master.
3. Partial deliveries/returns from customers and **recall execution workflow** (notifications, quarantine of returned goods) are Phase 8; the forward trace provides the affected-customer list.
4. Cold-chain (temperature) conditions during transport are not recorded.
5. Traceability graph is computed on demand (capped at 500 nodes, depth 12); no materialised genealogy table.
6. Stock reserved by a validated dispatch cannot be seen on a dedicated screen (only through available quantity).
