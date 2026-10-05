"""Phase 9: controlled report runs (printed-copy control), retention policies, archive packages, backup status."""
from datetime import date, datetime

from sqlalchemy import Boolean, CheckConstraint, Date, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import PK, Base, UTCDateTime
from app.core.time import utcnow
from app.models.base import AppendOnlyMixin, AuditedMixin


class ReportRun(AppendOnlyMixin, Base):
    """Every export/print of a report or controlled document: who, what, with which parameters, and the hash of the output (copy control)."""

    __tablename__ = "report_run"
    copy_no: Mapped[str] = mapped_column(String(30), nullable=False, unique=True)
    report_code: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    params_json: Mapped[str | None] = mapped_column(Text)
    output_format: Mapped[str] = mapped_column(String(8), nullable=False)
    row_count: Mapped[int | None] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[int] = mapped_column(PK, nullable=False)
    username: Mapped[str] = mapped_column(String(80), nullable=False)
    run_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    ref_entity: Mapped[str | None] = mapped_column(String(40))
    ref_id: Mapped[str | None] = mapped_column(String(40))


class RetentionPolicy(AuditedMixin, Base):
    __tablename__ = "retention_policy"
    __audit_module__ = "retention"
    __reason_required__ = True
    __table_args__ = (UniqueConstraint("record_type"), CheckConstraint("retention_years >= 1", name="years"))
    record_type: Mapped[str] = mapped_column(String(40), nullable=False)
    retention_years: Mapped[int] = mapped_column(Integer, nullable=False)
    legal_hold: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    legal_hold_reason: Mapped[str | None] = mapped_column(String(500))
    basis: Mapped[str | None] = mapped_column(String(300))          # e.g. "EU GMP Ch.4: 1 year after expiry or 5 years after QP certification"
    last_archived_cutoff: Mapped[date | None] = mapped_column(Date)


class ArchiveBatch(AppendOnlyMixin, Base):
    """Non-destructive archive package: records older than the retention cut-off exported with a hash. Originals are never deleted by the application."""

    __tablename__ = "archive_batch"
    archive_no: Mapped[str] = mapped_column(String(30), nullable=False, unique=True)
    record_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    cutoff_date: Mapped[date] = mapped_column(Date, nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    document_id: Mapped[int] = mapped_column(PK, ForeignKey("document.id"), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by_id: Mapped[int | None] = mapped_column(PK)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


class BackupRecord(AppendOnlyMixin, Base):
    """Evidence of backup / restore-test events (the application records them; it does not run the backup tooling)."""

    __tablename__ = "backup_record"
    __table_args__ = (CheckConstraint("backup_type IN ('FULL','DIFFERENTIAL','LOG','DOCUMENTS','RESTORE_TEST')", name="type"),
                      CheckConstraint("result IN ('SUCCESS','FAILED')", name="result"))
    backup_type: Mapped[str] = mapped_column(String(15), nullable=False)
    performed_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    result: Mapped[str] = mapped_column(String(8), default="SUCCESS", nullable=False)
    location: Mapped[str | None] = mapped_column(String(300))
    size_mb: Mapped[int | None] = mapped_column(Integer)
    sha256: Mapped[str | None] = mapped_column(String(64))
    tool: Mapped[str | None] = mapped_column(String(100))
    notes: Mapped[str | None] = mapped_column(String(500))
    audit_chain_verified: Mapped[bool | None] = mapped_column(Boolean)       # restore test: hash chain verified on the restored copy
    rto_minutes: Mapped[int | None] = mapped_column(Integer)                  # restore test: measured recovery time
    recorded_by_id: Mapped[int | None] = mapped_column(PK)
    recorded_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
