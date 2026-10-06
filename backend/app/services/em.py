"""Environmental monitoring (Phase 11a): limits, sampling, results, excursions, trending.

Limits come from the APPROVED limit set in force at the sampling time; the alert/action values are
copied onto the sample so a later limit-set revision never re-judges history. A result above the
action limit raises a deviation automatically; results that are corrected keep the original value in
an append-only amendment table. Reference limits shipped with the system are EU GMP Annex 1 (2022)
style values that the site must verify before approving them.
"""
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import BusinessRuleError, Conflict, ValidationFailed
from app.core.time import utcnow
from app.models.em import (EMIsolate, EMLimit, EMLimitSet, EMLocation, EMPlan, EMResultAmendment, EMSample, GRADES, SAMPLE_TYPES, STATES)
from app.models.master import Equipment
from app.services import config_service, masters, notifications, numbering, quality_system as qs, sod, stats, versioning
from app.services import master_services as ms
from app.workflows.state_machine import StateMachine, Transition as T, transition

D = Decimal

SAMPLE_MACHINE = StateMachine("em_sample", "SAMPLED", {
    "SAMPLED": {"RESULT_ENTERED": T("RESULT_ENTERED", "em.sample.enter"), "CANCELLED": T("CANCELLED", "em.sample.enter", requires_reason=True)},
    "RESULT_ENTERED": {"REVIEWED": T("REVIEWED", "em.sample.review", "REVIEWED_BY", True)},
})

# Reference values only (EU GMP Annex 1, 2022 style). The site must verify them against its own
# contamination control strategy before approving a limit set.
# (grade, sample_type, state, alert_high, action_high, unit)
ANNEX1_REFERENCE = [
    ("A", "VIABLE_AIR", "OPERATIONAL", None, 0, "cfu/m3"), ("B", "VIABLE_AIR", "OPERATIONAL", 5, 10, "cfu/m3"),
    ("C", "VIABLE_AIR", "OPERATIONAL", 50, 100, "cfu/m3"), ("D", "VIABLE_AIR", "OPERATIONAL", 100, 200, "cfu/m3"),
    ("A", "SETTLE_PLATE", "OPERATIONAL", None, 0, "cfu/4h"), ("B", "SETTLE_PLATE", "OPERATIONAL", 3, 5, "cfu/4h"),
    ("C", "SETTLE_PLATE", "OPERATIONAL", 25, 50, "cfu/4h"), ("D", "SETTLE_PLATE", "OPERATIONAL", 50, 100, "cfu/4h"),
    ("A", "CONTACT_PLATE", "OPERATIONAL", None, 0, "cfu/plate"), ("B", "CONTACT_PLATE", "OPERATIONAL", 3, 5, "cfu/plate"),
    ("C", "CONTACT_PLATE", "OPERATIONAL", 13, 25, "cfu/plate"), ("D", "CONTACT_PLATE", "OPERATIONAL", 25, 50, "cfu/plate"),
    ("A", "GLOVE_PRINT", "OPERATIONAL", None, 0, "cfu/glove"), ("B", "GLOVE_PRINT", "OPERATIONAL", 3, 5, "cfu/glove"),
    ("A", "NONVIABLE_05", "AT_REST", None, 3520, "particles/m3"), ("B", "NONVIABLE_05", "AT_REST", None, 3520, "particles/m3"),
    ("C", "NONVIABLE_05", "AT_REST", None, 352000, "particles/m3"), ("D", "NONVIABLE_05", "AT_REST", None, 3520000, "particles/m3"),
    ("A", "NONVIABLE_05", "OPERATIONAL", None, 3520, "particles/m3"), ("B", "NONVIABLE_05", "OPERATIONAL", None, 352000, "particles/m3"),
    ("C", "NONVIABLE_05", "OPERATIONAL", None, 3520000, "particles/m3"),
    ("B", "NONVIABLE_5", "AT_REST", None, 29, "particles/m3"), ("C", "NONVIABLE_5", "AT_REST", None, 2930, "particles/m3"),
    ("D", "NONVIABLE_5", "AT_REST", None, 29300, "particles/m3"), ("B", "NONVIABLE_5", "OPERATIONAL", None, 2930, "particles/m3"),
    ("C", "NONVIABLE_5", "OPERATIONAL", None, 29300, "particles/m3"),
]


