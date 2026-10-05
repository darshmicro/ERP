from datetime import datetime

from sqlalchemy import ForeignKey, Index, String, Text, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import PK, Base, UTCDateTime
from app.core.time import utcnow
from app.models.base import AppendOnlyMixin


class AuditTrail(AppendOnlyMixin, Base):
    __tablename__ = "audit_trail"
    __table_args__ = (Index("ix_audit_entity_record", "entity", "record_id", "occurred_at"),
                      Index("ix_audit_user_time", "user_id", "occurred_at"),
                      Index("ix_audit_time", "occurred_at"))

    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    tz_name: Mapped[str] = mapped_column(String(60), nullable=False)
    module: Mapped[str] = mapped_column(String(40), nullable=False)
    entity: Mapped[str] = mapped_column(String(80), nullable=False)
    record_id: Mapped[str | None] = mapped_column(String(60))
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    field_name: Mapped[str | None] = mapped_column(String(80))
    old_value: Mapped[str | None] = mapped_column(Text)
    new_value: Mapped[str | None] = mapped_column(Text)
    user_id: Mapped[int | None] = mapped_column(PK)  # no FK on purpose: survives any user lifecycle
    user_name: Mapped[str] = mapped_column(String(150), nullable=False)
    role_name: Mapped[str | None] = mapped_column(String(300))
    session_id: Mapped[str | None] = mapped_column(String(40))
    ip_address: Mapped[str | None] = mapped_column(String(64))
    device_info: Mapped[str | None] = mapped_column(String(300))
    reason: Mapped[str | None] = mapped_column(String(1000))
    signature_id: Mapped[int | None] = mapped_column(PK)
    correlation_id: Mapped[str | None] = mapped_column(String(40))
    prev_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    row_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class AuditChainHead(Base):
    """Single row; updating it first serialises audit writers so the hash chain stays linear."""

    __tablename__ = "audit_chain_head"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    lock_counter: Mapped[int] = mapped_column(PK, default=0, nullable=False)
    last_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="GENESIS")
    row_count: Mapped[int] = mapped_column(PK, default=0, nullable=False)


class ESignature(AppendOnlyMixin, Base):
    __tablename__ = "e_signature"
    __table_args__ = (Index("ix_esig_record", "entity", "record_id"),)

    user_id: Mapped[int] = mapped_column(PK, ForeignKey("users.id"), nullable=False)
    signed_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    tz_name: Mapped[str] = mapped_column(String(60), nullable=False)
    printed_name: Mapped[str] = mapped_column(String(150), nullable=False)
    username: Mapped[str] = mapped_column(String(80), nullable=False)
    role_name: Mapped[str | None] = mapped_column(String(300))
    meaning: Mapped[str] = mapped_column(String(40), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(1000))
    entity: Mapped[str] = mapped_column(String(80), nullable=False)
    record_id: Mapped[str] = mapped_column(String(60), nullable=False)
    record_version: Mapped[str | None] = mapped_column(String(30))
    record_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    auth_method: Mapped[str] = mapped_column(String(10), nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(64))
    manifest_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class SecurityEvent(AppendOnlyMixin, Base):
    __tablename__ = "security_event"
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    user_id: Mapped[int | None] = mapped_column(PK)
    username: Mapped[str | None] = mapped_column(String(80))
    ip_address: Mapped[str | None] = mapped_column(String(64))
    detail: Mapped[str | None] = mapped_column(Text)
    correlation_id: Mapped[str | None] = mapped_column(String(40))


class StatusHistory(AppendOnlyMixin, Base):
    """GMP transaction history of every controlled status change (spec 63 stream 4)."""

    __tablename__ = "gmp_status_history"
    __table_args__ = (Index("ix_status_hist_record", "entity", "record_id"),)
    entity: Mapped[str] = mapped_column(String(80), nullable=False)
    record_id: Mapped[str] = mapped_column(String(60), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(40))
    to_status: Mapped[str] = mapped_column(String(40), nullable=False)
    user_id: Mapped[int | None] = mapped_column(PK)
    signature_id: Mapped[int | None] = mapped_column(PK)
    reason: Mapped[str | None] = mapped_column(String(1000))
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


class RecordAction(AppendOnlyMixin, Base):
    """Who performed which controlled action on which record (drives segregation of duties)."""

    __tablename__ = "record_action"
    __table_args__ = (Index("ix_record_action", "entity", "record_id", "action_code"),)
    entity: Mapped[str] = mapped_column(String(80), nullable=False)
    record_id: Mapped[str] = mapped_column(String(60), nullable=False)
    action_code: Mapped[str] = mapped_column(String(100), nullable=False)
    user_id: Mapped[int] = mapped_column(PK, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


class ErrorLog(Base):
    """Technical error index; reference ERR-YYYY-NNNNNN is derived from id."""

    __tablename__ = "error_log"
    id: Mapped[int] = mapped_column(PK, primary_key=True, autoincrement=True)
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    correlation_id: Mapped[str | None] = mapped_column(String(40))
    route: Mapped[str | None] = mapped_column(String(200))
    user_id: Mapped[int | None] = mapped_column(PK)
    error_type: Mapped[str | None] = mapped_column(String(120))
