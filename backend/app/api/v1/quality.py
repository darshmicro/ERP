"""Phase 8 endpoints: deviation, CAPA, change control, risk assessment (FMEA), SOP control, complaints, recalls."""
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.crud import to_dict
from app.api.deps import Principal, get_db, get_principal, require
from app.api.helpers import page_args, use_reason
from app.core.errors import NotFound, PermissionDenied, ValidationFailed
from app.models.iam import User
from app.models.master import Location
from app.models.quality import (CAPA, CAPAAction, ChangeControl, Complaint, Deviation, Recall, RiskAssessment, SOP, SOPAcknowledgement)
from app.models.warehouse import MaterialBatch
from app.schemas.common import Reasoned
from app.services import documents, masters, quality_system as qs, versioning

router = APIRouter()


class SignedAction(Reasoned):
    password: str


def _page(s, stmt, Model, limit, offset, conv=to_dict):
    limit, offset = page_args(limit, offset)
    total = s.execute(select(func.count()).select_from(stmt.subquery())).scalar()
    rows = s.execute(stmt.order_by(Model.id.desc()).limit(limit).offset(offset)).scalars().all()
    return {"items": [conv(r) for r in rows], "total": total, "limit": limit, "offset": offset}


def _filters(stmt, Model, request: Request, names=("status",)):
    for f in names:
        if request.query_params.get(f):
            stmt = stmt.where(getattr(Model, f) == request.query_params[f])
    return stmt


def _like(stmt, col, q):
    return stmt.where(func.lower(col).like(f"%{q.lower()}%")) if q else stmt


# ============================================================ deviation
class DeviationIn(Reasoned):
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=3)
    category: str = "PROCESS"
    severity: str = Field(default="MINOR", pattern="^(MINOR|MAJOR|CRITICAL)$")
    entity_type: str | None = None
    record_id: int | None = None
    blocks_release: bool = True
    containment: str | None = None


class DeviationUpdate(Reasoned):
    model_config = {"extra": "forbid"}
    title: str | None = None
    description: str | None = None
    category: str | None = None
    severity: str | None = Field(default=None, pattern="^(MINOR|MAJOR|CRITICAL)$")
    containment: str | None = None
    root_cause: str | None = None
    impact_assessment: str | None = None
    no_capa_justification: str | None = None
    blocks_release: bool | None = None


def _dev_out(s: Session, d: Deviation) -> dict:
    out = to_dict(d)
    if d.entity_type == "MATERIAL_BATCH" and d.record_id:
        lot = s.get(MaterialBatch, d.record_id)
        out["ref_label"] = lot.lot_no if lot else None
    elif d.entity_type == "MFG_BATCH" and d.record_id:
        from app.models.manufacturing import ManufacturingBatch
        b = s.get(ManufacturingBatch, d.record_id)
        out["ref_label"] = b.batch_no if b else None
    if d.capa_id:
        c = s.get(CAPA, d.capa_id)
        out["capa_no"] = c.capa_no if c else None
    return out


@router.get("/deviations", tags=["Deviation"])
def list_deviations(request: Request, q: str | None = None, limit: int = Query(50), offset: int = Query(0),
                    p: Principal = Depends(require("quality.deviation.read")), s: Session = Depends(get_db)):
    stmt = _like(_filters(select(Deviation), Deviation, request, ("status", "severity", "source")), Deviation.dev_no, q)
    return _page(s, stmt, Deviation, limit, offset, lambda r: _dev_out(s, r))


@router.post("/deviations", status_code=201, tags=["Deviation"])
def create_deviation(body: DeviationIn, p: Principal = Depends(require("quality.deviation.create")), s: Session = Depends(get_db)):
    use_reason(body.reason or "Deviation raised")
    d = qs.raise_deviation(s, p.user.id, **body.model_dump(exclude={"reason"}))
    s.commit()
    return _dev_out(s, d)


def _dev(s, did):
    return masters.get_or_404(s, Deviation, did, "Deviation")


