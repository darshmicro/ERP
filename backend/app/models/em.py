"""Phase 11a: environmental monitoring (EU GMP Annex 1 style grades, alert/action limits, excursions)."""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, Date, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import PK, Base, UTCDateTime
from app.core.time import utcnow
from app.models.base import AppendOnlyMixin, AuditedMixin, StatefulMixin, VersionChildMixin, VersionedMixin

NUM = Numeric(18, 4)
GRADES = ("A", "B", "C", "D", "NC")
SAMPLE_TYPES = ("VIABLE_AIR", "SETTLE_PLATE", "CONTACT_PLATE", "GLOVE_PRINT", "NONVIABLE_05", "NONVIABLE_5",
                "DIFF_PRESSURE", "TEMPERATURE", "HUMIDITY")
STATES = ("AT_REST", "OPERATIONAL")
EM_STATUSES = ("SAMPLED", "RESULT_ENTERED", "REVIEWED", "CANCELLED")


class EMLimitSet(VersionedMixin, AuditedMixin, Base):
    """Controlled, versioned set of alert/action limits (QA approved, e-signed)."""

    __tablename__ = "em_limit_set"
    __audit_module__ = "em"
    __version_key__ = "limitset_no"
    __table_args__ = (UniqueConstraint("limitset_no", "version_no"),
                      CheckConstraint("status IN ('DRAFT','UNDER_REVIEW','APPROVED','SUPERSEDED')", name="status"))
    limitset_no: Mapped[str] = mapped_column(String(40), nullable=False)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    basis: Mapped[str | None] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(15), default="DRAFT", nullable=False)
    supersedes_id: Mapped[int | None] = mapped_column(PK, ForeignKey("em_limit_set.id"))
    effective_from: Mapped[datetime | None] = mapped_column(UTCDateTime)
    effective_to: Mapped[datetime | None] = mapped_column(UTCDateTime)
    change_reason: Mapped[str | None] = mapped_column(String(1000))
    approved_signature_id: Mapped[int | None] = mapped_column(PK, ForeignKey("e_signature.id"))


class EMLimit(VersionChildMixin, AuditedMixin, Base):
    __tablename__ = "em_limit"
    __audit_module__ = "em"
    __version_parent_model__ = "app.models.em.EMLimitSet"
    __version_parent_fk__ = "limit_set_id"
    __table_args__ = (UniqueConstraint("limit_set_id", "seq", name="uq_em_limit_seq"), UniqueConstraint("limit_set_id", "grade", "sample_type", "state", name="uq_em_limit_key"),
                      CheckConstraint("grade IN " + str(GRADES), name="grade"),
                      CheckConstraint("state IN " + str(STATES), name="state"))
    limit_set_id: Mapped[int] = mapped_column(PK, ForeignKey("em_limit_set.id"), nullable=False, index=True)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    grade: Mapped[str] = mapped_column(String(2), nullable=False)
    sample_type: Mapped[str] = mapped_column(String(15), nullable=False)
    state: Mapped[str] = mapped_column(String(12), nullable=False, default="OPERATIONAL")
    alert_high: Mapped[Decimal | None] = mapped_column(NUM)
    action_high: Mapped[Decimal | None] = mapped_column(NUM)
    alert_low: Mapped[Decimal | None] = mapped_column(NUM)
    action_low: Mapped[Decimal | None] = mapped_column(NUM)
    unit: Mapped[str | None] = mapped_column(String(20))


