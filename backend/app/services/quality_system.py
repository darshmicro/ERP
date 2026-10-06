"""Quality system (Phase 8): deviation, CAPA, change control, FMEA risk assessment, SOP control, complaints, recalls.

Links to the rest of the system:
  * open deviations block QA release and dispatch of the linked lot (BR-DEV-001 / BR-DSP-004)
  * IPC failures, temperature excursions and reconciliation breaches raise deviations automatically
  * an approved change control is required to approve a new version of a controlled master (BR-CC-001, configurable)
  * a recall places the lot on quality hold and derives the affected shipments from the dispatch ledger
"""
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import BusinessRuleError, Conflict, NotFound, ValidationFailed
from app.core.time import utcnow
from app.models.dispatch import Dispatch, DispatchLine
from app.models.manufacturing import ManufacturingBatch
from app.models.master import Location
from app.models.quality import (CAPA, CAPAAction, ChangeControl, ChangeControlLink, Complaint, Deviation, Recall, RecallLine, RiskAssessment,
                                RiskItem, SOP, SOPAcknowledgement)
from app.models.warehouse import MaterialBatch
from app.services import config_service, inventory, lots, masters, notifications, numbering, sod, versioning
from app.workflows.state_machine import StateMachine, Transition, transition

T = Transition
D = Decimal


def _plant(s: Session) -> int:
    return numbering.default_plant_id(s)


def _need(text: str | None, what: str) -> None:
    if not (text or "").strip():
        raise ValidationFailed(f"{what} is required", code="REASON_REQUIRED")


# ================================================================== deviation
DEV_MACHINE = StateMachine("deviation", "OPEN", {
    "OPEN": {"INVESTIGATION": T("INVESTIGATION", "quality.deviation.investigate"), "CANCELLED": T("CANCELLED", requires_reason=True)},
    "INVESTIGATION": {"CAPA_PROPOSED": T("CAPA_PROPOSED", "quality.deviation.investigate"), "CANCELLED": T("CANCELLED", requires_reason=True)},
    "CAPA_PROPOSED": {"QA_REVIEW": T("QA_REVIEW", "quality.deviation.investigate"), "INVESTIGATION": T("INVESTIGATION", requires_reason=True)},
    "QA_REVIEW": {"CLOSED": T("CLOSED", "quality.deviation.close", "QA_APPROVED", True), "INVESTIGATION": T("INVESTIGATION", requires_reason=True)},
})
DEV_FIELDS = {"title", "description", "category", "severity", "containment", "root_cause", "impact_assessment", "no_capa_justification", "blocks_release"}


def raise_deviation(session: Session, user_id: int | None, *, title: str, description: str, category: str = "PROCESS", severity: str = "MINOR", source: str = "MANUAL",
                    entity_type: str | None = None, record_id: int | None = None, blocks_release: bool = True, containment: str | None = None) -> Deviation:
    if entity_type == "MATERIAL_BATCH" and session.get(MaterialBatch, record_id) is None:
        raise ValidationFailed("Unknown lot")
    if entity_type == "MFG_BATCH" and session.get(ManufacturingBatch, record_id) is None:
        raise ValidationFailed("Unknown batch")
    if entity_type and entity_type not in ("MATERIAL_BATCH", "MFG_BATCH"):
        raise ValidationFailed("entity_type must be MATERIAL_BATCH or MFG_BATCH")
    d = Deviation(dev_no=numbering.next_number(session, _plant(session), "DEVIATION"), title=title, description=description, category=category, severity=severity,
                  source=source, entity_type=entity_type, record_id=record_id, blocks_release=blocks_release, status="OPEN", raised_by_id=user_id, containment=containment)
    session.add(d)
    session.flush()
    if user_id:
        sod.record_action(session, "deviation", d.id, "quality.deviation.raise", user_id)
    notifications.notify_roles(session, ["QA_OFFICER", "QA_HEAD"], category="DEVIATION", title=f"Deviation {d.dev_no} raised ({severity})", body=title,
                               ref_entity="deviation", ref_id=str(d.id))
    return d


