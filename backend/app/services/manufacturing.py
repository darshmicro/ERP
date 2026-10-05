"""Manufacturing: BOM, batches, material issue/return, MBR steps, IPC, reconciliation, output (spec 33-41, 68, 92)."""
import json
import re
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import BusinessRuleError, Conflict, NotFound, PermissionDenied, ValidationFailed
from app.core.time import utcnow
from app.models.manufacturing import (BatchEquipmentUse, BatchMaterial, BatchReconciliation, BatchStepExecution, BOMHeader, BOMLine,
                                      IPCResult, ManufacturingBatch, MaterialIssue, MaterialIssueIndent, MaterialReturn, MBRStep)
from app.models.master import Equipment, Location, Material, MaterialType
from app.models.warehouse import MaterialBatch, MaterialContainer
from app.services import config_service, inventory, lots, masters, notifications, numbering, qc, sod, versioning
from app.services import master_services as ms
from app.workflows.state_machine import StateMachine, Transition, transition

T = Transition
D = Decimal
BATCH_MACHINE = StateMachine("manufacturing_batch", "CREATED", {
    "CREATED": {"MATERIAL_ISSUED": T("MATERIAL_ISSUED"), "CANCELLED": T("CANCELLED", requires_reason=True)},
    "MATERIAL_ISSUED": {"IN_PROCESS": T("IN_PROCESS", "mfg.step.execute", "VERIFIED_BY", True)},
    "IN_PROCESS": {"PRODUCTION_COMPLETE": T("PRODUCTION_COMPLETE")},
    "PRODUCTION_COMPLETE": {"RECONCILED": T("RECONCILED")},
    "RECONCILED": {"QC_QA": T("QC_QA")},
    "QC_QA": {"RELEASED": T("RELEASED"), "REJECTED": T("REJECTED")},
})
RETURN_MACHINE = StateMachine("material_return", "REQUESTED", {"REQUESTED": {"ACCEPTED": T("ACCEPTED", "mfg.return.accept"), "REJECTED": T("REJECTED", "mfg.return.accept")}})
RECON_MACHINE = StateMachine("batch_reconciliation", "CALCULATED", {
    "CALCULATED": {"PRODUCTION_APPROVED": T("PRODUCTION_APPROVED", "mfg.reconciliation.approve", "APPROVED_BY", True),
                   "APPROVED": T("APPROVED", "mfg.reconciliation.approve", "APPROVED_BY", True)},
    "PRODUCTION_APPROVED": {"APPROVED": T("APPROVED", "mfg.reconciliation.qa_approve", "QA_APPROVED", True)},
})
PRODUCT_TYPES = ("SFG", "FG")
INPUT_TYPES_EXCLUDED = ("FG",)


def _plant(s: Session) -> int:
    return numbering.default_plant_id(s)


def _type_code(session: Session, mat: Material) -> str:
    return session.get(MaterialType, mat.type_id).code


# ================================================================== BOM
def _validate_bom_content(session: Session, hdr: BOMHeader, lines: list[dict]) -> None:
    prod = session.get(Material, hdr.product_material_id)
    if _type_code(session, prod) not in PRODUCT_TYPES:
        raise ValidationFailed("A BOM can only be created for a product of type SFG or FG")
    seen = set()
    for ln in lines:
        m = session.get(Material, ln["material_id"])
        if m is None:
            raise ValidationFailed("Unknown material on a BOM line")
        if m.id == prod.id:
            raise ValidationFailed("A product cannot be a component of its own BOM")
        if _type_code(session, m) in INPUT_TYPES_EXCLUDED:
            raise ValidationFailed(f"{m.material_code}: finished goods cannot be BOM inputs")
        if m.id in seen:
            raise ValidationFailed(f"{m.material_code} appears twice")
        seen.add(m.id)
        if D(str(ln["quantity"])) <= 0:
            raise ValidationFailed("BOM quantities must be positive")
        if ln.get("unit_id") and ln["unit_id"] != m.base_unit_id:
            raise ValidationFailed(f"{m.material_code}: unit must be the material's base unit")
        for f in ("process_loss_pct", "overage_pct"):
            if D(str(ln.get(f, 0))) < 0 or D(str(ln.get(f, 0))) > 100:
                raise ValidationFailed(f"{f} must be 0-100")


