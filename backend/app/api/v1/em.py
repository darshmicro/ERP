"""Phase 11a endpoints: environmental monitoring."""
from decimal import Decimal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.crud import to_dict
from app.api.deps import Principal, get_db, require
from app.api.helpers import page_args, use_reason
from app.core.errors import BusinessRuleError
from app.models.em import EMIsolate, EMLimit, EMLimitSet, EMLocation, EMPlan, EMResultAmendment, EMSample
from app.schemas.common import Reasoned
from app.services import em, masters, versioning

router = APIRouter(prefix="/em", tags=["Environmental monitoring"])


class SignedAction(Reasoned):
    password: str


def _page(s, stmt, Model, limit, offset, conv=to_dict):
    limit, offset = page_args(limit, offset)
    total = s.execute(select(func.count()).select_from(stmt.subquery())).scalar()
    rows = s.execute(stmt.order_by(Model.id.desc()).limit(limit).offset(offset)).scalars().all()
    return {"items": [conv(r) for r in rows], "total": total, "limit": limit, "offset": offset}


# ------------------------------------------------------------ locations / plans
class LocationIn(Reasoned):
    code: str | None = None
    name: str = Field(min_length=2, max_length=150)
    grade: str = Field(pattern="^(A|B|C|D|NC)$")
    location_id: int | None = None
    description: str | None = None


class LocationUpdate(Reasoned):
    model_config = {"extra": "forbid"}
    name: str | None = None
    grade: str | None = Field(default=None, pattern="^(A|B|C|D|NC)$")
    description: str | None = None
    is_active: bool | None = None


@router.get("/locations")
def list_locations(request: Request, limit: int = Query(100), offset: int = Query(0), p: Principal = Depends(require("em.location.read")), s: Session = Depends(get_db)):
    stmt = select(EMLocation)
    if request.query_params.get("active") == "true":
        stmt = stmt.where(EMLocation.is_active == True)  # noqa: E712
    return _page(s, stmt, EMLocation, limit, offset)


@router.post("/locations", status_code=201)
def create_location(body: LocationIn, p: Principal = Depends(require("em.location.create")), s: Session = Depends(get_db)):
    use_reason(body.reason or "EM location created")
    loc = em.create_location(s, body.model_dump(exclude={"reason"}, exclude_none=True))
    s.commit()
    return to_dict(loc)


@router.patch("/locations/{lid}")
def update_location(lid: int, body: LocationUpdate, p: Principal = Depends(require("em.location.update")), s: Session = Depends(get_db)):
    use_reason(body.reason)
    loc = masters.get_or_404(s, EMLocation, lid, "EM location")
    for k, v in body.model_dump(exclude={"reason"}, exclude_unset=True).items():
        setattr(loc, k, v)
    s.commit()
    return to_dict(loc)


class PlanIn(Reasoned):
    em_location_id: int
    sample_type: str
    state: str = Field(default="OPERATIONAL", pattern="^(AT_REST|OPERATIONAL)$")
    frequency_days: int = Field(gt=0)
    start_date: str


class PlanUpdate(Reasoned):
    model_config = {"extra": "forbid"}
    frequency_days: int | None = Field(default=None, gt=0)
    is_active: bool | None = None


@router.get("/plans")
def list_plans(limit: int = Query(100), offset: int = Query(0), p: Principal = Depends(require("em.plan.read")), s: Session = Depends(get_db)):
    return _page(s, select(EMPlan), EMPlan, limit, offset)


@router.post("/plans", status_code=201)
def create_plan(body: PlanIn, p: Principal = Depends(require("em.plan.create")), s: Session = Depends(get_db)):
    from datetime import date
    use_reason(body.reason or "EM plan created")
    d = body.model_dump(exclude={"reason"})
    d["start_date"] = date.fromisoformat(d["start_date"])
    plan = em.create_plan(s, d)
    s.commit()
    return to_dict(plan)


@router.patch("/plans/{pid}")
def update_plan(pid: int, body: PlanUpdate, p: Principal = Depends(require("em.plan.update")), s: Session = Depends(get_db)):
    use_reason(body.reason)
    plan = masters.get_or_404(s, EMPlan, pid, "EM plan")
    for k, v in body.model_dump(exclude={"reason"}, exclude_unset=True).items():
        setattr(plan, k, v)
    s.commit()
    return to_dict(plan)


# ------------------------------------------------------------ limit sets
class LimitIn(BaseModel):
    grade: str
    sample_type: str
    state: str = "OPERATIONAL"
    alert_high: Decimal | None = None
    action_high: Decimal | None = None
    alert_low: Decimal | None = None
    action_low: Decimal | None = None
    unit: str | None = None


