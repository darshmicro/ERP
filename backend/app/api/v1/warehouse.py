"""Phase 4 endpoints: GRN, lots, inventory, holds, labels, temperature, destruction."""
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.crud import to_dict, xlsx_response
from app.api.deps import Principal, get_db, require
from app.api.helpers import page_args, use_reason
from app.core.errors import NotFound, PermissionDenied, ValidationFailed
from app.models.master import Location, Material, Unit, Vendor
from app.models.purchase import PurchaseOrder, PurchaseOrderLine
from app.models.warehouse import (GRN, ChecklistItem, DestructionRecord, GRNLine, InventoryBalance, InventoryTransaction,
                                  MaterialBatch, MaterialContainer, MaterialLabel, QualityHold, StorageTemperatureLog)
from app.schemas.common import Reasoned
from app.services import grn as grn_svc
from app.services import inventory, labels, lots, masters, warehouse_ops

router = APIRouter()


class SignedAction(Reasoned):
    password: str


def _page(s, stmt, Model, limit, offset, conv=to_dict, order=None):
    limit, offset = page_args(limit, offset)
    total = s.execute(select(func.count()).select_from(stmt.subquery())).scalar()
    rows = s.execute(stmt.order_by(order if order is not None else Model.id.desc()).limit(limit).offset(offset)).scalars().all()
    return {"items": [conv(r) for r in rows], "total": total, "limit": limit, "offset": offset}


# ============================================================ GRN
class GRNLineIn(BaseModel):
    po_line_id: int
    vendor_batch_no: str = Field(min_length=1, max_length=60)
    quantity_received: Decimal = Field(gt=0)
    pack_count: int = Field(default=1, ge=1, le=5000)
    mfg_date: date | None = None
    expiry_date: date | None = None
    retest_date: date | None = None
    coa_received: bool = False
    container_condition: str | None = None
    seal_condition: str | None = None
    packaging_condition: str | None = None
    temperature_condition: str | None = None
    other_documents: str | None = None


class GRNHeader(BaseModel):
    invoice_no: str | None = None
    invoice_date: date | None = None
    vehicle_no: str | None = None
    transporter: str | None = None
    transport_details: str | None = None
    remarks: str | None = None


class GRNIn(Reasoned, GRNHeader):
    po_id: int
    lines: list[GRNLineIn] = Field(min_length=1)


class GRNUpdate(Reasoned):
    model_config = {"extra": "forbid"}
    invoice_no: str | None = None
    invoice_date: date | None = None
    vehicle_no: str | None = None
    transporter: str | None = None
    transport_details: str | None = None
    remarks: str | None = None


class GRNLines(Reasoned):
    lines: list[GRNLineIn] = Field(min_length=1)


class ChecklistIn(BaseModel):
    item_id: int
    answer: str = Field(pattern="^(YES|NO|NA)$")
    comment: str | None = None


class ChecklistSave(Reasoned):
    answers: list[ChecklistIn]


class VerifyIn(SignedAction):
    quarantine_location_id: int


class ExceptionIn(SignedAction):
    item_id: int
    exception_ref: str


def _grn_out(s: Session, g: GRN, detail: bool = False) -> dict:
    d = to_dict(g)
    po, v = s.get(PurchaseOrder, g.po_id), s.get(Vendor, g.vendor_id)
    d.update(po_no=po.po_no, vendor_code=v.vendor_code, vendor_name=v.name)
    if detail:
        lines = []
        for l in s.execute(select(GRNLine).where(GRNLine.grn_id == g.id).order_by(GRNLine.line_no)).scalars():
            m = s.get(Material, l.material_id)
            ld = to_dict(l)
            lot = s.get(MaterialBatch, l.material_batch_id) if l.material_batch_id else None
            ld.update(material_code=m.material_code, material_name=m.name, lot_no=lot.lot_no if lot else None)
            lines.append(ld)
        d["lines"] = lines
        d["checklist"] = grn_svc.checklist_state(s, g)
    return d


def _grn_query(request: Request, q: str | None):
    stmt = select(GRN)
    if q:
        stmt = stmt.where(func.lower(GRN.grn_no).like(f"%{q.lower()}%"))
    for f in ("status", "vendor_id", "po_id"):
        if request.query_params.get(f):
            stmt = stmt.where(getattr(GRN, f) == request.query_params[f])
    return stmt