def create_bom(session: Session, header: dict, lines: list[dict], steps: list[dict], key: str | None = None) -> BOMHeader:
    prod = session.get(Material, header["product_material_id"])
    if prod is None:
        raise ValidationFailed("Unknown product")
    if _type_code(session, prod) not in PRODUCT_TYPES:
        raise ValidationFailed("A BOM can only be created for a product of type SFG or FG")
    bom = versioning.create_draft(session, BOMHeader, header, key)
    set_bom_lines(session, bom, lines)
    set_mbr_steps(session, bom, steps)
    return bom


def set_bom_lines(session: Session, bom: BOMHeader, lines: list[dict]) -> None:
    if bom.status != "DRAFT":
        raise BusinessRuleError("Only a DRAFT BOM can be edited; create a new version", rule_id="BR-HIS-001")
    _validate_bom_content(session, bom, lines)
    for old in session.execute(select(BOMLine).where(BOMLine.bom_id == bom.id)).scalars():
        session.delete(old)
    session.flush()
    for i, ln in enumerate(lines, 1):
        m = session.get(Material, ln["material_id"])
        pct = (D(str(ln["quantity"])) / bom.batch_size * 100) if (ln.get("unit_id") or m.base_unit_id) == bom.unit_id else None
        session.add(BOMLine(bom_id=bom.id, line_no=i, seq=i, unit_id=ln.get("unit_id") or m.base_unit_id, percentage=pct,
                            **{k: v for k, v in ln.items() if k != "unit_id"}))
    session.flush()


def set_mbr_steps(session: Session, bom: BOMHeader, steps: list[dict]) -> None:
    if bom.status != "DRAFT":
        raise BusinessRuleError("Only a DRAFT BOM can be edited; create a new version", rule_id="BR-HIS-001")
    for old in session.execute(select(MBRStep).where(MBRStep.bom_id == bom.id)).scalars():
        session.delete(old)
    session.flush()
    for i, st in enumerate(steps, 1):
        session.add(MBRStep(bom_id=bom.id, step_no=i, seq=i, **st))
    session.flush()


def bom_lines(session: Session, bom_id: int) -> list[BOMLine]:
    return list(session.execute(select(BOMLine).where(BOMLine.bom_id == bom_id).order_by(BOMLine.line_no)).scalars())


def bom_steps(session: Session, bom_id: int) -> list[MBRStep]:
    return list(session.execute(select(MBRStep).where(MBRStep.bom_id == bom_id).order_by(MBRStep.step_no)).scalars())


def submit_bom(session: Session, bom: BOMHeader) -> None:
    lines = bom_lines(session, bom.id)
    if not lines:
        raise ValidationFailed("A BOM needs at least one line before submission")
    versioning.submit(session, bom)


def approve_bom(session: Session, bom: BOMHeader, user, password: str, reason: str) -> None:
    prod = session.get(Material, bom.product_material_id)
    if prod.master_status != "ACTIVE":
        raise BusinessRuleError(f"Product {prod.material_code} is {prod.master_status}; it must be ACTIVE", rule_id="BR-BOM-001")
    for ln in bom_lines(session, bom.id):
        m = session.get(Material, ln.material_id)
        if m.master_status != "ACTIVE":
            raise BusinessRuleError(f"BOM material {m.material_code} is {m.master_status}, not ACTIVE", rule_id="BR-BOM-001")
    versioning.approve(session, bom, user, password, reason)


def bom_in_force(session: Session, product_id: int, on=None) -> BOMHeader | None:
    return versioning.version_in_force(session, BOMHeader, BOMHeader.product_material_id == product_id, on=on)


# ================================================================== batch
_BATCH_NO = re.compile(r"^[A-Za-z0-9._/-]{3,40}$")


