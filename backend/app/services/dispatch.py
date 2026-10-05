"""Dispatch of released finished goods (spec 44-47; BR-DSP-001..006, BR-HOLD-003, BR-FGR-001)."""
import json
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit.context import get_context
from app.core.errors import BusinessRuleError, NotFound, ValidationFailed
from app.services.security_events import log_security_event
from app.core.time import utcnow
from app.models.dispatch import Dispatch, DispatchLine
from app.models.master import Customer, Location, Material, MaterialType
from app.models.qc import COA, OOSInvestigation
from app.models.warehouse import InventoryBalance, MaterialBatch
from app.services import inventory, lots, masters, notifications, numbering, sod
from app.workflows.state_machine import StateMachine, Transition, transition

T = Transition
D = Decimal
DISPATCH_MACHINE = StateMachine("dispatch", "DRAFT", {
    "DRAFT": {"VALIDATED": T("VALIDATED"), "CANCELLED": T("CANCELLED", requires_reason=True)},
    "VALIDATED": {"DRAFT": T("DRAFT", requires_reason=True), "APPROVED": T("APPROVED", "dispatch.order.approve", "APPROVED_BY", True),
                  "CANCELLED": T("CANCELLED", requires_reason=True)},
    "APPROVED": {"DISPATCHED": T("DISPATCHED", "dispatch.order.dispatch"), "CANCELLED": T("CANCELLED", requires_reason=True)},
    "DISPATCHED": {"DELIVERED": T("DELIVERED")},
})


@dataclass
class Violation:
    rule_id: str
    message: str
    severity: str = "BLOCK"          # BLOCK / WARN
    line_no: int | None = None


def _plant(s: Session) -> int:
    return numbering.default_plant_id(s)


def dispatch_lines(session: Session, did: int) -> list[DispatchLine]:
    return list(session.execute(select(DispatchLine).where(DispatchLine.dispatch_id == did).order_by(DispatchLine.line_no)).scalars())


# ------------------------------------------------------------------ extension point for Phase 8 (deviation / complaint / recall holds)
LOT_BLOCKERS: list = []


def lot_blockers(session: Session, lot: MaterialBatch) -> list[tuple[str, str]]:
    """Open records that must block distribution of a lot (BR-DSP-004)."""
    out = []
    n = session.execute(select(func.count()).select_from(OOSInvestigation).where(OOSInvestigation.material_batch_id == lot.id, OOSInvestigation.status != "CLOSED")).scalar()
    if n:
        out.append(("BR-DSP-004", f"Lot {lot.lot_no} has an open OOS investigation"))
    from app.services import quality_system
    out += quality_system.deviation_blockers(session, lot)
    for fn in LOT_BLOCKERS:
        out += fn(session, lot)
    return out


def latest_coa(session: Session, lot_id: int) -> COA | None:
    return session.execute(select(COA).where(COA.material_batch_id == lot_id).order_by(COA.version_no.desc())).scalars().first()


