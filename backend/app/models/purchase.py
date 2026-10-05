"""Phase 3: vendor qualification, vendor-material approval, purchase request, purchase order."""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (Boolean, CheckConstraint, Date, ForeignKey, Integer, Numeric, String, Text,
                        UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import PK, Base, UTCDateTime
from app.core.time import utcnow
from app.models.base import AuditedMixin, StatefulMixin, VersionChildMixin, VersionedMixin

QTY = Numeric(18, 6)
MONEY = Numeric(18, 4)

VQ_STATUSES = ("DRAFT", "UNDER_REVIEW", "APPROVED", "CONDITIONAL", "SUSPENDED", "EXPIRED", "DISQUALIFIED", "SUPERSEDED")


class VendorQualification(VersionedMixin, AuditedMixin, Base):
    """One row per qualification *version*. The vendor's current standing is the latest non-draft row;
    requalification creates a new version (history is never overwritten)."""

    __tablename__ = "vendor_qualification"
    __audit_module__ = "purchase"
    __version_mutable_fields__ = frozenset({"status_reason"})
    __table_args__ = (UniqueConstraint("vendor_id", "version_no"),
                      CheckConstraint("status IN " + str(VQ_STATUSES), name="status"),
                      CheckConstraint("risk_class IN ('CRITICAL','HIGH','MEDIUM','LOW')", name="risk_class"))
    vendor_id: Mapped[int] = mapped_column(PK, ForeignKey("vendor.id"), nullable=False, index=True)
    qualification_no: Mapped[str] = mapped_column(String(40), nullable=False)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="DRAFT")
    risk_class: Mapped[str] = mapped_column(String(10), nullable=False)
    qualified_on: Mapped[date | None] = mapped_column(Date)
    requalification_due_date: Mapped[date | None] = mapped_column(Date)
    basis: Mapped[str | None] = mapped_column(Text)            # questionnaire / audit / history summary
    audit_report_ref: Mapped[str | None] = mapped_column(String(100))
    supersedes_id: Mapped[int | None] = mapped_column(PK, ForeignKey("vendor_qualification.id"))
    effective_from: Mapped[datetime | None] = mapped_column(UTCDateTime)
    effective_to: Mapped[datetime | None] = mapped_column(UTCDateTime)
    status_reason: Mapped[str | None] = mapped_column(String(1000))
    change_reason: Mapped[str | None] = mapped_column(String(1000))
    approved_signature_id: Mapped[int | None] = mapped_column(PK, ForeignKey("e_signature.id"))


class VendorMaterial(VersionedMixin, AuditedMixin, Base):
    """Approved vendor for a material - the single source of truth (design decision C-03)."""

    __tablename__ = "vendor_material"
    __audit_module__ = "purchase"
    __version_mutable_fields__ = frozenset({"status_reason", "approved_to"})
    __table_args__ = (UniqueConstraint("vendor_id", "material_id", "version_no"),
                      CheckConstraint("status IN ('DRAFT','UNDER_REVIEW','APPROVED','SUPERSEDED','WITHDRAWN')", name="status"))
    vendor_id: Mapped[int] = mapped_column(PK, ForeignKey("vendor.id"), nullable=False, index=True)
    material_id: Mapped[int] = mapped_column(PK, ForeignKey("material.id"), nullable=False, index=True)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="DRAFT")
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    manufacturer_site: Mapped[str | None] = mapped_column(String(200))
    change_control_ref: Mapped[str | None] = mapped_column(String(60))
    supersedes_id: Mapped[int | None] = mapped_column(PK, ForeignKey("vendor_material.id"))
    effective_from: Mapped[datetime | None] = mapped_column(UTCDateTime)
    effective_to: Mapped[datetime | None] = mapped_column(UTCDateTime)
    approved_to: Mapped[date | None] = mapped_column(Date)
    status_reason: Mapped[str | None] = mapped_column(String(1000))
    change_reason: Mapped[str | None] = mapped_column(String(1000))
    approved_signature_id: Mapped[int | None] = mapped_column(PK, ForeignKey("e_signature.id"))


class PurchaseRequest(StatefulMixin, AuditedMixin, Base):
    __tablename__ = "purchase_request"
    __audit_module__ = "purchase"
    __editable_statuses__ = ("DRAFT",)
    __version_mutable_fields__ = frozenset({"workflow_instance_id"})
    __audit_exclude__ = frozenset({"workflow_instance_id"})
    __table_args__ = (UniqueConstraint("pr_no"),
                      CheckConstraint("status IN ('DRAFT','SUBMITTED','DEPARTMENT_APPROVED','APPROVED','CONVERTED','REJECTED','CANCELLED')", name="status"),
                      CheckConstraint("priority IN ('LOW','NORMAL','HIGH','URGENT')", name="priority"))
    pr_no: Mapped[str] = mapped_column(String(30), nullable=False)
    request_date: Mapped[date] = mapped_column(Date, nullable=False)
    department_id: Mapped[int] = mapped_column(PK, ForeignKey("department.id"), nullable=False)
    requested_by_id: Mapped[int] = mapped_column(PK, ForeignKey("users.id"), nullable=False)
    purpose: Mapped[str | None] = mapped_column(String(500))
    priority: Mapped[str] = mapped_column(String(10), default="NORMAL")
    remarks: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(25), default="DRAFT", nullable=False)
    workflow_instance_id: Mapped[int | None] = mapped_column(PK, ForeignKey("workflow_instance.id"))


