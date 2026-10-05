from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.api.deps import COOKIE, Principal, client_ip, current_user, get_db
from app.core.config import get_settings
from app.core.errors import AppError
from app.schemas.iam import ChangePasswordIn, LoginIn, MeOut, UserOut
from app.services import auth_service
from app.services.rate_limit import login_limiter
from app.services.security_events import log_security_event

router = APIRouter(prefix="/auth", tags=["auth"])


def _me(p: Principal, csrf: str | None = None) -> MeOut:
    return MeOut(user=UserOut.model_validate(p.user), roles=p.roles, permissions=sorted(p.perms), csrf_token=csrf)


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, s: Session = Depends(get_db)):
    cfg = get_settings()
    ip = client_ip(request)
    if not login_limiter.allow(ip or "unknown"):
        log_security_event("RATE_LIMITED", ip=ip, detail="login")
        raise AppError("Too many attempts. Try again later.", code="RATE_LIMITED", status_code=429)
    res = auth_service.login(body.username, body.password, ip, request.headers.get("user-agent"),
                             getattr(request.state, "correlation_id", None))
    response.set_cookie(COOKIE, res.token, httponly=True, secure=cfg.cookie_secure, samesite="strict",
                        max_age=cfg.session_absolute_hours * 3600, path="/")
    from app.models.iam import User
    from app.security.permissions import active_role_codes, effective_permissions
    u = s.get(User, res.user_id)
    return {"user": UserOut.model_validate(u), "roles": active_role_codes(s, u.id),
            "permissions": sorted(effective_permissions(s, u.id)), "csrf_token": res.csrf_token,
            "must_change_password": res.must_change_password}


@router.post("/logout")
def logout(response: Response, p: Principal = Depends(current_user), s: Session = Depends(get_db)):
    auth_service.logout(s, p.session)
    s.commit()
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@router.get("/me", response_model=MeOut)
def me(p: Principal = Depends(current_user)):
    return _me(p, p.session.csrf_token)


@router.post("/change-password")
def change_password(body: ChangePasswordIn, response: Response, p: Principal = Depends(current_user),
                    s: Session = Depends(get_db)):
    auth_service.change_password(s, p.user, body.current_password, body.new_password)
    s.commit()
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True, "message": "Password changed. Please log in again."}
