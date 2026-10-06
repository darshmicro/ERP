"""Phase 8 quality system: deviation, CAPA, change control, risk assessment (FMEA), SOP control, complaints and recalls."""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, Date, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import PK, Base, UTCDateTime
from app.core.time import utcnow
from app.models.base import AppendOnlyMixin, AuditedMixin, StatefulMixin, VersionChildMixin, VersionedMixin

QTY = Numeric(18, 6)
DEV_STATUSES = ("OPEN", "INVESTIGATION", "CAPA_PROPOSED", "QA_REVIEW", "CLOSED", "CANCELLED")
CAPA_STATUSES = ("OPEN", "IN_PROGRESS", "EFFECTIVENESS_CHECK", "CLOSED", "CANCELLED")
CC_STATUSES = ("DRAFT", "ASSESSMENT", "APPROVAL", "IMPLEMENTATION", "EFFECTIVENESS", "CLOSED", "REJECTED", "CANCELLED")


class Deviation(StatefulMixin, AuditedMixin, Base):
    __tablename__ = "deviation"
    __audit_module__ = "quality"
    __editable_statuses__ = ("OPEN", "INVESTIGATION")
    __version_mutable_fields__ = frozenset({"closed_by_id", "closed_at", "close_signature_id", "close_comment", "cancel_reason", "capa_id"})
    __table_args__ = (UniqueConstraint("dev_no"), CheckConstraint("status IN " + str(DEV_STATUSES), name="status"),
                      CheckConstraint("severity IN ('MINOR','MAJOR','CRITICAL')", name="severity"))
    dev_no: Mapped[str] = mapped_column(String(30), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(20), default="PROCESS")          # PROCESS / MATERIAL / EQUIPMENT / DOCUMENTATION / QC / OTHER
    severity: Mapped[str] = mapped_column(String(10), default="MINOR", nullable=False)
    source: Mapped[str] = mapped_column(String(15), default="MANUAL")            # MANUAL / IPC / TEMPERATURE / RECONCILIATION / OOS / COMPLAINT
    entity_type: Mapped[str | None] = mapped_column(String(20))                  # MATERIAL_BATCH / MFG_BATCH
    record_id: Mapped[int | None] = mapped_column(PK)
    blocks_release: Mapped[bool] = mapped_column(Boolean, default=True)           # open deviation blocks QA release / dispatch of the linked lot
    status: Mapped[str] = mapped_column(String(15), default="OPEN", nullable=False)
    raised_by_id: Mapped[int | None] = mapped_column(PK)
    containment: Mapped[str | None] = mapped_column(Text)
    root_cause: Mapped[str | None] = mapped_column(Text)
    impact_assessment: Mapped[str | None] = mapped_column(Text)
    no_capa_justification: Mapped[str | None] = mapped_column(String(500))
    capa_id: Mapped[int | None] = mapped_column(PK)
    closed_by_id: Mapped[int | None] = mapped_column(PK)
    closed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    close_signature_id: Mapped[int | None] = mapped_column(PK, ForeignKey("e_signature.id"))
    close_comment: Mapped[str | None] = mapped_column(String(500))
    cancel_reason: Mapped[str | None] = mapped_column(String(300))


