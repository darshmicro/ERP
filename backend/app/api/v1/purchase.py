"""Phase 3 endpoints: vendor qualification, vendor-material approval, purchase request, purchase order."""
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.crud import to_dict, xlsx_response
from app.api.deps import Principal, get_db, require
from app.api.helpers import page_args, use_reason
from app.core.errors import NotFound, PermissionDenied, ValidationFailed
from app.models.master import Material, Vendor
from app.models.purchase import (PurchaseOrder, PurchaseOrderLine, PurchaseRequest, PurchaseRequestLine,
                                 VendorMaterial, VendorQualification)
from app.schemas.common import Reasoned
from app.services import masters
from app.services import purchasing as pur
from app.services import vendor_materials as vms
from app.services import vendor_qualification as vqs
from app.workflows import approval

router = APIRouter()


class SignedAction(Reasoned):
    password: str


def _page(s: Session, stmt, Model, limit: int, offset: int, conv=to_dict):
    limit, offset = page_args(limit, offset)
    total = s.execute(select(func.count()).select_from(stmt.subquery())).scalar()
    rows = s.execute(stmt.order_by(Model.id.desc()).limit(limit).offset(offset)).scalars().all()
    return {"items": [conv(r) for r in rows], "total": total, "limit": limit, "offset": offset}


# ============================================================ vendor qualification
class VQIn(Reasoned):
    vendor_id: int
    risk_class: str | None = Field(default=None, pattern="^(CRITICAL|HIGH|MEDIUM|LOW)$")
    qualified_on: date | None = None
    requalification_due_date: date | None = None
    basis: str | None = None
    audit_report_ref: str | None = None
    change_reason: str | None = None


class VQUpdate(Reasoned):
    model_config = {"extra": "forbid"}
    risk_class: str | None = Field(default=None, pattern="^(CRITICAL|HIGH|MEDIUM|LOW)$")
    qualified_on: date | None = None
    requalification_due_date: date | None = None
    basis: str | None = None
    audit_report_ref: str | None = None


class VQApprove(SignedAction):
    conditional: bool = False


def _vq_out(s: Session, q: VendorQualification, today: date | None = None) -> dict:
    d = to_dict(q)
    v = s.get(Vendor, q.vendor_id)
    d["vendor_code"], d["vendor_name"] = v.vendor_code, v.name
    if q.requalification_due_date:
        d["days_to_due"] = (q.requalification_due_date - (today or date.today())).days
    d["effective_status"] = ("EXPIRED" if q.status in ("APPROVED", "CONDITIONAL") and q.requalification_due_date
                             and q.requalification_due_date < (today or date.today()) else q.status)
    return d


def _vq_query(request: Request):
    stmt = select(VendorQualification)
    for f in ("status", "vendor_id", "risk_class"):
        if request.query_params.get(f):
            stmt = stmt.where(getattr(VendorQualification, f) == request.query_params[f])
    return stmt


@router.get("/vendor-qualifications", tags=["Vendor qualification"])
def list_vq(request: Request, limit: int = Query(50), offset: int = Query(0), p: Principal = Depends(require("vq.qualification.read")),
            s: Session = Depends(get_db)):
    return _page(s, _vq_query(request), VendorQualification, limit, offset, lambda q: _vq_out(s, q))


@router.get("/vendor-qualifications/expiry-report", tags=["Vendor qualification"])
def vq_expiry_report(within_days: int = 90, p: Principal = Depends(require("vq.qualification.read")), s: Session = Depends(get_db)):
    """Current standing of every approved vendor, soonest due first (spec 50: Vendor expiry)."""
    out = []
    for v in s.execute(select(Vendor).where(Vendor.approval_status == "APPROVED")).scalars():
        st = vqs.standing(s, v.id)
        out.append({"vendor_id": v.id, "vendor_code": v.vendor_code, "vendor": v.name, "risk_class": v.risk_class,
                    "status": st.effective_status, "purchasable": st.purchasable,
                    "due": st.qualification.requalification_due_date.isoformat() if st.qualification and st.qualification.requalification_due_date else None,
                    "days_to_due": st.days_to_due})
    out.sort(key=lambda r: (r["days_to_due"] is None, r["days_to_due"] if r["days_to_due"] is not None else 0))
    return [r for r in out if r["days_to_due"] is None or r["days_to_due"] <= within_days or not r["purchasable"]]


