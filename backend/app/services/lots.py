"""Lot (material batch) rules: disposition machine, derived stock status, holds, issuability, FEFO, expiry job."""
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import BusinessRuleError, NotFound, PermissionDenied, ValidationFailed
from app.core.time import utcnow
from app.models.master import Material
from app.models.warehouse import InventoryBalance, MaterialBatch, QualityHold
from app.services import config_service, masters, notifications, numbering, sod
from app.workflows.state_machine import StateMachine, Transition, transition

T = Transition
LOT_MACHINE = StateMachine("material_batch", "QUARANTINE", {
    "QUARANTINE": {"QC_TESTING": T("QC_TESTING"), "REJECTED": T("REJECTED", "qa.lot.reject", "REJECTED_BY", True)},
    "QC_TESTING": {"QC_APPROVED": T("QC_APPROVED"), "REJECTED": T("REJECTED")},
    "QC_APPROVED": {"QA_REVIEW": T("QA_REVIEW"), "QC_TESTING": T("QC_TESTING", requires_reason=True), "REJECTED": T("REJECTED")},
    "QA_REVIEW": {"APPROVED": T("APPROVED"), "REJECTED": T("REJECTED"), "QC_TESTING": T("QC_TESTING", requires_reason=True)},
    "APPROVED": {"QC_TESTING": T("QC_TESTING", requires_reason=True), "EXPIRED": T("EXPIRED"),
                 "REJECTED": T("REJECTED", "qa.lot.reject", "REJECTED_BY", True), "RETURNED": T("RETURNED")},
    "EXPIRED": {"DESTROYED": T("DESTROYED")},
    "REJECTED": {"DESTROYED": T("DESTROYED")},
})
UNRELEASED = ("QUARANTINE", "QC_TESTING", "QC_APPROVED", "QA_REVIEW")


# ------------------------------------------------------------------ holds
def open_holds(session: Session, entity_type: str, record_id: int) -> list[QualityHold]:
    return list(session.execute(select(QualityHold).where(
        QualityHold.entity_type == entity_type, QualityHold.record_id == record_id, QualityHold.status == "OPEN")).scalars())


def has_open_hold(session: Session, entity_type: str, record_id: int) -> bool:
    return bool(open_holds(session, entity_type, record_id))


def place_hold(session: Session, entity_type: str, record_id: int, reason: str, *, source: str = "MANUAL",
               ref: str | None = None, user_id: int | None = None) -> QualityHold:
    if not (reason or "").strip():
        raise ValidationFailed("A reason is required to place a quality hold", code="REASON_REQUIRED")
    if entity_type == "MATERIAL_BATCH" and session.get(MaterialBatch, record_id) is None:
        raise NotFound("Lot not found")
    existing = session.execute(select(QualityHold).where(
        QualityHold.entity_type == entity_type, QualityHold.record_id == record_id, QualityHold.status == "OPEN",
        QualityHold.source == source, QualityHold.ref == ref)).scalars().first()
    if existing:
        return existing
    h = QualityHold(hold_no=numbering.next_number(session, numbering.default_plant_id(session), "HOLD"),
                    entity_type=entity_type, record_id=record_id, status="OPEN", source=source, reason=reason, ref=ref,
                    placed_by_id=user_id)
    session.add(h)
    session.flush()
    notifications.notify_roles(session, ["QA_OFFICER", "QA_HEAD"], category="QUALITY_HOLD",
                               title=f"Quality hold {h.hold_no} placed ({source})", body=reason,
                               ref_entity="quality_hold", ref_id=str(h.id))
    return h


def release_hold(session: Session, hold: QualityHold, user, password: str, reason: str) -> None:
    if hold.status != "OPEN":
        raise BusinessRuleError("Hold is already released", rule_id="BR-HOLD-004")
    mach = StateMachine("quality_hold", "OPEN", {"OPEN": {"RELEASED": T("RELEASED", "qa.hold.release", "RELEASED_BY", True)}})
    sig = masters.sign_and_transition(session, hold, mach, "RELEASED", user, password, reason=reason, meaning="RELEASED_BY")
    hold.released_by_id, hold.released_at, hold.release_reason, hold.release_signature_id = user.id, utcnow(), reason, sig.id


# ------------------------------------------------------------------ derived stock status & issuability
def derived_status(session: Session, lot: MaterialBatch, today: date | None = None, *, held: bool | None = None) -> str:
    today = today or date.today()
    if held is None:
        held = has_open_hold(session, "MATERIAL_BATCH", lot.id)
    if lot.disposition in ("REJECTED", "DESTROYED", "RETURNED"):
        return lot.disposition
    if held:
        return "HOLD"
    if lot.expiry_date and lot.expiry_date < today:
        return "EXPIRED"
    if lot.disposition == "APPROVED" and lot.retest_date and lot.retest_date < today:
        return "RETEST_DUE"
    return "QUARANTINE" if lot.disposition in ("QUARANTINE", "QC_TESTING", "QC_APPROVED", "QA_REVIEW") else lot.disposition


