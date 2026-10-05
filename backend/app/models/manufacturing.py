"""Phase 6: BOM, manufacturing batches, material issue/return, IPC, reconciliation; 6b: antisera (donor animals, bleeds, plasma pools).

Products are Materials of type SFG/FG (single master); their BOMs are versioned masters.
"""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (Boolean, CheckConstraint, Date, ForeignKey, Index, Integer, Numeric, String, Text,
                        UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import PK, Base, UTCDateTime
from app.core.time import utcnow
from app.models.base import AppendOnlyMixin, AuditedMixin, StatefulMixin, VersionChildMixin, VersionedMixin

QTY = Numeric(18, 6)
VER = "('DRAFT','UNDER_REVIEW','APPROVED','SUPERSEDED')"


class BOMHeader(VersionedMixin, AuditedMixin, Base):
    __tablename__ = "bom_header"
    __audit_module__ = "manufacturing"
    __version_key__ = "bom_no"
    __table_args__ = (UniqueConstraint("bom_no", "version_no"), CheckConstraint(f"status IN {VER}", name="status"),
                      CheckConstraint("batch_size > 0", name="batch_size"))
    bom_no: Mapped[str] = mapped_column(String(40), nullable=False)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    product_material_id: Mapped[int] = mapped_column(PK, ForeignKey("material.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), default="DRAFT", nullable=False)
    batch_size: Mapped[Decimal] = mapped_column(QTY, nullable=False)
    unit_id: Mapped[int] = mapped_column(PK, ForeignKey("unit.id"), nullable=False)
    expected_yield_pct: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=100)
    yield_min_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    yield_max_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    description: Mapped[str | None] = mapped_column(String(300))
    supersedes_id: Mapped[int | None] = mapped_column(PK, ForeignKey("bom_header.id"))
    effective_from: Mapped[datetime | None] = mapped_column(UTCDateTime)
    effective_to: Mapped[datetime | None] = mapped_column(UTCDateTime)
    change_reason: Mapped[str | None] = mapped_column(String(1000))
    approved_signature_id: Mapped[int | None] = mapped_column(PK, ForeignKey("e_signature.id"))


class BOMLine(VersionChildMixin, AuditedMixin, Base):
    __tablename__ = "bom_line"
    __audit_module__ = "manufacturing"
    __version_parent_model__ = "app.models.manufacturing.BOMHeader"
    __version_parent_fk__ = "bom_id"
    __table_args__ = (UniqueConstraint("bom_id", "line_no"), CheckConstraint("quantity > 0", name="quantity"),
                      CheckConstraint("overage_pct >= 0 AND process_loss_pct >= 0", name="pct"))
    bom_id: Mapped[int] = mapped_column(PK, ForeignKey("bom_header.id"), nullable=False, index=True)
    line_no: Mapped[int] = mapped_column(Integer, nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False, default=1)       # alias of line_no (used by generic copy)
    material_id: Mapped[int] = mapped_column(PK, ForeignKey("material.id"), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(QTY, nullable=False)
    unit_id: Mapped[int] = mapped_column(PK, ForeignKey("unit.id"), nullable=False)
    percentage: Mapped[Decimal | None] = mapped_column(Numeric(9, 4))
    process_loss_pct: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=0)
    overage_pct: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=0)
    sampling_qty: Mapped[Decimal] = mapped_column(QTY, default=0)
    reconcile: Mapped[bool] = mapped_column(Boolean, default=True)


class MBRStep(VersionChildMixin, AuditedMixin, Base):
    """Master batch record step (instruction template) belonging to a BOM version."""

    __tablename__ = "mbr_step"
    __audit_module__ = "manufacturing"
    __version_parent_model__ = "app.models.manufacturing.BOMHeader"
    __version_parent_fk__ = "bom_id"
    __table_args__ = (UniqueConstraint("bom_id", "step_no"),)
    bom_id: Mapped[int] = mapped_column(PK, ForeignKey("bom_header.id"), nullable=False, index=True)
    step_no: Mapped[int] = mapped_column(Integer, nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    stage: Mapped[str | None] = mapped_column(String(60))
    instruction: Mapped[str] = mapped_column(String(1000), nullable=False)
    requires_verification: Mapped[bool] = mapped_column(Boolean, default=True)
    requires_value: Mapped[bool] = mapped_column(Boolean, default=False)


BATCH_STATUSES = ("CREATED", "MATERIAL_ISSUED", "IN_PROCESS", "PRODUCTION_COMPLETE", "RECONCILED", "QC_QA", "RELEASED", "REJECTED", "CANCELLED")


class ManufacturingBatch(StatefulMixin, AuditedMixin, Base):
    __tablename__ = "manufacturing_batch"
    __audit_module__ = "manufacturing"
    __editable_statuses__ = ("CREATED",)
    __version_mutable_fields__ = frozenset({"actual_qty", "yield_pct", "start_at", "end_at", "output_lot_id", "line_clearance_signature_id",
                                            "uses_conditional_release", "cancel_reason"})
    __table_args__ = (UniqueConstraint("batch_no"), CheckConstraint("batch_type IN ('SFG','FG')", name="batch_type"),
                      CheckConstraint("planned_qty > 0", name="planned"),
                      CheckConstraint("status IN " + str(BATCH_STATUSES), name="status"))
    batch_no: Mapped[str] = mapped_column(String(40), nullable=False)
    batch_type: Mapped[str] = mapped_column(String(3), nullable=False)
    product_material_id: Mapped[int] = mapped_column(PK, ForeignKey("material.id"), nullable=False)
    bom_id: Mapped[int] = mapped_column(PK, ForeignKey("bom_header.id"), nullable=False)
    planned_qty: Mapped[Decimal] = mapped_column(QTY, nullable=False)
    unit_id: Mapped[int] = mapped_column(PK, ForeignKey("unit.id"), nullable=False)
    actual_qty: Mapped[Decimal | None] = mapped_column(QTY)
    yield_pct: Mapped[Decimal | None] = mapped_column(Numeric(7, 2))
    status: Mapped[str] = mapped_column(String(20), default="CREATED", nullable=False)
    created_by_user_id: Mapped[int] = mapped_column(PK, nullable=False)
    number_override_reason: Mapped[str | None] = mapped_column(String(300))
    uses_conditional_release: Mapped[bool] = mapped_column(Boolean, default=False)
    line_clearance_signature_id: Mapped[int | None] = mapped_column(PK, ForeignKey("e_signature.id"))
    output_lot_id: Mapped[int | None] = mapped_column(PK)
    start_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    end_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    cancel_reason: Mapped[str | None] = mapped_column(String(300))


class MaterialIssueIndent(AuditedMixin, Base):
    __tablename__ = "material_issue_indent"
    __audit_module__ = "manufacturing"
    __table_args__ = (UniqueConstraint("indent_no"), UniqueConstraint("batch_id"))
    indent_no: Mapped[str] = mapped_column(String(30), nullable=False)
    batch_id: Mapped[int] = mapped_column(PK, ForeignKey("manufacturing_batch.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(15), default="OPEN")      # OPEN / PARTIAL / ISSUED / CLOSED


class BatchMaterial(AuditedMixin, Base):
    """BOM requirement scaled to this batch; quantities are maintained by the issue/return/consumption services."""

    __tablename__ = "batch_material"
    __audit_module__ = "manufacturing"
    __table_args__ = (UniqueConstraint("batch_id", "bom_line_id"), CheckConstraint("required_qty >= 0", name="required"))
    batch_id: Mapped[int] = mapped_column(PK, ForeignKey("manufacturing_batch.id"), nullable=False, index=True)
    bom_line_id: Mapped[int] = mapped_column(PK, ForeignKey("bom_line.id"), nullable=False)
    material_id: Mapped[int] = mapped_column(PK, ForeignKey("material.id"), nullable=False)
    unit_id: Mapped[int] = mapped_column(PK, ForeignKey("unit.id"), nullable=False)
    required_qty: Mapped[Decimal] = mapped_column(QTY, nullable=False)
    reconcile: Mapped[bool] = mapped_column(Boolean, default=True)
    issued_qty: Mapped[Decimal] = mapped_column(QTY, default=0, nullable=False)
    returned_qty: Mapped[Decimal] = mapped_column(QTY, default=0, nullable=False)
    consumed_qty: Mapped[Decimal | None] = mapped_column(QTY)
    sample_qty: Mapped[Decimal | None] = mapped_column(QTY)
    waste_qty: Mapped[Decimal | None] = mapped_column(QTY)


class MaterialIssue(AppendOnlyMixin, Base):
    """BOM requirement -> material lot -> quantity -> production batch (BR-TRC-001: both FKs mandatory)."""

    __tablename__ = "material_issue"
    __table_args__ = (UniqueConstraint("issue_no"), CheckConstraint("quantity > 0", name="qty"), Index("ix_issue_lot", "material_batch_id"))
    issue_no: Mapped[str] = mapped_column(String(30), nullable=False)
    batch_id: Mapped[int] = mapped_column(PK, ForeignKey("manufacturing_batch.id"), nullable=False, index=True)
    batch_material_id: Mapped[int] = mapped_column(PK, ForeignKey("batch_material.id"), nullable=False)
    material_batch_id: Mapped[int] = mapped_column(PK, ForeignKey("material_batch.id"), nullable=False)
    location_id: Mapped[int] = mapped_column(PK, ForeignKey("location.id"), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(QTY, nullable=False)
    inventory_txn_id: Mapped[int | None] = mapped_column(PK)
    conditional_release_id: Mapped[int | None] = mapped_column(PK)
    fefo_override_reason: Mapped[str | None] = mapped_column(String(300))
    is_additional: Mapped[bool] = mapped_column(Boolean, default=False)
    issued_by_id: Mapped[int | None] = mapped_column(PK)
    issued_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class MaterialReturn(StatefulMixin, AuditedMixin, Base):
    __tablename__ = "material_return"
    __audit_module__ = "manufacturing"
    __editable_statuses__ = ("REQUESTED",)
    __version_mutable_fields__ = frozenset({"accepted_by_id", "accepted_at", "ledger_txn_id", "decision_comment"})
    __table_args__ = (UniqueConstraint("return_no"), CheckConstraint("returned_qty > 0", name="qty"),
                      CheckConstraint("status IN ('REQUESTED','ACCEPTED','REJECTED')", name="status"))
    return_no: Mapped[str] = mapped_column(String(30), nullable=False)
    issue_id: Mapped[int] = mapped_column(PK, ForeignKey("material_issue.id"), nullable=False)
    batch_id: Mapped[int] = mapped_column(PK, ForeignKey("manufacturing_batch.id"), nullable=False)
    batch_material_id: Mapped[int] = mapped_column(PK, ForeignKey("batch_material.id"), nullable=False)
    material_batch_id: Mapped[int] = mapped_column(PK, ForeignKey("material_batch.id"), nullable=False)
    issued_qty: Mapped[Decimal] = mapped_column(QTY, nullable=False)
    used_qty: Mapped[Decimal] = mapped_column(QTY, nullable=False)
    returned_qty: Mapped[Decimal] = mapped_column(QTY, nullable=False)
    damaged_qty: Mapped[Decimal] = mapped_column(QTY, default=0, nullable=False)
    location_id: Mapped[int] = mapped_column(PK, ForeignKey("location.id"), nullable=False)
    reason: Mapped[str] = mapped_column(String(300), nullable=False)
    status: Mapped[str] = mapped_column(String(10), default="REQUESTED", nullable=False)
    requested_by_id: Mapped[int] = mapped_column(PK, nullable=False)
    accepted_by_id: Mapped[int | None] = mapped_column(PK)
    accepted_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    ledger_txn_id: Mapped[int | None] = mapped_column(PK)
    decision_comment: Mapped[str | None] = mapped_column(String(300))


class BatchStepExecution(AuditedMixin, Base):
    __tablename__ = "batch_step_execution"
    __audit_module__ = "manufacturing"
    __table_args__ = (UniqueConstraint("batch_id", "step_no"),)
    batch_id: Mapped[int] = mapped_column(PK, ForeignKey("manufacturing_batch.id"), nullable=False, index=True)
    step_no: Mapped[int] = mapped_column(Integer, nullable=False)
    instruction: Mapped[str] = mapped_column(String(1000), nullable=False)       # snapshot of the pinned BOM version
    requires_verification: Mapped[bool] = mapped_column(Boolean, default=True)
    recorded_value: Mapped[str | None] = mapped_column(String(200))
    performed_by_id: Mapped[int | None] = mapped_column(PK)
    performed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    verified_by_id: Mapped[int | None] = mapped_column(PK)
    verified_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    verify_signature_id: Mapped[int | None] = mapped_column(PK, ForeignKey("e_signature.id"))
    remarks: Mapped[str | None] = mapped_column(String(300))


class BatchEquipmentUse(AuditedMixin, Base):
    __tablename__ = "batch_equipment_use"
    __audit_module__ = "manufacturing"
    batch_id: Mapped[int] = mapped_column(PK, ForeignKey("manufacturing_batch.id"), nullable=False, index=True)
    equipment_id: Mapped[int] = mapped_column(PK, ForeignKey("equipment.id"), nullable=False)
    used_by_id: Mapped[int] = mapped_column(PK, nullable=False)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    calibration_status: Mapped[str | None] = mapped_column(String(20))
    cleaning_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)


class IPCResult(AppendOnlyMixin, Base):
    __tablename__ = "ipc_result"
    __table_args__ = (CheckConstraint("pass_fail IN ('PASS','FAIL','NA')", name="pass_fail"),)
    batch_id: Mapped[int] = mapped_column(PK, ForeignKey("manufacturing_batch.id"), nullable=False, index=True)
    stage: Mapped[str] = mapped_column(String(60), nullable=False)
    parameter: Mapped[str] = mapped_column(String(100), nullable=False)
    value_numeric: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    value_text: Mapped[str | None] = mapped_column(String(200))
    unit: Mapped[str | None] = mapped_column(String(20))
    lsl: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    usl: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    pass_fail: Mapped[str] = mapped_column(String(4), nullable=False)
    equipment_id: Mapped[int | None] = mapped_column(PK, ForeignKey("equipment.id"))
    analyst_id: Mapped[int | None] = mapped_column(PK)
    recorded_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    remarks: Mapped[str | None] = mapped_column(String(300))


class BatchReconciliation(StatefulMixin, AuditedMixin, Base):
    __tablename__ = "batch_reconciliation"
    __audit_module__ = "manufacturing"
    __editable_statuses__ = ()
    __version_mutable_fields__ = frozenset({"production_approved_by_id", "production_signature_id", "qa_approved_by_id", "qa_signature_id",
                                            "deviation_ref", "justification", "approved_at"})
    __table_args__ = (UniqueConstraint("batch_id"),
                      CheckConstraint("status IN ('CALCULATED','PRODUCTION_APPROVED','APPROVED')", name="status"))
    batch_id: Mapped[int] = mapped_column(PK, ForeignKey("manufacturing_batch.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="CALCULATED", nullable=False)
    within_tolerance: Mapped[bool] = mapped_column(Boolean, nullable=False)
    yield_ok: Mapped[bool] = mapped_column(Boolean, default=True)
    tolerance_pct: Mapped[Decimal] = mapped_column(Numeric(6, 3), nullable=False)
    summary_json: Mapped[str] = mapped_column(Text, nullable=False)
    deviation_ref: Mapped[str | None] = mapped_column(String(60))
    justification: Mapped[str | None] = mapped_column(String(500))
    production_approved_by_id: Mapped[int | None] = mapped_column(PK)
    production_signature_id: Mapped[int | None] = mapped_column(PK, ForeignKey("e_signature.id"))
    qa_approved_by_id: Mapped[int | None] = mapped_column(PK)
    qa_signature_id: Mapped[int | None] = mapped_column(PK, ForeignKey("e_signature.id"))
    approved_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


# ----------------------------------------------------------------------------- Phase 6b: antisera
class Animal(AuditedMixin, Base):
    __tablename__ = "animal"
    __audit_module__ = "antisera"
    __reason_required__ = True
    __table_args__ = (UniqueConstraint("animal_tag"), CheckConstraint("status IN ('ACTIVE','QUARANTINED','RETIRED','DECEASED')", name="status"))
    animal_tag: Mapped[str] = mapped_column(String(30), nullable=False)
    species: Mapped[str] = mapped_column(String(40), default="Equine")
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(7, 2))
    status: Mapped[str] = mapped_column(String(12), default="ACTIVE", nullable=False)
    health_notes: Mapped[str | None] = mapped_column(String(500))
    min_bleed_interval_days: Mapped[int] = mapped_column(Integer, default=14)


class ImmunisationRecord(AppendOnlyMixin, Base):
    __tablename__ = "immunisation_record"
    animal_id: Mapped[int] = mapped_column(PK, ForeignKey("animal.id"), nullable=False, index=True)
    antigen: Mapped[str] = mapped_column(String(100), nullable=False)
    dose: Mapped[str | None] = mapped_column(String(60))
    administered_on: Mapped[date] = mapped_column(Date, nullable=False)
    administered_by_id: Mapped[int | None] = mapped_column(PK)
    remarks: Mapped[str | None] = mapped_column(String(300))


class BleedRecord(AuditedMixin, Base):
    __tablename__ = "bleed_record"
    __audit_module__ = "antisera"
    __version_mutable_fields__ = frozenset({"pool_id"})
    __table_args__ = (UniqueConstraint("bleed_no"), CheckConstraint("volume_l > 0", name="vol"))
    bleed_no: Mapped[str] = mapped_column(String(30), nullable=False)
    animal_id: Mapped[int] = mapped_column(PK, ForeignKey("animal.id"), nullable=False, index=True)
    bled_on: Mapped[date] = mapped_column(Date, nullable=False)
    volume_l: Mapped[Decimal] = mapped_column(Numeric(9, 3), nullable=False)
    recorded_by_id: Mapped[int | None] = mapped_column(PK)
    remarks: Mapped[str | None] = mapped_column(String(300))
    pool_id: Mapped[int | None] = mapped_column(PK)


class PlasmaPool(AuditedMixin, Base):
    __tablename__ = "plasma_pool"
    __audit_module__ = "antisera"
    __table_args__ = (UniqueConstraint("pool_no"),)
    pool_no: Mapped[str] = mapped_column(String(30), nullable=False)
    total_volume_l: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    material_batch_id: Mapped[int | None] = mapped_column(PK, ForeignKey("material_batch.id"))
    created_by_id: Mapped[int | None] = mapped_column(PK)
