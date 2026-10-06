import pytest
from sqlalchemy import select, text, update
from sqlalchemy.exc import DBAPIError

from app.audit import service as audit
from app.audit.context import AuditContext, audit_context
from app.core import db
from app.core.errors import ImmutableRecordError, ReasonRequired
from app.models import AuditTrail, Company, User
from tests.conftest import login, make_user, reason


def _drop_audit_triggers(conn):
    """Simulate a DBA removing the protection (dialect-aware)."""
    from app.audit.immutability import drop_statements
    for stmt in drop_statements(conn.dialect.name, ("audit_trail",)):
        conn.execute(text(stmt))


def test_field_level_audit_with_old_new_user_reason(client, admin):
    r = client.put("/api/v1/company", headers=admin, json={"gst_no": "29ABCDE1234F1Z5", "reason": "initial setup"})
    assert r.status_code == 200
    r = client.put("/api/v1/company", headers=admin, json={"gst_no": "29ZZZZZ1234F1Z5", "reason": "typo fix"})
    s = db.new_session()
    rows = s.execute(select(AuditTrail).where(AuditTrail.entity == "company", AuditTrail.field_name == "gst_no")
                     .order_by(AuditTrail.id)).scalars().all()
    s.close()
    assert [(x.old_value, x.new_value, x.reason) for x in rows] == [
        (None, "29ABCDE1234F1Z5", "initial setup"), ("29ABCDE1234F1Z5", "29ZZZZZ1234F1Z5", "typo fix")]
    assert rows[0].user_name == "admin1" and "SYSTEM_ADMIN" in rows[0].role_name and rows[0].ip_address


def test_master_update_without_reason_is_rejected_and_rolled_back(client, admin):
    r = client.put("/api/v1/company", headers=admin, json={"name": "Hacked Ltd"})
    assert r.status_code == 422 and r.json()["code"] == "REASON_REQUIRED"
    s = db.new_session()
    assert s.execute(select(Company.name)).scalar() == "Acme Biologicals"
    s.close()


def test_password_hash_is_redacted_in_audit(client, admin):
    client.post("/api/v1/users", headers=admin, json={"username": "red1", "full_name": "R", "reason": "x"})
    s = db.new_session()
    vals = " ".join((a.new_value or "") + (a.old_value or "") for a in s.execute(select(AuditTrail).where(
        AuditTrail.entity == "users")).scalars())
    s.close()
    assert "$argon2" not in vals and "REDACTED" in vals


def test_audit_rows_cannot_be_updated_or_deleted_via_orm(session, engine):
    audit.log_event(session, module="t", entity="x", record_id=1, action="A")
    session.commit()
    row = session.execute(select(AuditTrail)).scalars().first()
    row.reason = "tamper"
    with pytest.raises(ImmutableRecordError):
        session.flush()
    session.rollback()
    session.delete(session.execute(select(AuditTrail)).scalars().first())
    with pytest.raises(ImmutableRecordError):
        session.flush()


def test_audit_rows_cannot_be_modified_with_raw_sql_db_trigger(session):
    audit.log_event(session, module="t", entity="x", record_id=1, action="A")
    session.commit()
    with pytest.raises(DBAPIError):
        session.execute(text("UPDATE audit_trail SET new_value='x'"))
    session.rollback()
    with pytest.raises(DBAPIError):
        session.execute(text("DELETE FROM audit_trail"))


def test_hash_chain_verifies_and_detects_tampering(session, engine):
    for i in range(5):
        audit.log_event(session, module="t", entity="x", record_id=i, action="A", new=f"v{i}")
        session.commit()
    assert audit.verify_chain(session)["ok"]
    # an attacker with DBA rights drops the trigger and edits a row
    with engine.begin() as c:
        _drop_audit_triggers(c)
        c.execute(text("UPDATE audit_trail SET new_value='forged' WHERE id=3"))
    res = audit.verify_chain(session)
    assert res["ok"] is False and res["first_bad_audit_id"] == 3


def test_hash_chain_detects_removed_tail(session, engine):
    for i in range(3):
        audit.log_event(session, module="t", entity="x", record_id=i, action="A")
        session.commit()
    with engine.begin() as c:
        _drop_audit_triggers(c)
        c.execute(text("DELETE FROM audit_trail WHERE id=(SELECT MAX(id) FROM audit_trail)"))
    assert audit.verify_chain(session)["ok"] is False


def test_audit_written_in_same_transaction_rollback_removes_both(session):
    before = session.execute(select(AuditTrail.id)).all()
    with audit_context(AuditContext(user_name="t", reason="r")):
        c = session.execute(select(Company)).scalars().first()
        c.name = "Temp"
        session.flush()
    session.rollback()
    after = session.execute(select(AuditTrail.id)).all()
    assert before == after
    assert session.execute(select(Company.name)).scalar() == "Acme Biologicals"


def test_physical_delete_of_audited_record_refused(session):
    c = session.execute(select(Company)).scalars().first()
    session.delete(c)
    with pytest.raises(ImmutableRecordError):
        session.flush()


def test_audit_export_and_verify_endpoints_for_qa(client):
    make_user("qa1", ["QA_HEAD"])
    login(client, "qa1")
    h = {"X-CSRF-Token": client.get("/api/v1/auth/me").json()["csrf_token"]}
    assert client.get("/api/v1/audit-trail/verify").json()["ok"] is True
    r = client.get("/api/v1/audit-trail/export")
    assert r.status_code == 200 and r.text.startswith("# GMP-MERP audit trail export")
    # the export itself is audited
    items = client.get("/api/v1/audit-trail", params={"action": "EXPORT"}).json()["items"]
    assert len(items) == 1


def test_audit_keyset_pagination(client):
    make_user("qa2", ["QA_HEAD"])
    for i in range(5):
        client.post("/api/v1/auth/login", json={"username": "ghost", "password": "x"})
    login(client, "qa2")
    page1 = client.get("/api/v1/audit-trail", params={"limit": 3}).json()
    assert len(page1["items"]) == 3 and page1["next_before_id"]
    page2 = client.get("/api/v1/audit-trail", params={"limit": 3, "before_id": page1["next_before_id"]}).json()
    assert page2["items"] and page2["items"][0]["id"] < page1["items"][-1]["id"]


def test_normal_roles_have_no_audit_write_endpoints(client, admin):
    for method in ("put", "patch", "delete", "post"):
        r = getattr(client, method)("/api/v1/audit-trail/1", headers=admin)
        assert r.status_code in (404, 405)
