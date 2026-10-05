"""Master data endpoints (Phase 2): units, types, categories, customers, warehouses, equipment,
vendors (+documents), materials, locations."""
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.crud import crud_router, to_dict, xlsx_response
from app.api.deps import Principal, get_db, require
from app.api.helpers import page_args, use_reason
from app.core.errors import NotFound, PermissionDenied, ValidationFailed
from app.models.master import (VENDOR_DOC_TYPES, Calibration, Category, Customer, Equipment, Location, Material,
                               MaterialType, Unit, UnitConversion, Vendor, VendorDocument, Warehouse)
from app.models.platform import Document
from app.schemas.common import Reasoned
from app.services import master_services as ms, masters, numbering
from app.services import documents

router = APIRouter()
S = str

router.include_router(crud_router(
    prefix="/units", tag="Units", Model=Unit, perm="md.unit", search_cols=["code", "name"], unique=["code"],
    filters=["dimension", "is_active"],
    fields=[("code", S, True), ("name", S, True), ("dimension", S, False), ("is_active", bool, False)]))
router.include_router(crud_router(
    prefix="/material-types", tag="Material types", Model=MaterialType, perm="md.material_type",
    search_cols=["code", "name"], unique=["code"], filters=["is_active"],
    fields=[("code", S, True), ("name", S, True), ("is_stock_item", bool, False), ("is_active", bool, False)]))
router.include_router(crud_router(
    prefix="/categories", tag="Categories", Model=Category, perm="md.category", search_cols=["code", "name"],
    unique=["code"], filters=["is_active"],
    fields=[("code", S, True), ("name", S, True), ("parent_id", int, False), ("is_active", bool, False)]))
router.include_router(crud_router(
    prefix="/customers", tag="Customers", Model=Customer, perm="md.customer", search_cols=["customer_code", "name"],
    code_field="customer_code", doc_type="CUSTOMER", unique=["customer_code"], filters=["is_active", "is_authorised"],
    fields=[("customer_code", S, False), ("name", S, True), ("address", S, False), ("state", S, False),
            ("gst_no", S, False), ("licence_no", S, False), ("licence_expiry", date, False),
            ("contact_person", S, False), ("email", S, False), ("phone", S, False),
            ("is_authorised", bool, False), ("is_active", bool, False)]))


def _wh_plant(s: Session, data: dict, existing) -> None:
    if existing is None and not data.get("plant_id"):
        data["plant_id"] = numbering.default_plant_id(s)


router.include_router(crud_router(
    prefix="/warehouses", tag="Warehouses", Model=Warehouse, perm="md.warehouse",
    search_cols=["warehouse_code", "name"], unique=["warehouse_code"], filters=["is_active"], before_save=_wh_plant,
    fields=[("warehouse_code", S, True), ("name", S, True), ("storage_condition", S, False),
            ("plant_id", int, False), ("is_active", bool, False)]))


def _equipment_checks(s: Session, data: dict, existing) -> None:
    if existing is None and not data.get("equipment_code"):
        data["equipment_code"] = numbering.next_number(s, numbering.default_plant_id(s), "EQUIPMENT")


router.include_router(crud_router(
    prefix="/equipment", tag="Equipment", Model=Equipment, perm="md.equipment",
    search_cols=["equipment_code", "name", "serial_no"], unique=["equipment_code"],
    filters=["status", "qualification_status", "equipment_type"], before_save=_equipment_checks,
    fields=[("equipment_code", S, False), ("name", S, True), ("equipment_type", S, False),
            ("manufacturer", S, False), ("model", S, False), ("serial_no", S, False), ("location_id", int, False),
            ("qualification_status", S, False), ("status", S, False), ("calibration_required", bool, False),
            ("maintenance_due", date, False)]))


# ------------------------------------------------------------------ equipment calibration
class CalibrationIn(Reasoned):
    performed_on: date
    due_on: date
    result: str = Field(pattern="^(PASS|FAIL)$")
    performed_by: str | None = None
    certificate_no: str | None = None
    remarks: str | None = None


@router.get("/equipment/{equipment_id}/status", tags=["Equipment"])
def equipment_status(equipment_id: int, p: Principal = Depends(require("md.equipment.read")), s: Session = Depends(get_db)):
    eq = masters.get_or_404(s, Equipment, equipment_id, "Equipment")
    ok, why = ms.usable_for_testing(eq)
    return {"calibration_status": ms.calibration_status(eq), "usable_for_testing": ok, "reason": why}


