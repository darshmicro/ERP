"""QC / LIMS: sampling, tests, results, amendments, OOS/OOT, release workflow, conditional release (spec 23-30, 71)."""
import math
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit import service as audit
from app.audit.context import get_context
from app.core.errors import (BusinessRuleError, NotFound, PermissionDenied, SegregationOfDutiesError, ValidationFailed)
from app.core.time import utcnow
from app.models.audit import RecordAction
from app.models.master import Equipment, Material, MaterialType, Unit
from app.models.platform import WorkflowInstance, WorkflowTransaction
from app.models.qc import (ConditionalRelease, OOSInvestigation, OOTEvent, QCResult, QCResultAmendment, QCTest, Sample)
from app.models.spec import STP, SamplingPlan, Specification, SpecificationParameter
from app.models.warehouse import InventoryBalance, MaterialBatch
from app.security.permissions import effective_permissions
from app.services import config_service, inventory, lots, masters, notifications, numbering, sod, stats, versioning
from app.services import master_services as ms
from app.workflows import approval
from app.workflows.state_machine import StateMachine, Transition, transition

T = Transition
D = Decimal
SAMPLE_MACHINE = StateMachine("sample", "CREATED", {
    "CREATED": {"TESTING": T("TESTING")},
    "TESTING": {"COMPLETED": T("COMPLETED"), "TESTING": T("TESTING")},
    "COMPLETED": {"RETAINED": T("RETAINED"), "TESTING": T("TESTING")},
    "RETAINED": {"DISPOSED": T("DISPOSED", "qc.sample.dispose", "APPROVED_BY", True)},
})
TEST_MACHINE = StateMachine("qc_test", "ASSIGNED", {
    "ASSIGNED": {"STARTED": T("STARTED"), "SUBMITTED": T("SUBMITTED"), "INVALIDATED": T("INVALIDATED")},
    "STARTED": {"SUBMITTED": T("SUBMITTED"), "INVALIDATED": T("INVALIDATED")},
    "SUBMITTED": {"INVALIDATED": T("INVALIDATED", "oos.investigation.decide", "APPROVED_BY", True)},
})
RESULT_MACHINE = StateMachine("qc_result", "DRAFT", {"DRAFT": {"SUBMITTED": T("SUBMITTED")}})
AMEND_MACHINE = StateMachine("qc_result_amendment", "REQUESTED", {
    "REQUESTED": {"APPROVED": T("APPROVED", "qc.result.amend_approve", "APPROVED_BY", True),
                  "REJECTED": T("REJECTED", "qc.result.amend_approve", "REJECTED_BY", True)}})
OOS_MACHINE = StateMachine("oos_investigation", "RAISED", {
    "RAISED": {"PHASE1": T("PHASE1")}, "PHASE1": {"PHASE2": T("PHASE2"), "DECIDED": T("DECIDED", "oos.investigation.decide", "QA_APPROVED", True)},
    "PHASE2": {"DECIDED": T("DECIDED", "oos.investigation.decide", "QA_APPROVED", True)}, "DECIDED": {"CLOSED": T("CLOSED")}})
CR_MACHINE = StateMachine("conditional_release", "REQUESTED", {
    "REQUESTED": {"APPROVED": T("APPROVED", "conditional_release.request.approve", "QA_APPROVED", True),
                  "REJECTED": T("REJECTED", "conditional_release.request.approve", "REJECTED_BY", True)},
    "APPROVED": {"CLOSED": T("CLOSED"), "EXPIRED": T("EXPIRED")}})


def _plant(s: Session) -> int:
    return numbering.default_plant_id(s)


# ================================================================== sampling
def required_sampling(session: Session, lot: MaterialBatch, plan: SamplingPlan | None) -> dict:
    from app.models.warehouse import MaterialContainer
    n = session.execute(select(func.count()).select_from(MaterialContainer).where(MaterialContainer.batch_id == lot.id)).scalar() or 1
    rule = plan.sampling_rule if plan else "SQRT_N_PLUS_1"
    min_c, min_q = 1, D(0)
    if rule == "SQRT_N_PLUS_1":
        min_c = min(n, math.ceil(math.sqrt(n)) + 1)
    elif rule == "ALL":
        min_c = n
    elif rule == "FIXED" and plan and plan.fixed_qty:
        min_q = plan.fixed_qty
    elif rule == "PERCENT" and plan and plan.percent:
        min_q = lot.quantity * plan.percent / 100
    return {"rule": rule, "containers_total": n, "min_containers": min_c, "min_quantity": float(min_q)}


