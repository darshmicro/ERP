from sqlalchemy import select

from app.core import db
from app.models import SecurityEvent
from tests.conftest import PW, login, make_user, reason


def test_unauthorised_user_gets_403_and_event_logged(client):
    make_user("wh", ["WAREHOUSE_USER"])
    login(client, "wh")
    assert client.get("/api/v1/users").status_code == 403
    assert client.get("/api/v1/audit-trail").status_code == 403
    s = db.new_session()
    assert s.execute(select(SecurityEvent).where(SecurityEvent.event_type == "AUTHZ_DENIED")).first()
    s.close()


def test_unauthenticated_is_401(client):
    for path in ("/api/v1/users", "/api/v1/audit-trail", "/api/v1/company", "/api/v1/roles"):
        assert client.get(path).status_code == 401


def test_admin_creates_user_and_assigns_role_with_reason(client, admin):
    r = client.post("/api/v1/users", headers=admin, json={
        "username": "newuser", "full_name": "New User", "reason": "new joiner"})
    assert r.status_code == 201, r.text
    temp = r.json()["temporary_password"]
    uid = r.json()["user"]["id"]
    # reason mandatory for role assignment
    bad = client.post(f"/api/v1/users/{uid}/roles", headers=admin, json={"role_code": "QC_ANALYST"})
    assert bad.status_code == 422 and bad.json()["code"] == "REASON_REQUIRED"
    ok = client.post(f"/api/v1/users/{uid}/roles", headers=admin,
                     json={"role_code": "QC_ANALYST", "reason": "QC onboarding"})
    assert ok.status_code == 201, ok.text
    # temp password works but forces change
    client.post("/api/v1/auth/logout", headers=admin)
    res = client.post("/api/v1/auth/login", json={"username": "newuser", "password": temp})
    assert res.status_code == 200 and res.json()["must_change_password"] is True


def test_duplicate_username_rejected_case_insensitive(client, admin):
    client.post("/api/v1/users", headers=admin, json={"username": "dupe", "full_name": "A", "reason": "r"})
    r = client.post("/api/v1/users", headers=admin, json={"username": "DUPE", "full_name": "B", "reason": "r"})
    assert r.status_code == 409


def test_cannot_change_own_roles_sod10(client, admin):
    me = client.get("/api/v1/auth/me").json()["user"]["id"]
    r = client.post(f"/api/v1/users/{me}/roles", headers=admin,
                    json={"role_code": "AUDITOR", "reason": "self grant"})
    assert r.status_code == 409 and r.json()["rule_id"] == "SOD-10"


def test_admin_cannot_hold_gmp_approval_role_sod09(client, admin):
    uid = make_user("target", ["SYSTEM_ADMIN"])
    r = client.post(f"/api/v1/users/{uid}/roles", headers=admin,
                    json={"role_code": "QA_HEAD", "reason": "try conflict"})
    assert r.status_code == 409 and r.json()["rule_id"] == "SOD-09"


def test_admin_role_cannot_receive_approve_permission(client, admin):
    r = client.put("/api/v1/roles/SYSTEM_ADMIN/permissions", headers=admin, json={
        "permissions": ["iam.user.read", "workflow.definition.approve"], "reason": "bad idea"})
    assert r.status_code == 409 and r.json()["rule_id"] == "SOD-09"


def test_role_permission_change_takes_effect_and_is_audited(client, admin):
    make_user("wh2", ["WAREHOUSE_USER"])
    r = client.put("/api/v1/roles/WAREHOUSE_USER/permissions", headers=admin, json={
        "permissions": ["dashboard.view.read", "iam.user.read"], "reason": "test grant"})
    assert r.status_code == 200, r.text
    client.post("/api/v1/auth/logout", headers=admin)
    login(client, "wh2")
    assert client.get("/api/v1/users").status_code == 200
    client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": client.get("/api/v1/auth/me").json()["csrf_token"]})
    make_user("aud2", ["AUDITOR"])
    login(client, "aud2")
    rows = client.get("/api/v1/audit-trail", params={"entity": "role_permission"}).json()["items"]
    mine = [x for x in rows if x["user_name"] == "admin1"]
    assert mine and all(x["reason"] == "test grant" for x in mine)


def test_user_deactivation_revokes_sessions(client, admin):
    uid = make_user("victim", ["AUDITOR"])
    from fastapi.testclient import TestClient
    c2 = TestClient(client.app)
    login(c2, "victim")
    r = client.post(f"/api/v1/users/{uid}/active", headers=admin, json={"active": False, "reason": "left company"})
    assert r.status_code == 200
    assert c2.get("/api/v1/auth/me").status_code == 401


def test_cannot_deactivate_self(client, admin):
    me = client.get("/api/v1/auth/me").json()["user"]["id"]
    r = client.post(f"/api/v1/users/{me}/active", headers=admin, json={"active": False, "reason": "oops"})
    assert r.status_code == 409


def test_expired_access_blocks_login(client, admin):
    uid = make_user("temp1", ["AUDITOR"])
    client.patch(f"/api/v1/users/{uid}", headers=admin, json={"access_expiry": "2020-01-01", "reason": "contract end"})
    r = client.post("/api/v1/auth/login", json={"username": "temp1", "password": PW})
    assert r.status_code == 401


def test_status_not_writable_via_api_payload(client, admin):
    uid = make_user("x1", ["AUDITOR"])
    # pydantic ignores unknown fields, so is_active cannot be set through the update endpoint
    r = client.patch(f"/api/v1/users/{uid}", headers=admin, json={"is_active": False, "reason": "try"})
    assert r.status_code == 200 and r.json()["is_active"] is True
