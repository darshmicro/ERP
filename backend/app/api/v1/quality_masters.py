"""Versioned quality masters: STP, specification (+parameters), sampling plan (spec 13/14/59/60)."""
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.crud import to_dict, xlsx_response
from app.api.deps import Principal, get_db, require
from app.api.helpers import page_args, use_reason
from app.core.errors import NotFound, ValidationFailed
from app.models.spec import STP, SamplingPlan, Specification, SpecificationParameter
from app.schemas.common import Reasoned
from app.services import masters, versioning

router = APIRouter()


class SignedAction(Reasoned):
    password: str


def _list(request: Request, Model, key: str, q: str | None, p_limit: int, offset: int, s: Session, extra_filters=()):
    limit, offset = page_args(p_limit, offset)
    stmt = select(Model)
    if q:
        stmt = stmt.where(func.lower(getattr(Model, key)).like(f"%{q.lower()}%") | func.lower(Model.title).like(f"%{q.lower()}%")
                          if hasattr(Model, "title") else func.lower(getattr(Model, key)).like(f"%{q.lower()}%"))
    if request.query_params.get("status"):
        stmt = stmt.where(Model.status == request.query_params["status"])
    elif request.query_params.get("current") in ("1", "true"):
        stmt = stmt.where(Model.status == "APPROVED")
    for f in extra_filters:
        if request.query_params.get(f):
            stmt = stmt.where(getattr(Model, f) == request.query_params[f])
    total = s.execute(select(func.count()).select_from(stmt.subquery())).scalar()
    rows = s.execute(stmt.order_by(getattr(Model, key), Model.version_no.desc()).limit(limit).offset(offset)).scalars().all()
    return {"items": [to_dict(r) for r in rows], "total": total, "limit": limit, "offset": offset}


def _generic(prefix: str, tag: str, Model, perm: str, key: str, CreateIn, UpdateIn, extra_filters=()):
    @router.get(f"/{prefix}", tags=[tag])
    def list_(request: Request, q: str | None = None, limit: int = Query(50), offset: int = Query(0),
              p: Principal = Depends(require(f"{perm}.read")), s: Session = Depends(get_db)):
        return _list(request, Model, key, q, limit, offset, s, extra_filters)

    @router.post(f"/{prefix}", status_code=201, tags=[tag])
    def create(body: CreateIn, p: Principal = Depends(require(f"{perm}.create")), s: Session = Depends(get_db)):  # type: ignore[valid-type]
        use_reason(body.reason)
        data = body.model_dump(exclude={"reason", key}, exclude_none=True)
        obj = versioning.create_draft(s, Model, data, getattr(body, key, None))
        s.commit()
        return to_dict(obj)

    @router.get(f"/{prefix}/{{record_id}}", tags=[tag])
    def get(record_id: int, p: Principal = Depends(require(f"{perm}.read")), s: Session = Depends(get_db)):
        obj = masters.get_or_404(s, Model, record_id, tag)
        out = to_dict(obj)
        out["versions"] = [{"id": v.id, "version_no": v.version_no, "status": v.status,
                            "effective_from": v.effective_from.isoformat() if v.effective_from else None,
                            "effective_to": v.effective_to.isoformat() if v.effective_to else None,
                            "change_reason": v.change_reason} for v in versioning.history(s, obj)]
        if Model is Specification:
            out["parameters"] = [to_dict(x) for x in versioning.parameters(s, obj)]
        return out

    @router.patch(f"/{prefix}/{{record_id}}", tags=[tag])
    def update(record_id: int, body: UpdateIn, p: Principal = Depends(require(f"{perm}.update")), s: Session = Depends(get_db)):  # type: ignore[valid-type]
        use_reason(body.reason)
        obj = masters.get_or_404(s, Model, record_id, tag)
        data = body.model_dump(exclude={"reason"}, exclude_unset=True)
        masters.check_foreign_keys(s, Model, data)
        for k, v in data.items():
            setattr(obj, k, v)  # immutability of non-DRAFT versions is enforced by the ORM hook (BR-HIS-001)
        s.commit()
        return to_dict(obj)

    @router.post(f"/{prefix}/{{record_id}}/submit", tags=[tag])
    def submit(record_id: int, p: Principal = Depends(require(f"{perm}.update")), s: Session = Depends(get_db)):
        obj = masters.get_or_404(s, Model, record_id, tag)
        versioning.submit(s, obj)
        s.commit()
        return to_dict(obj)

    @router.post(f"/{prefix}/{{record_id}}/return", tags=[tag])
    def return_(record_id: int, body: Reasoned, p: Principal = Depends(require(f"{perm}.update")), s: Session = Depends(get_db)):
        use_reason(body.reason)
        obj = masters.get_or_404(s, Model, record_id, tag)
        versioning.return_to_draft(s, obj, body.reason or "")
        s.commit()
        return to_dict(obj)

    @router.post(f"/{prefix}/{{record_id}}/approve", tags=[tag])
    def approve(record_id: int, body: SignedAction, p: Principal = Depends(require(f"{perm}.approve")), s: Session = Depends(get_db)):
        use_reason(body.reason)
        obj = masters.get_or_404(s, Model, record_id, tag)
        versioning.approve(s, obj, p.user, body.password, body.reason or "")
        s.commit()
        return to_dict(obj)

    @router.post(f"/{prefix}/{{record_id}}/new-version", status_code=201, tags=[tag])
    def new_version(record_id: int, body: Reasoned, p: Principal = Depends(require(f"{perm}.create")), s: Session = Depends(get_db)):
        use_reason(body.reason)
        obj = masters.get_or_404(s, Model, record_id, tag)
        new = versioning.new_version(s, obj, body.reason or "")
        s.commit()
        return to_dict(new)


