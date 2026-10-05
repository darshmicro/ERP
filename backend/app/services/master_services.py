"""Vendor, material, location, equipment domain services."""
from datetime import date
from decimal import Decimal

from sqlalchemy import false as sa_false, true as sa_true
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import BusinessRuleError, Conflict, ValidationFailed
from app.core.time import utcnow
from app.models.master import (LOCATION_LEVELS, VENDOR_DOC_TYPES, Calibration, Category, Equipment, Location,
                               LocationCategory, LocationCompatRule, Material, Vendor, VendorDocument)
from app.models.platform import Document
from app.services import documents, masters, numbering, sod
from app.workflows.state_machine import StateMachine, Transition

# ---------------------------------------------------------------- vendor
VENDOR_MACHINE = StateMachine("vendor", "DRAFT", {
    "DRAFT": {"APPROVED": Transition("APPROVED", "md.vendor.approve", "APPROVED_BY", True)},
    "APPROVED": {"INACTIVE": Transition("INACTIVE", "md.vendor.deactivate", "APPROVED_BY", True)},
    "INACTIVE": {"APPROVED": Transition("APPROVED", "md.vendor.approve", "APPROVED_BY", True)},
})


def create_vendor(session: Session, data: dict, code: str | None = None) -> Vendor:
    code = code or numbering.next_number(session, numbering.default_plant_id(session), "VENDOR")
    masters.ensure_unique(session, Vendor, "vendor_code", code)
    if session.execute(select(Vendor.id).where(func.lower(Vendor.name) == data["name"].lower())).first():
        raise Conflict(f"A vendor named '{data['name']}' already exists")
    v = Vendor(vendor_code=code, approval_status="DRAFT", **data)
    session.add(v)
    session.flush()
    masters.record_author(session, v, "vendor.author")
    return v


def add_vendor_document(session: Session, vendor: Vendor, *, doc_type: str, filename: str, data: bytes,
                        doc_no: str | None, version: str, issue_date: date | None,
                        expiry_date: date | None) -> VendorDocument:
    if doc_type not in VENDOR_DOC_TYPES:
        raise ValidationFailed(f"Unknown document type '{doc_type}'")
    if issue_date and expiry_date and expiry_date < issue_date:
        raise ValidationFailed("Expiry date is before issue date")
    doc = documents.store(session, filename, data, doc_no=doc_no, version=version)
    vd = VendorDocument(vendor_id=vendor.id, document_id=doc.id, doc_type=doc_type, doc_no=doc_no,
                        version=version, issue_date=issue_date, expiry_date=expiry_date)
    session.add(vd)
    session.flush()
    masters.record_author(session, vd, "vendor_document.upload")
    return vd


def review_vendor_document(session: Session, vd: VendorDocument, user, approve: bool, comment: str) -> None:
    if not (comment or "").strip():
        raise ValidationFailed("A review comment is required", code="REASON_REQUIRED")
    sod.check(session, user.id, "vendor_document", vd.id, "vendor_document.review")
    vd.review_status = "APPROVED" if approve else "REJECTED"
    vd.reviewed_by_id = user.id
    vd.reviewed_at = utcnow()
    vd.review_comment = comment
    if approve:  # older approved documents of the same type are retained but no longer 'current'
        for old in session.execute(select(VendorDocument).where(
                VendorDocument.vendor_id == vd.vendor_id, VendorDocument.doc_type == vd.doc_type,
                VendorDocument.id != vd.id, VendorDocument.is_current == sa_true())).scalars():
            old.is_current = False
    sod.record_action(session, "vendor_document", vd.id, "vendor_document.review", user.id)


def vendor_documents(session: Session, vendor_id: int, today: date | None = None) -> list[dict]:
    today = today or date.today()
    rows = session.execute(select(VendorDocument, Document).join(Document, Document.id == VendorDocument.document_id)
                           .where(VendorDocument.vendor_id == vendor_id).order_by(VendorDocument.id.desc())).all()
    return [{"id": vd.id, "document_id": vd.document_id, "doc_type": vd.doc_type, "doc_no": vd.doc_no,
             "version": vd.version, "issue_date": vd.issue_date, "expiry_date": vd.expiry_date,
             "expired": bool(vd.expiry_date and vd.expiry_date < today), "review_status": vd.review_status,
             "reviewed_at": vd.reviewed_at, "is_current": vd.is_current, "filename": d.original_name,
             "sha256": d.sha256, "uploaded_at": d.uploaded_at} for vd, d in rows]