def create_sample(session: Session, user, lot: MaterialBatch, qty: D, containers: int, location_id: int, remarks: str | None,
                  sample_type: str = "RM_SAMPLE") -> Sample:
    if lot.disposition not in ("QUARANTINE", "QC_TESTING"):
        raise BusinessRuleError(f"Lot {lot.lot_no} is {lot.disposition}; samples are taken from quarantined lots", rule_id="BR-SMP-001")
    qty = D(str(qty))
    plan = versioning.version_in_force(session, SamplingPlan, SamplingPlan.material_id == lot.material_id)
    need = required_sampling(session, lot, plan)
    if containers < need["min_containers"] or containers > need["containers_total"]:
        raise BusinessRuleError(f"Sampling plan ({need['rule']}) requires at least {need['min_containers']} of "
                                f"{need['containers_total']} containers to be sampled", rule_id="BR-SMP-002", details=need)
    if qty < D(str(need["min_quantity"])):
        raise BusinessRuleError(f"Sampling plan requires at least {need['min_quantity']} to be sampled", rule_id="BR-SMP-002", details=need)
    if lot.specification_id is None:
        spec = versioning.current_spec_for_material(session, lot.material_id)
        if spec is None:
            raise BusinessRuleError("No approved specification exists for this material (BR-QC-001)", rule_id="BR-QC-001")
        lot.specification_id = spec.id
    if plan and lot.sampling_plan_id is None:
        lot.sampling_plan_id = plan.id
    sm = Sample(sample_no=numbering.next_number(session, _plant(session), "SAMPLE"), sample_type=sample_type, material_batch_id=lot.id,
                specification_id=lot.specification_id, sampling_plan_id=plan.id if plan else None, quantity_received=lot.quantity,
                quantity_sampled=qty, unit_id=lot.unit_id, containers_sampled=containers, sampling_location_id=location_id,
                sampled_by_id=user.id, remarks=remarks, status="CREATED")
    session.add(sm)
    session.flush()
    inventory.post(session, txn_type="SAMPLE", batch=lot, quantity=qty, from_location_id=location_id, ref_doc_type="SAMPLE", ref_doc_id=sm.sample_no)
    if lot.disposition == "QUARANTINE":
        transition(session, lots.LOT_MACHINE, lot, "QC_TESTING", reason=f"Sample {sm.sample_no} taken", module="warehouse")
    sod.record_action(session, "sample", sm.id, "qc.sample.create", user.id)
    return sm


# ================================================================== tests
def assign_tests(session: Session, sample: Sample, analyst_id: int | None, parameter_ids: list[int] | None = None) -> list[QCTest]:
    if sample.specification_id is None:
        raise BusinessRuleError("The sample has no specification; tests cannot be assigned", rule_id="BR-QC-001")
    params = versioning.parameters(session, session.get(Specification, sample.specification_id))
    if parameter_ids is not None:
        params = [p for p in params if p.id in set(parameter_ids)]
    existing = {t.spec_parameter_id for t in session.execute(select(QCTest).where(QCTest.sample_id == sample.id, QCTest.status != "INVALIDATED")).scalars()}
    out = []
    for p in params:
        if p.id in existing:
            continue
        t = QCTest(sample_id=sample.id, spec_parameter_id=p.id, test_name=p.test_name, stp_id=p.stp_id, analyst_id=analyst_id, status="ASSIGNED")
        session.add(t)
        out.append(t)
    session.flush()
    if sample.status == "CREATED" and out:
        transition(session, SAMPLE_MACHINE, sample, "TESTING", reason="Tests assigned", module="qc")
    return out


def start_test(session: Session, test: QCTest, user, equipment_id: int | None) -> None:
    if test.analyst_id and test.analyst_id != user.id:
        raise PermissionDenied("This test is assigned to another analyst")
    if test.stp_id:
        stp = session.get(STP, test.stp_id)
        if stp is None or stp.status != "APPROVED":
            raise BusinessRuleError("The STP version referenced by the specification is not currently APPROVED (BR-QC-003); "
                                    "the specification must be revised to the current STP", rule_id="BR-QC-003")
    if equipment_id:
        eq = session.get(Equipment, equipment_id)
        if eq is None:
            raise ValidationFailed("Unknown equipment")
        ok, why = ms.usable_for_testing(eq)
        test.equipment_id, test.calibration_status = eq.id, ms.calibration_status(eq)
        if not ok and not config_service.get_bool(session, "calibration.override_allowed", False):
            raise BusinessRuleError(f"Instrument {eq.equipment_code} cannot be used: {why} (BR-QC-002)", rule_id="BR-QC-002")
    test.started_at = utcnow()
    test.analyst_id = test.analyst_id or user.id
    transition(session, TEST_MACHINE, test, "STARTED", module="qc")


