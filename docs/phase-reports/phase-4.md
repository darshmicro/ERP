# Phase 4 Report — Warehouse

## What was implemented
* **GRN (§18–19)** — receipt against an approved PO (vendor must match the PO, quantity ≤ ordered + configurable over-delivery tolerance, date sanity checks), configurable 19-item receipt checklist with *critical* items. A critical "No" blocks verification (BR-GRN-004); QA Head may grant a documented, e-signed **exception** per item. Verification by a second person (SOD-22, e-signature) creates **lots + containers**, posts the `RECEIPT` ledger transaction into a **quarantine location** (BR-QRN-001), updates PO `received_quantity` / PO status, and places an automatic **hold** if the vendor qualification lapsed meanwhile (BR-GRN-005).
* **Inventory ledger (decision C-05)** — `inventory_transaction` is append-only and authoritative; `inventory_balance` is a projection updated by guarded atomic UPDATEs in the same transaction (no negative stock, BR-INV-002). Transaction types: RECEIPT, TRANSFER, SAMPLE, ISSUE, RETURN, REJECT_MOVE, DESTROY, ADJUST_IN/OUT, DISPATCH, OUTPUT. Ledger-vs-balance verification and per-lot reconciliation (received/sampled/issued/…/remaining).
* **Lot disposition engine** — `LOT_MACHINE` (QUARANTINE → QC_TESTING → QC_APPROVED → QA_REVIEW → APPROVED / REJECTED, EXPIRED, DESTROYED …). **Quality holds are an overlay** (`quality_hold`) rather than a disposition (documented refinement of Doc 05 §2.6) so releasing a hold restores exactly the previous state; derived stock status (HOLD / EXPIRED / RETEST_DUE).
* **Issue gates** — BR-ISS-001 (unreleased), BR-ISS-002 (rejected), BR-ISS-004 (expired / retest passed), BR-HOLD-001; FEFO/FIFO pick list per material (`pick_fefo`).
* **Put-away / transfer** — BR-QRN-001…004 and location compatibility/capacity (BR-LOC-001/002).
* **Labels** — Code128 + QR PDF labels (reportlab) with controlled numbering, print audit, reprint reason, copy limit (BR-LBL-001…003); sample and location labels.
* **Temperature log** — append-only; excursion ⇒ automatic holds on lots at that location (BR-TMP-001). **Destruction** — request → QA Head approve (SOD-23, e-signature) → execute with ledger `DESTROY`.
* **Jobs** — nightly lot expiry + expiry/retest alerts (90/60/30 d, configurable); dashboard cards (quarantine, near-expiry).
* **Frontend** — Goods Receipt (create, checklist, verify/reject, exceptions) and Inventory & Lots (stock, lots, holds, destruction, lot detail with ledger).

## Database
Migration `0004`: `checklist_item`, `grn`, `grn_line`, `grn_checklist`, `material_batch`, `material_container`, `inventory_transaction`*, `inventory_balance`, `quality_hold`, `material_label`*, `storage_temperature_log`*, `destruction_record` (* append-only, DB triggers installed).

## Tests
`tests/workflows/test_warehouse.py` — **19 passed** (critical tests 4, 5, 7, 8, 13 for issue gates and holds; GRN checklist and exception paths; ledger/balance integrity; FEFO; labels; temperature excursion; destruction; expiry job; SoD).

## Known limitations
Put-away *suggestions* are not computed (user chooses location); cycle-count/physical-stock reconciliation UI is not built (adjustments exist as ledger types); label templates are fixed layouts (no designer); barcode *scanning* is browser-keyboard-wedge only.
