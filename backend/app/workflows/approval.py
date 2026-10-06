"""Configurable approval-chain engine (spec 54, C-10).

Configuration (steps/roles/min approvals/e-signature/SLA/reject route) is data held in versioned,
QA-approved workflow definitions. Statuses themselves are code (state machines).
An instance is pinned to the definition version in force at submission.
"""
from datetime import timedelta
from typing import Any, Callable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit import service as audit
from app.audit.context import get_context
from app.core.errors import BusinessRuleError, NotFound, PermissionDenied, ValidationFailed
from app.core.time import utcnow
from app.models.iam import Role, User
from app.models.platform import (WorkflowDefinition, WorkflowInstance, WorkflowStep, WorkflowTransaction)
from app.security.permissions import active_role_codes
from app.services import esign, sod
from app.workflows.state_machine import StateMachine, Transition, transition

INSTANCE_MACHINE = StateMachine("workflow_instance", "IN_PROGRESS", {
    "IN_PROGRESS": {"APPROVED": Transition("APPROVED"), "REJECTED": Transition("REJECTED"),
                    "CANCELLED": Transition("CANCELLED")},
})
DEFINITION_MACHINE = StateMachine("workflow_definition", "DRAFT", {
    "DRAFT": {"APPROVED": Transition("APPROVED", "workflow.definition.approve", "APPROVED_BY", True)},
    "APPROVED": {"SUPERSEDED": Transition("SUPERSEDED")},
})

# process_code -> callback(session, instance) invoked when the chain completes (APPROVED / REJECTED)
_hooks: dict[tuple[str, str], Callable[[Session, WorkflowInstance], None]] = {}


def on_complete(process_code: str, outcome: str, fn: Callable[[Session, WorkflowInstance], None]) -> None:
    _hooks[(process_code, outcome)] = fn


def create_definition(session: Session, process_code: str, name: str, steps: list[dict]) -> WorkflowDefinition:
    if not steps:
        raise ValidationFailed("A workflow needs at least one step")
    seqs = [s["seq"] for s in steps]
    if sorted(seqs) != list(range(1, len(steps) + 1)):
        raise ValidationFailed("Step sequence numbers must be 1..N without gaps")
    ver = (session.execute(select(func.max(WorkflowDefinition.version_no))
                           .where(WorkflowDefinition.process_code == process_code)).scalar() or 0) + 1
    d = WorkflowDefinition(process_code=process_code, version_no=ver, name=name, status="DRAFT")
    session.add(d)
    session.flush()
    for st in steps:
        role = session.execute(select(Role).where(Role.role_code == st["role_code"])).scalar_one_or_none()
        if role is None:
            raise ValidationFailed(f"Unknown role '{st['role_code']}'")
        if st.get("meaning", "APPROVED_BY") not in esign.MEANINGS:
            raise ValidationFailed(f"Unknown signature meaning '{st.get('meaning')}'")
        session.add(WorkflowStep(definition_id=d.id, seq=st["seq"], name=st["name"], role_id=role.id,
                                 min_approvals=st.get("min_approvals", 1),
                                 esig_required=st.get("esig_required", True),
                                 meaning=st.get("meaning", "APPROVED_BY"), sla_hours=st.get("sla_hours"),
                                 reject_to_seq=st.get("reject_to_seq")))
    return d