def auto_deviation(session: Session, *, source: str, title: str, description: str, entity_type: str | None, record_id: int | None, severity: str = "MAJOR",
                   user_id: int | None = None) -> Deviation:
    """System-raised deviation (idempotent per source + record while one is still open)."""
    q = select(Deviation).where(Deviation.source == source, Deviation.entity_type == entity_type, Deviation.record_id == record_id,
                                Deviation.status.notin_(("CLOSED", "CANCELLED")))
    existing = session.execute(q).scalars().first()
    if existing:
        return existing
    return raise_deviation(session, user_id, title=title, description=description, severity=severity, source=source, entity_type=entity_type, record_id=record_id,
                           category="PROCESS" if source != "TEMPERATURE" else "EQUIPMENT")


def update_deviation(session: Session, d: Deviation, data: dict) -> None:
    bad = set(data) - DEV_FIELDS
    if bad:
        raise ValidationFailed(f"Not editable: {', '.join(sorted(bad))}")
    for k, v in data.items():
        setattr(d, k, v)


def start_investigation(session: Session, d: Deviation) -> None:
    transition(session, DEV_MACHINE, d, "INVESTIGATION", module="quality")


def propose_capa(session: Session, d: Deviation) -> None:
    _need(d.root_cause, "Root cause")
    _need(d.impact_assessment, "Impact assessment")
    if d.severity in ("MAJOR", "CRITICAL") and d.capa_id is None and not (d.no_capa_justification or "").strip():
        raise BusinessRuleError("A MAJOR/CRITICAL deviation needs a linked CAPA or a documented justification for none", rule_id="BR-DEV-002")
    transition(session, DEV_MACHINE, d, "CAPA_PROPOSED", module="quality")


def submit_dev_for_review(session: Session, d: Deviation) -> None:
    transition(session, DEV_MACHINE, d, "QA_REVIEW", module="quality")


def return_deviation(session: Session, d: Deviation, reason: str) -> None:
    _need(reason, "A reason")
    transition(session, DEV_MACHINE, d, "INVESTIGATION", reason=reason, module="quality")


def close_deviation(session: Session, d: Deviation, user, password: str, comment: str) -> None:
    if d.status != "QA_REVIEW":
        raise BusinessRuleError(f"Deviation is {d.status}; it must be in QA review", rule_id="BR-DEV-003")
    sod.check(session, user.id, "deviation", d.id, "quality.deviation.close")
    sig = masters.sign_and_transition(session, d, DEV_MACHINE, "CLOSED", user, password, reason=comment, meaning="QA_APPROVED", sod_action="quality.deviation.close")
    d.closed_by_id, d.closed_at, d.close_signature_id, d.close_comment = user.id, utcnow(), sig.id, comment


def cancel_deviation(session: Session, d: Deviation, reason: str) -> None:
    _need(reason, "A reason")
    d.cancel_reason = reason
    transition(session, DEV_MACHINE, d, "CANCELLED", reason=reason, module="quality")


def open_deviations_for_lot(session: Session, lot: MaterialBatch, *, only_blocking: bool = True) -> list[Deviation]:
    cond = [(Deviation.entity_type == "MATERIAL_BATCH") & (Deviation.record_id == lot.id)]
    if lot.manufacturing_batch_id:
        cond.append((Deviation.entity_type == "MFG_BATCH") & (Deviation.record_id == lot.manufacturing_batch_id))
    q = select(Deviation).where(cond[0] if len(cond) == 1 else cond[0] | cond[1], Deviation.status.notin_(("CLOSED", "CANCELLED")))
    if only_blocking:
        q = q.where(Deviation.blocks_release == True)  # noqa: E712
    return list(session.execute(q).scalars())


def deviation_blockers(session: Session, lot: MaterialBatch) -> list[tuple[str, str]]:
    return [("BR-DEV-001", f"Open deviation {d.dev_no} ({d.severity}) is linked to {lot.lot_no}") for d in open_deviations_for_lot(session, lot)]


# ================================================================== CAPA
CAPA_MACHINE = StateMachine("capa", "OPEN", {
    "OPEN": {"IN_PROGRESS": T("IN_PROGRESS"), "CANCELLED": T("CANCELLED", requires_reason=True)},
    "IN_PROGRESS": {"EFFECTIVENESS_CHECK": T("EFFECTIVENESS_CHECK"), "CANCELLED": T("CANCELLED", requires_reason=True)},
    "EFFECTIVENESS_CHECK": {"CLOSED": T("CLOSED", "quality.capa.close", "QA_APPROVED", True), "IN_PROGRESS": T("IN_PROGRESS", requires_reason=True)},
})


