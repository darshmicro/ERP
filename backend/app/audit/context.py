"""Request-scoped audit context (who/where/why)."""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, replace
from typing import Iterator


@dataclass(frozen=True)
class AuditContext:
    user_id: int | None = None
    user_name: str = "SYSTEM"
    role_name: str | None = None
    session_id: str | None = None
    ip_address: str | None = None
    device_info: str | None = None
    correlation_id: str | None = None
    reason: str | None = None


_ctx: ContextVar[AuditContext] = ContextVar("audit_ctx", default=AuditContext())


def get_context() -> AuditContext:
    return _ctx.get()


def set_context(ctx: AuditContext):
    return _ctx.set(ctx)


def reset_context(token) -> None:
    _ctx.reset(token)


def set_reason(reason: str | None) -> None:
    _ctx.set(replace(_ctx.get(), reason=(reason or "").strip() or None))


@contextmanager
def audit_context(ctx: AuditContext) -> Iterator[AuditContext]:
    token = _ctx.set(ctx)
    try:
        yield ctx
    finally:
        _ctx.reset(token)
