"""LDAP provider tested against a stub directory (NOT site-verified against a real AD server)."""
from app.core.config import get_settings
from app.security import providers
from tests.conftest import login, make_user


class FakeConn:
    GOOD = {"jdoe@corp.local": "Dir-Passw0rd!"}

    def __init__(self, server, user=None, password=None, **kw):
        self.user, self.password = user, password

    def bind(self):
        return self.GOOD.get(self.user) == self.password

    def unbind(self):
        pass


def _enable(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "ldap_enabled", True)
    monkeypatch.setattr(s, "ldap_server_uri", "ldaps://dc.corp.local")
    monkeypatch.setattr(s, "ldap_bind_format", "{username}@corp.local")
    import ldap3
    monkeypatch.setattr(ldap3, "Connection", FakeConn)
    monkeypatch.setattr(ldap3, "Server", lambda *a, **k: object())


def test_ldap_user_logs_in_with_directory_password(client, monkeypatch):
    _enable(monkeypatch)
    make_user("jdoe", ["AUDITOR"], auth_source="LDAP")
    assert client.post("/api/v1/auth/login", json={"username": "jdoe", "password": "Dir-Passw0rd!"}).status_code == 200


def test_ldap_wrong_password_and_empty_password_rejected(client, monkeypatch):
    _enable(monkeypatch)
    make_user("jdoe", ["AUDITOR"], auth_source="LDAP")
    assert client.post("/api/v1/auth/login", json={"username": "jdoe", "password": "nope"}).status_code == 401
    u = type("U", (), {"username": "jdoe"})()
    assert providers.LdapProvider().verify(u, "") is False  # anonymous-bind trap


def test_ldap_disabled_fails_closed(client):
    make_user("jdoe", ["AUDITOR"], auth_source="LDAP")
    assert client.post("/api/v1/auth/login", json={"username": "jdoe", "password": "Dir-Passw0rd!"}).status_code == 401