class EMLocation(AuditedMixin, Base):
    """A monitored room / point with a cleanroom grade."""

    __tablename__ = "em_location"
    __audit_module__ = "em"
    __reason_required__ = True
    __table_args__ = (UniqueConstraint("code"), CheckConstraint("grade IN " + str(GRADES), name="grade"))
    code: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    grade: Mapped[str] = mapped_column(String(2), nullable=False)
    location_id: Mapped[int | None] = mapped_column(PK, ForeignKey("location.id"))
    description: Mapped[str | None] = mapped_column(String(300))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class EMPlan(AuditedMixin, Base):
    """Monitoring programme line: how often a point is sampled for a parameter."""

    __tablename__ = "em_plan"
    __audit_module__ = "em"
    __reason_required__ = True
    __table_args__ = (UniqueConstraint("em_location_id", "sample_type", "state"), CheckConstraint("frequency_days > 0", name="freq"))
    em_location_id: Mapped[int] = mapped_column(PK, ForeignKey("em_location.id"), nullable=False, index=True)
    sample_type: Mapped[str] = mapped_column(String(15), nullable=False)
    state: Mapped[str] = mapped_column(String(12), nullable=False, default="OPERATIONAL")
    frequency_days: Mapped[int] = mapped_column(Integer, nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class EMSample(StatefulMixin, AuditedMixin, Base):
    __tablename__ = "em_sample"
    __audit_module__ = "em"
    __editable_statuses__ = ("SAMPLED",)
    __version_mutable_fields__ = frozenset({"result_value", "result_unit", "outcome", "limit_set_id", "grade", "alert_high", "action_high", "alert_low",
                                            "action_low", "entered_by_id", "entered_at", "reviewed_by_id", "reviewed_at", "review_signature_id",
                                            "deviation_id", "review_comment", "cancel_reason"})
    __table_args__ = (UniqueConstraint("sample_no"), CheckConstraint("status IN " + str(EM_STATUSES), name="status"),
                      CheckConstraint("sample_type IN " + str(SAMPLE_TYPES), name="sample_type"),
                      CheckConstraint("outcome IS NULL OR outcome IN ('WITHIN','ALERT','ACTION')", name="outcome"))
    sample_no: Mapped[str] = mapped_column(String(30), nullable=False)
    em_location_id: Mapped[int] = mapped_column(PK, ForeignKey("em_location.id"), nullable=False, index=True)
    plan_id: Mapped[int | None] = mapped_column(PK, ForeignKey("em_plan.id"))
    sample_type: Mapped[str] = mapped_column(String(15), nullable=False)
    state: Mapped[str] = mapped_column(String(12), nullable=False, default="OPERATIONAL")
    sample_point: Mapped[str | None] = mapped_column(String(100))
    manufacturing_batch_id: Mapped[int | None] = mapped_column(PK, ForeignKey("manufacturing_batch.id"), index=True)
    equipment_id: Mapped[int | None] = mapped_column(PK, ForeignKey("equipment.id"))
    sampled_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    sampled_by_id: Mapped[int] = mapped_column(PK, nullable=False)
    status: Mapped[str] = mapped_column(String(15), default="SAMPLED", nullable=False)
    grade: Mapped[str | None] = mapped_column(String(2))
    limit_set_id: Mapped[int | None] = mapped_column(PK, ForeignKey("em_limit_set.id"))
    alert_high: Mapped[Decimal | None] = mapped_column(NUM)
    action_high: Mapped[Decimal | None] = mapped_column(NUM)
    alert_low: Mapped[Decimal | None] = mapped_column(NUM)
    action_low: Mapped[Decimal | None] = mapped_column(NUM)
    result_value: Mapped[Decimal | None] = mapped_column(NUM)
    result_unit: Mapped[str | None] = mapped_column(String(20))
    outcome: Mapped[str | None] = mapped_column(String(8))
    entered_by_id: Mapped[int | None] = mapped_column(PK)
    entered_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    reviewed_by_id: Mapped[int | None] = mapped_column(PK)
    reviewed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    review_signature_id: Mapped[int | None] = mapped_column(PK, ForeignKey("e_signature.id"))
    review_comment: Mapped[str | None] = mapped_column(String(500))
    deviation_id: Mapped[int | None] = mapped_column(PK)
    remarks: Mapped[str | None] = mapped_column(String(500))
    cancel_reason: Mapped[str | None] = mapped_column(String(300))


class EMIsolate(AuditedMixin, Base):
    """Organism identified from a viable-count sample."""

    __tablename__ = "em_isolate"
    __audit_module__ = "em"
    __table_args__ = (CheckConstraint("cfu_count >= 0", name="cfu"),)
    sample_id: Mapped[int] = mapped_column(PK, ForeignKey("em_sample.id"), nullable=False, index=True)
    organism: Mapped[str] = mapped_column(String(150), nullable=False)
    gram_stain: Mapped[str | None] = mapped_column(String(20))
    cfu_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    identification_method: Mapped[str | None] = mapped_column(String(100))
    identified_by_id: Mapped[int | None] = mapped_column(PK)


class EMResultAmendment(AppendOnlyMixin, Base):
    """Corrections to an entered result keep the original (ALCOA+)."""

    __tablename__ = "em_result_amendment"
    sample_id: Mapped[int] = mapped_column(PK, ForeignKey("em_sample.id"), nullable=False, index=True)
    old_value: Mapped[Decimal | None] = mapped_column(NUM)
    new_value: Mapped[Decimal | None] = mapped_column(NUM)
    old_outcome: Mapped[str | None] = mapped_column(String(8))
    new_outcome: Mapped[str | None] = mapped_column(String(8))
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    user_id: Mapped[int] = mapped_column(PK, nullable=False)
    amended_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