# ------------------------------------------------------------------ limit sets
def create_limit_set(session: Session, data: dict, limits: list[dict] | None = None, key: str | None = None) -> EMLimitSet:
    ls = versioning.create_draft(session, EMLimitSet, data, key)
    for i, lim in enumerate(limits or [], 1):
        add_limit(session, ls, lim, seq=i)
    return ls


def load_reference_limits(session: Session, title: str = "EU GMP Annex 1 reference limits (to be verified by the site)") -> EMLimitSet:
    rows = [{"grade": g, "sample_type": t, "state": st, "alert_high": a, "action_high": ac, "unit": u} for g, t, st, a, ac, u in ANNEX1_REFERENCE]
    return create_limit_set(session, {"title": title, "basis": "Reference values; site verification and QA approval required before use"}, rows)


def add_limit(session: Session, ls: EMLimitSet, data: dict, seq: int | None = None) -> EMLimit:
    if ls.status != "DRAFT":
        raise BusinessRuleError("Limits can only be changed while the limit set is DRAFT", rule_id="BR-HIS-001")
    if data["grade"] not in GRADES or data["sample_type"] not in SAMPLE_TYPES or data.get("state", "OPERATIONAL") not in STATES:
        raise ValidationFailed("Unknown grade, sample type or state")
    vals = {k: data.get(k) for k in ("alert_high", "action_high", "alert_low", "action_low")}
    if all(v is None for v in vals.values()):
        raise ValidationFailed("A limit needs at least one alert/action value")
    if vals["alert_high"] is not None and vals["action_high"] is not None and D(str(vals["alert_high"])) > D(str(vals["action_high"])):
        raise ValidationFailed("Alert limit cannot exceed the action limit")
    if vals["alert_low"] is not None and vals["action_low"] is not None and D(str(vals["alert_low"])) < D(str(vals["action_low"])):
        raise ValidationFailed("Low alert limit cannot be below the low action limit")
    if seq is None:
        seq = (session.execute(select(func.max(EMLimit.seq)).where(EMLimit.limit_set_id == ls.id)).scalar() or 0) + 1
    row = EMLimit(limit_set_id=ls.id, seq=seq, grade=data["grade"], sample_type=data["sample_type"], state=data.get("state", "OPERATIONAL"),
                  unit=data.get("unit"), **vals)
    session.add(row)
    session.flush()
    return row


def validate_limit_set(session: Session, ls: EMLimitSet) -> None:
    n = session.execute(select(func.count()).select_from(EMLimit).where(EMLimit.limit_set_id == ls.id)).scalar()
    if not n:
        raise ValidationFailed("A limit set needs at least one limit before submission")


def limit_for(session: Session, grade: str, sample_type: str, state: str, on: datetime | None = None) -> tuple[EMLimitSet, EMLimit]:
    ls = versioning.version_in_force(session, EMLimitSet, on=on)
    if ls is None:
        raise BusinessRuleError("No APPROVED environmental-monitoring limit set is in force", rule_id="BR-EM-001")
    lim = session.execute(select(EMLimit).where(EMLimit.limit_set_id == ls.id, EMLimit.grade == grade, EMLimit.sample_type == sample_type,
                                                EMLimit.state == state)).scalars().first()
    if lim is None:
        raise BusinessRuleError(f"Limit set {ls.limitset_no} v{ls.version_no} has no limit for grade {grade} / {sample_type} / {state}", rule_id="BR-EM-001")
    return ls, lim


