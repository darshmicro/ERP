"""Inventory ledger + balance projection (spec 31, 69; design decision C-05).

Every movement is an append-only `inventory_transaction`; the balance row is updated in the SAME
transaction using guarded atomic UPDATEs, so concurrent issues cannot over-draw stock (BR-INV-002).
`verify_ledger` recomputes balances from the ledger and reports any drift.
"""
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import case, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit.context import get_context
from app.core.errors import BusinessRuleError, ValidationFailed
from app.models.master import Location, Material
from app.models.warehouse import InventoryBalance, InventoryTransaction, MaterialBatch, QualityHold
from app.services import master_services as ms

D = Decimal
IN_TYPES = {"RECEIPT", "RETURN", "ADJUST_IN", "OUTPUT"}
OUT_TYPES = {"SAMPLE", "ISSUE", "DESTROY", "ADJUST_OUT", "DISPATCH"}
MOVE_TYPES = {"TRANSFER", "REJECT_MOVE"}


def _bump_balance(session: Session, batch_id: int, loc_id: int, delta: Decimal) -> None:
    if delta > 0:
        n = session.execute(update(InventoryBalance).where(
            InventoryBalance.material_batch_id == batch_id, InventoryBalance.location_id == loc_id)
            .values(qty_on_hand=InventoryBalance.qty_on_hand + delta)).rowcount
        if n == 0:
            try:
                with session.begin_nested():
                    session.add(InventoryBalance(material_batch_id=batch_id, location_id=loc_id, qty_on_hand=delta, qty_reserved=0))
                    session.flush()
            except IntegrityError:   # concurrent creator won the race
                session.execute(update(InventoryBalance).where(
                    InventoryBalance.material_batch_id == batch_id, InventoryBalance.location_id == loc_id)
                    .values(qty_on_hand=InventoryBalance.qty_on_hand + delta))
    else:
        need = -delta
        n = session.execute(update(InventoryBalance).where(
            InventoryBalance.material_batch_id == batch_id, InventoryBalance.location_id == loc_id,
            InventoryBalance.qty_on_hand - InventoryBalance.qty_reserved >= need)
            .values(qty_on_hand=InventoryBalance.qty_on_hand - need)).rowcount
        if n == 0:
            raise BusinessRuleError("Insufficient available stock at this location (BR-INV-002: no negative stock)",
                                    rule_id="BR-INV-002")


def _occupancy(session: Session, loc_id: int, delta: Decimal) -> None:
    loc = session.get(Location, loc_id)
    if loc is None:
        raise ValidationFailed("Unknown location")
    new = (loc.current_occupancy or D(0)) + delta
    if delta > 0 and loc.capacity is not None and new > loc.capacity:
        raise BusinessRuleError(f"Location {loc.location_code} capacity exceeded ({new} > {loc.capacity})", rule_id="BR-LOC-002")
    loc.current_occupancy = new if new > 0 else D(0)


def post(session: Session, *, txn_type: str, batch: MaterialBatch, quantity: Decimal,
         from_location_id: int | None = None, to_location_id: int | None = None, ref_doc_type: str | None = None,
         ref_doc_id: Any = None, reason: str | None = None, signature_id: int | None = None,
         reverses_txn_id: int | None = None) -> InventoryTransaction:
    q = D(str(quantity))
    if q <= 0:
        raise ValidationFailed("Quantity must be positive")
    if txn_type in IN_TYPES and (to_location_id is None or from_location_id is not None):
        raise ValidationFailed(f"{txn_type} needs a destination location only")
    if txn_type in OUT_TYPES and (from_location_id is None or to_location_id is not None):
        raise ValidationFailed(f"{txn_type} needs a source location only")
    if txn_type in MOVE_TYPES and (from_location_id is None or to_location_id is None or from_location_id == to_location_id):
        raise ValidationFailed(f"{txn_type} needs two different locations")
    if from_location_id is not None:
        _bump_balance(session, batch.id, from_location_id, -q)
        _occupancy(session, from_location_id, -q)
    if to_location_id is not None:
        _bump_balance(session, batch.id, to_location_id, q)
        _occupancy(session, to_location_id, q)
    txn = InventoryTransaction(material_batch_id=batch.id, txn_type=txn_type, from_location_id=from_location_id,
                               to_location_id=to_location_id, quantity=q, unit_id=batch.unit_id, ref_doc_type=ref_doc_type,
                               ref_doc_id=None if ref_doc_id is None else str(ref_doc_id), reason=reason,
                               signature_id=signature_id, reverses_txn_id=reverses_txn_id, user_id=get_context().user_id)
    session.add(txn)
    session.flush()
    return txn


