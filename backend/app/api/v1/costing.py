"""Phase 11c endpoints: costing."""
from decimal import Decimal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.crud import to_dict
from app.api.deps import Principal, get_db, require
from app.api.helpers import page_args, use_reason
from app.models.costing import BatchCost, CostRateCard, LotCost, StandardCost
from app.models.manufacturing import ManufacturingBatch
from app.models.master import Material
from app.models.warehouse import MaterialBatch
from app.schemas.common import Reasoned
from app.services import costing as svc, masters, versioning

router = APIRouter(prefix="/costing", tags=["Costing"])


class SignedAction(Reasoned):
    password: str


def _page(s, stmt, Model, limit, offset, conv=to_dict):
    limit, offset = page_args(limit, offset)
    total = s.execute(select(func.count()).select_from(stmt.subquery())).scalar()
    rows = s.execute(stmt.order_by(Model.id.desc()).limit(limit).offset(offset)).scalars().all()
    return {"items": [conv(r) for r in rows], "total": total, "limit": limit, "offset": offset}


# ------------------------------------------------------------ rate cards
class CardIn(Reasoned):
    title: str = Field(min_length=3, max_length=200)
    currency: str = Field(default="INR", min_length=3, max_length=3)
    labour_rate_per_hour: Decimal = Field(ge=0)
    machine_rate_per_hour: Decimal = Field(ge=0)
    overhead_pct: Decimal = Field(default=0, ge=0, le=1000)
    card_no: str | None = None


class CardUpdate(Reasoned):
    model_config = {"extra": "forbid"}
    title: str | None = None
    currency: str | None = None
    labour_rate_per_hour: Decimal | None = Field(default=None, ge=0)
    machine_rate_per_hour: Decimal | None = Field(default=None, ge=0)
    overhead_pct: Decimal | None = Field(default=None, ge=0, le=1000)


def _card(s, cid):
    return masters.get_or_404(s, CostRateCard, cid, "Cost rate card")


@router.get("/rate-cards")
def list_cards(limit: int = Query(50), offset: int = Query(0), p: Principal = Depends(require("costing.rate.read")), s: Session = Depends(get_db)):
    return _page(s, select(CostRateCard), CostRateCard, limit, offset)


@router.post("/rate-cards", status_code=201)
def create_card(body: CardIn, p: Principal = Depends(require("costing.rate.create")), s: Session = Depends(get_db)):
    use_reason(body.reason or "Cost rate card created")
    x = versioning.create_draft(s, CostRateCard, body.model_dump(exclude={"reason", "card_no"}), body.card_no)
    s.commit()
    return to_dict(x)


@router.get("/rate-cards/{cid}")
def get_card(cid: int, p: Principal = Depends(require("costing.rate.read")), s: Session = Depends(get_db)):
    return to_dict(_card(s, cid))


@router.patch("/rate-cards/{cid}")
def update_card(cid: int, body: CardUpdate, p: Principal = Depends(require("costing.rate.update")), s: Session = Depends(get_db)):
    use_reason(body.reason)
    x = _card(s, cid)
    for k, v in body.model_dump(exclude={"reason"}, exclude_unset=True).items():
        setattr(x, k, v)
    s.commit()
    return to_dict(x)


@router.post("/rate-cards/{cid}/submit")
def submit_card(cid: int, p: Principal = Depends(require("costing.rate.update")), s: Session = Depends(get_db)):
    x = _card(s, cid)
    versioning.submit(s, x)
    s.commit()
    return to_dict(x)


@router.post("/rate-cards/{cid}/approve")
def approve_card(cid: int, body: SignedAction, p: Principal = Depends(require("costing.rate.approve")), s: Session = Depends(get_db)):
    use_reason(body.reason)
    x = _card(s, cid)
    versioning.approve(s, x, p.user, body.password, body.reason or "")
    s.commit()
    return to_dict(x)


@router.post("/rate-cards/{cid}/new-version", status_code=201)
def new_card_version(cid: int, body: Reasoned, p: Principal = Depends(require("costing.rate.create")), s: Session = Depends(get_db)):
    use_reason(body.reason)
    new = versioning.new_version(s, _card(s, cid), body.reason or "")
    s.commit()
    return to_dict(new)


