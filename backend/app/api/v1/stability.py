"""Phase 11b endpoints: stability protocols, studies, pulls, results, evaluation."""
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.crud import to_dict
from app.api.deps import Principal, get_db, require
from app.api.helpers import page_args, use_reason
from app.core.errors import BusinessRuleError
from app.models.master import Material
from app.models.stability import StabilityCondition, StabilityProtocol, StabilityPull, StabilityStudy, StabilityTimepoint
from app.models.warehouse import MaterialBatch
from app.schemas.common import Reasoned
from app.services import masters, stability as svc, versioning

router = APIRouter(prefix="/stability", tags=["Stability"])


class SignedAction(Reasoned):
    password: str


def _page(s, stmt, Model, limit, offset, conv=to_dict):
    limit, offset = page_args(limit, offset)
    total = s.execute(select(func.count()).select_from(stmt.subquery())).scalar()
    rows = s.execute(stmt.order_by(Model.id.desc()).limit(limit).offset(offset)).scalars().all()
    return {"items": [conv(r) for r in rows], "total": total, "limit": limit, "offset": offset}


# ------------------------------------------------------------ protocols
class ProtocolIn(Reasoned):
    title: str = Field(min_length=3, max_length=200)
    material_id: int
    specification_id: int
    container_closure: str | None = None
    proposed_shelf_life_months: int | None = Field(default=None, gt=0)
    pull_window_days: int = Field(default=14, ge=0, le=90)
    objective: str | None = None
    protocol_no: str | None = None


class ConditionIn(BaseModel):
    label: str = Field(min_length=2, max_length=80)
    condition_type: str = Field(pattern="^(LONG_TERM|INTERMEDIATE|ACCELERATED|STRESS|REFRIGERATED|FROZEN)$")
    temperature_c: Decimal
    temperature_tol_c: Decimal | None = None
    rh_pct: Decimal | None = Field(default=None, ge=0, le=100)
    rh_tol_pct: Decimal | None = None
    chamber_location_id: int | None = None


class TimepointIn(BaseModel):
    month: int = Field(ge=0, le=240)
    label: str | None = None


def _proto_out(s: Session, x: StabilityProtocol, detail: bool = False) -> dict:
    out = to_dict(x)
    m = s.get(Material, x.material_id)
    out["material_name"] = m.name if m else None
    if detail:
        out["conditions"] = [to_dict(c) for c in svc.conditions(s, x.id)]
        out["timepoints"] = [to_dict(t) for t in svc.timepoints(s, x.id)]
        out["versions"] = [{"id": v.id, "version_no": v.version_no, "status": v.status, "change_reason": v.change_reason} for v in versioning.history(s, x)]
    return out


def _proto(s, pid):
    return masters.get_or_404(s, StabilityProtocol, pid, "Stability protocol")


@router.get("/protocols")
def list_protocols(request: Request, limit: int = Query(50), offset: int = Query(0), p: Principal = Depends(require("stability.protocol.read")), s: Session = Depends(get_db)):
    stmt = select(StabilityProtocol)
    if request.query_params.get("status"):
        stmt = stmt.where(StabilityProtocol.status == request.query_params["status"])
    return _page(s, stmt, StabilityProtocol, limit, offset, lambda r: _proto_out(s, r))


@router.post("/protocols", status_code=201)
def create_protocol(body: ProtocolIn, p: Principal = Depends(require("stability.protocol.create")), s: Session = Depends(get_db)):
    use_reason(body.reason or "Stability protocol created")
    x = versioning.create_draft(s, StabilityProtocol, body.model_dump(exclude={"reason", "protocol_no"}, exclude_none=True), body.protocol_no)
    s.commit()
    return _proto_out(s, x, True)


@router.get("/protocols/{pid}")
def get_protocol(pid: int, p: Principal = Depends(require("stability.protocol.read")), s: Session = Depends(get_db)):
    return _proto_out(s, _proto(s, pid), True)


@router.post("/protocols/{pid}/conditions", status_code=201)
def add_condition(pid: int, body: ConditionIn, p: Principal = Depends(require("stability.protocol.update")), s: Session = Depends(get_db)):
    use_reason("Stability condition added")
    c = svc.add_condition(s, _proto(s, pid), body.model_dump())
    s.commit()
    return to_dict(c)


@router.delete("/protocols/{pid}/conditions/{cid}", status_code=204)
def delete_condition(pid: int, cid: int, p: Principal = Depends(require("stability.protocol.update")), s: Session = Depends(get_db)):
    use_reason("Stability condition removed")
    x = _proto(s, pid)
    c = masters.get_or_404(s, StabilityCondition, cid, "Condition")
    if c.protocol_id != x.id or x.status != "DRAFT":
        raise BusinessRuleError("Conditions can only be removed from a DRAFT protocol", rule_id="BR-HIS-001")
    s.delete(c)
    s.commit()