@router.get("/deviations/{did}", tags=["Deviation"])
def get_deviation(did: int, p: Principal = Depends(require("quality.deviation.read")), s: Session = Depends(get_db)):
    return _dev_out(s, _dev(s, did))


@router.patch("/deviations/{did}", tags=["Deviation"])
def update_deviation(did: int, body: DeviationUpdate, p: Principal = Depends(require("quality.deviation.update")), s: Session = Depends(get_db)):
    use_reason(body.reason or "Deviation updated")
    d = _dev(s, did)
    qs.update_deviation(s, d, body.model_dump(exclude={"reason"}, exclude_unset=True))
    s.commit()
    return _dev_out(s, d)


def _dev_action(path: str, perm: str, fn):
    @router.post(f"/deviations/{{did}}/{path}", tags=["Deviation"], name=f"deviation_{path}")
    def act(did: int, body: Reasoned, p: Principal = Depends(require(perm)), s: Session = Depends(get_db)):
        use_reason(body.reason)
        d = _dev(s, did)
        fn(s, d, body.reason or "")
        s.commit()
        return _dev_out(s, d)


_dev_action("investigate", "quality.deviation.investigate", lambda s, d, r: qs.start_investigation(s, d))
_dev_action("propose-capa", "quality.deviation.investigate", lambda s, d, r: qs.propose_capa(s, d))
_dev_action("submit-review", "quality.deviation.investigate", lambda s, d, r: qs.submit_dev_for_review(s, d))
_dev_action("return", "quality.deviation.close", lambda s, d, r: qs.return_deviation(s, d, r))
_dev_action("cancel", "quality.deviation.cancel", lambda s, d, r: qs.cancel_deviation(s, d, r))


@router.post("/deviations/{did}/close", tags=["Deviation"])
def close_deviation(did: int, body: SignedAction, p: Principal = Depends(require("quality.deviation.close")), s: Session = Depends(get_db)):
    use_reason(body.reason)
    d = _dev(s, did)
    qs.close_deviation(s, d, p.user, body.password, body.reason or "")
    s.commit()
    return _dev_out(s, d)


# ============================================================ CAPA
class CapaIn(Reasoned):
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=3)
    capa_type: str = Field(default="CORRECTIVE", pattern="^(CORRECTIVE|PREVENTIVE)$")
    source: str = Field(default="DEVIATION", pattern="^(DEVIATION|OOS|COMPLAINT|AUDIT|OTHER)$")
    source_ref: str | None = None
    owner_id: int
    due_date: date


class ActionIn(BaseModel):
    description: str = Field(min_length=3, max_length=500)
    owner_id: int
    due_date: date


def _capa_out(s: Session, c: CAPA, detail: bool = False) -> dict:
    out = to_dict(c)
    o = s.get(User, c.owner_id)
    out["owner"] = o.full_name if o else None
    out["overdue"] = c.status in ("OPEN", "IN_PROGRESS") and c.due_date < date.today()
    if detail:
        out["actions"] = [to_dict(a) for a in qs.capa_actions(s, c.id)]
    return out


@router.get("/capas", tags=["CAPA"])
def list_capas(request: Request, q: str | None = None, limit: int = Query(50), offset: int = Query(0), p: Principal = Depends(require("quality.capa.read")), s: Session = Depends(get_db)):
    stmt = _like(_filters(select(CAPA), CAPA, request, ("status", "source")), CAPA.capa_no, q)
    return _page(s, stmt, CAPA, limit, offset, lambda r: _capa_out(s, r))


@router.post("/capas", status_code=201, tags=["CAPA"])
def create_capa(body: CapaIn, p: Principal = Depends(require("quality.capa.create")), s: Session = Depends(get_db)):
    use_reason(body.reason or "CAPA created")
    c = qs.create_capa(s, p.user, body.model_dump(exclude={"reason"}))
    s.commit()
    return _capa_out(s, c, True)


def _capa(s, cid):
    return masters.get_or_404(s, CAPA, cid, "CAPA")


