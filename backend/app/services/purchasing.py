"""Purchase request and purchase order services, including the PO gate rules (BR-PO-001..010).

The gate is evaluated at PO creation, again at submission and again at approval (spec 12/17/92).
Hard blocks raise BusinessRuleError carrying every violation; each block is also written to the
security event log so QA can review attempted purchases from unqualified vendors.
"""
import json
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit import service as audit
from app.audit.context import get_context
from app.core.errors import (BusinessRuleError, NotFound, PermissionDenied, ValidationFailed)
from app.models.iam import Role, User
from app.models.master import Material, Vendor
from app.models.platform import WorkflowInstance, WorkflowTransaction
from app.models.purchase import (PurchaseOrder, PurchaseOrderLine, PurchaseRequest, PurchaseRequestLine,
                                 VendorMaterial)
from app.security.permissions import effective_permissions
from app.services import config_service, masters, numbering, sod
from app.services import vendor_materials as vms
from app.services import vendor_qualification as vqs
from app.services.security_events import log_security_event
from app.services import versioning
from app.workflows import approval
from app.workflows.state_machine import StateMachine, Transition, transition

T = Transition
PR_MACHINE = StateMachine("purchase_request", "DRAFT", {
    "DRAFT": {"SUBMITTED": T("SUBMITTED"), "CANCELLED": T("CANCELLED", requires_reason=True)},
    "SUBMITTED": {"DEPARTMENT_APPROVED": T("DEPARTMENT_APPROVED"), "APPROVED": T("APPROVED"),
                  "REJECTED": T("REJECTED"), "CANCELLED": T("CANCELLED", requires_reason=True)},
    "DEPARTMENT_APPROVED": {"APPROVED": T("APPROVED"), "REJECTED": T("REJECTED"),
                            "CANCELLED": T("CANCELLED", requires_reason=True)},
    "APPROVED": {"CONVERTED": T("CONVERTED"), "CANCELLED": T("CANCELLED", requires_reason=True)},
})
PO_MACHINE = StateMachine("purchase_order", "DRAFT", {
    "DRAFT": {"PENDING_APPROVAL": T("PENDING_APPROVAL"), "CANCELLED": T("CANCELLED", requires_reason=True)},
    "PENDING_APPROVAL": {"APPROVED": T("APPROVED"), "REJECTED": T("REJECTED"),
                         "CANCELLED": T("CANCELLED", "po.order.cancel", "APPROVED_BY", True)},
    "APPROVED": {"PARTIALLY_RECEIVED": T("PARTIALLY_RECEIVED"), "CLOSED": T("CLOSED"),
                 "CANCELLED": T("CANCELLED", "po.order.cancel", "APPROVED_BY", True)},
    "PARTIALLY_RECEIVED": {"CLOSED": T("CLOSED")},
})


# ================================================================== PO gate rules
@dataclass
class Violation:
    rule_id: str
    message: str
    severity: str = "BLOCK"          # BLOCK | WARN
    line_no: int | None = None


