"""User, role and permission administration (all changes audited; reasons mandatory)."""
import secrets
import string
from datetime import date

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.audit import service as audit
from app.audit.context import get_context
from app.core.errors import Conflict, NotFound, SegregationOfDutiesError, ValidationFailed
from app.core.time import utcnow
from app.models.iam import Permission, Role, RolePermission, User, UserRole, UserSession
from app.security.permissions import GMP_AUTHORITY_ACTIONS
from app.services import auth_service
from app.services.security_events import log_security_event


def _require_reason() -> str:
    r = get_context().reason
    if not r:
        from app.core.errors import ReasonRequired
        raise ReasonRequired("A reason is required for this change")
    return r


def generate_temp_password() -> str:
    alphabet = string.ascii_letters + string.digits
    core = "".join(secrets.choice(alphabet) for _ in range(14))
    return f"Aa1!{core}"  # satisfies complexity; user must change at first login


def get_user(session: Session, user_id: int) -> User:
    u = session.get(User, user_id)
    if u is None:
        raise NotFound("User not found")
    return u


def create_user(session: Session, *, username: str, full_name: str, email: str | None,
                designation: str | None, department_id: int | None, plant_id: int | None,
                auth_source: str, access_expiry: date | None, password: str | None) -> tuple[User, str | None]:
    if session.execute(select(User.id).where(func.lower(User.username) == username.lower())).first():
        raise Conflict("Username already exists (user IDs are unique and never reused)")
    u = User(username=username.strip(), full_name=full_name, email=email, designation=designation,
             department_id=department_id, plant_id=plant_id, auth_source=auth_source,
             access_expiry=access_expiry, is_active=True, must_change_password=True)
    session.add(u)
    session.flush()
    temp = None
    if auth_source == "LOCAL":
        temp = password or generate_temp_password()
        auth_service.set_password(session, u, temp, must_change=True, enforce_history=False)
    return u, temp


def update_user(session: Session, user: User, changes: dict) -> User:
    _require_reason()
    for k, v in changes.items():
        if k in {"full_name", "email", "designation", "department_id", "plant_id", "access_expiry"}:
            setattr(user, k, v)
    return user


def set_active(session: Session, user: User, active: bool, acting_user_id: int) -> None:
    _require_reason()
    if user.id == acting_user_id and not active:
        raise SegregationOfDutiesError("You cannot deactivate your own account.", rule_id="SOD-10")
    user.is_active = active
    if not active:
        revoke_all_sessions(session, user.id, "account deactivated")


def revoke_all_sessions(session: Session, user_id: int, reason: str) -> None:
    for s in session.execute(select(UserSession).where(UserSession.user_id == user_id,
                                                       UserSession.revoked_at.is_(None))).scalars():
        s.revoked_at = utcnow()
        s.revoke_reason = reason


def unlock(session: Session, user: User) -> None:
    _require_reason()
    user.locked_until = None
    user.failed_attempts = 0
    audit.log_event(session, module="iam", entity="users", record_id=user.id, action="ACCOUNT_UNLOCK")


def admin_reset_password(session: Session, user: User, acting_user_id: int) -> str:
    _require_reason()
    if user.auth_source != "LOCAL":
        raise ValidationFailed("Directory (AD/LDAP) users reset their password in the directory.")
    if user.id == acting_user_id:
        raise SegregationOfDutiesError("Use 'change password' for your own account.", rule_id="SOD-10")
    temp = generate_temp_password()
    auth_service.set_password(session, user, temp, must_change=True, enforce_history=False)
    revoke_all_sessions(session, user.id, "password reset")
    audit.log_event(session, module="iam", entity="users", record_id=user.id, action="PASSWORD_RESET")
    return temp


def _role_authority(session: Session, role_id: int) -> bool:
    codes = session.execute(select(Permission.action).join(
        RolePermission, RolePermission.permission_id == Permission.id).where(
        RolePermission.role_id == role_id, RolePermission.revoked_at.is_(None))).scalars().all()
    return any(a in GMP_AUTHORITY_ACTIONS for a in codes)


def _user_roles(session: Session, user_id: int) -> list[Role]:
    return list(session.execute(select(Role).join(UserRole, UserRole.role_id == Role.id).where(
        UserRole.user_id == user_id, UserRole.revoked_at.is_(None))).scalars())