def override_calibration(session: Session, test: QCTest, user, password: str, reason: str) -> None:
    """Configured, QA-signed exception for an instrument with expired calibration (decision C-14)."""
    from app.services import esign
    if not config_service.get_bool(session, "calibration.override_allowed", False):
        raise BusinessRuleError("Calibration overrides are not enabled (calibration.override_allowed)", rule_id="BR-QC-002")
    if test.equipment_id is None:
        raise ValidationFailed("The test has no instrument")
    sig = esign.sign(session, user, password, meaning="APPROVED_BY", entity="qc_test", record_id=test.id, record_snapshot={"test": test.id, "eq": test.equipment_id},
                     reason=reason, required_permission="qc.test.override_calibration")
    test.calibration_override_signature_id = sig.id


def evaluate(spec_type: str, lsl, usl, decimals, value: Any = None, conforms: bool | None = None) -> tuple[D | None, str]:
    if spec_type in ("NUMERIC", "RANGE"):
        if value is None:
            raise ValidationFailed("A numeric result is required")
        v = D(str(value))
        r = v.quantize(D(1).scaleb(-decimals), rounding=ROUND_HALF_UP) if decimals is not None else v
        ok = (lsl is None or r >= lsl) and (usl is None or r <= usl)
        return r, "PASS" if ok else "FAIL"
    if conforms is None:
        raise ValidationFailed("'conforms' (true/false) is required for this test")
    return None, "PASS" if conforms else "FAIL"


def enter_result(session: Session, test: QCTest, user, *, value=None, text: str | None = None, conforms: bool | None = None,
                 remarks: str | None = None) -> QCResult:
    if test.status not in ("ASSIGNED", "STARTED"):
        raise BusinessRuleError(f"Test is {test.status}; a result cannot be entered (submitted results are immutable)", rule_id="BR-QC-005")
    if test.analyst_id and test.analyst_id != user.id:
        raise PermissionDenied("This test is assigned to another analyst")
    sample = session.get(Sample, test.sample_id)
    lot = session.get(MaterialBatch, sample.material_batch_id) if sample.material_batch_id else None
    p = session.get(SpecificationParameter, test.spec_parameter_id)
    if test.equipment_id:   # BR-QC-002 re-checked at completion
        eq = session.get(Equipment, test.equipment_id)
        ok, why = ms.usable_for_testing(eq)
        if not ok and test.calibration_override_signature_id is None:
            raise BusinessRuleError(f"Instrument {eq.equipment_code} cannot be used: {why} (BR-QC-002)", rule_id="BR-QC-002")
    rounded, pf = evaluate(p.spec_type, p.lsl, p.usl, p.decimal_places, value, conforms)
    r = QCResult(test_id=test.id, spec_type=p.spec_type, value_numeric=D(str(value)) if value is not None else None, rounded_value=rounded,
                 value_text=text if text is not None else (("Conforms" if conforms else "Does not conform") if conforms is not None else None),
                 unit=p.unit, lsl=p.lsl, usl=p.usl, target=p.target, decimal_places=p.decimal_places, acceptance_criteria=p.acceptance_criteria,
                 pass_fail=pf, remarks=remarks, status="DRAFT", entered_by_id=user.id)
    session.add(r)
    session.flush()
    test.completed_at = utcnow()
    test.analyst_id = user.id
    transition(session, RESULT_MACHINE, r, "SUBMITTED", module="qc")      # submitted => locked (BR-QC-005)
    transition(session, TEST_MACHINE, test, "SUBMITTED", module="qc")
    if lot is not None:
        sod.record_action(session, "material_batch", lot.id, "qc.result.enter", user.id)
    if pf == "FAIL":
        raise_oos(session, r, test, sample, lot)
    elif p.spec_type in ("NUMERIC", "RANGE") and lot is not None:
        evaluate_oot(session, r, test, lot, p)
    open_ = session.execute(select(func.count()).select_from(QCTest).where(QCTest.sample_id == sample.id, QCTest.status.in_(("ASSIGNED", "STARTED")))).scalar()
    if not open_ and sample.status == "TESTING":
        transition(session, SAMPLE_MACHINE, sample, "COMPLETED", reason="All tests submitted", module="qc")
    return r