@router.get("/vendor-qualifications/expiry-report/export", tags=["Vendor qualification"])
def vq_expiry_export(within_days: int = 90, p: Principal = Depends(require("vq.qualification.read", "md.master.export")), s: Session = Depends(get_db)):
    rows = vq_expiry_report(within_days, p, s)
    cols = [("vendor_code", "Vendor code"), ("vendor", "Vendor"), ("risk_class", "Risk"), ("status", "Qualification status"),
            ("due", "Requalification due"), ("days_to_due", "Days to due"), ("purchasable", "Purchasable")]
    return xlsx_response(s, p, "Vendor qualification expiry", {"within_days": within_days}, cols, rows, "vendor_qualification")


@router.get("/vendors/{vendor_id}/purchase-status", tags=["Vendor qualification"])
def vendor_purchase_status(vendor_id: int, p: Principal = Depends(require("vq.qualification.read")), s: Session = Depends(get_db)):
    """What a buyer sees: can POs be raised for this vendor today, and why not."""
    v = masters.get_or_404(s, Vendor, vendor_id, "Vendor")
    st = vqs.standing(s, v.id)
    risk = st.qualification.risk_class if st.qualification else v.risk_class
    return {"vendor_approval": v.approval_status, "qualification_status": st.effective_status, "purchasable": st.purchasable and v.approval_status == "APPROVED",
            "message": st.message if not st.purchasable else None, "rule_id": st.block_rule, "days_to_due": st.days_to_due,
            "due": st.qualification.requalification_due_date.isoformat() if st.qualification and st.qualification.requalification_due_date else None,
            "document_gaps": vqs.document_gaps(s, v.id, risk)}


@router.post("/vendor-qualifications", status_code=201, tags=["Vendor qualification"])
def create_vq(body: VQIn, p: Principal = Depends(require("vq.qualification.create")), s: Session = Depends(get_db)):
    use_reason(body.reason or body.change_reason or "Vendor qualification created")
    v = masters.get_or_404(s, Vendor, body.vendor_id, "Vendor")
    q = vqs.create(s, v, body.model_dump(exclude={"reason", "vendor_id"}, exclude_none=True))
    s.commit()
    return _vq_out(s, q)


@router.get("/vendor-qualifications/{qid}", tags=["Vendor qualification"])
def get_vq(qid: int, p: Principal = Depends(require("vq.qualification.read")), s: Session = Depends(get_db)):
    q = masters.get_or_404(s, VendorQualification, qid, "Qualification")
    hist = s.execute(select(VendorQualification).where(VendorQualification.vendor_id == q.vendor_id)
                     .order_by(VendorQualification.version_no)).scalars().all()
    v = s.get(Vendor, q.vendor_id)
    return {**_vq_out(s, q), "versions": [{"id": h.id, "version_no": h.version_no, "status": h.status,
                                           "due": h.requalification_due_date.isoformat() if h.requalification_due_date else None} for h in hist],
            "document_gaps": vqs.document_gaps(s, q.vendor_id, q.risk_class),
            "quality_agreement_status": v.quality_agreement_status, "vendor_audit_status": v.vendor_audit_status}


@router.patch("/vendor-qualifications/{qid}", tags=["Vendor qualification"])
def update_vq(qid: int, body: VQUpdate, p: Principal = Depends(require("vq.qualification.update")), s: Session = Depends(get_db)):
    use_reason(body.reason or "Qualification draft updated")
    q = masters.get_or_404(s, VendorQualification, qid, "Qualification")
    for k, v in body.model_dump(exclude={"reason"}, exclude_unset=True).items():
        setattr(q, k, v)  # locked once submitted (ORM hook)
    s.commit()
    return _vq_out(s, q)


@router.post("/vendor-qualifications/{qid}/submit", tags=["Vendor qualification"])
def submit_vq(qid: int, p: Principal = Depends(require("vq.qualification.update")), s: Session = Depends(get_db)):
    q = masters.get_or_404(s, VendorQualification, qid, "Qualification")
    vqs.submit(s, q)
    s.commit()
    return _vq_out(s, q)


