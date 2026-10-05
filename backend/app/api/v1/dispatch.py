"""Phase 7 endpoints: dispatch, traceability graph, global search, QR resolution."""
import json
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.crud import to_dict
from app.api.deps import Principal, get_principal, get_db, require
from app.api.helpers import page_args, use_reason
from app.core.errors import NotFound, ValidationFailed
from app.models.dispatch import Dispatch, DispatchLine
from app.models.master import Customer, Location, Material
from app.models.warehouse import MaterialBatch
from app.schemas.common import Reasoned
from app.services import dispatch as dsp
from app.services import masters, search as search_svc, traceability

router = APIRouter()


class SignedAction(Reasoned):
    password: str


class LineIn(BaseModel):
    material_batch_id: int
    location_id: int
    quantity: Decimal = Field(gt=0)


class DispatchIn(Reasoned):
    customer_id: int
    dispatch_date: date | None = None
    invoice_no: str | None = None
    transporter: str | None = None
    vehicle_no: str | None = None
    lr_no: str | None = None
    shipping_address: str | None = None
    remarks: str | None = None
    lines: list[LineIn]


class DispatchUpdate(Reasoned):
    model_config = {"extra": "forbid"}
    dispatch_date: date | None = None
    invoice_no: str | None = None
    transporter: str | None = None
    vehicle_no: str | None = None
    lr_no: str | None = None
    shipping_address: str | None = None
    remarks: str | None = None
    lines: list[LineIn] | None = None


def _out(s: Session, d: Dispatch, detail: bool = False) -> dict:
    out = to_dict(d, exclude={"validation_snapshot"})
    c = s.get(Customer, d.customer_id)
    out.update(customer_code=c.customer_code, customer_name=c.name)
    if detail:
        lines = []
        for ln in dsp.dispatch_lines(s, d.id):
            lot = s.get(MaterialBatch, ln.material_batch_id)
            m = s.get(Material, lot.material_id)
            loc = s.get(Location, ln.location_id)
            lines.append({**to_dict(ln), "lot_no": lot.lot_no, "material_code": m.material_code, "material_name": m.name, "expiry_date": lot.expiry_date.isoformat() if lot.expiry_date else None,
                          "location": loc.location_code})
        out["lines"] = lines
        out["validation"] = json.loads(d.validation_snapshot) if d.validation_snapshot else None
    return out


def _get(s: Session, did: int) -> Dispatch:
    return masters.get_or_404(s, Dispatch, did, "Dispatch")


@router.get("/dispatches", tags=["Dispatch"])
def list_dispatches(request: Request, q: str | None = None, limit: int = Query(50), offset: int = Query(0),
                    p: Principal = Depends(require("dispatch.order.read")), s: Session = Depends(get_db)):
    limit, offset = page_args(limit, offset)
    stmt = select(Dispatch)
    if q:
        stmt = stmt.where(func.lower(Dispatch.dispatch_no).like(f"%{q.lower()}%") | func.lower(Dispatch.invoice_no).like(f"%{q.lower()}%"))
    for f in ("status", "customer_id"):
        if request.query_params.get(f):
            stmt = stmt.where(getattr(Dispatch, f) == request.query_params[f])
    total = s.execute(select(func.count()).select_from(stmt.subquery())).scalar()
    rows = s.execute(stmt.order_by(Dispatch.id.desc()).limit(limit).offset(offset)).scalars().all()
    return {"items": [_out(s, r) for r in rows], "total": total, "limit": limit, "offset": offset}


@router.post("/dispatches", status_code=201, tags=["Dispatch"])
def create_dispatch(body: DispatchIn, p: Principal = Depends(require("dispatch.order.create")), s: Session = Depends(get_db)):
    use_reason(body.reason or "Dispatch created")
    header = body.model_dump(exclude={"reason", "lines"}, exclude_none=True)
    d = dsp.create(s, p.user, header, [x.model_dump() for x in body.lines])
    s.commit()
    return _out(s, d, True)


@router.get("/dispatches/{did}", tags=["Dispatch"])
def get_dispatch(did: int, p: Principal = Depends(require("dispatch.order.read")), s: Session = Depends(get_db)):
    return _out(s, _get(s, did), True)


@router.patch("/dispatches/{did}", tags=["Dispatch"])
def update_dispatch(did: int, body: DispatchUpdate, p: Principal = Depends(require("dispatch.order.update")), s: Session = Depends(get_db)):
    use_reason(body.reason or "Dispatch updated")
    d = _get(s, did)
    data = body.model_dump(exclude={"reason", "lines"}, exclude_unset=True)
    for k, v in data.items():
        setattr(d, k, v)
    if body.lines is not None:
        dsp.set_lines(s, d, [x.model_dump() for x in body.lines])
    s.commit()
    return _out(s, d, True)