def evaluate_po(session: Session, *, vendor_id: int, lines: list[dict], stage: str, user_id: int | None,
                today: date | None = None, header: dict | None = None) -> tuple[list[Violation], dict]:
    """Evaluate every PO rule. Returns (violations, pins) where pins resolves the exact qualification,
    specification and vendor-material versions the PO relies on."""
    today = today or date.today()
    vio: list[Violation] = []
    pins: dict[str, Any] = {"qualification_id": None, "lines": []}
    vendor = session.get(Vendor, vendor_id)
    if vendor is None:
        return [Violation("BR-PO-002", "Vendor not found")], pins

    # BR-PO-007: authorisation (create/approve permission is also checked by the API layer; re-checked here)
    if user_id is not None:
        need = {"CREATE": "po.order.create", "SUBMIT": "po.order.submit", "APPROVE": "po.order.approve"}.get(stage)
        if need and need not in effective_permissions(session, user_id):
            vio.append(Violation("BR-PO-007", f"User is not authorised ({need})"))

    # BR-PO-002 / BR-PO-001: vendor approval + live qualification standing
    if vendor.approval_status != "APPROVED":
        vio.append(Violation("BR-PO-002", "PURCHASE BLOCKED — VENDOR NOT APPROVED."))
    st = vqs.standing(session, vendor_id, today)
    pins["qualification_id"] = st.qualification.id if st.qualification else None
    if not st.purchasable:
        vio.append(Violation(st.block_rule or "BR-PO-002", st.message or "PURCHASE BLOCKED — VENDOR NOT QUALIFIED."))
    else:
        warn_days = int(config_service.get(session, "po.warn_vendor_due_days", "60") or 60)
        if st.days_to_due is not None and st.days_to_due <= warn_days:
            vio.append(Violation("BR-PO-010", f"Vendor requalification due in {st.days_to_due} day(s) "
                                              f"({st.qualification.requalification_due_date.isoformat()}).", "WARN"))
        if st.effective_status == "CONDITIONAL":
            vio.append(Violation("BR-PO-010", "Vendor is CONDITIONALLY qualified — check the conditions.", "WARN"))

    # BR-PO-006: required vendor documents present, approved, unexpired
    risk = st.qualification.risk_class if st.qualification else vendor.risk_class
    for gap in vqs.document_gaps(session, vendor_id, risk, today):
        vio.append(Violation("BR-PO-006", f"Required vendor document missing/invalid — {gap}"))

    # header sanity (BR-PO-008)
    if header:
        po_date, dd = header.get("po_date"), header.get("delivery_date")
        if dd and po_date and dd < po_date:
            vio.append(Violation("BR-PO-008", "Delivery date is before the PO date"))
    if not lines:
        vio.append(Violation("BR-PO-008", "A purchase order needs at least one line"))
    seen: set[int] = set()
    for i, ln in enumerate(lines, 1):
        n = ln.get("line_no") or i
        mat = session.get(Material, ln["material_id"])
        if mat is None:
            vio.append(Violation("BR-PO-004", "Unknown material", line_no=n))
            continue
        if ln["material_id"] in seen:
            vio.append(Violation("BR-PO-008", f"Material {mat.material_code} appears twice", line_no=n))
        seen.add(ln["material_id"])
        q, rate, tax = Decimal(str(ln.get("quantity", 0))), Decimal(str(ln.get("rate", 0))), Decimal(str(ln.get("tax_pct", 0)))
        if q <= 0 or rate < 0 or tax < 0 or tax > 100:
            vio.append(Violation("BR-PO-008", f"Invalid quantity/rate/tax for {mat.material_code}", line_no=n))
        if ln.get("unit_id") and ln["unit_id"] != mat.base_unit_id:
            vio.append(Violation("BR-PO-008", f"Unit of {mat.material_code} must be its base unit", line_no=n))
        if mat.master_status != "ACTIVE":       # BR-PO-004
            vio.append(Violation("BR-PO-004", f"Material {mat.material_code} is {mat.master_status}, not ACTIVE", line_no=n))
        vm = vms.approved_mapping(session, vendor_id, ln["material_id"], today)   # BR-PO-003
        if vm is None:
            vio.append(Violation("BR-PO-003", f"PURCHASE BLOCKED — VENDOR NOT APPROVED FOR MATERIAL {mat.material_code}.", line_no=n))
        spec = versioning.current_spec_for_material(session, ln["material_id"])   # BR-PO-005
        if spec is None:
            vio.append(Violation("BR-PO-005", f"No approved specification exists for {mat.material_code}", line_no=n))
        pins["lines"].append({"material_id": ln["material_id"], "vendor_material_id": vm.id if vm else None,
                              "specification_id": spec.id if spec else None})
    return vio, pins


def blocks(vio: list[Violation]) -> list[Violation]:
    return [v for v in vio if v.severity == "BLOCK"]


def assert_allowed(session: Session, vio: list[Violation], *, stage: str, vendor_id: int, po_ref: str = "new") -> None:
    b = blocks(vio)
    if not b:
        return
    ctx = get_context()
    log_security_event("PO_BLOCKED", user_id=ctx.user_id, username=ctx.user_name,
                       detail=f"{stage} vendor={vendor_id} po={po_ref}: " + "; ".join(f"{v.rule_id} {v.message}" for v in b))
    raise BusinessRuleError(b[0].message, rule_id=b[0].rule_id, details=[asdict(v) for v in vio])


# ================================================================== helpers
def _plant(session: Session) -> int:
    return numbering.default_plant_id(session)