# ------------------------------------------------------------------ masters
def create_location(session: Session, data: dict) -> EMLocation:
    masters.check_foreign_keys(session, EMLocation, data)
    code = data.get("code") or numbering.next_number(session, numbering.default_plant_id(session), "EMLOC")
    if session.execute(select(EMLocation.id).where(EMLocation.code == code)).first():
        raise Conflict(f"EM location '{code}' already exists")
    loc = EMLocation(**{**data, "code": code})
    session.add(loc)
    session.flush()
    return loc


def create_plan(session: Session, data: dict) -> EMPlan:
    loc = session.get(EMLocation, data["em_location_id"])
    if loc is None or not loc.is_active:
        raise ValidationFailed("Unknown or inactive monitoring location")
    if data["sample_type"] not in SAMPLE_TYPES or data.get("state", "OPERATIONAL") not in STATES:
        raise ValidationFailed("Unknown sample type or state")
    if session.execute(select(EMPlan.id).where(EMPlan.em_location_id == loc.id, EMPlan.sample_type == data["sample_type"],
                                               EMPlan.state == data.get("state", "OPERATIONAL"))).first():
        raise Conflict("A plan for this location, sample type and state already exists")
    plan = EMPlan(**{"state": "OPERATIONAL", **data})
    session.add(plan)
    session.flush()
    return plan


# ------------------------------------------------------------------ sampling
def create_sample(session: Session, user, data: dict) -> EMSample:
    loc = session.get(EMLocation, data["em_location_id"])
    if loc is None or not loc.is_active:
        raise ValidationFailed("Unknown or inactive monitoring location")
    if data["sample_type"] not in SAMPLE_TYPES or data.get("state", "OPERATIONAL") not in STATES:
        raise ValidationFailed("Unknown sample type or state")
    if data.get("equipment_id"):
        eq = session.get(Equipment, data["equipment_id"])
        if eq is None:
            raise ValidationFailed("Unknown instrument")
        ok, why = ms.usable_for_testing(eq)
        if not ok:
            raise BusinessRuleError(f"Instrument {eq.equipment_code} cannot be used: {why} (BR-QC-002)", rule_id="BR-QC-002")
    masters.check_foreign_keys(session, EMSample, data)
    plan_id = data.get("plan_id")
    if plan_id:
        plan = session.get(EMPlan, plan_id)
        if plan is None or plan.em_location_id != loc.id or plan.sample_type != data["sample_type"]:
            raise ValidationFailed("Plan does not match the location / sample type")
    s = EMSample(sample_no=numbering.next_number(session, numbering.default_plant_id(session), "EMSAMPLE"), status="SAMPLED", sampled_by_id=user.id,
                 grade=loc.grade, **{"state": "OPERATIONAL", **data})
    session.add(s)
    session.flush()
    return s


def judge(value: D, lim) -> str:
    """lim has alert/action high/low attributes (EMLimit or EMSample snapshot)."""
    def gt(a):
        return a is not None and value > D(str(a))

    def lt(a):
        return a is not None and value < D(str(a))
    if gt(lim.action_high) or lt(lim.action_low):
        return "ACTION"
    if gt(lim.alert_high) or lt(lim.alert_low):
        return "ALERT"
    return "WITHIN"


def _apply_outcome(session: Session, s: EMSample, user_id: int) -> None:
    loc = session.get(EMLocation, s.em_location_id)
    if s.outcome == "ACTION" and s.deviation_id is None:
        sev = "CRITICAL" if s.grade in ("A", "B") else "MAJOR"
        d = qs.raise_deviation(session, user_id, title=f"EM action limit exceeded: {loc.code} {s.sample_type} ({s.sample_no})",
                               description=f"{s.sample_type} result {s.result_value} {s.result_unit or ''} at {loc.code} ({loc.name}), grade {s.grade}, exceeds the action limit "
                                           f"(alert {s.alert_high}/{s.alert_low}, action {s.action_high}/{s.action_low}).",
                               category="ENVIRONMENT", severity=sev, source="EM", entity_type="MFG_BATCH" if s.manufacturing_batch_id else None,
                               record_id=s.manufacturing_batch_id, blocks_release=bool(s.manufacturing_batch_id))
        s.deviation_id = d.id
    elif s.outcome == "ALERT":
        notifications.notify_roles(session, [r.strip() for r in config_service.get(session, "em.alert_notify_roles").split(",") if r.strip()], category="EM_ALERT", title=f"EM alert limit exceeded: {loc.code} {s.sample_type}",
                                   body=f"{s.sample_no}: {s.result_value} {s.result_unit or ''}", ref_entity="em_sample", ref_id=str(s.id))


