"""Phase 5 endpoints: sampling, QC tests/results, amendments, release, OOS/OOT, trends, CoA, conditional release."""
from datetime import date, datetime, timezone
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
from app.models.iam import User
from app.models.master import Equipment, Location, Material
from app.models.platform import Document
from app.models.qc import (COA, ConditionalRelease, OOSInvestigation, OOTEvent, QCResult, QCResultAmendment, QCTest, Sample)
from app.models.spec import SamplingPlan, SpecificationParameter
from app.models.warehouse import MaterialBatch
from app.schemas.common import Reasoned
from app.services import coa as coa_svc
from app.services import config_service, documents, labels, lots, masters, qc, stats, versioning
from app.services import purchasing as pur

router = APIRouter()


class SignedAction(Reasoned):
    password: str


def _page(s, stmt, Model, limit, offset, conv=to_dict):
    limit, offset = page_args(limit, offset)
    total = s.execute(select(func.count()).select_from(stmt.subquery())).scalar()
    rows = s.execute(stmt.order_by(Model.id.desc()).limit(limit).offset(offset)).scalars().all()
    return {"items": [conv(r) for r in rows], "total": total, "limit": limit, "offset": offset}


# ============================================================ samples
class SampleIn(Reasoned):
    material_batch_id: int
    quantity_sampled: Decimal = Field(gt=0)
    containers_sampled: int = Field(default=1, ge=1)
    sampling_location_id: int
    sample_type: str = "RM_SAMPLE"
    remarks: str | None = None


class AssignIn(Reasoned):
    analyst_id: int | None = None
    parameter_ids: list[int] | None = None


def _sample_out(s: Session, sm: Sample, detail: bool = False) -> dict:
    d = to_dict(sm)
    if sm.material_batch_id:
        lot = s.get(MaterialBatch, sm.material_batch_id)
        m = s.get(Material, lot.material_id)
        d.update(lot_no=lot.lot_no, material_code=m.material_code, material_name=m.name)
    if detail:
        tests = []
        for t in s.execute(select(QCTest).where(QCTest.sample_id == sm.id).order_by(QCTest.id)).scalars():
            td = to_dict(t)
            r = s.execute(select(QCResult).where(QCResult.test_id == t.id)).scalars().first()
            if r:
                td["result"] = {**to_dict(r), "effective": {k: (float(v) if isinstance(v, Decimal) else v) for k, v in qc.effective(s, r).items()}}
            if t.analyst_id:
                td["analyst"] = s.get(User, t.analyst_id).full_name
            tests.append(td)
        d["tests"] = tests
    return d


@router.get("/lots/{lid}/sampling-requirements", tags=["Sampling"])
def sampling_requirements(lid: int, p: Principal = Depends(require("qc.sample.read")), s: Session = Depends(get_db)):
    lot = masters.get_or_404(s, MaterialBatch, lid, "Lot")
    plan = versioning.version_in_force(s, SamplingPlan, SamplingPlan.material_id == lot.material_id)
    return qc.required_sampling(s, lot, plan)


@router.get("/samples", tags=["Sampling"])
def list_samples(request: Request, q: str | None = None, limit: int = Query(50), offset: int = Query(0),
                 p: Principal = Depends(require("qc.sample.read")), s: Session = Depends(get_db)):
    stmt = select(Sample)
    if q:
        stmt = stmt.where(func.lower(Sample.sample_no).like(f"%{q.lower()}%"))
    for f in ("status", "sample_type", "material_batch_id"):
        if request.query_params.get(f):
            stmt = stmt.where(getattr(Sample, f) == request.query_params[f])
    return _page(s, stmt, Sample, limit, offset, lambda x: _sample_out(s, x))


@router.post("/samples", status_code=201, tags=["Sampling"])
def create_sample(body: SampleIn, p: Principal = Depends(require("qc.sample.create")), s: Session = Depends(get_db)):
    use_reason(body.reason or "Sample taken")
    lot = masters.get_or_404(s, MaterialBatch, body.material_batch_id, "Lot")
    sm = qc.create_sample(s, p.user, lot, body.quantity_sampled, body.containers_sampled, body.sampling_location_id, body.remarks, body.sample_type)
    s.commit()
    return _sample_out(s, sm, True)


