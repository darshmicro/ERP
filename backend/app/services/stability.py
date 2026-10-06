"""Stability studies (Phase 11b): protocol -> study -> scheduled pulls -> results -> evaluation -> QA conclusion.

* Protocols are versioned masters (QA e-signature); a study pins the exact protocol version it started on.
* Starting a study books the stability sample quantity out of the lot via the inventory ledger.
* Results are append-only; corrections add a superseding row with a reason.
* A failing result raises a deviation linked to the lot (so it blocks dispatch/release like any open deviation).
* The regression helper follows the ICH Q1E idea (one-sided 95 % confidence bound vs the specification limit,
  extrapolation capped); it is an aid to the QA decision, not an automatic shelf-life assignment, and it does not
  implement batch-pooling tests.
"""
import calendar
import math
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import BusinessRuleError, ValidationFailed
from app.core.time import utcnow
from app.models.master import Equipment, Location
from app.models.spec import Specification, SpecificationParameter
from app.models.stability import (StabilityCondition, StabilityProtocol, StabilityPull, StabilityResult, StabilityStudy, StabilityTimepoint)
from app.models.warehouse import MaterialBatch
from app.services import inventory, masters, numbering, quality_system as qs, sod, versioning
from app.services import master_services as ms
from app.services.qc import evaluate
from app.workflows.state_machine import StateMachine, Transition as T, transition

D = Decimal

STUDY_MACHINE = StateMachine("stability_study", "PLANNED", {
    "PLANNED": {"ACTIVE": T("ACTIVE", "stability.study.start"), "TERMINATED": T("TERMINATED", "stability.study.terminate", requires_reason=True)},
    "ACTIVE": {"COMPLETED": T("COMPLETED", "stability.study.update"), "TERMINATED": T("TERMINATED", "stability.study.terminate", requires_reason=True)},
    "COMPLETED": {"CONCLUDED": T("CONCLUDED", "stability.study.conclude", "QA_APPROVED", True)},
})
PULL_MACHINE = StateMachine("stability_pull", "SCHEDULED", {
    "SCHEDULED": {"PULLED": T("PULLED", "stability.pull.record"), "MISSED": T("MISSED"), "SKIPPED": T("SKIPPED", "stability.pull.skip", requires_reason=True)},
    "PULLED": {"TESTED": T("TESTED", "stability.result.enter")},
    "TESTED": {"REVIEWED": T("REVIEWED", "stability.pull.review", "REVIEWED_BY", True)},
})
OPEN_PULL = ("SCHEDULED", "PULLED", "TESTED")

# one-sided 95 % Student-t quantiles, df 1..30 (ICH Q1E style confidence bound)
_T95 = [6.314, 2.920, 2.353, 2.132, 2.015, 1.943, 1.895, 1.860, 1.833, 1.812, 1.796, 1.782, 1.771, 1.761, 1.753, 1.746, 1.740, 1.734, 1.729, 1.725,
        1.721, 1.717, 1.714, 1.711, 1.708, 1.706, 1.703, 1.701, 1.699, 1.697]


def add_months(d: date, m: int) -> date:
    y, mo = divmod(d.month - 1 + m, 12)
    y, mo = d.year + y, mo + 1
    return date(y, mo, min(d.day, calendar.monthrange(y, mo)[1]))


# ------------------------------------------------------------------ protocol
def add_condition(session: Session, p: StabilityProtocol, data: dict) -> StabilityCondition:
    if p.status != "DRAFT":
        raise BusinessRuleError("Conditions can only be changed while the protocol is DRAFT", rule_id="BR-HIS-001")
    masters.check_foreign_keys(session, StabilityCondition, data)
    seq = (session.execute(select(func.max(StabilityCondition.seq)).where(StabilityCondition.protocol_id == p.id)).scalar() or 0) + 1
    c = StabilityCondition(protocol_id=p.id, seq=seq, **data)
    session.add(c)
    session.flush()
    return c