class LimitSetIn(Reasoned):
    title: str = Field(min_length=3, max_length=200)
    basis: str | None = None
    limitset_no: str | None = None
    limits: list[LimitIn] = []


def _ls_out(s: Session, ls: EMLimitSet, detail: bool = False) -> dict:
    out = to_dict(ls)
    if detail:
        out["limits"] = [to_dict(x) for x in s.execute(select(EMLimit).where(EMLimit.limit_set_id == ls.id).order_by(EMLimit.seq)).scalars()]
        out["versions"] = [{"id": v.id, "version_no": v.version_no, "status": v.status, "change_reason": v.change_reason} for v in versioning.history(s, ls)]
    return out


def _ls(s, lid):
    return masters.get_or_404(s, EMLimitSet, lid, "EM limit set")


@router.get("/limit-sets")
def list_limit_sets(limit: int = Query(50), offset: int = Query(0), p: Principal = Depends(require("em.limit.read")), s: Session = Depends(get_db)):
    return _page(s, select(EMLimitSet), EMLimitSet, limit, offset, lambda r: _ls_out(s, r))


@router.post("/limit-sets", status_code=201)
def create_limit_set(body: LimitSetIn, p: Principal = Depends(require("em.limit.create")), s: Session = Depends(get_db)):
    use_reason(body.reason or "EM limit set created")
    ls = em.create_limit_set(s, {"title": body.title, "basis": body.basis}, [x.model_dump() for x in body.limits], body.limitset_no)
    s.commit()
    return _ls_out(s, ls, True)


@router.post("/limit-sets/load-reference", status_code=201)
def load_reference(body: Reasoned, p: Principal = Depends(require("em.limit.create")), s: Session = Depends(get_db)):
    """Creates a DRAFT limit set from Annex 1 style reference values; the site must verify and approve it."""
    use_reason(body.reason or "Reference limits loaded")
    ls = em.load_reference_limits(s)
    s.commit()
    return _ls_out(s, ls, True)


@router.get("/limit-sets/{lid}")
def get_limit_set(lid: int, p: Principal = Depends(require("em.limit.read")), s: Session = Depends(get_db)):
    return _ls_out(s, _ls(s, lid), True)


@router.post("/limit-sets/{lid}/limits", status_code=201)
def add_limit(lid: int, body: LimitIn, p: Principal = Depends(require("em.limit.update")), s: Session = Depends(get_db)):
    use_reason("EM limit added")
    row = em.add_limit(s, _ls(s, lid), body.model_dump())
    s.commit()
    return to_dict(row)


@router.delete("/limit-sets/{lid}/limits/{xid}", status_code=204)
def delete_limit(lid: int, xid: int, p: Principal = Depends(require("em.limit.update")), s: Session = Depends(get_db)):
    use_reason("EM limit removed")
    ls = _ls(s, lid)
    row = masters.get_or_404(s, EMLimit, xid, "EM limit")
    if row.limit_set_id != ls.id or ls.status != "DRAFT":
        raise BusinessRuleError("Limits can only be removed from a DRAFT limit set", rule_id="BR-HIS-001")
    s.delete(row)
    s.commit()


@router.post("/limit-sets/{lid}/submit")
def submit_limit_set(lid: int, p: Principal = Depends(require("em.limit.update")), s: Session = Depends(get_db)):
    ls = _ls(s, lid)
    versioning.submit(s, ls)
    s.commit()
    return _ls_out(s, ls, True)


@router.post("/limit-sets/{lid}/approve")
def approve_limit_set(lid: int, body: SignedAction, p: Principal = Depends(require("em.limit.approve")), s: Session = Depends(get_db)):
    use_reason(body.reason)
    ls = _ls(s, lid)
    versioning.approve(s, ls, p.user, body.password, body.reason or "")
    s.commit()
    return _ls_out(s, ls, True)


@router.post("/limit-sets/{lid}/new-version", status_code=201)
def new_limit_set_version(lid: int, body: Reasoned, p: Principal = Depends(require("em.limit.create")), s: Session = Depends(get_db)):
    use_reason(body.reason)
    new = versioning.new_version(s, _ls(s, lid), body.reason or "")
    s.commit()
    return _ls_out(s, new, True)


# ------------------------------------------------------------ samples
class SampleIn(Reasoned):
    em_location_id: int
    sample_type: str
    state: str = Field(default="OPERATIONAL", pattern="^(AT_REST|OPERATIONAL)$")
    plan_id: int | None = None
    sample_point: str | None = Field(default=None, max_length=100)
    manufacturing_batch_id: int | None = None
    equipment_id: int | None = None
    remarks: str | None = None


class IsolateIn(BaseModel):
    organism: str = Field(min_length=2, max_length=150)
    gram_stain: str | None = None
    cfu_count: int = Field(default=1, ge=0)
    identification_method: str | None = None