@router.post("/protocols/{pid}/timepoints", status_code=201)
def add_timepoint(pid: int, body: TimepointIn, p: Principal = Depends(require("stability.protocol.update")), s: Session = Depends(get_db)):
    use_reason("Stability time point added")
    t = svc.add_timepoint(s, _proto(s, pid), body.model_dump())
    s.commit()
    return to_dict(t)


@router.delete("/protocols/{pid}/timepoints/{tid}", status_code=204)
def delete_timepoint(pid: int, tid: int, p: Principal = Depends(require("stability.protocol.update")), s: Session = Depends(get_db)):
    use_reason("Stability time point removed")
    x = _proto(s, pid)
    t = masters.get_or_404(s, StabilityTimepoint, tid, "Time point")
    if t.protocol_id != x.id or x.status != "DRAFT":
        raise BusinessRuleError("Time points can only be removed from a DRAFT protocol", rule_id="BR-HIS-001")
    s.delete(t)
    s.commit()


@router.post("/protocols/{pid}/submit")
def submit_protocol(pid: int, p: Principal = Depends(require("stability.protocol.update")), s: Session = Depends(get_db)):
    x = _proto(s, pid)
    versioning.submit(s, x)
    s.commit()
    return _proto_out(s, x, True)


@router.post("/protocols/{pid}/approve")
def approve_protocol(pid: int, body: SignedAction, p: Principal = Depends(require("stability.protocol.approve")), s: Session = Depends(get_db)):
    use_reason(body.reason)
    x = _proto(s, pid)
    versioning.approve(s, x, p.user, body.password, body.reason or "")
    s.commit()
    return _proto_out(s, x, True)


@router.post("/protocols/{pid}/new-version", status_code=201)
def new_protocol_version(pid: int, body: Reasoned, p: Principal = Depends(require("stability.protocol.create")), s: Session = Depends(get_db)):
    use_reason(body.reason)
    new = versioning.new_version(s, _proto(s, pid), body.reason or "")
    s.commit()
    return _proto_out(s, new, True)


# ------------------------------------------------------------ studies
class StudyIn(Reasoned):
    protocol_id: int
    material_batch_id: int
    start_date: date
    units_per_pull: Decimal = Field(gt=0)
    source_location_id: int


def _study_out(s: Session, x: StabilityStudy, detail: bool = False) -> dict:
    out = to_dict(x)
    lot = s.get(MaterialBatch, x.material_batch_id)
    out["lot_no"] = lot.lot_no if lot else None
    proto = s.get(StabilityProtocol, x.protocol_id)
    out["protocol_no"], out["protocol_version"] = (proto.protocol_no, proto.version_no) if proto else (None, None)
    if detail:
        conds = {c.id: c for c in svc.conditions(s, x.protocol_id)}
        out["pulls"] = [{**to_dict(pl), "condition": conds[pl.condition_id].label if pl.condition_id in conds else None,
                         "results": [to_dict(r) for r in svc.current_results(s, pl.id)]} for pl in svc.pulls(s, x.id)]
    return out


def _study(s, sid):
    return masters.get_or_404(s, StabilityStudy, sid, "Stability study")


@router.get("/studies")
def list_studies(request: Request, limit: int = Query(50), offset: int = Query(0), p: Principal = Depends(require("stability.study.read")), s: Session = Depends(get_db)):
    stmt = select(StabilityStudy)
    if request.query_params.get("status"):
        stmt = stmt.where(StabilityStudy.status == request.query_params["status"])
    return _page(s, stmt, StabilityStudy, limit, offset, lambda r: _study_out(s, r))


@router.post("/studies", status_code=201)
def create_study(body: StudyIn, p: Principal = Depends(require("stability.study.create")), s: Session = Depends(get_db)):
    use_reason(body.reason or "Stability study created")
    x = svc.create_study(s, p.user, body.model_dump(exclude={"reason"}))
    s.commit()
    return _study_out(s, x, True)


@router.get("/studies/{sid}")
def get_study(sid: int, p: Principal = Depends(require("stability.study.read")), s: Session = Depends(get_db)):
    return _study_out(s, _study(s, sid), True)


@router.post("/studies/{sid}/start")
def start_study(sid: int, body: Reasoned, p: Principal = Depends(require("stability.study.start")), s: Session = Depends(get_db)):
    use_reason(body.reason or "Stability study started")
    x = svc.start_study(s, _study(s, sid), p.user)
    s.commit()
    return _study_out(s, x, True)


@router.post("/studies/{sid}/complete")
def complete_study(sid: int, body: Reasoned, p: Principal = Depends(require("stability.study.update")), s: Session = Depends(get_db)):
    use_reason(body.reason or "Stability study completed")
    x = svc.complete_study(s, _study(s, sid))
    s.commit()
    return _study_out(s, x, True)