@router.get("/grn", tags=["GRN"])
def list_grn(request: Request, q: str | None = None, limit: int = Query(50), offset: int = Query(0),
             p: Principal = Depends(require("grn.receipt.read")), s: Session = Depends(get_db)):
    return _page(s, _grn_query(request, q), GRN, limit, offset, lambda g: _grn_out(s, g))


@router.get("/grn/export", tags=["GRN"])
def export_grn(request: Request, p: Principal = Depends(require("grn.receipt.read", "grn.receipt.export")), s: Session = Depends(get_db)):
    rows = []
    for g in s.execute(_grn_query(request, None).order_by(GRN.id)).scalars():
        for l in s.execute(select(GRNLine).where(GRNLine.grn_id == g.id)).scalars():
            m = s.get(Material, l.material_id)
            lot = s.get(MaterialBatch, l.material_batch_id) if l.material_batch_id else None
            rows.append({**_grn_out(s, g), "material": f"{m.material_code} {m.name}", "vendor_batch_no": l.vendor_batch_no,
                         "quantity": l.quantity_received, "expiry_date": l.expiry_date, "lot_no": lot.lot_no if lot else None})
    cols = [("grn_no", "GRN"), ("grn_date", "Date"), ("po_no", "PO"), ("vendor_name", "Vendor"), ("material", "Material"),
            ("vendor_batch_no", "Vendor batch"), ("quantity", "Qty received"), ("expiry_date", "Expiry"), ("lot_no", "Lot"), ("status", "Status")]
    return xlsx_response(s, p, "GRN register", {"status": request.query_params.get("status")}, cols, rows, "grn")


@router.post("/grn", status_code=201, tags=["GRN"])
def create_grn(body: GRNIn, p: Principal = Depends(require("grn.receipt.create")), s: Session = Depends(get_db)):
    use_reason(body.reason or "GRN created")
    po = masters.get_or_404(s, PurchaseOrder, body.po_id, "Purchase order")
    g = grn_svc.create_grn(s, p.user, po, body.model_dump(exclude={"reason", "po_id", "lines"}), [l.model_dump() for l in body.lines])
    s.commit()
    return _grn_out(s, g, True)


@router.get("/grn/{gid}", tags=["GRN"])
def get_grn(gid: int, p: Principal = Depends(require("grn.receipt.read")), s: Session = Depends(get_db)):
    return _grn_out(s, masters.get_or_404(s, GRN, gid, "GRN"), True)


@router.patch("/grn/{gid}", tags=["GRN"])
def update_grn(gid: int, body: GRNUpdate, p: Principal = Depends(require("grn.receipt.update")), s: Session = Depends(get_db)):
    use_reason(body.reason or "GRN edited")
    g = masters.get_or_404(s, GRN, gid, "GRN")
    for k, v in body.model_dump(exclude={"reason"}, exclude_unset=True).items():
        setattr(g, k, v)
    s.commit()
    return _grn_out(s, g, True)


@router.put("/grn/{gid}/lines", tags=["GRN"])
def put_grn_lines(gid: int, body: GRNLines, p: Principal = Depends(require("grn.receipt.update")), s: Session = Depends(get_db)):
    use_reason(body.reason or "GRN lines edited")
    g = masters.get_or_404(s, GRN, gid, "GRN")
    grn_svc.replace_lines(s, g, [l.model_dump() for l in body.lines])
    s.commit()
    return _grn_out(s, g, True)


@router.post("/grn/{gid}/submit", tags=["GRN"])
def submit_grn(gid: int, p: Principal = Depends(require("grn.receipt.submit")), s: Session = Depends(get_db)):
    g = masters.get_or_404(s, GRN, gid, "GRN")
    warnings = grn_svc.submit(s, g, p.user)
    s.commit()
    return {**_grn_out(s, g, True), "warnings": warnings}


@router.put("/grn/{gid}/checklist", tags=["GRN"])
def put_checklist(gid: int, body: ChecklistSave, p: Principal = Depends(require("grn.receipt.verify")), s: Session = Depends(get_db)):
    use_reason(body.reason or "GRN checklist completed")
    g = masters.get_or_404(s, GRN, gid, "GRN")
    grn_svc.save_checklist(s, g, p.user, [a.model_dump() for a in body.answers])
    s.commit()
    return grn_svc.checklist_state(s, g)


@router.post("/grn/{gid}/exception", tags=["GRN"])
def grant_exception(gid: int, body: ExceptionIn, p: Principal = Depends(require("grn.receipt.exception")), s: Session = Depends(get_db)):
    use_reason(body.reason)
    g = masters.get_or_404(s, GRN, gid, "GRN")
    grn_svc.grant_exception(s, g, p.user, body.password, body.item_id, body.exception_ref, body.reason or "")
    s.commit()
    return grn_svc.checklist_state(s, g)


