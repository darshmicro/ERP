"""Goods receipt: GRN, configurable checklist, lot creation, auto-quarantine, PO receipt tracking (spec 18-20)."""
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import BusinessRuleError, NotFound, PermissionDenied, ValidationFailed
from app.core.time import utcnow
from app.models.master import Location, Material, Vendor
from app.models.purchase import PurchaseOrder, PurchaseOrderLine
from app.models.warehouse import (GRN, ChecklistItem, GRNChecklist, GRNLine, MaterialBatch, MaterialContainer)
from app.services import config_service, inventory, lots, masters, numbering, sod
from app.services import master_services as ms
from app.services import purchasing as pur
from app.services import vendor_qualification as vqs
from app.services import versioning
from app.workflows.state_machine import StateMachine, Transition, transition

T = Transition
GRN_MACHINE = StateMachine("grn", "DRAFT", {
    "DRAFT": {"SUBMITTED": T("SUBMITTED"), "CANCELLED": T("CANCELLED", requires_reason=True)},
    "SUBMITTED": {"VERIFIED": T("VERIFIED", "grn.receipt.verify", "VERIFIED_BY", True),
                  "REJECTED": T("REJECTED", "grn.receipt.reject", "REJECTED_BY", True), "DRAFT": T("DRAFT", requires_reason=True)},
    "VERIFIED": {"QUARANTINE": T("QUARANTINE")},
})
DEFAULT_CHECKLIST = [
    ("PO_AVAILABLE", "Purchase order available", True), ("APPROVED_VENDOR", "Approved vendor", True),
    ("CORRECT_MATERIAL", "Correct material", True), ("CORRECT_CODE", "Correct material code", True),
    ("QTY_VERIFIED", "Quantity verified", True), ("CONTAINER_INTEGRITY", "Container integrity", True),
    ("LABEL_VERIFIED", "Label verified", False), ("BATCH_VERIFIED", "Batch number verified", True),
    ("MFG_DATE", "Manufacturing date", False), ("EXPIRY_DATE", "Expiry date", True), ("RETEST_DATE", "Retest date", False),
    ("COA_AVAILABLE", "CoA available", True), ("TRANSPORT_CONDITION", "Transport condition", False),
    ("STORAGE_CONDITION", "Storage condition", False), ("TAMPER_EVIDENCE", "Tamper evidence", True),
    ("DAMAGE_CHECK", "Damage check", False), ("MOISTURE_CHECK", "Moisture check (where applicable)", False),
    ("TEMP_LOGGER", "Temperature logger reviewed", False), ("SPECIAL_CONDITIONS", "Special conditions checked", False),
]


def seed_checklist(session: Session) -> None:
    for i, (code, text, crit) in enumerate(DEFAULT_CHECKLIST):
        if session.execute(select(ChecklistItem.id).where(ChecklistItem.code == code)).first() is None:
            session.add(ChecklistItem(code=code, text=text, is_critical=crit, seq=(i + 1) * 10))


def _plant(session: Session) -> int:
    return numbering.default_plant_id(session)


# ------------------------------------------------------------------ create / edit
def _validate_lines(session: Session, po: PurchaseOrder, lines: list[dict], *, exclude_grn: int | None = None) -> None:
    if po.status not in ("APPROVED", "PARTIALLY_RECEIVED"):
        raise BusinessRuleError(f"PO {po.po_no} is {po.status}; goods can only be received against an approved PO", rule_id="BR-GRN-001")
    if not lines:
        raise ValidationFailed("A GRN needs at least one line")
    tol = Decimal(config_service.get(session, "grn.over_delivery_tolerance_pct", "0") or 0)
    today = date.today()
    per_po_line: dict[int, Decimal] = {}
    for ln in lines:
        pol = session.get(PurchaseOrderLine, ln["po_line_id"])
        if pol is None or pol.po_id != po.id:
            raise ValidationFailed("po_line_id does not belong to this purchase order")
        mat = session.get(Material, pol.material_id)
        q = Decimal(str(ln["quantity_received"]))
        if q <= 0:
            raise ValidationFailed("Received quantity must be positive")
        per_po_line[pol.id] = per_po_line.get(pol.id, Decimal(0)) + q
        if pol.received_quantity + per_po_line[pol.id] > pol.quantity * (1 + tol / 100):
            raise BusinessRuleError(f"Receipt of {mat.material_code} exceeds the ordered quantity (ordered {pol.quantity}, "
                                    f"already received {pol.received_quantity}, tolerance {tol}%)", rule_id="BR-GRN-001")
        mfg, exp, rt = ln.get("mfg_date"), ln.get("expiry_date"), ln.get("retest_date")
        if mfg and exp and exp < mfg:
            raise BusinessRuleError("Expiry date is before manufacturing date", rule_id="BR-GRN-003")
        if exp and exp <= today:
            raise BusinessRuleError(f"{mat.material_code}: material is already expired and cannot be received", rule_id="BR-GRN-003")
        if rt and exp and rt > exp:
            raise BusinessRuleError("Retest date is after expiry date", rule_id="BR-GRN-003")
        if mat.shelf_life_days and not exp:
            raise BusinessRuleError(f"{mat.material_code} has a shelf life: expiry date is mandatory", rule_id="BR-GRN-003")
        if not (ln.get("vendor_batch_no") or "").strip():
            raise ValidationFailed("Vendor batch number is required")
        pack = ln.get("pack_count", 1)
        if pack < 1 or pack > 5000:
            raise ValidationFailed("pack_count must be between 1 and 5000")


