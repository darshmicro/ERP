"""Version control for GMP masters (spec 59/60): STP, specification, sampling plan.

* Only DRAFT versions are editable; approved versions are immutable (hook-enforced, BR-HIS-001).
* Approval = QA e-signature, author != approver; approving version N supersedes version N-1.
* `version_in_force` returns the version valid at a given instant, so historical transactions can
  always be shown against the version that applied at the time.
"""
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import Session

from app.core.errors import BusinessRuleError, Conflict, ValidationFailed
from app.core.time import utcnow
from app.models.spec import STP, SamplingPlan, Specification, SpecificationParameter
from app.services import masters, numbering
from app.workflows.state_machine import StateMachine, Transition, transition

VERSION_MACHINE_BASE = {
    "DRAFT": {"UNDER_REVIEW": Transition("UNDER_REVIEW")},
    "UNDER_REVIEW": {"DRAFT": Transition("DRAFT", requires_reason=True)},
    "APPROVED": {"SUPERSEDED": Transition("SUPERSEDED")},
}


def _machine(name: str, approve_perm: str) -> StateMachine:
    t = {k: dict(v) for k, v in VERSION_MACHINE_BASE.items()}
    t["UNDER_REVIEW"]["APPROVED"] = Transition("APPROVED", approve_perm, "QA_APPROVED", True)
    return StateMachine(name, "DRAFT", t)


KINDS: dict[type, dict[str, Any]] = {
    Specification: {"key": "spec_no", "doc_type": "SPEC", "prefix": "spec",
                    "machine": _machine("specification", "md.spec.approve"), "children": [(SpecificationParameter, "specification_id")]},
    STP: {"key": "stp_no", "doc_type": "STP", "prefix": "stp", "machine": _machine("stp", "md.stp.approve")},
    SamplingPlan: {"key": "plan_no", "doc_type": "SPLAN", "prefix": "sampling_plan",
                   "machine": _machine("sampling_plan", "md.sampling_plan.approve")},
}
_SKIP_COPY = {"id", "created_at", "created_by_id", "updated_at", "updated_by_id", "row_version", "status",
              "version_no", "effective_from", "effective_to", "approved_signature_id", "supersedes_id",
              "change_reason"}


def machine_for(obj_or_cls) -> StateMachine:
    cls = obj_or_cls if isinstance(obj_or_cls, type) else type(obj_or_cls)
    return KINDS[cls]["machine"]


def create_draft(session: Session, Model, data: dict, key_value: str | None = None):
    k = KINDS[Model]
    key = key_value or numbering.next_number(session, numbering.default_plant_id(session), k["doc_type"])
    if session.execute(select(Model.id).where(getattr(Model, k["key"]) == key)).first():
        raise Conflict(f"{k['key']} '{key}' already exists; create a new version of it instead")
    masters.check_foreign_keys(session, Model, data)
    obj = Model(**{k["key"]: key}, version_no=1, status="DRAFT", **data)
    session.add(obj)
    session.flush()
    masters.record_author(session, obj, f"{k['prefix']}.author")
    return obj


def _children(session: Session, C, fk: str, parent_id: int) -> list:
    return list(session.execute(select(C).where(getattr(C, fk) == parent_id).order_by(C.seq)).scalars())


def parameters(session: Session, spec: Specification) -> list[SpecificationParameter]:
    return list(session.execute(select(SpecificationParameter).where(
        SpecificationParameter.specification_id == spec.id).order_by(SpecificationParameter.seq)).scalars())


def validate_for_submission(session: Session, obj) -> None:
    if isinstance(obj, Specification):
        params = parameters(session, obj)
        if not params:
            raise ValidationFailed("A specification needs at least one test parameter before submission")
        for p in params:
            if p.spec_type in ("NUMERIC", "RANGE") and p.lsl is None and p.usl is None:
                raise ValidationFailed(f"Parameter '{p.test_name}': numeric tests need an LSL and/or USL")
            if p.stp_id:
                stp = session.get(STP, p.stp_id)
                if stp is None or stp.status != "APPROVED":
                    raise ValidationFailed(f"Parameter '{p.test_name}': referenced STP must be APPROVED")
    if isinstance(obj, SamplingPlan):
        if obj.sampling_rule == "FIXED" and not obj.fixed_qty:
            raise ValidationFailed("FIXED sampling plan needs fixed_qty")
        if obj.sampling_rule == "PERCENT" and not obj.percent:
            raise ValidationFailed("PERCENT sampling plan needs percent")
    if isinstance(obj, STP) and not (obj.procedure or "").strip():
        raise ValidationFailed("An STP needs a procedure before submission")
    v = KINDS[type(obj)].get("validate")
    if v:
        v(session, obj)


def submit(session: Session, obj) -> None:
    validate_for_submission(session, obj)
    transition(session, machine_for(obj), obj, "UNDER_REVIEW", module="quality_master")


def return_to_draft(session: Session, obj, reason: str) -> None:
    transition(session, machine_for(obj), obj, "DRAFT", reason=reason, module="quality_master")


