"""FastAPI dependencies: DB session, authentication, CSRF, authorisation, audit context."""
from datetime import timedelta
from typing import Callable, Iterator

from fastapi import Depends, Request
from starlette.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.context import AuditContext, set_context
from app.core import db
from app.core.config import get_settings
from app.core.errors import AuthenticationError, PermissionDenied
from app.core.time import utcnow
from app.models.iam import User, UserSession
from app.security.permissions import active_role_codes, effective_permissions
from app.services.auth_service import hash_token
from app.services.security_events import log_security_event

COOKIE = "merp_session"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def get_db() -> Iterator[Session]:
    s = db.new_session()
    try:
        yield s
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


class Principal:
    def __init__(self, user: User, session: UserSession, perms: set[str], roles: list[str]):
        self.user, self.session, self.perms, self.roles = user, session, perms, roles


def client_ip(request: Request) -> str | None:
    fwd = request.headers.get("x-forwarded-for")
    if fwd and request.app.state.trust_proxy:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else None


async def get_principal(request: Request, s: Session = Depends(get_db)) -> Principal:
    """Async on purpose: the audit ContextVar must be set in the request task so it propagates to the
    (threadpool-run) endpoint. Blocking DB work is pushed to a worker thread."""
    principal, ctx = await run_in_threadpool(_authenticate, request, s)
    set_context(ctx)
    request.state.principal = principal
    return principal


def _authenticate(request: Request, s: Session):
    cfg = get_settings()
    token = request.cookies.get(COOKIE)
    if not token:
        raise AuthenticationError("Not authenticated.")
    sess = s.execute(select(UserSession).where(UserSession.token_hash == hash_token(token))).scalar_one_or_none()
    now = utcnow()
    if sess is None or sess.revoked_at is not None:
        raise AuthenticationError("Session is no longer valid. Please log in again.")
    if now > sess.absolute_expires_at or now > sess.last_seen_at + timedelta(minutes=cfg.session_idle_minutes):
        _expire(sess.id, "timeout")
        raise AuthenticationError("Session expired. Please log in again.", code="SESSION_EXPIRED")
    user = s.get(User, sess.user_id)
    from datetime import date
    if user is None or not user.is_active or (user.access_expiry and user.access_expiry < date.today()):
        raise AuthenticationError("Account is not active.")
    if request.method not in SAFE_METHODS:
        if request.headers.get("x-csrf-token") != sess.csrf_token:
            log_security_event("CSRF_REJECTED", user_id=user.id, username=user.username,
                               ip=client_ip(request), detail=request.url.path)
            raise PermissionDenied("CSRF token missing or invalid.", code="CSRF")
    if now - sess.last_seen_at > timedelta(seconds=30):
        _touch(sess.id)
    perms = effective_permissions(s, user.id)
    roles = active_role_codes(s, user.id)
    ctx = AuditContext(user_id=user.id, user_name=user.username, role_name=", ".join(roles),
                       session_id=str(sess.id), ip_address=client_ip(request),
                       device_info=(request.headers.get("user-agent") or "")[:300],
                       correlation_id=getattr(request.state, "correlation_id", None),
                       reason=_reason(request))
    return Principal(user, sess, perms, roles), ctx


def _reason(request: Request) -> str | None:
    r = request.headers.get("x-change-reason")
    return r.strip()[:1000] if r and r.strip() else None


def _expire(session_id: int, why: str) -> None:
    s = db.new_session()
    try:
        row = s.get(UserSession, session_id)
        if row and row.revoked_at is None:
            row.revoked_at = utcnow()
            row.revoke_reason = why
            s.commit()
    finally:
        s.close()


def _touch(session_id: int) -> None:
    s = db.new_session()
    try:
        row = s.get(UserSession, session_id)
        if row:
            row.last_seen_at = utcnow()
            s.commit()
    finally:
        s.close()


async def current_user(p: Principal = Depends(get_principal)) -> Principal:
    return p


def require(*codes: str) -> Callable[..., Principal]:
    """Dependency: user must hold ALL listed permissions. Also enforced again in services where relevant."""

    async def dep(request: Request, p: Principal = Depends(get_principal)) -> Principal:
        if p.user.must_change_password and not getattr(request.state, "allow_pwd_change", False):
            raise PermissionDenied("Password change required before continuing.", code="PASSWORD_CHANGE_REQUIRED")
        missing = [c for c in codes if c not in p.perms]
        if missing:
            log_security_event("AUTHZ_DENIED", user_id=p.user.id, username=p.user.username,
                               ip=client_ip(request), detail=f"{request.method} {request.url.path} needs {missing}")
            raise PermissionDenied("You are not authorised to perform this action.")
        return p

    return dep