def create_capa(session: Session, user, data: dict) -> CAPA:
    if data["due_date"] < date.today():
        raise ValidationFailed("Due date cannot be in the past")
    from app.models.iam import User
    if session.get(User, data["owner_id"]) is None:
        raise ValidationFailed("Unknown owner")
    capa = CAPA(capa_no=numbering.next_number(session, _plant(session), "CAPA"), status="OPEN", created_by_user_id=user.id, **data)
    session.add(capa)
    session.flush()
    if data.get("source") == "DEVIATION" and data.get("source_ref"):
        dev = session.execute(select(Deviation).where(Deviation.dev_no == data["source_ref"])).scalars().first()
        if dev is None:
            raise ValidationFailed(f"Deviation {data['source_ref']} not found")
        if dev.capa_id is None:
            dev.capa_id = capa.id
    sod.record_action(session, "capa", capa.id, "quality.capa.create", user.id)
    return capa


def capa_actions(session: Session, capa_id: int) -> list[CAPAAction]:
    return list(session.execute(select(CAPAAction).where(CAPAAction.capa_id == capa_id).order_by(CAPAAction.seq)).scalars())


def add_action(session: Session, capa: CAPA, description: str, owner_id: int, due: date) -> CAPAAction:
    if capa.status not in ("OPEN", "IN_PROGRESS"):
        raise BusinessRuleError(f"CAPA is {capa.status}; actions can no longer be added", rule_id="BR-CAPA-001")
    if due < date.today():
        raise ValidationFailed("Due date cannot be in the past")
    seq = (session.execute(select(func.max(CAPAAction.seq)).where(CAPAAction.capa_id == capa.id)).scalar() or 0) + 1
    a = CAPAAction(capa_id=capa.id, seq=seq, description=description, owner_id=owner_id, due_date=due, status="OPEN")
    session.add(a)
    session.flush()
    if capa.status == "OPEN":
        transition(session, CAPA_MACHINE, capa, "IN_PROGRESS", reason="First action planned", module="quality")
    return a


def complete_action(session: Session, capa: CAPA, action: CAPAAction, user, notes: str) -> None:
    if action.capa_id != capa.id:
        raise NotFound("Action not found")
    if action.status == "DONE":
        raise BusinessRuleError("Action already completed", rule_id="BR-HIS-001")
    _need(notes, "Completion notes")
    action.status, action.completed_at, action.completion_notes = "DONE", utcnow(), notes


def start_effectiveness(session: Session, capa: CAPA, due: date) -> None:
    acts = capa_actions(session, capa.id)
    if not acts or any(a.status != "DONE" for a in acts):
        raise BusinessRuleError("All CAPA actions must be completed before the effectiveness check", rule_id="BR-CAPA-002")
    capa.effectiveness_due = due
    session.flush()
    transition(session, CAPA_MACHINE, capa, "EFFECTIVENESS_CHECK", module="quality")


def close_capa(session: Session, capa: CAPA, user, password: str, effective: bool, comment: str) -> None:
    if capa.status != "EFFECTIVENESS_CHECK":
        raise BusinessRuleError(f"CAPA is {capa.status}", rule_id="BR-CAPA-002")
    _need(comment, "An effectiveness comment")
    if not effective:
        capa.effectiveness_result, capa.effectiveness_comment = "INEFFECTIVE", comment
        transition(session, CAPA_MACHINE, capa, "IN_PROGRESS", reason=f"Ineffective: {comment}", module="quality")
        return
    sod.check(session, user.id, "capa", capa.id, "quality.capa.close")
    sig = masters.sign_and_transition(session, capa, CAPA_MACHINE, "CLOSED", user, password, reason=comment, meaning="QA_APPROVED", sod_action="quality.capa.close")
    capa.effectiveness_result, capa.effectiveness_comment = "EFFECTIVE", comment
    capa.closed_by_id, capa.closed_at, capa.close_signature_id = user.id, utcnow(), sig.id


def capa_overdue(session: Session, today: date | None = None) -> list[CAPA]:
    today = today or date.today()
    return list(session.execute(select(CAPA).where(CAPA.status.in_(("OPEN", "IN_PROGRESS")), CAPA.due_date < today)).scalars())