@router.post("/studies/{sid}/terminate")
def terminate_study(sid: int, body: Reasoned, p: Principal = Depends(require("stability.study.terminate")), s: Session = Depends(get_db)):
    use_reason(body.reason)
    x = svc.terminate_study(s, _study(s, sid), body.reason or "")
    s.commit()
    return _study_out(s, x, True)


class ConcludeIn(SignedAction):
    shelf_life_months: int = Field(ge=0, le=240)
    conclusion: str = Field(min_length=3)


@router.post("/studies/{sid}/conclude")
def conclude_study(sid: int, body: ConcludeIn, p: Principal = Depends(require("stability.study.conclude")), s: Session = Depends(get_db)):
    use_reason(body.reason)
    x = _study(s, sid)
    svc.conclude(s, x, p.user, body.password, body.reason or "", body.shelf_life_months, body.conclusion)
    s.commit()
    return _study_out(s, x, True)


@router.get("/studies/{sid}/evaluation")
def evaluation(sid: int, p: Principal = Depends(require("stability.result.read")), s: Session = Depends(get_db)):
    return svc.evaluation(s, _study(s, sid))


# ------------------------------------------------------------ pulls / results
class PullIn(Reasoned):
    actual_qty: Decimal | None = Field(default=None, gt=0)
    remarks: str | None = None


class ResultIn(BaseModel):
    parameter_id: int
    value: Decimal | None = None
    text: str | None = None
    conforms: bool | None = None
    equipment_id: int | None = None


class ResultsIn(Reasoned):
    results: list[ResultIn] = Field(min_length=1)


class CorrectionIn(Reasoned):
    correction_of: int
    result: ResultIn


def _pull(s, pid):
    return masters.get_or_404(s, StabilityPull, pid, "Stability pull")


def _pull_out(s, x):
    return {**to_dict(x), "results": [to_dict(r) for r in svc.current_results(s, x.id)]}


@router.get("/pulls/due")
def due_pulls(horizon_days: int = 14, p: Principal = Depends(require("stability.pull.read")), s: Session = Depends(get_db)):
    return svc.due(s, horizon_days)


@router.post("/pulls/check-missed")
def check_missed(p: Principal = Depends(require("stability.pull.skip")), s: Session = Depends(get_db)):
    use_reason("Missed stability pulls identified")
    rows = svc.mark_missed(s)
    s.commit()
    return {"marked_missed": [r.id for r in rows]}


@router.get("/pulls/{pid}")
def get_pull(pid: int, p: Principal = Depends(require("stability.pull.read")), s: Session = Depends(get_db)):
    return _pull_out(s, _pull(s, pid))


@router.post("/pulls/{pid}/pull")
def record_pull(pid: int, body: PullIn, p: Principal = Depends(require("stability.pull.record")), s: Session = Depends(get_db)):
    use_reason(body.reason or "Stability sample pulled")
    x = svc.record_pull(s, _pull(s, pid), p.user, body.actual_qty, body.remarks)
    s.commit()
    return _pull_out(s, x)


@router.post("/pulls/{pid}/results", status_code=201)
def enter_results(pid: int, body: ResultsIn, p: Principal = Depends(require("stability.result.enter")), s: Session = Depends(get_db)):
    use_reason(body.reason or "Stability results entered")
    x = _pull(s, pid)
    for it in body.results:
        svc.enter_result(s, x, p.user, it.model_dump())
    s.commit()
    return _pull_out(s, x)


@router.post("/pulls/{pid}/correct")
def correct_result(pid: int, body: CorrectionIn, p: Principal = Depends(require("stability.result.enter")), s: Session = Depends(get_db)):
    use_reason(body.reason)
    x = _pull(s, pid)
    svc.enter_result(s, x, p.user, body.result.model_dump(), correction_of=body.correction_of, reason=body.reason)
    s.commit()
    return _pull_out(s, x)


@router.post("/pulls/{pid}/complete-testing")
def complete_testing(pid: int, p: Principal = Depends(require("stability.result.enter")), s: Session = Depends(get_db)):
    use_reason("Stability testing complete")
    x = svc.complete_testing(s, _pull(s, pid))
    s.commit()
    return _pull_out(s, x)


@router.post("/pulls/{pid}/review")
def review_pull(pid: int, body: SignedAction, p: Principal = Depends(require("stability.pull.review")), s: Session = Depends(get_db)):
    use_reason(body.reason)
    x = _pull(s, pid)
    svc.review_pull(s, x, p.user, body.password, body.reason or "")
    s.commit()
    return _pull_out(s, x)


@router.post("/pulls/{pid}/skip")
def skip_pull(pid: int, body: Reasoned, p: Principal = Depends(require("stability.pull.skip")), s: Session = Depends(get_db)):
    use_reason(body.reason)
    x = _pull(s, pid)
    svc.skip_pull(s, x, body.reason or "")
    s.commit()
    return _pull_out(s, x)
