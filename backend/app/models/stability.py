"""Phase 11b: stability studies (ICH Q1A(R2)-style protocols, pull schedule, results, ICH Q1E-style evaluation)."""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, Date, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import PK, Base, UTCDateTime
from app.core.time import utcnow
from app.models.base import AppendOnlyMixin, AuditedMixin, StatefulMixin, VersionChildMixin, VersionedMixin

QTY = Numeric(18, 6)
CONDITION_TYPES = ("LONG_TERM", "INTERMEDIATE", "ACCELERATED", "STRESS", "REFRIGERATED", "FROZEN")
STUDY_STATUSES = ("PLANNED", "ACTIVE", "COMPLETED", "CONCLUDED", "TERMINATED")
PULL_STATUSES = ("SCHEDULED", "PULLED", "TESTED", "REVIEWED", "MISSED", "SKIPPED")


class StabilityProtocol(VersionedMixin, AuditedMixin, Base):
    __tablename__ = "stability_protocol"
    __audit_module__ = "stability"
    __version_key__ = "protocol_no"
    __table_args__ = (UniqueConstraint("protocol_no", "version_no"),
                      CheckConstraint("status IN ('DRAFT','UNDER_REVIEW','APPROVED','SUPERSEDED')", name="status"))
    protocol_no: Mapped[str] = mapped_column(String(40), nullable=False)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    material_id: Mapped[int] = mapped_column(PK, ForeignKey("material.id"), nullable=False, index=True)
    specification_id: Mapped[int] = mapped_column(PK, ForeignKey("specification.id"), nullable=False)
    container_closure: Mapped[str | None] = mapped_column(String(200))
    proposed_shelf_life_months: Mapped[int | None] = mapped_column(Integer)
    pull_window_days: Mapped[int] = mapped_column(Integer, default=14, nullable=False)
    objective: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(15), default="DRAFT", nullable=False)
    supersedes_id: Mapped[int | None] = mapped_column(PK, ForeignKey("stability_protocol.id"))
    effective_from: Mapped[datetime | None] = mapped_column(UTCDateTime)
    effective_to: Mapped[datetime | None] = mapped_column(UTCDateTime)
    change_reason: Mapped[str | None] = mapped_column(String(1000))
    approved_signature_id: Mapped[int | None] = mapped_column(PK, ForeignKey("e_signature.id"))


class StabilityCondition(VersionChildMixin, AuditedMixin, Base):
    __tablename__ = "stability_condition"
    __audit_module__ = "stability"
    __version_parent_model__ = "app.models.stability.StabilityProtocol"
    __version_parent_fk__ = "protocol_id"
    __table_args__ = (UniqueConstraint("protocol_id", "seq"), CheckConstraint("condition_type IN " + str(CONDITION_TYPES), name="ctype"))
    protocol_id: Mapped[int] = mapped_column(PK, ForeignKey("stability_protocol.id"), nullable=False, index=True)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str] = mapped_column(String(80), nullable=False)
    condition_type: Mapped[str] = mapped_column(String(15), nullable=False)
    temperature_c: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    temperature_tol_c: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    rh_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 1))
    rh_tol_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 1))
    chamber_location_id: Mapped[int | None] = mapped_column(PK, ForeignKey("location.id"))


class StabilityTimepoint(VersionChildMixin, AuditedMixin, Base):
    __tablename__ = "stability_timepoint"
    __audit_module__ = "stability"
    __version_parent_model__ = "app.models.stability.StabilityProtocol"
    __version_parent_fk__ = "protocol_id"
    __table_args__ = (UniqueConstraint("protocol_id", "seq", name="uq_stability_timepoint_seq"), UniqueConstraint("protocol_id", "month", name="uq_stability_timepoint_month"), CheckConstraint("month >= 0", name="month"))
    protocol_id: Mapped[int] = mapped_column(PK, ForeignKey("stability_protocol.id"), nullable=False, index=True)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str | None] = mapped_column(String(40))