@router.post("/vendor-qualifications/{qid}/return", tags=["Vendor qualification"])
def return_vq(qid: int, body: Reasoned, p: Principal = Depends(require("vq.qualification.update")), s: Session = Depends(get_db)):
    use_reason(body.reason)
    q = masters.get_or_404(s, VendorQualification, qid, "Qualification")
    vqs.return_to_draft(s, q, body.reason or "")
    s.commit()
    return _vq_out(s, q)


@router.post("/vendor-qualifications/{qid}/approve", tags=["Vendor qualification"])
def approve_vq(qid: int, body: VQApprove, p: Principal = Depends(require("vq.qualification.approve")), s: Session = Depends(get_db)):
    use_reason(body.reason)
    q = masters.get_or_404(s, VendorQualification, qid, "Qualification")
    vqs.approve(s, q, p.user, body.password, body.reason or "", body.conditional)
    s.commit()
    return _vq_out(s, q)


@router.post("/vendor-qualifications/{qid}/suspend", tags=["Vendor qualification"])
def suspend_vq(qid: int, body: SignedAction, p: Principal = Depends(require("vq.qualification.suspend")), s: Session = Depends(get_db)):
    use_reason(body.reason)
    q = masters.get_or_404(s, VendorQualification, qid, "Qualification")
    vqs.suspend(s, q, p.user, body.password, body.reason or "")
    s.commit()
    return _vq_out(s, q)


@router.post("/vendor-qualifications/{qid}/disqualify", tags=["Vendor qualification"])
def disqualify_vq(qid: int, body: SignedAction, p: Principal = Depends(require("vq.qualification.disqualify")), s: Session = Depends(get_db)):
    use_reason(body.reason)
    q = masters.get_or_404(s, VendorQualification, qid, "Qualification")
    vqs.disqualify(s, q, p.user, body.password, body.reason or "")
    s.commit()
    return _vq_out(s, q)


@router.post("/jobs/vendor-qualification-expiry", tags=["Jobs"])
def run_expiry_job(p: Principal = Depends(require("config.job.run")), s: Session = Depends(get_db)):
    """Same job the scheduler runs daily (idempotent). Persists EXPIRED and sends alerts."""
    use_reason("Scheduled job: vendor qualification expiry (manual run)")
    expired = vqs.expire_due(s)
    alerts = vqs.alert_upcoming(s)
    s.commit()
    return {"expired": expired, "alerts_created": alerts}


# ============================================================ vendor-material mapping
class VMIn(Reasoned):
    vendor_id: int
    material_id: int
    is_primary: bool = False
    manufacturer_site: str | None = None
    change_control_ref: str | None = None
    approved_to: date | None = None


class VMUpdate(Reasoned):
    model_config = {"extra": "forbid"}
    is_primary: bool | None = None
    manufacturer_site: str | None = None
    change_control_ref: str | None = None
    approved_to: date | None = None


def _vm_out(s: Session, vm: VendorMaterial) -> dict:
    d = to_dict(vm)
    v, m = s.get(Vendor, vm.vendor_id), s.get(Material, vm.material_id)
    d.update(vendor_code=v.vendor_code, vendor_name=v.name, material_code=m.material_code, material_name=m.name)
    return d


def _vm_query(request: Request):
    stmt = select(VendorMaterial)
    for f in ("status", "vendor_id", "material_id"):
        if request.query_params.get(f):
            stmt = stmt.where(getattr(VendorMaterial, f) == request.query_params[f])
    return stmt


@router.get("/vendor-materials", tags=["Vendor-material mapping"])
def list_vm(request: Request, limit: int = Query(100), offset: int = Query(0), p: Principal = Depends(require("vm.mapping.read")),
            s: Session = Depends(get_db)):
    return _page(s, _vm_query(request), VendorMaterial, limit, offset, lambda x: _vm_out(s, x))


