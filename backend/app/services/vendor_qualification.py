"""Vendor qualification (spec 10) and the live 'is this vendor purchasable today?' evaluation.

Rule 1 (BR-PO-001) must not depend on a nightly job having run: `standing()` compares today's date with
the requalification due date on every evaluation. The job only persists the EXPIRED status and notifies.
"""
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import BusinessRuleError, Conflict, ValidationFailed
from app.core.time import utcnow
from app.models.master import Vendor, VendorDocument
from app.models.purchase import VendorQualification
from app.services import config_service, masters, notifications, numbering
from app.workflows.state_machine import StateMachine, Transition, transition

T = Transition
_SUSP = T("SUSPENDED", "vq.qualification.suspend", "APPROVED_BY", True)
_DISQ = T("DISQUALIFIED", "vq.qualification.disqualify", "APPROVED_BY", True)
VQ_MACHINE = StateMachine("vendor_qualification", "DRAFT", {
    "DRAFT": {"UNDER_REVIEW": T("UNDER_REVIEW")},
    "UNDER_REVIEW": {"DRAFT": T("DRAFT", requires_reason=True),
                     "APPROVED": T("APPROVED", "vq.qualification.approve", "QA_APPROVED", True),
                     "CONDITIONAL": T("CONDITIONAL", "vq.qualification.approve", "QA_APPROVED", True)},
    "APPROVED": {"SUSPENDED": _SUSP, "DISQUALIFIED": _DISQ, "EXPIRED": T("EXPIRED"), "SUPERSEDED": T("SUPERSEDED")},
    "CONDITIONAL": {"SUSPENDED": _SUSP, "DISQUALIFIED": _DISQ, "EXPIRED": T("EXPIRED"), "SUPERSEDED": T("SUPERSEDED")},
    "SUSPENDED": {"DISQUALIFIED": _DISQ, "EXPIRED": T("EXPIRED"), "SUPERSEDED": T("SUPERSEDED")},
    "EXPIRED": {"SUPERSEDED": T("SUPERSEDED")},
    "DISQUALIFIED": {"SUPERSEDED": T("SUPERSEDED")},
})
STANDING = ("APPROVED", "CONDITIONAL", "SUSPENDED", "EXPIRED", "DISQUALIFIED")


@dataclass
class Standing:
    qualification: VendorQualification | None
    effective_status: str            # NONE / APPROVED / CONDITIONAL / SUSPENDED / EXPIRED / DISQUALIFIED
    purchasable: bool
    block_rule: str | None
    message: str | None
    days_to_due: int | None


def current(session: Session, vendor_id: int) -> VendorQualification | None:
    return session.execute(select(VendorQualification).where(
        VendorQualification.vendor_id == vendor_id, VendorQualification.status.in_(STANDING))
        .order_by(VendorQualification.version_no.desc())).scalars().first()


def standing(session: Session, vendor_id: int, today: date | None = None) -> Standing:
    today = today or date.today()
    q = current(session, vendor_id)
    if q is None:
        return Standing(None, "NONE", False, "BR-PO-002", "PURCHASE BLOCKED — VENDOR NOT QUALIFIED.", None)
    days = (q.requalification_due_date - today).days if q.requalification_due_date else None
    eff = q.status
    if q.status in ("APPROVED", "CONDITIONAL") and (q.requalification_due_date is None or q.requalification_due_date < today):
        eff = "EXPIRED"
    if eff in ("APPROVED", "CONDITIONAL"):
        return Standing(q, eff, True, None, None, days)
    if eff == "EXPIRED":
        return Standing(q, eff, False, "BR-PO-001", "PURCHASE BLOCKED — VENDOR QUALIFICATION EXPIRED.", days)
    return Standing(q, eff, False, "BR-PO-002", f"PURCHASE BLOCKED — VENDOR QUALIFICATION {eff}.", days)