def add_timepoint(session: Session, p: StabilityProtocol, data: dict) -> StabilityTimepoint:
    if p.status != "DRAFT":
        raise BusinessRuleError("Time points can only be changed while the protocol is DRAFT", rule_id="BR-HIS-001")
    if session.execute(select(StabilityTimepoint.id).where(StabilityTimepoint.protocol_id == p.id, StabilityTimepoint.month == data["month"])).first():
        raise ValidationFailed(f"Month {data['month']} is already a time point")
    seq = (session.execute(select(func.max(StabilityTimepoint.seq)).where(StabilityTimepoint.protocol_id == p.id)).scalar() or 0) + 1
    t = StabilityTimepoint(protocol_id=p.id, seq=seq, label=data.get("label") or f"{data['month']} M", month=data["month"])
    session.add(t)
    session.flush()
    return t


def conditions(session: Session, pid: int) -> list[StabilityCondition]:
    return list(session.execute(select(StabilityCondition).where(StabilityCondition.protocol_id == pid).order_by(StabilityCondition.seq)).scalars())


def timepoints(session: Session, pid: int) -> list[StabilityTimepoint]:
    return list(session.execute(select(StabilityTimepoint).where(StabilityTimepoint.protocol_id == pid).order_by(StabilityTimepoint.month)).scalars())


def validate_protocol(session: Session, p: StabilityProtocol) -> None:
    spec = session.get(Specification, p.specification_id)
    if spec is None or spec.status != "APPROVED":
        raise ValidationFailed("The protocol's specification must be APPROVED")
    if spec.material_id != p.material_id:
        raise ValidationFailed("The specification belongs to a different material")
    if not conditions(session, p.id):
        raise ValidationFailed("A protocol needs at least one storage condition")
    if not timepoints(session, p.id):
        raise ValidationFailed("A protocol needs at least one time point")
    if not any(c.condition_type in ("LONG_TERM", "REFRIGERATED", "FROZEN") for c in conditions(session, p.id)):
        raise ValidationFailed("A protocol needs a long-term (or refrigerated/frozen) storage condition")


# ------------------------------------------------------------------ study
def create_study(session: Session, user, data: dict) -> StabilityStudy:
    p = session.get(StabilityProtocol, data["protocol_id"])
    if p is None or p.status != "APPROVED":
        raise BusinessRuleError("A study needs an APPROVED protocol version", rule_id="BR-STB-001")
    lot = session.get(MaterialBatch, data["material_batch_id"])
    if lot is None:
        raise ValidationFailed("Unknown lot")
    if lot.material_id != p.material_id:
        raise ValidationFailed("The lot's material does not match the protocol's material")
    if session.get(Location, data["source_location_id"]) is None:
        raise ValidationFailed("Unknown source location")
    st = StabilityStudy(study_no=numbering.next_number(session, numbering.default_plant_id(session), "STUDY"), status="PLANNED", created_by_user_id=user.id, **data)
    session.add(st)
    session.flush()
    sod.record_action(session, "stability_study", st.id, "stability.study.create", user.id)
    return st


def start_study(session: Session, st: StabilityStudy, user) -> StabilityStudy:
    p = session.get(StabilityProtocol, st.protocol_id)
    lot = session.get(MaterialBatch, st.material_batch_id)
    conds, tps = conditions(session, p.id), timepoints(session, p.id)
    total = st.units_per_pull * len(conds) * len(tps)
    if lot.disposition in ("REJECTED", "DESTROYED", "RETURNED"):
        raise BusinessRuleError(f"Lot {lot.lot_no} is {lot.disposition}", rule_id="BR-STB-002")
    txn = inventory.post(session, txn_type="SAMPLE", batch=lot, quantity=total, from_location_id=st.source_location_id, ref_doc_type="STABILITY",
                         ref_doc_id=st.study_no, reason=f"Stability study {st.study_no}: {len(conds)} condition(s) x {len(tps)} time point(s)")
    st.placed_qty, st.ledger_txn_id, st.started_at = total, txn.id, utcnow()
    transition(session, STUDY_MACHINE, st, "ACTIVE", module="stability")
    for c in conds:
        for t in tps:
            session.add(StabilityPull(study_id=st.id, condition_id=c.id, timepoint_id=t.id, month=t.month, due_date=add_months(st.start_date, t.month),
                                      window_days=p.pull_window_days, status="SCHEDULED"))
    session.flush()
    return st


