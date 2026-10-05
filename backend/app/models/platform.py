from datetime import date, datetime

from sqlalchemy import (Boolean, CheckConstraint, Date, ForeignKey, Index, Integer, String, Text,
                        UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import PK, Base, UTCDateTime
from app.core.time import utcnow
from app.models.base import AppendOnlyMixin, AuditedMixin, StatefulMixin


class NumberSequence(Base):
    """Counter per (plant, doc type, period). Allocated with an atomic UPDATE (see numbering service)."""

    __tablename__ = "number_sequence"
    __table_args__ = (UniqueConstraint("plant_id", "doc_type", "period_key"),)
    id: Mapped[int] = mapped_column(PK, primary_key=True, autoincrement=True)
    plant_id: Mapped[int] = mapped_column(PK, ForeignKey("plant.id"), nullable=False)
    doc_type: Mapped[str] = mapped_column(String(30), nullable=False)
    period_key: Mapped[str] = mapped_column(String(10), nullable=False)  # '2026' or 'ALL'
    current_value: Mapped[int] = mapped_column(PK, nullable=False, default=0)


class NumberRegistry(AuditedMixin, Base):
    """Per doc-type numbering configuration (prefix/format/reset) administrators may change."""

    __tablename__ = "number_registry"
    __audit_module__ = "config"
    __reason_required__ = True
    __table_args__ = (UniqueConstraint("plant_id", "doc_type"),
                      CheckConstraint("reset_policy IN ('YEARLY','NEVER')", name="reset_policy"))
    plant_id: Mapped[int] = mapped_column(PK, ForeignKey("plant.id"), nullable=False)
    doc_type: Mapped[str] = mapped_column(String(30), nullable=False)
    prefix: Mapped[str] = mapped_column(String(20), nullable=False)
    format: Mapped[str] = mapped_column(String(100), nullable=False, default="{prefix}-{year}-{seq:06d}")
    reset_policy: Mapped[str] = mapped_column(String(10), nullable=False, default="YEARLY")


class SystemConfiguration(AuditedMixin, Base):
    __tablename__ = "system_configuration"
    __audit_module__ = "config"
    __reason_required__ = True
    __table_args__ = (UniqueConstraint("config_key"),)
    config_key: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(String(300))


class Notification(Base):
    __tablename__ = "notification"
    __table_args__ = (Index("ix_notification_user", "user_id", "read_at"),)
    id: Mapped[int] = mapped_column(PK, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(PK, ForeignKey("users.id"), nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str | None] = mapped_column(Text)
    ref_entity: Mapped[str | None] = mapped_column(String(80))
    ref_id: Mapped[str | None] = mapped_column(String(60))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    read_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    emailed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class Document(Base):
    """Write-once controlled document (BR-DOC-001). Replacement = new row linked by supersedes_id."""

    __tablename__ = "document"
    id: Mapped[int] = mapped_column(PK, primary_key=True, autoincrement=True)
    doc_no: Mapped[str | None] = mapped_column(String(60))
    version: Mapped[str] = mapped_column(String(20), default="1")
    effective_date: Mapped[date | None] = mapped_column(Date)
    expiry_date: Mapped[date | None] = mapped_column(Date)
    original_name: Mapped[str] = mapped_column(String(260), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(PK, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    storage_key: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    supersedes_id: Mapped[int | None] = mapped_column(PK, ForeignKey("document.id"))
    uploaded_by_id: Mapped[int | None] = mapped_column(PK)
    uploaded_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class WorkflowDefinition(StatefulMixin, AuditedMixin, Base):
    __tablename__ = "workflow_definition"
    __audit_module__ = "workflow"
    __reason_required__ = True
    __table_args__ = (UniqueConstraint("process_code", "version_no"),
                      CheckConstraint("status IN ('DRAFT','APPROVED','SUPERSEDED')", name="status"))
    process_code: Mapped[str] = mapped_column(String(60), nullable=False)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="DRAFT", nullable=False)
    effective_from: Mapped[datetime | None] = mapped_column(UTCDateTime)
    approved_signature_id: Mapped[int | None] = mapped_column(PK, ForeignKey("e_signature.id"))


class WorkflowStep(Base):
    """Steps belong to exactly one definition version; DRAFT only, immutable once APPROVED."""

    __tablename__ = "workflow_step"
    __table_args__ = (UniqueConstraint("definition_id", "seq"),
                      CheckConstraint("min_approvals >= 1", name="min_approvals"))
    id: Mapped[int] = mapped_column(PK, primary_key=True, autoincrement=True)
    definition_id: Mapped[int] = mapped_column(PK, ForeignKey("workflow_definition.id"), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    role_id: Mapped[int] = mapped_column(PK, ForeignKey("role.id"), nullable=False)
    min_approvals: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    esig_required: Mapped[bool] = mapped_column(Boolean, default=True)
    meaning: Mapped[str] = mapped_column(String(40), default="APPROVED_BY")
    sla_hours: Mapped[int | None] = mapped_column(Integer)
    escalate_role_id: Mapped[int | None] = mapped_column(PK, ForeignKey("role.id"))
    reject_to_seq: Mapped[int | None] = mapped_column(Integer)  # null => rejection is terminal


class WorkflowInstance(StatefulMixin, Base):
    __tablename__ = "workflow_instance"
    __table_args__ = (Index("ix_wfi_record", "entity", "record_id"),
                      CheckConstraint("status IN ('IN_PROGRESS','APPROVED','REJECTED','CANCELLED')",
                                      name="status"))
    id: Mapped[int] = mapped_column(PK, primary_key=True, autoincrement=True)
    definition_id: Mapped[int] = mapped_column(PK, ForeignKey("workflow_definition.id"), nullable=False)
    process_code: Mapped[str] = mapped_column(String(60), nullable=False)
    entity: Mapped[str] = mapped_column(String(80), nullable=False)
    record_id: Mapped[str] = mapped_column(String(60), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="IN_PROGRESS", nullable=False)
    current_seq: Mapped[int] = mapped_column(Integer, nullable=False)
    initiated_by_id: Mapped[int] = mapped_column(PK, ForeignKey("users.id"), nullable=False)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    step_started_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class WorkflowTransaction(AppendOnlyMixin, Base):
    __tablename__ = "workflow_transaction"
    instance_id: Mapped[int] = mapped_column(PK, ForeignKey("workflow_instance.id"), nullable=False, index=True)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    actor_id: Mapped[int] = mapped_column(PK, ForeignKey("users.id"), nullable=False)
    decision: Mapped[str] = mapped_column(String(20), nullable=False)  # SUBMIT/APPROVE/REJECT/CANCEL
    signature_id: Mapped[int | None] = mapped_column(PK, ForeignKey("e_signature.id"))
    comment: Mapped[str | None] = mapped_column(String(1000))
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