# ------------------------------------------------------------ standard cost
class StandardIn(Reasoned):
    material_id: int
    std_unit_cost: Decimal = Field(ge=0)
    remarks: str | None = None


@router.get("/standards")
def list_standards(limit: int = Query(100), offset: int = Query(0), p: Principal = Depends(require("costing.standard.read")), s: Session = Depends(get_db)):
    def conv(r):
        m = s.get(Material, r.material_id)
        return {**to_dict(r), "material_name": m.name if m else None}
    return _page(s, select(StandardCost), StandardCost, limit, offset, conv)


@router.put("/standards")
def set_standard(body: StandardIn, p: Principal = Depends(require("costing.standard.update")), s: Session = Depends(get_db)):
    use_reason(body.reason)
    x = svc.set_standard(s, body.material_id, body.std_unit_cost, body.remarks)
    s.commit()
    return to_dict(x)


# ------------------------------------------------------------ lot cost
class LotCostIn(Reasoned):
    unit_cost: Decimal = Field(ge=0)


@router.get("/lots/{lot_id}")
def lot_cost(lot_id: int, p: Principal = Depends(require("costing.lot.read")), s: Session = Depends(get_db)):
    masters.get_or_404(s, MaterialBatch, lot_id, "Lot")
    rows = s.execute(select(LotCost).where(LotCost.material_batch_id == lot_id).order_by(LotCost.id)).scalars().all()
    return {"current": to_dict(rows[-1]) if rows else None, "history": [to_dict(r) for r in rows]}


@router.post("/lots/{lot_id}/cost", status_code=201)
def set_lot_cost(lot_id: int, body: LotCostIn, p: Principal = Depends(require("costing.lot.set")), s: Session = Depends(get_db)):
    use_reason(body.reason)
    lot = masters.get_or_404(s, MaterialBatch, lot_id, "Lot")
    row = svc.set_lot_cost(s, lot, body.unit_cost, body.reason or "", p.user.id)
    s.commit()
    return to_dict(row)


# ------------------------------------------------------------ batch cost
class CalcIn(Reasoned):
    labour_hours: Decimal = Field(ge=0)
    machine_hours: Decimal = Field(ge=0)


def _bc_out(s: Session, x: BatchCost, detail: bool = False) -> dict:
    out = to_dict(x, exclude={"lines_snapshot"})
    b = s.get(ManufacturingBatch, x.batch_id)
    out["batch_no"] = b.batch_no if b else None
    if detail:
        out["lines"] = svc.lines(x)
    return out


def _bc(s, bid):
    return masters.get_or_404(s, BatchCost, bid, "Batch cost")


@router.get("/batch-costs")
def list_batch_costs(request: Request, limit: int = Query(50), offset: int = Query(0), p: Principal = Depends(require("costing.batch.read")), s: Session = Depends(get_db)):
    stmt = select(BatchCost)
    if request.query_params.get("status"):
        stmt = stmt.where(BatchCost.status == request.query_params["status"])
    return _page(s, stmt, BatchCost, limit, offset, lambda r: _bc_out(s, r))


@router.post("/batches/{batch_id}/calculate")
def calculate(batch_id: int, body: CalcIn, p: Principal = Depends(require("costing.batch.calculate")), s: Session = Depends(get_db)):
    use_reason(body.reason or "Batch cost calculated")
    b = masters.get_or_404(s, ManufacturingBatch, batch_id, "Batch")
    x = svc.calculate(s, p.user, b, body.labour_hours, body.machine_hours)
    s.commit()
    return _bc_out(s, x, True)


@router.get("/batch-costs/{bid}")
def get_batch_cost(bid: int, p: Principal = Depends(require("costing.batch.read")), s: Session = Depends(get_db)):
    return _bc_out(s, _bc(s, bid), True)


@router.post("/batch-costs/{bid}/approve")
def approve_batch_cost(bid: int, body: SignedAction, p: Principal = Depends(require("costing.batch.approve")), s: Session = Depends(get_db)):
    use_reason(body.reason)
    x = _bc(s, bid)
    svc.approve(s, x, p.user, body.password, body.reason or "")
    s.commit()
    return _bc_out(s, x, True)


@router.get("/valuation")
def valuation(p: Principal = Depends(require("costing.valuation.read")), s: Session = Depends(get_db)):
    return svc.valuation(s)