class ResultIn(Reasoned):
    value: Decimal = Field(ge=0)
    unit: str | None = None
    isolates: list[IsolateIn] = []


class AmendIn(Reasoned):
    value: Decimal = Field(ge=0)


class ReviewIn(SignedAction):
    comment: str | None = None


def _out(s: Session, x: EMSample, detail: bool = False) -> dict:
    out = to_dict(x)
    loc = s.get(EMLocation, x.em_location_id)
    out["location_code"], out["location_name"] = (loc.code, loc.name) if loc else (None, None)
    if detail:
        out["isolates"] = [to_dict(i) for i in s.execute(select(EMIsolate).where(EMIsolate.sample_id == x.id)).scalars()]
        out["amendments"] = [to_dict(a) for a in s.execute(select(EMResultAmendment).where(EMResultAmendment.sample_id == x.id).order_by(EMResultAmendment.id)).scalars()]
    return out


def _sample(s, sid):
    return masters.get_or_404(s, EMSample, sid, "EM sample")


@router.get("/samples")
def list_samples(request: Request, limit: int = Query(50), offset: int = Query(0), p: Principal = Depends(require("em.sample.read")), s: Session = Depends(get_db)):
    stmt = select(EMSample)
    for f in ("status", "outcome", "sample_type", "em_location_id", "grade"):
        if request.query_params.get(f):
            stmt = stmt.where(getattr(EMSample, f) == request.query_params[f])
    return _page(s, stmt, EMSample, limit, offset, lambda r: _out(s, r))


@router.post("/samples", status_code=201)
def create_sample(body: SampleIn, p: Principal = Depends(require("em.sample.create")), s: Session = Depends(get_db)):
    use_reason(body.reason or "EM sample taken")
    x = em.create_sample(s, p.user, body.model_dump(exclude={"reason"}, exclude_none=True))
    s.commit()
    return _out(s, x, True)


@router.get("/samples/{sid}")
def get_sample(sid: int, p: Principal = Depends(require("em.sample.read")), s: Session = Depends(get_db)):
    return _out(s, _sample(s, sid), True)


@router.post("/samples/{sid}/result")
def enter_result(sid: int, body: ResultIn, p: Principal = Depends(require("em.sample.enter")), s: Session = Depends(get_db)):
    use_reason(body.reason or "EM result entered")
    x = em.enter_result(s, _sample(s, sid), p.user, body.value, body.unit, [i.model_dump() for i in body.isolates])
    s.commit()
    return _out(s, x, True)


@router.post("/samples/{sid}/amend")
def amend_result(sid: int, body: AmendIn, p: Principal = Depends(require("em.sample.enter")), s: Session = Depends(get_db)):
    use_reason(body.reason)
    x = em.amend_result(s, _sample(s, sid), p.user, body.value, body.reason or "")
    s.commit()
    return _out(s, x, True)


@router.post("/samples/{sid}/isolates", status_code=201)
def add_isolate(sid: int, body: IsolateIn, p: Principal = Depends(require("em.sample.enter")), s: Session = Depends(get_db)):
    use_reason("Organism recorded")
    iso = em.add_isolate(s, _sample(s, sid), p.user, body.model_dump())
    s.commit()
    return to_dict(iso)


@router.post("/samples/{sid}/review")
def review_sample(sid: int, body: ReviewIn, p: Principal = Depends(require("em.sample.review")), s: Session = Depends(get_db)):
    use_reason(body.reason)
    x = _sample(s, sid)
    em.review(s, x, p.user, body.password, body.reason or "", body.comment)
    s.commit()
    return _out(s, x, True)


@router.post("/samples/{sid}/cancel")
def cancel_sample(sid: int, body: Reasoned, p: Principal = Depends(require("em.sample.enter")), s: Session = Depends(get_db)):
    use_reason(body.reason)
    x = _sample(s, sid)
    em.cancel(s, x, body.reason or "")
    s.commit()
    return _out(s, x)


# ------------------------------------------------------------ schedule / trend / excursions
@router.get("/schedule")
def schedule(horizon_days: int = 7, p: Principal = Depends(require("em.plan.read")), s: Session = Depends(get_db)):
    return em.schedule(s, horizon_days)


@router.get("/trend")
def trend(em_location_id: int, sample_type: str, state: str = "OPERATIONAL", days: int = 365, p: Principal = Depends(require("em.sample.read")), s: Session = Depends(get_db)):
    return em.trend(s, em_location_id, sample_type, state, days)


@router.get("/excursions")
def excursions(days: int = 30, p: Principal = Depends(require("em.sample.read")), s: Session = Depends(get_db)):
    return [_out(s, x) for x in em.excursions(s, days)]