@router.get("/capas/{cid}", tags=["CAPA"])
def get_capa(cid: int, p: Principal = Depends(require("quality.capa.read")), s: Session = Depends(get_db)):
    return _capa_out(s, _capa(s, cid), True)


@router.post("/capas/{cid}/actions", status_code=201, tags=["CAPA"])
def add_action(cid: int, body: ActionIn, p: Principal = Depends(require("quality.capa.update")), s: Session = Depends(get_db)):
    c = _capa(s, cid)
    a = qs.add_action(s, c, body.description, body.owner_id, body.due_date)
    s.commit()
    return to_dict(a)


class CompleteActionIn(Reasoned):
    notes: str = Field(min_length=3)


@router.post("/capas/{cid}/actions/{aid}/complete", tags=["CAPA"])
def complete_action(cid: int, aid: int, body: CompleteActionIn, p: Principal = Depends(require("quality.capa.update")), s: Session = Depends(get_db)):
    use_reason(body.reason or body.notes)
    c = _capa(s, cid)
    a = masters.get_or_404(s, CAPAAction, aid, "Action")
    qs.complete_action(s, c, a, p.user, body.notes)
    s.commit()
    return to_dict(a)


class EffectivenessIn(Reasoned):
    effectiveness_due: date


@router.post("/capas/{cid}/effectiveness-check", tags=["CAPA"])
def start_effectiveness(cid: int, body: EffectivenessIn, p: Principal = Depends(require("quality.capa.update")), s: Session = Depends(get_db)):
    use_reason(body.reason or "All actions completed")
    c = _capa(s, cid)
    qs.start_effectiveness(s, c, body.effectiveness_due)
    s.commit()
    return _capa_out(s, c, True)


class CapaCloseIn(SignedAction):
    effective: bool = True


@router.post("/capas/{cid}/close", tags=["CAPA"])
def close_capa(cid: int, body: CapaCloseIn, p: Principal = Depends(require("quality.capa.close")), s: Session = Depends(get_db)):
    use_reason(body.reason)
    c = _capa(s, cid)
    qs.close_capa(s, c, p.user, body.password, body.effective, body.reason or "")
    s.commit()
    return _capa_out(s, c, True)


@router.post("/capas/{cid}/cancel", tags=["CAPA"])
def cancel_capa(cid: int, body: Reasoned, p: Principal = Depends(require("quality.capa.close")), s: Session = Depends(get_db)):
    use_reason(body.reason)
    c = _capa(s, cid)
    if not (body.reason or "").strip():
        raise ValidationFailed("A reason is required", code="REASON_REQUIRED")
    from app.workflows.state_machine import transition
    c.cancel_reason = body.reason
    transition(s, qs.CAPA_MACHINE, c, "CANCELLED", reason=body.reason, module="quality")
    s.commit()
    return _capa_out(s, c)


# ============================================================ change control
class CCIn(Reasoned):
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=3)
    change_type: str = Field(default="MASTER_DATA", pattern="^(MASTER_DATA|PROCESS|EQUIPMENT|DOCUMENT|SYSTEM|OTHER)$")


class CCUpdate(Reasoned):
    model_config = {"extra": "forbid"}
    title: str | None = None
    description: str | None = None
    change_type: str | None = None


def _cc_out(s: Session, cc: ChangeControl, detail: bool = False) -> dict:
    out = to_dict(cc)
    if detail:
        links = []
        for l in qs.cc_links(s, cc.id):
            obj = s.get(masters.model_for_table(l.entity), l.record_id)
            links.append({**to_dict(l), "status": obj.status if obj else None, "version_no": getattr(obj, "version_no", None),
                          "number": getattr(obj, getattr(type(obj), "__version_key__", "id"), None) if obj else None})
        out["links"] = links
    return out


def _cc(s, cid):
    return masters.get_or_404(s, ChangeControl, cid, "Change control")


@router.get("/change-controls", tags=["Change control"])
def list_cc(request: Request, q: str | None = None, limit: int = Query(50), offset: int = Query(0), p: Principal = Depends(require("quality.cc.read")), s: Session = Depends(get_db)):
    stmt = _like(_filters(select(ChangeControl), ChangeControl, request, ("status", "change_type")), ChangeControl.cc_no, q)
    return _page(s, stmt, ChangeControl, limit, offset, lambda r: _cc_out(s, r))