# ================================================================== effective values / amendments
def effective(session: Session, r: QCResult) -> dict:
    a = session.execute(select(QCResultAmendment).where(QCResultAmendment.result_id == r.id, QCResultAmendment.status == "APPROVED")
                        .order_by(QCResultAmendment.id.desc())).scalars().first()
    if a is None:
        return {"value": r.rounded_value if r.rounded_value is not None else r.value_text, "pass_fail": r.pass_fail, "amended": False}
    return {"value": a.new_value, "pass_fail": a.new_pass_fail, "amended": True, "amendment_id": a.id, "original": a.original_value}


def request_amendment(session: Session, user, r: QCResult, new_value: Any, conforms: bool | None, reason: str) -> QCResultAmendment:
    if not (reason or "").strip():
        raise ValidationFailed("A reason is required", code="REASON_REQUIRED")
    if r.status != "SUBMITTED":
        raise BusinessRuleError("Only submitted results can be amended", rule_id="BR-QC-005")
    if session.execute(select(QCResultAmendment.id).where(QCResultAmendment.result_id == r.id, QCResultAmendment.status == "REQUESTED")).first():
        raise BusinessRuleError("An amendment is already pending for this result", rule_id="BR-QC-005")
    rounded, pf = evaluate(r.spec_type, r.lsl, r.usl, r.decimal_places, new_value, conforms)
    cur = effective(session, r)
    a = QCResultAmendment(result_id=r.id, original_value=str(cur["value"]), new_value=str(rounded if rounded is not None else (new_value if new_value is not None else conforms)),
                          new_pass_fail=pf, reason=reason, status="REQUESTED", requested_by_id=user.id)
    session.add(a)
    session.flush()
    sod.record_action(session, "qc_result_amendment", a.id, "qc.amendment.request", user.id)
    return a


def decide_amendment(session: Session, a: QCResultAmendment, user, password: str, approve: bool, comment: str) -> None:
    sod.check(session, user.id, "qc_result_amendment", a.id, "qc.amendment.approve")
    sig = masters.sign_and_transition(session, a, AMEND_MACHINE, "APPROVED" if approve else "REJECTED", user, password, reason=comment,
                                      meaning="APPROVED_BY" if approve else "REJECTED_BY")
    a.approved_by_id, a.approved_signature_id, a.decided_at, a.decision_comment = user.id, sig.id, utcnow(), comment
    sod.record_action(session, "qc_result_amendment", a.id, "qc.amendment.approve", user.id)
    if approve:
        r = session.get(QCResult, a.result_id)
        test = session.get(QCTest, r.test_id)
        sample = session.get(Sample, test.sample_id)
        lot = session.get(MaterialBatch, sample.material_batch_id) if sample.material_batch_id else None
        if a.new_pass_fail == "FAIL" and lot is not None and not session.execute(select(OOSInvestigation.id).where(OOSInvestigation.qc_result_id == r.id)).first():
            raise_oos(session, r, test, sample, lot)


# ================================================================== OOS / OOT
def raise_oos(session: Session, r: QCResult, test: QCTest, sample: Sample, lot: MaterialBatch | None) -> OOSInvestigation:
    no = numbering.next_number(session, _plant(session), "OOS")
    o = OOSInvestigation(oos_no=no, qc_result_id=r.id, qc_test_id=test.id, sample_id=sample.id, material_batch_id=lot.id if lot else None,
                         description=f"{test.test_name}: result {r.rounded_value if r.rounded_value is not None else r.value_text} "
                                     f"{r.unit or ''} outside specification (LSL {r.lsl}, USL {r.usl})", status="RAISED")
    session.add(o)
    session.flush()
    if lot is not None:
        h = lots.place_hold(session, "MATERIAL_BATCH", lot.id, f"OOS {no}: {test.test_name}", source="OOS", ref=no, user_id=get_context().user_id)
        o.hold_id = h.id
    notifications.notify_roles(session, ["QC_HEAD", "QA_OFFICER", "QA_HEAD"], category="OOS", title=f"OOS raised {no}", body=o.description,
                               ref_entity="oos_investigation", ref_id=str(o.id))
    return o


def oos_investigate(session: Session, o: OOSInvestigation, phase: str, findings: str) -> None:
    if not (findings or "").strip():
        raise ValidationFailed("Findings are required", code="REASON_REQUIRED")
    if phase == "PHASE1":
        o.phase1_findings = findings
        if o.status == "RAISED":
            transition(session, OOS_MACHINE, o, "PHASE1", reason="Phase I laboratory investigation", module="qc")
    else:
        if o.status != "PHASE1":
            raise BusinessRuleError("Phase II follows Phase I", rule_id="OOS-001")
        o.phase2_findings = findings
        transition(session, OOS_MACHINE, o, "PHASE2", reason="Phase II full-scale investigation", module="qc")