def create_batch(session: Session, user, product_id: int, planned_qty: D, *, batch_no: str | None = None, override_reason: str | None = None,
                 can_override: bool = False) -> ManufacturingBatch:
    prod = session.get(Material, product_id)
    if prod is None:
        raise NotFound("Product not found")
    btype = _type_code(session, prod)
    if btype not in PRODUCT_TYPES:
        raise ValidationFailed("Batches are created for SFG or FG products")
    if prod.master_status != "ACTIVE":
        raise BusinessRuleError(f"Product {prod.material_code} is {prod.master_status}", rule_id="BR-BOM-001")
    bom = bom_in_force(session, product_id)
    if bom is None:
        raise BusinessRuleError("No approved, effective BOM exists for this product (BR-BOM-001)", rule_id="BR-BOM-001")
    planned = D(str(planned_qty))
    if planned <= 0:
        raise ValidationFailed("Planned quantity must be positive")
    if batch_no:
        if not can_override:
            raise PermissionDenied("You are not permitted to override the batch number")
        if not (override_reason or "").strip():
            raise ValidationFailed("A reason is required to override the batch number", code="REASON_REQUIRED")
        if not _BATCH_NO.match(batch_no):
            raise ValidationFailed("Batch number may contain letters, digits and . _ / - (3-40 characters)")
        if session.execute(select(ManufacturingBatch.id).where(func.lower(ManufacturingBatch.batch_no) == batch_no.lower())).first() or \
                session.execute(select(MaterialBatch.id).where(func.lower(MaterialBatch.lot_no) == batch_no.lower())).first():
            raise Conflict(f"Batch number '{batch_no}' already exists (duplicates are never allowed; cancelled numbers are not reused)")
    else:
        batch_no = numbering.next_number(session, _plant(session), btype)
    factor = planned / bom.batch_size
    b = ManufacturingBatch(batch_no=batch_no, batch_type=btype, product_material_id=product_id, bom_id=bom.id, planned_qty=planned,
                           unit_id=bom.unit_id, status="CREATED", created_by_user_id=user.id, number_override_reason=override_reason if batch_no and can_override and override_reason else None)
    session.add(b)
    session.flush()
    ind = MaterialIssueIndent(indent_no=numbering.next_number(session, _plant(session), "INDENT"), batch_id=b.id, status="OPEN")
    session.add(ind)
    for ln in bom_lines(session, bom.id):
        req = ln.quantity * factor * (1 + ln.overage_pct / 100)
        session.add(BatchMaterial(batch_id=b.id, bom_line_id=ln.id, material_id=ln.material_id, unit_id=ln.unit_id, required_qty=req, reconcile=ln.reconcile))
    session.flush()
    sod.record_action(session, "manufacturing_batch", b.id, "mfg.batch.create", user.id)
    return b


def batch_materials(session: Session, batch_id: int) -> list[BatchMaterial]:
    return list(session.execute(select(BatchMaterial).where(BatchMaterial.batch_id == batch_id).order_by(BatchMaterial.id)).scalars())


def cancel_batch(session: Session, b: ManufacturingBatch, reason: str) -> None:
    if session.execute(select(func.count()).select_from(MaterialIssue).where(MaterialIssue.batch_id == b.id)).scalar():
        raise BusinessRuleError("Material has been issued to this batch; it cannot be cancelled", rule_id="BR-BAT-002")
    transition(session, BATCH_MACHINE, b, "CANCELLED", reason=reason, module="manufacturing")
    b.cancel_reason = reason          # the batch number stays on record (never reused)


# ================================================================== issue / return
def _destination_ok(session: Session, lot: MaterialBatch, loc: Location) -> None:
    d = lot.disposition
    if d in lots.UNRELEASED and not loc.is_quarantine:
        raise BusinessRuleError("Unreleased material may only be stored in a quarantine location", rule_id="BR-QRN-001")
    if d == "APPROVED" and (loc.is_quarantine or loc.is_rejected_area):
        raise BusinessRuleError("Approved material cannot be placed in a quarantine or rejected area", rule_id="BR-QRN-002")