def approve_definition(session: Session, definition: WorkflowDefinition, user: User, password: str,
                       reason: str, perms: set[str]) -> None:
    sod.check(session, user.id, "workflow_definition", definition.id, "workflow.definition.approve")
    snapshot = {"process": definition.process_code, "version": definition.version_no,
                "steps": [(s.seq, s.role_id, s.min_approvals, s.esig_required, s.meaning, s.sla_hours,
                           s.reject_to_seq) for s in session.execute(
                    select(WorkflowStep).where(WorkflowStep.definition_id == definition.id)
                    .order_by(WorkflowStep.seq)).scalars()]}
    sig = esign.sign(session, user, password, meaning="APPROVED_BY", entity="workflow_definition",
                     record_id=definition.id, record_version=definition.version_no, reason=reason,
                     record_snapshot=snapshot, required_permission="workflow.definition.approve")
    previous = session.execute(select(WorkflowDefinition).where(
        WorkflowDefinition.process_code == definition.process_code,
        WorkflowDefinition.status == "APPROVED")).scalars().all()
    for p in previous:
        transition(session, DEFINITION_MACHINE, p, "SUPERSEDED", reason="superseded by new version",
                   module="workflow")
    definition.approved_signature_id = sig.id
    definition.effective_from = utcnow()
    transition(session, DEFINITION_MACHINE, definition, "APPROVED", user_permissions=perms,
               reason=reason, signature_id=sig.id, module="workflow")


def freeze_steps_guard(session: Session, definition: WorkflowDefinition) -> None:
    if definition.status != "DRAFT":
        raise BusinessRuleError("Approved workflow versions are immutable; create a new version.",
                                rule_id="BR-HIS-001")


def _definition_for(session: Session, process_code: str) -> WorkflowDefinition:
    d = session.execute(select(WorkflowDefinition).where(
        WorkflowDefinition.process_code == process_code, WorkflowDefinition.status == "APPROVED")
        .order_by(WorkflowDefinition.version_no.desc())).scalars().first()
    if d is None:
        raise BusinessRuleError(f"No approved workflow is configured for '{process_code}'",
                                rule_id="WF-001")
    return d


def start(session: Session, process_code: str, entity: str, record_id: Any, user: User) -> WorkflowInstance:
    d = _definition_for(session, process_code)
    inst = WorkflowInstance(definition_id=d.id, process_code=process_code, entity=entity,
                            record_id=str(record_id), current_seq=1, initiated_by_id=user.id)
    session.add(inst)
    session.flush()
    session.add(WorkflowTransaction(instance_id=inst.id, seq=0, actor_id=user.id, decision="SUBMIT"))
    sod.record_action(session, entity, record_id, f"{process_code}.submit", user.id)
    audit.log_event(session, module="workflow", entity=entity, record_id=record_id, action="WORKFLOW_SUBMIT",
                    new=f"{process_code} v{d.version_no}")
    return inst


def _step(session: Session, inst: WorkflowInstance, seq: int) -> WorkflowStep:
    return session.execute(select(WorkflowStep).where(WorkflowStep.definition_id == inst.definition_id,
                                                      WorkflowStep.seq == seq)).scalar_one()


def current_step(session: Session, inst: WorkflowInstance) -> WorkflowStep:
    return _step(session, inst, inst.current_seq)