# ---- STP
class StpIn(Reasoned):
    stp_no: str | None = None
    title: str = Field(min_length=3, max_length=200)
    test_method: str | None = None
    equipment_required: str | None = None
    reagents_required: str | None = None
    reference_standards: str | None = None
    procedure: str | None = None
    calculation: str | None = None
    acceptance_criteria: str | None = None
    safety_precautions: str | None = None


class StpUpdate(Reasoned):
    model_config = {"extra": "forbid"}
    title: str | None = None
    test_method: str | None = None
    equipment_required: str | None = None
    reagents_required: str | None = None
    reference_standards: str | None = None
    procedure: str | None = None
    calculation: str | None = None
    acceptance_criteria: str | None = None
    safety_precautions: str | None = None


_generic("stps", "STP", STP, "md.stp", "stp_no", StpIn, StpUpdate)


# ---- Specification
class SpecIn(Reasoned):
    spec_no: str | None = None
    material_id: int
    title: str | None = None
    pharmacopoeial_reference: str | None = None


class SpecUpdate(Reasoned):
    model_config = {"extra": "forbid"}
    title: str | None = None
    pharmacopoeial_reference: str | None = None


_generic("specifications", "Specifications", Specification, "md.spec", "spec_no", SpecIn, SpecUpdate, ("material_id",))


class ParamIn(Reasoned):
    seq: int | None = Field(default=None, ge=1)
    test_name: str = Field(min_length=1, max_length=150)
    test_method: str | None = None
    stp_id: int | None = None
    spec_type: str = Field(default="NUMERIC", pattern="^(NUMERIC|RANGE|TEXT|PASS_FAIL)$")
    lsl: Decimal | None = None
    usl: Decimal | None = None
    target: Decimal | None = None
    unit: str | None = None
    decimal_places: int | None = Field(default=None, ge=0, le=10)
    acceptance_criteria: str | None = None
    pharmacopoeial_reference: str | None = None
    frequency: str | None = None
    criticality: str = Field(default="MAJOR", pattern="^(CRITICAL|MAJOR|MINOR)$")
    alert_low: Decimal | None = None
    alert_high: Decimal | None = None
    action_low: Decimal | None = None
    action_high: Decimal | None = None


class ParamUpdate(Reasoned):
    model_config = {"extra": "forbid"}
    seq: int | None = Field(default=None, ge=1)
    test_name: str | None = Field(default=None, min_length=1, max_length=150)
    test_method: str | None = None
    stp_id: int | None = None
    spec_type: str | None = Field(default=None, pattern="^(NUMERIC|RANGE|TEXT|PASS_FAIL)$")
    lsl: Decimal | None = None
    usl: Decimal | None = None
    target: Decimal | None = None
    unit: str | None = None
    decimal_places: int | None = Field(default=None, ge=0, le=10)
    acceptance_criteria: str | None = None
    pharmacopoeial_reference: str | None = None
    frequency: str | None = None
    criticality: str | None = Field(default=None, pattern="^(CRITICAL|MAJOR|MINOR)$")
    alert_low: Decimal | None = None
    alert_high: Decimal | None = None
    action_low: Decimal | None = None
    action_high: Decimal | None = None


def _check_param(d: dict) -> None:
    lsl, usl = d.get("lsl"), d.get("usl")
    if lsl is not None and usl is not None and usl < lsl:
        raise ValidationFailed("USL is below LSL")
    t = d.get("target")
    if t is not None and ((lsl is not None and t < lsl) or (usl is not None and t > usl)):
        raise ValidationFailed("Target lies outside the specification limits")