@router.post("/change-controls", status_code=201, tags=["Change control"])
def create_cc(body: CCIn, p: Principal = Depends(require("quality.cc.create")), s: Session = Depends(get_db)):
    use_reason(body.reason or "Change control raised")
    cc = qs.create_cc(s, p.user, body.model_dump(exclude={"reason"}))
    s.commit()
    return _cc_out(s, cc, True)


@router.get("/change-controls/{cid}", tags=["Change control"])
def get_cc(cid: int, p: Principal = Depends(require("quality.cc.read")), s: Session = Depends(get_db)):
    return _cc_out(s, _cc(s, cid), True)


@router.patch("/change-controls/{cid}", tags=["Change control"])
def update_cc(cid: int, body: CCUpdate, p: Principal = Depends(require("quality.cc.update")), s: Session = Depends(get_db)):
    use_reason(body.reason or "Change control updated")
    cc = _cc(s, cid)
    for k, v in body.model_dump(exclude={"reason"}, exclude_unset=True).items():
        setattr(cc, k, v)
    s.commit()
    return _cc_out(s, cc, True)


class LinkIn(Reasoned):
    entity: str
    record_id: int


@router.post("/change-controls/{cid}/links", status_code=201, tags=["Change control"])
def link_cc(cid: int, body: LinkIn, p: Principal = Depends(require("quality.cc.update")), s: Session = Depends(get_db)):
    use_reason(body.reason or "Master change linked")
    cc = _cc(s, cid)
    qs.link_master(s, cc, body.entity, body.record_id)
    s.commit()
    return _cc_out(s, cc, True)


@router.post("/change-controls/{cid}/submit", tags=["Change control"])
def submit_cc(cid: int, p: Principal = Depends(require("quality.cc.update")), s: Session = Depends(get_db)):
    cc = _cc(s, cid)
    qs.submit_assessment(s, cc)
    s.commit()
    return _cc_out(s, cc, True)


class AssessIn(Reasoned):
    impact_assessment: str = Field(min_length=3)
    risk_level: str = Field(pattern="^(LOW|MEDIUM|HIGH)$")
    regulatory_impact: bool = False


@router.post("/change-controls/{cid}/assess", tags=["Change control"])
def assess_cc(cid: int, body: AssessIn, p: Principal = Depends(require("quality.cc.assess")), s: Session = Depends(get_db)):
    use_reason(body.reason or "Impact assessed")
    cc = _cc(s, cid)
    qs.complete_assessment(s, cc, body.impact_assessment, body.risk_level, body.regulatory_impact)
    s.commit()
    return _cc_out(s, cc, True)


class CCDecision(SignedAction):
    approve: bool = True


@router.post("/change-controls/{cid}/decision", tags=["Change control"])
def decide_cc(cid: int, body: CCDecision, p: Principal = Depends(require("quality.cc.approve")), s: Session = Depends(get_db)):
    use_reason(body.reason)
    cc = _cc(s, cid)
    qs.decide_cc(s, cc, p.user, body.password, body.approve, body.reason or "")
    s.commit()
    return _cc_out(s, cc, True)


class NotesIn(Reasoned):
    notes: str = Field(min_length=3)


@router.post("/change-controls/{cid}/implemented", tags=["Change control"])
def implemented_cc(cid: int, body: NotesIn, p: Principal = Depends(require("quality.cc.update")), s: Session = Depends(get_db)):
    use_reason(body.reason or body.notes)
    cc = _cc(s, cid)
    qs.complete_implementation(s, cc, body.notes)
    s.commit()
    return _cc_out(s, cc, True)


class CCClose(SignedAction):
    notes: str = Field(min_length=3)