@router.get("/samples/{sid}", tags=["Sampling"])
def get_sample(sid: int, p: Principal = Depends(require("qc.sample.read")), s: Session = Depends(get_db)):
    return _sample_out(s, masters.get_or_404(s, Sample, sid, "Sample"), True)


@router.post("/samples/{sid}/assign", tags=["QC tests"])
def assign(sid: int, body: AssignIn, p: Principal = Depends(require("qc.test.assign")), s: Session = Depends(get_db)):
    use_reason(body.reason or "Tests assigned")
    sm = masters.get_or_404(s, Sample, sid, "Sample")
    qc.assign_tests(s, sm, body.analyst_id, body.parameter_ids)
    s.commit()
    return _sample_out(s, sm, True)


@router.post("/samples/{sid}/label", tags=["Labels"])
def sample_label(sid: int, p: Principal = Depends(require("label.lot.print")), s: Session = Depends(get_db)):
    sm = masters.get_or_404(s, Sample, sid, "Sample")
    lot = s.get(MaterialBatch, sm.material_batch_id)
    pdf, row = labels.print_sample_label(s, sm, lot, p.user.id)
    s.commit()
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{row.label_no}.pdf"'})


class RetainIn(Reasoned):
    retention_until: date


@router.post("/samples/{sid}/retain", tags=["Sampling"])
def retain_sample(sid: int, body: RetainIn, p: Principal = Depends(require("qc.sample.read", "qc.test.assign")), s: Session = Depends(get_db)):
    use_reason(body.reason or "Sample retained")
    sm = masters.get_or_404(s, Sample, sid, "Sample")
    qc.retain(s, sm, body.retention_until)
    s.commit()
    return _sample_out(s, sm)


@router.post("/samples/{sid}/dispose", tags=["Sampling"])
def dispose_sample(sid: int, body: SignedAction, p: Principal = Depends(require("qc.sample.dispose")), s: Session = Depends(get_db)):
    use_reason(body.reason)
    sm = masters.get_or_404(s, Sample, sid, "Sample")
    qc.dispose(s, sm, p.user, body.password, body.reason or "")
    s.commit()
    return _sample_out(s, sm)


# ============================================================ tests & results
class StartIn(BaseModel):
    equipment_id: int | None = None


class ResultIn(Reasoned):
    value: Decimal | None = None
    conforms: bool | None = None
    text: str | None = None
    remarks: str | None = None


@router.get("/qc/tests", tags=["QC tests"])
def list_tests(request: Request, mine: bool = False, limit: int = Query(100), offset: int = Query(0), p: Principal = Depends(require("qc.test.read")), s: Session = Depends(get_db)):
    stmt = select(QCTest)
    if mine:
        stmt = stmt.where(QCTest.analyst_id == p.user.id)
    if request.query_params.get("status"):
        stmt = stmt.where(QCTest.status == request.query_params["status"])
    return _page(s, stmt, QCTest, limit, offset)


@router.post("/qc/tests/{tid}/start", tags=["QC tests"])
def start_test(tid: int, body: StartIn, p: Principal = Depends(require("qc.test.start")), s: Session = Depends(get_db)):
    use_reason("Test started")
    t = masters.get_or_404(s, QCTest, tid, "Test")
    qc.start_test(s, t, p.user, body.equipment_id)
    s.commit()
    return to_dict(t)


@router.post("/qc/tests/{tid}/override-calibration", tags=["QC tests"])
def override_cal(tid: int, body: SignedAction, p: Principal = Depends(require("qc.test.override_calibration")), s: Session = Depends(get_db)):
    use_reason(body.reason)
    t = masters.get_or_404(s, QCTest, tid, "Test")
    qc.override_calibration(s, t, p.user, body.password, body.reason or "")
    s.commit()
    return to_dict(t)