@router.post("/grn/{gid}/verify", tags=["GRN"])
def verify_grn(gid: int, body: VerifyIn, p: Principal = Depends(require("grn.receipt.verify")), s: Session = Depends(get_db)):
    use_reason(body.reason or "GRN verified")
    g = masters.get_or_404(s, GRN, gid, "GRN")
    loc = masters.get_or_404(s, Location, body.quarantine_location_id, "Location")
    created = grn_svc.verify(s, g, p.user, body.password, loc, body.reason or "GRN verified")
    s.commit()
    return {**_grn_out(s, g, True), "lots": [{"id": l.id, "lot_no": l.lot_no, "disposition": l.disposition} for l in created]}


@router.post("/grn/{gid}/reject", tags=["GRN"])
def reject_grn(gid: int, body: SignedAction, p: Principal = Depends(require("grn.receipt.reject")), s: Session = Depends(get_db)):
    use_reason(body.reason)
    g = masters.get_or_404(s, GRN, gid, "GRN")
    grn_svc.reject(s, g, p.user, body.password, body.reason or "")
    s.commit()
    return _grn_out(s, g, True)


@router.post("/grn/{gid}/cancel", tags=["GRN"])
def cancel_grn(gid: int, body: Reasoned, p: Principal = Depends(require("grn.receipt.cancel")), s: Session = Depends(get_db)):
    use_reason(body.reason)
    g = masters.get_or_404(s, GRN, gid, "GRN")
    grn_svc.cancel(s, g, body.reason or "")
    s.commit()
    return _grn_out(s, g)


@router.get("/grn-checklist-items", tags=["GRN"])
def checklist_items(p: Principal = Depends(require("warehouse.checklist.read")), s: Session = Depends(get_db)):
    return [to_dict(i) for i in s.execute(select(ChecklistItem).order_by(ChecklistItem.seq)).scalars()]


class ChecklistItemUpdate(Reasoned):
    model_config = {"extra": "forbid"}
    text: str | None = None
    is_critical: bool | None = None
    is_active: bool | None = None


@router.patch("/grn-checklist-items/{iid}", tags=["GRN"])
def update_checklist_item(iid: int, body: ChecklistItemUpdate, p: Principal = Depends(require("warehouse.checklist.update")), s: Session = Depends(get_db)):
    use_reason(body.reason)
    it = masters.get_or_404(s, ChecklistItem, iid, "Checklist item")
    for k, v in body.model_dump(exclude={"reason"}, exclude_unset=True).items():
        setattr(it, k, v)
    s.commit()
    return to_dict(it)


# ============================================================ lots & inventory
def _lot_out(s: Session, lot: MaterialBatch) -> dict:
    d = to_dict(lot)
    m, u = s.get(Material, lot.material_id), s.get(Unit, lot.unit_id)
    d.update(material_code=m.material_code, material_name=m.name, unit=u.code, status=lots.derived_status(s, lot),
             on_hand=float(inventory.on_hand(s, lot.id)))
    if lot.vendor_id:
        d["vendor_name"] = s.get(Vendor, lot.vendor_id).name
    return d


def _lot_query(request: Request, q: str | None):
    stmt = select(MaterialBatch)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(func.lower(MaterialBatch.lot_no).like(like) | func.lower(MaterialBatch.vendor_batch_no).like(like))
    for f in ("material_id", "disposition", "vendor_id", "source_type"):
        if request.query_params.get(f):
            stmt = stmt.where(getattr(MaterialBatch, f) == request.query_params[f])
    return stmt


@router.get("/lots", tags=["Inventory"])
def list_lots(request: Request, q: str | None = None, limit: int = Query(50), offset: int = Query(0),
              p: Principal = Depends(require("inventory.lot.read")), s: Session = Depends(get_db)):
    return _page(s, _lot_query(request, q), MaterialBatch, limit, offset, lambda l: _lot_out(s, l))