def enter_result(session: Session, s: EMSample, user, value, unit: str | None = None, isolates: list[dict] | None = None) -> EMSample:
    if s.status != "SAMPLED":
        raise BusinessRuleError(f"Sample is {s.status}; a result can only be entered once (use an amendment before review)", rule_id="BR-EM-002")
    if value is None or D(str(value)) < 0:
        raise ValidationFailed("A non-negative result is required")
    loc = session.get(EMLocation, s.em_location_id)
    ls, lim = limit_for(session, loc.grade, s.sample_type, s.state)
    s.grade, s.limit_set_id = loc.grade, ls.id
    s.alert_high, s.action_high, s.alert_low, s.action_low = lim.alert_high, lim.action_high, lim.alert_low, lim.action_low
    s.result_value, s.result_unit = D(str(value)), unit or lim.unit
    s.outcome = judge(s.result_value, lim)
    s.entered_by_id, s.entered_at = user.id, utcnow()
    transition(session, SAMPLE_MACHINE, s, "RESULT_ENTERED", module="em")
    sod.record_action(session, "em_sample", s.id, "em.result.enter", user.id)
    for iso in isolates or []:
        add_isolate(session, s, user, iso)
    _apply_outcome(session, s, user.id)
    return s


def amend_result(session: Session, s: EMSample, user, value, reason: str) -> EMSample:
    if s.status != "RESULT_ENTERED":
        raise BusinessRuleError("A result can only be amended after entry and before QA review", rule_id="BR-EM-002")
    if not (reason or "").strip():
        raise ValidationFailed("A reason is required to amend a result", code="REASON_REQUIRED")
    if value is None or D(str(value)) < 0:
        raise ValidationFailed("A non-negative result is required")
    old_v, old_o = s.result_value, s.outcome
    s.result_value = D(str(value))
    s.outcome = judge(s.result_value, s)
    session.add(EMResultAmendment(sample_id=s.id, old_value=old_v, new_value=s.result_value, old_outcome=old_o, new_outcome=s.outcome, reason=reason, user_id=user.id))
    _apply_outcome(session, s, user.id)
    return s


def add_isolate(session: Session, s: EMSample, user, data: dict) -> EMIsolate:
    if s.status not in ("SAMPLED", "RESULT_ENTERED"):
        raise BusinessRuleError("Organisms can only be recorded before QA review", rule_id="BR-EM-002")
    if not (data.get("organism") or "").strip():
        raise ValidationFailed("Organism name is required")
    iso = EMIsolate(sample_id=s.id, identified_by_id=user.id, **data)
    session.add(iso)
    session.flush()
    return iso


def review(session: Session, s: EMSample, user, password: str, reason: str, comment: str | None = None) -> None:
    if s.status != "RESULT_ENTERED":
        raise BusinessRuleError(f"Sample is {s.status}; only an entered result can be reviewed", rule_id="BR-EM-002")
    if s.outcome == "ACTION" and s.deviation_id is None:
        raise BusinessRuleError("An action-limit result needs a deviation before review", rule_id="BR-EM-003")
    sod.check(session, user.id, "em_sample", s.id, "em.sample.review")
    s.review_comment = comment
    sig = masters.sign_and_transition(session, s, SAMPLE_MACHINE, "REVIEWED", user, password, reason=reason, meaning="REVIEWED_BY", sod_action="em.sample.review")
    s.reviewed_by_id, s.reviewed_at, s.review_signature_id = user.id, utcnow(), sig.id


