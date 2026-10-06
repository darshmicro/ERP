from datetime import timedelta

from sqlalchemy import select

from app.core import db
from app.core.time import utcnow
from app.models import SecurityEvent, User, UserSession
from tests.conftest import PW, login, make_user, reason


def test_login_logout_and_me(client):
    make_user("alice", ["QA_HEAD"])
    h = login(client, "alice")
    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200 and me.json()["user"]["username"] == "alice"
    assert "workflow.definition.approve" in me.json()["permissions"]
    assert client.post("/api/v1/auth/logout", headers=h).status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 401


def test_unknown_user_and_bad_password_give_same_generic_error(client):
    make_user("bob", ["AUDITOR"])
    a = client.post("/api/v1/auth/login", json={"username": "nobody", "password": "x" * 14})
    b = client.post("/api/v1/auth/login", json={"username": "bob", "password": "wrong-password-1A!"})
    assert a.status_code == b.status_code == 401
    assert a.json()["message"] == b.json()["message"]


def test_lockout_after_threshold_and_events_logged(client):
    make_user("carol", ["AUDITOR"])
    for _ in range(5):
        client.post("/api/v1/auth/login", json={"username": "carol", "password": "bad-password-1A!"})
    r = client.post("/api/v1/auth/login", json={"username": "carol", "password": PW})
    assert r.status_code == 401  # correct password but account locked
    s = db.new_session()
    types = {e.event_type for e in s.execute(select(SecurityEvent)).scalars()}
    s.close()
    assert {"LOGIN_FAILED", "ACCOUNT_LOCKED", "LOGIN_REJECTED"} <= types


def test_failed_login_is_audited(client):
    make_user("dave", ["AUDITOR"])
    client.post("/api/v1/auth/login", json={"username": "dave", "password": "bad-password-1A!"})
    make_user("aud", ["AUDITOR"])
    login(client, "aud")
    r = client.get("/api/v1/audit-trail", params={"action": "LOGIN_FAILED"})
    assert r.status_code == 200 and len(r.json()["items"]) == 1


def test_inactive_user_cannot_login(client):
    make_user("erin", ["AUDITOR"], active=False)
    assert client.post("/api/v1/auth/login", json={"username": "erin", "password": PW}).status_code == 401


def test_idle_timeout_expires_session(client):
    make_user("frank", ["AUDITOR"])
    login(client, "frank")
    s = db.new_session()
    row = s.execute(select(UserSession)).scalars().first()
    row.last_seen_at = utcnow() - timedelta(minutes=16)
    s.commit()
    s.close()
    r = client.get("/api/v1/auth/me")
    assert r.status_code == 401 and r.json()["code"] == "SESSION_EXPIRED"


def test_csrf_required_on_state_change(client, admin):
    r = client.post("/api/v1/users/1/unlock", json={"reason": "x"})  # no CSRF header
    assert r.status_code == 403 and r.json()["code"] == "CSRF"


def test_must_change_password_blocks_other_endpoints(client):
    make_user("gina", ["SYSTEM_ADMIN"], must_change=True)
    login(client, "gina")
    assert client.get("/api/v1/users").status_code == 403
    assert client.get("/api/v1/auth/me").status_code == 200


def test_password_policy_and_history(client):
    make_user("hank", ["AUDITOR"])
    h = login(client, "hank")
    weak = client.post("/api/v1/auth/change-password", headers=h,
                       json={"current_password": PW, "new_password": "short"})
    assert weak.status_code == 422 and weak.json()["code"] == "PASSWORD_POLICY"
    reuse = client.post("/api/v1/auth/change-password", headers=h,
                        json={"current_password": PW, "new_password": PW})
    assert reuse.status_code == 422 and reuse.json()["code"] == "PASSWORD_REUSE"
    ok = client.post("/api/v1/auth/change-password", headers=h,
                     json={"current_password": PW, "new_password": "An0ther!Strong#Pass"})
    assert ok.status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 401  # sessions revoked


def test_login_rate_limit(client):
    from app.core.config import get_settings
    n = get_settings().login_rate_limit_per_minute
    codes = [client.post("/api/v1/auth/login", json={"username": "x", "password": "y"}).status_code
             for _ in range(n + 2)]
    assert 429 in codes


def test_security_headers_and_correlation_id(client):
    r = client.get("/api/v1/health/live")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY" and r.headers["x-correlation-id"]


def test_unhandled_error_hides_internals(app, client):
    @app.get("/boom")
    def boom():
        raise RuntimeError("secret db password leaked")

    r = client.get("/boom")
    assert r.status_code == 500
    assert "secret" not in r.text and r.json()["reference"].startswith("ERR-")


def test_concurrent_logins_of_the_same_account_do_not_conflict(app):
    """Found by the SQL Server load test: simultaneous logins of one account returned 409 CONCURRENT_MODIFICATION (optimistic row_version on users).
    Only meaningful on a server database (SQLite serialises writers), so it is skipped there."""
    import os
    import threading

    import pytest
    from fastapi.testclient import TestClient

    if not os.environ.get("MERP_TEST_DATABASE_URL"):
        pytest.skip("needs a multi-writer database (set MERP_TEST_DATABASE_URL)")
    make_user("multi_dev", ["QA_HEAD"])
    codes = []

    def go():
        c = TestClient(app, raise_server_exceptions=False)
        codes.append(c.post("/api/v1/auth/login", json={"username": "multi_dev", "password": PW}).status_code)

    ts = [threading.Thread(target=go) for _ in range(10)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert codes == [200] * 10
