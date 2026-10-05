"""SQLAlchemy session hooks: field-level audit capture, reason enforcement, delete refusal,
append-only protection, status-column protection (BR-SEC-001)."""
from sqlalchemy import event, inspect
from sqlalchemy.orm import Session

from app.audit import service
from app.audit.context import get_context
from app.core.errors import ImmutableRecordError, ReasonRequired
from app.core.time import utcnow
from app.models.base import AppendOnlyMixin, AuditedMixin, StatefulMixin

_TECH_FIELDS = {"row_version", "updated_at", "updated_by_id", "created_at", "created_by_id"}
REDACTED = "[REDACTED]"
_installed = False


def _field_changes(obj) -> list[tuple[str, object, object]]:
    st = inspect(obj)
    cls = type(obj)
    excl = set(cls.__audit_exclude__) | _TECH_FIELDS
    out = []
    for attr in st.mapper.column_attrs:
        if attr.key in excl:
            continue
        hist = st.attrs[attr.key].history
        if not hist.has_changes():
            continue
        old = hist.deleted[0] if hist.deleted else None
        new = hist.added[0] if hist.added else None
        if old == new:
            continue
        if attr.key in cls.__audit_sensitive__:
            old = REDACTED if old is not None else None
            new = REDACTED if new is not None else None
        out.append((attr.key, old, new))
    return out


def _snapshot(obj) -> dict:
    cls = type(obj)
    st = inspect(obj)
    skip = set(cls.__audit_exclude__) | {"row_version", "updated_at", "updated_by_id"}
    snap = {}
    for attr in st.mapper.column_attrs:
        if attr.key in skip:
            continue
        v = getattr(obj, attr.key)
        snap[attr.key] = REDACTED if attr.key in cls.__audit_sensitive__ and v is not None else service.to_text(v)
    return snap


def _before_flush(session: Session, flush_context, instances) -> None:
    ctx = get_context()
    from app.workflows import state_machine as sm  # local import (avoid cycle)

    for obj in list(session.deleted):
        if isinstance(obj, (AuditedMixin, AppendOnlyMixin)):
            raise ImmutableRecordError(
                f"{type(obj).__tablename__}: GMP records cannot be deleted", rule_id="BR-RET-001")

    for obj in list(session.new):
        if isinstance(obj, AuditedMixin):
            if obj.created_by_id is None and ctx.user_id:
                obj.created_by_id = ctx.user_id
            session.info.setdefault("audit_new", []).append(obj)

    for obj in list(session.dirty):
        if not session.is_modified(obj, include_collections=False):
            continue
        if isinstance(obj, AppendOnlyMixin):
            raise ImmutableRecordError(f"{type(obj).__tablename__}: record is append-only",
                                       rule_id="BR-AUD-001")
        if isinstance(obj, StatefulMixin):
            field = obj.__status_field__
            hist = inspect(obj).attrs[field].history
            if hist.has_changes() and hist.deleted and not sm.transition_active():
                raise ImmutableRecordError(
                    f"{type(obj).__tablename__}.{field} may only change via the status engine",
                    rule_id="BR-SEC-001")
        if isinstance(obj, AuditedMixin):
            changes = _field_changes(obj)
            if not changes:
                continue
            if type(obj).__reason_required__ and not ctx.reason:
                raise ReasonRequired(
                    f"A reason is required to change {type(obj).__tablename__}", rule_id="GMP-REASON")
            obj.updated_at = utcnow()
            if ctx.user_id:
                obj.updated_by_id = ctx.user_id
            for name, old, new in changes:
                service.log_event(session, module=type(obj).__audit_module__,
                                  entity=type(obj).__tablename__, record_id=obj.id, action="UPDATE",
                                  field_name=name, old=old, new=new)


def _after_flush(session: Session, flush_context) -> None:
    new_objs = session.info.pop("audit_new", [])
    for obj in new_objs:
        service.log_event(session, module=type(obj).__audit_module__, entity=type(obj).__tablename__,
                          record_id=obj.id, action="CREATE", field_name="*",
                          new=_snapshot(obj))


def _before_commit(session: Session) -> None:
    session.flush()
    service.flush_pending(session)


def _after_rollback(session: Session) -> None:
    session.info.pop("audit_pending", None)
    session.info.pop("audit_new", None)


def install() -> None:
    global _installed
    if _installed:
        return
    event.listen(Session, "before_flush", _before_flush)
    event.listen(Session, "after_flush", _after_flush)
    event.listen(Session, "before_commit", _before_commit)
    event.listen(Session, "after_soft_rollback", lambda s, t: _after_rollback(s))
    _installed = True