@router.get("/equipment/{equipment_id}/calibrations", tags=["Equipment"])
def list_calibrations(equipment_id: int, p: Principal = Depends(require("md.calibration.read")), s: Session = Depends(get_db)):
    masters.get_or_404(s, Equipment, equipment_id, "Equipment")
    return [to_dict(c) for c in s.execute(select(Calibration).where(Calibration.equipment_id == equipment_id)
                                          .order_by(Calibration.performed_on.desc(), Calibration.id.desc())).scalars()]


@router.post("/equipment/{equipment_id}/calibrations", status_code=201, tags=["Equipment"])
def add_calibration(equipment_id: int, body: CalibrationIn, p: Principal = Depends(require("md.calibration.create")),
                    s: Session = Depends(get_db)):
    use_reason(body.reason or "Calibration recorded")
    eq = masters.get_or_404(s, Equipment, equipment_id, "Equipment")
    cal = ms.add_calibration(s, eq, body.model_dump(exclude={"reason"}))
    s.commit()
    return to_dict(cal)


# ------------------------------------------------------------------ vendors
VENDOR_FIELDS = ["name", "vendor_type", "address", "country", "state", "city", "gst_no", "pan_no", "contact_person",
                 "email", "phone", "bank_name", "bank_account_no", "bank_ifsc", "material_categories", "risk_class",
                 "criticality", "quality_agreement_status", "vendor_audit_status"]