def evaluate(session: Session, d: Dispatch, lines: list[DispatchLine], *, today: date | None = None) -> list[Violation]:
    today = today or date.today()
    out: list[Violation] = []
    cust = session.get(Customer, d.customer_id)
    if not cust.is_active:
        out.append(Violation("BR-DSP-005", f"Customer {cust.name} is inactive"))
    if not cust.is_authorised:
        out.append(Violation("BR-DSP-005", f"Customer {cust.name} is not authorised to receive product"))
    if cust.licence_no and cust.licence_expiry and cust.licence_expiry < today:
        out.append(Violation("BR-DSP-005", f"Customer licence {cust.licence_no} expired on {cust.licence_expiry.isoformat()}"))
    elif cust.licence_no and cust.licence_expiry and (cust.licence_expiry - today).days <= 30:
        out.append(Violation("BR-DSP-005", f"Customer licence expires on {cust.licence_expiry.isoformat()}", "WARN"))
    if not lines:
        out.append(Violation("BR-DSP-003", "A dispatch needs at least one line"))
    per_lot: dict[tuple[int, int], D] = {}
    for ln in lines:
        lot = session.get(MaterialBatch, ln.material_batch_id)
        mat = session.get(Material, lot.material_id)
        n = ln.line_no
        if session.get(MaterialType, mat.type_id).code != "FG":
            out.append(Violation("BR-FGR-001", f"{lot.lot_no}: only finished goods can be dispatched", line_no=n))
        if lot.disposition != "APPROVED":                                     # BR-DSP-001 / critical rule 6
            out.append(Violation("BR-DSP-001", f"DISPATCH BLOCKED — batch {lot.lot_no} is {lot.disposition}; QA release is required.", line_no=n))
        if lots.has_open_hold(session, "MATERIAL_BATCH", lot.id):               # BR-HOLD-003
            out.append(Violation("BR-HOLD-003", f"Batch {lot.lot_no} is on QUALITY HOLD.", line_no=n))
        for rid, msg in lot_blockers(session, lot):
            out.append(Violation(rid, msg, line_no=n))
        if lot.expiry_date:
            remaining = (lot.expiry_date - d.dispatch_date).days
            if lot.expiry_date < d.dispatch_date:
                out.append(Violation("BR-DSP-002", f"Batch {lot.lot_no} expired on {lot.expiry_date.isoformat()}", line_no=n))
            elif cust.min_remaining_shelf_life_days and remaining < cust.min_remaining_shelf_life_days:
                out.append(Violation("BR-DSP-002", f"Batch {lot.lot_no}: {remaining} days of shelf life remain; customer requires {cust.min_remaining_shelf_life_days}", line_no=n))
            elif remaining <= 30:
                out.append(Violation("BR-DSP-002", f"Batch {lot.lot_no}: only {remaining} days of shelf life remain", "WARN", n))
        if lot.disposition == "APPROVED" and lot.retest_date and lot.retest_date < d.dispatch_date:
            out.append(Violation("BR-DSP-002", f"Batch {lot.lot_no} retest date has passed", line_no=n))
        if latest_coa(session, lot.id) is None:
            out.append(Violation("BR-FGR-002", f"Batch {lot.lot_no} has no CoA (issued only after QA release)", line_no=n))
        bal = session.execute(select(InventoryBalance).where(InventoryBalance.material_batch_id == lot.id, InventoryBalance.location_id == ln.location_id)).scalars().first()
        free = (bal.qty_on_hand - bal.qty_reserved + (ln.quantity if ln.reserved else 0)) if bal else D(0)
        key = (lot.id, ln.location_id)
        per_lot[key] = per_lot.get(key, D(0)) + ln.quantity
        if per_lot[key] > free:                                                 # BR-DSP-003
            out.append(Violation("BR-DSP-003", f"Batch {lot.lot_no}: {per_lot[key]} requested, only {free} available at the location", line_no=n))
    return out


def blocks(v: list[Violation]) -> list[Violation]:
    return [x for x in v if x.severity == "BLOCK"]


def _snapshot(v: list[Violation], stage: str) -> str:
    return json.dumps({"stage": stage, "at": utcnow().isoformat(), "violations": [asdict(x) for x in v]})


def assert_allowed(session: Session, d: Dispatch, v: list[Violation], stage: str) -> None:
    b = blocks(v)
    if not b:
        return
    ctx = get_context()
    log_security_event("DISPATCH_BLOCKED", user_id=ctx.user_id, username=ctx.user_name,
                       detail=f"{stage} {d.dispatch_no}: " + "; ".join(f"{x.rule_id} {x.message}" for x in b))
    raise BusinessRuleError(b[0].message, rule_id=b[0].rule_id, details=[asdict(x) for x in v])


# ------------------------------------------------------------------ lifecycle
def set_lines(session: Session, d: Dispatch, lines: list[dict]) -> None:
    if d.status != "DRAFT":
        raise BusinessRuleError("Only a DRAFT dispatch can be edited", rule_id="BR-HIS-001")
    if not lines:
        raise ValidationFailed("At least one line is required")
    for old in dispatch_lines(session, d.id):
        session.delete(old)
    session.flush()
    for i, ln in enumerate(lines, 1):
        lot = session.get(MaterialBatch, ln["material_batch_id"])
        loc = session.get(Location, ln["location_id"])
        if lot is None or loc is None:
            raise ValidationFailed("Unknown lot or location")
        if D(str(ln["quantity"])) <= 0:
            raise ValidationFailed("Quantity must be positive")
        session.add(DispatchLine(dispatch_id=d.id, line_no=i, material_batch_id=lot.id, location_id=loc.id, quantity=ln["quantity"], unit_id=lot.unit_id))
    session.flush()


def create(session: Session, user, header: dict, lines: list[dict]) -> Dispatch:
    cust = session.get(Customer, header["customer_id"])
    if cust is None:
        raise ValidationFailed("Unknown customer")
    d = Dispatch(dispatch_no=numbering.next_number(session, _plant(session), "DISPATCH"), dispatch_date=header.pop("dispatch_date", None) or date.today(),
                 status="DRAFT", created_by_user_id=user.id, **header)
    session.add(d)
    session.flush()
    set_lines(session, d, lines)
    sod.record_action(session, "dispatch", d.id, "dispatch.order.create", user.id)
    return d