# ================================================================== change control
CC_MACHINE = StateMachine("change_control", "DRAFT", {
    "DRAFT": {"ASSESSMENT": T("ASSESSMENT"), "CANCELLED": T("CANCELLED", requires_reason=True)},
    "ASSESSMENT": {"APPROVAL": T("APPROVAL", "quality.cc.assess"), "DRAFT": T("DRAFT", requires_reason=True), "CANCELLED": T("CANCELLED", requires_reason=True)},
    "APPROVAL": {"IMPLEMENTATION": T("IMPLEMENTATION", "quality.cc.approve", "QA_APPROVED", True), "REJECTED": T("REJECTED", "quality.cc.approve", "REJECTED_BY", True),
                 "ASSESSMENT": T("ASSESSMENT", requires_reason=True)},
    "IMPLEMENTATION": {"EFFECTIVENESS": T("EFFECTIVENESS")},
    "EFFECTIVENESS": {"CLOSED": T("CLOSED", "quality.cc.close", "QA_APPROVED", True)},
})
VERSIONED_TABLES = {"specification", "stp", "sampling_plan", "bom_header", "vendor_material", "sop"}


def create_cc(session: Session, user, data: dict) -> ChangeControl:
    cc = ChangeControl(cc_no=numbering.next_number(session, _plant(session), "CC"), status="DRAFT", requested_by_id=user.id, **data)
    session.add(cc)
    session.flush()
    sod.record_action(session, "change_control", cc.id, "quality.cc.create", user.id)
    return cc


def cc_links(session: Session, cc_id: int) -> list[ChangeControlLink]:
    return list(session.execute(select(ChangeControlLink).where(ChangeControlLink.cc_id == cc_id)).scalars())


def link_master(session: Session, cc: ChangeControl, entity: str, record_id: int) -> ChangeControlLink:
    if cc.status in ("CLOSED", "REJECTED", "CANCELLED", "EFFECTIVENESS"):
        raise BusinessRuleError(f"Change control is {cc.status}", rule_id="BR-CC-002")
    if entity not in VERSIONED_TABLES:
        raise ValidationFailed(f"entity must be one of {sorted(VERSIONED_TABLES)}")
    Model = masters.model_for_table(entity)
    obj = session.get(Model, record_id)
    if obj is None:
        raise NotFound("Versioned record not found")
    if obj.status not in ("DRAFT", "UNDER_REVIEW"):
        raise BusinessRuleError("Link the new DRAFT / UNDER_REVIEW version, not an approved one", rule_id="BR-CC-002")
    link = ChangeControlLink(cc_id=cc.id, entity=entity, record_id=record_id)
    session.add(link)
    session.flush()
    return link


def submit_assessment(session: Session, cc: ChangeControl) -> None:
    transition(session, CC_MACHINE, cc, "ASSESSMENT", module="quality")


def complete_assessment(session: Session, cc: ChangeControl, impact: str, risk_level: str, regulatory: bool) -> None:
    if cc.status != "ASSESSMENT":
        raise BusinessRuleError(f"Change control is {cc.status}", rule_id="BR-CC-002")
    _need(impact, "Impact assessment")
    if risk_level not in ("LOW", "MEDIUM", "HIGH"):
        raise ValidationFailed("risk_level must be LOW, MEDIUM or HIGH")
    cc.impact_assessment, cc.risk_level, cc.regulatory_impact = impact, risk_level, regulatory
    session.flush()
    transition(session, CC_MACHINE, cc, "APPROVAL", module="quality")


def decide_cc(session: Session, cc: ChangeControl, user, password: str, approve: bool, comment: str) -> None:
    if cc.status != "APPROVAL":
        raise BusinessRuleError(f"Change control is {cc.status}", rule_id="BR-CC-002")
    sod.check(session, user.id, "change_control", cc.id, "quality.cc.approve")
    sig = masters.sign_and_transition(session, cc, CC_MACHINE, "IMPLEMENTATION" if approve else "REJECTED", user, password, reason=comment,
                                      meaning="QA_APPROVED" if approve else "REJECTED_BY", sod_action="quality.cc.approve")
    cc.approved_by_id, cc.approved_signature_id, cc.approved_at, cc.decision_comment = user.id, sig.id, utcnow(), comment


def complete_implementation(session: Session, cc: ChangeControl, notes: str) -> None:
    _need(notes, "Implementation notes")
    pending = []
    for l in cc_links(session, cc.id):
        obj = session.get(masters.model_for_table(l.entity), l.record_id)
        if obj.status != "APPROVED":
            pending.append(f"{l.entity} #{l.record_id} is {obj.status}")
    if pending:
        raise BusinessRuleError("Linked master changes are not yet approved/effective: " + "; ".join(pending), rule_id="BR-CC-003", details=pending)
    cc.implementation_notes = notes
    session.flush()
    transition(session, CC_MACHINE, cc, "EFFECTIVENESS", module="quality")