def create_grn(session: Session, user, po: PurchaseOrder, header: dict, lines: list[dict]) -> GRN:
    _validate_lines(session, po, lines)
    g = GRN(grn_no=numbering.next_number(session, _plant(session), "GRN"), grn_date=date.today(), po_id=po.id,
            vendor_id=po.vendor_id, received_by_id=user.id, status="DRAFT", **header)
    session.add(g)
    session.flush()
    _write_lines(session, g, lines)
    sod.record_action(session, "grn", g.id, "grn.receipt.create", user.id)
    return g


def _write_lines(session: Session, g: GRN, lines: list[dict]) -> None:
    for old in session.execute(select(GRNLine).where(GRNLine.grn_id == g.id)).scalars():
        session.delete(old)
    session.flush()
    for i, ln in enumerate(lines, 1):
        pol = session.get(PurchaseOrderLine, ln["po_line_id"])
        mat = session.get(Material, pol.material_id)
        rt = ln.get("retest_date")
        if not rt and mat.retest_days and ln.get("mfg_date"):
            rt = ln["mfg_date"] + timedelta(days=mat.retest_days)
        data = {k: v for k, v in ln.items() if k not in ("retest_date",)}
        session.add(GRNLine(grn_id=g.id, line_no=i, material_id=pol.material_id, unit_id=pol.unit_id, retest_date=rt, **data))
    session.flush()


def replace_lines(session: Session, g: GRN, lines: list[dict]) -> None:
    if g.status != "DRAFT":
        raise BusinessRuleError("Only a DRAFT GRN can be edited", rule_id="BR-HIS-001")
    _validate_lines(session, session.get(PurchaseOrder, g.po_id), lines)
    _write_lines(session, g, lines)


def submit(session: Session, g: GRN, user) -> list[str]:
    if g.received_by_id != user.id:
        raise PermissionDenied("Only the receiver can submit the GRN")
    lines = _lines(session, g)
    po = session.get(PurchaseOrder, g.po_id)
    _validate_lines(session, po, [{"po_line_id": l.po_line_id, "quantity_received": l.quantity_received, "mfg_date": l.mfg_date,
                                   "expiry_date": l.expiry_date, "retest_date": l.retest_date, "vendor_batch_no": l.vendor_batch_no,
                                   "pack_count": l.pack_count} for l in lines])
    warnings = []
    st = vqs.standing(session, g.vendor_id)
    if not st.purchasable:       # BR-GRN-005: receive, but the lots are placed on hold at verification
        warnings.append(f"Vendor qualification problem at receipt ({st.message}); lots will be placed on quality hold.")
    transition(session, GRN_MACHINE, g, "SUBMITTED", module="warehouse")
    return warnings


def _lines(session: Session, g: GRN) -> list[GRNLine]:
    return list(session.execute(select(GRNLine).where(GRNLine.grn_id == g.id).order_by(GRNLine.line_no)).scalars())


# ------------------------------------------------------------------ checklist
def checklist_items(session: Session) -> list[ChecklistItem]:
    return list(session.execute(select(ChecklistItem).where(ChecklistItem.is_active == True).order_by(ChecklistItem.seq)).scalars())  # noqa: E712