def assign_role(session: Session, user: User, role: Role, acting_user_id: int, *,
                valid_to: date | None = None) -> UserRole:
    reason = _require_reason()
    if user.id == acting_user_id:
        raise SegregationOfDutiesError("You cannot change your own roles.", rule_id="SOD-10")
    if not role.is_active:
        raise ValidationFailed("Role is inactive")
    # SOD-09: administrative roles must not carry GMP approval authority (in either direction)
    held = _user_roles(session, user.id)
    new_admin, new_auth = role.is_admin_role, _role_authority(session, role.id)
    for r in held:
        if (new_admin and _role_authority(session, r.id)) or (new_auth and r.is_admin_role):
            raise SegregationOfDutiesError(
                "SOD-09: a user may not hold both an administrator role and a GMP approval role.",
                rule_id="SOD-09")
    if new_admin and new_auth:
        raise SegregationOfDutiesError("SOD-09: administrator role carries GMP approval authority.",
                                       rule_id="SOD-09")
    existing = session.execute(select(UserRole).where(UserRole.user_id == user.id, UserRole.role_id == role.id,
                                                      UserRole.revoked_at.is_(None))).scalar_one_or_none()
    if existing:
        raise Conflict("User already holds this role")
    ur = UserRole(user_id=user.id, role_id=role.id, granted_by_id=acting_user_id, valid_from=date.today(),
                  valid_to=valid_to, reason=reason)
    session.add(ur)
    return ur


def remove_role(session: Session, user: User, role_id: int, acting_user_id: int) -> None:
    _require_reason()
    if user.id == acting_user_id:
        raise SegregationOfDutiesError("You cannot change your own roles.", rule_id="SOD-10")
    ur = session.execute(select(UserRole).where(UserRole.user_id == user.id, UserRole.role_id == role_id,
                                                UserRole.revoked_at.is_(None))).scalar_one_or_none()
    if ur is None:
        raise NotFound("User does not hold this role")
    ur.revoked_at = utcnow()


def set_role_disabled(session: Session, user: User, role_id: int, disabled: bool, acting_user_id: int) -> None:
    _require_reason()
    if user.id == acting_user_id:
        raise SegregationOfDutiesError("You cannot change your own roles.", rule_id="SOD-10")
    ur = session.execute(select(UserRole).where(UserRole.user_id == user.id, UserRole.role_id == role_id,
                                                UserRole.revoked_at.is_(None))).scalar_one_or_none()
    if ur is None:
        raise NotFound("User does not hold this role")
    ur.is_disabled = disabled


def create_role(session: Session, role_code: str, name: str, description: str | None,
                is_admin_role: bool) -> Role:
    if session.execute(select(Role.id).where(Role.role_code == role_code)).first():
        raise Conflict("Role code already exists")
    r = Role(role_code=role_code, name=name, description=description, is_admin_role=is_admin_role)
    session.add(r)
    return r


def set_role_permissions(session: Session, role: Role, perm_codes: list[str]) -> None:
    _require_reason()
    wanted = set(perm_codes)
    perms = {p.perm_code: p for p in session.execute(select(Permission)).scalars()}
    unknown = wanted - set(perms)
    if unknown:
        raise ValidationFailed("Unknown permissions: " + ", ".join(sorted(unknown)))
    if role.is_admin_role and any(perms[c].action in GMP_AUTHORITY_ACTIONS for c in wanted):
        raise SegregationOfDutiesError("SOD-09: administrator roles cannot carry GMP approval permissions.",
                                       rule_id="SOD-09")
    existing = {rp.permission_id: rp for rp in session.execute(
        select(RolePermission).where(RolePermission.role_id == role.id)).scalars()}
    for code in wanted:
        p = perms[code]
        rp = existing.get(p.id)
        if rp is None:
            session.add(RolePermission(role_id=role.id, permission_id=p.id))
        elif rp.revoked_at is not None:
            rp.revoked_at = None
    for pid, rp in existing.items():
        code = next(c for c, p in perms.items() if p.id == pid)
        if code not in wanted and rp.revoked_at is None:
            rp.revoked_at = utcnow()


def search_users(session: Session, q: str | None, limit: int, offset: int, active: bool | None):
    stmt = select(User)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(or_(func.lower(User.username).like(like), func.lower(User.full_name).like(like)))
    if active is not None:
        stmt = stmt.where(User.is_active.is_(active))
    total = session.execute(select(func.count()).select_from(stmt.subquery())).scalar()
    rows = session.execute(stmt.order_by(User.username).limit(limit).offset(offset)).scalars().all()
    return rows, total