# ---------------------------------------------------------------- material
MATERIAL_MACHINE = StateMachine("material", "DRAFT", {
    "DRAFT": {"APPROVED": Transition("APPROVED", "md.material.approve", "QA_APPROVED", True)},
    "APPROVED": {"ACTIVE": Transition("ACTIVE", "md.material.approve", "QA_APPROVED", True),
                 "OBSOLETE": Transition("OBSOLETE", "md.material.deactivate", "APPROVED_BY", True)},
    "ACTIVE": {"OBSOLETE": Transition("OBSOLETE", "md.material.deactivate", "APPROVED_BY", True)},
})


def create_material(session: Session, data: dict, code: str | None = None) -> Material:
    code = code or numbering.next_number(session, numbering.default_plant_id(session), "MATERIAL")
    masters.ensure_unique(session, Material, "material_code", code)
    masters.check_foreign_keys(session, Material, data)
    _check_ranges(data)
    m = Material(material_code=code, master_status="DRAFT", barcode=code, **data)
    session.add(m)
    session.flush()
    masters.record_author(session, m, "material.author")
    return m


def _check_ranges(d: dict) -> None:
    for lo, hi, label in (("temp_min", "temp_max", "temperature"), ("humidity_min", "humidity_max", "humidity")):
        if d.get(lo) is not None and d.get(hi) is not None and Decimal(str(d[hi])) < Decimal(str(d[lo])):
            raise ValidationFailed(f"{label} maximum is below minimum")
    if d.get("retest_days") and d.get("shelf_life_days") and d["retest_days"] > d["shelf_life_days"]:
        raise ValidationFailed("Retest period cannot exceed shelf life")
    if d.get("min_stock") is not None and d.get("max_stock") is not None and Decimal(str(d["max_stock"])) < Decimal(str(d["min_stock"])):
        raise ValidationFailed("Maximum stock is below minimum stock")


def material_usable(m: Material) -> bool:
    """Used by PR/PO/GRN (later phases): only ACTIVE materials can be purchased/received."""
    return m.master_status == "ACTIVE"


# ---------------------------------------------------------------- locations
def _level(t: str) -> int:
    return LOCATION_LEVELS.index(t)


def validate_location(session: Session, data: dict, existing: Location | None = None) -> None:
    parent_id = data.get("parent_id", existing.parent_id if existing else None)
    ltype = data.get("location_type", existing.location_type if existing else None)
    wh = data.get("warehouse_id", existing.warehouse_id if existing else None)
    if ltype not in LOCATION_LEVELS:
        raise ValidationFailed(f"location_type must be one of {LOCATION_LEVELS}")
    if parent_id:
        parent = session.get(Location, parent_id)
        if parent is None:
            raise ValidationFailed("Unknown parent location")
        if parent.warehouse_id != wh:
            raise ValidationFailed("Parent location belongs to a different warehouse")
        if _level(ltype) <= _level(parent.location_type):
            raise ValidationFailed(f"A {ltype} cannot be placed under a {parent.location_type} "
                                   f"(hierarchy: {' > '.join(LOCATION_LEVELS)})")
    if existing is not None:
        changed_structure = ("parent_id" in data and data["parent_id"] != existing.parent_id) or \
                            ("location_type" in data and data["location_type"] != existing.location_type) or \
                            ("warehouse_id" in data and data["warehouse_id"] != existing.warehouse_id)
        has_children = session.execute(select(Location.id).where(Location.parent_id == existing.id)).first()
        if changed_structure and has_children:
            raise BusinessRuleError("Cannot restructure a location that has child locations", rule_id="LOC-001")
    _check_ranges(data)
    if data.get("capacity") is not None and Decimal(str(data["capacity"])) < 0:
        raise ValidationFailed("Capacity cannot be negative")


def create_location(session: Session, data: dict) -> Location:
    masters.ensure_unique(session, Location, "location_code", data["location_code"])
    masters.check_foreign_keys(session, Location, data)
    validate_location(session, data)
    loc = Location(**data)
    session.add(loc)
    session.flush()
    return loc