def save_checklist(session: Session, g: GRN, user, answers: list[dict]) -> None:
    if g.status not in ("DRAFT", "SUBMITTED"):
        raise BusinessRuleError("The checklist can only be changed before verification", rule_id="BR-HIS-001")
    items = {i.id: i for i in checklist_items(session)}
    for a in answers:
        it = items.get(a["item_id"])
        if it is None:
            raise ValidationFailed("Unknown checklist item")
        if a["answer"] not in ("YES", "NO", "NA"):
            raise ValidationFailed("answer must be YES, NO or NA")
        if a["answer"] == "NO" and not (a.get("comment") or "").strip():
            raise ValidationFailed(f"A comment is required when '{it.text}' is NO")
        row = session.execute(select(GRNChecklist).where(GRNChecklist.grn_id == g.id, GRNChecklist.item_id == it.id)).scalar_one_or_none()
        if row is None:
            session.add(GRNChecklist(grn_id=g.id, item_id=it.id, answer=a["answer"], comment=a.get("comment")))
        else:
            if row.exception_signature_id and (row.answer != a["answer"]):
                raise BusinessRuleError("A QA exception was granted for this item; it cannot be changed", rule_id="BR-GRN-004")
            row.answer, row.comment = a["answer"], a.get("comment")
    session.flush()


def checklist_state(session: Session, g: GRN) -> dict:
    items = checklist_items(session)
    rows = {r.item_id: r for r in session.execute(select(GRNChecklist).where(GRNChecklist.grn_id == g.id)).scalars()}
    unanswered = [i.text for i in items if i.id not in rows]
    blocking = [i.text for i in items if i.id in rows and rows[i.id].answer == "NO" and i.is_critical and not rows[i.id].exception_signature_id]
    return {"complete": not unanswered, "unanswered": unanswered, "critical_failures": blocking,
            "items": [{"item_id": i.id, "code": i.code, "text": i.text, "critical": i.is_critical,
                       "answer": rows[i.id].answer if i.id in rows else None, "comment": rows[i.id].comment if i.id in rows else None,
                       "exception_ref": rows[i.id].exception_ref if i.id in rows else None,
                       "exception_granted": bool(i.id in rows and rows[i.id].exception_signature_id)} for i in items]}


def grant_exception(session: Session, g: GRN, user, password: str, item_id: int, ref: str, reason: str) -> None:
    """QA accepts a critical checklist failure for this receipt (signed, with a deviation/exception reference)."""
    from app.services import esign
    if g.status != "SUBMITTED":
        raise BusinessRuleError("Exceptions can only be granted while the GRN awaits verification", rule_id="BR-GRN-004")
    if not (ref or "").strip() or not (reason or "").strip():
        raise ValidationFailed("An exception reference and reason are required", code="REASON_REQUIRED")
    row = session.execute(select(GRNChecklist).where(GRNChecklist.grn_id == g.id, GRNChecklist.item_id == item_id)).scalar_one_or_none()
    if row is None or row.answer != "NO":
        raise ValidationFailed("There is no failed answer for this item")
    sig = esign.sign(session, user, password, meaning="APPROVED_BY", entity="grn_checklist", record_id=row.id,
                     record_snapshot={"grn": g.grn_no, "item": item_id, "ref": ref}, reason=reason, required_permission="grn.receipt.exception")
    row.exception_ref, row.exception_signature_id = ref, sig.id