def issue_material(session: Session, user, batch: ManufacturingBatch, bm: BatchMaterial, lot: MaterialBatch, location_id: int, qty: D, *,
                   fefo_override_reason: str | None = None, additional: bool = False) -> MaterialIssue:
    qty = D(str(qty))
    if bm.batch_id != batch.id:
        raise ValidationFailed("Requirement does not belong to this batch")
    if batch.status not in ("CREATED", "MATERIAL_ISSUED", "IN_PROCESS"):
        raise BusinessRuleError(f"Batch is {batch.status}; material can no longer be issued", rule_id="BR-ISS-006")
    if lots.has_open_hold(session, "MFG_BATCH", batch.id):
        raise BusinessRuleError("The manufacturing batch is on quality hold", rule_id="BR-HOLD-002")
    if lot.material_id != bm.material_id:       # BR-ISS-003 / BR-TRC-001
        raise BusinessRuleError("The selected lot is not the material required by this BOM line", rule_id="BR-ISS-003")
    cr = None
    viol = lots.issue_violations(session, lot)
    if viol:
        cr = qc.active_conditional_release(session, lot, qty) if lot.disposition in lots.UNRELEASED else None
        if cr is not None and cr.intended_batch_ref and cr.intended_batch_ref != batch.batch_no:
            raise BusinessRuleError(f"The conditional release authorises use only in batch {cr.intended_batch_ref} (BR-CRL-003)", rule_id="BR-CRL-003")
        if cr is not None:
            viol = lots.issue_violations(session, lot, conditional_release_ok=True)
        if viol:
            raise BusinessRuleError(viol[0][1], rule_id=viol[0][0], details=[{"rule_id": r, "message": m} for r, m in viol])
    remaining = bm.required_qty - bm.issued_qty
    if qty > remaining and not additional:
        raise BusinessRuleError(f"Issue of {qty} exceeds the remaining requirement ({remaining}); an approved additional issue is required", rule_id="BR-ISS-006")
    if cr is None:       # FEFO/FIFO check applies to released stock
        try:
            pick = lots.pick_fefo(session, bm.material_id, min(qty, max(remaining, qty)))
        except BusinessRuleError:
            pick = []
        if pick and pick[0]["lot_id"] != lot.id and not (fefo_override_reason or "").strip():
            raise BusinessRuleError(f"{session.get(Material, lot.material_id).fefo_mode} order: lot {pick[0]['lot_no']} (expiry {pick[0]['expiry_date']}) must be issued first. "
                                    "A reason is required to deviate (BR-ISS-005).", rule_id="BR-ISS-005", details=pick)
    txn = inventory.post(session, txn_type="ISSUE", batch=lot, quantity=qty, from_location_id=location_id, ref_doc_type="MFG_BATCH", ref_doc_id=batch.batch_no)
    iss = MaterialIssue(issue_no=numbering.next_number(session, _plant(session), "ISSUE"), batch_id=batch.id, batch_material_id=bm.id,
                        material_batch_id=lot.id, location_id=location_id, quantity=qty, inventory_txn_id=txn.id,
                        conditional_release_id=cr.id if cr else None, fefo_override_reason=fefo_override_reason, is_additional=additional, issued_by_id=user.id)
    session.add(iss)
    session.flush()
    bm.issued_qty = bm.issued_qty + qty
    if cr is not None:
        cr.quantity_used = cr.quantity_used + qty
        batch.uses_conditional_release = True
    if batch.status == "CREATED":
        transition(session, BATCH_MACHINE, batch, "MATERIAL_ISSUED", reason="First material issued", module="manufacturing")
    ind = session.execute(select(MaterialIssueIndent).where(MaterialIssueIndent.batch_id == batch.id)).scalar_one()
    done = all(m.issued_qty >= m.required_qty for m in batch_materials(session, batch.id))
    ind.status = "ISSUED" if done else "PARTIAL"
    return iss


def request_return(session: Session, user, issue: MaterialIssue, returned: D, used: D, damaged: D, location: Location, reason: str) -> MaterialReturn:
    batch = session.get(ManufacturingBatch, issue.batch_id)
    if batch.status not in ("MATERIAL_ISSUED", "IN_PROCESS", "PRODUCTION_COMPLETE"):
        raise BusinessRuleError(f"Batch is {batch.status}; returns are not possible", rule_id="BR-RET-001")
    returned, used, damaged = D(str(returned)), D(str(used)), D(str(damaged))
    if returned <= 0 or used < 0 or damaged < 0:
        raise ValidationFailed("Returned quantity must be positive; used and damaged cannot be negative")
    done = D(str(session.execute(select(func.coalesce(func.sum(MaterialReturn.returned_qty), 0)).where(
        MaterialReturn.issue_id == issue.id, MaterialReturn.status.in_(("REQUESTED", "ACCEPTED")))).scalar()))
    if returned + used + damaged > issue.quantity or done + returned > issue.quantity:
        raise BusinessRuleError("Used + returned + damaged exceeds the issued quantity", rule_id="BR-RET-001")
    if not (reason or "").strip():
        raise ValidationFailed("A reason is required", code="REASON_REQUIRED")
    lot = session.get(MaterialBatch, issue.material_batch_id)
    _destination_ok(session, lot, location)
    r = MaterialReturn(return_no=numbering.next_number(session, _plant(session), "RETURN"), issue_id=issue.id, batch_id=batch.id,
                       batch_material_id=issue.batch_material_id, material_batch_id=lot.id, issued_qty=issue.quantity, used_qty=used,
                       returned_qty=returned, damaged_qty=damaged, location_id=location.id, reason=reason, status="REQUESTED", requested_by_id=user.id)
    session.add(r)
    session.flush()
    sod.record_action(session, "material_return", r.id, "mfg.return.request", user.id)
    return r