@router.get("/lots/{lid}", tags=["Inventory"])
def get_lot(lid: int, p: Principal = Depends(require("inventory.lot.read")), s: Session = Depends(get_db)):
    lot = masters.get_or_404(s, MaterialBatch, lid, "Lot")
    d = _lot_out(s, lot)
    d["balances"] = [{"location_id": b.location_id, "location": s.get(Location, b.location_id).location_code,
                      "on_hand": float(b.qty_on_hand), "reserved": float(b.qty_reserved)}
                     for b in s.execute(select(InventoryBalance).where(InventoryBalance.material_batch_id == lid, InventoryBalance.qty_on_hand > 0)).scalars()]
    d["holds"] = [to_dict(h) for h in lots.open_holds(s, "MATERIAL_BATCH", lid)]
    d["containers"] = [to_dict(c) for c in s.execute(select(MaterialContainer).where(MaterialContainer.batch_id == lid).order_by(MaterialContainer.container_no)).scalars()]
    d["reconciliation"] = inventory.lot_reconciliation(s, lot)
    d["issue_violations"] = [{"rule_id": r, "message": m} for r, m in lots.issue_violations(s, lot)]
    if lot.grn_line_id:
        gl = s.get(GRNLine, lot.grn_line_id)
        g = s.get(GRN, gl.grn_id)
        d["grn"] = {"id": g.id, "grn_no": g.grn_no, "po_id": g.po_id, "po_no": s.get(PurchaseOrder, g.po_id).po_no}
    return d


@router.get("/lots/{lid}/ledger", tags=["Inventory"])
def lot_ledger(lid: int, p: Principal = Depends(require("inventory.ledger.read")), s: Session = Depends(get_db)):
    masters.get_or_404(s, MaterialBatch, lid, "Lot")
    return [to_dict(t) for t in s.execute(select(InventoryTransaction).where(InventoryTransaction.material_batch_id == lid).order_by(InventoryTransaction.id)).scalars()]


class TransferIn(Reasoned):
    from_location_id: int
    to_location_id: int
    quantity: Decimal = Field(gt=0)
    reject_move: bool = False


@router.post("/lots/{lid}/transfer", tags=["Inventory"])
def transfer_lot(lid: int, body: TransferIn, p: Principal = Depends(require("inventory.stock.transfer")), s: Session = Depends(get_db)):
    use_reason(body.reason or "Stock transfer")
    lot = masters.get_or_404(s, MaterialBatch, lid, "Lot")
    f, t = masters.get_or_404(s, Location, body.from_location_id, "Location"), masters.get_or_404(s, Location, body.to_location_id, "Location")
    tx = inventory.transfer(s, lot, body.quantity, f, t, reason=body.reason, reject_move=body.reject_move)
    s.commit()
    return to_dict(tx)


def _stock_rows(s: Session, request: Request):
    q = (select(InventoryBalance, MaterialBatch).join(MaterialBatch, MaterialBatch.id == InventoryBalance.material_batch_id)
         .where(InventoryBalance.qty_on_hand > 0))
    for f, col in (("material_id", MaterialBatch.material_id), ("location_id", InventoryBalance.location_id), ("disposition", MaterialBatch.disposition)):
        if request.query_params.get(f):
            q = q.where(col == request.query_params[f])
    rows = []
    for b, lot in s.execute(q).all():
        m, loc = s.get(Material, lot.material_id), s.get(Location, b.location_id)
        st = lots.derived_status(s, lot)
        if request.query_params.get("status") and st != request.query_params["status"]:
            continue
        rows.append({"lot_id": lot.id, "lot_no": lot.lot_no, "material_code": m.material_code, "material_name": m.name,
                     "location": loc.location_code, "on_hand": float(b.qty_on_hand), "reserved": float(b.qty_reserved),
                     "available": float(b.qty_on_hand - b.qty_reserved), "status": st, "expiry_date": lot.expiry_date,
                     "retest_date": lot.retest_date, "vendor_batch_no": lot.vendor_batch_no, "unit": s.get(Unit, lot.unit_id).code})
    rows.sort(key=lambda r: (r["material_code"], str(r["expiry_date"] or "9999"), r["lot_no"]))
    return rows


@router.get("/inventory/stock", tags=["Inventory"])
def stock(request: Request, limit: int = Query(100), offset: int = Query(0), p: Principal = Depends(require("inventory.stock.read")),
          s: Session = Depends(get_db)):
    rows = _stock_rows(s, request)
    limit, offset = page_args(limit, offset)
    return {"items": rows[offset:offset + limit], "total": len(rows), "limit": limit, "offset": offset}


