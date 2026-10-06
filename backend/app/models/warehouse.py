"""Phase 4: GRN, lots (material batches), containers, inventory ledger, holds, labels, temperature, destruction."""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (Boolean, CheckConstraint, Date, ForeignKey, Index, Integer, Numeric, String, Text,
                        UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import PK, Base, UTCDateTime
from app.core.time import utcnow
from app.models.base import AppendOnlyMixin, AuditedMixin, StatefulMixin, VersionChildMixin

QTY = Numeric(18, 6)
DISPOSITIONS = ("QUARANTINE", "QC_TESTING", "QC_APPROVED", "QA_REVIEW", "APPROVED", "REJECTED", "EXPIRED", "RETURNED", "DESTROYED")


class ChecklistItem(AuditedMixin, Base):
    __tablename__ = "checklist_item"
    __audit_module__ = "warehouse"
    __reason_required__ = True
    __table_args__ = (UniqueConstraint("code"),)
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    text: Mapped[str] = mapped_column(String(200), nullable=False)
    is_critical: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    seq: Mapped[int] = mapped_column(Integer, default=100)


class GRN(StatefulMixin, AuditedMixin, Base):
    __tablename__ = "grn"
    __audit_module__ = "warehouse"
    __editable_statuses__ = ("DRAFT",)
    __version_mutable_fields__ = frozenset({"checklist_passed", "quarantine_location_id", "verified_by_id", "reject_reason"})
    __table_args__ = (UniqueConstraint("grn_no"),
                      CheckConstraint("status IN ('DRAFT','SUBMITTED','VERIFIED','QUARANTINE','REJECTED','CANCELLED')", name="status"))
    grn_no: Mapped[str] = mapped_column(String(30), nullable=False)
    grn_date: Mapped[date] = mapped_column(Date, nullable=False)
    po_id: Mapped[int] = mapped_column(PK, ForeignKey("purchase_order.id"), nullable=False, index=True)
    vendor_id: Mapped[int] = mapped_column(PK, ForeignKey("vendor.id"), nullable=False)
    invoice_no: Mapped[str | None] = mapped_column(String(60))
    invoice_date: Mapped[date | None] = mapped_column(Date)
    vehicle_no: Mapped[str | None] = mapped_column(String(30))
    transporter: Mapped[str | None] = mapped_column(String(100))
    transport_details: Mapped[str | None] = mapped_column(String(300))
    remarks: Mapped[str | None] = mapped_column(String(500))
    received_by_id: Mapped[int] = mapped_column(PK, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="DRAFT", nullable=False)
    checklist_passed: Mapped[bool | None] = mapped_column(Boolean)
    quarantine_location_id: Mapped[int | None] = mapped_column(PK, ForeignKey("location.id"))
    verified_by_id: Mapped[int | None] = mapped_column(PK)
    reject_reason: Mapped[str | None] = mapped_column(String(500))


class GRNLine(VersionChildMixin, AuditedMixin, Base):
    __tablename__ = "grn_line"
    __audit_module__ = "warehouse"
    __version_parent_model__ = "app.models.warehouse.GRN"
    __version_parent_fk__ = "grn_id"
    __child_mutable_fields__ = frozenset({"material_batch_id"})
    __table_args__ = (UniqueConstraint("grn_id", "line_no"), CheckConstraint("quantity_received > 0", name="qty"),
                      CheckConstraint("expiry_date IS NULL OR mfg_date IS NULL OR expiry_date >= mfg_date", name="dates"))
    grn_id: Mapped[int] = mapped_column(PK, ForeignKey("grn.id"), nullable=False, index=True)
    line_no: Mapped[int] = mapped_column(Integer, nullable=False)
    po_line_id: Mapped[int] = mapped_column(PK, ForeignKey("purchase_order_line.id"), nullable=False)
    material_id: Mapped[int] = mapped_column(PK, ForeignKey("material.id"), nullable=False)
    vendor_batch_no: Mapped[str] = mapped_column(String(60), nullable=False)
    quantity_received: Mapped[Decimal] = mapped_column(QTY, nullable=False)
    unit_id: Mapped[int] = mapped_column(PK, ForeignKey("unit.id"), nullable=False)
    pack_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    mfg_date: Mapped[date | None] = mapped_column(Date)
    expiry_date: Mapped[date | None] = mapped_column(Date)
    retest_date: Mapped[date | None] = mapped_column(Date)
    coa_received: Mapped[bool] = mapped_column(Boolean, default=False)
    container_condition: Mapped[str | None] = mapped_column(String(100))
    seal_condition: Mapped[str | None] = mapped_column(String(100))
    packaging_condition: Mapped[str | None] = mapped_column(String(100))
    temperature_condition: Mapped[str | None] = mapped_column(String(100))
    other_documents: Mapped[str | None] = mapped_column(String(300))
    material_batch_id: Mapped[int | None] = mapped_column(PK)   # lot created at verification


class GRNChecklist(AuditedMixin, Base):
    __tablename__ = "grn_checklist"
    __audit_module__ = "warehouse"
    __table_args__ = (UniqueConstraint("grn_id", "item_id"), CheckConstraint("answer IN ('YES','NO','NA')", name="answer"))
    grn_id: Mapped[int] = mapped_column(PK, ForeignKey("grn.id"), nullable=False, index=True)
    item_id: Mapped[int] = mapped_column(PK, ForeignKey("checklist_item.id"), nullable=False)
    answer: Mapped[str] = mapped_column(String(3), nullable=False)
    comment: Mapped[str | None] = mapped_column(String(300))
    exception_ref: Mapped[str | None] = mapped_column(String(100))        # deviation / QA exception reference
    exception_signature_id: Mapped[int | None] = mapped_column(PK, ForeignKey("e_signature.id"))


class MaterialBatch(StatefulMixin, AuditedMixin, Base):
    """A lot. Disposition is controlled by the status engine; holds are an overlay (quality_hold)."""

    __tablename__ = "material_batch"
    __audit_module__ = "warehouse"
    __status_field__ = "disposition"
    __editable_statuses__ = ()          # identity/quantity/dates are never edited after creation
    __version_mutable_fields__ = frozenset({"qc_no", "qa_release_no", "released_at", "release_signature_id",
                                            "specification_id", "retest_date", "sampling_plan_id"})
    __table_args__ = (UniqueConstraint("lot_no"),
                      CheckConstraint("disposition IN " + str(DISPOSITIONS), name="disposition"),
                      Index("ix_lot_material_disp", "material_id", "disposition"))
    lot_no: Mapped[str] = mapped_column(String(40), nullable=False)
    material_id: Mapped[int] = mapped_column(PK, ForeignKey("material.id"), nullable=False)
    source_type: Mapped[str] = mapped_column(String(10), default="GRN", nullable=False)   # GRN / MFG / POOL
    grn_line_id: Mapped[int | None] = mapped_column(PK)
    manufacturing_batch_id: Mapped[int | None] = mapped_column(PK)
    vendor_id: Mapped[int | None] = mapped_column(PK, ForeignKey("vendor.id"))
    vendor_batch_no: Mapped[str | None] = mapped_column(String(60))
    mfg_date: Mapped[date | None] = mapped_column(Date)
    expiry_date: Mapped[date | None] = mapped_column(Date)
    retest_date: Mapped[date | None] = mapped_column(Date)
    quantity: Mapped[Decimal] = mapped_column(QTY, nullable=False)
    unit_id: Mapped[int] = mapped_column(PK, ForeignKey("unit.id"), nullable=False)
    disposition: Mapped[str] = mapped_column(String(15), default="QUARANTINE", nullable=False)
    qc_no: Mapped[str | None] = mapped_column(String(40))
    qa_release_no: Mapped[str | None] = mapped_column(String(40))
    released_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    release_signature_id: Mapped[int | None] = mapped_column(PK)
    specification_id: Mapped[int | None] = mapped_column(PK, ForeignKey("specification.id"))
    sampling_plan_id: Mapped[int | None] = mapped_column(PK, ForeignKey("sampling_plan.id"))


class MaterialContainer(AuditedMixin, Base):
    __tablename__ = "material_container"
    __audit_module__ = "warehouse"
    __table_args__ = (UniqueConstraint("batch_id", "container_no"),)
    batch_id: Mapped[int] = mapped_column(PK, ForeignKey("material_batch.id"), nullable=False, index=True)
    container_no: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(QTY, nullable=False)


class InventoryTransaction(AppendOnlyMixin, Base):
    """Authoritative stock ledger (design decision C-05). Never updated or deleted."""

    __tablename__ = "inventory_transaction"
    __table_args__ = (CheckConstraint("quantity > 0", name="qty_positive"),
                      CheckConstraint("txn_type IN ('RECEIPT','TRANSFER','SAMPLE','ISSUE','RETURN','REJECT_MOVE','DESTROY',"
                                      "'ADJUST_IN','ADJUST_OUT','DISPATCH','OUTPUT')", name="txn_type"),
                      Index("ix_invtxn_batch_ts", "material_batch_id", "txn_ts"))
    material_batch_id: Mapped[int] = mapped_column(PK, ForeignKey("material_batch.id"), nullable=False)
    txn_type: Mapped[str] = mapped_column(String(15), nullable=False)
    from_location_id: Mapped[int | None] = mapped_column(PK, ForeignKey("location.id"))
    to_location_id: Mapped[int | None] = mapped_column(PK, ForeignKey("location.id"))
    quantity: Mapped[Decimal] = mapped_column(QTY, nullable=False)
    unit_id: Mapped[int] = mapped_column(PK, ForeignKey("unit.id"), nullable=False)
    ref_doc_type: Mapped[str | None] = mapped_column(String(30))
    ref_doc_id: Mapped[str | None] = mapped_column(String(40))
    reverses_txn_id: Mapped[int | None] = mapped_column(PK)
    reason: Mapped[str | None] = mapped_column(String(500))
    signature_id: Mapped[int | None] = mapped_column(PK)
    user_id: Mapped[int | None] = mapped_column(PK)
    txn_ts: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


class InventoryBalance(Base):
    """Projection of the ledger, maintained in the same transaction (verified by `inventory.verify_ledger`)."""

    __tablename__ = "inventory_balance"
    __table_args__ = (UniqueConstraint("material_batch_id", "location_id"),
                      CheckConstraint("qty_on_hand >= 0", name="on_hand"), CheckConstraint("qty_reserved >= 0", name="reserved"),
                      CheckConstraint("qty_reserved <= qty_on_hand", name="reserved_le_on_hand"))
    id: Mapped[int] = mapped_column(PK, primary_key=True, autoincrement=True)
    material_batch_id: Mapped[int] = mapped_column(PK, ForeignKey("material_batch.id"), nullable=False, index=True)
    location_id: Mapped[int] = mapped_column(PK, ForeignKey("location.id"), nullable=False, index=True)
    qty_on_hand: Mapped[Decimal] = mapped_column(QTY, nullable=False, default=0)
    qty_reserved: Mapped[Decimal] = mapped_column(QTY, nullable=False, default=0)


class QualityHold(StatefulMixin, AuditedMixin, Base):
    __tablename__ = "quality_hold"
    __audit_module__ = "quality"
    __editable_statuses__ = ()
    __version_mutable_fields__ = frozenset({"released_by_id", "released_at", "release_reason", "release_signature_id"})
    __table_args__ = (CheckConstraint("status IN ('OPEN','RELEASED')", name="status"),
                      CheckConstraint("entity_type IN ('MATERIAL_BATCH','MFG_BATCH')", name="entity_type"),
                      Index("ix_hold_entity", "entity_type", "record_id", "status"))
    hold_no: Mapped[str] = mapped_column(String(30), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(15), nullable=False)
    record_id: Mapped[int] = mapped_column(PK, nullable=False)
    status: Mapped[str] = mapped_column(String(10), default="OPEN", nullable=False)
    source: Mapped[str] = mapped_column(String(15), default="MANUAL")      # MANUAL / OOS / TEMPERATURE / GRN / OTHER
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    ref: Mapped[str | None] = mapped_column(String(60))
    placed_by_id: Mapped[int | None] = mapped_column(PK)
    placed_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    released_by_id: Mapped[int | None] = mapped_column(PK)
    released_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    release_reason: Mapped[str | None] = mapped_column(String(500))
    release_signature_id: Mapped[int | None] = mapped_column(PK)


class MaterialLabel(AppendOnlyMixin, Base):
    """Every label print/reprint is a row (controlled numbering, template version, reason for reprints)."""

    __tablename__ = "material_label"
    __table_args__ = (UniqueConstraint("label_no"), Index("ix_label_batch", "material_batch_id"))
    label_no: Mapped[str] = mapped_column(String(30), nullable=False)
    label_type: Mapped[str] = mapped_column(String(15), nullable=False)    # QUARANTINE / APPROVED / SAMPLE / LOCATION / FG
    material_batch_id: Mapped[int | None] = mapped_column(PK, ForeignKey("material_batch.id"))
    ref_type: Mapped[str | None] = mapped_column(String(30))
    ref_id: Mapped[str | None] = mapped_column(String(40))
    template_version: Mapped[str] = mapped_column(String(10), default="1")
    copies: Mapped[int] = mapped_column(Integer, default=1)
    reprint_reason: Mapped[str | None] = mapped_column(String(300))
    printed_by_id: Mapped[int | None] = mapped_column(PK)
    printed_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class StorageTemperatureLog(AppendOnlyMixin, Base):
    __tablename__ = "storage_temperature_log"
    location_id: Mapped[int] = mapped_column(PK, ForeignKey("location.id"), nullable=False, index=True)
    reading: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    recorded_by_id: Mapped[int | None] = mapped_column(PK)
    excursion: Mapped[bool] = mapped_column(Boolean, default=False)
    remarks: Mapped[str | None] = mapped_column(String(300))


class DestructionRecord(StatefulMixin, AuditedMixin, Base):
    __tablename__ = "destruction_record"
    __audit_module__ = "warehouse"
    __editable_statuses__ = ("REQUESTED",)
    __version_mutable_fields__ = frozenset({"approved_by_id", "approved_signature_id", "executed_at", "ledger_txn_id"})
    __table_args__ = (UniqueConstraint("destruction_no"), CheckConstraint("quantity > 0", name="qty"),
                      CheckConstraint("status IN ('REQUESTED','APPROVED','REJECTED','EXECUTED')", name="status"))
    destruction_no: Mapped[str] = mapped_column(String(30), nullable=False)
    material_batch_id: Mapped[int] = mapped_column(PK, ForeignKey("material_batch.id"), nullable=False)
    location_id: Mapped[int] = mapped_column(PK, ForeignKey("location.id"), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(QTY, nullable=False)
    method: Mapped[str] = mapped_column(String(100), nullable=False)
    reason: Mapped[str] = mapped_column(String(300), nullable=False)
    status: Mapped[str] = mapped_column(String(10), default="REQUESTED", nullable=False)
    requested_by_id: Mapped[int] = mapped_column(PK, nullable=False)
    approved_by_id: Mapped[int | None] = mapped_column(PK)
    approved_signature_id: Mapped[int | None] = mapped_column(PK)
    executed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    ledger_txn_id: Mapped[int | None] = mapped_column(PK)
