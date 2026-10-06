from datetime import date, datetime

from sqlalchemy import (Boolean, CheckConstraint, Date, ForeignKey, Index, Integer, String, Text,
                        UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import PK, Base, UTCDateTime
from app.core.time import utcnow
from app.models.base import AuditedMixin


class User(AuditedMixin, Base):
    __tablename__ = "users"
    __audit_module__ = "iam"
    __reason_required__ = True
    # Volatile security counters are logged as security events, not field-audited.
    __audit_exclude__ = frozenset({"failed_attempts", "locked_until", "last_login_at", "password_changed_at"})
    __audit_sensitive__ = frozenset({"password_hash"})
    __table_args__ = (
        UniqueConstraint("username"),
        CheckConstraint("auth_source IN ('LOCAL','LDAP')", name="auth_source"),
    )

    username: Mapped[str] = mapped_column(String(80), nullable=False)
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    email: Mapped[str | None] = mapped_column(String(150))
    designation: Mapped[str | None] = mapped_column(String(100))
    department_id: Mapped[int | None] = mapped_column(PK, ForeignKey("department.id"))
    plant_id: Mapped[int | None] = mapped_column(PK, ForeignKey("plant.id"))
    auth_source: Mapped[str] = mapped_column(String(10), default="LOCAL", nullable=False)
    password_hash: Mapped[str | None] = mapped_column(String(300))
    password_changed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    access_expiry: Mapped[date | None] = mapped_column(Date)
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_login_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class Role(AuditedMixin, Base):
    __tablename__ = "role"
    __audit_module__ = "iam"
    __reason_required__ = True
    __table_args__ = (UniqueConstraint("role_code"),)

    role_code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(String(300))
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)
    is_admin_role: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Permission(Base):
    """Seed data defined in code (core/permissions.py); not user-editable."""

    __tablename__ = "permission"
    __table_args__ = (UniqueConstraint("perm_code"),)

    id: Mapped[int] = mapped_column(PK, primary_key=True, autoincrement=True)
    perm_code: Mapped[str] = mapped_column(String(100), nullable=False)
    module: Mapped[str] = mapped_column(String(40), nullable=False)
    resource: Mapped[str] = mapped_column(String(40), nullable=False)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    description: Mapped[str | None] = mapped_column(String(200))


class RolePermission(AuditedMixin, Base):
    __tablename__ = "role_permission"
    __audit_module__ = "iam"
    __table_args__ = (UniqueConstraint("role_id", "permission_id"),)

    role_id: Mapped[int] = mapped_column(PK, ForeignKey("role.id"), nullable=False)
    permission_id: Mapped[int] = mapped_column(PK, ForeignKey("permission.id"), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class UserRole(AuditedMixin, Base):
    __tablename__ = "user_role"
    __audit_module__ = "iam"
    __table_args__ = (UniqueConstraint("user_id", "role_id", "valid_from"),
                      Index("ix_user_role_user", "user_id"))

    user_id: Mapped[int] = mapped_column(PK, ForeignKey("users.id"), nullable=False)
    role_id: Mapped[int] = mapped_column(PK, ForeignKey("role.id"), nullable=False)
    granted_by_id: Mapped[int | None] = mapped_column(PK, ForeignKey("users.id"))
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date)
    is_disabled: Mapped[bool] = mapped_column(Boolean, default=False)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    reason: Mapped[str | None] = mapped_column(String(500))


class UserSession(Base):
    __tablename__ = "user_session"
    __table_args__ = (UniqueConstraint("token_hash"), Index("ix_user_session_user", "user_id"))

    id: Mapped[int] = mapped_column(PK, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(PK, ForeignKey("users.id"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    csrf_token: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    absolute_expires_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(300))
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    revoke_reason: Mapped[str | None] = mapped_column(String(100))


class PasswordHistory(Base):
    __tablename__ = "password_history"
    id: Mapped[int] = mapped_column(PK, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(PK, ForeignKey("users.id"), nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(300), nullable=False)
    set_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class TrainingRecord(AuditedMixin, Base):
    __tablename__ = "training_record"
    __audit_module__ = "iam"
    user_id: Mapped[int] = mapped_column(PK, ForeignKey("users.id"), nullable=False, index=True)
    training_code: Mapped[str] = mapped_column(String(60), nullable=False)  # SOP/document code
    document_version: Mapped[str | None] = mapped_column(String(20))
    trained_on: Mapped[date] = mapped_column(Date, nullable=False)
    valid_until: Mapped[date | None] = mapped_column(Date)
    remarks: Mapped[str | None] = mapped_column(Text)


class SodRule(AuditedMixin, Base):
    """Segregation of duties: the same user may not perform `conflicts_with` and `action_code`
    on the same record."""

    __tablename__ = "sod_rule"
    __audit_module__ = "iam"
    __reason_required__ = True
    __table_args__ = (UniqueConstraint("action_code", "conflicts_with_action_code"),
                      CheckConstraint("enforcement IN ('BLOCK','WARN')", name="enforcement"))
    sod_id: Mapped[str] = mapped_column(String(20), nullable=False)
    action_code: Mapped[str] = mapped_column(String(100), nullable=False)
    conflicts_with_action_code: Mapped[str] = mapped_column(String(100), nullable=False)
    enforcement: Mapped[str] = mapped_column(String(10), default="BLOCK")
    description: Mapped[str | None] = mapped_column(String(300))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
