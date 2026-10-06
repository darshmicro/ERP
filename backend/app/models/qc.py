"""Phase 5: sampling, QC/LIMS tests and results, amendments, OOS/OOT, COA, conditional release."""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (Boolean, CheckConstraint, Date, ForeignKey, Index, Integer, Numeric, String, Text,
                        UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import PK, Base, UTCDateTime
from app.core.time import utcnow
from app.models.base import AppendOnlyMixin, AuditedMixin, StatefulMixin, VersionChildMixin

QTY = Numeric(18, 6)
SAMPLE_TYPES = ("RM_SAMPLE", "PM_SAMPLE", "IN_PROCESS", "SFG", "FG", "STABILITY", "RETENTION", "VENDOR", "INVESTIGATION")


class Sample(StatefulMixin, AuditedMixin, Base):
    __tablename__ = "sample"
    __audit_module__ = "qc"
    __editable_statuses__ = ("CREATED",)
    __version_mutable_fields__ = frozenset({"retention_until", "disposal_approved_by_id", "disposed_at", "disposal_signature_id"})
    __table_args__ = (UniqueConstraint("sample_no"), CheckConstraint("quantity_sampled > 0", name="qty"),
                      CheckConstraint("sample_type IN " + str(SAMPLE_TYPES), name="sample_type"),
                      CheckConstraint("status IN ('CREATED','TESTING','COMPLETED','RETAINED','DISPOSED')", name="status"))
    sample_no: Mapped[str] = mapped_column(String(30), nullable=False)
    sample_type: Mapped[str] = mapped_column(String(15), nullable=False, default="RM_SAMPLE")
    material_batch_id: Mapped[int | None] = mapped_column(PK, ForeignKey("material_batch.id"), index=True)
    mfg_batch_id: Mapped[int | None] = mapped_column(PK, index=True)           # in-process / manufacturing-batch samples
    specification_id: Mapped[int | None] = mapped_column(PK, ForeignKey("specification.id"))
    sampling_plan_id: Mapped[int | None] = mapped_column(PK, ForeignKey("sampling_plan.id"))
    quantity_received: Mapped[Decimal | None] = mapped_column(QTY)
    quantity_sampled: Mapped[Decimal] = mapped_column(QTY, nullable=False)
    unit_id: Mapped[int] = mapped_column(PK, ForeignKey("unit.id"), nullable=False)
    containers_sampled: Mapped[int] = mapped_column(Integer, default=1)
    sampling_location_id: Mapped[int | None] = mapped_column(PK, ForeignKey("location.id"))
    sampled_by_id: Mapped[int] = mapped_column(PK, nullable=False)
    sampled_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    stage: Mapped[str | None] = mapped_column(String(60))                       # in-process stage
    remarks: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(12), default="CREATED", nullable=False)
    retention_until: Mapped[date | None] = mapped_column(Date)
    disposal_approved_by_id: Mapped[int | None] = mapped_column(PK)
    disposal_signature_id: Mapped[int | None] = mapped_column(PK)
    disposed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class QCTest(StatefulMixin, AuditedMixin, Base):
    __tablename__ = "qc_test"
    __audit_module__ = "qc"
    __editable_statuses__ = ("ASSIGNED",)
    __version_mutable_fields__ = frozenset({"started_at", "completed_at", "equipment_id", "calibration_status",
                                            "calibration_override_signature_id", "analyst_id"})
    __table_args__ = (CheckConstraint("status IN ('ASSIGNED','STARTED','SUBMITTED','INVALIDATED')", name="status"),
                      Index("ix_qctest_sample", "sample_id"))
    sample_id: Mapped[int] = mapped_column(PK, ForeignKey("sample.id"), nullable=False)
    spec_parameter_id: Mapped[int | None] = mapped_column(PK, ForeignKey("specification_parameter.id"))
    test_name: Mapped[str] = mapped_column(String(150), nullable=False)
    stp_id: Mapped[int | None] = mapped_column(PK, ForeignKey("stp.id"))
    analyst_id: Mapped[int | None] = mapped_column(PK)
    equipment_id: Mapped[int | None] = mapped_column(PK, ForeignKey("equipment.id"))
    calibration_status: Mapped[str | None] = mapped_column(String(20))
    calibration_override_signature_id: Mapped[int | None] = mapped_column(PK, ForeignKey("e_signature.id"))
    status: Mapped[str] = mapped_column(String(12), default="ASSIGNED", nullable=False)
    retest_of_id: Mapped[int | None] = mapped_column(PK)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class QCResult(StatefulMixin, AuditedMixin, Base):
    """Immutable once SUBMITTED. Corrections are separate amendment rows (original is always retained)."""

    __tablename__ = "qc_result"
    __audit_module__ = "qc"
    __editable_statuses__ = ("DRAFT",)
    __table_args__ = (UniqueConstraint("test_id"),
                      CheckConstraint("pass_fail IN ('PASS','FAIL','NA')", name="pass_fail"),
                      CheckConstraint("status IN ('DRAFT','SUBMITTED')", name="status"))
    test_id: Mapped[int] = mapped_column(PK, ForeignKey("qc_test.id"), nullable=False)
    spec_type: Mapped[str] = mapped_column(String(10), nullable=False)
    value_numeric: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    rounded_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    value_text: Mapped[str | None] = mapped_column(String(300))
    unit: Mapped[str | None] = mapped_column(String(20))
    lsl: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    usl: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    target: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    decimal_places: Mapped[int | None] = mapped_column(Integer)
    acceptance_criteria: Mapped[str | None] = mapped_column(String(300))
    pass_fail: Mapped[str] = mapped_column(String(4), nullable=False)
    remarks: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(10), default="DRAFT", nullable=False)
    entered_by_id: Mapped[int] = mapped_column(PK, nullable=False)
    entered_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