@router.post("/change-controls/{cid}/close", tags=["Change control"])
def close_cc(cid: int, body: CCClose, p: Principal = Depends(require("quality.cc.close")), s: Session = Depends(get_db)):
    use_reason(body.reason or body.notes)
    cc = _cc(s, cid)
    qs.close_cc(s, cc, p.user, body.password, body.notes)
    s.commit()
    return _cc_out(s, cc, True)


@router.post("/change-controls/{cid}/cancel", tags=["Change control"])
def cancel_cc(cid: int, body: Reasoned, p: Principal = Depends(require("quality.cc.update")), s: Session = Depends(get_db)):
    use_reason(body.reason)
    cc = _cc(s, cid)
    qs.cancel_cc(s, cc, body.reason or "")
    s.commit()
    return _cc_out(s, cc)


# ============================================================ risk assessment
class RiskItemIn(BaseModel):
    function_step: str = Field(min_length=2, max_length=200)
    failure_mode: str = Field(min_length=2, max_length=300)
    effect: str | None = None
    cause: str | None = None
    controls: str | None = None
    severity: int = Field(ge=1, le=10)
    occurrence: int = Field(ge=1, le=10)
    detection: int = Field(ge=1, le=10)
    mitigation: str | None = None
    residual_severity: int | None = Field(default=None, ge=1, le=10)
    residual_occurrence: int | None = Field(default=None, ge=1, le=10)
    residual_detection: int | None = Field(default=None, ge=1, le=10)


class RiskIn(Reasoned):
    title: str = Field(min_length=3, max_length=200)
    scope: str | None = None
    ref_type: str | None = None
    ref_no: str | None = None
    items: list[RiskItemIn] = []


def _ra_out(s: Session, ra: RiskAssessment, detail: bool = False) -> dict:
    out = to_dict(ra)
    items = qs.ra_items(s, ra.id)
    out["max_rpn"] = max((i.rpn for i in items), default=0)
    out["high_items"] = sum(1 for i in items if i.risk_level == "HIGH")
    if detail:
        out["items"] = [to_dict(i) for i in items]
    return out


def _ra(s, rid):
    return masters.get_or_404(s, RiskAssessment, rid, "Risk assessment")


@router.get("/risk-assessments", tags=["Risk"])
def list_ra(request: Request, q: str | None = None, limit: int = Query(50), offset: int = Query(0), p: Principal = Depends(require("quality.risk.read")), s: Session = Depends(get_db)):
    stmt = _like(_filters(select(RiskAssessment), RiskAssessment, request), RiskAssessment.ra_no, q)
    return _page(s, stmt, RiskAssessment, limit, offset, lambda r: _ra_out(s, r))


@router.post("/risk-assessments", status_code=201, tags=["Risk"])
def create_ra(body: RiskIn, p: Principal = Depends(require("quality.risk.create")), s: Session = Depends(get_db)):
    use_reason(body.reason or "Risk assessment created")
    ra = qs.create_ra(s, p.user, body.model_dump(include={"title", "scope", "ref_type", "ref_no"}), [i.model_dump() for i in body.items])
    s.commit()
    return _ra_out(s, ra, True)


@router.get("/risk-assessments/{rid}", tags=["Risk"])
def get_ra(rid: int, p: Principal = Depends(require("quality.risk.read")), s: Session = Depends(get_db)):
    return _ra_out(s, _ra(s, rid), True)


class RiskItemsIn(Reasoned):
    items: list[RiskItemIn]


@router.put("/risk-assessments/{rid}/items", tags=["Risk"])
def put_items(rid: int, body: RiskItemsIn, p: Principal = Depends(require("quality.risk.update")), s: Session = Depends(get_db)):
    use_reason(body.reason or "FMEA items updated")
    ra = _ra(s, rid)
    qs.set_items(s, ra, [i.model_dump() for i in body.items])
    s.commit()
    return _ra_out(s, ra, True)


@router.post("/risk-assessments/{rid}/approve", tags=["Risk"])
def approve_ra(rid: int, body: SignedAction, p: Principal = Depends(require("quality.risk.approve")), s: Session = Depends(get_db)):
    use_reason(body.reason)
    ra = _ra(s, rid)
    qs.approve_ra(s, ra, p.user, body.password, body.reason or "")
    s.commit()
    return _ra_out(s, ra, True)