# ------------------------------------------------------------------ documents
def required_doc_types(session: Session, risk_class: str) -> list[str]:
    raw = config_service.get(session, f"po.required_docs.{risk_class}", "") or ""
    return [x.strip() for x in raw.split(",") if x.strip()]


def document_gaps(session: Session, vendor_id: int, risk_class: str, today: date | None = None) -> list[str]:
    today = today or date.today()
    gaps = []
    for dt in required_doc_types(session, risk_class):
        docs = session.execute(select(VendorDocument).where(
            VendorDocument.vendor_id == vendor_id, VendorDocument.doc_type == dt,
            VendorDocument.review_status == "APPROVED", VendorDocument.is_current == True)).scalars().all()  # noqa: E712
        ok = [d for d in docs if not d.expiry_date or d.expiry_date >= today]
        if not ok:
            gaps.append(f"{dt}: " + ("expired" if docs else "no approved document"))
    return gaps


# ------------------------------------------------------------------ lifecycle
def _open_version(session: Session, vendor_id: int):
    return session.execute(select(VendorQualification.id).where(
        VendorQualification.vendor_id == vendor_id, VendorQualification.status.in_(("DRAFT", "UNDER_REVIEW")))).first()


def create(session: Session, vendor: Vendor, data: dict) -> VendorQualification:
    if vendor.approval_status != "APPROVED":
        raise BusinessRuleError("The vendor master record must be APPROVED before qualification", rule_id="VQ-001")
    if _open_version(session, vendor.id):
        raise Conflict("A qualification for this vendor is already in draft/under review")
    prev = session.execute(select(VendorQualification).where(VendorQualification.vendor_id == vendor.id)
                           .order_by(VendorQualification.version_no.desc())).scalars().first()
    no = prev.qualification_no if prev else numbering.next_number(session, numbering.default_plant_id(session), "VQUAL")
    q = VendorQualification(vendor_id=vendor.id, qualification_no=no, version_no=(prev.version_no + 1) if prev else 1,
                            status="DRAFT", risk_class=data.pop("risk_class", None) or vendor.risk_class,
                            supersedes_id=prev.id if prev else None, change_reason=data.pop("change_reason", None), **data)
    if prev is not None and not q.change_reason:
        raise ValidationFailed("A reason is required for a requalification (new version)", code="REASON_REQUIRED")
    session.add(q)
    session.flush()
    masters.record_author(session, q, "vendor_qualification.author")
    return q


def validate_content(session: Session, q: VendorQualification, vendor: Vendor, today: date | None = None) -> None:
    today = today or date.today()
    errs = []
    if q.qualified_on is None:
        errs.append("qualified_on (date of qualification decision basis) is required")
    elif q.qualified_on > today:
        errs.append("qualified_on cannot be in the future")
    if q.requalification_due_date is None:
        errs.append("requalification_due_date is required")
    elif q.requalification_due_date <= today:
        errs.append("requalification_due_date must be in the future")
    elif q.qualified_on and q.requalification_due_date <= q.qualified_on:
        errs.append("requalification_due_date must be after qualified_on")
    errs += [f"Document {g}" for g in document_gaps(session, vendor.id, q.risk_class, today)]
    if q.risk_class == "CRITICAL":
        if vendor.quality_agreement_status != "SIGNED":
            errs.append("Critical vendors require a signed quality agreement")
        if vendor.vendor_audit_status == "NOT_AUDITED" and not q.audit_report_ref:
            errs.append("Critical vendors require an audit (or audit report reference)")
    if errs:
        raise ValidationFailed("Qualification is not ready: " + "; ".join(errs), code="VQ_NOT_READY", details=errs)


def submit(session: Session, q: VendorQualification) -> None:
    validate_content(session, q, session.get(Vendor, q.vendor_id))
    transition(session, VQ_MACHINE, q, "UNDER_REVIEW", module="purchase")


def return_to_draft(session: Session, q: VendorQualification, reason: str) -> None:
    transition(session, VQ_MACHINE, q, "DRAFT", reason=reason, module="purchase")