def close_cc(session: Session, cc: ChangeControl, user, password: str, notes: str) -> None:
    if cc.status != "EFFECTIVENESS":
        raise BusinessRuleError(f"Change control is {cc.status}", rule_id="BR-CC-002")
    _need(notes, "Effectiveness notes")
    sig = masters.sign_and_transition(session, cc, CC_MACHINE, "CLOSED", user, password, reason=notes, meaning="QA_APPROVED")
    cc.effectiveness_notes, cc.closed_by_id, cc.closed_at, cc.close_signature_id = notes, user.id, utcnow(), sig.id


def cancel_cc(session: Session, cc: ChangeControl, reason: str) -> None:
    _need(reason, "A reason")
    transition(session, CC_MACHINE, cc, "CANCELLED", reason=reason, module="quality")


def assert_change_control(session: Session, obj) -> None:
    """BR-CC-001 / BR-BOM-002 / BR-VM-001: when enabled, a new version of a controlled master needs an approved, in-implementation change control."""
    if not config_service.get_bool(session, "cc.required_for_master_changes", False):
        return
    if getattr(obj, "version_no", 1) <= 1 or type(obj).__tablename__ not in VERSIONED_TABLES:
        return
    ok = session.execute(select(ChangeControl.id).join(ChangeControlLink, ChangeControlLink.cc_id == ChangeControl.id).where(
        ChangeControlLink.entity == type(obj).__tablename__, ChangeControlLink.record_id == obj.id,
        ChangeControl.status.in_(("IMPLEMENTATION", "EFFECTIVENESS", "CLOSED"))).limit(1)).first()
    if not ok:
        raise BusinessRuleError(f"Approving a new version of {type(obj).__tablename__} requires an approved change control linked to it (BR-CC-001)", rule_id="BR-CC-001")


# ================================================================== risk assessment (FMEA)
def _level(session: Session, rpn: int) -> str:
    high = int(config_service.get(session, "risk.rpn_high", "200") or 200)
    med = int(config_service.get(session, "risk.rpn_medium", "100") or 100)
    return "HIGH" if rpn >= high else "MEDIUM" if rpn >= med else "LOW"


def create_ra(session: Session, user, data: dict, items: list[dict]) -> RiskAssessment:
    ra = RiskAssessment(ra_no=numbering.next_number(session, _plant(session), "RISK"), status="DRAFT", created_by_user_id=user.id, **data)
    session.add(ra)
    session.flush()
    set_items(session, ra, items)
    sod.record_action(session, "risk_assessment", ra.id, "quality.risk.author", user.id)
    return ra


def ra_items(session: Session, ra_id: int) -> list[RiskItem]:
    return list(session.execute(select(RiskItem).where(RiskItem.ra_id == ra_id).order_by(RiskItem.seq)).scalars())


def set_items(session: Session, ra: RiskAssessment, items: list[dict]) -> None:
    if ra.status != "DRAFT":
        raise BusinessRuleError("An approved risk assessment is immutable; create a new one", rule_id="BR-HIS-001")
    for old in ra_items(session, ra.id):
        session.delete(old)
    session.flush()
    for i, it in enumerate(items, 1):
        rpn = it["severity"] * it["occurrence"] * it["detection"]
        extra = {}
        if it.get("residual_severity") and it.get("residual_occurrence") and it.get("residual_detection"):
            rr = it["residual_severity"] * it["residual_occurrence"] * it["residual_detection"]
            extra = {"residual_rpn": rr, "residual_level": _level(session, rr)}
        session.add(RiskItem(ra_id=ra.id, seq=i, rpn=rpn, risk_level=_level(session, rpn), **{**it, **extra}))
    session.flush()


def approve_ra(session: Session, ra: RiskAssessment, user, password: str, reason: str) -> None:
    items = ra_items(session, ra.id)
    if not items:
        raise ValidationFailed("A risk assessment needs at least one item")
    open_high = [i.seq for i in items if i.risk_level == "HIGH" and (not (i.mitigation or "").strip() or i.residual_rpn is None)]
    if open_high:
        raise BusinessRuleError(f"HIGH risk items {open_high} need a mitigation and a residual risk rating before approval", rule_id="BR-RSK-001", details=open_high)
    sod.check(session, user.id, "risk_assessment", ra.id, "quality.risk.approve")
    machine = StateMachine("risk_assessment", "DRAFT", {"DRAFT": {"APPROVED": T("APPROVED", "quality.risk.approve", "QA_APPROVED", True)}})
    sig = masters.sign_and_transition(session, ra, machine, "APPROVED", user, password, reason=reason, meaning="QA_APPROVED", sod_action="quality.risk.approve")
    ra.approved_by_id, ra.approved_signature_id, ra.approved_at = user.id, sig.id, utcnow()