def _reserve(session: Session, d: Dispatch) -> None:
    for ln in dispatch_lines(session, d.id):
        if not ln.reserved:
            inventory.reserve(session, ln.material_batch_id, ln.location_id, ln.quantity)
            ln.reserved = True
    session.flush()


def _unreserve(session: Session, d: Dispatch) -> None:
    for ln in dispatch_lines(session, d.id):
        if ln.reserved:
            inventory.release_reservation(session, ln.material_batch_id, ln.location_id, ln.quantity)
            ln.reserved = False
    session.flush()


def validate(session: Session, d: Dispatch) -> list[Violation]:
    """Dry run (any status): returns violations without changing anything."""
    return evaluate(session, d, dispatch_lines(session, d.id))


def submit_validation(session: Session, d: Dispatch) -> list[Violation]:
    if d.status != "DRAFT":
        raise BusinessRuleError(f"Dispatch is {d.status}", rule_id="BR-HIS-001")
    v = evaluate(session, d, dispatch_lines(session, d.id))
    assert_allowed(session, d, v, "VALIDATE")
    d.validation_snapshot = _snapshot(v, "VALIDATE")
    session.flush()
    _reserve(session, d)                                                 # stock is earmarked once validated
    transition(session, DISPATCH_MACHINE, d, "VALIDATED", module="dispatch")
    return v


def reopen(session: Session, d: Dispatch, reason: str) -> None:
    if not (reason or "").strip():
        raise ValidationFailed("A reason is required", code="REASON_REQUIRED")
    _unreserve(session, d)
    transition(session, DISPATCH_MACHINE, d, "DRAFT", reason=reason, module="dispatch")


def approve(session: Session, d: Dispatch, user, password: str, reason: str) -> list[Violation]:
    if d.status != "VALIDATED":
        raise BusinessRuleError(f"Dispatch is {d.status}; validate it first", rule_id="BR-DSP-001")
    v = evaluate(session, d, dispatch_lines(session, d.id))
    assert_allowed(session, d, v, "APPROVE")
    sig = masters.sign_and_transition(session, d, DISPATCH_MACHINE, "APPROVED", user, password, reason=reason, meaning="APPROVED_BY", sod_action="dispatch.order.approve")
    d.approved_by_id, d.approved_signature_id, d.approved_at = user.id, sig.id, utcnow()
    d.validation_snapshot = _snapshot(v, "APPROVE")
    return v


def dispatch(session: Session, d: Dispatch, user) -> list[Violation]:
    if d.status != "APPROVED":
        raise BusinessRuleError(f"Dispatch is {d.status}; it must be APPROVED", rule_id="BR-DSP-001")
    sod.check(session, user.id, "dispatch", d.id, "dispatch.order.dispatch")
    v = evaluate(session, d, dispatch_lines(session, d.id))
    assert_allowed(session, d, v, "DISPATCH")
    for ln in dispatch_lines(session, d.id):
        lot = session.get(MaterialBatch, ln.material_batch_id)
        if ln.reserved:
            inventory.release_reservation(session, lot.id, ln.location_id, ln.quantity)
            ln.reserved = False
        txn = inventory.post(session, txn_type="DISPATCH", batch=lot, quantity=ln.quantity, from_location_id=ln.location_id, ref_doc_type="DISPATCH", ref_doc_id=d.dispatch_no)
        coa = latest_coa(session, lot.id)
        ln.ledger_txn_id, ln.coa_id = txn.id, coa.id if coa else None
    d.dispatched_by_id, d.dispatched_at = user.id, utcnow()
    d.validation_snapshot = _snapshot(v, "DISPATCH")
    transition(session, DISPATCH_MACHINE, d, "DISPATCHED", module="dispatch")
    sod.record_action(session, "dispatch", d.id, "dispatch.order.dispatch", user.id)
    return v


def deliver(session: Session, d: Dispatch, remarks: str | None) -> None:
    d.delivered_at, d.delivery_remarks = utcnow(), remarks
    transition(session, DISPATCH_MACHINE, d, "DELIVERED", reason=remarks or "Delivered", module="dispatch")


def cancel(session: Session, d: Dispatch, reason: str) -> None:
    if not (reason or "").strip():
        raise ValidationFailed("A reason is required", code="REASON_REQUIRED")
    _unreserve(session, d)
    d.cancel_reason = reason
    transition(session, DISPATCH_MACHINE, d, "CANCELLED", reason=reason, module="dispatch")
