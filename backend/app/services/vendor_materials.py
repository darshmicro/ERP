"""Vendor-material approval (spec 12, design decision C-03): the only record of 'approved vendor for material'."""
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy import inspect as sa_inspect

from app.core.errors import BusinessRuleError, Conflict, ValidationFailed
from app.core.time import utcnow
from app.models.master import Material, Vendor
from app.models.purchase import VendorMaterial
from app.services import masters
from app.workflows.state_machine import StateMachine, Transition, transition

T = Transition
VM_MACHINE = StateMachine("vendor_material", "DRAFT", {
    "DRAFT": {"UNDER_REVIEW": T("UNDER_REVIEW")},
    "UNDER_REVIEW": {"DRAFT": T("DRAFT", requires_reason=True),
                     "APPROVED": T("APPROVED", "vm.mapping.approve", "QA_APPROVED", True)},
    "APPROVED": {"SUPERSEDED": T("SUPERSEDED"), "WITHDRAWN": T("WITHDRAWN", "vm.mapping.withdraw", "APPROVED_BY", True)},
})


def _check_parties(session: Session, vendor_id: int, material_id: int) -> tuple[Vendor, Material]:
    v = session.get(Vendor, vendor_id)
    m = session.get(Material, material_id)
    if v is None or m is None:
        raise ValidationFailed("Unknown vendor or material")
    if v.approval_status != "APPROVED":
        raise BusinessRuleError("Vendor master record must be APPROVED", rule_id="VM-001")
    if m.master_status not in ("APPROVED", "ACTIVE"):
        raise BusinessRuleError("Material must be APPROVED or ACTIVE", rule_id="VM-002")
    return v, m


def create(session: Session, data: dict) -> VendorMaterial:
    _check_parties(session, data["vendor_id"], data["material_id"])
    open_ = session.execute(select(VendorMaterial.id).where(
        VendorMaterial.vendor_id == data["vendor_id"], VendorMaterial.material_id == data["material_id"],
        VendorMaterial.status.in_(("DRAFT", "UNDER_REVIEW")))).first()
    if open_:
        raise Conflict("A draft/under-review mapping already exists for this vendor and material")
    approved = session.execute(select(VendorMaterial.id).where(
        VendorMaterial.vendor_id == data["vendor_id"], VendorMaterial.material_id == data["material_id"],
        VendorMaterial.status == "APPROVED")).first()
    if approved:
        raise Conflict("An approved mapping exists; create a new version of it instead")
    latest = session.execute(select(VendorMaterial.version_no).where(
        VendorMaterial.vendor_id == data["vendor_id"], VendorMaterial.material_id == data["material_id"])
        .order_by(VendorMaterial.version_no.desc())).scalars().first() or 0
    vm = VendorMaterial(**data, version_no=latest + 1, status="DRAFT")
    session.add(vm)
    session.flush()
    masters.record_author(session, vm, "vendor_material.author")
    return vm


def new_version(session: Session, vm: VendorMaterial, reason: str) -> VendorMaterial:
    if not (reason or "").strip():
        raise ValidationFailed("A change reason is required", code="REASON_REQUIRED")
    if vm.status != "APPROVED":
        raise BusinessRuleError("Only the APPROVED mapping can be revised", rule_id="BR-HIS-001")
    if session.execute(select(VendorMaterial.id).where(
            VendorMaterial.vendor_id == vm.vendor_id, VendorMaterial.material_id == vm.material_id,
            VendorMaterial.status.in_(("DRAFT", "UNDER_REVIEW")))).first():
        raise Conflict("A newer draft already exists")
    latest = session.execute(select(VendorMaterial.version_no).where(
        VendorMaterial.vendor_id == vm.vendor_id, VendorMaterial.material_id == vm.material_id)
        .order_by(VendorMaterial.version_no.desc())).scalars().first()
    skip = {"id", "created_at", "created_by_id", "updated_at", "updated_by_id", "row_version", "status", "version_no",
            "effective_from", "effective_to", "approved_signature_id", "supersedes_id", "change_reason", "status_reason"}
    cols = {a.key: getattr(vm, a.key) for a in sa_inspect(VendorMaterial).column_attrs if a.key not in skip}
    new = VendorMaterial(**cols, version_no=latest + 1, status="DRAFT", supersedes_id=vm.id, change_reason=reason)
    session.add(new)
    session.flush()
    masters.record_author(session, new, "vendor_material.author")
    return new


def submit(session: Session, vm: VendorMaterial) -> None:
    _check_parties(session, vm.vendor_id, vm.material_id)
    transition(session, VM_MACHINE, vm, "UNDER_REVIEW", module="purchase")


def approve(session: Session, vm: VendorMaterial, user, password: str, reason: str) -> None:
    _check_parties(session, vm.vendor_id, vm.material_id)
    if vm.approved_to and vm.approved_to < date.today():
        raise ValidationFailed("approved_to date is in the past")
    sig = masters.sign_and_transition(session, vm, VM_MACHINE, "APPROVED", user, password, reason=reason,
                                      meaning="QA_APPROVED", sod_action="vendor_material.approve")
    now = utcnow()
    vm.effective_from, vm.approved_signature_id = now, sig.id
    for old in session.execute(select(VendorMaterial).where(
            VendorMaterial.vendor_id == vm.vendor_id, VendorMaterial.material_id == vm.material_id,
            VendorMaterial.status == "APPROVED", VendorMaterial.id != vm.id)).scalars():
        old.effective_to = now
        transition(session, VM_MACHINE, old, "SUPERSEDED", reason=f"superseded by v{vm.version_no}", module="purchase")


def withdraw(session: Session, vm: VendorMaterial, user, password: str, reason: str) -> None:
    masters.sign_and_transition(session, vm, VM_MACHINE, "WITHDRAWN", user, password, reason=reason,
                                meaning="APPROVED_BY")
    vm.effective_to = utcnow()
    vm.status_reason = reason


def approved_mapping(session: Session, vendor_id: int, material_id: int, today: date | None = None):
    today = today or date.today()
    vm = session.execute(select(VendorMaterial).where(
        VendorMaterial.vendor_id == vendor_id, VendorMaterial.material_id == material_id,
        VendorMaterial.status == "APPROVED").order_by(VendorMaterial.version_no.desc())).scalars().first()
    if vm is None or (vm.approved_to and vm.approved_to < today):
        return None
    return vm
