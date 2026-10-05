"""Phase 7: dispatch of released finished goods to customers (spec 44-47)."""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, Date, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import PK, Base, UTCDateTime
from app.models.base import AuditedMixin, StatefulMixin, VersionChildMixin

QTY = Numeric(18, 6)
DISPATCH_STATUSES = ("DRAFT", "VALIDATED", "APPROVED", "DISPATCHED", "DELIVERED", "CANCELLED")


class Dispatch(StatefulMixin, AuditedMixin, Base):
    __tablename__ = "dispatch"
    __audit_module__ = "dispatch"
    __editable_statuses__ = ("DRAFT",)
    __version_mutable_fields__ = frozenset({"validation_snapshot", "approved_by_id", "approved_signature_id", "approved_at", "dispatched_by_id", "dispatched_at",
                                            "delivered_at", "delivery_remarks", "cancel_reason"})
    __audit_exclude__ = frozenset({"validation_snapshot"})
    __table_args__ = (UniqueConstraint("dispatch_no"), CheckConstraint("status IN " + str(DISPATCH_STATUSES), name="status"))
    dispatch_no: Mapped[str] = mapped_column(String(30), nullable=False)
    dispatch_date: Mapped[date] = mapped_column(Date, nullable=False)
    customer_id: Mapped[int] = mapped_column(PK, ForeignKey("customer.id"), nullable=False, index=True)
    invoice_no: Mapped[str | None] = mapped_column(String(40))
    transporter: Mapped[str | None] = mapped_column(String(100))
    vehicle_no: Mapped[str | None] = mapped_column(String(30))
    lr_no: Mapped[str | None] = mapped_column(String(40))
    shipping_address: Mapped[str | None] = mapped_column(Text)
    remarks: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(15), default="DRAFT", nullable=False)
    validation_snapshot: Mapped[str | None] = mapped_column(Text)
    created_by_user_id: Mapped[int] = mapped_column(PK, nullable=False)
    approved_by_id: Mapped[int | None] = mapped_column(PK)
    approved_signature_id: Mapped[int | None] = mapped_column(PK, ForeignKey("e_signature.id"))
    approved_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    dispatched_by_id: Mapped[int | None] = mapped_column(PK)
    dispatched_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    delivered_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    delivery_remarks: Mapped[str | None] = mapped_column(String(300))
    cancel_reason: Mapped[str | None] = mapped_column(String(500))


class DispatchLine(VersionChildMixin, AuditedMixin, Base):
    __tablename__ = "dispatch_line"
    __audit_module__ = "dispatch"
    __version_parent_model__ = "app.models.dispatch.Dispatch"
    __version_parent_fk__ = "dispatch_id"
    __child_mutable_fields__ = frozenset({"ledger_txn_id", "coa_id", "reserved"})
    __table_args__ = (UniqueConstraint("dispatch_id", "line_no"), CheckConstraint("quantity > 0", name="qty"))
    dispatch_id: Mapped[int] = mapped_column(PK, ForeignKey("dispatch.id"), nullable=False, index=True)
    line_no: Mapped[int] = mapped_column(Integer, nullable=False)
    material_batch_id: Mapped[int] = mapped_column(PK, ForeignKey("material_batch.id"), nullable=False, index=True)
    location_id: Mapped[int] = mapped_column(PK, ForeignKey("location.id"), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(QTY, nullable=False)
    unit_id: Mapped[int] = mapped_column(PK, ForeignKey("unit.id"), nullable=False)
    reserved: Mapped[bool] = mapped_column(Boolean, default=False)
    coa_id: Mapped[int | None] = mapped_column(PK)
    ledger_txn_id: Mapped[int | None] = mapped_column(PK)