@router.get("/vendor-materials/export", tags=["Vendor-material mapping"])
def export_vm(request: Request, p: Principal = Depends(require("vm.mapping.read", "md.master.export")), s: Session = Depends(get_db)):
    rows = [_vm_out(s, x) for x in s.execute(_vm_query(request).order_by(VendorMaterial.id)).scalars()]
    cols = [("material_code", "Material"), ("material_name", "Name"), ("vendor_code", "Vendor"), ("vendor_name", "Vendor name"),
            ("version_no", "Ver"), ("status", "Status"), ("is_primary", "Primary"), ("approved_to", "Approved until")]
    return xlsx_response(s, p, "Vendor-material mapping", {"status": request.query_params.get("status")}, cols, rows, "vendor_material")


@router.get("/vendor-materials/check", tags=["Vendor-material mapping"])
def check_vm(vendor_id: int, material_id: int, p: Principal = Depends(require("vm.mapping.read")), s: Session = Depends(get_db)):
    vm = vms.approved_mapping(s, vendor_id, material_id)
    return {"approved": vm is not None, "mapping_id": vm.id if vm else None}


@router.post("/vendor-materials", status_code=201, tags=["Vendor-material mapping"])
def create_vm(body: VMIn, p: Principal = Depends(require("vm.mapping.create")), s: Session = Depends(get_db)):
    use_reason(body.reason or "Vendor-material mapping proposed")
    vm = vms.create(s, body.model_dump(exclude={"reason"}, exclude_none=True))
    s.commit()
    return _vm_out(s, vm)


@router.get("/vendor-materials/{vid}", tags=["Vendor-material mapping"])
def get_vm(vid: int, p: Principal = Depends(require("vm.mapping.read")), s: Session = Depends(get_db)):
    return _vm_out(s, masters.get_or_404(s, VendorMaterial, vid, "Mapping"))


@router.patch("/vendor-materials/{vid}", tags=["Vendor-material mapping"])
def update_vm(vid: int, body: VMUpdate, p: Principal = Depends(require("vm.mapping.update")), s: Session = Depends(get_db)):
    use_reason(body.reason or "Mapping draft updated")
    vm = masters.get_or_404(s, VendorMaterial, vid, "Mapping")
    for k, v in body.model_dump(exclude={"reason"}, exclude_unset=True).items():
        setattr(vm, k, v)
    s.commit()
    return _vm_out(s, vm)


@router.post("/vendor-materials/{vid}/submit", tags=["Vendor-material mapping"])
def submit_vm(vid: int, p: Principal = Depends(require("vm.mapping.update")), s: Session = Depends(get_db)):
    vm = masters.get_or_404(s, VendorMaterial, vid, "Mapping")
    vms.submit(s, vm)
    s.commit()
    return _vm_out(s, vm)


@router.post("/vendor-materials/{vid}/approve", tags=["Vendor-material mapping"])
def approve_vm(vid: int, body: SignedAction, p: Principal = Depends(require("vm.mapping.approve")), s: Session = Depends(get_db)):
    use_reason(body.reason)
    vm = masters.get_or_404(s, VendorMaterial, vid, "Mapping")
    vms.approve(s, vm, p.user, body.password, body.reason or "")
    s.commit()
    return _vm_out(s, vm)


@router.post("/vendor-materials/{vid}/withdraw", tags=["Vendor-material mapping"])
def withdraw_vm(vid: int, body: SignedAction, p: Principal = Depends(require("vm.mapping.withdraw")), s: Session = Depends(get_db)):
    use_reason(body.reason)
    vm = masters.get_or_404(s, VendorMaterial, vid, "Mapping")
    vms.withdraw(s, vm, p.user, body.password, body.reason or "")
    s.commit()
    return _vm_out(s, vm)


@router.post("/vendor-materials/{vid}/new-version", status_code=201, tags=["Vendor-material mapping"])
def new_version_vm(vid: int, body: Reasoned, p: Principal = Depends(require("vm.mapping.create")), s: Session = Depends(get_db)):
    use_reason(body.reason)
    vm = masters.get_or_404(s, VendorMaterial, vid, "Mapping")
    n = vms.new_version(s, vm, body.reason or "")
    s.commit()
    return _vm_out(s, n)


# ============================================================ purchase request
class PRLineIn(BaseModel):
    material_id: int
    quantity: Decimal = Field(gt=0)
    unit_id: int | None = None
    required_date: date | None = None
    preferred_vendor_id: int | None = None
    remarks: str | None = None