@router.get("/inventory/stock/export", tags=["Inventory"])
def stock_export(request: Request, p: Principal = Depends(require("inventory.stock.read", "inventory.stock.export")), s: Session = Depends(get_db)):
    cols = [("material_code", "Material"), ("material_name", "Name"), ("lot_no", "Lot"), ("vendor_batch_no", "Vendor batch"),
            ("location", "Location"), ("on_hand", "On hand"), ("reserved", "Reserved"), ("available", "Available"), ("unit", "UoM"),
            ("status", "Status"), ("expiry_date", "Expiry"), ("retest_date", "Retest")]
    return xlsx_response(s, p, "Stock by lot and location", {k: request.query_params.get(k) for k in ("status", "material_id", "location_id")}, cols, _stock_rows(s, request), "inventory_stock")


@router.get("/inventory/ledger", tags=["Inventory"])
def ledger(txn_type: str | None = None, before_id: int | None = None, limit: int = 100, p: Principal = Depends(require("inventory.ledger.read")),
           s: Session = Depends(get_db)):
    limit, _ = page_args(limit, 0)
    stmt = select(InventoryTransaction)
    if txn_type:
        stmt = stmt.where(InventoryTransaction.txn_type == txn_type)
    if before_id:
        stmt = stmt.where(InventoryTransaction.id < before_id)
    rows = s.execute(stmt.order_by(InventoryTransaction.id.desc()).limit(limit)).scalars().all()
    return {"items": [to_dict(t) for t in rows], "next_before_id": rows[-1].id if len(rows) == limit else None}


@router.get("/inventory/verify", tags=["Inventory"])
def verify_inventory(p: Principal = Depends(require("inventory.ledger.verify")), s: Session = Depends(get_db)):
    d = inventory.verify_ledger(s)
    return {"ok": not d, "discrepancies": d}


@router.get("/inventory/fefo-pick", tags=["Inventory"])
def fefo_pick(material_id: int, quantity: Decimal, p: Principal = Depends(require("inventory.stock.read")), s: Session = Depends(get_db)):
    return lots.pick_fefo(s, material_id, quantity)


# ============================================================ holds
class HoldIn(Reasoned):
    entity_type: str = Field(pattern="^(MATERIAL_BATCH|MFG_BATCH)$")
    record_id: int
    reason: str = Field(min_length=3)


@router.get("/holds", tags=["Quality hold"])
def list_holds(status: str | None = None, limit: int = 100, offset: int = 0, p: Principal = Depends(require("qa.hold.read")), s: Session = Depends(get_db)):
    stmt = select(QualityHold)
    if status:
        stmt = stmt.where(QualityHold.status == status)
    return _page(s, stmt, QualityHold, limit, offset)


@router.post("/holds", status_code=201, tags=["Quality hold"])
def place_hold(body: HoldIn, p: Principal = Depends(require("qa.hold.place")), s: Session = Depends(get_db)):
    use_reason(body.reason)
    h = lots.place_hold(s, body.entity_type, body.record_id, body.reason, user_id=p.user.id)
    s.commit()
    return to_dict(h)


@router.post("/holds/{hid}/release", tags=["Quality hold"])
def release_hold(hid: int, body: SignedAction, p: Principal = Depends(require("qa.hold.release")), s: Session = Depends(get_db)):
    use_reason(body.reason)
    h = masters.get_or_404(s, QualityHold, hid, "Hold")
    lots.release_hold(s, h, p.user, body.password, body.reason or "")
    s.commit()
    return to_dict(h)


# ============================================================ labels
class LabelIn(BaseModel):
    label_type: str = Field(pattern="^(QUARANTINE|APPROVED)$")
    copies: int = Field(default=1, ge=1, le=100)
    reprint_reason: str | None = None
    location_id: int | None = None


@router.post("/lots/{lid}/labels", tags=["Labels"])
def print_label(lid: int, body: LabelIn, p: Principal = Depends(require("label.lot.print")), s: Session = Depends(get_db)):
    lot = masters.get_or_404(s, MaterialBatch, lid, "Lot")
    use_reason(body.reprint_reason)
    loc = s.get(Location, body.location_id) if body.location_id else None
    if loc is None:   # default: where most of the lot is stored
        b = s.execute(select(InventoryBalance).where(InventoryBalance.material_batch_id == lid, InventoryBalance.qty_on_hand > 0)
                      .order_by(InventoryBalance.qty_on_hand.desc())).scalars().first()
        loc = s.get(Location, b.location_id) if b else None
    pdf, row = labels.print_lot_label(s, lot, body.label_type, body.copies, p.user.id, body.reprint_reason, loc)
    s.commit()
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{row.label_no}.pdf"', "X-Label-No": row.label_no})