@router.post("/qc/tests/{tid}/result", status_code=201, tags=["QC tests"])
def enter_result(tid: int, body: ResultIn, p: Principal = Depends(require("qc.test.enter")), s: Session = Depends(get_db)):
    use_reason(body.reason or "Result entered")
    t = masters.get_or_404(s, QCTest, tid, "Test")
    r = qc.enter_result(s, t, p.user, value=body.value, text=body.text, conforms=body.conforms, remarks=body.remarks)
    s.commit()
    return {**to_dict(r), "test": to_dict(t)}


@router.post("/qc/tests/{tid}/retest", status_code=201, tags=["QC tests"])
def retest(tid: int, p: Principal = Depends(require("qc.test.assign")), s: Session = Depends(get_db)):
    use_reason("Retest after invalidated OOS")
    t = masters.get_or_404(s, QCTest, tid, "Test")
    n = qc.retest(s, t, p.user)
    s.commit()
    return to_dict(n)


class AmendIn(Reasoned):
    value: Decimal | None = None
    conforms: bool | None = None
    reason: str = Field(min_length=3)


class DecisionIn(SignedAction):
    approve: bool = True


@router.post("/qc/results/{rid}/amendments", status_code=201, tags=["QC tests"])
def request_amendment(rid: int, body: AmendIn, p: Principal = Depends(require("qc.result.amend_request")), s: Session = Depends(get_db)):
    use_reason(body.reason)
    r = masters.get_or_404(s, QCResult, rid, "Result")
    a = qc.request_amendment(s, p.user, r, body.value, body.conforms, body.reason)
    s.commit()
    return to_dict(a)


@router.get("/qc/results/{rid}/amendments", tags=["QC tests"])
def list_amendments(rid: int, p: Principal = Depends(require("qc.test.read")), s: Session = Depends(get_db)):
    return [to_dict(a) for a in s.execute(select(QCResultAmendment).where(QCResultAmendment.result_id == rid).order_by(QCResultAmendment.id)).scalars()]


@router.post("/qc/amendments/{aid}/decision", tags=["QC tests"])
def decide_amendment(aid: int, body: DecisionIn, p: Principal = Depends(require("qc.result.amend_approve")), s: Session = Depends(get_db)):
    use_reason(body.reason)
    a = masters.get_or_404(s, QCResultAmendment, aid, "Amendment")
    qc.decide_amendment(s, a, p.user, body.password, body.approve, body.reason or "")
    s.commit()
    return to_dict(a)


# ============================================================ release workflow
class ReleaseAct(BaseModel):
    decision: str = Field(pattern="^(APPROVE|REJECT)$")
    comment: str | None = None
    password: str | None = None


@router.get("/lots/{lid}/release", tags=["Release"])
def release_status(lid: int, p: Principal = Depends(require("inventory.lot.read")), s: Session = Depends(get_db)):
    lot = masters.get_or_404(s, MaterialBatch, lid, "Lot")
    insts = s.execute(select(qc.WorkflowInstance).where(qc.WorkflowInstance.entity == "material_batch", qc.WorkflowInstance.record_id == str(lid))
                      .order_by(qc.WorkflowInstance.id.desc())).scalars().all()
    return {"disposition": lot.disposition, "readiness": qc.release_readiness(s, lot) if lot.disposition == "QC_TESTING" else [],
            "workflow": pur.workflow_view(s, insts[0].id) if insts else None, "qc_no": lot.qc_no, "qa_release_no": lot.qa_release_no}


@router.post("/lots/{lid}/submit-release", tags=["Release"])
def submit_release(lid: int, p: Principal = Depends(require("qc.release.submit")), s: Session = Depends(get_db)):
    lot = masters.get_or_404(s, MaterialBatch, lid, "Lot")
    qc.submit_for_release(s, lot, p.user)
    s.commit()
    return release_status(lid, p, s)


@router.post("/lots/{lid}/release-decision", tags=["Release"])
def release_decision(lid: int, body: ReleaseAct, p: Principal = Depends(require("qc.release.approve")), s: Session = Depends(get_db)):
    use_reason(body.comment or f"Release {body.decision.lower()}")
    lot = masters.get_or_404(s, MaterialBatch, lid, "Lot")
    qc.act_release(s, lot, p.user, body.decision, body.comment, body.password)
    s.commit()
    return release_status(lid, p, s)


