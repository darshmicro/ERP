"""Access-control test protocol, GENERATED from the live route table and the seeded role catalogue (Validation Strategy §2 'Access-control test protocol').

For every API route that declares required permissions and every seeded role:
  * a role that LACKS a required permission must receive 403 (authorisation is evaluated before the handler runs);
  * a role that HOLDS all of them must NOT receive 403 / 401 (it may get 404/422/409 because the dummy request carries no real record).
Every route must also refuse unauthenticated callers with 401."""
import re

import pytest
from fastapi.testclient import TestClient

from app.models import Role
from app.services.seed import ROLES
from tests.conftest import PW, login, make_user

PUBLIC = {"/api/v1/auth/login", "/api/v1/health/live", "/api/v1/health/ready", "/api/v1/company/branding", "/api/v1/company/logo"}   # the complete, reviewed list of unauthenticated endpoints
SKIP_PREFIX = ("/api/docs", "/api/openapi")


def _flatten(routes, prefix=""):
    """FastAPI >= 0.14x keeps included routers lazy (_IncludedRouter); walk them with their prefixes."""
    for r in routes:
        if hasattr(r, "original_router"):
            yield from _flatten(r.original_router.routes, prefix + (r.include_context.prefix or ""))
        elif hasattr(r, "dependant"):
            yield prefix + r.path, r
        elif hasattr(r, "routes"):
            yield from _flatten(r.routes, prefix + getattr(r, "path", ""))


def _routes(app):
    out = []
    for path, r in _flatten(app.routes):
        if not path.startswith("/api/v1"):
            continue
        req: tuple = ()
        for d in r.dependant.dependencies:
            req += tuple(getattr(d.call, "required_permissions", ()))
        for m in r.methods - {"HEAD", "OPTIONS"}:
            out.append((m, path, req))
    return out


def _url(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "1", path)


@pytest.fixture()
def matrix(app):
    users = {}
    for code in ROLES:
        if code == "SYSTEM_ADMIN":
            continue                      # admin cannot hold GMP roles; included below as its own role set
        users[code] = make_user(f"m_{code.lower()}", [code])
    users["SYSTEM_ADMIN"] = make_user("m_sysadmin", ["SYSTEM_ADMIN"])
    clients = {}
    for code in users:
        c = TestClient(app, raise_server_exceptions=False)
        h = login(c, f"m_{code.lower()}" if code != "SYSTEM_ADMIN" else "m_sysadmin")
        clients[code] = (c, h)
    return clients


def _perms_of(app_perm_map: dict, role: str) -> set:
    return app_perm_map[role]


@pytest.fixture()
def role_perms(app):
    from app.core import db
    from app.security.permissions import effective_permissions
    from app.models import User
    from sqlalchemy import select
    s = db.new_session()
    out = {}
    for code in ROLES:
        uname = f"m_{code.lower()}" if code != "SYSTEM_ADMIN" else "m_sysadmin"
        uid = s.execute(select(User.id).where(User.username == uname)).scalar()
        if uid:
            out[code] = effective_permissions(s, uid)
    s.close()
    return out


def test_every_route_requires_authentication(app):
    c = TestClient(app, raise_server_exceptions=False)
    bad = []
    for m, path, _req in _routes(app):
        if path in PUBLIC or path.startswith(SKIP_PREFIX):
            continue
        r = c.request(m, _url(path), json={} if m in ("POST", "PUT", "PATCH") else None)
        if r.status_code != 401:
            bad.append((m, path, r.status_code))
    assert not bad, f"{len(bad)} routes answer unauthenticated callers: {bad[:15]}"


def test_generated_role_by_route_permission_matrix(app, matrix, role_perms):
    routes = [(m, p, req) for m, p, req in _routes(app) if req]
    assert len(routes) > 300                                   # the protocol covers the whole API surface
    problems, checked = [], 0
    for role, (client, h) in matrix.items():
        perms = role_perms[role]
        for m, path, req in routes:
            if m in ("POST", "PUT", "PATCH", "DELETE"):
                pass
            allowed = all(r in perms for r in req)
            kwargs = {"headers": {"X-CSRF-Token": h["X-CSRF-Token"]}}
            if m in ("POST", "PUT", "PATCH"):
                kwargs["json"] = {}
            resp = client.request(m, _url(path), **kwargs)
            checked += 1
            if not allowed and resp.status_code != 403:
                problems.append(f"{role} {m} {path} lacks {[r for r in req if r not in perms]} but got {resp.status_code}")
            if allowed and resp.status_code in (401, 403):
                problems.append(f"{role} {m} {path} holds {req} but got {resp.status_code}")
    assert checked > 3000
    assert not problems, f"{len(problems)} violations of {checked} checks:\n" + "\n".join(problems[:25])


def test_admin_roles_hold_no_gmp_approval_authority(app, matrix, role_perms):
    """SoD-09 as a catalogue-level property: no administrative role may carry approval/release/sign actions on GMP records."""
    from app.security.permissions import GMP_AUTHORITY_ACTIONS
    gmp_modules = ("md.spec", "md.stp", "po.", "pr.", "grn", "qc.", "qa.", "oos", "dispatch", "mfg", "quality", "vq", "vm.", "conditional_release", "warehouse.destruction")
    bad = [p for p in role_perms["SYSTEM_ADMIN"] if p.split(".")[-1] in GMP_AUTHORITY_ACTIONS and p.startswith(gmp_modules)]
    assert bad == []