def pulls(session: Session, study_id: int) -> list[StabilityPull]:
    return list(session.execute(select(StabilityPull).where(StabilityPull.study_id == study_id).order_by(StabilityPull.month, StabilityPull.condition_id)).scalars())


def _lot_of(session: Session, st: StabilityStudy) -> MaterialBatch:
    return session.get(MaterialBatch, st.material_batch_id)


def record_pull(session: Session, pull: StabilityPull, user, qty=None, remarks: str | None = None, on: date | None = None) -> StabilityPull:
    on = on or date.today()
    st = session.get(StabilityStudy, pull.study_id)
    if st.status != "ACTIVE":
        raise BusinessRuleError(f"Study is {st.status}", rule_id="BR-STB-003")
    outside = on < pull.due_date - timedelta(days=pull.window_days) or on > pull.due_date + timedelta(days=pull.window_days)
    if outside and not (remarks or "").strip():
        raise ValidationFailed(f"Pull is outside the allowed window ({pull.due_date} ± {pull.window_days} d); remarks are required")
    pull.pulled_at, pull.pulled_by_id, pull.actual_qty, pull.remarks = utcnow(), user.id, qty, remarks
    transition(session, PULL_MACHINE, pull, "PULLED", module="stability")
    if outside:
        d = qs.raise_deviation(session, user.id, title=f"Stability pull outside window: {st.study_no} month {pull.month}", category="PROCESS", severity="MINOR", source="STABILITY",
                               description=f"Pull due {pull.due_date} (±{pull.window_days} d) was performed on {on}. {remarks}", entity_type="MATERIAL_BATCH", record_id=st.material_batch_id,
                               blocks_release=False)
        pull.deviation_id = d.id
    return pull


def current_results(session: Session, pull_id: int) -> list[StabilityResult]:
    sup = select(StabilityResult.supersedes_id).where(StabilityResult.supersedes_id.is_not(None), StabilityResult.pull_id == pull_id)
    return list(session.execute(select(StabilityResult).where(StabilityResult.pull_id == pull_id, StabilityResult.id.notin_(sup)).order_by(StabilityResult.parameter_id)).scalars())


def _params(session: Session, protocol_id: int) -> list[SpecificationParameter]:
    p = session.get(StabilityProtocol, protocol_id)
    return list(session.execute(select(SpecificationParameter).where(SpecificationParameter.specification_id == p.specification_id).order_by(SpecificationParameter.seq)).scalars())


def enter_result(session: Session, pull: StabilityPull, user, item: dict, correction_of: int | None = None, reason: str | None = None) -> StabilityResult:
    if pull.status not in ("PULLED", "TESTED"):
        raise BusinessRuleError(f"Pull is {pull.status}; results cannot be entered", rule_id="BR-STB-004")
    st = session.get(StabilityStudy, pull.study_id)
    param = session.get(SpecificationParameter, item["parameter_id"])
    if param is None or param.id not in {x.id for x in _params(session, st.protocol_id)}:
        raise ValidationFailed("Parameter does not belong to the protocol's specification")
    cur = {r.parameter_id: r for r in current_results(session, pull.id)}
    old = cur.get(param.id)
    if old and correction_of != old.id:
        raise BusinessRuleError("A result already exists for this parameter; submit a correction that references it", rule_id="BR-STB-005")
    if correction_of and (old is None or old.id != correction_of):
        raise ValidationFailed("The result to correct is not the current result for this parameter")
    if correction_of and not (reason or "").strip():
        raise ValidationFailed("A reason is required to correct a result", code="REASON_REQUIRED")
    if item.get("equipment_id"):
        eq = session.get(Equipment, item["equipment_id"])
        if eq is None:
            raise ValidationFailed("Unknown instrument")
        ok, why = ms.usable_for_testing(eq)
        if not ok:
            raise BusinessRuleError(f"Instrument {eq.equipment_code} cannot be used: {why} (BR-QC-002)", rule_id="BR-QC-002")
    rounded, pf = evaluate(param.spec_type, param.lsl, param.usl, param.decimal_places, item.get("value"), item.get("conforms"))
    dev_id = _raise_oos(session, st, pull, param, rounded, item, pf, user.id) if pf == "FAIL" else None
    r = StabilityResult(pull_id=pull.id, parameter_id=param.id, value_numeric=D(str(item["value"])) if item.get("value") is not None else None, rounded_value=rounded,
                        value_text=item.get("text") or (("Conforms" if item.get("conforms") else "Does not conform") if item.get("conforms") is not None else None),
                        unit=param.unit, lsl=param.lsl, usl=param.usl, pass_fail=pf, equipment_id=item.get("equipment_id"), supersedes_id=correction_of,
                        correction_reason=reason if correction_of else None, deviation_id=dev_id, entered_by_id=user.id)
    session.add(r)
    session.flush()
    sod.record_action(session, "stability_pull", pull.id, "stability.result.enter", user.id)
    return r