def accept_return(session: Session, user, ret: MaterialReturn, accept: bool, comment: str) -> None:
    sod.check(session, user.id, "material_return", ret.id, "mfg.return.accept")
    if not accept:
        transition(session, RETURN_MACHINE, ret, "REJECTED", reason=comment, module="manufacturing")
        ret.accepted_by_id, ret.accepted_at, ret.decision_comment = user.id, utcnow(), comment
        return
    lot = session.get(MaterialBatch, ret.material_batch_id)
    loc = session.get(Location, ret.location_id)
    _destination_ok(session, lot, loc)
    txn = inventory.post(session, txn_type="RETURN", batch=lot, quantity=ret.returned_qty, to_location_id=loc.id, ref_doc_type="MFG_RETURN", ref_doc_id=ret.return_no)
    bm = session.get(BatchMaterial, ret.batch_material_id)
    bm.returned_qty = bm.returned_qty + ret.returned_qty
    ret.accepted_by_id, ret.accepted_at, ret.ledger_txn_id, ret.decision_comment = user.id, utcnow(), txn.id, comment
    sod.record_action(session, "material_return", ret.id, "mfg.return.accept", user.id)
    transition(session, RETURN_MACHINE, ret, "ACCEPTED", reason=comment, module="manufacturing")


# ================================================================== process execution
def start_processing(session: Session, user, batch: ManufacturingBatch, password: str, reason: str) -> None:
    if batch.status != "MATERIAL_ISSUED":
        raise BusinessRuleError(f"Batch is {batch.status}", rule_id="BR-MFG-002")
    short = [session.get(Material, m.material_id).material_code for m in batch_materials(session, batch.id) if m.issued_qty < m.required_qty]
    if short:
        raise BusinessRuleError("Materials not fully issued: " + ", ".join(short), rule_id="BR-MFG-002", details=short)
    if lots.has_open_hold(session, "MFG_BATCH", batch.id):
        raise BusinessRuleError("The manufacturing batch is on quality hold", rule_id="BR-HOLD-002")
    sig = masters.sign_and_transition(session, batch, BATCH_MACHINE, "IN_PROCESS", user, password, reason=reason or "Line clearance confirmed", meaning="VERIFIED_BY")
    batch.line_clearance_signature_id, batch.start_at = sig.id, utcnow()
    for st in bom_steps(session, batch.bom_id):
        session.add(BatchStepExecution(batch_id=batch.id, step_no=st.step_no, instruction=st.instruction, requires_verification=st.requires_verification))
    session.flush()


def _in_process(batch: ManufacturingBatch) -> None:
    if batch.status != "IN_PROCESS":
        raise BusinessRuleError(f"Batch is {batch.status}; this action needs IN_PROCESS", rule_id="BR-MFG-002")


def use_equipment(session: Session, user, batch: ManufacturingBatch, equipment_id: int, cleaning_confirmed: bool) -> BatchEquipmentUse:
    _in_process(batch)
    eq = session.get(Equipment, equipment_id)
    if eq is None:
        raise NotFound("Equipment not found")
    ok, why = ms.usable_for_testing(eq)
    if not ok:
        raise BusinessRuleError(f"Equipment {eq.equipment_code} cannot be used: {why} (BR-MFG-001)", rule_id="BR-MFG-001")
    if not cleaning_confirmed:
        raise BusinessRuleError("Equipment cleaning status must be confirmed (BR-MFG-001)", rule_id="BR-MFG-001")
    u = BatchEquipmentUse(batch_id=batch.id, equipment_id=eq.id, used_by_id=user.id, calibration_status=ms.calibration_status(eq), cleaning_confirmed=True)
    session.add(u)
    session.flush()
    return u