# ================================================================== SOP control
def approve_sop(session: Session, sop: SOP, user, password: str, reason: str) -> None:
    if sop.document_id is None:
        raise BusinessRuleError("Attach the SOP document before approval", rule_id="BR-SOP-001")
    versioning.approve(session, sop, user, password, reason)
    months = sop.review_period_months or 24
    sop.review_due_date = date.today() + timedelta(days=int(months * 30.4375))


def acknowledge_sop(session: Session, sop: SOP, user) -> SOPAcknowledgement:
    if sop.status != "APPROVED":
        raise BusinessRuleError("Only an APPROVED (current) SOP can be acknowledged", rule_id="BR-SOP-002")
    if session.execute(select(SOPAcknowledgement.id).where(SOPAcknowledgement.sop_id == sop.id, SOPAcknowledgement.user_id == user.id)).first():
        raise Conflict("You have already acknowledged this SOP version")
    a = SOPAcknowledgement(sop_id=sop.id, user_id=user.id)
    session.add(a)
    session.flush()
    return a


def sops_due_for_review(session: Session, days: int = 30, today: date | None = None) -> list[SOP]:
    today = today or date.today()
    return list(session.execute(select(SOP).where(SOP.status == "APPROVED", SOP.review_due_date <= today + timedelta(days=days))).scalars())


# ================================================================== complaints
COMPLAINT_MACHINE = StateMachine("complaint", "RECEIVED", {
    "RECEIVED": {"INVESTIGATION": T("INVESTIGATION", "quality.complaint.update"), "CANCELLED": T("CANCELLED", requires_reason=True)},
    "INVESTIGATION": {"CLOSED": T("CLOSED", "quality.complaint.close", "QA_APPROVED", True)},
})


def create_complaint(session: Session, user, data: dict) -> Complaint:
    lot = session.get(MaterialBatch, data["material_batch_id"]) if data.get("material_batch_id") else None
    if data.get("material_batch_id") and lot is None:
        raise ValidationFailed("Unknown lot")
    if data.get("dispatch_id"):
        disp = session.get(Dispatch, data["dispatch_id"])
        if disp is None:
            raise ValidationFailed("Unknown dispatch")
        data["customer_id"] = data.get("customer_id") or disp.customer_id
        if lot is not None and not session.execute(select(DispatchLine.id).where(DispatchLine.dispatch_id == disp.id, DispatchLine.material_batch_id == lot.id)).first():
            raise ValidationFailed("The lot was not part of that dispatch")
    c = Complaint(complaint_no=numbering.next_number(session, _plant(session), "COMPLAINT"), status="RECEIVED", created_by_user_id=user.id,
                  received_on=data.pop("received_on", None) or date.today(), **data)
    session.add(c)
    session.flush()
    if lot is not None and (c.severity == "CRITICAL" or c.category == "ADVERSE_EVENT"):
        h = lots.place_hold(session, "MATERIAL_BATCH", lot.id, f"Complaint {c.complaint_no} ({c.severity}): {c.description[:150]}", source="COMPLAINT", ref=c.complaint_no, user_id=user.id)
        c.hold_id = h.id
    notifications.notify_roles(session, ["QA_OFFICER", "QA_HEAD"], category="COMPLAINT", title=f"Complaint {c.complaint_no} received ({c.severity})", body=c.description[:200],
                               ref_entity="complaint", ref_id=str(c.id))
    sod.record_action(session, "complaint", c.id, "quality.complaint.create", user.id)
    return c


def investigate_complaint(session: Session, c: Complaint, investigation: str) -> None:
    _need(investigation, "Investigation notes")
    if c.status == "RECEIVED":
        c.investigation = investigation
        session.flush()
        transition(session, COMPLAINT_MACHINE, c, "INVESTIGATION", module="quality")
    elif c.status == "INVESTIGATION":
        c.investigation = investigation
    else:
        raise BusinessRuleError(f"Complaint is {c.status}", rule_id="BR-CMP-001")