class PRIn(Reasoned):
    purpose: str | None = None
    priority: str = Field(default="NORMAL", pattern="^(LOW|NORMAL|HIGH|URGENT)$")
    remarks: str | None = None
    lines: list[PRLineIn] = Field(min_length=1)


class PRUpdate(Reasoned):
    model_config = {"extra": "forbid"}
    purpose: str | None = None
    priority: str | None = Field(default=None, pattern="^(LOW|NORMAL|HIGH|URGENT)$")
    remarks: str | None = None


class ActIn(BaseModel):
    decision: str = Field(pattern="^(APPROVE|REJECT)$")
    comment: str | None = None
    password: str | None = None


def _pr_out(s: Session, pr: PurchaseRequest, detail: bool = False) -> dict:
    d = to_dict(pr)
    d["requested_by"] = s.get(__import__("app.models.iam", fromlist=["User"]).User, pr.requested_by_id).full_name
    if detail:
        d["lines"] = [to_dict(l) for l in s.execute(select(PurchaseRequestLine).where(PurchaseRequestLine.pr_id == pr.id)
                                                    .order_by(PurchaseRequestLine.line_no)).scalars()]
        d["workflow"] = pur.workflow_view(s, pr.workflow_instance_id)
    return d


def _pr_query(request: Request, q: str | None):
    stmt = select(PurchaseRequest)
    if q:
        stmt = stmt.where(func.lower(PurchaseRequest.pr_no).like(f"%{q.lower()}%"))
    for f in ("status", "department_id", "priority"):
        if request.query_params.get(f):
            stmt = stmt.where(getattr(PurchaseRequest, f) == request.query_params[f])
    if request.query_params.get("date_from"):
        stmt = stmt.where(PurchaseRequest.request_date >= request.query_params["date_from"])
    if request.query_params.get("date_to"):
        stmt = stmt.where(PurchaseRequest.request_date <= request.query_params["date_to"])
    return stmt


@router.get("/purchase-requests", tags=["Purchase requests"])
def list_pr(request: Request, q: str | None = None, limit: int = Query(50), offset: int = Query(0),
            p: Principal = Depends(require("pr.request.read")), s: Session = Depends(get_db)):
    return _page(s, _pr_query(request, q), PurchaseRequest, limit, offset, lambda x: _pr_out(s, x))


@router.get("/purchase-requests/export", tags=["Purchase requests"])
def export_pr(request: Request, q: str | None = None, p: Principal = Depends(require("pr.request.read", "pr.request.export")),
              s: Session = Depends(get_db)):
    rows = []
    for pr in s.execute(_pr_query(request, q).order_by(PurchaseRequest.id)).scalars():
        for l in s.execute(select(PurchaseRequestLine).where(PurchaseRequestLine.pr_id == pr.id)).scalars():
            m = s.get(Material, l.material_id)
            rows.append({**_pr_out(s, pr), "material": f"{m.material_code} {m.name}", "quantity": l.quantity,
                         "required_date": l.required_date})
    cols = [("pr_no", "PR no."), ("request_date", "Date"), ("requested_by", "Requested by"), ("priority", "Priority"),
            ("status", "Status"), ("material", "Material"), ("quantity", "Quantity"), ("required_date", "Required by")]
    return xlsx_response(s, p, "Purchase requests", {"status": request.query_params.get("status")}, cols, rows, "purchase_request")


@router.post("/purchase-requests", status_code=201, tags=["Purchase requests"])
def create_pr(body: PRIn, p: Principal = Depends(require("pr.request.create")), s: Session = Depends(get_db)):
    use_reason(body.reason or "Purchase request created")
    pr = pur.create_pr(s, p.user, body.model_dump(exclude={"reason", "lines"}), [l.model_dump(exclude_none=True) for l in body.lines])
    s.commit()
    return _pr_out(s, pr, True)


@router.get("/purchase-requests/{rid}", tags=["Purchase requests"])
def get_pr(rid: int, p: Principal = Depends(require("pr.request.read")), s: Session = Depends(get_db)):
    return _pr_out(s, masters.get_or_404(s, PurchaseRequest, rid, "Purchase request"), True)