def oos_decide(session: Session, o: OOSInvestigation, user, password: str, decision: str, root_cause: str, capa_ref: str | None, reason: str) -> None:
    """QA decision. INVALIDATED (assignable lab error) permits a retest; CONFIRMED_FAIL rejects the lot."""
    if decision not in ("CONFIRMED_FAIL", "INVALIDATED"):
        raise ValidationFailed("decision must be CONFIRMED_FAIL or INVALIDATED")
    if o.status not in ("PHASE1", "PHASE2"):
        raise BusinessRuleError("Complete the investigation phases before a decision", rule_id="OOS-001")
    if not (root_cause or "").strip():
        raise ValidationFailed("Root cause is required", code="REASON_REQUIRED")
    sig = masters.sign_and_transition(session, o, OOS_MACHINE, "DECIDED", user, password, reason=reason, meaning="QA_APPROVED")
    o.decision, o.decision_reason, o.root_cause, o.capa_ref, o.decided_by_id, o.decision_signature_id = decision, reason, root_cause, capa_ref, user.id, sig.id
    lot = session.get(MaterialBatch, o.material_batch_id) if o.material_batch_id else None
    test = session.get(QCTest, o.qc_test_id)
    if decision == "INVALIDATED":
        transition(session, TEST_MACHINE, test, "INVALIDATED", user_permissions=effective_permissions(session, user.id), reason="OOS invalidated: " + root_cause,
                   signature_id=sig.id, module="qc")
    elif lot is not None and lot.disposition in ("QC_TESTING", "QA_REVIEW", "QC_APPROVED", "QUARANTINE"):
        transition(session, lots.LOT_MACHINE, lot, "REJECTED", reason=f"OOS {o.oos_no} confirmed", signature_id=sig.id, module="warehouse")
    if o.hold_id:
        from app.models.warehouse import QualityHold
        h = session.get(QualityHold, o.hold_id)
        if h and h.status == "OPEN":
            h.released_by_id, h.released_at, h.release_reason, h.release_signature_id = user.id, utcnow(), f"OOS {o.oos_no} decided: {decision}", sig.id
            transition(session, StateMachine("quality_hold", "OPEN", {"OPEN": {"RELEASED": T("RELEASED")}}), h, "RELEASED",
                       reason=f"OOS {o.oos_no} decided: {decision}", signature_id=sig.id, module="quality")
    transition(session, OOS_MACHINE, o, "CLOSED", reason="Decision recorded", module="qc")
    o.closed_at = utcnow()


def retest(session: Session, test: QCTest, user) -> QCTest:
    if test.status != "INVALIDATED":
        raise BusinessRuleError("A retest is only permitted for an invalidated test", rule_id="OOS-002")
    n = QCTest(sample_id=test.sample_id, spec_parameter_id=test.spec_parameter_id, test_name=test.test_name, stp_id=test.stp_id,
               analyst_id=None, status="ASSIGNED", retest_of_id=test.id)
    session.add(n)
    session.flush()
    sample = session.get(Sample, test.sample_id)
    if sample.status == "COMPLETED":
        transition(session, SAMPLE_MACHINE, sample, "TESTING", reason="Retest assigned", module="qc")
    return n


def history_values(session: Session, material_id: int, test_name: str, *, vendor_id: int | None = None, date_from=None, date_to=None) -> list[dict]:
    q = (select(QCResult, QCTest, Sample, MaterialBatch).join(QCTest, QCTest.id == QCResult.test_id).join(Sample, Sample.id == QCTest.sample_id)
         .join(MaterialBatch, MaterialBatch.id == Sample.material_batch_id)
         .where(MaterialBatch.material_id == material_id, QCTest.test_name == test_name, QCResult.status == "SUBMITTED",
                QCResult.rounded_value.is_not(None), QCTest.status == "SUBMITTED"))
    if vendor_id:
        q = q.where(MaterialBatch.vendor_id == vendor_id)
    if date_from:
        q = q.where(QCResult.entered_at >= date_from)
    if date_to:
        q = q.where(QCResult.entered_at <= date_to)
    out = []
    for r, t, sm, lot in session.execute(q.order_by(QCResult.entered_at, QCResult.id)).all():
        e = effective(session, r)
        v = float(e["value"]) if e["amended"] else float(r.rounded_value)
        out.append({"result_id": r.id, "value": v, "at": r.entered_at, "lot_no": lot.lot_no, "vendor_id": lot.vendor_id, "pass_fail": e["pass_fail"],
                    "lsl": float(r.lsl) if r.lsl is not None else None, "usl": float(r.usl) if r.usl is not None else None})
    return out