def act(session: Session, inst: WorkflowInstance, user: User, decision: str, *, password: str | None,
        comment: str | None, record_snapshot: Any) -> WorkflowInstance:
    if inst.status != "IN_PROGRESS":
        raise BusinessRuleError("Workflow is already completed.", rule_id="WF-002")
    if decision not in ("APPROVE", "REJECT"):
        raise ValidationFailed("decision must be APPROVE or REJECT")
    step = current_step(session, inst)
    role_codes = set(active_role_codes(session, user.id))
    role = session.get(Role, step.role_id)
    if role.role_code not in role_codes:
        raise PermissionDenied(f"This step requires role {role.role_code}.")
    action_code = f"{inst.process_code}.approve"
    sod.check(session, user.id, inst.entity, inst.record_id, action_code)
    prior = session.execute(select(func.count()).select_from(WorkflowTransaction).where(
        WorkflowTransaction.instance_id == inst.id, WorkflowTransaction.seq == step.seq,
        WorkflowTransaction.actor_id == user.id, WorkflowTransaction.decision == "APPROVE")).scalar()
    if prior:
        raise BusinessRuleError("You have already approved this step.", rule_id="WF-003")
    if decision == "APPROVE" and inst.process_code.endswith(".release"):
        other = session.execute(select(func.count()).select_from(WorkflowTransaction).where(
            WorkflowTransaction.instance_id == inst.id, WorkflowTransaction.actor_id == user.id,
            WorkflowTransaction.decision == "APPROVE")).scalar()
        if other:   # SOD-03: one person cannot be both the QC reviewer and the QA releaser
            raise BusinessRuleError("SOD-03: you already approved an earlier step of this release; a different person must release.", rule_id="SOD-03")
    sig_id = None
    if step.esig_required:
        meaning = step.meaning if decision == "APPROVE" else "REJECTED_BY"
        sig = esign.sign(session, user, password or "", meaning=meaning, entity=inst.entity,
                         record_id=inst.record_id, record_snapshot=record_snapshot, reason=comment)
        sig_id = sig.id
    session.add(WorkflowTransaction(instance_id=inst.id, seq=step.seq, actor_id=user.id, decision=decision,
                                    signature_id=sig_id, comment=comment))
    audit.log_event(session, module="workflow", entity=inst.entity, record_id=inst.record_id,
                    action=f"WORKFLOW_{decision}", field_name=f"step {step.seq}", new=step.name,
                    reason=comment, signature_id=sig_id)
    if decision == "APPROVE":
        sod.record_action(session, inst.entity, inst.record_id, action_code, user.id)
        n = session.execute(select(func.count()).select_from(WorkflowTransaction).where(
            WorkflowTransaction.instance_id == inst.id, WorkflowTransaction.seq == step.seq,
            WorkflowTransaction.decision == "APPROVE")).scalar()
        if n >= step.min_approvals:
            nxt = session.execute(select(func.min(WorkflowStep.seq)).where(
                WorkflowStep.definition_id == inst.definition_id, WorkflowStep.seq > step.seq)).scalar()
            if nxt is None:
                inst.completed_at = utcnow()
                transition(session, INSTANCE_MACHINE, inst, "APPROVED", reason=comment, module="workflow")
                _fire(session, inst, "APPROVED")
            else:
                inst.current_seq = nxt
                inst.step_started_at = utcnow()
    else:
        if step.reject_to_seq:
            inst.current_seq = step.reject_to_seq
            inst.step_started_at = utcnow()
        else:
            inst.completed_at = utcnow()
            transition(session, INSTANCE_MACHINE, inst, "REJECTED", reason=comment, module="workflow")
            _fire(session, inst, "REJECTED")
    return inst


def _fire(session: Session, inst: WorkflowInstance, outcome: str) -> None:
    fn = _hooks.get((inst.process_code, outcome))
    if fn:
        fn(session, inst)


def cancel(session: Session, inst: WorkflowInstance, user: User, reason: str) -> None:
    """Withdraw an in-progress approval (e.g. the underlying record is cancelled)."""
    if inst.status != "IN_PROGRESS":
        return
    session.add(WorkflowTransaction(instance_id=inst.id, seq=inst.current_seq, actor_id=user.id,
                                    decision="CANCEL", comment=reason))
    inst.completed_at = utcnow()
    transition(session, INSTANCE_MACHINE, inst, "CANCELLED", reason=reason, module="workflow")


def overdue_instances(session: Session) -> list[WorkflowInstance]:
    """SLA breach detection for the escalation job."""
    out = []
    for inst in session.execute(select(WorkflowInstance).where(WorkflowInstance.status == "IN_PROGRESS")).scalars():
        st = current_step(session, inst)
        if st.sla_hours and inst.step_started_at + timedelta(hours=st.sla_hours) < utcnow():
            out.append(inst)
    return out


def pending_for_user(session: Session, user_id: int) -> list[WorkflowInstance]:
    codes = set(active_role_codes(session, user_id))
    out = []
    for inst in session.execute(select(WorkflowInstance).where(WorkflowInstance.status == "IN_PROGRESS")).scalars():
        st = current_step(session, inst)
        role = session.get(Role, st.role_id)
        if role.role_code in codes and inst.initiated_by_id != user_id:
            out.append(inst)
    return out