class CAPA(StatefulMixin, AuditedMixin, Base):
    __tablename__ = "capa"
    __audit_module__ = "quality"
    __editable_statuses__ = ("OPEN", "IN_PROGRESS")
    __version_mutable_fields__ = frozenset({"effectiveness_result", "effectiveness_comment", "closed_by_id", "closed_at", "close_signature_id", "cancel_reason"})
    __table_args__ = (UniqueConstraint("capa_no"), CheckConstraint("status IN " + str(CAPA_STATUSES), name="status"))
    capa_no: Mapped[str] = mapped_column(String(30), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    capa_type: Mapped[str] = mapped_column(String(12), default="CORRECTIVE")     # CORRECTIVE / PREVENTIVE
    source: Mapped[str] = mapped_column(String(15), default="DEVIATION")         # DEVIATION / OOS / COMPLAINT / AUDIT / OTHER
    source_ref: Mapped[str | None] = mapped_column(String(60))
    owner_id: Mapped[int] = mapped_column(PK, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    effectiveness_due: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="OPEN", nullable=False)
    effectiveness_result: Mapped[str | None] = mapped_column(String(15))         # EFFECTIVE / INEFFECTIVE
    effectiveness_comment: Mapped[str | None] = mapped_column(String(500))
    closed_by_id: Mapped[int | None] = mapped_column(PK)
    closed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    close_signature_id: Mapped[int | None] = mapped_column(PK, ForeignKey("e_signature.id"))
    cancel_reason: Mapped[str | None] = mapped_column(String(300))
    created_by_user_id: Mapped[int | None] = mapped_column(PK)


class CAPAAction(AuditedMixin, Base):
    __tablename__ = "capa_action"
    __audit_module__ = "quality"
    capa_id: Mapped[int] = mapped_column(PK, ForeignKey("capa.id"), nullable=False, index=True)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    owner_id: Mapped[int] = mapped_column(PK, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(8), default="OPEN")              # OPEN / DONE
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    completion_notes: Mapped[str | None] = mapped_column(String(500))


class ChangeControl(StatefulMixin, AuditedMixin, Base):
    __tablename__ = "change_control"
    __audit_module__ = "quality"
    __editable_statuses__ = ("DRAFT", "ASSESSMENT")
    __version_mutable_fields__ = frozenset({"approved_by_id", "approved_signature_id", "approved_at", "closed_by_id", "closed_at", "close_signature_id",
                                            "decision_comment", "implementation_notes", "effectiveness_notes"})
    __table_args__ = (UniqueConstraint("cc_no"), CheckConstraint("status IN " + str(CC_STATUSES), name="status"))
    cc_no: Mapped[str] = mapped_column(String(30), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    change_type: Mapped[str] = mapped_column(String(15), default="MASTER_DATA")  # MASTER_DATA / PROCESS / EQUIPMENT / DOCUMENT / SYSTEM / OTHER
    risk_level: Mapped[str | None] = mapped_column(String(8))                    # LOW / MEDIUM / HIGH
    impact_assessment: Mapped[str | None] = mapped_column(Text)
    regulatory_impact: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(15), default="DRAFT", nullable=False)
    requested_by_id: Mapped[int] = mapped_column(PK, nullable=False)
    approved_by_id: Mapped[int | None] = mapped_column(PK)
    approved_signature_id: Mapped[int | None] = mapped_column(PK, ForeignKey("e_signature.id"))
    approved_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    decision_comment: Mapped[str | None] = mapped_column(String(500))
    implementation_notes: Mapped[str | None] = mapped_column(Text)
    effectiveness_notes: Mapped[str | None] = mapped_column(Text)
    closed_by_id: Mapped[int | None] = mapped_column(PK)
    closed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    close_signature_id: Mapped[int | None] = mapped_column(PK, ForeignKey("e_signature.id"))


class ChangeControlLink(AuditedMixin, Base):
    """Versioned master (spec / STP / sampling plan / BOM / vendor-material / qualification / SOP) governed by a change control."""

    __tablename__ = "change_control_link"
    __audit_module__ = "quality"
    __table_args__ = (UniqueConstraint("cc_id", "entity", "record_id"),)
    cc_id: Mapped[int] = mapped_column(PK, ForeignKey("change_control.id"), nullable=False, index=True)
    entity: Mapped[str] = mapped_column(String(40), nullable=False)             # table name of the versioned master
    record_id: Mapped[int] = mapped_column(PK, nullable=False)


class RiskAssessment(StatefulMixin, AuditedMixin, Base):
    __tablename__ = "risk_assessment"
    __audit_module__ = "quality"
    __editable_statuses__ = ("DRAFT",)
    __version_mutable_fields__ = frozenset({"approved_by_id", "approved_signature_id", "approved_at"})
    __table_args__ = (UniqueConstraint("ra_no"), CheckConstraint("status IN ('DRAFT','APPROVED','OBSOLETE')", name="status"))
    ra_no: Mapped[str] = mapped_column(String(30), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    scope: Mapped[str | None] = mapped_column(Text)
    ref_type: Mapped[str | None] = mapped_column(String(20))                    # CHANGE_CONTROL / DEVIATION / VENDOR / MATERIAL / PROCESS
    ref_no: Mapped[str | None] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(10), default="DRAFT", nullable=False)
    created_by_user_id: Mapped[int | None] = mapped_column(PK)
    approved_by_id: Mapped[int | None] = mapped_column(PK)
    approved_signature_id: Mapped[int | None] = mapped_column(PK, ForeignKey("e_signature.id"))
    approved_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class RiskItem(VersionChildMixin, AuditedMixin, Base):
    """FMEA row. RPN = severity x occurrence x detection (computed server-side). Editable only while the assessment is DRAFT."""

    __tablename__ = "risk_item"
    __audit_module__ = "quality"
    __version_parent_model__ = "app.models.quality.RiskAssessment"
    __version_parent_fk__ = "ra_id"
    __table_args__ = (UniqueConstraint("ra_id", "seq"),
                      CheckConstraint("severity BETWEEN 1 AND 10 AND occurrence BETWEEN 1 AND 10 AND detection BETWEEN 1 AND 10", name="scores"))
    ra_id: Mapped[int] = mapped_column(PK, ForeignKey("risk_assessment.id"), nullable=False, index=True)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    function_step: Mapped[str] = mapped_column(String(200), nullable=False)
    failure_mode: Mapped[str] = mapped_column(String(300), nullable=False)
    effect: Mapped[str | None] = mapped_column(String(300))
    cause: Mapped[str | None] = mapped_column(String(300))
    controls: Mapped[str | None] = mapped_column(String(300))
    severity: Mapped[int] = mapped_column(Integer, nullable=False)
    occurrence: Mapped[int] = mapped_column(Integer, nullable=False)
    detection: Mapped[int] = mapped_column(Integer, nullable=False)
    rpn: Mapped[int] = mapped_column(Integer, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(8), nullable=False)
    mitigation: Mapped[str | None] = mapped_column(String(500))
    residual_severity: Mapped[int | None] = mapped_column(Integer)
    residual_occurrence: Mapped[int | None] = mapped_column(Integer)
    residual_detection: Mapped[int | None] = mapped_column(Integer)
    residual_rpn: Mapped[int | None] = mapped_column(Integer)
    residual_level: Mapped[str | None] = mapped_column(String(8))


class SOP(VersionedMixin, AuditedMixin, Base):
    __tablename__ = "sop"
    __audit_module__ = "quality"
    __version_key__ = "sop_no"
    __version_mutable_fields__ = frozenset({"review_due_date"})
    __table_args__ = (UniqueConstraint("sop_no", "version_no"),
                      CheckConstraint("status IN ('DRAFT','UNDER_REVIEW','APPROVED','SUPERSEDED')", name="status"))
    sop_no: Mapped[str] = mapped_column(String(40), nullable=False)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    department_id: Mapped[int | None] = mapped_column(PK, ForeignKey("department.id"))
    owner_id: Mapped[int | None] = mapped_column(PK)
    document_id: Mapped[int | None] = mapped_column(PK, ForeignKey("document.id"))
    review_period_months: Mapped[int] = mapped_column(Integer, default=24)
    review_due_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(15), default="DRAFT", nullable=False)
    supersedes_id: Mapped[int | None] = mapped_column(PK, ForeignKey("sop.id"))
    effective_from: Mapped[datetime | None] = mapped_column(UTCDateTime)
    effective_to: Mapped[datetime | None] = mapped_column(UTCDateTime)
    change_reason: Mapped[str | None] = mapped_column(String(1000))
    approved_signature_id: Mapped[int | None] = mapped_column(PK, ForeignKey("e_signature.id"))