def location_path(session: Session, loc: Location) -> str:
    parts, cur = [], loc
    while cur is not None:
        parts.append(cur.location_code)
        cur = session.get(Location, cur.parent_id) if cur.parent_id else None
    return " > ".join(reversed(parts))


def allowed_categories(session: Session, location_id: int) -> set[int]:
    return set(session.execute(select(LocationCategory.category_id).where(
        LocationCategory.location_id == location_id, LocationCategory.revoked_at.is_(None))).scalars())


def set_location_categories(session: Session, loc: Location, category_ids: list[int]) -> None:
    for cid in category_ids:
        if session.get(Category, cid) is None:
            raise ValidationFailed(f"Unknown category {cid}")
    existing = {lc.category_id: lc for lc in session.execute(
        select(LocationCategory).where(LocationCategory.location_id == loc.id)).scalars()}
    for cid in category_ids:
        if cid not in existing:
            session.add(LocationCategory(location_id=loc.id, category_id=cid))
        elif existing[cid].revoked_at is not None:
            existing[cid].revoked_at = None
    for cid, lc in existing.items():
        if cid not in category_ids and lc.revoked_at is None:
            lc.revoked_at = utcnow()


def storage_violations(session: Session, loc: Location, material: Material,
                       categories_present: list[int] | None = None) -> list[str]:
    """Why `material` may not be stored in `loc` (empty list = OK). Used by GRN/put-away (Phase 4)."""
    out: list[str] = []
    if loc.status != "ACTIVE":
        out.append("Location is not active")
    allowed = allowed_categories(session, loc.id)
    if allowed and material.category_id not in allowed:
        out.append("Material category is not allowed in this location")
    if material.temp_min is not None and loc.temp_min is not None and material.temp_min < loc.temp_min:
        out.append("Location minimum temperature is above the material's required minimum")
    if material.temp_max is not None and loc.temp_max is not None and material.temp_max > loc.temp_max:
        out.append("Location maximum temperature is above the material's allowed maximum")
    if material.temp_min is not None and loc.temp_max is not None and loc.temp_max < material.temp_min:
        out.append("Location is colder than the material's storage range")
    if material.category_id and categories_present:
        for other in categories_present:
            pair = session.execute(select(LocationCompatRule).where(
                LocationCompatRule.allowed == sa_false(),
                ((LocationCompatRule.category_a_id == material.category_id) & (LocationCompatRule.category_b_id == other)) |
                ((LocationCompatRule.category_a_id == other) & (LocationCompatRule.category_b_id == material.category_id)))
            ).first()
            if pair:
                out.append("Incompatible with a material category already stored here")
                break
    return out


# ---------------------------------------------------------------- equipment & calibration
def calibration_status(eq: Equipment, on: date | None = None) -> str:
    on = on or date.today()
    if not eq.calibration_required:
        return "NOT_REQUIRED"
    if eq.calibration_due is None:
        return "NOT_CALIBRATED"
    return "VALID" if eq.calibration_due >= on else "EXPIRED"


def usable_for_testing(eq: Equipment, on: date | None = None) -> tuple[bool, str | None]:
    """Gate for QC testing / manufacturing (Phase 5/6): status, qualification and calibration."""
    if eq.status != "ACTIVE":
        return False, f"Equipment status is {eq.status}"
    if eq.qualification_status != "QUALIFIED":
        return False, f"Equipment qualification is {eq.qualification_status}"
    cs = calibration_status(eq, on)
    if cs in ("EXPIRED", "NOT_CALIBRATED"):
        return False, f"Calibration {cs}"
    return True, None


def add_calibration(session: Session, eq: Equipment, data: dict) -> Calibration:
    if data["due_on"] <= data["performed_on"]:
        raise ValidationFailed("Next due date must be after the calibration date")
    if data["performed_on"] > date.today():
        raise ValidationFailed("Calibration date cannot be in the future")
    cal = Calibration(equipment_id=eq.id, **data)
    session.add(cal)
    session.flush()
    latest = session.execute(select(func.max(Calibration.performed_on)).where(Calibration.equipment_id == eq.id)).scalar()
    if data["result"] == "PASS" and (latest is None or data["performed_on"] >= latest):
        eq.calibration_due = data["due_on"]
        if eq.status == "OUT_OF_SERVICE":
            eq.status = "ACTIVE"
    elif data["result"] == "FAIL":
        eq.status = "OUT_OF_SERVICE"
        eq.calibration_due = None
    return cal