@router.patch("/purchase-requests/{rid}", tags=["Purchase requests"])
def update_pr(rid: int, body: PRUpdate, p: Principal = Depends(require("pr.request.update")), s: Session = Depends(get_db)):
    use_reason(body.reason or "Purchase request edited")
    pr = masters.get_or_404(s, PurchaseRequest, rid, "Purchase request")
    if pr.requested_by_id != p.user.id:
        raise PermissionDenied("Only the requester can edit a draft")
    for k, v in body.model_dump(exclude={"reason"}, exclude_unset=True).items():
        setattr(pr, k, v)
    s.commit()
    return _pr_out(s, pr, True)


class PRLines(Reasoned):
    lines: list[PRLineIn] = Field(min_length=1)


@router.put("/purchase-requests/{rid}/lines", tags=["Purchase requests"])
def put_pr_lines(rid: int, body: PRLines, p: Principal = Depends(require("pr.request.update")), s: Session = Depends(get_db)):
    use_reason(body.reason or "Purchase request lines edited")
    pr = masters.get_or_404(s, PurchaseRequest, rid, "Purchase request")
    if pr.requested_by_id != p.user.id:
        raise PermissionDenied("Only the requester can edit a draft")
    pur.replace_pr_lines(s, pr, [l.model_dump(exclude_none=True) for l in body.lines])
    s.commit()
    return _pr_out(s, pr, True)


@router.post("/purchase-requests/{rid}/submit", tags=["Purchase requests"])
def submit_pr(rid: int, p: Principal = Depends(require("pr.request.submit")), s: Session = Depends(get_db)):
    pr = masters.get_or_404(s, PurchaseRequest, rid, "Purchase request")
    pur.submit_pr(s, pr, p.user)
    s.commit()
    return _pr_out(s, pr, True)


@router.post("/purchase-requests/{rid}/decision", tags=["Purchase requests"])
def decide_pr(rid: int, body: ActIn, p: Principal = Depends(require("pr.request.approve")), s: Session = Depends(get_db)):
    use_reason(body.comment or f"Purchase request {body.decision.lower()}")
    pr = masters.get_or_404(s, PurchaseRequest, rid, "Purchase request")
    pur.act_pr(s, pr, p.user, body.decision, body.comment, body.password)
    s.commit()
    return _pr_out(s, pr, True)


@router.post("/purchase-requests/{rid}/cancel", tags=["Purchase requests"])
def cancel_pr(rid: int, body: Reasoned, p: Principal = Depends(require("pr.request.cancel")), s: Session = Depends(get_db)):
    use_reason(body.reason)
    pr = masters.get_or_404(s, PurchaseRequest, rid, "Purchase request")
    pur.cancel_pr(s, pr, p.user, body.reason or "")
    s.commit()
    return _pr_out(s, pr, True)


# ============================================================ purchase order
class POLineIn(BaseModel):
    material_id: int
    quantity: Decimal = Field(gt=0)
    rate: Decimal = Field(ge=0)
    tax_pct: Decimal = Field(default=Decimal(0), ge=0, le=100)
    unit_id: int | None = None
    delivery_date: date | None = None
    remarks: str | None = None
    pr_line_id: int | None = None


class POHeader(BaseModel):
    vendor_id: int
    currency: str = Field(default="INR", min_length=3, max_length=3)
    payment_terms: str | None = None
    delivery_date: date | None = None
    purchase_conditions: str | None = None
    quality_requirements: str | None = None


class POIn(Reasoned, POHeader):
    lines: list[POLineIn] = Field(min_length=1)


class POUpdate(Reasoned):
    model_config = {"extra": "forbid"}
    payment_terms: str | None = None
    delivery_date: date | None = None
    purchase_conditions: str | None = None
    quality_requirements: str | None = None


class POLines(Reasoned):
    lines: list[POLineIn] = Field(min_length=1)


class POFromPR(Reasoned, POHeader):
    pr_id: int
    lines: list[dict]   # [{pr_line_id, rate, tax_pct?}]


class POCancel(Reasoned):
    password: str | None = None


