"""Phase 6 / 6b endpoints: BOM, manufacturing batches, issue/return, process execution, IPC, reconciliation, output, antisera."""
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.crud import to_dict
from app.api.deps import Principal, get_db, require
from app.api.helpers import page_args, use_reason
from app.core.errors import NotFound, PermissionDenied, ValidationFailed
from app.models.manufacturing import (Animal, BatchEquipmentUse, BatchMaterial, BatchReconciliation, BatchStepExecution, BleedRecord, BOMHeader,
                                      ImmunisationRecord, IPCResult, ManufacturingBatch, MaterialIssue, MaterialIssueIndent, MaterialReturn, PlasmaPool)
from app.models.master import Location, Material
from app.models.warehouse import MaterialBatch
from app.schemas.common import Reasoned
from app.services import antisera, lots, manufacturing as mfg, masters, versioning
import json

router = APIRouter()


class SignedAction(Reasoned):
    password: str


def _page(s, stmt, Model, limit, offset):
    limit, offset = page_args(limit, offset)
    total = s.execute(select(func.count()).select_from(stmt.subquery())).scalar()
    rows = s.execute(stmt.order_by(Model.id.desc()).limit(limit).offset(offset)).scalars().all()
    return rows, total, limit, offset


# ============================================================ BOM
class BomLineIn(BaseModel):
    material_id: int
    quantity: Decimal = Field(gt=0)
    unit_id: int | None = None
    process_loss_pct: Decimal = Field(default=Decimal(0), ge=0, le=100)
    overage_pct: Decimal = Field(default=Decimal(0), ge=0, le=100)
    sampling_qty: Decimal = Field(default=Decimal(0), ge=0)
    reconcile: bool = True


class MbrStepIn(BaseModel):
    stage: str | None = None
    instruction: str = Field(min_length=3, max_length=1000)
    requires_verification: bool = True
    requires_value: bool = False


class BomIn(Reasoned):
    bom_no: str | None = None
    product_material_id: int
    batch_size: Decimal = Field(gt=0)
    unit_id: int
    expected_yield_pct: Decimal = Decimal(100)
    yield_min_pct: Decimal | None = None
    yield_max_pct: Decimal | None = None
    description: str | None = None
    lines: list[BomLineIn] = []
    steps: list[MbrStepIn] = []


class BomUpdate(Reasoned):
    model_config = {"extra": "forbid"}
    batch_size: Decimal | None = Field(default=None, gt=0)
    expected_yield_pct: Decimal | None = None
    yield_min_pct: Decimal | None = None
    yield_max_pct: Decimal | None = None
    description: str | None = None


def _bom_out(s: Session, b: BOMHeader, detail: bool = False) -> dict:
    d = to_dict(b)
    prod = s.get(Material, b.product_material_id)
    d.update(product_code=prod.material_code, product_name=prod.name)
    if detail:
        lines = []
        for ln in mfg.bom_lines(s, b.id):
            m = s.get(Material, ln.material_id)
            lines.append({**to_dict(ln), "material_code": m.material_code, "material_name": m.name})
        d["lines"] = lines
        d["steps"] = [to_dict(x) for x in mfg.bom_steps(s, b.id)]
        d["versions"] = [{"id": v.id, "version_no": v.version_no, "status": v.status, "change_reason": v.change_reason} for v in versioning.history(s, b)]
    return d


@router.get("/boms", tags=["BOM"])
def list_boms(request: Request, q: str | None = None, limit: int = Query(50), offset: int = Query(0),
              p: Principal = Depends(require("md.bom.read")), s: Session = Depends(get_db)):
    stmt = select(BOMHeader)
    if q:
        stmt = stmt.where(func.lower(BOMHeader.bom_no).like(f"%{q.lower()}%"))
    if request.query_params.get("status"):
        stmt = stmt.where(BOMHeader.status == request.query_params["status"])
    if request.query_params.get("product_material_id"):
        stmt = stmt.where(BOMHeader.product_material_id == int(request.query_params["product_material_id"]))
    rows, total, limit, offset = _page(s, stmt, BOMHeader, limit, offset)
    return {"items": [_bom_out(s, r) for r in rows], "total": total, "limit": limit, "offset": offset}