def issue_violations(session: Session, lot: MaterialBatch, today: date | None = None,
                     conditional_release_ok: bool = False) -> list[tuple[str, str]]:
    """Why a lot may not be issued/used (empty = OK). Rules BR-ISS-001/002/004, BR-HOLD-001/002."""
    today = today or date.today()
    out: list[tuple[str, str]] = []
    if lot.disposition == "REJECTED":
        out.append(("BR-ISS-002", f"Lot {lot.lot_no} is REJECTED and cannot be issued."))
    elif lot.disposition in UNRELEASED and not conditional_release_ok:
        out.append(("BR-ISS-001", f"Lot {lot.lot_no} is in {lot.disposition} (not released) and cannot be issued to production."))
    elif lot.disposition in ("EXPIRED", "DESTROYED", "RETURNED"):
        out.append(("BR-ISS-004", f"Lot {lot.lot_no} is {lot.disposition}."))
    if has_open_hold(session, "MATERIAL_BATCH", lot.id):
        out.append(("BR-HOLD-001", f"Lot {lot.lot_no} is on QUALITY HOLD."))
    if lot.expiry_date and lot.expiry_date < today:
        out.append(("BR-ISS-004", f"Lot {lot.lot_no} expired on {lot.expiry_date.isoformat()}."))
    if lot.disposition == "APPROVED" and lot.retest_date and lot.retest_date < today:
        out.append(("BR-ISS-004", f"Lot {lot.lot_no} retest date {lot.retest_date.isoformat()} has passed."))
    return out


def assert_issuable(session: Session, lot: MaterialBatch, today: date | None = None, conditional_release_ok: bool = False) -> None:
    v = issue_violations(session, lot, today, conditional_release_ok)
    if v:
        raise BusinessRuleError(v[0][1], rule_id=v[0][0], details=[{"rule_id": r, "message": m} for r, m in v])


def pick_fefo(session: Session, material_id: int, quantity: Decimal, today: date | None = None,
              location_ids: list[int] | None = None) -> list[dict]:
    """Allocate `quantity` from issuable lots in FEFO (or FIFO per material setting) order."""
    today = today or date.today()
    mat = session.get(Material, material_id)
    q = (select(MaterialBatch, InventoryBalance).join(InventoryBalance, InventoryBalance.material_batch_id == MaterialBatch.id)
         .where(MaterialBatch.material_id == material_id, MaterialBatch.disposition == "APPROVED",
                InventoryBalance.qty_on_hand - InventoryBalance.qty_reserved > 0))
    rows = session.execute(q).all()
    cands = []
    for lot, bal in rows:
        if location_ids and bal.location_id not in location_ids:
            continue
        if issue_violations(session, lot, today):
            continue
        cands.append((lot, bal))
    if mat.fefo_mode == "FEFO":
        cands.sort(key=lambda r: (r[0].expiry_date is None, r[0].expiry_date or date.max, r[0].created_at, r[0].id))
    else:
        cands.sort(key=lambda r: (r[0].created_at, r[0].id))
    need, out = Decimal(str(quantity)), []
    for lot, bal in cands:
        if need <= 0:
            break
        avail = bal.qty_on_hand - bal.qty_reserved
        take = min(avail, need)
        out.append({"lot_id": lot.id, "lot_no": lot.lot_no, "location_id": bal.location_id, "available": float(avail),
                    "take": float(take), "expiry_date": lot.expiry_date.isoformat() if lot.expiry_date else None})
        need -= take
    if need > 0:
        raise BusinessRuleError(f"Only {float(Decimal(str(quantity)) - need)} available from issuable lots", rule_id="BR-INV-002",
                                details=out)
    return out


# ------------------------------------------------------------------ jobs
def expire_lots(session: Session, today: date | None = None) -> list[int]:
    today = today or date.today()
    done = []
    for lot in session.execute(select(MaterialBatch).where(MaterialBatch.expiry_date < today,
                                                           MaterialBatch.disposition.in_(("APPROVED",) + UNRELEASED))).scalars():
        if lot.disposition != "APPROVED":
            continue   # unreleased lots stay controlled in quarantine; they can no longer be released (QA rejects)
        transition(session, LOT_MACHINE, lot, "EXPIRED", reason="Automatic: expiry date passed", module="warehouse")
        mat = session.get(Material, lot.material_id)
        notifications.notify_roles(session, ["WAREHOUSE_USER", "QA_OFFICER", "QA_HEAD"], category="EXPIRY",
                                   title=f"Lot expired: {lot.lot_no} ({mat.name})", ref_entity="material_batch", ref_id=str(lot.id))
        done.append(lot.id)
    return done


def alert_expiry(session: Session, today: date | None = None) -> int:
    today = today or date.today()
    ths = sorted({int(x) for x in (config_service.get(session, "expiry.alert_days", "90,60,30") or "").split(",") if x.strip()})
    if not ths:
        return 0
    n = 0
    hz = today + timedelta(days=max(ths))
    for lot in session.execute(select(MaterialBatch).where(MaterialBatch.disposition == "APPROVED",
                                                           ((MaterialBatch.expiry_date >= today) & (MaterialBatch.expiry_date <= hz)) |
                                                           ((MaterialBatch.retest_date >= today) & (MaterialBatch.retest_date <= hz)))).scalars():
        mat = session.get(Material, lot.material_id)
        for kind, d in (("expiry", lot.expiry_date), ("retest", lot.retest_date)):
            if d and today <= d <= hz:
                bucket = min(t for t in ths if (d - today).days <= t)
                n += notifications.notify_roles(session, ["WAREHOUSE_USER", "QA_OFFICER"], category="EXPIRY",
                                                title=f"{kind.title()} within {bucket} days: {lot.lot_no} ({mat.name})",
                                                body=f"{kind} date {d.isoformat()}", ref_entity="material_batch", ref_id=str(lot.id))
    return n