class QCResultAmendment(StatefulMixin, AuditedMixin, Base):
    __tablename__ = "qc_result_amendment"
    __audit_module__ = "qc"
    __editable_statuses__ = ("REQUESTED",)
    __version_mutable_fields__ = frozenset({"approved_by_id", "approved_signature_id", "decided_at", "decision_comment"})
    __table_args__ = (CheckConstraint("status IN ('REQUESTED','APPROVED','REJECTED')", name="status"),)
    result_id: Mapped[int] = mapped_column(PK, ForeignKey("qc_result.id"), nullable=False, index=True)
    original_value: Mapped[str | None] = mapped_column(String(300))
    new_value: Mapped[str] = mapped_column(String(300), nullable=False)
    new_pass_fail: Mapped[str] = mapped_column(String(4), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(10), default="REQUESTED", nullable=False)
    requested_by_id: Mapped[int] = mapped_column(PK, nullable=False)
    approved_by_id: Mapped[int | None] = mapped_column(PK)
    approved_signature_id: Mapped[int | None] = mapped_column(PK, ForeignKey("e_signature.id"))
    decided_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    decision_comment: Mapped[str | None] = mapped_column(String(500))


class OOSInvestigation(StatefulMixin, AuditedMixin, Base):
    __tablename__ = "oos_investigation"
    __audit_module__ = "qc"
    __editable_statuses__ = ()
    __version_mutable_fields__ = frozenset({"phase1_findings", "phase2_findings", "root_cause", "capa_ref", "decision",
                                            "decision_reason", "decided_by_id", "decision_signature_id", "closed_at", "hold_id"})
    __table_args__ = (UniqueConstraint("oos_no"),
                      CheckConstraint("status IN ('RAISED','PHASE1','PHASE2','DECIDED','CLOSED')", name="status"))
    oos_no: Mapped[str] = mapped_column(String(30), nullable=False)
    qc_result_id: Mapped[int] = mapped_column(PK, ForeignKey("qc_result.id"), nullable=False)
    qc_test_id: Mapped[int] = mapped_column(PK, ForeignKey("qc_test.id"), nullable=False)
    sample_id: Mapped[int] = mapped_column(PK, ForeignKey("sample.id"), nullable=False)
    material_batch_id: Mapped[int | None] = mapped_column(PK, ForeignKey("material_batch.id"))
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(10), default="RAISED", nullable=False)
    phase1_findings: Mapped[str | None] = mapped_column(Text)
    phase2_findings: Mapped[str | None] = mapped_column(Text)
    root_cause: Mapped[str | None] = mapped_column(Text)
    capa_ref: Mapped[str | None] = mapped_column(String(60))
    decision: Mapped[str | None] = mapped_column(String(20))        # CONFIRMED_FAIL / INVALIDATED
    decision_reason: Mapped[str | None] = mapped_column(String(500))
    decided_by_id: Mapped[int | None] = mapped_column(PK)
    decision_signature_id: Mapped[int | None] = mapped_column(PK, ForeignKey("e_signature.id"))
    hold_id: Mapped[int | None] = mapped_column(PK)
    raised_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    closed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class OOTEvent(AuditedMixin, Base):
    __tablename__ = "oot_event"
    __audit_module__ = "qc"
    __table_args__ = (UniqueConstraint("oot_no"),)
    oot_no: Mapped[str] = mapped_column(String(30), nullable=False)
    qc_result_id: Mapped[int] = mapped_column(PK, ForeignKey("qc_result.id"), nullable=False)
    material_id: Mapped[int] = mapped_column(PK, ForeignKey("material.id"), nullable=False)
    test_name: Mapped[str] = mapped_column(String(150), nullable=False)
    rule: Mapped[str] = mapped_column(String(30), nullable=False)       # ALERT_LIMIT / ACTION_LIMIT / NELSON_n
    detail: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(10), default="OPEN")     # OPEN / REVIEWED
    reviewed_by_id: Mapped[int | None] = mapped_column(PK)
    review_comment: Mapped[str | None] = mapped_column(String(500))


