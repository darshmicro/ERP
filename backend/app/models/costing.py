"""Phase 11c: costing (lot cost, standard cost, actual batch cost, variance, valuation)."""
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import PK, Base, UTCDateTime
from app.core.time import utcnow
from app.models.base import AppendOnlyMixin, AuditedMixin, StatefulMixin, VersionedMixin

MONEY = Numeric(18, 4)
UNIT_COST = Numeric(18, 6)
QTY = Numeric(18, 6)
COST_BASES = ("PO_RATE", "BATCH_COST", "MANUAL")


class CostRateCard(VersionedMixin, AuditedMixin, Base):
    """Controlled conversion rates (labour, machine, overhead). Approved versions are immutable."""

    __tablename__ = "cost_rate_card"
    __audit_module__ = "costing"
    __version_key__ = "card_no"
    __table_args__ = (UniqueConstraint("card_no", "version_no"),
                      CheckConstraint("status IN ('DRAFT','UNDER_REVIEW','APPROVED','SUPERSEDED')", name="status"),
                      CheckConstraint("labour_rate_per_hour >= 0 AND machine_rate_per_hour >= 0 AND overhead_pct >= 0", name="rates"))
    card_no: Mapped[str] = mapped_column(String(40), nullable=False)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="INR", nullable=False)
    labour_rate_per_hour: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=0)
    machine_rate_per_hour: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=0)
    overhead_pct: Mapped[Decimal] = mapped_column(Numeric(7, 2), nullable=False, default=0)   # % of labour + machine cost
    status: Mapped[str] = mapped_column(String(15), default="DRAFT", nullable=False)
    supersedes_id: Mapped[int | None] = mapped_column(PK, ForeignKey("cost_rate_card.id"))
    effective_from: Mapped[datetime | None] = mapped_column(UTCDateTime)
    effective_to: Mapped[datetime | None] = mapped_column(UTCDateTime)
    change_reason: Mapped[str | None] = mapped_column(String(1000))
    approved_signature_id: Mapped[int | None] = mapped_column(PK, ForeignKey("e_signature.id"))


class StandardCost(AuditedMixin, Base):
    """Standard unit cost per material/product (changes audited with a reason)."""

    __tablename__ = "standard_cost"
    __audit_module__ = "costing"
    __reason_required__ = True
    __table_args__ = (UniqueConstraint("material_id"), CheckConstraint("std_unit_cost >= 0", name="std"))
    material_id: Mapped[int] = mapped_column(PK, ForeignKey("material.id"), nullable=False)
    std_unit_cost: Mapped[Decimal] = mapped_column(UNIT_COST, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="INR", nullable=False)
    remarks: Mapped[str | None] = mapped_column(String(300))


class LotCost(AppendOnlyMixin, Base):
    """Cost history of a lot; the latest row is the current unit cost."""

    __tablename__ = "lot_cost"
    __table_args__ = (CheckConstraint("unit_cost >= 0", name="unit_cost"), CheckConstraint("basis IN " + str(COST_BASES), name="basis"))
    material_batch_id: Mapped[int] = mapped_column(PK, ForeignKey("material_batch.id"), nullable=False, index=True)
    unit_cost: Mapped[Decimal] = mapped_column(UNIT_COST, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="INR", nullable=False)
    basis: Mapped[str] = mapped_column(String(12), nullable=False)
    po_line_id: Mapped[int | None] = mapped_column(PK)
    batch_cost_id: Mapped[int | None] = mapped_column(PK)
    reason: Mapped[str | None] = mapped_column(String(500))
    recorded_by_id: Mapped[int | None] = mapped_column(PK)
    recorded_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


class BatchCost(StatefulMixin, AuditedMixin, Base):
    __tablename__ = "batch_cost"
    __audit_module__ = "costing"
    __editable_statuses__ = ("DRAFT",)
    __version_mutable_fields__ = frozenset({"approved_by_id", "approved_at", "approved_signature_id"})
    __table_args__ = (UniqueConstraint("batch_id"), CheckConstraint("status IN ('DRAFT','APPROVED')", name="status"),
                      CheckConstraint("labour_hours >= 0 AND machine_hours >= 0", name="hours"))
    batch_id: Mapped[int] = mapped_column(PK, ForeignKey("manufacturing_batch.id"), nullable=False)
    rate_card_id: Mapped[int] = mapped_column(PK, ForeignKey("cost_rate_card.id"), nullable=False)
    labour_hours: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    machine_hours: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    material_cost: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=0)
    labour_cost: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=0)
    machine_cost: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=0)
    overhead_cost: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=0)
    total_cost: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=0)
    output_qty: Mapped[Decimal] = mapped_column(QTY, nullable=False, default=0)
    unit_cost: Mapped[Decimal] = mapped_column(UNIT_COST, nullable=False, default=0)
    standard_unit_cost: Mapped[Decimal | None] = mapped_column(UNIT_COST)
    variance: Mapped[Decimal | None] = mapped_column(MONEY)           # actual total - standard unit cost x output
    variance_pct: Mapped[Decimal | None] = mapped_column(Numeric(9, 2))
    currency: Mapped[str] = mapped_column(String(3), default="INR", nullable=False)
    lines_snapshot: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(10), default="DRAFT", nullable=False)
    calculated_by_id: Mapped[int] = mapped_column(PK, nullable=False)
    approved_by_id: Mapped[int | None] = mapped_column(PK)
    approved_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    approved_signature_id: Mapped[int | None] = mapped_column(PK, ForeignKey("e_signature.id"))