def deviation_from_complaint(session: Session, user, c: Complaint) -> Deviation:
    if c.deviation_id:
        raise Conflict("A deviation is already linked to this complaint")
    d = raise_deviation(session, user.id, title=f"Complaint {c.complaint_no}", description=c.description, category="QC", severity=c.severity, source="COMPLAINT",
                        entity_type="MATERIAL_BATCH" if c.material_batch_id else None, record_id=c.material_batch_id)
    c.deviation_id = d.id
    return d


def close_complaint(session: Session, c: Complaint, user, password: str, conclusion: str) -> None:
    if c.status != "INVESTIGATION":
        raise BusinessRuleError("Investigate the complaint before closing it", rule_id="BR-CMP-001")
    _need(conclusion, "A conclusion")
    if c.deviation_id:
        dev = session.get(Deviation, c.deviation_id)
        if dev.status not in ("CLOSED", "CANCELLED"):
            raise BusinessRuleError(f"Linked deviation {dev.dev_no} is still {dev.status}", rule_id="BR-CMP-001")
    sig = masters.sign_and_transition(session, c, COMPLAINT_MACHINE, "CLOSED", user, password, reason=conclusion, meaning="QA_APPROVED")
    c.conclusion, c.closed_by_id, c.closed_at, c.close_signature_id = conclusion, user.id, utcnow(), sig.id


# ================================================================== recall
RECALL_MACHINE = StateMachine("recall", "INITIATED", {
    "INITIATED": {"IN_PROGRESS": T("IN_PROGRESS")},
    "IN_PROGRESS": {"CLOSED": T("CLOSED", "quality.recall.close", "QA_APPROVED", True)},
})


def initiate_recall(session: Session, user, lot: MaterialBatch, recall_class: str, reason: str, password: str, complaint_id: int | None) -> Recall:
    _need(reason, "A reason")
    from app.services import esign
    # authenticate/sign BEFORE any write (failed-login bookkeeping uses an independent transaction)
    sig = esign.sign(session, user, password, meaning="APPROVED_BY", entity="material_batch", record_id=lot.id,
                     record_snapshot={"action": "RECALL", "lot": lot.lot_no, "class": recall_class, "reason": reason}, reason=reason, required_permission="quality.recall.create")
    rc = Recall(recall_no=numbering.next_number(session, _plant(session), "RECALL"), material_batch_id=lot.id, recall_class=recall_class, reason=reason,
                complaint_id=complaint_id, status="INITIATED", initiated_by_id=user.id, initiated_signature_id=sig.id)
    session.add(rc)
    session.flush()
    h = lots.place_hold(session, "MATERIAL_BATCH", lot.id, f"Recall {rc.recall_no} (class {recall_class}): {reason[:150]}", source="RECALL", ref=rc.recall_no, user_id=user.id)
    rc.hold_id = h.id
    sent: dict[int, tuple[int, Decimal]] = {}
    for did, cid, q in session.execute(select(DispatchLine.dispatch_id, Dispatch.customer_id, DispatchLine.quantity).join(Dispatch, Dispatch.id == DispatchLine.dispatch_id).where(
            DispatchLine.material_batch_id == lot.id, Dispatch.status.in_(("DISPATCHED", "DELIVERED")))):
        prev = sent.get(did, (cid, D(0)))
        sent[did] = (cid, prev[1] + q)
    for did, (cid, q) in sent.items():
        session.add(RecallLine(recall_id=rc.id, dispatch_id=did, customer_id=cid, quantity_dispatched=q))
    session.flush()
    notifications.notify_roles(session, ["QA_OFFICER", "QA_HEAD", "DISPATCH_USER", "MANAGEMENT"], category="RECALL", title=f"RECALL {rc.recall_no} initiated for {lot.lot_no}",
                               body=reason[:200], ref_entity="recall", ref_id=str(rc.id))
    sod.record_action(session, "recall", rc.id, "quality.recall.create", user.id)
    return rc


def recall_lines(session: Session, recall_id: int) -> list[RecallLine]:
    return list(session.execute(select(RecallLine).where(RecallLine.recall_id == recall_id).order_by(RecallLine.id)).scalars())