@router.post("/boms", status_code=201, tags=["BOM"])
def create_bom(body: BomIn, p: Principal = Depends(require("md.bom.create")), s: Session = Depends(get_db)):
    use_reason(body.reason)
    header = body.model_dump(include={"product_material_id", "batch_size", "unit_id", "expected_yield_pct", "yield_min_pct", "yield_max_pct", "description"}, exclude_none=True)
    bom = mfg.create_bom(s, header, [x.model_dump() for x in body.lines], [x.model_dump() for x in body.steps], body.bom_no)
    s.commit()
    return _bom_out(s, bom, True)


@router.get("/boms/{bid}", tags=["BOM"])
def get_bom(bid: int, p: Principal = Depends(require("md.bom.read")), s: Session = Depends(get_db)):
    return _bom_out(s, masters.get_or_404(s, BOMHeader, bid, "BOM"), True)


@router.patch("/boms/{bid}", tags=["BOM"])
def update_bom(bid: int, body: BomUpdate, p: Principal = Depends(require("md.bom.update")), s: Session = Depends(get_db)):
    use_reason(body.reason)
    b = masters.get_or_404(s, BOMHeader, bid, "BOM")
    for k, v in body.model_dump(exclude={"reason"}, exclude_unset=True).items():
        setattr(b, k, v)
    s.commit()
    return _bom_out(s, b, True)


class BomLinesIn(Reasoned):
    lines: list[BomLineIn]


class BomStepsIn(Reasoned):
    steps: list[MbrStepIn]


@router.put("/boms/{bid}/lines", tags=["BOM"])
def put_lines(bid: int, body: BomLinesIn, p: Principal = Depends(require("md.bom.update")), s: Session = Depends(get_db)):
    use_reason(body.reason)
    b = masters.get_or_404(s, BOMHeader, bid, "BOM")
    mfg.set_bom_lines(s, b, [x.model_dump() for x in body.lines])
    s.commit()
    return _bom_out(s, b, True)


@router.put("/boms/{bid}/steps", tags=["BOM"])
def put_steps(bid: int, body: BomStepsIn, p: Principal = Depends(require("md.bom.update")), s: Session = Depends(get_db)):
    use_reason(body.reason)
    b = masters.get_or_404(s, BOMHeader, bid, "BOM")
    mfg.set_mbr_steps(s, b, [x.model_dump() for x in body.steps])
    s.commit()
    return _bom_out(s, b, True)


@router.post("/boms/{bid}/submit", tags=["BOM"])
def submit_bom(bid: int, p: Principal = Depends(require("md.bom.update")), s: Session = Depends(get_db)):
    b = masters.get_or_404(s, BOMHeader, bid, "BOM")
    mfg.submit_bom(s, b)
    s.commit()
    return _bom_out(s, b)


@router.post("/boms/{bid}/return", tags=["BOM"])
def return_bom(bid: int, body: Reasoned, p: Principal = Depends(require("md.bom.update")), s: Session = Depends(get_db)):
    use_reason(body.reason)
    b = masters.get_or_404(s, BOMHeader, bid, "BOM")
    versioning.return_to_draft(s, b, body.reason or "")
    s.commit()
    return _bom_out(s, b)


@router.post("/boms/{bid}/approve", tags=["BOM"])
def approve_bom(bid: int, body: SignedAction, p: Principal = Depends(require("md.bom.approve")), s: Session = Depends(get_db)):
    use_reason(body.reason)
    b = masters.get_or_404(s, BOMHeader, bid, "BOM")
    mfg.approve_bom(s, b, p.user, body.password, body.reason or "")
    s.commit()
    return _bom_out(s, b)


@router.post("/boms/{bid}/new-version", status_code=201, tags=["BOM"])
def new_bom_version(bid: int, body: Reasoned, p: Principal = Depends(require("md.bom.create")), s: Session = Depends(get_db)):
    use_reason(body.reason)
    b = masters.get_or_404(s, BOMHeader, bid, "BOM")
    new = versioning.new_version(s, b, body.reason or "")
    s.commit()
    return _bom_out(s, new, True)


@router.get("/products/{pid}/bom-in-force", tags=["BOM"])
def bom_in_force(pid: int, p: Principal = Depends(require("md.bom.read")), s: Session = Depends(get_db)):
    b = mfg.bom_in_force(s, pid)
    if b is None:
        raise NotFound("No approved BOM is in force for this product")
    return _bom_out(s, b, True)


# ============================================================ batches
class BatchIn(Reasoned):
    product_material_id: int
    planned_qty: Decimal = Field(gt=0)
    batch_no: str | None = None


