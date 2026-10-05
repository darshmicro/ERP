"""Controlled status engine. Statuses change only through transition() (spec 55, BR-SEC-001)."""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Iterator

from sqlalchemy.orm import Session

from app.audit import service as audit
from app.audit.context import get_context, set_reason
from app.core.errors import IllegalTransition, PermissionDenied
from app.models.audit import StatusHistory

_active: ContextVar[bool] = ContextVar("transition_active", default=False)


def transition_active() -> bool:
    return _active.get()


@contextmanager
def transition_context() -> Iterator[None]:
    token = _active.set(True)
    try:
        yield
    finally:
        _active.reset(token)


@dataclass(frozen=True)
class Transition:
    to_status: str
    permission: str | None = None          # required permission code
    signature_meaning: str | None = None   # informational; signing performed by caller/service
    requires_reason: bool = False


@dataclass
class StateMachine:
    name: str
    initial: str
    transitions: dict[str, dict[str, Transition]] = field(default_factory=dict)

    def allowed(self, from_status: str) -> dict[str, Transition]:
        return self.transitions.get(from_status, {})

    def statuses(self) -> set[str]:
        s = {self.initial}
        for f, d in self.transitions.items():
            s.add(f)
            s.update(d)
        return s


def transition(session: Session, machine: StateMachine, obj: Any, to_status: str, *,
               user_permissions: set[str] | None = None, reason: str | None = None,
               signature_id: int | None = None, module: str = "core") -> None:
    ctx = get_context()
    field_name = obj.__status_field__
    current = getattr(obj, field_name)
    t = machine.allowed(current).get(to_status)
    if t is None:
        raise IllegalTransition(f"{machine.name}: {current} -> {to_status} is not allowed",
                                rule_id="BR-STATUS")
    if t.permission and user_permissions is not None and t.permission not in user_permissions:
        raise PermissionDenied(f"Permission {t.permission} required for {current} -> {to_status}")
    eff_reason = reason or ctx.reason
    if t.requires_reason and not eff_reason:
        from app.core.errors import ReasonRequired
        raise ReasonRequired(f"A reason is required for {current} -> {to_status}")
    if eff_reason and not ctx.reason:
        set_reason(eff_reason)
    with transition_context():
        setattr(obj, field_name, to_status)
        session.flush()
    session.add(StatusHistory(entity=type(obj).__tablename__, record_id=str(obj.id), from_status=current,
                              to_status=to_status, user_id=ctx.user_id, signature_id=signature_id,
                              reason=eff_reason))
    audit.log_event(session, module=module, entity=type(obj).__tablename__, record_id=obj.id,
                    action="STATUS_CHANGE", field_name=field_name, old=current, new=to_status,
                    reason=eff_reason, signature_id=signature_id)