@router.get("/dispatches/{did}/check", tags=["Dispatch"])
def check_dispatch(did: int, p: Principal = Depends(require("dispatch.order.read")), s: Session = Depends(get_db)):
    """Dry run of the dispatch rules (BR-DSP-001..006) without changing anything."""
    from dataclasses import asdict
    v = dsp.validate(s, _get(s, did))
    return {"allowed": not dsp.blocks(v), "violations": [asdict(x) for x in v]}


@router.post("/dispatches/{did}/validate", tags=["Dispatch"])
def validate_dispatch(did: int, p: Principal = Depends(require("dispatch.order.validate")), s: Session = Depends(get_db)):
    d = _get(s, did)
    dsp.submit_validation(s, d)
    s.commit()
    return _out(s, d, True)


@router.post("/dispatches/{did}/reopen", tags=["Dispatch"])
def reopen_dispatch(did: int, body: Reasoned, p: Principal = Depends(require("dispatch.order.update")), s: Session = Depends(get_db)):
    use_reason(body.reason)
    d = _get(s, did)
    dsp.reopen(s, d, body.reason or "")
    s.commit()
    return _out(s, d, True)


@router.post("/dispatches/{did}/approve", tags=["Dispatch"])
def approve_dispatch(did: int, body: SignedAction, p: Principal = Depends(require("dispatch.order.approve")), s: Session = Depends(get_db)):
    use_reason(body.reason)
    d = _get(s, did)
    dsp.approve(s, d, p.user, body.password, body.reason or "")
    s.commit()
    return _out(s, d, True)


@router.post("/dispatches/{did}/dispatch", tags=["Dispatch"])
def execute_dispatch(did: int, p: Principal = Depends(require("dispatch.order.dispatch")), s: Session = Depends(get_db)):
    d = _get(s, did)
    dsp.dispatch(s, d, p.user)
    s.commit()
    return _out(s, d, True)


class DeliverIn(Reasoned):
    remarks: str | None = None


@router.post("/dispatches/{did}/deliver", tags=["Dispatch"])
def deliver_dispatch(did: int, body: DeliverIn, p: Principal = Depends(require("dispatch.order.deliver")), s: Session = Depends(get_db)):
    d = _get(s, did)
    dsp.deliver(s, d, body.remarks)
    s.commit()
    return _out(s, d, True)


@router.post("/dispatches/{did}/cancel", tags=["Dispatch"])
def cancel_dispatch(did: int, body: Reasoned, p: Principal = Depends(require("dispatch.order.cancel")), s: Session = Depends(get_db)):
    use_reason(body.reason)
    d = _get(s, did)
    dsp.cancel(s, d, body.reason or "")
    s.commit()
    return _out(s, d)


@router.get("/fg/available", tags=["Dispatch"])
def fg_available(p: Principal = Depends(require("dispatch.order.read")), s: Session = Depends(get_db)):
    """Released finished-goods stock that is dispatchable now (APPROVED, unexpired, not held)."""
    from app.models.master import MaterialType
    from app.models.warehouse import InventoryBalance
    from app.services import lots
    rows = s.execute(select(MaterialBatch, InventoryBalance, Material).join(InventoryBalance, InventoryBalance.material_batch_id == MaterialBatch.id)
                     .join(Material, Material.id == MaterialBatch.material_id).join(MaterialType, MaterialType.id == Material.type_id)
                     .where(MaterialType.code == "FG", MaterialBatch.disposition == "APPROVED", InventoryBalance.qty_on_hand - InventoryBalance.qty_reserved > 0)
                     .order_by(MaterialBatch.expiry_date)).all()
    out = []
    for lot, bal, m in rows:
        if lots.issue_violations(s, lot):
            continue
        out.append({"lot_id": lot.id, "lot_no": lot.lot_no, "material_code": m.material_code, "material_name": m.name, "location_id": bal.location_id,
                    "available": float(bal.qty_on_hand - bal.qty_reserved), "expiry_date": lot.expiry_date.isoformat() if lot.expiry_date else None})
    return out


# ============================================================ traceability / search / QR
@router.get("/trace/{entity}/{ref}", tags=["Traceability"])
def trace(entity: str, ref: str, direction: str = "both", p: Principal = Depends(require("trace.record.read")), s: Session = Depends(get_db)):
    root = traceability.resolve(s, entity, ref)
    return traceability.trace(s, root, direction)


@router.get("/search", tags=["Search"])
def global_search(q: str, p: Principal = Depends(get_principal), s: Session = Depends(get_db)):
    return search_svc.search(s, q, p.perms)


@router.get("/qr/resolve", tags=["Search"])
def qr_resolve(code: str, p: Principal = Depends(get_principal), s: Session = Depends(get_db)):
    r = search_svc.resolve_qr(s, code)
    if r is None:
        raise NotFound("No record matches this code")
    return r