def _batch_out(s: Session, b: ManufacturingBatch, detail: bool = False) -> dict:
    d = to_dict(b)
    m = s.get(Material, b.product_material_id)
    d.update(product_code=m.material_code, product_name=m.name, on_hold=lots.has_open_hold(s, "MFG_BATCH", b.id))
    if detail:
        bom = s.get(BOMHeader, b.bom_id)
        d["bom"] = {"id": bom.id, "bom_no": bom.bom_no, "version_no": bom.version_no, "batch_size": float(bom.batch_size)}
        ind = s.execute(select(MaterialIssueIndent).where(MaterialIssueIndent.batch_id == b.id)).scalar_one_or_none()
        d["indent"] = to_dict(ind) if ind else None
        mats = []
        for bm in mfg.batch_materials(s, b.id):
            mm = s.get(Material, bm.material_id)
            mats.append({**to_dict(bm), "material_code": mm.material_code, "material_name": mm.name})
        d["materials"] = mats
        issues = []
        for i in s.execute(select(MaterialIssue).where(MaterialIssue.batch_id == b.id).order_by(MaterialIssue.id)).scalars():
            lot = s.get(MaterialBatch, i.material_batch_id)
            issues.append({**to_dict(i), "lot_no": lot.lot_no, "material_id": lot.material_id})
        d["issues"] = issues
        d["returns"] = [to_dict(r) for r in s.execute(select(MaterialReturn).where(MaterialReturn.batch_id == b.id).order_by(MaterialReturn.id)).scalars()]
        d["steps"] = [to_dict(x) for x in s.execute(select(BatchStepExecution).where(BatchStepExecution.batch_id == b.id).order_by(BatchStepExecution.step_no)).scalars()]
        d["equipment"] = [to_dict(x) for x in s.execute(select(BatchEquipmentUse).where(BatchEquipmentUse.batch_id == b.id)).scalars()]
        d["ipc"] = [to_dict(x) for x in s.execute(select(IPCResult).where(IPCResult.batch_id == b.id).order_by(IPCResult.id)).scalars()]
        rec = s.execute(select(BatchReconciliation).where(BatchReconciliation.batch_id == b.id)).scalar_one_or_none()
        d["reconciliation"] = _recon_out(rec) if rec else None
        d["holds"] = [to_dict(h) for h in lots.open_holds(s, "MFG_BATCH", b.id)]
        if b.output_lot_id:
            lot = s.get(MaterialBatch, b.output_lot_id)
            d["output_lot"] = {"id": lot.id, "lot_no": lot.lot_no, "disposition": lot.disposition}
    return d


def _recon_out(rec: BatchReconciliation) -> dict:
    d = to_dict(rec)
    d["summary"] = json.loads(d.pop("summary_json"))
    return d


def _batch(s: Session, bid: int) -> ManufacturingBatch:
    return masters.get_or_404(s, ManufacturingBatch, bid, "Batch")


@router.get("/mfg/batches", tags=["Manufacturing"])
def list_batches(request: Request, q: str | None = None, limit: int = Query(50), offset: int = Query(0),
                 p: Principal = Depends(require("mfg.batch.read")), s: Session = Depends(get_db)):
    stmt = select(ManufacturingBatch)
    if q:
        stmt = stmt.where(func.lower(ManufacturingBatch.batch_no).like(f"%{q.lower()}%"))
    for f in ("status", "batch_type", "product_material_id"):
        if request.query_params.get(f):
            stmt = stmt.where(getattr(ManufacturingBatch, f) == request.query_params[f])
    rows, total, limit, offset = _page(s, stmt, ManufacturingBatch, limit, offset)
    return {"items": [_batch_out(s, r) for r in rows], "total": total, "limit": limit, "offset": offset}


@router.post("/mfg/batches", status_code=201, tags=["Manufacturing"])
def create_batch(body: BatchIn, p: Principal = Depends(require("mfg.batch.create")), s: Session = Depends(get_db)):
    use_reason(body.reason)
    b = mfg.create_batch(s, p.user, body.product_material_id, body.planned_qty, batch_no=body.batch_no, override_reason=body.reason,
                         can_override="mfg.batch.override_number" in p.perms)
    s.commit()
    return _batch_out(s, b, True)