# ============================================================ OOS / OOT
class InvestigateIn(Reasoned):
    phase: str = Field(pattern="^(PHASE1|PHASE2)$")
    findings: str = Field(min_length=3)


class OOSDecide(SignedAction):
    decision: str = Field(pattern="^(CONFIRMED_FAIL|INVALIDATED)$")
    root_cause: str = Field(min_length=3)
    capa_ref: str | None = None


@router.get("/oos", tags=["OOS/OOT"])
def list_oos(status: str | None = None, limit: int = 100, offset: int = 0, p: Principal = Depends(require("oos.investigation.read")), s: Session = Depends(get_db)):
    stmt = select(OOSInvestigation)
    if status:
        stmt = stmt.where(OOSInvestigation.status == status)
    return _page(s, stmt, OOSInvestigation, limit, offset)


@router.get("/oos/{oid}", tags=["OOS/OOT"])
def get_oos(oid: int, p: Principal = Depends(require("oos.investigation.read")), s: Session = Depends(get_db)):
    return to_dict(masters.get_or_404(s, OOSInvestigation, oid, "OOS"))


@router.post("/oos/{oid}/investigate", tags=["OOS/OOT"])
def investigate(oid: int, body: InvestigateIn, p: Principal = Depends(require("oos.investigation.update")), s: Session = Depends(get_db)):
    use_reason(body.reason or "OOS investigation updated")
    o = masters.get_or_404(s, OOSInvestigation, oid, "OOS")
    qc.oos_investigate(s, o, body.phase, body.findings)
    s.commit()
    return to_dict(o)


@router.post("/oos/{oid}/decide", tags=["OOS/OOT"])
def decide_oos(oid: int, body: OOSDecide, p: Principal = Depends(require("oos.investigation.decide")), s: Session = Depends(get_db)):
    use_reason(body.reason)
    o = masters.get_or_404(s, OOSInvestigation, oid, "OOS")
    qc.oos_decide(s, o, p.user, body.password, body.decision, body.root_cause, body.capa_ref, body.reason or "")
    s.commit()
    return to_dict(o)


@router.get("/oot", tags=["OOS/OOT"])
def list_oot(limit: int = 100, offset: int = 0, p: Principal = Depends(require("oot.event.read")), s: Session = Depends(get_db)):
    return _page(s, select(OOTEvent), OOTEvent, limit, offset)


@router.post("/oot/{oid}/review", tags=["OOS/OOT"])
def review_oot(oid: int, body: Reasoned, p: Principal = Depends(require("oot.event.review")), s: Session = Depends(get_db)):
    use_reason(body.reason)
    e = masters.get_or_404(s, OOTEvent, oid, "OOT event")
    e.status, e.reviewed_by_id, e.review_comment = "REVIEWED", p.user.id, body.reason
    s.commit()
    return to_dict(e)


# ============================================================ trends & capability
@router.get("/qc/trends", tags=["Statistics"])
def trends(material_id: int, test_name: str, vendor_id: int | None = None, date_from: datetime | None = None, date_to: datetime | None = None,
           group: str = "batch", p: Principal = Depends(require("stats.trend.read")), s: Session = Depends(get_db)):
    pts = qc.history_values(s, material_id, test_name, vendor_id=vendor_id, date_from=date_from, date_to=date_to)
    values = [x["value"] for x in pts]
    min_n = int(config_service.get(s, "stats.min_n_capability", "25") or 25)
    lsl = next((x["lsl"] for x in reversed(pts) if x["lsl"] is not None), None)
    usl = next((x["usl"] for x in reversed(pts) if x["usl"] is not None), None)
    cl = stats.control_limits(values)
    enabled = [int(x) for x in (config_service.get(s, "stats.nelson_rules", "1,2,3,5,6") or "").split(",") if x.strip()]
    rules = stats.nelson_rules(values, cl["cl"], cl["sigma"], enabled) if cl and cl["sigma"] > 0 else []
    groups = None
    if group in ("month", "year", "vendor"):
        buckets: dict[str, list[float]] = {}
        for x in pts:
            key = f"{x['at'].year}-{x['at'].month:02d}" if group == "month" else str(x["at"].year) if group == "year" else str(x["vendor_id"])
            buckets.setdefault(key, []).append(x["value"])
        groups = [{"key": k, **stats.describe(v)} for k, v in sorted(buckets.items())]
    return {"points": [{**x, "at": x["at"].isoformat()} for x in pts], "descriptive": stats.describe(values), "control_limits": cl,
            "capability": stats.capability(values, lsl, usl, min_n), "lsl": lsl, "usl": usl, "nelson_violations": rules, "groups": groups}