class SOPAcknowledgement(AppendOnlyMixin, Base):
    """Read-and-understood record: user x SOP version."""

    __tablename__ = "sop_acknowledgement"
    __table_args__ = (UniqueConstraint("sop_id", "user_id"),)
    sop_id: Mapped[int] = mapped_column(PK, ForeignKey("sop.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(PK, nullable=False)
    acknowledged_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


class Complaint(StatefulMixin, AuditedMixin, Base):
    __tablename__ = "complaint"
    __audit_module__ = "quality"
    __editable_statuses__ = ("RECEIVED",)
    __version_mutable_fields__ = frozenset({"investigation", "conclusion", "deviation_id", "closed_by_id", "closed_at", "close_signature_id", "hold_id"})
    __table_args__ = (UniqueConstraint("complaint_no"), CheckConstraint("status IN ('RECEIVED','INVESTIGATION','CLOSED','CANCELLED')", name="status"),
                      CheckConstraint("severity IN ('MINOR','MAJOR','CRITICAL')", name="severity"))
    complaint_no: Mapped[str] = mapped_column(String(30), nullable=False)
    received_on: Mapped[date] = mapped_column(Date, nullable=False)
    customer_id: Mapped[int | None] = mapped_column(PK, ForeignKey("customer.id"))
    material_batch_id: Mapped[int | None] = mapped_column(PK, ForeignKey("material_batch.id"), index=True)
    dispatch_id: Mapped[int | None] = mapped_column(PK, ForeignKey("dispatch.id"))
    category: Mapped[str] = mapped_column(String(20), default="QUALITY")         # QUALITY / ADVERSE_EVENT / PACKAGING / DELIVERY / OTHER
    severity: Mapped[str] = mapped_column(String(10), default="MINOR", nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(15), default="RECEIVED", nullable=False)
    investigation: Mapped[str | None] = mapped_column(Text)
    conclusion: Mapped[str | None] = mapped_column(Text)
    deviation_id: Mapped[int | None] = mapped_column(PK)
    hold_id: Mapped[int | None] = mapped_column(PK)
    created_by_user_id: Mapped[int | None] = mapped_column(PK)
    closed_by_id: Mapped[int | None] = mapped_column(PK)
    closed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    close_signature_id: Mapped[int | None] = mapped_column(PK, ForeignKey("e_signature.id"))


class Recall(StatefulMixin, AuditedMixin, Base):
    __tablename__ = "recall"
    __audit_module__ = "quality"
    __editable_statuses__ = ("INITIATED",)
    __version_mutable_fields__ = frozenset({"closed_by_id", "closed_at", "close_signature_id", "closure_summary", "initiated_signature_id"})
    __table_args__ = (UniqueConstraint("recall_no"), CheckConstraint("status IN ('INITIATED','IN_PROGRESS','CLOSED')", name="status"),
                      CheckConstraint("recall_class IN ('I','II','III')", name="class"))
    recall_no: Mapped[str] = mapped_column(String(30), nullable=False)
    material_batch_id: Mapped[int] = mapped_column(PK, ForeignKey("material_batch.id"), nullable=False, index=True)
    recall_class: Mapped[str] = mapped_column(String(3), default="II")
    reason: Mapped[str] = mapped_column(String(1000), nullable=False)
    complaint_id: Mapped[int | None] = mapped_column(PK)
    status: Mapped[str] = mapped_column(String(12), default="INITIATED", nullable=False)
    initiated_by_id: Mapped[int | None] = mapped_column(PK)
    initiated_signature_id: Mapped[int | None] = mapped_column(PK, ForeignKey("e_signature.id"))
    hold_id: Mapped[int | None] = mapped_column(PK)
    closure_summary: Mapped[str | None] = mapped_column(String(1000))
    closed_by_id: Mapped[int | None] = mapped_column(PK)
    closed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    close_signature_id: Mapped[int | None] = mapped_column(PK, ForeignKey("e_signature.id"))


class RecallLine(AuditedMixin, Base):
    """One affected customer shipment of the recalled lot (computed from the dispatch ledger at initiation)."""

    __tablename__ = "recall_line"
    __audit_module__ = "quality"
    __table_args__ = (UniqueConstraint("recall_id", "dispatch_id"),)
    recall_id: Mapped[int] = mapped_column(PK, ForeignKey("recall.id"), nullable=False, index=True)
    dispatch_id: Mapped[int] = mapped_column(PK, ForeignKey("dispatch.id"), nullable=False)
    customer_id: Mapped[int] = mapped_column(PK, ForeignKey("customer.id"), nullable=False)
    quantity_dispatched: Mapped[Decimal] = mapped_column(QTY, nullable=False)
    notified_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    response: Mapped[str | None] = mapped_column(String(300))
    quantity_returned: Mapped[Decimal] = mapped_column(QTY, default=0, nullable=False)
    quantity_consumed_or_unrecoverable: Mapped[Decimal] = mapped_column(QTY, default=0, nullable=False)