def workflow_view(session: Session, inst_id: int | None) -> dict | None:
    if not inst_id:
        return None
    inst = session.get(WorkflowInstance, inst_id)
    if inst is None:
        return None
    from app.models.platform import WorkflowStep
    steps = session.execute(select(WorkflowStep, Role.role_code).join(Role, Role.id == WorkflowStep.role_id)
                            .where(WorkflowStep.definition_id == inst.definition_id).order_by(WorkflowStep.seq)).all()
    hist = session.execute(select(WorkflowTransaction, User.full_name).join(User, User.id == WorkflowTransaction.actor_id)
                           .where(WorkflowTransaction.instance_id == inst.id).order_by(WorkflowTransaction.id)).all()
    return {"id": inst.id, "status": inst.status, "current_seq": inst.current_seq,
            "steps": [{"seq": s.seq, "name": s.name, "role": rc, "esig": s.esig_required} for s, rc in steps],
            "history": [{"seq": t.seq, "decision": t.decision, "by": n, "comment": t.comment,
                         "signed": t.signature_id is not None, "at": t.occurred_at.isoformat()} for t, n in hist]}


def _cancel_instance(session: Session, inst_id: int | None, user: User, reason: str) -> None:
    if not inst_id:
        return
    inst = session.get(WorkflowInstance, inst_id)
    if inst and inst.status == "IN_PROGRESS":
        approval.cancel(session, inst, user, reason)


# ================================================================== purchase request
def create_pr(session: Session, user: User, header: dict, lines: list[dict]) -> PurchaseRequest:
    if not user.department_id:
        raise ValidationFailed("Your user account has no department; ask the administrator to set it.")
    _validate_pr_lines(session, lines)
    pr = PurchaseRequest(pr_no=numbering.next_number(session, _plant(session), "PR"), request_date=date.today(),
                         department_id=user.department_id, requested_by_id=user.id, status="DRAFT", **header)
    session.add(pr)
    session.flush()
    _set_pr_lines(session, pr, lines)
    sod.record_action(session, "purchase_request", pr.id, "pr.request.create", user.id)
    return pr


def _validate_pr_lines(session: Session, lines: list[dict]) -> None:
    if not lines:
        raise ValidationFailed("A purchase request needs at least one line")
    seen = set()
    for ln in lines:
        m = session.get(Material, ln["material_id"])
        if m is None:
            raise ValidationFailed("Unknown material on a line")
        if m.master_status != "ACTIVE":
            raise BusinessRuleError(f"Material {m.material_code} is {m.master_status}; only ACTIVE materials can be requested",
                                    rule_id="BR-PR-002")
        if m.id in seen:
            raise ValidationFailed(f"Material {m.material_code} appears more than once")
        seen.add(m.id)
        if Decimal(str(ln["quantity"])) <= 0:
            raise ValidationFailed("Quantity must be positive")
        if ln.get("unit_id") and ln["unit_id"] != m.base_unit_id:
            raise ValidationFailed(f"Unit of {m.material_code} must be its base unit")
        if ln.get("preferred_vendor_id") and session.get(Vendor, ln["preferred_vendor_id"]) is None:
            raise ValidationFailed("Unknown preferred vendor")


def _set_pr_lines(session: Session, pr: PurchaseRequest, lines: list[dict]) -> None:
    for old in session.execute(select(PurchaseRequestLine).where(PurchaseRequestLine.pr_id == pr.id)).scalars():
        session.delete(old)   # DRAFT only (ORM hook); logged as DELETE in the audit trail
    session.flush()
    for i, ln in enumerate(lines, 1):
        m = session.get(Material, ln["material_id"])
        session.add(PurchaseRequestLine(pr_id=pr.id, line_no=i, unit_id=ln.get("unit_id") or m.base_unit_id,
                                        **{k: v for k, v in ln.items() if k != "unit_id"}))
    session.flush()


def replace_pr_lines(session: Session, pr: PurchaseRequest, lines: list[dict]) -> None:
    if pr.status != "DRAFT":
        raise BusinessRuleError("Only a DRAFT request can be edited", rule_id="BR-HIS-001")
    _validate_pr_lines(session, lines)
    _set_pr_lines(session, pr, lines)