def cancel(session: Session, s: EMSample, reason: str) -> None:
    if not (reason or "").strip():
        raise ValidationFailed("A reason is required", code="REASON_REQUIRED")
    s.cancel_reason = reason
    transition(session, SAMPLE_MACHINE, s, "CANCELLED", reason=reason, module="em")


# ------------------------------------------------------------------ schedule / trend
def schedule(session: Session, horizon_days: int = 7, today: date | None = None) -> list[dict]:
    today = today or date.today()
    out = []
    plans = session.execute(select(EMPlan, EMLocation).join(EMLocation, EMLocation.id == EMPlan.em_location_id)
                            .where(EMPlan.is_active == True, EMLocation.is_active == True)).all()  # noqa: E712
    for plan, loc in plans:
        last = session.execute(select(func.max(EMSample.sampled_at)).where(EMSample.plan_id == plan.id, EMSample.status != "CANCELLED")).scalar()
        due = plan.start_date if last is None else last.date() + timedelta(days=plan.frequency_days)
        if due <= today + timedelta(days=horizon_days):
            out.append({"plan_id": plan.id, "em_location_id": loc.id, "location_code": loc.code, "location_name": loc.name, "grade": loc.grade,
                        "sample_type": plan.sample_type, "state": plan.state, "due_date": due.isoformat(), "overdue": due < today,
                        "last_sampled": last.date().isoformat() if last else None})
    return sorted(out, key=lambda r: (r["due_date"], r["location_code"]))


def trend(session: Session, em_location_id: int, sample_type: str, state: str = "OPERATIONAL", days: int = 365) -> dict:
    since = utcnow() - timedelta(days=days)
    rows = session.execute(select(EMSample).where(EMSample.em_location_id == em_location_id, EMSample.sample_type == sample_type, EMSample.state == state,
                                                  EMSample.result_value.is_not(None), EMSample.status != "CANCELLED", EMSample.sampled_at >= since)
                           .order_by(EMSample.sampled_at)).scalars().all()
    values = [float(r.result_value) for r in rows]
    out = {"n": len(values), "points": [{"sample_no": r.sample_no, "sampled_at": r.sampled_at.isoformat(), "value": float(r.result_value), "outcome": r.outcome} for r in rows],
           "alerts": sum(1 for r in rows if r.outcome == "ALERT"), "actions": sum(1 for r in rows if r.outcome == "ACTION"),
           "stats": stats.describe(values), "signals": []}
    lim = stats.control_limits(values)
    if lim and lim["sigma"] > 0:
        out["control_limits"] = lim
        out["signals"] = stats.nelson_rules(values, lim["cl"], lim["sigma"])
        out["note"] = "Indicative only: count data are rarely normal; the site's trending procedure decides on action."
    return out


def excursions(session: Session, days: int = 30) -> list[EMSample]:
    since = utcnow() - timedelta(days=days)
    return list(session.execute(select(EMSample).where(EMSample.outcome.in_(("ALERT", "ACTION")), EMSample.status != "CANCELLED", EMSample.sampled_at >= since)
                                .order_by(EMSample.sampled_at.desc())).scalars())


def daily_alerts(session: Session) -> int:
    """Notify QC of overdue monitoring points (idempotent: identical unread notices are not repeated)."""
    n = 0
    for r in schedule(session, 0):
        if r["overdue"]:
            n += notifications.notify_roles(session, ["QC_HEAD", "QC_ANALYST"], category="EM_DUE", title=f"EM sampling overdue: {r['location_code']} {r['sample_type']}",
                                            body=f"Due {r['due_date']}", ref_entity="em_plan", ref_id=str(r["plan_id"]))
    return n