def evaluate_oot(session: Session, r: QCResult, test: QCTest, lot: MaterialBatch, p: SpecificationParameter) -> list[OOTEvent]:
    found: list[tuple[str, str]] = []
    v = float(r.rounded_value)
    if p.action_high is not None and v > float(p.action_high) or p.action_low is not None and v < float(p.action_low):
        found.append(("ACTION_LIMIT", f"{v} outside action limits ({p.action_low}–{p.action_high})"))
    elif p.alert_high is not None and v > float(p.alert_high) or p.alert_low is not None and v < float(p.alert_low):
        found.append(("ALERT_LIMIT", f"{v} outside alert limits ({p.alert_low}–{p.alert_high})"))
    hist = [h["value"] for h in history_values(session, lot.material_id, test.test_name)]
    min_trend = int(config_service.get(session, "stats.min_n_trend", "10") or 10)
    if len(hist) >= min_trend:
        cl = stats.control_limits(hist)
        enabled = [int(x) for x in (config_service.get(session, "stats.nelson_rules", "1,2,3,5,6") or "").split(",") if x.strip()]
        for v_ in stats.nelson_rules(hist, cl["cl"], cl["sigma"], enabled):
            if v_["index"] == len(hist) - 1:
                found.append((f"NELSON_{v_['rule']}", v_["text"]))
    events = []
    for rule, detail in found:
        e = OOTEvent(oot_no=numbering.next_number(session, _plant(session), "OOT"), qc_result_id=r.id, material_id=lot.material_id,
                     test_name=test.test_name, rule=rule, detail=detail)
        session.add(e)
        events.append(e)
    if events:
        session.flush()
        notifications.notify_roles(session, ["QC_HEAD", "QA_OFFICER"], category="OOT", title=f"OOT: {test.test_name} ({lot.lot_no})",
                                   body="; ".join(d for _r, d in found), ref_entity="oot_event", ref_id=str(events[0].id))
    return events      # NB: OOT never changes lot disposition unless an approved business rule says so (spec 27)


# ================================================================== release workflow
RELEASE_PROCESSES = ("material.release", "fg.release")


def release_process(session: Session, lot: MaterialBatch) -> str:
    mat = session.get(Material, lot.material_id)
    t = session.get(MaterialType, mat.type_id)
    return "fg.release" if t.code == "FG" else "material.release"


def _lot_results(session: Session, lot: MaterialBatch) -> list[tuple[QCTest, QCResult | None]]:
    rows = session.execute(select(QCTest, QCResult).join(Sample, Sample.id == QCTest.sample_id)
                           .outerjoin(QCResult, QCResult.test_id == QCTest.id).where(Sample.material_batch_id == lot.id, QCTest.status != "INVALIDATED")).all()
    return [(t, r) for t, r in rows]


def release_readiness(session: Session, lot: MaterialBatch) -> list[str]:
    problems = []
    if lot.disposition != "QC_TESTING":
        problems.append(f"Lot is {lot.disposition}; release review starts from QC_TESTING")
    from app.services import manufacturing
    problems += manufacturing.conditional_material_problems(session, lot)
    from app.services import quality_system
    problems += [f"{m} (BR-DEV-001)" for _, m in quality_system.deviation_blockers(session, lot)]
    if lot.specification_id is None:
        problems.append("No specification pinned to the lot")
        return problems
    params = versioning.parameters(session, session.get(Specification, lot.specification_id))
    rows = _lot_results(session, lot)
    by_param = {t.spec_parameter_id: (t, r) for t, r in rows}
    for p in params:
        t_r = by_param.get(p.id)
        if t_r is None:
            problems.append(f"Test not assigned: {p.test_name}")
        elif t_r[1] is None or t_r[0].status != "SUBMITTED":
            problems.append(f"Result pending: {p.test_name}")
        elif effective(session, t_r[1])["pass_fail"] != "PASS":
            problems.append(f"Result failed: {p.test_name}")
    if session.execute(select(func.count()).select_from(OOSInvestigation).where(OOSInvestigation.material_batch_id == lot.id, OOSInvestigation.status != "CLOSED")).scalar():
        problems.append("Open OOS investigation")
    if lots.has_open_hold(session, "MATERIAL_BATCH", lot.id):
        problems.append("Lot is on quality hold")
    if lot.grn_line_id:
        from app.models.warehouse import GRNLine
        gl = session.get(GRNLine, lot.grn_line_id)
        if gl is not None and not gl.coa_received:
            problems.append("Vendor CoA was not received (BR-REL-002)")
    if lot.expiry_date and lot.expiry_date < date.today():
        problems.append("Lot is expired")
    return problems