def _raise_oos(session: Session, st: StabilityStudy, pull: StabilityPull, param: SpecificationParameter, rounded, item: dict, pf: str, user_id: int) -> int:
    """One deviation per pull (further failures in the same pull attach to it). Results are append-only, so this runs before the row is created."""
    if pull.oos_deviation_id:
        return pull.oos_deviation_id
    sev = {"CRITICAL": "CRITICAL", "MAJOR": "MAJOR"}.get(param.criticality, "MINOR")
    shown = rounded if rounded is not None else (item.get("text") or "does not conform")
    d = qs.raise_deviation(session, user_id, title=f"Stability OOS: {st.study_no} month {pull.month} {param.test_name}", category="QC", severity=sev, source="STABILITY",
                           description=f"{param.test_name} = {shown} {param.unit or ''} fails specification (LSL {param.lsl}, USL {param.usl}) at month {pull.month}.",
                           entity_type="MATERIAL_BATCH", record_id=st.material_batch_id, blocks_release=True)
    pull.oos_deviation_id = d.id
    return d.id


def complete_testing(session: Session, pull: StabilityPull) -> StabilityPull:
    st = session.get(StabilityStudy, pull.study_id)
    have = {r.parameter_id for r in current_results(session, pull.id)}
    missing = [p.test_name for p in _params(session, st.protocol_id) if p.id not in have]
    if missing:
        raise BusinessRuleError(f"Results missing for: {', '.join(missing)}", rule_id="BR-STB-006")
    pull.tested_at = utcnow()
    transition(session, PULL_MACHINE, pull, "TESTED", module="stability")
    return pull


def review_pull(session: Session, pull: StabilityPull, user, password: str, reason: str) -> None:
    failing = [r for r in current_results(session, pull.id) if r.pass_fail == "FAIL"]
    if failing and pull.oos_deviation_id is None:
        raise BusinessRuleError("A failing result needs a deviation before review", rule_id="BR-STB-007")
    sig = masters.sign_and_transition(session, pull, PULL_MACHINE, "REVIEWED", user, password, reason=reason, meaning="REVIEWED_BY", sod_action="stability.pull.review")
    pull.reviewed_by_id, pull.reviewed_at, pull.review_signature_id = user.id, utcnow(), sig.id


def skip_pull(session: Session, pull: StabilityPull, reason: str) -> None:
    if not (reason or "").strip():
        raise ValidationFailed("A reason is required", code="REASON_REQUIRED")
    pull.skip_reason = reason
    transition(session, PULL_MACHINE, pull, "SKIPPED", reason=reason, module="stability")