class StabilityStudy(StatefulMixin, AuditedMixin, Base):
    __tablename__ = "stability_study"
    __audit_module__ = "stability"
    __editable_statuses__ = ("PLANNED",)
    __version_mutable_fields__ = frozenset({"started_at", "placed_qty", "ledger_txn_id", "completed_at", "shelf_life_months", "conclusion", "concluded_by_id",
                                            "concluded_at", "conclusion_signature_id", "terminate_reason"})
    __table_args__ = (UniqueConstraint("study_no"), CheckConstraint("status IN " + str(STUDY_STATUSES), name="status"),
                      CheckConstraint("units_per_pull > 0", name="units"))
    study_no: Mapped[str] = mapped_column(String(30), nullable=False)
    protocol_id: Mapped[int] = mapped_column(PK, ForeignKey("stability_protocol.id"), nullable=False, index=True)
    material_batch_id: Mapped[int] = mapped_column(PK, ForeignKey("material_batch.id"), nullable=False, index=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    units_per_pull: Mapped[Decimal] = mapped_column(QTY, nullable=False)
    source_location_id: Mapped[int | None] = mapped_column(PK, ForeignKey("location.id"))
    status: Mapped[str] = mapped_column(String(15), default="PLANNED", nullable=False)
    created_by_user_id: Mapped[int] = mapped_column(PK, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    placed_qty: Mapped[Decimal | None] = mapped_column(QTY)
    ledger_txn_id: Mapped[int | None] = mapped_column(PK)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    shelf_life_months: Mapped[int | None] = mapped_column(Integer)
    conclusion: Mapped[str | None] = mapped_column(Text)
    concluded_by_id: Mapped[int | None] = mapped_column(PK)
    concluded_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    conclusion_signature_id: Mapped[int | None] = mapped_column(PK, ForeignKey("e_signature.id"))
    terminate_reason: Mapped[str | None] = mapped_column(String(500))


class StabilityPull(StatefulMixin, AuditedMixin, Base):
    __tablename__ = "stability_pull"
    __audit_module__ = "stability"
    __editable_statuses__ = ()
    __version_mutable_fields__ = frozenset({"pulled_at", "pulled_by_id", "actual_qty", "tested_at", "reviewed_by_id", "reviewed_at", "review_signature_id",
                                            "deviation_id", "oos_deviation_id", "skip_reason", "remarks"})
    __table_args__ = (UniqueConstraint("study_id", "condition_id", "timepoint_id"),
                      CheckConstraint("status IN " + str(PULL_STATUSES), name="status"))
    study_id: Mapped[int] = mapped_column(PK, ForeignKey("stability_study.id"), nullable=False, index=True)
    condition_id: Mapped[int] = mapped_column(PK, ForeignKey("stability_condition.id"), nullable=False)
    timepoint_id: Mapped[int] = mapped_column(PK, ForeignKey("stability_timepoint.id"), nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    window_days: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(10), default="SCHEDULED", nullable=False)
    pulled_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    pulled_by_id: Mapped[int | None] = mapped_column(PK)
    actual_qty: Mapped[Decimal | None] = mapped_column(QTY)
    tested_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    reviewed_by_id: Mapped[int | None] = mapped_column(PK)
    reviewed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    review_signature_id: Mapped[int | None] = mapped_column(PK, ForeignKey("e_signature.id"))
    deviation_id: Mapped[int | None] = mapped_column(PK)           # window / missed-pull deviation
    oos_deviation_id: Mapped[int | None] = mapped_column(PK)       # out-of-specification deviation
    skip_reason: Mapped[str | None] = mapped_column(String(500))
    remarks: Mapped[str | None] = mapped_column(String(500))


class StabilityResult(AppendOnlyMixin, Base):
    """One result of a spec parameter at a pull. Corrections insert a new row that supersedes the old one."""

    __tablename__ = "stability_result"
    __table_args__ = (CheckConstraint("pass_fail IN ('PASS','FAIL')", name="pf"),)
    pull_id: Mapped[int] = mapped_column(PK, ForeignKey("stability_pull.id"), nullable=False, index=True)
    parameter_id: Mapped[int] = mapped_column(PK, ForeignKey("specification_parameter.id"), nullable=False)
    value_numeric: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    rounded_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    value_text: Mapped[str | None] = mapped_column(String(300))
    unit: Mapped[str | None] = mapped_column(String(20))
    lsl: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    usl: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    pass_fail: Mapped[str] = mapped_column(String(4), nullable=False)
    equipment_id: Mapped[int | None] = mapped_column(PK, ForeignKey("equipment.id"))
    supersedes_id: Mapped[int | None] = mapped_column(PK, ForeignKey("stability_result.id"))
    correction_reason: Mapped[str | None] = mapped_column(String(500))
    deviation_id: Mapped[int | None] = mapped_column(PK)
    entered_by_id: Mapped[int] = mapped_column(PK, nullable=False)
    entered_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