def submit_pr(session: Session, pr: PurchaseRequest, user: User) -> None:
    if pr.requested_by_id != user.id:
        raise PermissionDenied("Only the requester can submit this request")
    lines = list(session.execute(select(PurchaseRequestLine).where(PurchaseRequestLine.pr_id == pr.id)).scalars())
    _validate_pr_lines(session, [{"material_id": l.material_id, "quantity": l.quantity, "unit_id": l.unit_id,
                                  "preferred_vendor_id": l.preferred_vendor_id} for l in lines])
    inst = approval.start(session, "pr.request", "purchase_request", pr.id, user)
    pr.workflow_instance_id = inst.id
    transition(session, PR_MACHINE, pr, "SUBMITTED", module="purchase")


def pr_snapshot(session: Session, pr: PurchaseRequest) -> dict:
    lines = session.execute(select(PurchaseRequestLine).where(PurchaseRequestLine.pr_id == pr.id)
                            .order_by(PurchaseRequestLine.line_no)).scalars().all()
    return {**masters.snapshot(pr), "lines": [masters.snapshot(l) for l in lines]}


def act_pr(session: Session, pr: PurchaseRequest, user: User, decision: str, comment: str | None,
           password: str | None) -> None:
    if pr.status not in ("SUBMITTED", "DEPARTMENT_APPROVED"):
        raise BusinessRuleError(f"Request is {pr.status}; nothing to approve", rule_id="WF-002")
    inst = session.get(WorkflowInstance, pr.workflow_instance_id)
    step = approval.current_step(session, inst)
    role = session.get(Role, step.role_id)
    if role.role_code == "DEPARTMENT_HEAD" and user.department_id != pr.department_id:
        raise PermissionDenied("Only the head of the requesting department can approve at this step")
    approval.act(session, inst, user, decision, password=password, comment=comment, record_snapshot=pr_snapshot(session, pr))
    if inst.status == "APPROVED":
        transition(session, PR_MACHINE, pr, "APPROVED", reason=comment, module="purchase")
    elif inst.status == "REJECTED":
        transition(session, PR_MACHINE, pr, "REJECTED", reason=comment, module="purchase")
    elif inst.current_seq > 1 and pr.status == "SUBMITTED":
        transition(session, PR_MACHINE, pr, "DEPARTMENT_APPROVED", reason=comment, module="purchase")


def cancel_pr(session: Session, pr: PurchaseRequest, user: User, reason: str) -> None:
    if not (reason or "").strip():
        raise ValidationFailed("A reason is required", code="REASON_REQUIRED")
    if pr.requested_by_id != user.id and "pr.request.approve" not in effective_permissions(session, user.id):
        raise PermissionDenied("Only the requester or an approver can cancel")
    _cancel_instance(session, pr.workflow_instance_id, user, reason)
    transition(session, PR_MACHINE, pr, "CANCELLED", reason=reason, module="purchase")


# ================================================================== purchase order
def po_totals(session: Session, po_id: int) -> dict:
    lines = session.execute(select(PurchaseOrderLine).where(PurchaseOrderLine.po_id == po_id)).scalars().all()
    sub = sum((l.quantity * l.rate for l in lines), Decimal(0))
    tax = sum((l.quantity * l.rate * l.tax_pct / 100 for l in lines), Decimal(0))
    return {"subtotal": float(round(sub, 2)), "tax": float(round(tax, 2)), "total": float(round(sub + tax, 2))}


def po_snapshot(session: Session, po: PurchaseOrder) -> dict:
    lines = session.execute(select(PurchaseOrderLine).where(PurchaseOrderLine.po_id == po.id)
                            .order_by(PurchaseOrderLine.line_no)).scalars().all()
    return {**masters.snapshot(po, exclude={"validation_snapshot"}), "lines": [masters.snapshot(l) for l in lines]}


def _snapshot_json(vio: list[Violation], stage: str) -> str:
    return json.dumps({"stage": stage, "results": [asdict(v) for v in vio]})


def create_po(session: Session, user: User, header: dict, lines: list[dict], pr: PurchaseRequest | None = None) -> PurchaseOrder:
    vendor_id = header["vendor_id"]
    hdr = {**header, "po_date": date.today()}
    vio, pins = evaluate_po(session, vendor_id=vendor_id, lines=lines, stage="CREATE", user_id=user.id, header=hdr)
    assert_allowed(session, vio, stage="CREATE", vendor_id=vendor_id)
    po = PurchaseOrder(po_no=numbering.next_number(session, _plant(session), "PO"), po_date=date.today(),
                       status="DRAFT", vendor_qualification_id=pins["qualification_id"], pr_id=pr.id if pr else None,
                       validation_snapshot=_snapshot_json(vio, "CREATE"), **header)
    session.add(po)
    session.flush()
    _write_po_lines(session, po, lines, pins)
    sod.record_action(session, "purchase_order", po.id, "po.order.create", user.id)
    return po