# ============================================================ SOP control
def _sop_out(s: Session, sop: SOP, detail: bool = False, user_id: int | None = None) -> dict:
    out = to_dict(sop)
    if sop.document_id:
        from app.models.platform import Document
        d = s.get(Document, sop.document_id)
        out["document"] = {"id": d.id, "name": d.original_name, "sha256": d.sha256} if d else None
    out["review_overdue"] = bool(sop.status == "APPROVED" and sop.review_due_date and sop.review_due_date < date.today())
    if detail:
        out["acknowledgements"] = s.execute(select(func.count()).select_from(SOPAcknowledgement).where(SOPAcknowledgement.sop_id == sop.id)).scalar()
        if user_id:
            out["acknowledged_by_me"] = bool(s.execute(select(SOPAcknowledgement.id).where(SOPAcknowledgement.sop_id == sop.id, SOPAcknowledgement.user_id == user_id)).first())
        out["versions"] = [{"id": v.id, "version_no": v.version_no, "status": v.status, "change_reason": v.change_reason} for v in versioning.history(s, sop)]
    return out


def _sop(s, sid):
    return masters.get_or_404(s, SOP, sid, "SOP")


class SopIn(Reasoned):
    sop_no: str | None = None
    title: str = Field(min_length=3, max_length=200)
    department_id: int | None = None
    owner_id: int | None = None
    review_period_months: int = Field(default=24, ge=1, le=120)


@router.get("/sops", tags=["SOP"])
def list_sops(request: Request, q: str | None = None, limit: int = Query(50), offset: int = Query(0), p: Principal = Depends(require("quality.sop.read")), s: Session = Depends(get_db)):
    stmt = select(SOP)
    if q:
        stmt = stmt.where(func.lower(SOP.sop_no).like(f"%{q.lower()}%") | func.lower(SOP.title).like(f"%{q.lower()}%"))
    stmt = _filters(stmt, SOP, request)
    return _page(s, stmt, SOP, limit, offset, lambda r: _sop_out(s, r))


@router.post("/sops", status_code=201, tags=["SOP"])
def create_sop(body: SopIn, p: Principal = Depends(require("quality.sop.create")), s: Session = Depends(get_db)):
    use_reason(body.reason or "SOP drafted")
    sop = versioning.create_draft(s, SOP, body.model_dump(exclude={"reason", "sop_no"}, exclude_none=True), body.sop_no)
    s.commit()
    return _sop_out(s, sop, True)


@router.get("/sops/{sid}", tags=["SOP"])
def get_sop(sid: int, p: Principal = Depends(require("quality.sop.read")), s: Session = Depends(get_db)):
    return _sop_out(s, _sop(s, sid), True, p.user.id)


@router.post("/sops/{sid}/document", tags=["SOP"])
async def attach_sop_document(sid: int, file: UploadFile = File(...), p: Principal = Depends(require("quality.sop.update")), s: Session = Depends(get_db)):
    sop = _sop(s, sid)
    data = await file.read()
    doc = documents.store(s, file.filename or "sop.pdf", data, allowed_ext={".pdf"}, doc_no=sop.sop_no, version=str(sop.version_no))
    sop.document_id = doc.id
    s.commit()
    return _sop_out(s, sop, True)


@router.post("/sops/{sid}/submit", tags=["SOP"])
def submit_sop(sid: int, p: Principal = Depends(require("quality.sop.update")), s: Session = Depends(get_db)):
    sop = _sop(s, sid)
    versioning.submit(s, sop)
    s.commit()
    return _sop_out(s, sop)


@router.post("/sops/{sid}/approve", tags=["SOP"])
def approve_sop(sid: int, body: SignedAction, p: Principal = Depends(require("quality.sop.approve")), s: Session = Depends(get_db)):
    use_reason(body.reason)
    sop = _sop(s, sid)
    qs.approve_sop(s, sop, p.user, body.password, body.reason or "")
    s.commit()
    return _sop_out(s, sop, True, p.user.id)


