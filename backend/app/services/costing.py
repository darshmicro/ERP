"""Costing (Phase 11c): lot cost, controlled rate cards, actual batch cost, standard-cost variance, inventory valuation.

* Purchased lots are costed from the PO line rate (tax excluded unless `costing.include_tax`); SFG/FG lots take the
  unit cost of their APPROVED batch cost, so SFG -> FG costs roll up through the genealogy.
* A batch cost is derived from the immutable issue/return records, never typed in; labour and machine hours are the
  only manual inputs. Costs of uncosted input lots block the calculation instead of being treated as zero.
* Lot costs are append-only (a correction adds a row with a reason); an approved batch cost is locked.
"""
import json
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import BusinessRuleError, ValidationFailed
from app.core.time import utcnow
from app.models.costing import BatchCost, CostRateCard, LotCost, StandardCost
from app.models.manufacturing import ManufacturingBatch, MaterialIssue, MaterialReturn
from app.models.master import Material
from app.models.purchase import PurchaseOrderLine
from app.models.warehouse import GRNLine, InventoryBalance, MaterialBatch
from app.services import config_service, masters, sod, versioning
from app.workflows.state_machine import StateMachine, Transition as T

D = Decimal
Q6, Q4 = D("0.000001"), D("0.0001")

BATCH_COST_MACHINE = StateMachine("batch_cost", "DRAFT", {"DRAFT": {"APPROVED": T("APPROVED", "costing.batch.approve", "APPROVED_BY", True)}})


def q4(v: D) -> D:
    return v.quantize(Q4, rounding=ROUND_HALF_UP)


def q6(v: D) -> D:
    return v.quantize(Q6, rounding=ROUND_HALF_UP)


# ------------------------------------------------------------------ lot cost
def current_cost(session: Session, lot_id: int) -> LotCost | None:
    return session.execute(select(LotCost).where(LotCost.material_batch_id == lot_id).order_by(LotCost.id.desc())).scalars().first()


def set_lot_cost(session: Session, lot: MaterialBatch, unit_cost, reason: str, user_id: int | None, *, basis: str = "MANUAL", **kw) -> LotCost:
    if not (reason or "").strip():
        raise ValidationFailed("A reason is required", code="REASON_REQUIRED")
    uc = D(str(unit_cost))
    if uc < 0:
        raise ValidationFailed("Unit cost cannot be negative")
    row = LotCost(material_batch_id=lot.id, unit_cost=q6(uc), basis=basis, reason=reason, recorded_by_id=user_id, **kw)
    session.add(row)
    session.flush()
    return row


def ensure_lot_cost(session: Session, lot: MaterialBatch, user_id: int | None) -> LotCost:
    cur = current_cost(session, lot.id)
    if cur is not None:
        return cur
    if lot.source_type == "GRN" and lot.grn_line_id:
        gl = session.get(GRNLine, lot.grn_line_id)
        pl = session.get(PurchaseOrderLine, gl.po_line_id) if gl else None
        if pl is not None:
            if pl.unit_id != lot.unit_id:
                raise BusinessRuleError(f"Lot {lot.lot_no}: PO unit differs from the lot unit; record a manual cost with a reason", rule_id="BR-COST-001")
            rate = D(str(pl.rate))
            if config_service.get_bool(session, "costing.include_tax", False):
                rate = rate * (1 + D(str(pl.tax_pct)) / 100)
            return set_lot_cost(session, lot, rate, f"PO line rate ({pl.id})", user_id, basis="PO_RATE", po_line_id=pl.id)
    if lot.source_type == "MFG":
        raise BusinessRuleError(f"Lot {lot.lot_no} is manufactured and has no approved batch cost; cost and approve its batch first", rule_id="BR-COST-002")
    raise BusinessRuleError(f"Lot {lot.lot_no} has no cost basis; record a manual cost with a reason", rule_id="BR-COST-001")


# ------------------------------------------------------------------ rate cards / standards
def card_in_force(session: Session) -> CostRateCard:
    c = versioning.version_in_force(session, CostRateCard)
    if c is None:
        raise BusinessRuleError("No APPROVED cost rate card is in force", rule_id="BR-COST-003")
    return c


def set_standard(session: Session, material_id: int, std_unit_cost, remarks: str | None = None) -> StandardCost:
    if session.get(Material, material_id) is None:
        raise ValidationFailed("Unknown material")
    v = D(str(std_unit_cost))
    if v < 0:
        raise ValidationFailed("Standard cost cannot be negative")
    row = session.execute(select(StandardCost).where(StandardCost.material_id == material_id)).scalars().first()
    if row is None:
        row = StandardCost(material_id=material_id, std_unit_cost=q6(v), remarks=remarks)
        session.add(row)
    else:
        row.std_unit_cost, row.remarks = q6(v), remarks
    session.flush()
    return row


# ------------------------------------------------------------------ batch cost
def _net_issues(session: Session, batch_id: int) -> dict[int, D]:
    """Net quantity of each lot charged to the batch: issued minus accepted returns."""
    net: dict[int, D] = {}
    for iss in session.execute(select(MaterialIssue).where(MaterialIssue.batch_id == batch_id)).scalars():
        net[iss.material_batch_id] = net.get(iss.material_batch_id, D(0)) + D(str(iss.quantity))
    for ret in session.execute(select(MaterialReturn).where(MaterialReturn.batch_id == batch_id, MaterialReturn.status == "ACCEPTED")).scalars():
        net[ret.material_batch_id] = net.get(ret.material_batch_id, D(0)) - D(str(ret.returned_qty))
    return {k: v for k, v in net.items() if v != 0}


