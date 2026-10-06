from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import Principal, get_db, require
from app.api.helpers import page_args, use_reason
from app.core.errors import NotFound
from app.models.iam import Permission, Role, RolePermission, TrainingRecord, UserRole
from app.schemas.common import Page
from app.schemas.iam import (ActiveIn, RoleAssignIn, RoleCreateIn, RoleOut, RolePermissionsIn, TrainingIn,
                             UserCreateIn, UserOut, UserUpdateIn)
from app.schemas.common import Reasoned
from app.security.permissions import active_role_codes
from app.services import user_service as svc

router = APIRouter(tags=["iam"])


@router.get("/users", response_model=Page[UserOut])
def list_users(q: str | None = None, active: bool | None = None, limit: int = Query(50), offset: int = Query(0),
               p: Principal = Depends(require("iam.user.read")), s: Session = Depends(get_db)):
    limit, offset = page_args(limit, offset)
    rows, total = svc.search_users(s, q, limit, offset, active)
    return Page(items=[UserOut.model_validate(r) for r in rows], total=total, limit=limit, offset=offset)


@router.post("/users", status_code=201)
def create_user(body: UserCreateIn, p: Principal = Depends(require("iam.user.create")), s: Session = Depends(get_db)):
    use_reason(body.reason)
    u, temp = svc.create_user(s, username=body.username, full_name=body.full_name, email=body.email,
                              designation=body.designation, department_id=body.department_id,
                              plant_id=body.plant_id, auth_source=body.auth_source,
                              access_expiry=body.access_expiry, password=None)
    if body.initial_role_codes:
        if "iam.user.assign_role" not in p.perms:
            from app.core.errors import PermissionDenied
            raise PermissionDenied("Assigning roles requires iam.user.assign_role")
        for code in body.initial_role_codes:
            role = s.execute(select(Role).where(Role.role_code == code)).scalar_one_or_none()
            if role is None:
                raise NotFound(f"Role {code} not found")
            svc.assign_role(s, u, role, p.user.id)
    s.commit()
    return {"user": UserOut.model_validate(u), "temporary_password": temp,
            "note": "Shown once. User must change it at first login."}


@router.get("/users/{user_id}")
def get_user(user_id: int, p: Principal = Depends(require("iam.user.read")), s: Session = Depends(get_db)):
    u = svc.get_user(s, user_id)
    roles = s.execute(select(UserRole, Role).join(Role, Role.id == UserRole.role_id)
                      .where(UserRole.user_id == u.id, UserRole.revoked_at.is_(None))).all()
    return {"user": UserOut.model_validate(u),
            "roles": [{"role_code": r.role_code, "name": r.name, "valid_from": ur.valid_from,
                       "valid_to": ur.valid_to, "is_disabled": ur.is_disabled} for ur, r in roles],
            "effective_roles": active_role_codes(s, u.id)}


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(user_id: int, body: UserUpdateIn, p: Principal = Depends(require("iam.user.update")),
                s: Session = Depends(get_db)):
    use_reason(body.reason)
    u = svc.update_user(s, svc.get_user(s, user_id), body.model_dump(exclude={"reason"}, exclude_unset=True))
    s.commit()
    return u


@router.post("/users/{user_id}/active")
def set_active(user_id: int, body: ActiveIn, p: Principal = Depends(require("iam.user.deactivate")),
               s: Session = Depends(get_db)):
    use_reason(body.reason)
    svc.set_active(s, svc.get_user(s, user_id), body.active, p.user.id)
    s.commit()
    return {"ok": True}


@router.post("/users/{user_id}/unlock")
def unlock(user_id: int, body: Reasoned, p: Principal = Depends(require("iam.user.update")), s: Session = Depends(get_db)):
    use_reason(body.reason)
    svc.unlock(s, svc.get_user(s, user_id))
    s.commit()
    return {"ok": True}