@router.get("/lots/{lid}/labels", tags=["Labels"])
def label_history(lid: int, p: Principal = Depends(require("inventory.lot.read")), s: Session = Depends(get_db)):
    return [to_dict(l) for l in s.execute(select(MaterialLabel).where(MaterialLabel.material_batch_id == lid).order_by(MaterialLabel.id)).scalars()]


@router.post("/locations/{lid}/label", tags=["Labels"])
def location_label(lid: int, copies: int = 1, p: Principal = Depends(require("label.location.print")), s: Session = Depends(get_db)):
    loc = masters.get_or_404(s, Location, lid, "Location")
    pdf, row = labels.print_location_label(s, loc, max(1, min(copies, 10)), p.user.id)
    s.commit()
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{row.label_no}.pdf"'})


# ============================================================ temperature & destruction
class TempIn(Reasoned):
    reading: Decimal
    remarks: str | None = None


@router.post("/locations/{lid}/temperature", status_code=201, tags=["Warehouse"])
def log_temp(lid: int, body: TempIn, p: Principal = Depends(require("warehouse.temperature.create")), s: Session = Depends(get_db)):
    use_reason("Storage temperature recorded")
    loc = masters.get_or_404(s, Location, lid, "Location")
    r = warehouse_ops.log_temperature(s, loc, body.reading, p.user.id, body.remarks)
    s.commit()
    return r


@router.get("/locations/{lid}/temperature", tags=["Warehouse"])
def temp_history(lid: int, p: Principal = Depends(require("warehouse.temperature.read")), s: Session = Depends(get_db)):
    return [to_dict(t) for t in s.execute(select(StorageTemperatureLog).where(StorageTemperatureLog.location_id == lid)
                                          .order_by(StorageTemperatureLog.id.desc()).limit(200)).scalars()]


class DestrIn(Reasoned):
    material_batch_id: int
    location_id: int
    quantity: Decimal = Field(gt=0)
    method: str = Field(min_length=3)
    reason: str = Field(min_length=3)


class DestrDecision(SignedAction):
    approve: bool = True


@router.get("/destructions", tags=["Warehouse"])
def list_destr(limit: int = 100, offset: int = 0, p: Principal = Depends(require("warehouse.destruction.read")), s: Session = Depends(get_db)):
    return _page(s, select(DestructionRecord), DestructionRecord, limit, offset)


@router.post("/destructions", status_code=201, tags=["Warehouse"])
def request_destr(body: DestrIn, p: Principal = Depends(require("warehouse.destruction.create")), s: Session = Depends(get_db)):
    use_reason(body.reason)
    lot = masters.get_or_404(s, MaterialBatch, body.material_batch_id, "Lot")
    loc = masters.get_or_404(s, Location, body.location_id, "Location")
    d = warehouse_ops.request_destruction(s, p.user, lot, loc, body.quantity, body.method, body.reason)
    s.commit()
    return to_dict(d)


@router.post("/destructions/{did}/decision", tags=["Warehouse"])
def decide_destr(did: int, body: DestrDecision, p: Principal = Depends(require("warehouse.destruction.approve")), s: Session = Depends(get_db)):
    use_reason(body.reason)
    d = masters.get_or_404(s, DestructionRecord, did, "Destruction")
    warehouse_ops.decide(s, d, p.user, body.password, body.approve, body.reason or "")
    s.commit()
    return to_dict(d)


@router.post("/destructions/{did}/execute", tags=["Warehouse"])
def execute_destr(did: int, p: Principal = Depends(require("warehouse.destruction.create")), s: Session = Depends(get_db)):
    use_reason("Destruction executed")
    d = masters.get_or_404(s, DestructionRecord, did, "Destruction")
    if d.status != "APPROVED":
        from app.core.errors import BusinessRuleError
        raise BusinessRuleError("Only an APPROVED destruction can be executed", rule_id="BR-DES-003")
    warehouse_ops.execute(s, d, p.user)
    s.commit()
    return to_dict(d)


@router.post("/jobs/inventory-expiry", tags=["Jobs"])
def run_inventory_job(p: Principal = Depends(require("config.job.run")), s: Session = Depends(get_db)):
    use_reason("Scheduled job: inventory expiry (manual run)")
    expired = lots.expire_lots(s)
    alerts = lots.alert_expiry(s)
    s.commit()
    return {"expired": expired, "alerts_created": alerts}