def calculate(session: Session, user, batch: ManufacturingBatch, labour_hours, machine_hours) -> BatchCost:
    if batch.output_lot_id is None or not batch.actual_qty or D(str(batch.actual_qty)) <= 0:
        raise BusinessRuleError("The batch has no recorded output yet; cost it after the output is booked", rule_id="BR-COST-004")
    lh, mh = D(str(labour_hours)), D(str(machine_hours))
    if lh < 0 or mh < 0:
        raise ValidationFailed("Hours cannot be negative")
    bc = session.execute(select(BatchCost).where(BatchCost.batch_id == batch.id)).scalars().first()
    if bc is not None and bc.status == "APPROVED":
        raise BusinessRuleError("An approved batch cost is locked", rule_id="BR-COST-005")
    card = card_in_force(session)
    lines, missing, material = [], [], D(0)
    for lot_id, qty in _net_issues(session, batch.id).items():
        lot = session.get(MaterialBatch, lot_id)
        try:
            lc = ensure_lot_cost(session, lot, user.id)
        except BusinessRuleError as e:
            missing.append(str(e))
            continue
        amt = q4(qty * D(str(lc.unit_cost)))
        material += amt
        lines.append({"lot_id": lot.id, "lot_no": lot.lot_no, "material_id": lot.material_id, "net_qty": str(qty), "unit_cost": str(lc.unit_cost), "basis": lc.basis, "amount": str(amt)})
    if missing:
        raise BusinessRuleError("Input lots without a cost: " + " | ".join(missing), rule_id="BR-COST-001")
    labour, machine = q4(lh * D(str(card.labour_rate_per_hour))), q4(mh * D(str(card.machine_rate_per_hour)))
    overhead = q4((labour + machine) * D(str(card.overhead_pct)) / 100)
    total = material + labour + machine + overhead
    out_qty = D(str(batch.actual_qty))
    unit = q6(total / out_qty)
    std = session.execute(select(StandardCost).where(StandardCost.material_id == batch.product_material_id)).scalars().first()
    std_unit = D(str(std.std_unit_cost)) if std else None
    variance = q4(total - std_unit * out_qty) if std_unit is not None else None
    vpct = (variance / (std_unit * out_qty) * 100).quantize(D("0.01")) if std_unit and variance is not None and std_unit * out_qty != 0 else None
    vals = dict(rate_card_id=card.id, labour_hours=lh, machine_hours=mh, material_cost=material, labour_cost=labour, machine_cost=machine, overhead_cost=overhead, total_cost=total,
                output_qty=out_qty, unit_cost=unit, standard_unit_cost=std_unit, variance=variance, variance_pct=vpct, currency=card.currency, lines_snapshot=json.dumps(lines))
    if bc is None:
        bc = BatchCost(batch_id=batch.id, status="DRAFT", calculated_by_id=user.id, **vals)
        session.add(bc)
    else:
        for k, v in vals.items():
            setattr(bc, k, v)
        bc.calculated_by_id = user.id
    session.flush()
    sod.record_action(session, "batch_cost", bc.id, "costing.batch.calculate", user.id)
    return bc


def approve(session: Session, bc: BatchCost, user, password: str, reason: str) -> None:
    sig = masters.sign_and_transition(session, bc, BATCH_COST_MACHINE, "APPROVED", user, password, reason=reason, meaning="APPROVED_BY", sod_action="costing.batch.approve")
    bc.approved_by_id, bc.approved_at, bc.approved_signature_id = user.id, utcnow(), sig.id
    batch = session.get(ManufacturingBatch, bc.batch_id)
    lot = session.get(MaterialBatch, batch.output_lot_id)
    set_lot_cost(session, lot, bc.unit_cost, f"Approved batch cost {batch.batch_no}", user.id, basis="BATCH_COST", batch_cost_id=bc.id, currency=bc.currency)


def lines(bc: BatchCost) -> list[dict]:
    return json.loads(bc.lines_snapshot) if bc.lines_snapshot else []


# ------------------------------------------------------------------ valuation
def valuation(session: Session) -> dict:
    rows = session.execute(select(InventoryBalance.material_batch_id, func.sum(InventoryBalance.qty_on_hand)).where(InventoryBalance.qty_on_hand > 0)
                           .group_by(InventoryBalance.material_batch_id)).all()
    out, total, uncosted = [], D(0), 0
    for lot_id, qty in rows:
        lot = session.get(MaterialBatch, lot_id)
        lc = current_cost(session, lot_id)
        qty = D(str(qty))
        val = q4(qty * D(str(lc.unit_cost))) if lc else None
        if val is not None:
            total += val
        else:
            uncosted += 1
        out.append({"lot_id": lot_id, "lot_no": lot.lot_no, "material_id": lot.material_id, "disposition": lot.disposition, "qty_on_hand": str(qty),
                    "unit_cost": str(lc.unit_cost) if lc else None, "basis": lc.basis if lc else None, "value": str(val) if val is not None else None})
    return {"total_value": str(total), "lots": len(out), "uncosted_lots": uncosted, "items": out}