def _supersede_previous(session: Session, q: VendorQualification) -> None:
    now = utcnow()
    for old in session.execute(select(VendorQualification).where(
            VendorQualification.vendor_id == q.vendor_id, VendorQualification.id != q.id,
            VendorQualification.status.in_(STANDING))).scalars():
        old.effective_to = now
        transition(session, VQ_MACHINE, old, "SUPERSEDED", reason=f"superseded by v{q.version_no}", module="purchase")


def approve(session: Session, q: VendorQualification, user, password: str, reason: str, conditional: bool) -> None:
    vendor = session.get(Vendor, q.vendor_id)
    if vendor.approval_status != "APPROVED":
        raise BusinessRuleError("The vendor master record is not APPROVED", rule_id="VQ-001")
    validate_content(session, q, vendor)
    to = "CONDITIONAL" if conditional else "APPROVED"
    sig = masters.sign_and_transition(session, q, VQ_MACHINE, to, user, password, reason=reason,
                                      meaning="QA_APPROVED", sod_action="vendor_qualification.approve")
    q.effective_from = utcnow()
    q.approved_signature_id = sig.id
    _supersede_previous(session, q)


def _adverse(session: Session, q: VendorQualification, to: str, user, password: str, reason: str) -> None:
    sig = masters.sign_and_transition(session, q, VQ_MACHINE, to, user, password, reason=reason,
                                      meaning="APPROVED_BY")
    q.status_reason = reason


def suspend(session, q, user, password, reason):
    _adverse(session, q, "SUSPENDED", user, password, reason)


def disqualify(session, q, user, password, reason):
    _adverse(session, q, "DISQUALIFIED", user, password, reason)


# ------------------------------------------------------------------ job
def expire_due(session: Session, today: date | None = None) -> list[int]:
    """Persist EXPIRED for qualifications past their due date (system action) and notify QA/Purchase."""
    today = today or date.today()
    expired = []
    for q in session.execute(select(VendorQualification).where(
            VendorQualification.status.in_(("APPROVED", "CONDITIONAL")),
            VendorQualification.requalification_due_date < today)).scalars():
        transition(session, VQ_MACHINE, q, "EXPIRED", reason="Automatic expiry: requalification due date passed",
                   module="purchase")
        v = session.get(Vendor, q.vendor_id)
        notifications.notify_roles(session, ["QA_OFFICER", "QA_HEAD", "PURCHASE_MANAGER", "PURCHASE_USER"],
                                   category="VENDOR_QUALIFICATION",
                                   title=f"Vendor qualification EXPIRED: {v.vendor_code} {v.name}",
                                   body="Purchase orders for this vendor are blocked until requalification is approved.",
                                   ref_entity="vendor_qualification", ref_id=str(q.id))
        expired.append(q.id)
    return expired


def alert_upcoming(session: Session, today: date | None = None) -> int:
    today = today or date.today()
    thresholds = sorted({int(x) for x in (config_service.get(session, "vq.alert_days", "90,60,30,7") or "").split(",") if x.strip()})
    if not thresholds:
        return 0
    n = 0
    for q in session.execute(select(VendorQualification).where(
            VendorQualification.status.in_(("APPROVED", "CONDITIONAL")),
            VendorQualification.requalification_due_date >= today,
            VendorQualification.requalification_due_date <= today + timedelta(days=max(thresholds)))).scalars():
        days = (q.requalification_due_date - today).days
        bucket = min(t for t in thresholds if days <= t)
        v = session.get(Vendor, q.vendor_id)
        n += notifications.notify_roles(
            session, ["QA_OFFICER", "QA_HEAD", "PURCHASE_MANAGER"], category="VENDOR_QUALIFICATION",
            title=f"Vendor requalification due within {bucket} days: {v.vendor_code} {v.name}",
            body=f"Due {q.requalification_due_date.isoformat()} ({days} days).", ref_entity="vendor_qualification",
            ref_id=str(q.id))
    return n