def execute_step(session: Session, user, batch: ManufacturingBatch, step_no: int, value: str | None, remarks: str | None) -> BatchStepExecution:
    _in_process(batch)
    st = session.execute(select(BatchStepExecution).where(BatchStepExecution.batch_id == batch.id, BatchStepExecution.step_no == step_no)).scalar_one_or_none()
    if st is None:
        raise NotFound("Step not found")
    prev = session.execute(select(BatchStepExecution).where(BatchStepExecution.batch_id == batch.id, BatchStepExecution.step_no < step_no,
                                                            BatchStepExecution.performed_at.is_(None))).first()
    if prev:
        raise BusinessRuleError("Earlier steps must be executed first", rule_id="BR-MFG-004")
    if st.performed_at:
        raise BusinessRuleError("Step already executed (records are not overwritten)", rule_id="BR-HIS-001")
    st.recorded_value, st.remarks, st.performed_by_id, st.performed_at = value, remarks, user.id, utcnow()
    sod.record_action(session, "batch_step_execution", st.id, "mfg.step.perform", user.id)
    return st


def verify_step(session: Session, user, batch: ManufacturingBatch, step_no: int, password: str) -> BatchStepExecution:
    from app.services import esign
    _in_process(batch)
    st = session.execute(select(BatchStepExecution).where(BatchStepExecution.batch_id == batch.id, BatchStepExecution.step_no == step_no)).scalar_one_or_none()
    if st is None or not st.performed_at:
        raise BusinessRuleError("The step has not been executed yet", rule_id="BR-MFG-004")
    if not st.requires_verification:
        raise BusinessRuleError("This step needs no second verification", rule_id="BR-MFG-004")
    if st.verified_at:
        raise BusinessRuleError("Step already verified", rule_id="BR-HIS-001")
    sod.check(session, user.id, "batch_step_execution", st.id, "mfg.step.verify")
    sig = esign.sign(session, user, password, meaning="VERIFIED_BY", entity="batch_step_execution", record_id=st.id,
                     record_snapshot={"batch": batch.batch_no, "step": st.step_no, "value": st.recorded_value}, required_permission="mfg.step.verify")
    st.verified_by_id, st.verified_at, st.verify_signature_id = user.id, utcnow(), sig.id
    return st


def record_ipc(session: Session, user, batch: ManufacturingBatch, stage: str, parameter: str, *, value: D | None, text: str | None,
               lsl: D | None, usl: D | None, equipment_id: int | None, remarks: str | None) -> IPCResult:
    _in_process(batch)
    if equipment_id:
        eq = session.get(Equipment, equipment_id)
        ok, why = ms.usable_for_testing(eq) if eq else (False, "unknown equipment")
        if not ok:
            raise BusinessRuleError(f"Instrument cannot be used: {why} (BR-QC-002)", rule_id="BR-QC-002")
    if value is not None:
        v = D(str(value))
        pf = "PASS" if (lsl is None or v >= lsl) and (usl is None or v <= usl) else "FAIL"
    else:
        pf = "NA"
    r = IPCResult(batch_id=batch.id, stage=stage, parameter=parameter, value_numeric=value, value_text=text, lsl=lsl, usl=usl, pass_fail=pf,
                  equipment_id=equipment_id, analyst_id=user.id, remarks=remarks)
    session.add(r)
    session.flush()
    if pf == "FAIL":        # BR-MFG-003: hold + deviation prompt
        lots.place_hold(session, "MFG_BATCH", batch.id, f"IPC failure: {parameter} = {value} at stage '{stage}' (limits {lsl}–{usl})", source="OTHER",
                        ref=f"IPC{r.id}", user_id=user.id)
        notifications.notify_roles(session, ["QA_OFFICER", "QA_HEAD", "PRODUCTION_MANAGER"], category="IPC", title=f"IPC failure on batch {batch.batch_no}",
                                   body=f"{parameter}: {value}. Batch placed on hold; raise a deviation.", ref_entity="manufacturing_batch", ref_id=str(batch.id))
    return r


def complete_production(session: Session, user, batch: ManufacturingBatch, actual_qty: D) -> None:
    _in_process(batch)
    if lots.has_open_hold(session, "MFG_BATCH", batch.id):
        raise BusinessRuleError("The manufacturing batch is on quality hold", rule_id="BR-HOLD-002")
    open_steps = session.execute(select(BatchStepExecution).where(BatchStepExecution.batch_id == batch.id)).scalars().all()
    pend = [s.step_no for s in open_steps if not s.performed_at or (s.requires_verification and not s.verified_at)]
    if pend:
        raise BusinessRuleError(f"Steps not executed/verified: {pend}", rule_id="BR-MFG-004", details=pend)
    actual = D(str(actual_qty))
    if actual <= 0:
        raise ValidationFailed("Actual quantity must be positive")
    batch.actual_qty, batch.end_at = actual, utcnow()
    batch.yield_pct = (actual / batch.planned_qty * 100).quantize(D("0.01"))
    transition(session, BATCH_MACHINE, batch, "PRODUCTION_COMPLETE", reason=f"Actual {actual}", module="manufacturing")