def submit_for_release(session: Session, lot: MaterialBatch, user) -> WorkflowInstance:
    problems = release_readiness(session, lot)
    if problems:
        raise BusinessRuleError("Not ready for release: " + "; ".join(problems), rule_id="BR-REL-001", details=problems)
    proc = release_process(session, lot)
    if session.execute(select(WorkflowInstance.id).where(WorkflowInstance.entity == "material_batch", WorkflowInstance.record_id == str(lot.id),
                                                         WorkflowInstance.status == "IN_PROGRESS")).first():
        raise BusinessRuleError("A release review is already in progress", rule_id="BR-REL-001")
    inst = approval.start(session, proc, "material_batch", lot.id, user)
    return inst


def active_release(session: Session, lot: MaterialBatch) -> WorkflowInstance | None:
    return session.execute(select(WorkflowInstance).where(WorkflowInstance.entity == "material_batch", WorkflowInstance.record_id == str(lot.id),
                                                          WorkflowInstance.status == "IN_PROGRESS")).scalars().first()


def lot_snapshot(session: Session, lot: MaterialBatch) -> dict:
    res = []
    for t, r in _lot_results(session, lot):
        if r is not None:
            e = effective(session, r)
            res.append({"test": t.test_name, "value": str(e["value"]), "pass_fail": e["pass_fail"], "result_id": r.id})
    return {**masters.snapshot(lot), "results": sorted(res, key=lambda x: x["test"])}


def _advance(session: Session, lot: MaterialBatch, target: str, signature_id: int | None, reason: str) -> None:
    path = ["QC_TESTING", "QC_APPROVED", "QA_REVIEW", "APPROVED"]
    while lot.disposition != target and lot.disposition in path and path.index(lot.disposition) < path.index(target):
        nxt = path[path.index(lot.disposition) + 1]
        transition(session, lots.LOT_MACHINE, lot, nxt, reason=reason, signature_id=signature_id, module="warehouse")


def act_release(session: Session, lot: MaterialBatch, user, decision: str, comment: str | None, password: str | None) -> WorkflowInstance:
    inst = active_release(session, lot)
    if inst is None:
        raise BusinessRuleError("No release review is in progress for this lot", rule_id="WF-002")
    if session.execute(select(RecordAction.id).where(RecordAction.entity == "material_batch", RecordAction.record_id == str(lot.id),
                                                      RecordAction.action_code == "qc.result.enter", RecordAction.user_id == user.id)).first():
        from app.models.master import Material as _M
        raise SegregationOfDutiesError("SOD-02/03: you entered results for this lot and cannot review or release it.", rule_id="SOD-02")
    if decision == "APPROVE":
        problems = release_readiness(session, lot) if lot.disposition == "QC_TESTING" else []
        problems = [p for p in problems if not p.startswith("Lot is ")]   # in-chain states are expected
        if problems:
            raise BusinessRuleError("Not ready for release: " + "; ".join(problems), rule_id="BR-REL-001", details=problems)
        if lots.has_open_hold(session, "MATERIAL_BATCH", lot.id):
            raise BusinessRuleError("Lot is on quality hold", rule_id="BR-HOLD-004")
    snap = lot_snapshot(session, lot)
    approval.act(session, inst, user, decision, password=password, comment=comment, record_snapshot=snap)
    sig = session.execute(select(WorkflowTransaction.signature_id).where(WorkflowTransaction.instance_id == inst.id, WorkflowTransaction.decision == decision)
                          .order_by(WorkflowTransaction.id.desc())).scalars().first()
    from app.services import manufacturing
    if inst.status == "REJECTED":
        transition(session, lots.LOT_MACHINE, lot, "REJECTED", reason=comment, signature_id=sig, module="warehouse")
        manufacturing.on_lot_released(session, lot, "REJECTED")
    elif inst.status == "APPROVED":
        _advance(session, lot, "APPROVED", sig, comment or "Released")
        lot.qa_release_no = numbering.next_number(session, _plant(session), "QARELEASE")
        lot.released_at, lot.release_signature_id = utcnow(), sig
        if not lot.qc_no:
            lot.qc_no = numbering.next_number(session, _plant(session), "QCNO")
        from app.services import coa as coa_svc
        coa_svc.generate(session, lot, user, "Issued at QA release", sig)
        manufacturing.on_lot_released(session, lot, "APPROVED")
    elif inst.current_seq == 2:
        if not lot.qc_no:
            lot.qc_no = numbering.next_number(session, _plant(session), "QCNO")
        _advance(session, lot, "QC_APPROVED", sig, comment or "QC review complete")
    elif inst.current_seq >= 3:
        _advance(session, lot, "QA_REVIEW", sig, comment or "Verified")
    return inst


