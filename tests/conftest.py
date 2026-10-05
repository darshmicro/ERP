import os
import tempfile

os.environ.setdefault("MERP_SECRET_KEY", "test-secret-key-0123456789")
os.environ.setdefault("MERP_AUDIT_HMAC_KEY", "test-audit-hmac-key-0123456789")
os.environ["MERP_COOKIE_SECURE"] = "false"
os.environ.setdefault("MERP_ARGON2_TIME_COST", "1")
os.environ.setdefault("MERP_ARGON2_MEMORY_KIB", "1024")
os.environ.setdefault("MERP_ARGON2_PARALLELISM", "1")
os.environ["MERP_ENVIRONMENT"] = "test"
os.environ["MERP_FRONTEND_DIST"] = tempfile.mkdtemp(prefix="merp-nodist-")  # tests never depend on a built SPA
os.environ["MERP_LOG_DIR"] = tempfile.mkdtemp(prefix="merp-logs-")
os.environ["MERP_FILE_STORAGE_PATH"] = tempfile.mkdtemp(prefix="merp-docs-")

from datetime import date  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.audit import hooks  # noqa: E402
from app.audit.context import AuditContext, audit_context  # noqa: E402
from app.audit.immutability import install_triggers  # noqa: E402
from app.core import db  # noqa: E402
from app.core.db import Base  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models import Role, User, UserRole  # noqa: E402
from app.services import auth_service, seed  # noqa: E402
from app.services.rate_limit import login_limiter  # noqa: E402

PW = "Str0ng!Passw0rd#1"


def _reset_server_database(engine):
    """Tests leave sessions open; on SQL Server their locks would block DROP TABLE. Roll them back first."""
    from sqlalchemy import text
    if engine.dialect.name == "mssql":
        dbname = engine.url.database
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as c:
            c.execute(text(f"ALTER DATABASE [{dbname}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE"))
            c.execute(text(f"ALTER DATABASE [{dbname}] SET MULTI_USER"))
        engine.dispose()
    Base.metadata.drop_all(engine)


@pytest.fixture()
def engine(tmp_path):
    # MERP_TEST_DATABASE_URL lets the same suite run against SQL Server / PostgreSQL (see docs/validation).
    url = os.environ.get("MERP_TEST_DATABASE_URL") or f"sqlite:///{tmp_path/'t.db'}"
    engine = db.configure(url)
    import app.models  # noqa: F401
    if not url.startswith("sqlite"):
        _reset_server_database(engine)
    Base.metadata.create_all(engine)
    install_triggers(engine)
    hooks.install()
    s = db.new_session()
    with audit_context(AuditContext(user_name="TEST-SEED", reason="seed")):
        seed.seed_baseline(s, company_name="Acme Biologicals")
        s.commit()
    s.close()
    login_limiter.reset()
    yield engine
    engine.dispose()


@pytest.fixture()
def session(engine):
    s = db.new_session()
    yield s
    s.close()


def make_user(username: str, role_codes: list[str], password: str = PW, *, must_change: bool = False,
              active: bool = True, auth_source: str = "LOCAL", full_name: str | None = None) -> int:
    s = db.new_session()
    try:
        with audit_context(AuditContext(user_name="TEST-SETUP", reason="test setup")):
            u = User(username=username, full_name=full_name or f"Test {username.title()}",
                     auth_source=auth_source, is_active=active)
            s.add(u)
            s.flush()
            if auth_source == "LOCAL":
                auth_service.set_password(s, u, password, must_change=must_change, enforce_history=False)
            for code in role_codes:
                role = s.execute(select(Role).where(Role.role_code == code)).scalar_one()
                s.add(UserRole(user_id=u.id, role_id=role.id, valid_from=date(2020, 1, 1)))
            s.commit()
            return u.id
    finally:
        s.close()


@pytest.fixture()
def app(engine):
    return create_app(configure_db=False)


@pytest.fixture()
def client(app):
    return TestClient(app, raise_server_exceptions=False)


def login(client: TestClient, username: str, password: str = PW) -> dict:
    r = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"X-CSRF-Token": r.json()["csrf_token"]}


@pytest.fixture()
def admin(client):
    make_user("admin1", ["SYSTEM_ADMIN"])
    return login(client, "admin1")


def reason(h: dict, why: str = "test reason") -> dict:
    return {**h, "X-Change-Reason": why}
