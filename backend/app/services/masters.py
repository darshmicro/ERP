"""Shared helpers for master-data services: FK checks, controlled sign-and-transition, snapshots."""
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import Session

from app.audit.context import get_context
from app.core.db import Base
from app.core.errors import Conflict, NotFound, ValidationFailed
from app.models.base import AuditedMixin
from app.security.permissions import effective_permissions
from app.services import esign, sod
from app.workflows.state_machine import StateMachine, transition


def model_for_table(table_name: str):
    for m in Base.registry.mappers:
        if m.local_table.name == table_name:
            return m.class_
    raise KeyError(table_name)


def check_foreign_keys(session: Session, Model, data: dict[str, Any]) -> None:
    """Friendly 'unknown X' errors instead of raw FK violations."""
    for col in Model.__table__.columns:
        if col.name in data and data[col.name] is not None and col.foreign_keys:
            fk = next(iter(col.foreign_keys))
            target = model_for_table(fk.column.table.name)
            if session.get(target, data[col.name]) is None:
                raise ValidationFailed(f"Unknown reference for '{col.name}' (id {data[col.name]})")


def ensure_unique(session: Session, Model, field: str, value: Any, exclude_id: int | None = None) -> None:
    from sqlalchemy import func, select
    col = getattr(Model, field)
    q = select(Model.id).where(func.lower(col) == str(value).lower()) if isinstance(value, str) \
        else select(Model.id).where(col == value)
    row = session.execute(q).first()
    if row and row[0] != exclude_id:
        raise Conflict(f"{field} '{value}' already exists")


def get_or_404(session: Session, Model, record_id: int, what: str):
    obj = session.get(Model, record_id)
    if obj is None:
        raise NotFound(f"{what} not found")
    return obj


def snapshot(obj: Any, *, exclude: set[str] | None = None) -> dict:
    """Canonical content snapshot of a row (for signature record hashes)."""
    skip = {"row_version", "updated_at", "updated_by_id", "created_at", "created_by_id"} | (exclude or set())
    out = {}
    for attr in sa_inspect(obj).mapper.column_attrs:
        if attr.key in skip or attr.key in getattr(type(obj), "__audit_sensitive__", ()):
            continue
        v = getattr(obj, attr.key)
        out[attr.key] = v.isoformat() if isinstance(v, (date, datetime)) else str(v) if isinstance(v, Decimal) else v
    return out


def sign_and_transition(session: Session, obj: Any, machine: StateMachine, to_status: str, user, password: str,
                        *, reason: str, meaning: str, sod_action: str | None = None, extra: dict | None = None):
    """The standard controlled GMP approval: SoD -> e-signature (fresh auth) -> status transition."""
    if not (reason or "").strip():
        raise ValidationFailed("A reason is required", code="REASON_REQUIRED")
    entity = type(obj).__tablename__
    if sod_action:
        sod.check(session, user.id, entity, obj.id, sod_action)
    perms = effective_permissions(session, user.id)
    t = machine.allowed(getattr(obj, obj.__status_field__)).get(to_status)
    required = t.permission if t else None
    sig = esign.sign(session, user, password, meaning=meaning, entity=entity, record_id=obj.id,
                     record_snapshot={**snapshot(obj), "to_status": to_status, **(extra or {})},
                     record_version=getattr(obj, "version_no", None), reason=reason,
                     required_permission=required)
    transition(session, machine, obj, to_status, user_permissions=perms, reason=reason,
               signature_id=sig.id, module="master")
    if sod_action:
        sod.record_action(session, entity, obj.id, sod_action, user.id)
    return sig


def record_author(session: Session, obj: Any, action: str) -> None:
    uid = get_context().user_id
    if uid:
        sod.record_action(session, type(obj).__tablename__, obj.id, action, uid)
