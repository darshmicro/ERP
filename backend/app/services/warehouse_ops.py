"""Temperature excursions and destruction of rejected/expired material."""
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import BusinessRuleError, NotFound, ValidationFailed
from app.core.time import utcnow
from app.models.master import Location
from app.models.warehouse import DestructionRecord, InventoryBalance, MaterialBatch, StorageTemperatureLog
from app.services import inventory, lots, masters, notifications, numbering, sod
from app.workflows.state_machine import StateMachine, Transition, transition

T = Transition
DESTR_MACHINE = StateMachine("destruction_record", "REQUESTED", {
    "REQUESTED": {"APPROVED": T("APPROVED", "warehouse.destruction.approve", "APPROVED_BY", True),
                  "REJECTED": T("REJECTED", "warehouse.destruction.approve", "REJECTED_BY", True)},
    "APPROVED": {"EXECUTED": T("EXECUTED")},
})


def log_temperature(session: Session, loc: Location, reading: Decimal, user_id: int | None, remarks: str | None = None) -> dict:
    r = Decimal(str(reading))
    exc = (loc.temp_min is not None and r < loc.temp_min) or (loc.temp_max is not None and r > loc.temp_max)
    row = StorageTemperatureLog(location_id=loc.id, reading=r, recorded_by_id=user_id, excursion=bool(exc), remarks=remarks)
    session.add(row)
    session.flush()
    held = []
    if exc:   # BR-TMP-001: excursion => hold every lot stored there and prompt a deviation
        for lot in session.execute(select(MaterialBatch).join(InventoryBalance, InventoryBalance.material_batch_id == MaterialBatch.id)
                                   .where(InventoryBalance.location_id == loc.id, InventoryBalance.qty_on_hand > 0)).scalars():
            h = lots.place_hold(session, "MATERIAL_BATCH", lot.id,
                                f"Temperature excursion at {loc.location_code}: {r} °C (range {loc.temp_min}–{loc.temp_max})",
                                source="TEMPERATURE", ref=f"LOG{row.id}", user_id=user_id)
            held.append(h.hold_no)
        notifications.notify_roles(session, ["QA_OFFICER", "QA_HEAD", "WAREHOUSE_USER"], category="TEMPERATURE",
                                   title=f"Temperature excursion at {loc.location_code}: {r} °C",
                                   body="Lots in this location were placed on quality hold. Raise a deviation.",
                                   ref_entity="location", ref_id=str(loc.id))
    return {"id": row.id, "excursion": bool(exc), "holds": held}


def request_destruction(session: Session, user, lot: MaterialBatch, loc: Location, qty: Decimal, method: str, reason: str) -> DestructionRecord:
    if lot.disposition not in ("REJECTED", "EXPIRED"):
        raise BusinessRuleError("Only REJECTED or EXPIRED material can be destroyed", rule_id="BR-DES-001")
    if not loc.is_rejected_area:
        raise BusinessRuleError("Material must be in a rejected-material area before destruction", rule_id="BR-DES-002")
    if inventory.on_hand(session, lot.id, loc.id) < Decimal(str(qty)):
        raise BusinessRuleError("Quantity exceeds stock at the location", rule_id="BR-INV-002")
    d = DestructionRecord(destruction_no=numbering.next_number(session, numbering.default_plant_id(session), "DESTR"),
                          material_batch_id=lot.id, location_id=loc.id, quantity=qty, method=method, reason=reason,
                          status="REQUESTED", requested_by_id=user.id)
    session.add(d)
    session.flush()
    sod.record_action(session, "destruction_record", d.id, "warehouse.destruction.request", user.id)
    return d


def decide(session: Session, d: DestructionRecord, user, password: str, approve: bool, reason: str) -> None:
    sod.check(session, user.id, "destruction_record", d.id, "warehouse.destruction.approve")
    sig = masters.sign_and_transition(session, d, DESTR_MACHINE, "APPROVED" if approve else "REJECTED", user, password,
                                      reason=reason, meaning="APPROVED_BY" if approve else "REJECTED_BY")
    d.approved_by_id, d.approved_signature_id = user.id, sig.id
    sod.record_action(session, "destruction_record", d.id, "warehouse.destruction.approve", user.id)


def execute(session: Session, d: DestructionRecord, user) -> None:
    lot = session.get(MaterialBatch, d.material_batch_id)
    txn = inventory.post(session, txn_type="DESTROY", batch=lot, quantity=d.quantity, from_location_id=d.location_id,
                         ref_doc_type="DESTRUCTION", ref_doc_id=d.destruction_no, reason=d.reason, signature_id=d.approved_signature_id)
    d.executed_at, d.ledger_txn_id = utcnow(), txn.id
    transition(session, DESTR_MACHINE, d, "EXECUTED", reason="Destroyed per approved record", module="warehouse")
    if inventory.on_hand(session, lot.id) == 0 and lot.disposition in ("REJECTED", "EXPIRED"):
        transition(session, lots.LOT_MACHINE, lot, "DESTROYED", reason=f"All stock destroyed ({d.destruction_no})", module="warehouse")