def _write_po_lines(session: Session, po: PurchaseOrder, lines: list[dict], pins: dict) -> None:
    for old in session.execute(select(PurchaseOrderLine).where(PurchaseOrderLine.po_id == po.id)).scalars():
        session.delete(old)
    session.flush()
    for i, (ln, pin) in enumerate(zip(lines, pins["lines"]), 1):
        mat = session.get(Material, ln["material_id"])
        session.add(PurchaseOrderLine(po_id=po.id, line_no=i, material_id=ln["material_id"],
                                      specification_id=pin["specification_id"], vendor_material_id=pin["vendor_material_id"],
                                      pr_line_id=ln.get("pr_line_id"), quantity=ln["quantity"],
                                      unit_id=ln.get("unit_id") or mat.base_unit_id, rate=ln["rate"],
                                      tax_pct=ln.get("tax_pct", 0), delivery_date=ln.get("delivery_date"),
                                      remarks=ln.get("remarks")))
    session.flush()


def _po_lines_as_dicts(session: Session, po: PurchaseOrder) -> list[dict]:
    return [{"line_no": l.line_no, "material_id": l.material_id, "quantity": l.quantity, "rate": l.rate,
             "tax_pct": l.tax_pct, "unit_id": l.unit_id, "pr_line_id": l.pr_line_id, "delivery_date": l.delivery_date,
             "remarks": l.remarks}
            for l in session.execute(select(PurchaseOrderLine).where(PurchaseOrderLine.po_id == po.id)
                                     .order_by(PurchaseOrderLine.line_no)).scalars()]


def replace_po_lines(session: Session, po: PurchaseOrder, user: User, lines: list[dict]) -> None:
    if po.status != "DRAFT":
        raise BusinessRuleError("Only a DRAFT purchase order can be edited", rule_id="BR-HIS-001")
    vio, pins = evaluate_po(session, vendor_id=po.vendor_id, lines=lines, stage="CREATE", user_id=user.id,
                            header={"po_date": po.po_date, "delivery_date": po.delivery_date})
    assert_allowed(session, vio, stage="EDIT", vendor_id=po.vendor_id, po_ref=po.po_no)
    _write_po_lines(session, po, lines, pins)
    po.validation_snapshot = _snapshot_json(vio, "EDIT")


def submit_po(session: Session, po: PurchaseOrder, user: User) -> list[Violation]:
    if po.status != "DRAFT":
        raise BusinessRuleError("Only a DRAFT purchase order can be submitted", rule_id="BR-HIS-001")
    lines = _po_lines_as_dicts(session, po)
    vio, pins = evaluate_po(session, vendor_id=po.vendor_id, lines=lines, stage="SUBMIT", user_id=user.id,
                            header={"po_date": po.po_date, "delivery_date": po.delivery_date})
    assert_allowed(session, vio, stage="SUBMIT", vendor_id=po.vendor_id, po_ref=po.po_no)
    # re-pin to the versions in force now (PO is still DRAFT, so this is a controlled, audited update)
    for l, pin in zip(session.execute(select(PurchaseOrderLine).where(PurchaseOrderLine.po_id == po.id)
                                      .order_by(PurchaseOrderLine.line_no)).scalars(), pins["lines"]):
        l.specification_id, l.vendor_material_id = pin["specification_id"], pin["vendor_material_id"]
    po.vendor_qualification_id = pins["qualification_id"]
    po.validation_snapshot = _snapshot_json(vio, "SUBMIT")
    session.flush()   # persist re-pinned lines while the PO is still DRAFT
    inst = approval.start(session, "po.order", "purchase_order", po.id, user)
    po.workflow_instance_id = inst.id
    transition(session, PO_MACHINE, po, "PENDING_APPROVAL", module="purchase")
    return vio