class COA(AppendOnlyMixin, Base):
    """Certificate of analysis; every (re)issue is a new immutable version."""

    __tablename__ = "coa"
    __table_args__ = (UniqueConstraint("coa_no", "version_no"),)
    coa_no: Mapped[str] = mapped_column(String(30), nullable=False)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    material_batch_id: Mapped[int | None] = mapped_column(PK, ForeignKey("material_batch.id"), index=True)
    mfg_batch_id: Mapped[int | None] = mapped_column(PK)
    pdf_document_id: Mapped[int] = mapped_column(PK, ForeignKey("document.id"), nullable=False)
    xlsx_document_id: Mapped[int] = mapped_column(PK, ForeignKey("document.id"), nullable=False)
    conclusion: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(300))
    generated_by_id: Mapped[int | None] = mapped_column(PK)
    signature_id: Mapped[int | None] = mapped_column(PK)
    generated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class ConditionalRelease(StatefulMixin, AuditedMixin, Base):
    __tablename__ = "conditional_release"
    __audit_module__ = "qc"
    __editable_statuses__ = ("REQUESTED",)
    __version_mutable_fields__ = frozenset({"quantity_used", "approved_by_id", "approved_signature_id", "decided_at", "decision_comment"})
    __table_args__ = (UniqueConstraint("cr_no"), CheckConstraint("quantity_authorised > 0", name="qty"),
                      CheckConstraint("status IN ('REQUESTED','APPROVED','REJECTED','CLOSED','EXPIRED')", name="status"))
    cr_no: Mapped[str] = mapped_column(String(30), nullable=False)
    material_batch_id: Mapped[int] = mapped_column(PK, ForeignKey("material_batch.id"), nullable=False, index=True)
    quantity_authorised: Mapped[Decimal] = mapped_column(QTY, nullable=False)
    quantity_used: Mapped[Decimal] = mapped_column(QTY, nullable=False, default=0)
    intended_batch_ref: Mapped[str] = mapped_column(String(60), nullable=False)
    mfg_batch_id: Mapped[int | None] = mapped_column(PK)
    justification: Mapped[str] = mapped_column(String(1000), nullable=False)
    risk_assessment_ref: Mapped[str] = mapped_column(String(60), nullable=False)
    identity_confirmed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    expires_at: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(10), default="REQUESTED", nullable=False)
    requested_by_id: Mapped[int] = mapped_column(PK, nullable=False)
    approved_by_id: Mapped[int | None] = mapped_column(PK)
    approved_signature_id: Mapped[int | None] = mapped_column(PK, ForeignKey("e_signature.id"))
    decided_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    decision_comment: Mapped[str | None] = mapped_column(String(500))