@router.get("/mfg/batches/{bid}", tags=["Manufacturing"])
def get_batch(bid: int, p: Principal = Depends(require("mfg.batch.read")), s: Session = Depends(get_db)):
    return _batch_out(s, _batch(s, bid), True)


@router.post("/mfg/batches/{bid}/cancel", tags=["Manufacturing"])
def cancel_batch(bid: int, body: Reasoned, p: Principal = Depends(require("mfg.batch.cancel")), s: Session = Depends(get_db)):
    use_reason(body.reason)
    if not (body.reason or "").strip():
        raise ValidationFailed("A reason is required", code="REASON_REQUIRED")
    b = _batch(s, bid)
    mfg.cancel_batch(s, b, body.reason)
    s.commit()
    return _batch_out(s, b)


@router.get("/mfg/batches/{bid}/release-readiness", tags=["Manufacturing"])
def batch_readiness(bid: int, p: Principal = Depends(require("mfg.batch.release_check")), s: Session = Depends(get_db)):
    b = _batch(s, bid)
    problems = []
    if b.status != "QC_QA":
        problems.append(f"Batch is {b.status}, not QC_QA")
    if b.output_lot_id:
        problems += mfg.conditional_material_problems(s, s.get(MaterialBatch, b.output_lot_id))
    return {"ready": not problems, "problems": problems}


# ---- issue
class IssueIn(Reasoned):
    batch_material_id: int
    material_batch_id: int
    location_id: int
    quantity: Decimal = Field(gt=0)
    fefo_override_reason: str | None = None
    additional: bool = False


@router.get("/mfg/batches/{bid}/fefo-suggestion", tags=["Manufacturing"])
def fefo_suggestion(bid: int, batch_material_id: int, quantity: Decimal | None = None, p: Principal = Depends(require("mfg.issue.read")),
                    s: Session = Depends(get_db)):
    b = _batch(s, bid)
    bm = s.get(BatchMaterial, batch_material_id)
    if bm is None or bm.batch_id != b.id:
        raise NotFound("Requirement not found")
    qty = quantity if quantity is not None else bm.required_qty - bm.issued_qty
    if qty <= 0:
        return []
    return lots.pick_fefo(s, bm.material_id, qty)


@router.post("/mfg/batches/{bid}/issue", status_code=201, tags=["Manufacturing"])
def issue(bid: int, body: IssueIn, p: Principal = Depends(require("mfg.issue.create")), s: Session = Depends(get_db)):
    use_reason(body.reason)
    if body.additional and "mfg.issue.additional" not in p.perms:
        raise PermissionDenied("Additional issue needs the 'mfg.issue.additional' permission")
    b = _batch(s, bid)
    bm = masters.get_or_404(s, BatchMaterial, body.batch_material_id, "Requirement")
    lot = masters.get_or_404(s, MaterialBatch, body.material_batch_id, "Lot")
    iss = mfg.issue_material(s, p.user, b, bm, lot, body.location_id, body.quantity, fefo_override_reason=body.fefo_override_reason or None,
                             additional=body.additional)
    s.commit()
    return to_dict(iss)


# ---- returns
class ReturnIn(Reasoned):
    issue_id: int
    returned_qty: Decimal = Field(gt=0)
    used_qty: Decimal = Field(default=Decimal(0), ge=0)
    damaged_qty: Decimal = Field(default=Decimal(0), ge=0)
    location_id: int


class ReturnDecision(Reasoned):
    accept: bool
    comment: str = Field(min_length=3)


@router.post("/mfg/returns", status_code=201, tags=["Manufacturing"])
def request_return(body: ReturnIn, p: Principal = Depends(require("mfg.return.request")), s: Session = Depends(get_db)):
    use_reason(body.reason)
    iss = masters.get_or_404(s, MaterialIssue, body.issue_id, "Issue")
    loc = masters.get_or_404(s, Location, body.location_id, "Location")
    r = mfg.request_return(s, p.user, iss, body.returned_qty, body.used_qty, body.damaged_qty, loc, body.reason or "")
    s.commit()
    return to_dict(r)


@router.get("/mfg/returns", tags=["Manufacturing"])
def list_returns(request: Request, limit: int = Query(50), offset: int = Query(0), p: Principal = Depends(require("mfg.return.read")), s: Session = Depends(get_db)):
    stmt = select(MaterialReturn)
    if request.query_params.get("status"):
        stmt = stmt.where(MaterialReturn.status == request.query_params["status"])
    rows, total, limit, offset = _page(s, stmt, MaterialReturn, limit, offset)
    return {"items": [to_dict(r) for r in rows], "total": total, "limit": limit, "offset": offset}