def act_po(session: Session, po: PurchaseOrder, user: User, decision: str, comment: str | None, password: str | None) -> list[Violation]:
    if po.status != "PENDING_APPROVAL":
        raise BusinessRuleError(f"PO is {po.status}; nothing to approve", rule_id="WF-002")
    vio: list[Violation] = []
    if decision == "APPROVE":
        # BR-PO-007: creator cannot approve (checked by the workflow engine via SoD) and the gate is re-run
        vio, pins = evaluate_po(session, vendor_id=po.vendor_id, lines=_po_lines_as_dicts(session, po), stage="APPROVE",
                                user_id=user.id, header={"po_date": po.po_date, "delivery_date": po.delivery_date})
        assert_allowed(session, vio, stage="APPROVE", vendor_id=po.vendor_id, po_ref=po.po_no)
    inst = session.get(WorkflowInstance, po.workflow_instance_id)
    # NB: authentication / SoD checks happen inside act(); no writes may precede them (independent-session
    # security events would otherwise contend with this transaction's locks).
    approval.act(session, inst, user, decision, password=password, comment=comment, record_snapshot=po_snapshot(session, po))
    if decision == "APPROVE":
        po.vendor_qualification_id = pins["qualification_id"]
        po.validation_snapshot = _snapshot_json(vio, "APPROVE")
    if inst.status == "APPROVED":
        sig = session.execute(select(WorkflowTransaction.signature_id).where(
            WorkflowTransaction.instance_id == inst.id, WorkflowTransaction.decision == "APPROVE")
            .order_by(WorkflowTransaction.id.desc())).scalars().first()
        transition(session, PO_MACHINE, po, "APPROVED", reason=comment, signature_id=sig, module="purchase")
    elif inst.status == "REJECTED":
        transition(session, PO_MACHINE, po, "REJECTED", reason=comment, module="purchase")
    return vio


def cancel_po(session: Session, po: PurchaseOrder, user: User, reason: str, password: str | None) -> None:
    if not (reason or "").strip():
        raise ValidationFailed("A reason is required", code="REASON_REQUIRED")
    received = session.execute(select(func.coalesce(func.sum(PurchaseOrderLine.received_quantity), 0))
                               .where(PurchaseOrderLine.po_id == po.id)).scalar()
    if received and Decimal(str(received)) > 0:
        raise BusinessRuleError("Material has already been received against this PO", rule_id="BR-PO-011")
    if po.status == "DRAFT":
        transition(session, PO_MACHINE, po, "CANCELLED", reason=reason, module="purchase")
    else:
        masters.sign_and_transition(session, po, PO_MACHINE, "CANCELLED", user, password or "", reason=reason,
                                    meaning="APPROVED_BY")
        _cancel_instance(session, po.workflow_instance_id, user, reason)
    po.cancel_reason = reason
    for l in session.execute(select(PurchaseOrderLine).where(PurchaseOrderLine.po_id == po.id)).scalars():
        if l.pr_line_id:  # release the PR line so it can be re-ordered
            prl = session.get(PurchaseRequestLine, l.pr_line_id)
            if prl is not None:
                prl.po_line_id = None


def create_po_from_pr(session: Session, user: User, pr: PurchaseRequest, header: dict, line_inputs: list[dict]) -> PurchaseOrder:
    if pr.status != "APPROVED":
        raise BusinessRuleError("Only an APPROVED purchase request can be converted", rule_id="BR-PR-001")
    pr_lines = {l.id: l for l in session.execute(select(PurchaseRequestLine).where(PurchaseRequestLine.pr_id == pr.id)).scalars()}
    lines = []
    for li in line_inputs:
        prl = pr_lines.get(li["pr_line_id"])
        if prl is None:
            raise ValidationFailed("pr_line_id does not belong to this request")
        if prl.po_line_id:
            raise BusinessRuleError(f"PR line {prl.line_no} is already on a purchase order", rule_id="BR-PR-003")
        lines.append({"pr_line_id": prl.id, "material_id": prl.material_id, "quantity": prl.quantity,
                      "unit_id": prl.unit_id, "rate": li["rate"], "tax_pct": li.get("tax_pct", 0),
                      "delivery_date": prl.required_date})
    po = create_po(session, user, header, lines, pr)
    for pol in session.execute(select(PurchaseOrderLine).where(PurchaseOrderLine.po_id == po.id)).scalars():
        if pol.pr_line_id:
            pr_lines[pol.pr_line_id].po_line_id = pol.id
    session.flush()
    if all(l.po_line_id for l in pr_lines.values()):
        transition(session, PR_MACHINE, pr, "CONVERTED", reason=f"all lines on {po.po_no}", module="purchase")
    return po