# ------------------------------------------------------------------ verify -> lots in quarantine
def verify(session: Session, g: GRN, user, password: str, quarantine_location: Location, reason: str) -> list[MaterialBatch]:
    sod.check(session, user.id, "grn", g.id, "grn.receipt.verify")          # second-person verification
    cs = checklist_state(session, g)
    if not cs["complete"]:
        raise BusinessRuleError("Checklist incomplete: " + "; ".join(cs["unanswered"][:5]), rule_id="BR-GRN-004", details=cs["unanswered"])
    if cs["critical_failures"]:
        raise BusinessRuleError("Critical checklist failure(s): " + "; ".join(cs["critical_failures"]) +
                                ". Reject the receipt or obtain a QA exception.", rule_id="BR-GRN-004", details=cs["critical_failures"])
    if quarantine_location.status != "ACTIVE" or not quarantine_location.is_quarantine:
        raise BusinessRuleError("Receipts must be placed in an active quarantine location", rule_id="BR-QRN-001")
    lines = _lines(session, g)
    po = session.get(PurchaseOrder, g.po_id)
    _validate_lines(session, po, [{"po_line_id": l.po_line_id, "quantity_received": l.quantity_received, "mfg_date": l.mfg_date,
                                   "expiry_date": l.expiry_date, "retest_date": l.retest_date, "vendor_batch_no": l.vendor_batch_no,
                                   "pack_count": l.pack_count} for l in lines])
    for l in lines:   # storage rules for the quarantine location
        viol = [v for v in ms.storage_violations(session, quarantine_location, session.get(Material, l.material_id)) if "category" not in v]
        if viol:
            raise BusinessRuleError("Quarantine location unsuitable: " + "; ".join(viol), rule_id="BR-LOC-001", details=viol)
    sig_row = masters.sign_and_transition(session, g, GRN_MACHINE, "VERIFIED", user, password, reason=reason, meaning="VERIFIED_BY")
    g.checklist_passed, g.verified_by_id, g.quarantine_location_id = not cs["critical_failures"], user.id, quarantine_location.id
    st = vqs.standing(session, g.vendor_id)
    created = []
    for l in lines:
        mat = session.get(Material, l.material_id)
        spec = versioning.current_spec_for_material(session, mat.id)
        lot = MaterialBatch(lot_no=numbering.next_number(session, _plant(session), "LOT"), material_id=mat.id, source_type="GRN",
                            grn_line_id=l.id, vendor_id=g.vendor_id, vendor_batch_no=l.vendor_batch_no, mfg_date=l.mfg_date,
                            expiry_date=l.expiry_date, retest_date=l.retest_date, quantity=l.quantity_received, unit_id=l.unit_id,
                            disposition="QUARANTINE", specification_id=spec.id if spec else None)
        session.add(lot)
        session.flush()
        per = (l.quantity_received / l.pack_count)
        for n in range(1, l.pack_count + 1):
            session.add(MaterialContainer(batch_id=lot.id, container_no=n, quantity=per if n < l.pack_count else l.quantity_received - per * (l.pack_count - 1)))
        inventory.post(session, txn_type="RECEIPT", batch=lot, quantity=l.quantity_received, to_location_id=quarantine_location.id,
                       ref_doc_type="GRN", ref_doc_id=g.grn_no, signature_id=sig_row.id)
        l.material_batch_id = lot.id
        pol = session.get(PurchaseOrderLine, l.po_line_id)
        pol.received_quantity = pol.received_quantity + l.quantity_received
        if not st.purchasable:
            lots.place_hold(session, "MATERIAL_BATCH", lot.id, f"Vendor qualification problem at receipt: {st.message}",
                            source="GRN", ref=g.grn_no, user_id=user.id)
        created.append(lot)
    session.flush()
    _update_po_status(session, po)
    transition(session, GRN_MACHINE, g, "QUARANTINE", reason="Lots created in quarantine", module="warehouse")
    return created


def _update_po_status(session: Session, po: PurchaseOrder) -> None:
    pls = session.execute(select(PurchaseOrderLine).where(PurchaseOrderLine.po_id == po.id)).scalars().all()
    done = all(l.received_quantity >= l.quantity for l in pls)
    target = "CLOSED" if done else "PARTIALLY_RECEIVED"
    if po.status == "APPROVED" and target == "PARTIALLY_RECEIVED":
        transition(session, pur.PO_MACHINE, po, "PARTIALLY_RECEIVED", reason="Goods received", module="purchase")
    elif target == "CLOSED" and po.status in ("APPROVED", "PARTIALLY_RECEIVED"):
        transition(session, pur.PO_MACHINE, po, "CLOSED", reason="Fully received", module="purchase")


def reject(session: Session, g: GRN, user, password: str, reason: str) -> None:
    masters.sign_and_transition(session, g, GRN_MACHINE, "REJECTED", user, password, reason=reason, meaning="REJECTED_BY")
    g.reject_reason = reason


def cancel(session: Session, g: GRN, reason: str) -> None:
    transition(session, GRN_MACHINE, g, "CANCELLED", reason=reason, module="warehouse")