def _po_out(s: Session, po: PurchaseOrder, detail: bool = False) -> dict:
    import json as _json
    d = to_dict(po)
    v = s.get(Vendor, po.vendor_id)
    d.update(vendor_code=v.vendor_code, vendor_name=v.name, **pur.po_totals(s, po.id))
    if po.vendor_qualification_id:
        q = s.get(VendorQualification, po.vendor_qualification_id)
        d["vendor_qualification"] = {"id": q.id, "version_no": q.version_no, "status": q.status,
                                     "due": q.requalification_due_date.isoformat() if q.requalification_due_date else None}
    snap = _json.loads(po.validation_snapshot) if po.validation_snapshot else None
    d["validation"] = snap
    if detail:
        lines = []
        for l in s.execute(select(PurchaseOrderLine).where(PurchaseOrderLine.po_id == po.id).order_by(PurchaseOrderLine.line_no)).scalars():
            m = s.get(Material, l.material_id)
            ld = to_dict(l)
            ld.update(material_code=m.material_code, material_name=m.name,
                      line_total=float(round(l.quantity * l.rate * (1 + l.tax_pct / 100), 2)))
            lines.append(ld)
        d["lines"] = lines
        d["workflow"] = pur.workflow_view(s, po.workflow_instance_id)
    return d


def _po_query(request: Request, q: str | None):
    stmt = select(PurchaseOrder)
    if q:
        stmt = stmt.where(func.lower(PurchaseOrder.po_no).like(f"%{q.lower()}%"))
    for f in ("status", "vendor_id"):
        if request.query_params.get(f):
            stmt = stmt.where(getattr(PurchaseOrder, f) == request.query_params[f])
    if request.query_params.get("open") in ("1", "true"):
        stmt = stmt.where(PurchaseOrder.status.in_(("PENDING_APPROVAL", "APPROVED", "PARTIALLY_RECEIVED")))
    if request.query_params.get("date_from"):
        stmt = stmt.where(PurchaseOrder.po_date >= request.query_params["date_from"])
    if request.query_params.get("date_to"):
        stmt = stmt.where(PurchaseOrder.po_date <= request.query_params["date_to"])
    return stmt


@router.get("/purchase-orders", tags=["Purchase orders"])
def list_po(request: Request, q: str | None = None, limit: int = Query(50), offset: int = Query(0),
            p: Principal = Depends(require("po.order.read")), s: Session = Depends(get_db)):
    return _page(s, _po_query(request, q), PurchaseOrder, limit, offset, lambda x: _po_out(s, x))


@router.get("/purchase-orders/export", tags=["Purchase orders"])
def export_po(request: Request, q: str | None = None, p: Principal = Depends(require("po.order.read", "po.order.export")),
              s: Session = Depends(get_db)):
    rows = []
    for po in s.execute(_po_query(request, q).order_by(PurchaseOrder.id)).scalars():
        for l in s.execute(select(PurchaseOrderLine).where(PurchaseOrderLine.po_id == po.id)).scalars():
            m = s.get(Material, l.material_id)
            rows.append({**_po_out(s, po), "material": f"{m.material_code} {m.name}", "quantity": l.quantity, "rate": l.rate,
                         "received": l.received_quantity})
    cols = [("po_no", "PO no."), ("po_date", "Date"), ("vendor_code", "Vendor"), ("vendor_name", "Vendor name"), ("status", "Status"),
            ("material", "Material"), ("quantity", "Quantity"), ("rate", "Rate"), ("received", "Received"), ("total", "PO total")]
    return xlsx_response(s, p, "Purchase orders", {"status": request.query_params.get("status")}, cols, rows, "purchase_order")


@router.post("/purchase-orders/validate", tags=["Purchase orders"])
def validate_po(body: POIn, p: Principal = Depends(require("po.order.create")), s: Session = Depends(get_db)):
    """Dry run of the gate (nothing is created) so the buyer sees every blocker before saving."""
    from dataclasses import asdict
    vio, _ = pur.evaluate_po(s, vendor_id=body.vendor_id, lines=[l.model_dump() for l in body.lines], stage="CREATE",
                             user_id=p.user.id, header={"po_date": date.today(), "delivery_date": body.delivery_date})
    return {"allowed": not pur.blocks(vio), "results": [asdict(v) for v in vio]}