@router.post("/mfg/returns/{rid}/decide", tags=["Manufacturing"])
def decide_return(rid: int, body: ReturnDecision, p: Principal = Depends(require("mfg.return.accept")), s: Session = Depends(get_db)):
    use_reason(body.reason or body.comment)
    r = masters.get_or_404(s, MaterialReturn, rid, "Return")
    mfg.accept_return(s, p.user, r, body.accept, body.comment)
    s.commit()
    return to_dict(r)


# ---- process
@router.post("/mfg/batches/{bid}/start", tags=["Manufacturing"])
def start(bid: int, body: SignedAction, p: Principal = Depends(require("mfg.step.execute")), s: Session = Depends(get_db)):
    use_reason(body.reason)
    b = _batch(s, bid)
    mfg.start_processing(s, p.user, b, body.password, body.reason or "Line clearance confirmed")
    s.commit()
    return _batch_out(s, b, True)


class EquipmentUseIn(BaseModel):
    equipment_id: int
    cleaning_confirmed: bool


@router.post("/mfg/batches/{bid}/equipment", status_code=201, tags=["Manufacturing"])
def use_equipment(bid: int, body: EquipmentUseIn, p: Principal = Depends(require("mfg.equipment.use")), s: Session = Depends(get_db)):
    b = _batch(s, bid)
    u = mfg.use_equipment(s, p.user, b, body.equipment_id, body.cleaning_confirmed)
    s.commit()
    return to_dict(u)


class StepExec(Reasoned):
    value: str | None = None
    remarks: str | None = None


@router.post("/mfg/batches/{bid}/steps/{step_no}/execute", tags=["Manufacturing"])
def execute_step(bid: int, step_no: int, body: StepExec, p: Principal = Depends(require("mfg.step.execute")), s: Session = Depends(get_db)):
    b = _batch(s, bid)
    st = mfg.execute_step(s, p.user, b, step_no, body.value, body.remarks)
    s.commit()
    return to_dict(st)


@router.post("/mfg/batches/{bid}/steps/{step_no}/verify", tags=["Manufacturing"])
def verify_step(bid: int, step_no: int, body: SignedAction, p: Principal = Depends(require("mfg.step.verify")), s: Session = Depends(get_db)):
    use_reason(body.reason)
    b = _batch(s, bid)
    st = mfg.verify_step(s, p.user, b, step_no, body.password)
    s.commit()
    return to_dict(st)


class IPCIn(BaseModel):
    stage: str = Field(min_length=1, max_length=60)
    parameter: str = Field(min_length=1, max_length=100)
    value: Decimal | None = None
    text: str | None = None
    lsl: Decimal | None = None
    usl: Decimal | None = None
    equipment_id: int | None = None
    remarks: str | None = None


@router.post("/mfg/batches/{bid}/ipc", status_code=201, tags=["Manufacturing"])
def record_ipc(bid: int, body: IPCIn, p: Principal = Depends(require("mfg.ipc.create")), s: Session = Depends(get_db)):
    b = _batch(s, bid)
    r = mfg.record_ipc(s, p.user, b, body.stage, body.parameter, value=body.value, text=body.text, lsl=body.lsl, usl=body.usl,
                       equipment_id=body.equipment_id, remarks=body.remarks)
    s.commit()
    return to_dict(r)


class CompleteIn(Reasoned):
    actual_qty: Decimal = Field(gt=0)


@router.post("/mfg/batches/{bid}/complete", tags=["Manufacturing"])
def complete(bid: int, body: CompleteIn, p: Principal = Depends(require("mfg.step.execute")), s: Session = Depends(get_db)):
    use_reason(body.reason)
    b = _batch(s, bid)
    mfg.complete_production(s, p.user, b, body.actual_qty)
    s.commit()
    return _batch_out(s, b, True)


# ---- reconciliation
class ConsumptionEntry(BaseModel):
    batch_material_id: int
    consumed: Decimal = Field(ge=0)
    sampled: Decimal = Field(default=Decimal(0), ge=0)
    waste: Decimal = Field(default=Decimal(0), ge=0)


class ConsumptionIn(Reasoned):
    entries: list[ConsumptionEntry]