@router.post("/specifications/{spec_id}/parameters", status_code=201, tags=["Specifications"])
def add_param(spec_id: int, body: ParamIn, p: Principal = Depends(require("md.spec.update")), s: Session = Depends(get_db)):
    use_reason(body.reason or "Specification parameter added")
    spec = masters.get_or_404(s, Specification, spec_id, "Specification")
    data = body.model_dump(exclude={"reason", "seq"}, exclude_none=True)
    _check_param(data)
    masters.check_foreign_keys(s, SpecificationParameter, data)
    seq = body.seq or ((s.execute(select(func.max(SpecificationParameter.seq)).where(
        SpecificationParameter.specification_id == spec.id)).scalar() or 0) + 1)
    par = SpecificationParameter(specification_id=spec.id, seq=seq, **data)  # ORM hook rejects if spec not DRAFT
    s.add(par)
    s.commit()
    return to_dict(par)


@router.patch("/specifications/{spec_id}/parameters/{param_id}", tags=["Specifications"])
def update_param(spec_id: int, param_id: int, body: ParamUpdate, p: Principal = Depends(require("md.spec.update")),
                 s: Session = Depends(get_db)):
    use_reason(body.reason or "Specification parameter changed")
    par = masters.get_or_404(s, SpecificationParameter, param_id, "Parameter")
    if par.specification_id != spec_id:
        raise NotFound("Parameter not found")
    data = body.model_dump(exclude={"reason"}, exclude_unset=True)
    _check_param({**to_dict(par), **data})
    masters.check_foreign_keys(s, SpecificationParameter, data)
    for k, v in data.items():
        setattr(par, k, v)
    s.commit()
    return to_dict(par)


@router.delete("/specifications/{spec_id}/parameters/{param_id}", tags=["Specifications"])
def delete_param(spec_id: int, param_id: int, body: Reasoned, p: Principal = Depends(require("md.spec.update")),
                 s: Session = Depends(get_db)):
    use_reason(body.reason)
    par = masters.get_or_404(s, SpecificationParameter, param_id, "Parameter")
    if par.specification_id != spec_id:
        raise NotFound("Parameter not found")
    s.delete(par)  # allowed only while the parent version is DRAFT; logged as DELETE in the audit trail
    s.commit()
    return {"ok": True}


@router.get("/materials/{material_id}/specification-in-force", tags=["Specifications"])
def spec_in_force(material_id: int, on: datetime | None = None, p: Principal = Depends(require("md.spec.read")),
                  s: Session = Depends(get_db)):
    """The specification version valid at `on` (default now): historical records stay linked to their version."""
    from datetime import timezone
    if on is not None and on.tzinfo is None:
        on = on.replace(tzinfo=timezone.utc)
    spec = versioning.current_spec_for_material(s, material_id, on)
    if spec is None:
        raise NotFound("No approved specification was in force for this material at that time")
    return {**to_dict(spec), "parameters": [to_dict(x) for x in versioning.parameters(s, spec)]}


# ---- Sampling plan
class PlanIn(Reasoned):
    plan_no: str | None = None
    material_id: int
    sampling_rule: str = Field(default="SQRT_N_PLUS_1", pattern="^(FIXED|SQRT_N_PLUS_1|PERCENT|ALL)$")
    fixed_qty: Decimal | None = Field(default=None, gt=0)
    percent: Decimal | None = Field(default=None, gt=0, le=100)
    unit_id: int | None = None
    container_rule: str | None = None
    remarks: str | None = None


class PlanUpdate(Reasoned):
    model_config = {"extra": "forbid"}
    sampling_rule: str | None = Field(default=None, pattern="^(FIXED|SQRT_N_PLUS_1|PERCENT|ALL)$")
    fixed_qty: Decimal | None = None
    percent: Decimal | None = None
    unit_id: int | None = None
    container_rule: str | None = None
    remarks: str | None = None


_generic("sampling-plans", "Sampling plans", SamplingPlan, "md.sampling_plan", "plan_no", PlanIn, PlanUpdate, ("material_id",))


@router.get("/specifications-export", tags=["Specifications"])
def export_specs(p: Principal = Depends(require("md.spec.read", "md.master.export")), s: Session = Depends(get_db)):
    rows = []
    for sp in s.execute(select(Specification).where(Specification.status == "APPROVED")).scalars():
        for par in versioning.parameters(s, sp):
            rows.append({"spec_no": sp.spec_no, "version": sp.version_no, "material_id": sp.material_id, **to_dict(par)})
    cols = [("spec_no", "Spec no"), ("version", "Version"), ("material_id", "Material id"), ("seq", "#"),
            ("test_name", "Test"), ("test_method", "Method"), ("spec_type", "Type"), ("lsl", "LSL"), ("usl", "USL"),
            ("target", "Target"), ("unit", "Unit"), ("acceptance_criteria", "Acceptance"), ("criticality", "Criticality")]
    return xlsx_response(s, p, "Approved specifications", {"status": "APPROVED"}, cols, rows, "specification")