@router.post("/sops/{sid}/new-version", status_code=201, tags=["SOP"])
def new_sop_version(sid: int, body: Reasoned, p: Principal = Depends(require("quality.sop.create")), s: Session = Depends(get_db)):
    use_reason(body.reason)
    sop = _sop(s, sid)
    new = versioning.new_version(s, sop, body.reason or "")
    s.commit()
    return _sop_out(s, new, True)


@router.post("/sops/{sid}/acknowledge", tags=["SOP"])
def acknowledge_sop(sid: int, p: Principal = Depends(require("quality.sop.acknowledge")), s: Session = Depends(get_db)):
    sop = _sop(s, sid)
    qs.acknowledge_sop(s, sop, p.user)
    s.commit()
    return _sop_out(s, sop, True, p.user.id)


@router.get("/sops-review-due", tags=["SOP"])
def sops_review_due(days: int = 30, p: Principal = Depends(require("quality.sop.read")), s: Session = Depends(get_db)):
    return [_sop_out(s, x) for x in qs.sops_due_for_review(s, days)]


# ============================================================ complaints
class ComplaintIn(Reasoned):
    received_on: date | None = None
    customer_id: int | None = None
    material_batch_id: int | None = None
    dispatch_id: int | None = None
    category: str = Field(default="QUALITY", pattern="^(QUALITY|ADVERSE_EVENT|PACKAGING|DELIVERY|OTHER)$")
    severity: str = Field(default="MINOR", pattern="^(MINOR|MAJOR|CRITICAL)$")
    description: str = Field(min_length=3)


def _cmp(s, cid):
    return masters.get_or_404(s, Complaint, cid, "Complaint")


@router.get("/complaints", tags=["Complaint"])
def list_complaints(request: Request, q: str | None = None, limit: int = Query(50), offset: int = Query(0), p: Principal = Depends(require("quality.complaint.read")), s: Session = Depends(get_db)):
    stmt = _like(_filters(select(Complaint), Complaint, request, ("status", "severity")), Complaint.complaint_no, q)
    return _page(s, stmt, Complaint, limit, offset)


@router.post("/complaints", status_code=201, tags=["Complaint"])
def create_complaint(body: ComplaintIn, p: Principal = Depends(require("quality.complaint.create")), s: Session = Depends(get_db)):
    use_reason(body.reason or "Complaint received")
    c = qs.create_complaint(s, p.user, body.model_dump(exclude={"reason"}, exclude_none=True))
    s.commit()
    return to_dict(c)


@router.get("/complaints/{cid}", tags=["Complaint"])
def get_complaint(cid: int, p: Principal = Depends(require("quality.complaint.read")), s: Session = Depends(get_db)):
    return to_dict(_cmp(s, cid))


class InvestigationIn(Reasoned):
    investigation: str = Field(min_length=3)


@router.post("/complaints/{cid}/investigate", tags=["Complaint"])
def investigate_complaint(cid: int, body: InvestigationIn, p: Principal = Depends(require("quality.complaint.update")), s: Session = Depends(get_db)):
    use_reason(body.reason or "Investigation recorded")
    c = _cmp(s, cid)
    qs.investigate_complaint(s, c, body.investigation)
    s.commit()
    return to_dict(c)


@router.post("/complaints/{cid}/deviation", status_code=201, tags=["Complaint"])
def complaint_deviation(cid: int, p: Principal = Depends(require("quality.deviation.create")), s: Session = Depends(get_db)):
    c = _cmp(s, cid)
    d = qs.deviation_from_complaint(s, p.user, c)
    s.commit()
    return _dev_out(s, d)


class ComplaintClose(SignedAction):
    conclusion: str = Field(min_length=3)


@router.post("/complaints/{cid}/close", tags=["Complaint"])
def close_complaint(cid: int, body: ComplaintClose, p: Principal = Depends(require("quality.complaint.close")), s: Session = Depends(get_db)):
    use_reason(body.reason or body.conclusion)
    c = _cmp(s, cid)
    qs.close_complaint(s, c, p.user, body.password, body.conclusion)
    s.commit()
    return to_dict(c)