@router.put("/mfg/batches/{bid}/consumption", tags=["Manufacturing"])
def consumption(bid: int, body: ConsumptionIn, p: Principal = Depends(require("mfg.consumption.record")), s: Session = Depends(get_db)):
    use_reason(body.reason)
    b = _batch(s, bid)
    mfg.record_consumption(s, b, [e.model_dump() for e in body.entries])
    s.commit()
    return _batch_out(s, b, True)


@router.post("/mfg/batches/{bid}/reconcile", tags=["Manufacturing"])
def reconcile(bid: int, p: Principal = Depends(require("mfg.reconciliation.read")), s: Session = Depends(get_db)):
    b = _batch(s, bid)
    rec = mfg.reconcile(s, b)
    s.commit()
    return _recon_out(rec)


@router.post("/mfg/batches/{bid}/reconciliation/approve", tags=["Manufacturing"])
def approve_recon(bid: int, body: SignedAction, p: Principal = Depends(require("mfg.reconciliation.approve")), s: Session = Depends(get_db)):
    use_reason(body.reason)
    b = _batch(s, bid)
    rec = s.execute(select(BatchReconciliation).where(BatchReconciliation.batch_id == b.id)).scalar_one_or_none()
    if rec is None:
        raise NotFound("Reconcile the batch first")
    mfg.approve_reconciliation_production(s, p.user, b, rec, body.password, body.reason or "Reconciliation reviewed")
    s.commit()
    return _batch_out(s, b, True)


class QAReconIn(SignedAction):
    deviation_ref: str = Field(min_length=2)
    justification: str = Field(min_length=5)


@router.post("/mfg/batches/{bid}/reconciliation/qa-approve", tags=["Manufacturing"])
def qa_approve_recon(bid: int, body: QAReconIn, p: Principal = Depends(require("mfg.reconciliation.qa_approve")), s: Session = Depends(get_db)):
    use_reason(body.reason or body.justification)
    b = _batch(s, bid)
    rec = s.execute(select(BatchReconciliation).where(BatchReconciliation.batch_id == b.id)).scalar_one_or_none()
    if rec is None:
        raise NotFound("Reconcile the batch first")
    mfg.approve_reconciliation_qa(s, p.user, b, rec, body.password, body.deviation_ref, body.justification)
    s.commit()
    return _batch_out(s, b, True)


class OutputIn(Reasoned):
    quarantine_location_id: int


@router.post("/mfg/batches/{bid}/output", status_code=201, tags=["Manufacturing"])
def output(bid: int, body: OutputIn, p: Principal = Depends(require("mfg.output.create")), s: Session = Depends(get_db)):
    use_reason(body.reason)
    b = _batch(s, bid)
    loc = masters.get_or_404(s, Location, body.quarantine_location_id, "Location")
    lot = mfg.create_output(s, p.user, b, loc)
    s.commit()
    return {"lot_id": lot.id, "lot_no": lot.lot_no, "batch": _batch_out(s, b)}


# ============================================================ antisera (6b)
class AnimalIn(Reasoned):
    animal_tag: str = Field(min_length=2, max_length=30)
    species: str = "Equine"
    date_of_birth: date | None = None
    weight_kg: Decimal | None = None
    health_notes: str | None = None
    min_bleed_interval_days: int = Field(default=14, ge=1)


class AnimalUpdate(Reasoned):
    model_config = {"extra": "forbid"}
    weight_kg: Decimal | None = None
    status: str | None = None
    health_notes: str | None = None
    min_bleed_interval_days: int | None = Field(default=None, ge=1)


@router.get("/antisera/animals", tags=["Antisera"])
def list_animals(limit: int = Query(100), offset: int = Query(0), p: Principal = Depends(require("antisera.animal.read")), s: Session = Depends(get_db)):
    rows, total, limit, offset = _page(s, select(Animal), Animal, limit, offset)
    return {"items": [to_dict(r) for r in rows], "total": total, "limit": limit, "offset": offset}


@router.post("/antisera/animals", status_code=201, tags=["Antisera"])
def create_animal(body: AnimalIn, p: Principal = Depends(require("antisera.animal.create")), s: Session = Depends(get_db)):
    use_reason(body.reason or "Animal registered")
    masters.ensure_unique(s, Animal, "animal_tag", body.animal_tag)
    a = Animal(**body.model_dump(exclude={"reason"}))
    s.add(a)
    s.commit()
    return to_dict(a)