def mark_missed(session: Session, today: date | None = None) -> list[StabilityPull]:
    """Pulls whose window has closed without being pulled become MISSED with a deviation (idempotent)."""
    today = today or date.today()
    out = []
    rows = session.execute(select(StabilityPull, StabilityStudy).join(StabilityStudy, StabilityStudy.id == StabilityPull.study_id)
                           .where(StabilityPull.status == "SCHEDULED", StabilityStudy.status == "ACTIVE")).all()
    for pull, st in rows:
        if pull.due_date + timedelta(days=pull.window_days) < today:
            d = qs.raise_deviation(session, None, title=f"Stability pull missed: {st.study_no} month {pull.month}", category="PROCESS", severity="MAJOR", source="STABILITY",
                                   description=f"The pull due {pull.due_date} (±{pull.window_days} d) was not performed.", entity_type="MATERIAL_BATCH", record_id=st.material_batch_id,
                                   blocks_release=False)
            pull.deviation_id = d.id
            transition(session, PULL_MACHINE, pull, "MISSED", reason="window closed", module="stability")
            out.append(pull)
    return out


def due(session: Session, horizon_days: int = 14, today: date | None = None) -> list[dict]:
    today = today or date.today()
    rows = session.execute(select(StabilityPull, StabilityStudy, StabilityCondition).join(StabilityStudy, StabilityStudy.id == StabilityPull.study_id)
                           .join(StabilityCondition, StabilityCondition.id == StabilityPull.condition_id)
                           .where(StabilityPull.status == "SCHEDULED", StabilityStudy.status == "ACTIVE", StabilityPull.due_date <= today + timedelta(days=horizon_days))
                           .order_by(StabilityPull.due_date)).all()
    return [{"pull_id": p.id, "study_id": s.id, "study_no": s.study_no, "lot_id": s.material_batch_id, "condition": c.label, "month": p.month, "due_date": p.due_date.isoformat(),
             "window_days": p.window_days, "overdue": p.due_date < today, "missed_if_after": (p.due_date + timedelta(days=p.window_days)).isoformat()} for p, s, c in rows]


def complete_study(session: Session, st: StabilityStudy) -> StabilityStudy:
    open_ = [p for p in pulls(session, st.id) if p.status in OPEN_PULL]
    if open_:
        raise BusinessRuleError(f"{len(open_)} pull(s) are still open (scheduled/pulled/tested)", rule_id="BR-STB-008")
    st.completed_at = utcnow()
    transition(session, STUDY_MACHINE, st, "COMPLETED", module="stability")
    return st


def terminate_study(session: Session, st: StabilityStudy, reason: str) -> StabilityStudy:
    if not (reason or "").strip():
        raise ValidationFailed("A reason is required", code="REASON_REQUIRED")
    st.terminate_reason = reason
    transition(session, STUDY_MACHINE, st, "TERMINATED", reason=reason, module="stability")
    for p in pulls(session, st.id):
        if p.status == "SCHEDULED":
            p.skip_reason = f"Study terminated: {reason}"
            transition(session, PULL_MACHINE, p, "SKIPPED", reason=reason, module="stability")
    return st


def conclude(session: Session, st: StabilityStudy, user, password: str, reason: str, shelf_life_months: int, conclusion: str) -> None:
    if shelf_life_months < 0 or not (conclusion or "").strip():
        raise ValidationFailed("A shelf life (months) and a written conclusion are required")
    open_dev = [p for p in pulls(session, st.id) if any(d and _open_deviation(session, d) for d in (p.deviation_id, p.oos_deviation_id))]
    if open_dev:
        raise BusinessRuleError("Linked deviations are still open; close them before the study conclusion", rule_id="BR-STB-009")
    st.shelf_life_months, st.conclusion = shelf_life_months, conclusion
    sig = masters.sign_and_transition(session, st, STUDY_MACHINE, "CONCLUDED", user, password, reason=reason, meaning="QA_APPROVED", sod_action="stability.study.conclude")
    st.concluded_by_id, st.concluded_at, st.conclusion_signature_id = user.id, utcnow(), sig.id


def _open_deviation(session: Session, dev_id: int) -> bool:
    from app.models.quality import Deviation
    d = session.get(Deviation, dev_id)
    return d is not None and d.status not in ("CLOSED", "CANCELLED")