@router.post("/purchase-orders", status_code=201, tags=["Purchase orders"])
def create_po(body: POIn, p: Principal = Depends(require("po.order.create")), s: Session = Depends(get_db)):
    use_reason(body.reason or "Purchase order created")
    po = pur.create_po(s, p.user, body.model_dump(exclude={"reason", "lines"}), [l.model_dump() for l in body.lines])
    s.commit()
    return _po_out(s, po, True)


@router.post("/purchase-orders/from-pr", status_code=201, tags=["Purchase orders"])
def po_from_pr(body: POFromPR, p: Principal = Depends(require("po.order.create")), s: Session = Depends(get_db)):
    use_reason(body.reason or "Purchase order created from purchase request")
    pr = masters.get_or_404(s, PurchaseRequest, body.pr_id, "Purchase request")
    po = pur.create_po_from_pr(s, p.user, pr, body.model_dump(exclude={"reason", "lines", "pr_id"}), body.lines)
    s.commit()
    return _po_out(s, po, True)


@router.get("/purchase-orders/{pid}", tags=["Purchase orders"])
def get_po(pid: int, p: Principal = Depends(require("po.order.read")), s: Session = Depends(get_db)):
    return _po_out(s, masters.get_or_404(s, PurchaseOrder, pid, "Purchase order"), True)


@router.patch("/purchase-orders/{pid}", tags=["Purchase orders"])
def update_po(pid: int, body: POUpdate, p: Principal = Depends(require("po.order.update")), s: Session = Depends(get_db)):
    use_reason(body.reason or "Purchase order edited")
    po = masters.get_or_404(s, PurchaseOrder, pid, "Purchase order")
    for k, v in body.model_dump(exclude={"reason"}, exclude_unset=True).items():
        setattr(po, k, v)   # locked unless DRAFT (ORM hook, BR-HIS-001)
    s.commit()
    return _po_out(s, po, True)


@router.put("/purchase-orders/{pid}/lines", tags=["Purchase orders"])
def put_po_lines(pid: int, body: POLines, p: Principal = Depends(require("po.order.update")), s: Session = Depends(get_db)):
    use_reason(body.reason or "Purchase order lines edited")
    po = masters.get_or_404(s, PurchaseOrder, pid, "Purchase order")
    pur.replace_po_lines(s, po, p.user, [l.model_dump() for l in body.lines])
    s.commit()
    return _po_out(s, po, True)


@router.post("/purchase-orders/{pid}/submit", tags=["Purchase orders"])
def submit_po(pid: int, p: Principal = Depends(require("po.order.submit")), s: Session = Depends(get_db)):
    po = masters.get_or_404(s, PurchaseOrder, pid, "Purchase order")
    pur.submit_po(s, po, p.user)
    s.commit()
    return _po_out(s, po, True)


@router.post("/purchase-orders/{pid}/decision", tags=["Purchase orders"])
def decide_po(pid: int, body: ActIn, p: Principal = Depends(require("po.order.approve")), s: Session = Depends(get_db)):
    use_reason(body.comment or f"Purchase order {body.decision.lower()}")
    po = masters.get_or_404(s, PurchaseOrder, pid, "Purchase order")
    pur.act_po(s, po, p.user, body.decision, body.comment, body.password)
    s.commit()
    return _po_out(s, po, True)


@router.post("/purchase-orders/{pid}/cancel", tags=["Purchase orders"])
def cancel_po(pid: int, body: POCancel, p: Principal = Depends(require("po.order.cancel")), s: Session = Depends(get_db)):
    use_reason(body.reason)
    po = masters.get_or_404(s, PurchaseOrder, pid, "Purchase order")
    pur.cancel_po(s, po, p.user, body.reason or "", body.password)
    s.commit()
    return _po_out(s, po, True)


@router.get("/approvals/pending", tags=["Workflow"])
def pending_approvals(p: Principal = Depends(require("dashboard.view.read")), s: Session = Depends(get_db)):
    out = []
    for inst in approval.pending_for_user(s, p.user.id):
        step = approval.current_step(s, inst)
        out.append({"instance_id": inst.id, "process": inst.process_code, "entity": inst.entity, "record_id": inst.record_id,
                    "step": step.name, "since": inst.step_started_at.isoformat()})
    return out