@router.post("/users/{user_id}/reset-password")
def reset_password(user_id: int, body: Reasoned, p: Principal = Depends(require("iam.user.reset_password")),
                   s: Session = Depends(get_db)):
    use_reason(body.reason)
    temp = svc.admin_reset_password(s, svc.get_user(s, user_id), p.user.id)
    s.commit()
    return {"temporary_password": temp, "note": "Shown once. User must change it at next login."}


@router.post("/users/{user_id}/roles", status_code=201)
def assign_role(user_id: int, body: RoleAssignIn, p: Principal = Depends(require("iam.user.assign_role")),
                s: Session = Depends(get_db)):
    use_reason(body.reason)
    role = s.execute(select(Role).where(Role.role_code == body.role_code)).scalar_one_or_none()
    if role is None:
        raise NotFound("Role not found")
    svc.assign_role(s, svc.get_user(s, user_id), role, p.user.id, valid_to=body.valid_to)
    s.commit()
    return {"ok": True}


@router.delete("/users/{user_id}/roles/{role_code}")
def remove_role(user_id: int, role_code: str, body: Reasoned, p: Principal = Depends(require("iam.user.assign_role")),
                s: Session = Depends(get_db)):
    use_reason(body.reason)
    role = s.execute(select(Role).where(Role.role_code == role_code)).scalar_one_or_none()
    if role is None:
        raise NotFound("Role not found")
    svc.remove_role(s, svc.get_user(s, user_id), role.id, p.user.id)
    s.commit()
    return {"ok": True}


@router.get("/roles", response_model=list[RoleOut])
def list_roles(p: Principal = Depends(require("iam.role.read")), s: Session = Depends(get_db)):
    return s.execute(select(Role).order_by(Role.role_code)).scalars().all()


@router.get("/roles/{role_code}")
def get_role(role_code: str, p: Principal = Depends(require("iam.role.read")), s: Session = Depends(get_db)):
    r = s.execute(select(Role).where(Role.role_code == role_code)).scalar_one_or_none()
    if r is None:
        raise NotFound("Role not found")
    perms = s.execute(select(Permission.perm_code).join(RolePermission, RolePermission.permission_id == Permission.id)
                      .where(RolePermission.role_id == r.id, RolePermission.revoked_at.is_(None))
                      .order_by(Permission.perm_code)).scalars().all()
    return {"role": RoleOut.model_validate(r), "permissions": perms}


@router.post("/roles", status_code=201, response_model=RoleOut)
def create_role(body: RoleCreateIn, p: Principal = Depends(require("iam.role.create")), s: Session = Depends(get_db)):
    use_reason(body.reason)
    r = svc.create_role(s, body.role_code, body.name, body.description, body.is_admin_role)
    s.commit()
    return r


@router.put("/roles/{role_code}/permissions")
def set_permissions(role_code: str, body: RolePermissionsIn, p: Principal = Depends(require("iam.role.update")),
                    s: Session = Depends(get_db)):
    use_reason(body.reason)
    r = s.execute(select(Role).where(Role.role_code == role_code)).scalar_one_or_none()
    if r is None:
        raise NotFound("Role not found")
    svc.set_role_permissions(s, r, body.permissions)
    s.commit()
    return {"ok": True}


@router.get("/permissions")
def list_permissions(p: Principal = Depends(require("iam.role.read")), s: Session = Depends(get_db)):
    return [{"perm_code": x.perm_code, "module": x.module, "resource": x.resource, "action": x.action}
            for x in s.execute(select(Permission).order_by(Permission.perm_code)).scalars()]


@router.post("/training-records", status_code=201)
def add_training(body: TrainingIn, p: Principal = Depends(require("training.record.create")),
                 s: Session = Depends(get_db)):
    use_reason(body.reason)
    t = TrainingRecord(user_id=body.user_id, training_code=body.training_code,
                       document_version=body.document_version, trained_on=body.trained_on,
                       valid_until=body.valid_until)
    s.add(t)
    s.commit()
    return {"id": t.id}