# ------------------------------------------------------------------ evaluation (ICH Q1E-style)
def _t95(df: int) -> float:
    return _T95[df - 1] if df <= 30 else 1.66


def regress(points: list[tuple[float, float]], lsl: float | None, usl: float | None, max_months: float = 120.0) -> dict:
    n = len(points)
    if n < 3:
        return {"status": "INSUFFICIENT_DATA", "n": n, "note": "At least 3 time points are needed for a regression"}
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    xb, yb = sum(xs) / n, sum(ys) / n
    sxx = sum((x - xb) ** 2 for x in xs)
    if sxx == 0:
        return {"status": "INSUFFICIENT_DATA", "n": n, "note": "All results are at the same time point"}
    slope = sum((x - xb) * (y - yb) for x, y in points) / sxx
    icpt = yb - slope * xb
    sse = sum((y - (icpt + slope * x)) ** 2 for x, y in points)
    s = math.sqrt(sse / (n - 2))
    sst = sum((y - yb) ** 2 for y in ys)
    t = _t95(n - 2)

    def bound(x: float, upper: bool) -> float:
        half = t * s * math.sqrt(1 / n + (x - xb) ** 2 / sxx)
        return icpt + slope * x + (half if upper else -half)
    est = None
    step, x = 0.1, 0.0
    # first month at which the one-sided 95 % bound crosses a specification limit
    while x <= max_months:
        if lsl is not None and bound(x, False) < lsl or usl is not None and bound(x, True) > usl:
            est = round(x, 1)
            break
        x += step
    observed = max(xs)
    cap = min(2 * observed, observed + 12)
    out = {"status": "OK", "n": n, "slope_per_month": slope, "intercept": icpt, "r2": (1 - sse / sst) if sst > 0 else None, "residual_sd": s, "t_95_one_sided": t,
           "observed_months": observed, "extrapolation_cap_months": cap, "estimated_limit_crossing_months": est,
           "supported_shelf_life_months": None if est is None else min(est, cap) if est > observed else est}
    if est is None:
        out["supported_shelf_life_months"] = cap
        out["note"] = "Bound does not cross the limit within the search range; support is capped by the extrapolation rule (min of 2x observed, observed + 12 months)."
    return out


def evaluation(session: Session, st: StabilityStudy) -> list[dict]:
    """Per condition x numeric parameter regression on current (non-superseded) results."""
    out = []
    allp = pulls(session, st.id)
    params = [p for p in _params(session, st.protocol_id) if p.spec_type in ("NUMERIC", "RANGE")]
    for c in conditions(session, st.protocol_id):
        for p in params:
            pts = []
            for pl in allp:
                if pl.condition_id != c.id or pl.status not in ("TESTED", "REVIEWED"):
                    continue
                r = next((x for x in current_results(session, pl.id) if x.parameter_id == p.id and x.rounded_value is not None), None)
                if r:
                    pts.append((float(pl.month), float(r.rounded_value)))
            ev = regress(pts, float(p.lsl) if p.lsl is not None else None, float(p.usl) if p.usl is not None else None)
            out.append({"condition_id": c.id, "condition": c.label, "condition_type": c.condition_type, "parameter_id": p.id, "test_name": p.test_name, "unit": p.unit,
                        "lsl": float(p.lsl) if p.lsl is not None else None, "usl": float(p.usl) if p.usl is not None else None,
                        "points": [{"month": x, "value": y} for x, y in pts], **ev})
    return out


def daily_alerts(session: Session) -> int:
    """Close the windows of missed pulls (deviation raised) and warn QC about pulls due within 7 days."""
    from app.services import notifications
    n = len(mark_missed(session))
    for r in due(session, 7):
        n += notifications.notify_roles(session, ["QC_HEAD", "QC_ANALYST"], category="STABILITY_DUE", title=f"Stability pull due: {r['study_no']} month {r['month']} ({r['condition']})",
                                        body=f"Due {r['due_date']}, window closes {r['missed_if_after']}", ref_entity="stability_pull", ref_id=str(r["pull_id"]))
    return n