class PurchaseRequestLine(VersionChildMixin, AuditedMixin, Base):
    __tablename__ = "purchase_request_line"
    __audit_module__ = "purchase"
    __version_parent_model__ = "app.models.purchase.PurchaseRequest"
    __version_parent_fk__ = "pr_id"
    __child_mutable_fields__ = frozenset({"po_line_id"})
    __table_args__ = (UniqueConstraint("pr_id", "line_no"), CheckConstraint("quantity > 0", name="quantity"))
    pr_id: Mapped[int] = mapped_column(PK, ForeignKey("purchase_request.id"), nullable=False, index=True)
    line_no: Mapped[int] = mapped_column(Integer, nullable=False)
    material_id: Mapped[int] = mapped_column(PK, ForeignKey("material.id"), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(QTY, nullable=False)
    unit_id: Mapped[int] = mapped_column(PK, ForeignKey("unit.id"), nullable=False)
    required_date: Mapped[date | None] = mapped_column(Date)
    preferred_vendor_id: Mapped[int | None] = mapped_column(PK, ForeignKey("vendor.id"))
    remarks: Mapped[str | None] = mapped_column(String(300))
    po_line_id: Mapped[int | None] = mapped_column(PK)  # set when converted (plain id: avoids FK cycle)


class PurchaseOrder(StatefulMixin, AuditedMixin, Base):
    __tablename__ = "purchase_order"
    __audit_module__ = "purchase"
    __editable_statuses__ = ("DRAFT",)
    __version_mutable_fields__ = frozenset({"workflow_instance_id", "validation_snapshot", "cancel_reason", "vendor_qualification_id"})
    __audit_exclude__ = frozenset({"workflow_instance_id", "validation_snapshot"})
    __table_args__ = (UniqueConstraint("po_no"),
                      CheckConstraint("status IN ('DRAFT','PENDING_APPROVAL','APPROVED','PARTIALLY_RECEIVED','CLOSED','CANCELLED','REJECTED')", name="status"))
    po_no: Mapped[str] = mapped_column(String(30), nullable=False)
    po_date: Mapped[date] = mapped_column(Date, nullable=False)
    vendor_id: Mapped[int] = mapped_column(PK, ForeignKey("vendor.id"), nullable=False, index=True)
    vendor_qualification_id: Mapped[int | None] = mapped_column(PK, ForeignKey("vendor_qualification.id"))
    pr_id: Mapped[int | None] = mapped_column(PK, ForeignKey("purchase_request.id"))
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    payment_terms: Mapped[str | None] = mapped_column(String(200))
    delivery_date: Mapped[date | None] = mapped_column(Date)
    purchase_conditions: Mapped[str | None] = mapped_column(Text)
    quality_requirements: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(25), default="DRAFT", nullable=False)
    workflow_instance_id: Mapped[int | None] = mapped_column(PK, ForeignKey("workflow_instance.id"))
    validation_snapshot: Mapped[str | None] = mapped_column(Text)   # JSON: rule results at create/submit/approve
    cancel_reason: Mapped[str | None] = mapped_column(String(500))


class PurchaseOrderLine(VersionChildMixin, AuditedMixin, Base):
    __tablename__ = "purchase_order_line"
    __audit_module__ = "purchase"
    __version_parent_model__ = "app.models.purchase.PurchaseOrder"
    __version_parent_fk__ = "po_id"
    __child_mutable_fields__ = frozenset({"received_quantity"})
    __table_args__ = (UniqueConstraint("po_id", "line_no"),
                      CheckConstraint("quantity > 0", name="quantity"), CheckConstraint("rate >= 0", name="rate"),
                      CheckConstraint("tax_pct >= 0 AND tax_pct <= 100", name="tax"))
    po_id: Mapped[int] = mapped_column(PK, ForeignKey("purchase_order.id"), nullable=False, index=True)
    line_no: Mapped[int] = mapped_column(Integer, nullable=False)
    material_id: Mapped[int] = mapped_column(PK, ForeignKey("material.id"), nullable=False)
    specification_id: Mapped[int] = mapped_column(PK, ForeignKey("specification.id"), nullable=False)
    vendor_material_id: Mapped[int] = mapped_column(PK, ForeignKey("vendor_material.id"), nullable=False)
    pr_line_id: Mapped[int | None] = mapped_column(PK)
    quantity: Mapped[Decimal] = mapped_column(QTY, nullable=False)
    unit_id: Mapped[int] = mapped_column(PK, ForeignKey("unit.id"), nullable=False)
    rate: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    tax_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    delivery_date: Mapped[date | None] = mapped_column(Date)
    received_quantity: Mapped[Decimal] = mapped_column(QTY, nullable=False, default=0)  # maintained by GRN (Phase 4)
    remarks: Mapped[str | None] = mapped_column(String(300))
