"""Login, logout, sessions, lockout, password change."""
import hashlib
import secrets
from datetime import timedelta
from typing import NamedTuple

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit import service as audit
from app.audit.context import AuditContext, audit_context, get_context, set_reason
from app.core import db
from app.core.config import get_settings
from app.core.errors import AuthenticationError, ValidationFailed
from app.core.time import utcnow
from app.models.iam import PasswordHistory, User, UserSession
from app.security import passwords
from app.security.permissions import active_role_codes
from app.security.providers import provider_for
from app.services.security_events import log_security_event

GENERIC_FAIL = "Invalid username or password, or the account is not available."


class LoginResult(NamedTuple):
    user_id: int
    token: str
    csrf_token: str
    must_change_password: bool


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _is_locked(user: User) -> bool:
    return bool(user.locked_until and user.locked_until > utcnow())


def _access_expired(user: User) -> bool:
    from datetime import date
    return bool(user.access_expiry and user.access_expiry < date.today())


def register_failed_attempt(user_id: int, ip: str | None, reason: str) -> bool:
    """Increment failure counter in an independent transaction. Returns True if account is now locked."""
    s_cfg = get_settings()
    s = db.new_session()
    locked = False
    try:
        u = s.get(User, user_id)
        if u is None:
            return False
        u.failed_attempts = (u.failed_attempts or 0) + 1
        if u.failed_attempts >= s_cfg.lockout_threshold:
            u.locked_until = utcnow() + timedelta(minutes=s_cfg.lockout_minutes)
            u.failed_attempts = 0
            locked = True
        s.commit()
    finally:
        s.close()
    log_security_event("LOGIN_FAILED", user_id=user_id, username=u.username, ip=ip, detail=reason)
    if locked:
        log_security_event("ACCOUNT_LOCKED", user_id=user_id, username=u.username, ip=ip,
                           detail=f"locked for {s_cfg.lockout_minutes} min after repeated failures")
    return locked


def login(username: str, password: str, ip: str | None, user_agent: str | None,
          correlation_id: str | None = None) -> LoginResult:
    cfg = get_settings()
    s = db.new_session()
    try:
        user = s.execute(select(User).where(func.lower(User.username) == username.strip().lower())
                         ).scalar_one_or_none()
        ctx = AuditContext(user_id=user.id if user else None, user_name=user.username if user else username[:80],
                           ip_address=ip, device_info=(user_agent or "")[:300], correlation_id=correlation_id)
        if user is None:
            passwords.dummy_verify(password)
            log_security_event("LOGIN_FAILED", username=username[:80], ip=ip, detail="unknown user")
            audit.log_event_independent(module="auth", entity="session", record_id=None, action="LOGIN_FAILED",
                                        reason="unknown user")
            raise AuthenticationError(GENERIC_FAIL)
        if not user.is_active or _access_expired(user) or _is_locked(user):
            why = ("inactive" if not user.is_active else "access expired" if _access_expired(user)
                   else "locked")
            log_security_event("LOGIN_REJECTED", user_id=user.id, username=user.username, ip=ip, detail=why)
            with audit_context(ctx):
                audit.log_event_independent(module="auth", entity="session", record_id=None,
                                            action="LOGIN_FAILED", reason=why)
            raise AuthenticationError(GENERIC_FAIL)
        if not provider_for(user).verify(user, password):
            register_failed_attempt(user.id, ip, "bad credentials")
            with audit_context(ctx):
                audit.log_event_independent(module="auth", entity="session", record_id=None,
                                            action="LOGIN_FAILED", reason="bad credentials")
            raise AuthenticationError(GENERIC_FAIL)

        user.failed_attempts = 0
        user.locked_until = None
        user.last_login_at = utcnow()
        token = secrets.token_urlsafe(32)
        csrf = secrets.token_urlsafe(24)
        now = utcnow()
        sess = UserSession(user_id=user.id, token_hash=hash_token(token), csrf_token=csrf,
                           absolute_expires_at=now + timedelta(hours=cfg.session_absolute_hours),
                           ip_address=ip, user_agent=(user_agent or "")[:300])
        s.add(sess)
        s.flush()
        if cfg.max_concurrent_sessions > 0:
            active = s.execute(select(UserSession).where(
                UserSession.user_id == user.id, UserSession.revoked_at.is_(None),
                UserSession.id != sess.id).order_by(UserSession.created_at.desc())).scalars().all()
            for old in active[cfg.max_concurrent_sessions - 1:]:
                old.revoked_at = now
                old.revoke_reason = "concurrent session limit"
        roles = ", ".join(active_role_codes(s, user.id))
        must_change = user.must_change_password or _password_expired(user)
        with audit_context(AuditContext(user_id=user.id, user_name=user.username, role_name=roles,
                                        session_id=str(sess.id), ip_address=ip,
                                        device_info=(user_agent or "")[:300], correlation_id=correlation_id)):
            audit.log_event(s, module="auth", entity="session", record_id=sess.id, action="LOGIN")
            s.commit()
        return LoginResult(user.id, token, csrf, must_change)
    finally:
        s.close()


def _password_expired(user: User) -> bool:
    cfg = get_settings()
    if user.auth_source != "LOCAL" or cfg.password_max_age_days <= 0 or not user.password_changed_at:
        return False
    return user.password_changed_at + timedelta(days=cfg.password_max_age_days) < utcnow()


def logout(session: Session, sess: UserSession) -> None:
    sess.revoked_at = utcnow()
    sess.revoke_reason = "logout"
    audit.log_event(session, module="auth", entity="session", record_id=sess.id, action="LOGOUT")


def set_password(session: Session, user: User, new_password: str, *, must_change: bool,
                 enforce_history: bool = True) -> None:
    cfg = get_settings()
    errs = passwords.policy_errors(new_password, user.username, user.full_name)
    if errs:
        raise ValidationFailed("Password does not meet the policy: " + ", ".join(errs),
                               code="PASSWORD_POLICY", details=errs)
    if enforce_history:
        recent = session.execute(select(PasswordHistory.password_hash).where(
            PasswordHistory.user_id == user.id).order_by(PasswordHistory.id.desc())
            .limit(cfg.password_history)).scalars().all()
        if any(passwords.verify_password(h, new_password) for h in recent):
            raise ValidationFailed(f"Password was used recently (last {cfg.password_history} are blocked)",
                                   code="PASSWORD_REUSE")
    h = passwords.hash_password(new_password)
    user.password_hash = h
    user.password_changed_at = utcnow()
    user.must_change_password = must_change
    session.add(PasswordHistory(user_id=user.id, password_hash=h))


def change_password(session: Session, user: User, current: str, new: str) -> None:
    if user.auth_source != "LOCAL":
        raise ValidationFailed("Directory (AD/LDAP) passwords are changed in the directory.")
    if not passwords.verify_password(user.password_hash, current):
        register_failed_attempt(user.id, None, "bad current password on change")
        raise AuthenticationError("Current password is incorrect.")
    if not get_context().reason:
        set_reason("Self-service password change")
    set_password(session, user, new, must_change=False)
    audit.log_event(session, module="iam", entity="users", record_id=user.id, action="PASSWORD_CHANGE")
    # revoke all other sessions
    for s_ in session.execute(select(UserSession).where(
            UserSession.user_id == user.id, UserSession.revoked_at.is_(None))).scalars():
        s_.revoked_at = utcnow()
        s_.revoke_reason = "password changed"