def approve(session: Session, obj, user, password: str, reason: str) -> None:
    from app.services import quality_system
    quality_system.assert_change_control(session, obj)          # BR-CC-001 (configurable)
    k = KINDS[type(obj)]
    previous = session.execute(select(type(obj)).where(
        getattr(type(obj), k["key"]) == getattr(obj, k["key"]), type(obj).status == "APPROVED",
        type(obj).id != obj.id)).scalars().all()
    extra = {"children": [masters.snapshot(c) for C, fk in k.get("children", []) for c in _children(session, C, fk, obj.id)]} if k.get("children") else None
    sig = masters.sign_and_transition(session, obj, k["machine"], "APPROVED", user, password, reason=reason,
                                meaning="QA_APPROVED", sod_action=f"{k['prefix']}.approve", extra=extra)
    now = utcnow()
    for p in previous:
        p.effective_to = now
        transition(session, k["machine"], p, "SUPERSEDED", reason=f"superseded by v{obj.version_no}",
                   module="quality_master")
    obj.effective_from = now
    obj.approved_signature_id = sig.id


def new_version(session: Session, obj, reason: str):
    """Controlled change: copy an APPROVED version into a new DRAFT (v+1)."""
    if not (reason or "").strip():
        raise ValidationFailed("A change reason is required to create a new version", code="REASON_REQUIRED")
    Model, k = type(obj), KINDS[type(obj)]
    if obj.status != "APPROVED":
        raise BusinessRuleError("Only the currently APPROVED version can be revised", rule_id="BR-HIS-001")
    open_ = session.execute(select(Model.id).where(getattr(Model, k["key"]) == getattr(obj, k["key"]),
                                                   Model.status.in_(("DRAFT", "UNDER_REVIEW")))).first()
    if open_:
        raise Conflict("A newer draft/under-review version already exists for this record")
    latest = session.execute(select(Model.version_no).where(getattr(Model, k["key"]) == getattr(obj, k["key"]))
                             .order_by(Model.version_no.desc())).scalars().first()
    cols = {a.key: getattr(obj, a.key) for a in sa_inspect(Model).column_attrs if a.key not in _SKIP_COPY}
    new = Model(**cols, version_no=latest + 1, status="DRAFT", supersedes_id=obj.id, change_reason=reason)
    session.add(new)
    session.flush()
    for C, fk in k.get("children", []):
        for ch in _children(session, C, fk, obj.id):
            ccols = {a.key: getattr(ch, a.key) for a in sa_inspect(C).column_attrs if a.key not in _SKIP_COPY and a.key != fk}
            session.add(C(**ccols, **{fk: new.id}))
    session.flush()
    masters.record_author(session, new, f"{k['prefix']}.author")
    return new


def history(session: Session, obj) -> list:
    Model, k = type(obj), KINDS[type(obj)]
    return list(session.execute(select(Model).where(getattr(Model, k["key"]) == getattr(obj, k["key"]))
                                .order_by(Model.version_no)).scalars())


def version_in_force(session: Session, Model, *filters, on: datetime | None = None):
    """The APPROVED/SUPERSEDED version whose effective window contains `on` (default: now)."""
    on = on or utcnow()
    q = select(Model).where(*filters, Model.effective_from.is_not(None), Model.effective_from <= on,
                            (Model.effective_to.is_(None)) | (Model.effective_to > on)).order_by(Model.version_no.desc())
    return session.execute(q).scalars().first()


def current_spec_for_material(session: Session, material_id: int, on: datetime | None = None):
    return version_in_force(session, Specification, Specification.material_id == material_id, on=on)


def register_bom() -> None:
    from app.models.manufacturing import BOMHeader, BOMLine, MBRStep
    KINDS[BOMHeader] = {"key": "bom_no", "doc_type": "BOM", "prefix": "bom", "machine": _machine("bom_header", "md.bom.approve"),
                        "children": [(BOMLine, "bom_id"), (MBRStep, "bom_id")]}


def register_sop() -> None:
    from app.models.quality import SOP
    KINDS[SOP] = {"key": "sop_no", "doc_type": "SOP", "prefix": "sop", "machine": _machine("sop", "quality.sop.approve"), "children": []}


def register_phase11() -> None:
    from app.models.costing import CostRateCard
    from app.models.em import EMLimit, EMLimitSet
    from app.models.stability import StabilityCondition, StabilityProtocol, StabilityTimepoint
    from app.services import em, stability
    KINDS[EMLimitSet] = {"key": "limitset_no", "doc_type": "EMLIM", "prefix": "em_limit_set", "machine": _machine("em_limit_set", "em.limit.approve"),
                         "children": [(EMLimit, "limit_set_id")], "validate": em.validate_limit_set}
    KINDS[StabilityProtocol] = {"key": "protocol_no", "doc_type": "STABPROT", "prefix": "stability_protocol", "machine": _machine("stability_protocol", "stability.protocol.approve"),
                                "children": [(StabilityCondition, "protocol_id"), (StabilityTimepoint, "protocol_id")], "validate": stability.validate_protocol}
    KINDS[CostRateCard] = {"key": "card_no", "doc_type": "COSTCARD", "prefix": "cost_rate_card", "machine": _machine("cost_rate_card", "costing.rate.approve"), "children": []}


register_bom()
register_sop()
register_phase11()
