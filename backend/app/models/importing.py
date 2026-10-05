from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import PK, Base, UTCDateTime
from app.core.time import utcnow
from app.models.base import AppendOnlyMixin, StatefulMixin


class ImportJob(StatefulMixin, Base):
    """Controlled Excel import (spec 87). Uploaded data never touches production tables until approved."""

    __tablename__ = "import_job"
    __table_args__ = (CheckConstraint(
        "status IN ('UPLOADED','VALIDATED','REJECTED','SUBMITTED','APPROVED','IMPORTED','FAILED')", name="status"),)
    id: Mapped[int] = mapped_column(PK, primary_key=True, autoincrement=True)
    entity: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="UPLOADED", nullable=False)
    filename: Mapped[str] = mapped_column(String(260), nullable=False)
    document_id: Mapped[int] = mapped_column(PK, ForeignKey("document.id"), nullable=False)
    total_rows: Mapped[int] = mapped_column(Integer, default=0)
    error_rows: Mapped[int] = mapped_column(Integer, default=0)
    created_by_id: Mapped[int] = mapped_column(PK, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    submitted_by_id: Mapped[int | None] = mapped_column(PK)
    approved_by_id: Mapped[int | None] = mapped_column(PK)
    approved_signature_id: Mapped[int | None] = mapped_column(PK)
    imported_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    result_summary: Mapped[str | None] = mapped_column(Text)


class ImportRow(Base):
    """Staging row. Mutable only by the validation step of its own job."""

    __tablename__ = "import_row"
    id: Mapped[int] = mapped_column(PK, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(PK, ForeignKey("import_job.id"), nullable=False, index=True)
    row_no: Mapped[int] = mapped_column(Integer, nullable=False)
    data_json: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(10), default="VALID")  # VALID/ERROR/IMPORTED
    errors_json: Mapped[str | None] = mapped_column(Text)