class VendorIn(Reasoned):
    vendor_code: str | None = None
    name: str = Field(min_length=2, max_length=200)
    vendor_type: str = "MANUFACTURER"
    address: str | None = None
    country: str | None = None
    state: str | None = None
    city: str | None = None
    gst_no: str | None = Field(default=None, max_length=30)
    pan_no: str | None = Field(default=None, pattern=r"^[A-Za-z]{5}[0-9]{4}[A-Za-z]$")
    contact_person: str | None = None
    email: str | None = Field(default=None, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    phone: str | None = None
    bank_name: str | None = None
    bank_account_no: str | None = None
    bank_ifsc: str | None = None
    material_categories: str | None = None
    risk_class: str = Field(default="MEDIUM", pattern="^(CRITICAL|HIGH|MEDIUM|LOW)$")
    criticality: str | None = None
    quality_agreement_status: str = Field(default="NONE", pattern="^(NONE|PENDING|SIGNED)$")
    vendor_audit_status: str = "NOT_AUDITED"


class VendorUpdate(Reasoned):
    model_config = {"extra": "forbid"}
    name: str | None = None
    vendor_type: str | None = None
    address: str | None = None
    country: str | None = None
    state: str | None = None
    city: str | None = None
    gst_no: str | None = None
    pan_no: str | None = Field(default=None, pattern=r"^[A-Za-z]{5}[0-9]{4}[A-Za-z]$")
    contact_person: str | None = None
    email: str | None = Field(default=None, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    phone: str | None = None
    bank_name: str | None = None
    bank_account_no: str | None = None
    bank_ifsc: str | None = None
    material_categories: str | None = None
    risk_class: str | None = Field(default=None, pattern="^(CRITICAL|HIGH|MEDIUM|LOW)$")
    criticality: str | None = None
    quality_agreement_status: str | None = Field(default=None, pattern="^(NONE|PENDING|SIGNED)$")
    vendor_audit_status: str | None = None


class SignedAction(Reasoned):
    password: str


def _vendor_out(v: Vendor) -> dict:
    d = to_dict(v)
    d["bank_account_masked"] = ("*" * max(0, len(v.bank_account_no) - 4) + v.bank_account_no[-4:]) if v.bank_account_no else None
    return d


def _vendor_query(request: Request, q: str | None):
    stmt = select(Vendor)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(func.lower(Vendor.name).like(like) | func.lower(Vendor.vendor_code).like(like))
    for f in ("approval_status", "risk_class"):
        if request.query_params.get(f):
            stmt = stmt.where(getattr(Vendor, f) == request.query_params[f])
    return stmt


@router.get("/vendors", tags=["Vendors"])
def list_vendors(request: Request, q: str | None = None, limit: int = Query(50), offset: int = Query(0),
                 p: Principal = Depends(require("md.vendor.read")), s: Session = Depends(get_db)):
    limit, offset = page_args(limit, offset)
    stmt = _vendor_query(request, q)
    total = s.execute(select(func.count()).select_from(stmt.subquery())).scalar()
    rows = s.execute(stmt.order_by(Vendor.id).limit(limit).offset(offset)).scalars().all()
    return {"items": [_vendor_out(v) for v in rows], "total": total, "limit": limit, "offset": offset}


@router.get("/vendors/export", tags=["Vendors"])
def export_vendors(request: Request, q: str | None = None, p: Principal = Depends(require("md.vendor.read", "md.master.export")),
                   s: Session = Depends(get_db)):
    rows = [to_dict(v, {"bank_account_no", "bank_ifsc", "bank_name"}) for v in s.execute(_vendor_query(request, q)).scalars()]
    cols = [("vendor_code", "Vendor code"), ("name", "Name"), ("vendor_type", "Type"), ("country", "Country"),
            ("state", "State"), ("city", "City"), ("gst_no", "GST"), ("pan_no", "PAN"), ("email", "Email"),
            ("phone", "Phone"), ("risk_class", "Risk class"), ("criticality", "Criticality"),
            ("quality_agreement_status", "Quality agreement"), ("vendor_audit_status", "Audit status"),
            ("approval_status", "Approval status")]
    return xlsx_response(s, p, "Vendor master", {"search": q, "approval_status": request.query_params.get("approval_status")},
                         cols, rows, "vendor")


@router.post("/vendors", status_code=201, tags=["Vendors"])
def create_vendor(body: VendorIn, p: Principal = Depends(require("md.vendor.create")), s: Session = Depends(get_db)):
    use_reason(body.reason)
    data = body.model_dump(exclude={"reason", "vendor_code"}, exclude_none=True)
    v = ms.create_vendor(s, data, body.vendor_code)
    s.commit()
    return _vendor_out(v)


@router.get("/vendors/{vendor_id}", tags=["Vendors"])
def get_vendor(vendor_id: int, p: Principal = Depends(require("md.vendor.read")), s: Session = Depends(get_db)):
    v = masters.get_or_404(s, Vendor, vendor_id, "Vendor")
    return {**_vendor_out(v), "documents": ms.vendor_documents(s, v.id)}


@router.patch("/vendors/{vendor_id}", tags=["Vendors"])
def update_vendor(vendor_id: int, body: VendorUpdate, p: Principal = Depends(require("md.vendor.update")), s: Session = Depends(get_db)):
    use_reason(body.reason)
    v = masters.get_or_404(s, Vendor, vendor_id, "Vendor")
    data = body.model_dump(exclude={"reason"}, exclude_unset=True)
    if "name" in data:
        masters.ensure_unique(s, Vendor, "name", data["name"], exclude_id=v.id)
    for k, val in data.items():
        setattr(v, k, val)
    s.commit()
    return _vendor_out(v)


def _vendor_transition(vendor_id: int, to: str, perm_dep, body: SignedAction, p: Principal, s: Session):
    use_reason(body.reason)
    v = masters.get_or_404(s, Vendor, vendor_id, "Vendor")
    masters.sign_and_transition(s, v, ms.VENDOR_MACHINE, to, p.user, body.password, reason=body.reason or "",
                                meaning="APPROVED_BY", sod_action="vendor.approve" if to == "APPROVED" else None)
    s.commit()
    return _vendor_out(v)


@router.post("/vendors/{vendor_id}/approve", tags=["Vendors"])
def approve_vendor(vendor_id: int, body: SignedAction, p: Principal = Depends(require("md.vendor.approve")), s: Session = Depends(get_db)):
    return _vendor_transition(vendor_id, "APPROVED", None, body, p, s)


@router.post("/vendors/{vendor_id}/deactivate", tags=["Vendors"])
def deactivate_vendor(vendor_id: int, body: SignedAction, p: Principal = Depends(require("md.vendor.deactivate")), s: Session = Depends(get_db)):
    return _vendor_transition(vendor_id, "INACTIVE", None, body, p, s)


@router.get("/vendor-document-types", tags=["Vendors"])
def vendor_doc_types(p: Principal = Depends(require("md.vendor.read"))):
    return VENDOR_DOC_TYPES


@router.post("/vendors/{vendor_id}/documents", status_code=201, tags=["Vendors"])
async def upload_vendor_document(vendor_id: int, doc_type: str = Form(...), version: str = Form("1"),
                                 doc_no: str | None = Form(None), issue_date: date | None = Form(None),
                                 expiry_date: date | None = Form(None), file: UploadFile = File(...),
                                 p: Principal = Depends(require("md.vendor.update", "doc.document.create")),
                                 s: Session = Depends(get_db)):
    use_reason(f"Vendor document upload ({doc_type})")
    v = masters.get_or_404(s, Vendor, vendor_id, "Vendor")
    data = await file.read()
    vd = ms.add_vendor_document(s, v, doc_type=doc_type, filename=file.filename or "document", data=data,
                                doc_no=doc_no, version=version, issue_date=issue_date, expiry_date=expiry_date)
    s.commit()
    return to_dict(vd)


class ReviewIn(BaseModel):
    approve: bool
    comment: str


@router.post("/vendor-documents/{vd_id}/review", tags=["Vendors"])
def review_vendor_document(vd_id: int, body: ReviewIn, p: Principal = Depends(require("md.vendor.review_document")),
                           s: Session = Depends(get_db)):
    use_reason(body.comment)
    vd = masters.get_or_404(s, VendorDocument, vd_id, "Vendor document")
    ms.review_vendor_document(s, vd, p.user, body.approve, body.comment)
    s.commit()
    return to_dict(vd)


# ------------------------------------------------------------------ materials
class MaterialIn(Reasoned):
    material_code: str | None = None
    name: str = Field(min_length=2, max_length=200)
    generic_name: str | None = None
    type_id: int
    category_id: int | None = None
    subcategory: str | None = None
    grade: str | None = None
    pharmacopoeial_standard: str | None = None
    manufacturer: str | None = None
    base_unit_id: int
    pack_size: str | None = None
    storage_condition: str | None = None
    temp_min: Decimal | None = None
    temp_max: Decimal | None = None
    humidity_min: Decimal | None = None
    humidity_max: Decimal | None = None
    shelf_life_days: int | None = Field(default=None, gt=0)
    retest_days: int | None = Field(default=None, gt=0)
    requires_qc: bool = True
    requires_qa_release: bool = True
    gmp_criticality: str = Field(default="MAJOR", pattern="^(CRITICAL|MAJOR|MINOR)$")
    hazard_class: str | None = None
    fefo_mode: str = Field(default="FEFO", pattern="^(FEFO|FIFO)$")
    min_stock: Decimal | None = Field(default=None, ge=0)
    max_stock: Decimal | None = Field(default=None, ge=0)


class MaterialUpdate(MaterialIn):
    model_config = {"extra": "forbid"}
    name: str | None = None  # type: ignore[assignment]
    type_id: int | None = None  # type: ignore[assignment]
    base_unit_id: int | None = None  # type: ignore[assignment]
    material_code: None = None  # code is immutable


def _material_query(request: Request, q: str | None):
    stmt = select(Material)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(func.lower(Material.name).like(like) | func.lower(Material.material_code).like(like))
    for f in ("master_status", "type_id", "category_id", "gmp_criticality"):
        if request.query_params.get(f):
            stmt = stmt.where(getattr(Material, f) == request.query_params[f])
    return stmt


@router.get("/materials", tags=["Materials"])
def list_materials(request: Request, q: str | None = None, limit: int = Query(50), offset: int = Query(0),
                   p: Principal = Depends(require("md.material.read")), s: Session = Depends(get_db)):
    limit, offset = page_args(limit, offset)
    stmt = _material_query(request, q)
    total = s.execute(select(func.count()).select_from(stmt.subquery())).scalar()
    rows = s.execute(stmt.order_by(Material.id).limit(limit).offset(offset)).scalars().all()
    return {"items": [to_dict(m) for m in rows], "total": total, "limit": limit, "offset": offset}


@router.get("/materials/export", tags=["Materials"])
def export_materials(request: Request, q: str | None = None, p: Principal = Depends(require("md.material.read", "md.master.export")),
                     s: Session = Depends(get_db)):
    rows = [to_dict(m) for m in s.execute(_material_query(request, q)).scalars()]
    cols = [("material_code", "Material code"), ("name", "Name"), ("generic_name", "Generic name"), ("grade", "Grade"),
            ("pharmacopoeial_standard", "Pharmacopoeia"), ("manufacturer", "Manufacturer"), ("pack_size", "Pack size"),
            ("storage_condition", "Storage"), ("temp_min", "Temp min"), ("temp_max", "Temp max"),
            ("shelf_life_days", "Shelf life (d)"), ("retest_days", "Retest (d)"), ("gmp_criticality", "GMP criticality"),
            ("fefo_mode", "FEFO/FIFO"), ("master_status", "Status")]
    return xlsx_response(s, p, "Material master", {"search": q, "status": request.query_params.get("master_status")},
                         cols, rows, "material")


@router.post("/materials", status_code=201, tags=["Materials"])
def create_material(body: MaterialIn, p: Principal = Depends(require("md.material.create")), s: Session = Depends(get_db)):
    use_reason(body.reason)
    m = ms.create_material(s, body.model_dump(exclude={"reason", "material_code"}, exclude_none=True), body.material_code)
    s.commit()
    return to_dict(m)


@router.get("/materials/{material_id}", tags=["Materials"])
def get_material(material_id: int, p: Principal = Depends(require("md.material.read")), s: Session = Depends(get_db)):
    return to_dict(masters.get_or_404(s, Material, material_id, "Material"))


@router.patch("/materials/{material_id}", tags=["Materials"])
def update_material(material_id: int, body: MaterialUpdate, p: Principal = Depends(require("md.material.update")),
                    s: Session = Depends(get_db)):
    use_reason(body.reason)
    m = masters.get_or_404(s, Material, material_id, "Material")
    if m.master_status == "OBSOLETE":
        raise PermissionDenied("An OBSOLETE material cannot be modified")
    data = body.model_dump(exclude={"reason", "material_code"}, exclude_unset=True)
    masters.check_foreign_keys(s, Material, data)
    ms._check_ranges({**to_dict(m), **data})
    for k, val in data.items():
        setattr(m, k, val)
    s.commit()
    return to_dict(m)


def _material_step(material_id: int, to: str, body: SignedAction, p: Principal, s: Session, sod_action: str | None):
    use_reason(body.reason)
    m = masters.get_or_404(s, Material, material_id, "Material")
    t = ms.MATERIAL_MACHINE.allowed(m.master_status).get(to)
    masters.sign_and_transition(s, m, ms.MATERIAL_MACHINE, to, p.user, body.password, reason=body.reason or "",
                                meaning=t.signature_meaning if t else "APPROVED_BY", sod_action=sod_action)
    s.commit()
    return to_dict(m)


@router.post("/materials/{material_id}/approve", tags=["Materials"])
def approve_material(material_id: int, body: SignedAction, p: Principal = Depends(require("md.material.approve")), s: Session = Depends(get_db)):
    return _material_step(material_id, "APPROVED", body, p, s, "material.approve")


@router.post("/materials/{material_id}/activate", tags=["Materials"])
def activate_material(material_id: int, body: SignedAction, p: Principal = Depends(require("md.material.approve")), s: Session = Depends(get_db)):
    return _material_step(material_id, "ACTIVE", body, p, s, None)


@router.post("/materials/{material_id}/obsolete", tags=["Materials"])
def obsolete_material(material_id: int, body: SignedAction, p: Principal = Depends(require("md.material.deactivate")), s: Session = Depends(get_db)):
    return _material_step(material_id, "OBSOLETE", body, p, s, None)


# ------------------------------------------------------------------ locations
class LocationIn(Reasoned):
    warehouse_id: int
    parent_id: int | None = None
    location_code: str = Field(min_length=1, max_length=40)
    name: str
    location_type: str
    storage_condition: str | None = None
    temp_min: Decimal | None = None
    temp_max: Decimal | None = None
    humidity_min: Decimal | None = None
    humidity_max: Decimal | None = None
    capacity: Decimal | None = Field(default=None, ge=0)
    capacity_unit_id: int | None = None
    is_quarantine: bool = False
    is_rejected_area: bool = False
    status: str = Field(default="ACTIVE", pattern="^(ACTIVE|INACTIVE)$")
    allowed_category_ids: list[int] = []


class LocationUpdate(Reasoned):
    model_config = {"extra": "forbid"}
    parent_id: int | None = None
    name: str | None = None
    location_type: str | None = None
    storage_condition: str | None = None
    temp_min: Decimal | None = None
    temp_max: Decimal | None = None
    humidity_min: Decimal | None = None
    humidity_max: Decimal | None = None
    capacity: Decimal | None = Field(default=None, ge=0)
    capacity_unit_id: int | None = None
    is_quarantine: bool | None = None
    is_rejected_area: bool | None = None
    status: str | None = Field(default=None, pattern="^(ACTIVE|INACTIVE)$")
    allowed_category_ids: list[int] | None = None


def _loc_out(s: Session, loc: Location) -> dict:
    d = to_dict(loc)
    d["path"] = ms.location_path(s, loc)
    d["allowed_category_ids"] = sorted(ms.allowed_categories(s, loc.id))
    d["utilisation_pct"] = round(float(loc.current_occupancy or 0) / float(loc.capacity) * 100, 1) if loc.capacity else None
    return d


@router.get("/locations", tags=["Locations"])
def list_locations(request: Request, q: str | None = None, warehouse_id: int | None = None, limit: int = Query(200),
                   offset: int = Query(0), p: Principal = Depends(require("md.location.read")), s: Session = Depends(get_db)):
    limit, offset = page_args(limit, offset)
    stmt = select(Location)
    if q:
        stmt = stmt.where(func.lower(Location.location_code).like(f"%{q.lower()}%") | func.lower(Location.name).like(f"%{q.lower()}%"))
    if warehouse_id:
        stmt = stmt.where(Location.warehouse_id == warehouse_id)
    for f in ("status", "location_type"):
        if request.query_params.get(f):
            stmt = stmt.where(getattr(Location, f) == request.query_params[f])
    total = s.execute(select(func.count()).select_from(stmt.subquery())).scalar()
    rows = s.execute(stmt.order_by(Location.location_code).limit(limit).offset(offset)).scalars().all()
    return {"items": [_loc_out(s, r) for r in rows], "total": total, "limit": limit, "offset": offset}


@router.get("/locations/export", tags=["Locations"])
def export_locations(p: Principal = Depends(require("md.location.read", "md.master.export")), s: Session = Depends(get_db)):
    rows = [_loc_out(s, r) for r in s.execute(select(Location).order_by(Location.location_code)).scalars()]
    cols = [("location_code", "Location code"), ("path", "Path"), ("name", "Name"), ("location_type", "Type"),
            ("storage_condition", "Storage condition"), ("temp_min", "Temp min"), ("temp_max", "Temp max"),
            ("capacity", "Capacity"), ("current_occupancy", "Occupancy"), ("is_quarantine", "Quarantine"), ("status", "Status")]
    return xlsx_response(s, p, "Location master", {}, cols, rows, "location")


@router.post("/locations", status_code=201, tags=["Locations"])
def create_location(body: LocationIn, p: Principal = Depends(require("md.location.create")), s: Session = Depends(get_db)):
    use_reason(body.reason)
    data = body.model_dump(exclude={"reason", "allowed_category_ids"}, exclude_none=True)
    loc = ms.create_location(s, data)
    if body.allowed_category_ids:
        ms.set_location_categories(s, loc, body.allowed_category_ids)
    s.commit()
    return _loc_out(s, loc)


@router.get("/locations/{location_id}", tags=["Locations"])
def get_location(location_id: int, p: Principal = Depends(require("md.location.read")), s: Session = Depends(get_db)):
    return _loc_out(s, masters.get_or_404(s, Location, location_id, "Location"))


@router.patch("/locations/{location_id}", tags=["Locations"])
def update_location(location_id: int, body: LocationUpdate, p: Principal = Depends(require("md.location.update")),
                    s: Session = Depends(get_db)):
    use_reason(body.reason)
    loc = masters.get_or_404(s, Location, location_id, "Location")
    data = body.model_dump(exclude={"reason", "allowed_category_ids"}, exclude_unset=True)
    masters.check_foreign_keys(s, Location, data)
    ms.validate_location(s, data, loc)
    for k, v in data.items():
        setattr(loc, k, v)
    if body.allowed_category_ids is not None:
        ms.set_location_categories(s, loc, body.allowed_category_ids)
    s.commit()
    return _loc_out(s, loc)


@router.get("/locations/{location_id}/storage-check", tags=["Locations"])
def storage_check(location_id: int, material_id: int, p: Principal = Depends(require("md.location.read")),
                  s: Session = Depends(get_db)):
    loc = masters.get_or_404(s, Location, location_id, "Location")
    mat = masters.get_or_404(s, Material, material_id, "Material")
    v = ms.storage_violations(s, loc, mat)
    return {"ok": not v, "violations": v}


router.include_router(crud_router(
    prefix="/unit-conversions", tag="Units", Model=UnitConversion, perm="md.unit", search_cols=[],
    fields=[("from_unit_id", int, True), ("to_unit_id", int, True), ("factor", Decimal, True)]))

from app.models.master import LocationCompatRule  # noqa: E402

router.include_router(crud_router(
    prefix="/location-compat-rules", tag="Locations", Model=LocationCompatRule, perm="md.location", search_cols=[],
    fields=[("category_a_id", int, True), ("category_b_id", int, True), ("allowed", bool, False)]))
