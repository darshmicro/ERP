"""Phase 2 master data: units, types/categories, vendor, material, locations, equipment, customers."""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (Boolean, CheckConstraint, Date, ForeignKey, Integer, Numeric, String, Text,
                        UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import PK, Base, UTCDateTime
from app.models.base import AuditedMixin, StatefulMixin

QTY = Numeric(18, 6)


class Unit(AuditedMixin, Base):
    __tablename__ = "unit"
    __audit_module__ = "master"
    __reason_required__ = True
    __table_args__ = (UniqueConstraint("code"),)
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    dimension: Mapped[str] = mapped_column(String(20), default="COUNT")  # MASS/VOLUME/COUNT/LENGTH/OTHER
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class UnitConversion(AuditedMixin, Base):
    __tablename__ = "unit_conversion"
    __audit_module__ = "master"
    __reason_required__ = True
    __table_args__ = (UniqueConstraint("from_unit_id", "to_unit_id"),
                      CheckConstraint("factor > 0", name="factor_positive"))
    from_unit_id: Mapped[int] = mapped_column(PK, ForeignKey("unit.id"), nullable=False)
    to_unit_id: Mapped[int] = mapped_column(PK, ForeignKey("unit.id"), nullable=False)
    factor: Mapped[Decimal] = mapped_column(Numeric(24, 10), nullable=False)


class MaterialType(AuditedMixin, Base):
    __tablename__ = "material_type"
    __audit_module__ = "master"
    __reason_required__ = True
    __table_args__ = (UniqueConstraint("code"),)
    code: Mapped[str] = mapped_column(String(20), nullable=False)   # RM, PM, API, SFG, FG ...
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    is_stock_item: Mapped[bool] = mapped_column(Boolean, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Category(AuditedMixin, Base):
    __tablename__ = "category"
    __audit_module__ = "master"
    __reason_required__ = True
    __table_args__ = (UniqueConstraint("code"),)
    code: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    parent_id: Mapped[int | None] = mapped_column(PK, ForeignKey("category.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Vendor(StatefulMixin, AuditedMixin, Base):
    __tablename__ = "vendor"
    __audit_module__ = "master"
    __reason_required__ = True
    __audit_sensitive__ = frozenset({"bank_account_no"})
    __table_args__ = (UniqueConstraint("vendor_code"),
                      CheckConstraint("approval_status IN ('DRAFT','APPROVED','INACTIVE')", name="approval_status"),
                      CheckConstraint("risk_class IN ('CRITICAL','HIGH','MEDIUM','LOW')", name="risk_class"))
    vendor_code: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    vendor_type: Mapped[str] = mapped_column(String(40), default="MANUFACTURER")
    address: Mapped[str | None] = mapped_column(Text)
    country: Mapped[str | None] = mapped_column(String(60))
    state: Mapped[str | None] = mapped_column(String(60))
    city: Mapped[str | None] = mapped_column(String(60))
    gst_no: Mapped[str | None] = mapped_column(String(30))
    pan_no: Mapped[str | None] = mapped_column(String(15))
    contact_person: Mapped[str | None] = mapped_column(String(100))
    email: Mapped[str | None] = mapped_column(String(150))
    phone: Mapped[str | None] = mapped_column(String(40))
    bank_name: Mapped[str | None] = mapped_column(String(100))
    bank_account_no: Mapped[str | None] = mapped_column(String(40))
    bank_ifsc: Mapped[str | None] = mapped_column(String(20))
    material_categories: Mapped[str | None] = mapped_column(String(300))
    risk_class: Mapped[str] = mapped_column(String(10), default="MEDIUM", nullable=False)
    criticality: Mapped[str | None] = mapped_column(String(20))
    quality_agreement_status: Mapped[str] = mapped_column(String(20), default="NONE")  # NONE/PENDING/SIGNED
    vendor_audit_status: Mapped[str] = mapped_column(String(20), default="NOT_AUDITED")
    approval_status: Mapped[str] = mapped_column(String(20), default="DRAFT", nullable=False)
    __status_field__ = "approval_status"
    # Qualification status/dates are owned by the Phase 3 vendor_qualification module.


class VendorDocument(AuditedMixin, Base):
    __tablename__ = "vendor_document"
    __audit_module__ = "master"
    vendor_id: Mapped[int] = mapped_column(PK, ForeignKey("vendor.id"), nullable=False, index=True)
    document_id: Mapped[int] = mapped_column(PK, ForeignKey("document.id"), nullable=False)
    doc_type: Mapped[str] = mapped_column(String(40), nullable=False)
    doc_no: Mapped[str | None] = mapped_column(String(60))
    version: Mapped[str] = mapped_column(String(20), default="1")
    issue_date: Mapped[date | None] = mapped_column(Date)
    expiry_date: Mapped[date | None] = mapped_column(Date)
    review_status: Mapped[str] = mapped_column(String(20), default="PENDING")  # PENDING/APPROVED/REJECTED
    reviewed_by_id: Mapped[int | None] = mapped_column(PK)
    reviewed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    review_comment: Mapped[str | None] = mapped_column(String(500))
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (CheckConstraint("review_status IN ('PENDING','APPROVED','REJECTED')", name="review_status"),)


VENDOR_DOC_TYPES = [
    "VENDOR_QUESTIONNAIRE", "GMP_CERTIFICATE", "MANUFACTURING_LICENCE", "ISO_CERTIFICATE", "COA_SAMPLE",
    "SPECIFICATION", "TSE_BSE_DECLARATION", "ANIMAL_ORIGIN_DECLARATION", "ALLERGEN_DECLARATION",
    "RESIDUAL_SOLVENT_DECLARATION", "ELEMENTAL_IMPURITY_DECLARATION", "NITROSAMINE_DECLARATION",
    "STERILITY_INFORMATION", "ENDOTOXIN_INFORMATION", "REGULATORY_DOCUMENT", "QUALITY_AGREEMENT",
    "AUDIT_REPORT", "CAPA", "PREVIOUS_QUALIFICATION", "OTHER"]


class Material(StatefulMixin, AuditedMixin, Base):
    __tablename__ = "material"
    __audit_module__ = "master"
    __reason_required__ = True
    __table_args__ = (UniqueConstraint("material_code"),
                      CheckConstraint("master_status IN ('DRAFT','APPROVED','ACTIVE','OBSOLETE')", name="master_status"),
                      CheckConstraint("fefo_mode IN ('FEFO','FIFO')", name="fefo_mode"),
                      CheckConstraint("temp_max IS NULL OR temp_min IS NULL OR temp_max >= temp_min", name="temp_range"),
                      CheckConstraint("shelf_life_days IS NULL OR shelf_life_days > 0", name="shelf_life"))
    material_code: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    generic_name: Mapped[str | None] = mapped_column(String(200))
    type_id: Mapped[int] = mapped_column(PK, ForeignKey("material_type.id"), nullable=False)
    category_id: Mapped[int | None] = mapped_column(PK, ForeignKey("category.id"))
    subcategory: Mapped[str | None] = mapped_column(String(100))
    grade: Mapped[str | None] = mapped_column(String(50))
    pharmacopoeial_standard: Mapped[str | None] = mapped_column(String(100))
    manufacturer: Mapped[str | None] = mapped_column(String(200))
    base_unit_id: Mapped[int] = mapped_column(PK, ForeignKey("unit.id"), nullable=False)
    pack_size: Mapped[str | None] = mapped_column(String(60))
    storage_condition: Mapped[str | None] = mapped_column(String(200))
    temp_min: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    temp_max: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    humidity_min: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    humidity_max: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    shelf_life_days: Mapped[int | None] = mapped_column(Integer)
    retest_days: Mapped[int | None] = mapped_column(Integer)
    requires_qc: Mapped[bool] = mapped_column(Boolean, default=True)
    requires_qa_release: Mapped[bool] = mapped_column(Boolean, default=True)
    gmp_criticality: Mapped[str] = mapped_column(String(20), default="MAJOR")
    hazard_class: Mapped[str | None] = mapped_column(String(60))
    fefo_mode: Mapped[str] = mapped_column(String(4), default="FEFO", nullable=False)
    min_stock: Mapped[Decimal | None] = mapped_column(QTY)
    max_stock: Mapped[Decimal | None] = mapped_column(QTY)
    barcode: Mapped[str | None] = mapped_column(String(60))
    master_status: Mapped[str] = mapped_column(String(20), default="DRAFT", nullable=False)
    __status_field__ = "master_status"


class Customer(AuditedMixin, Base):
    __tablename__ = "customer"
    __audit_module__ = "master"
    __reason_required__ = True
    __table_args__ = (UniqueConstraint("customer_code"),)
    customer_code: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    address: Mapped[str | None] = mapped_column(Text)
    state: Mapped[str | None] = mapped_column(String(60))
    gst_no: Mapped[str | None] = mapped_column(String(30))
    licence_no: Mapped[str | None] = mapped_column(String(60))
    licence_expiry: Mapped[date | None] = mapped_column(Date)
    contact_person: Mapped[str | None] = mapped_column(String(100))
    email: Mapped[str | None] = mapped_column(String(150))
    phone: Mapped[str | None] = mapped_column(String(40))
    is_authorised: Mapped[bool] = mapped_column(Boolean, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Warehouse(AuditedMixin, Base):
    __tablename__ = "warehouse"
    __audit_module__ = "master"
    __reason_required__ = True
    __table_args__ = (UniqueConstraint("warehouse_code"),)
    plant_id: Mapped[int] = mapped_column(PK, ForeignKey("plant.id"), nullable=False)
    warehouse_code: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    storage_condition: Mapped[str | None] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


LOCATION_LEVELS = ["ZONE", "ROOM", "RACK", "SHELF", "BIN"]  # Plant -> Warehouse -> Zone -> Room -> Rack -> Shelf -> Bin


class Location(AuditedMixin, Base):
    __tablename__ = "location"
    __audit_module__ = "master"
    __reason_required__ = True
    __audit_exclude__ = frozenset({"current_occupancy"})
    __table_args__ = (UniqueConstraint("location_code"),
                      CheckConstraint("location_type IN ('ZONE','ROOM','RACK','SHELF','BIN')", name="location_type"),
                      CheckConstraint("capacity IS NULL OR capacity >= 0", name="capacity"),
                      CheckConstraint("temp_max IS NULL OR temp_min IS NULL OR temp_max >= temp_min", name="temp_range"))
    warehouse_id: Mapped[int] = mapped_column(PK, ForeignKey("warehouse.id"), nullable=False, index=True)
    parent_id: Mapped[int | None] = mapped_column(PK, ForeignKey("location.id"))
    location_code: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    location_type: Mapped[str] = mapped_column(String(10), nullable=False)
    storage_condition: Mapped[str | None] = mapped_column(String(100))
    temp_min: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    temp_max: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    humidity_min: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    humidity_max: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    capacity: Mapped[Decimal | None] = mapped_column(QTY)
    capacity_unit_id: Mapped[int | None] = mapped_column(PK, ForeignKey("unit.id"))
    current_occupancy: Mapped[Decimal] = mapped_column(QTY, default=0)  # maintained by inventory (Phase 4)
    is_quarantine: Mapped[bool] = mapped_column(Boolean, default=False)
    is_rejected_area: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(10), default="ACTIVE")


class LocationCategory(AuditedMixin, Base):
    """Material categories allowed in a location (empty set = unrestricted)."""

    __tablename__ = "location_category"
    __audit_module__ = "master"
    __table_args__ = (UniqueConstraint("location_id", "category_id"),)
    location_id: Mapped[int] = mapped_column(PK, ForeignKey("location.id"), nullable=False)
    category_id: Mapped[int] = mapped_column(PK, ForeignKey("category.id"), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class LocationCompatRule(AuditedMixin, Base):
    """Category pairs that must not be stored in the same location."""

    __tablename__ = "location_compat_rule"
    __audit_module__ = "master"
    __reason_required__ = True
    __table_args__ = (UniqueConstraint("category_a_id", "category_b_id"),)
    category_a_id: Mapped[int] = mapped_column(PK, ForeignKey("category.id"), nullable=False)
    category_b_id: Mapped[int] = mapped_column(PK, ForeignKey("category.id"), nullable=False)
    allowed: Mapped[bool] = mapped_column(Boolean, default=False)


class Equipment(AuditedMixin, Base):
    __tablename__ = "equipment"
    __audit_module__ = "master"
    __reason_required__ = True
    __table_args__ = (UniqueConstraint("equipment_code"),
                      CheckConstraint("status IN ('ACTIVE','UNDER_MAINTENANCE','OUT_OF_SERVICE','RETIRED')", name="status"),
                      CheckConstraint("qualification_status IN ('NOT_QUALIFIED','QUALIFIED','REQUALIFICATION_DUE','DISQUALIFIED')",
                                      name="qualification_status"))
    equipment_code: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    equipment_type: Mapped[str] = mapped_column(String(40), default="INSTRUMENT")  # INSTRUMENT / PRODUCTION / UTILITY
    manufacturer: Mapped[str | None] = mapped_column(String(100))
    model: Mapped[str | None] = mapped_column(String(100))
    serial_no: Mapped[str | None] = mapped_column(String(100))
    location_id: Mapped[int | None] = mapped_column(PK, ForeignKey("location.id"))
    qualification_status: Mapped[str] = mapped_column(String(25), default="NOT_QUALIFIED")
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    calibration_required: Mapped[bool] = mapped_column(Boolean, default=True)
    calibration_due: Mapped[date | None] = mapped_column(Date)
    maintenance_due: Mapped[date | None] = mapped_column(Date)


class Calibration(AuditedMixin, Base):
    __tablename__ = "calibration"
    __audit_module__ = "master"
    __table_args__ = (CheckConstraint("result IN ('PASS','FAIL')", name="result"),
                      CheckConstraint("due_on > performed_on", name="due_after_performed"))
    equipment_id: Mapped[int] = mapped_column(PK, ForeignKey("equipment.id"), nullable=False, index=True)
    performed_on: Mapped[date] = mapped_column(Date, nullable=False)
    due_on: Mapped[date] = mapped_column(Date, nullable=False)
    result: Mapped[str] = mapped_column(String(4), nullable=False)
    performed_by: Mapped[str | None] = mapped_column(String(150))
    certificate_no: Mapped[str | None] = mapped_column(String(80))
    certificate_document_id: Mapped[int | None] = mapped_column(PK, ForeignKey("document.id"))
    remarks: Mapped[str | None] = mapped_column(String(500))