# ================================================================== conditional release
def request_conditional_release(session: Session, user, lot: MaterialBatch, qty: D, intended_batch_ref: str, justification: str,
                                risk_ref: str, identity_confirmed: bool, expires_at: date) -> ConditionalRelease:
    if lot.disposition not in lots.UNRELEASED:
        raise BusinessRuleError(f"Conditional release applies to unreleased lots only (lot is {lot.disposition})", rule_id="BR-CRL-002")
    if lots.has_open_hold(session, "MATERIAL_BATCH", lot.id):
        raise BusinessRuleError("A lot on quality hold cannot be conditionally released", rule_id="BR-CRL-002")
    if session.execute(select(func.count()).select_from(OOSInvestigation).where(OOSInvestigation.material_batch_id == lot.id, OOSInvestigation.status != "CLOSED")).scalar():
        raise BusinessRuleError("A lot with an open OOS investigation cannot be conditionally released", rule_id="BR-CRL-002")
    if lot.expiry_date and lot.expiry_date < date.today():
        raise BusinessRuleError("Expired material cannot be conditionally released", rule_id="BR-CRL-002")
    if not identity_confirmed:
        raise ValidationFailed("Material identity must be confirmed before conditional release")
    if expires_at <= date.today():
        raise ValidationFailed("The authorisation must expire in the future")
    for fld, val in (("justification", justification), ("risk assessment reference", risk_ref), ("intended batch", intended_batch_ref)):
        if not (val or "").strip():
            raise ValidationFailed(f"{fld} is required", code="REASON_REQUIRED")
    if D(str(qty)) > inventory.on_hand(session, lot.id):
        raise BusinessRuleError("Quantity exceeds stock of the lot", rule_id="BR-INV-002")
    cr = ConditionalRelease(cr_no=numbering.next_number(session, _plant(session), "CRELEASE"), material_batch_id=lot.id, quantity_authorised=qty,
                            intended_batch_ref=intended_batch_ref, justification=justification, risk_assessment_ref=risk_ref,
                            identity_confirmed=True, expires_at=expires_at, status="REQUESTED", requested_by_id=user.id)
    session.add(cr)
    session.flush()
    sod.record_action(session, "conditional_release", cr.id, "conditional_release.request", user.id)
    return cr


def decide_conditional_release(session: Session, cr: ConditionalRelease, user, password: str, approve: bool, comment: str) -> None:
    sod.check(session, user.id, "conditional_release", cr.id, "conditional_release.approve")
    sig = masters.sign_and_transition(session, cr, CR_MACHINE, "APPROVED" if approve else "REJECTED", user, password, reason=comment,
                                      meaning="QA_APPROVED" if approve else "REJECTED_BY")
    cr.approved_by_id, cr.approved_signature_id, cr.decided_at, cr.decision_comment = user.id, sig.id, utcnow(), comment
    sod.record_action(session, "conditional_release", cr.id, "conditional_release.approve", user.id)


def active_conditional_release(session: Session, lot: MaterialBatch, qty: D, today: date | None = None) -> ConditionalRelease | None:
    """Approved, unexpired authorisation with enough remaining quantity (used by material issue, Phase 6)."""
    today = today or date.today()
    if lot.disposition == "REJECTED":
        return None
    for cr in session.execute(select(ConditionalRelease).where(ConditionalRelease.material_batch_id == lot.id, ConditionalRelease.status == "APPROVED",
                                                               ConditionalRelease.expires_at >= today)).scalars():
        if cr.quantity_authorised - cr.quantity_used >= D(str(qty)):
            return cr
    return None


# ================================================================== sample retention & disposal
def retain(session: Session, sample: Sample, until: date) -> None:
    sample.retention_until = until
    transition(session, SAMPLE_MACHINE, sample, "RETAINED", reason=f"Retained until {until.isoformat()}", module="qc")


def dispose(session: Session, sample: Sample, user, password: str, reason: str) -> None:
    if sample.retention_until and sample.retention_until > date.today():
        raise BusinessRuleError(f"Retention period runs until {sample.retention_until.isoformat()}", rule_id="BR-SMP-003")
    sig = masters.sign_and_transition(session, sample, SAMPLE_MACHINE, "DISPOSED", user, password, reason=reason, meaning="APPROVED_BY")
    sample.disposal_approved_by_id, sample.disposal_signature_id, sample.disposed_at = user.id, sig.id, utcnow()