# ================================================================== reconciliation
def record_consumption(session: Session, batch: ManufacturingBatch, entries: list[dict]) -> None:
    if batch.status not in ("IN_PROCESS", "PRODUCTION_COMPLETE"):
        raise BusinessRuleError(f"Batch is {batch.status}", rule_id="BR-REC-001")
    bms = {m.id: m for m in batch_materials(session, batch.id)}
    for e in entries:
        m = bms.get(e["batch_material_id"])
        if m is None:
            raise ValidationFailed("Unknown batch material")
        for k in ("consumed", "sampled", "waste"):
            if D(str(e.get(k, 0))) < 0:
                raise ValidationFailed(f"{k} cannot be negative")
        m.consumed_qty, m.sample_qty, m.waste_qty = D(str(e.get("consumed", 0))), D(str(e.get("sampled", 0))), D(str(e.get("waste", 0)))


def reconcile(session: Session, batch: ManufacturingBatch) -> BatchReconciliation:
    if batch.status != "PRODUCTION_COMPLETE":
        raise BusinessRuleError("Reconcile after production is complete", rule_id="BR-REC-001")
    existing = session.execute(select(BatchReconciliation).where(BatchReconciliation.batch_id == batch.id)).scalar_one_or_none()
    if existing and existing.status != "CALCULATED":
        raise BusinessRuleError("The reconciliation is already under approval", rule_id="BR-REC-001")
    tol = D(str(config_service.get(session, "recon.tolerance_pct", "0.5") or "0.5"))
    lines, ok = [], True
    for m in batch_materials(session, batch.id):
        if not m.reconcile:
            continue
        if m.consumed_qty is None:
            raise BusinessRuleError(f"Consumption not entered for {session.get(Material, m.material_id).material_code}", rule_id="BR-REC-001")
        accounted = m.consumed_qty + m.sample_qty + m.waste_qty + m.returned_qty
        unacc = m.issued_qty - accounted
        var = (abs(unacc) / m.issued_qty * 100) if m.issued_qty > 0 else D(0)
        within = var <= tol
        ok = ok and within
        mat = session.get(Material, m.material_id)
        lines.append({"batch_material_id": m.id, "material": f"{mat.material_code} {mat.name}", "issued": float(m.issued_qty), "consumed": float(m.consumed_qty),
                      "sampled": float(m.sample_qty), "waste": float(m.waste_qty), "returned": float(m.returned_qty), "unaccounted": float(unacc),
                      "variance_pct": float(round(var, 3)), "within_tolerance": within})
    bom = session.get(BOMHeader, batch.bom_id)
    yield_ok = True
    if batch.yield_pct is not None:
        if bom.yield_min_pct is not None and batch.yield_pct < bom.yield_min_pct:
            yield_ok = False
        if bom.yield_max_pct is not None and batch.yield_pct > bom.yield_max_pct:
            yield_ok = False
    summary = json.dumps({"lines": lines, "yield_pct": float(batch.yield_pct or 0), "tolerance_pct": float(tol)})
    if existing:
        session.delete(existing)
        session.flush()
    rec = BatchReconciliation(batch_id=batch.id, status="CALCULATED", within_tolerance=ok, yield_ok=yield_ok, tolerance_pct=tol, summary_json=summary)
    session.add(rec)
    session.flush()
    return rec


def approve_reconciliation_production(session: Session, user, batch: ManufacturingBatch, rec: BatchReconciliation, password: str, reason: str) -> None:
    if rec.status != "CALCULATED":
        raise BusinessRuleError("Already approved by production", rule_id="BR-REC-001")
    final = rec.within_tolerance and rec.yield_ok
    sig = masters.sign_and_transition(session, rec, RECON_MACHINE, "APPROVED" if final else "PRODUCTION_APPROVED", user, password, reason=reason,
                                      meaning="APPROVED_BY", sod_action=None)
    rec.production_approved_by_id, rec.production_signature_id = user.id, sig.id
    sod.record_action(session, "batch_reconciliation", rec.id, "mfg.reconciliation.production_approve", user.id)
    if final:
        rec.approved_at = utcnow()
        transition(session, BATCH_MACHINE, batch, "RECONCILED", reason="Reconciliation within tolerance", module="manufacturing")