def transfer(session: Session, batch: MaterialBatch, qty: Decimal, from_loc: Location, to_loc: Location,
             *, reason: str | None = None, reject_move: bool = False) -> InventoryTransaction:
    """Put-away / move with the location rules: quarantine lots only in quarantine areas, approved lots never
    in quarantine/rejected areas, rejected lots only in rejected areas, plus storage compatibility (BR-LOC-001)."""
    mat = session.get(Material, batch.material_id)
    d = batch.disposition
    if d in ("QUARANTINE", "QC_TESTING", "QC_APPROVED", "QA_REVIEW") and not to_loc.is_quarantine:
        raise BusinessRuleError("Unreleased material may only be stored in a quarantine location", rule_id="BR-QRN-001")
    if d == "APPROVED" and (to_loc.is_quarantine or to_loc.is_rejected_area):
        raise BusinessRuleError("Approved material cannot be moved into a quarantine or rejected area", rule_id="BR-QRN-002")
    if d in ("REJECTED", "EXPIRED") and not to_loc.is_rejected_area:
        raise BusinessRuleError("Rejected/expired material may only be moved to a rejected-material area", rule_id="BR-QRN-003")
    if d == "DESTROYED":
        raise BusinessRuleError("Destroyed material cannot be moved", rule_id="BR-QRN-004")
    present = [c for (c,) in session.execute(select(Material.category_id).join(MaterialBatch, MaterialBatch.material_id == Material.id)
                                             .join(InventoryBalance, InventoryBalance.material_batch_id == MaterialBatch.id)
                                             .where(InventoryBalance.location_id == to_loc.id, InventoryBalance.qty_on_hand > 0,
                                                    MaterialBatch.id != batch.id).distinct()).all() if c]
    viol = ms.storage_violations(session, to_loc, mat, present)
    if viol:
        raise BusinessRuleError("Cannot store here: " + "; ".join(viol), rule_id="BR-LOC-001", details=viol)
    return post(session, txn_type="REJECT_MOVE" if reject_move else "TRANSFER", batch=batch, quantity=qty,
                from_location_id=from_loc.id, to_location_id=to_loc.id, reason=reason)


def reserve(session: Session, batch_id: int, location_id: int, qty: Decimal) -> None:
    n = session.execute(update(InventoryBalance).where(
        InventoryBalance.material_batch_id == batch_id, InventoryBalance.location_id == location_id,
        InventoryBalance.qty_on_hand - InventoryBalance.qty_reserved >= qty)
        .values(qty_reserved=InventoryBalance.qty_reserved + qty)).rowcount
    if n == 0:
        raise BusinessRuleError("Not enough unreserved stock to reserve", rule_id="BR-INV-002")


def release_reservation(session: Session, batch_id: int, location_id: int, qty: Decimal) -> None:
    session.execute(update(InventoryBalance).where(
        InventoryBalance.material_batch_id == batch_id, InventoryBalance.location_id == location_id,
        InventoryBalance.qty_reserved >= qty).values(qty_reserved=InventoryBalance.qty_reserved - qty))


def on_hand(session: Session, batch_id: int, location_id: int | None = None) -> Decimal:
    q = select(func.coalesce(func.sum(InventoryBalance.qty_on_hand), 0)).where(InventoryBalance.material_batch_id == batch_id)
    if location_id:
        q = q.where(InventoryBalance.location_id == location_id)
    return D(str(session.execute(q).scalar()))


def verify_ledger(session: Session) -> list[dict]:
    """Recompute every (lot, location) balance from the ledger; return the discrepancies (BR-INV-003)."""
    signed: dict[tuple[int, int], Decimal] = {}
    for t in session.execute(select(InventoryTransaction)).scalars():
        if t.to_location_id:
            k = (t.material_batch_id, t.to_location_id)
            signed[k] = signed.get(k, D(0)) + t.quantity
        if t.from_location_id:
            k = (t.material_batch_id, t.from_location_id)
            signed[k] = signed.get(k, D(0)) - t.quantity
    bal = {(b.material_batch_id, b.location_id): b.qty_on_hand for b in session.execute(select(InventoryBalance)).scalars()}
    out = []
    for k in set(signed) | set(bal):
        if D(str(signed.get(k, 0))) != D(str(bal.get(k, 0))):
            out.append({"material_batch_id": k[0], "location_id": k[1], "ledger": float(signed.get(k, 0)), "balance": float(bal.get(k, 0))})
    return out


def lot_reconciliation(session: Session, batch: MaterialBatch) -> dict:
    """Received → sampled → issued → returned → rejected/destroyed → remaining, from the ledger (spec 68)."""
    sums = dict(session.execute(select(InventoryTransaction.txn_type, func.coalesce(func.sum(InventoryTransaction.quantity), 0))
                                .where(InventoryTransaction.material_batch_id == batch.id).group_by(InventoryTransaction.txn_type)).all())
    g = lambda k: D(str(sums.get(k, 0)))
    received = g("RECEIPT") + g("OUTPUT")
    adj = g("ADJUST_IN") - g("ADJUST_OUT")
    remaining_book = received + g("RETURN") + adj - g("SAMPLE") - g("ISSUE") - g("DESTROY") - g("DISPATCH")
    physical = on_hand(session, batch.id)
    return {"received": float(received), "sampled": float(g("SAMPLE")), "issued": float(g("ISSUE")),
            "returned": float(g("RETURN")), "destroyed": float(g("DESTROY")), "dispatched": float(g("DISPATCH")),
            "adjustments": float(adj), "remaining_book": float(remaining_book), "on_hand": float(physical),
            "unexplained": float(physical - remaining_book)}
