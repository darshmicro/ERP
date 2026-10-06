"""Versioned quality masters: STP, specification (+parameters), sampling plan."""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (Boolean, CheckConstraint, Date, ForeignKey, Integer, Numeric, String, Text,
                        UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import PK, Base, UTCDateTime
from app.models.base import AuditedMixin, VersionChildMixin, VersionedMixin

VERSION_STATUSES = "('DRAFT','UNDER_REVIEW','APPROVED','SUPERSEDED')"


class _VersionCols:
    version_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(20), default="DRAFT", nullable=False)
    effective_from: Mapped[datetime | None] = mapped_column(UTCDateTime)
    effective_to: Mapped[datetime | None] = mapped_column(UTCDateTime)
    change_reason: Mapped[str | None] = mapped_column(String(1000))
    approved_signature_id: Mapped[int | None] = mapped_column(PK, ForeignKey("e_signature.id"))


class STP(VersionedMixin, _VersionCols, AuditedMixin, Base):
    __tablename__ = "stp"
    __audit_module__ = "quality_master"
    __version_key__ = "stp_no"
    __table_args__ = (UniqueConstraint("stp_no", "version_no"),
                      CheckConstraint(f"status IN {VERSION_STATUSES}", name="status"))
    stp_no: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    supersedes_id: Mapped[int | None] = mapped_column(PK, ForeignKey("stp.id"))
    test_method: Mapped[str | None] = mapped_column(String(200))
    equipment_required: Mapped[str | None] = mapped_column(Text)
    reagents_required: Mapped[str | None] = mapped_column(Text)
    reference_standards: Mapped[str | None] = mapped_column(Text)
    procedure: Mapped[str | None] = mapped_column(Text)
    calculation: Mapped[str | None] = mapped_column(Text)
    acceptance_criteria: Mapped[str | None] = mapped_column(Text)
    safety_precautions: Mapped[str | None] = mapped_column(Text)


class Specification(VersionedMixin, _VersionCols, AuditedMixin, Base):
    __tablename__ = "specification"
    __audit_module__ = "quality_master"
    __version_key__ = "spec_no"
    __table_args__ = (UniqueConstraint("spec_no", "version_no"),
                      CheckConstraint(f"status IN {VERSION_STATUSES}", name="status"))
    spec_no: Mapped[str] = mapped_column(String(40), nullable=False)
    material_id: Mapped[int] = mapped_column(PK, ForeignKey("material.id"), nullable=False, index=True)
    title: Mapped[str | None] = mapped_column(String(200))
    supersedes_id: Mapped[int | None] = mapped_column(PK, ForeignKey("specification.id"))
    pharmacopoeial_reference: Mapped[str | None] = mapped_column(String(100))


class SpecificationParameter(VersionChildMixin, AuditedMixin, Base):
    __tablename__ = "specification_parameter"
    __audit_module__ = "quality_master"
    __version_parent_model__ = "app.models.spec.Specification"
    __version_parent_fk__ = "specification_id"
    __table_args__ = (UniqueConstraint("specification_id", "seq"),
                      CheckConstraint("spec_type IN ('NUMERIC','RANGE','TEXT','PASS_FAIL')", name="spec_type"),
                      CheckConstraint("usl IS NULL OR lsl IS NULL OR usl >= lsl", name="usl_ge_lsl"),
                      CheckConstraint("criticality IN ('CRITICAL','MAJOR','MINOR')", name="criticality"))
    specification_id: Mapped[int] = mapped_column(PK, ForeignKey("specification.id"), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    test_name: Mapped[str] = mapped_column(String(150), nullable=False)
    test_method: Mapped[str | None] = mapped_column(String(150))
    stp_id: Mapped[int | None] = mapped_column(PK, ForeignKey("stp.id"))  # pins the exact STP version
    spec_type: Mapped[str] = mapped_column(String(10), nullable=False, default="NUMERIC")
    lsl: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    usl: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    target: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    unit: Mapped[str | None] = mapped_column(String(20))
    decimal_places: Mapped[int | None] = mapped_column(Integer)
    acceptance_criteria: Mapped[str | None] = mapped_column(String(300))
    pharmacopoeial_reference: Mapped[str | None] = mapped_column(String(100))
    frequency: Mapped[str | None] = mapped_column(String(60))
    criticality: Mapped[str] = mapped_column(String(10), default="MAJOR", nullable=False)
    alert_low: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    alert_high: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    action_low: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    action_high: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))


class SamplingPlan(VersionedMixin, _VersionCols, AuditedMixin, Base):
    __tablename__ = "sampling_plan"
    __audit_module__ = "quality_master"
    __version_key__ = "plan_no"
    __table_args__ = (UniqueConstraint("plan_no", "version_no"),
                      CheckConstraint(f"status IN {VERSION_STATUSES}", name="status"),
                      CheckConstraint("sampling_rule IN ('FIXED','SQRT_N_PLUS_1','PERCENT','ALL')", name="sampling_rule"))
    plan_no: Mapped[str] = mapped_column(String(40), nullable=False)
    material_id: Mapped[int] = mapped_column(PK, ForeignKey("material.id"), nullable=False, index=True)
    supersedes_id: Mapped[int | None] = mapped_column(PK, ForeignKey("sampling_plan.id"))
    sampling_rule: Mapped[str] = mapped_column(String(15), nullable=False, default="SQRT_N_PLUS_1")
    fixed_qty: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    percent: Mapped[Decimal | None] = mapped_column(Numeric(7, 3))
    unit_id: Mapped[int | None] = mapped_column(PK, ForeignKey("unit.id"))
    container_rule: Mapped[str | None] = mapped_column(String(200))
    remarks: Mapped[str | None] = mapped_column(String(500))