# ============================================================ recall
class RecallIn(SignedAction):
    material_batch_id: int
    recall_class: str = Field(default="II", pattern="^(I|II|III)$")
    complaint_id: int | None = None


def _rc_out(s: Session, rc: Recall, detail: bool = False) -> dict:
    out = to_dict(rc)
    lot = s.get(MaterialBatch, rc.material_batch_id)
    out["lot_no"] = lot.lot_no
    if detail:
        from app.models.dispatch import Dispatch
        from app.models.master import Customer
        lines = []
        for l in qs.recall_lines(s, rc.id):
            lines.append({**to_dict(l), "dispatch_no": s.get(Dispatch, l.dispatch_id).dispatch_no, "customer": s.get(Customer, l.customer_id).name})
        out["lines"] = lines
        out["reconciliation"] = qs.recall_reconciliation(s, rc)
    return out


def _rc(s, rid):
    return masters.get_or_404(s, Recall, rid, "Recall")


@router.get("/recalls", tags=["Recall"])
def list_recalls(request: Request, limit: int = Query(50), offset: int = Query(0), p: Principal = Depends(require("quality.recall.read")), s: Session = Depends(get_db)):
    return _page(s, _filters(select(Recall), Recall, request), Recall, limit, offset, lambda r: _rc_out(s, r))


@router.post("/recalls", status_code=201, tags=["Recall"])
def initiate_recall(body: RecallIn, p: Principal = Depends(require("quality.recall.create")), s: Session = Depends(get_db)):
    use_reason(body.reason)
    lot = masters.get_or_404(s, MaterialBatch, body.material_batch_id, "Lot")
    rc = qs.initiate_recall(s, p.user, lot, body.recall_class, body.reason or "", body.password, body.complaint_id)
    s.commit()
    return _rc_out(s, rc, True)


@router.get("/recalls/{rid}", tags=["Recall"])
def get_recall(rid: int, p: Principal = Depends(require("quality.recall.read")), s: Session = Depends(get_db)):
    return _rc_out(s, _rc(s, rid), True)


class NotifyIn(Reasoned):
    response: str | None = None


@router.post("/recalls/{rid}/lines/{lid}/notify", tags=["Recall"])
def notify_line(rid: int, lid: int, body: NotifyIn, p: Principal = Depends(require("quality.recall.update")), s: Session = Depends(get_db)):
    from app.models.quality import RecallLine
    rc = _rc(s, rid)
    qs.notify_customer(s, rc, masters.get_or_404(s, RecallLine, lid, "Recall line"), body.response)
    s.commit()
    return _rc_out(s, rc, True)


class ReturnIn(Reasoned):
    returned: Decimal = Field(default=Decimal(0), ge=0)
    unrecoverable: Decimal = Field(default=Decimal(0), ge=0)
    location_id: int | None = None


@router.post("/recalls/{rid}/lines/{lid}/return", tags=["Recall"])
def line_return(rid: int, lid: int, body: ReturnIn, p: Principal = Depends(require("quality.recall.update")), s: Session = Depends(get_db)):
    from app.models.quality import RecallLine
    use_reason(body.reason or "Recalled goods received")
    rc = _rc(s, rid)
    loc = s.get(Location, body.location_id) if body.location_id else None
    qs.record_return(s, rc, masters.get_or_404(s, RecallLine, lid, "Recall line"), body.returned, body.unrecoverable, loc)
    s.commit()
    return _rc_out(s, rc, True)


class RecallClose(SignedAction):
    summary: str = Field(min_length=3)


@router.post("/recalls/{rid}/close", tags=["Recall"])
def close_recall(rid: int, body: RecallClose, p: Principal = Depends(require("quality.recall.close")), s: Session = Depends(get_db)):
    use_reason(body.reason or body.summary)
    rc = _rc(s, rid)
    qs.close_recall(s, rc, p.user, body.password, body.summary)
    s.commit()
    return _rc_out(s, rc, True)