def notify_customer(session: Session, rc: Recall, line: RecallLine, response: str | None) -> None:
    if line.recall_id != rc.id:
        raise NotFound("Recall line not found")
    if rc.status == "CLOSED":
        raise BusinessRuleError("Recall is closed", rule_id="BR-RCL-001")
    line.notified_at, line.response = utcnow(), response
    if rc.status == "INITIATED":
        transition(session, RECALL_MACHINE, rc, "IN_PROGRESS", reason="Customer notification started", module="quality")


def record_return(session: Session, rc: Recall, line: RecallLine, returned: D, unrecoverable: D, location: Location | None) -> None:
    if line.recall_id != rc.id:
        raise NotFound("Recall line not found")
    if rc.status != "IN_PROGRESS":
        raise BusinessRuleError("Notify customers first (recall must be IN_PROGRESS)", rule_id="BR-RCL-001")
    returned, unrecoverable = D(str(returned)), D(str(unrecoverable))
    if returned < 0 or unrecoverable < 0 or line.quantity_returned + line.quantity_consumed_or_unrecoverable + returned + unrecoverable > line.quantity_dispatched:
        raise BusinessRuleError("Returned + unrecoverable exceeds the quantity dispatched", rule_id="BR-RCL-002")
    if returned > 0:
        if location is None or not (location.is_quarantine or location.is_rejected_area):
            raise BusinessRuleError("Recalled stock must be received into a quarantine or rejected-material location", rule_id="BR-RCL-003")
        lot = session.get(MaterialBatch, rc.material_batch_id)
        inventory.post(session, txn_type="RETURN", batch=lot, quantity=returned, to_location_id=location.id, ref_doc_type="RECALL", ref_doc_id=rc.recall_no)
    line.quantity_returned = line.quantity_returned + returned
    line.quantity_consumed_or_unrecoverable = line.quantity_consumed_or_unrecoverable + unrecoverable


def close_recall(session: Session, rc: Recall, user, password: str, summary: str) -> dict:
    if rc.status != "IN_PROGRESS":
        raise BusinessRuleError(f"Recall is {rc.status}", rule_id="BR-RCL-001")
    _need(summary, "A closure summary")
    lines = recall_lines(session, rc.id)
    un_notified = [l.id for l in lines if l.notified_at is None]
    if un_notified:
        raise BusinessRuleError("Every affected customer must be notified before closing", rule_id="BR-RCL-004", details=un_notified)
    result = recall_reconciliation(session, rc)
    sig = masters.sign_and_transition(session, rc, RECALL_MACHINE, "CLOSED", user, password, reason=summary, meaning="QA_APPROVED")
    rc.closure_summary, rc.closed_by_id, rc.closed_at, rc.close_signature_id = summary, user.id, utcnow(), sig.id
    return result


def recall_reconciliation(session: Session, rc: Recall) -> dict:
    lines = recall_lines(session, rc.id)
    disp = sum((l.quantity_dispatched for l in lines), D(0))
    ret = sum((l.quantity_returned for l in lines), D(0))
    un = sum((l.quantity_consumed_or_unrecoverable for l in lines), D(0))
    return {"dispatched": float(disp), "returned": float(ret), "unrecoverable": float(un), "outstanding": float(disp - ret - un),
            "recovery_pct": float(round(ret / disp * 100, 2)) if disp else 0.0}


# ================================================================== daily job
def daily_alerts(session: Session, today: date | None = None) -> int:
    """Overdue CAPAs (owner + QA) and SOPs due for periodic review (QA). Idempotent: identical unread notifications are not duplicated."""
    from app.models.platform import Notification
    today = today or date.today()
    n = 0
    for c in capa_overdue(session, today):
        title = f"CAPA {c.capa_no} is overdue (due {c.due_date.isoformat()})"
        if not session.execute(select(Notification.id).where(Notification.user_id == c.owner_id, Notification.title == title, Notification.read_at.is_(None))).first():
            session.add(Notification(user_id=c.owner_id, category="CAPA", title=title, body=c.title, ref_entity="capa", ref_id=str(c.id)))
            n += 1
        notifications.notify_roles(session, ["QA_OFFICER", "QA_HEAD"], category="CAPA", title=title, body=c.title, ref_entity="capa", ref_id=str(c.id))
    for sp in sops_due_for_review(session, 30, today):
        notifications.notify_roles(session, ["QA_OFFICER", "QA_HEAD"], category="SOP", title=f"SOP {sp.sop_no} v{sp.version_no} review due {sp.review_due_date.isoformat()}",
                                   body=sp.title, ref_entity="sop", ref_id=str(sp.id))
        n += 1
    return n