# ============================================================ CoA
def _coa_out(s: Session, c: COA) -> dict:
    d = to_dict(c)
    return d


@router.get("/lots/{lid}/coa", tags=["CoA"])
def list_coa(lid: int, p: Principal = Depends(require("coa.document.read")), s: Session = Depends(get_db)):
    return [_coa_out(s, c) for c in s.execute(select(COA).where(COA.material_batch_id == lid).order_by(COA.version_no)).scalars()]


@router.post("/lots/{lid}/coa", status_code=201, tags=["CoA"])
def reissue_coa(lid: int, body: Reasoned, p: Principal = Depends(require("coa.document.generate")), s: Session = Depends(get_db)):
    use_reason(body.reason)
    lot = masters.get_or_404(s, MaterialBatch, lid, "Lot")
    if not (body.reason or "").strip():
        raise ValidationFailed("A reason is required to reissue a CoA", code="REASON_REQUIRED")
    prev = coa_svc.latest(s, lid)
    c = coa_svc.generate(s, lot, p.user, body.reason or "", prev.signature_id if prev else lot.release_signature_id)
    s.commit()
    return _coa_out(s, c)


@router.get("/coa/{cid}/{fmt}", tags=["CoA"])
def download_coa(cid: int, fmt: str, p: Principal = Depends(require("coa.document.read")), s: Session = Depends(get_db)):
    c = masters.get_or_404(s, COA, cid, "CoA")
    if fmt not in ("pdf", "xlsx"):
        raise NotFound("Unknown format")
    doc = s.get(Document, c.pdf_document_id if fmt == "pdf" else c.xlsx_document_id)
    data = documents.read(s, doc)
    s.commit()
    return Response(data, media_type=doc.mime_type, headers={"Content-Disposition": f'attachment; filename="{doc.original_name}"'})


# ============================================================ conditional release
class CRIn(Reasoned):
    material_batch_id: int
    quantity_authorised: Decimal = Field(gt=0)
    intended_batch_ref: str
    justification: str
    risk_assessment_ref: str
    identity_confirmed: bool
    expires_at: date


@router.get("/conditional-releases", tags=["Conditional release"])
def list_cr(limit: int = 100, offset: int = 0, p: Principal = Depends(require("conditional_release.request.read")), s: Session = Depends(get_db)):
    return _page(s, select(ConditionalRelease), ConditionalRelease, limit, offset)


@router.post("/conditional-releases", status_code=201, tags=["Conditional release"])
def request_cr(body: CRIn, p: Principal = Depends(require("conditional_release.request.create")), s: Session = Depends(get_db)):
    use_reason(body.justification)
    lot = masters.get_or_404(s, MaterialBatch, body.material_batch_id, "Lot")
    cr = qc.request_conditional_release(s, p.user, lot, body.quantity_authorised, body.intended_batch_ref, body.justification,
                                        body.risk_assessment_ref, body.identity_confirmed, body.expires_at)
    s.commit()
    return to_dict(cr)


@router.post("/conditional-releases/{cid}/decision", tags=["Conditional release"])
def decide_cr(cid: int, body: DecisionIn, p: Principal = Depends(require("conditional_release.request.approve")), s: Session = Depends(get_db)):
    use_reason(body.reason)
    cr = masters.get_or_404(s, ConditionalRelease, cid, "Conditional release")
    qc.decide_conditional_release(s, cr, p.user, body.password, body.approve, body.reason or "")
    s.commit()
    return to_dict(cr)