def approve_reconciliation_qa(session: Session, user, batch: ManufacturingBatch, rec: BatchReconciliation, password: str, deviation_ref: str, justification: str) -> None:
    if rec.status != "PRODUCTION_APPROVED":
        raise BusinessRuleError("QA approval applies after production approval of an out-of-tolerance reconciliation", rule_id="BR-REC-001")
    if not (deviation_ref or "").strip() or not (justification or "").strip():
        raise ValidationFailed("A deviation reference and justification are required for an out-of-tolerance reconciliation", code="REASON_REQUIRED")
    sod.check(session, user.id, "batch_reconciliation", rec.id, "mfg.reconciliation.qa_approve")
    sig = masters.sign_and_transition(session, rec, RECON_MACHINE, "APPROVED", user, password, reason=justification, meaning="QA_APPROVED")
    rec.qa_approved_by_id, rec.qa_signature_id, rec.deviation_ref, rec.justification, rec.approved_at = user.id, sig.id, deviation_ref, justification, utcnow()
    transition(session, BATCH_MACHINE, batch, "RECONCILED", reason=f"Out-of-tolerance reconciliation accepted ({deviation_ref})", module="manufacturing")


# ================================================================== output lot
def create_output(session: Session, user, batch: ManufacturingBatch, quarantine_location: Location) -> MaterialBatch:
    if batch.status != "RECONCILED":
        raise BusinessRuleError("Output can be booked after the reconciliation is approved", rule_id="BR-REC-001")
    if not quarantine_location.is_quarantine or quarantine_location.status != "ACTIVE":
        raise BusinessRuleError("Output must be placed in an active quarantine location", rule_id="BR-QRN-001")
    prod = session.get(Material, batch.product_material_id)
    spec = versioning.current_spec_for_material(session, prod.id)
    exp = date.today() + timedelta(days=prod.shelf_life_days) if prod.shelf_life_days else None
    rt = date.today() + timedelta(days=prod.retest_days) if prod.retest_days else None
    lot = MaterialBatch(lot_no=batch.batch_no, material_id=prod.id, source_type="MFG", manufacturing_batch_id=batch.id, quantity=batch.actual_qty,
                        unit_id=batch.unit_id, mfg_date=date.today(), expiry_date=exp, retest_date=rt, disposition="QUARANTINE",
                        specification_id=spec.id if spec else None)
    session.add(lot)
    session.flush()
    session.add(MaterialContainer(batch_id=lot.id, container_no=1, quantity=batch.actual_qty))
    inventory.post(session, txn_type="OUTPUT", batch=lot, quantity=batch.actual_qty, to_location_id=quarantine_location.id, ref_doc_type="MFG_BATCH", ref_doc_id=batch.batch_no)
    batch.output_lot_id = lot.id
    transition(session, BATCH_MACHINE, batch, "QC_QA", reason=f"Output lot {lot.lot_no} in quarantine", module="manufacturing")
    return lot


def on_lot_released(session: Session, lot: MaterialBatch, outcome: str) -> None:
    """Called by the release workflow when an output lot reaches APPROVED / REJECTED."""
    if not lot.manufacturing_batch_id:
        return
    b = session.get(ManufacturingBatch, lot.manufacturing_batch_id)
    if b is not None and b.status == "QC_QA":
        transition(session, BATCH_MACHINE, b, "RELEASED" if outcome == "APPROVED" else "REJECTED", reason=f"Output lot {outcome}", module="manufacturing")


def conditional_material_problems(session: Session, lot: MaterialBatch) -> list[str]:
    """BR-CRL-004: a batch that consumed conditionally-released material cannot be released until that material is finally APPROVED."""
    if not lot.manufacturing_batch_id:
        return []
    out = []
    for iss in session.execute(select(MaterialIssue).where(MaterialIssue.batch_id == lot.manufacturing_batch_id, MaterialIssue.conditional_release_id.is_not(None))).scalars():
        src = session.get(MaterialBatch, iss.material_batch_id)
        if src.disposition != "APPROVED":
            out.append(f"Batch used conditionally released lot {src.lot_no} which is {src.disposition} (BR-CRL-004)")
    return out