@router.patch("/antisera/animals/{aid}", tags=["Antisera"])
def update_animal(aid: int, body: AnimalUpdate, p: Principal = Depends(require("antisera.animal.update")), s: Session = Depends(get_db)):
    use_reason(body.reason)
    a = masters.get_or_404(s, Animal, aid, "Animal")
    data = body.model_dump(exclude={"reason"}, exclude_unset=True)
    if data.get("status") and data["status"] not in ("ACTIVE", "QUARANTINED", "RETIRED", "DECEASED"):
        raise ValidationFailed("Invalid status")
    for k, v in data.items():
        setattr(a, k, v)
    s.commit()
    return to_dict(a)


class ImmunisationIn(BaseModel):
    antigen: str = Field(min_length=2)
    dose: str | None = None
    administered_on: date
    remarks: str | None = None


@router.post("/antisera/animals/{aid}/immunisations", status_code=201, tags=["Antisera"])
def add_immunisation(aid: int, body: ImmunisationIn, p: Principal = Depends(require("antisera.bleed.create")), s: Session = Depends(get_db)):
    a = masters.get_or_404(s, Animal, aid, "Animal")
    r = antisera.immunise(s, p.user, a, body.antigen, body.dose, body.administered_on, body.remarks)
    s.commit()
    return to_dict(r)


@router.get("/antisera/animals/{aid}/immunisations", tags=["Antisera"])
def list_immunisations(aid: int, p: Principal = Depends(require("antisera.animal.read")), s: Session = Depends(get_db)):
    return [to_dict(r) for r in s.execute(select(ImmunisationRecord).where(ImmunisationRecord.animal_id == aid).order_by(ImmunisationRecord.id)).scalars()]


class BleedIn(BaseModel):
    animal_id: int
    bled_on: date
    volume_l: Decimal = Field(gt=0)
    remarks: str | None = None


@router.post("/antisera/bleeds", status_code=201, tags=["Antisera"])
def add_bleed(body: BleedIn, p: Principal = Depends(require("antisera.bleed.create")), s: Session = Depends(get_db)):
    a = masters.get_or_404(s, Animal, body.animal_id, "Animal")
    b = antisera.record_bleed(s, p.user, a, body.bled_on, body.volume_l, body.remarks)
    s.commit()
    return to_dict(b)


@router.get("/antisera/bleeds", tags=["Antisera"])
def list_bleeds(unpooled: bool = False, limit: int = Query(100), offset: int = Query(0), p: Principal = Depends(require("antisera.bleed.read")),
                s: Session = Depends(get_db)):
    stmt = select(BleedRecord)
    if unpooled:
        stmt = stmt.where(BleedRecord.pool_id.is_(None))
    rows, total, limit, offset = _page(s, stmt, BleedRecord, limit, offset)
    return {"items": [to_dict(r) for r in rows], "total": total, "limit": limit, "offset": offset}


class PoolIn(Reasoned):
    bleed_ids: list[int]
    material_id: int
    quarantine_location_id: int


@router.post("/antisera/pools", status_code=201, tags=["Antisera"])
def create_pool(body: PoolIn, p: Principal = Depends(require("antisera.pool.create")), s: Session = Depends(get_db)):
    use_reason(body.reason or "Plasma pool created")
    mat = masters.get_or_404(s, Material, body.material_id, "Material")
    loc = masters.get_or_404(s, Location, body.quarantine_location_id, "Location")
    pool = antisera.create_pool(s, p.user, body.bleed_ids, mat, loc)
    s.commit()
    return antisera.genealogy(s, pool)


@router.get("/antisera/pools", tags=["Antisera"])
def list_pools(limit: int = Query(100), offset: int = Query(0), p: Principal = Depends(require("antisera.pool.read")), s: Session = Depends(get_db)):
    rows, total, limit, offset = _page(s, select(PlasmaPool), PlasmaPool, limit, offset)
    return {"items": [to_dict(r) for r in rows], "total": total, "limit": limit, "offset": offset}


@router.get("/antisera/pools/{pid}", tags=["Antisera"])
def get_pool(pid: int, p: Principal = Depends(require("antisera.pool.read")), s: Session = Depends(get_db)):
    return antisera.genealogy(s, masters.get_or_404(s, PlasmaPool, pid, "Pool"))
