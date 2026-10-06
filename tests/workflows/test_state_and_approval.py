import pytest
from sqlalchemy import Column, ForeignKey, Integer, String, select

from app.core import db
from app.core.db import Base
from app.core.errors import (IllegalTransition, ImmutableRecordError, PermissionDenied,
                             SegregationOfDutiesError, AuthenticationError)
from app.models import ESignature, SodRule, StatusHistory, User, WorkflowDefinition
from app.models.base import AuditedMixin, StatefulMixin
from app.audit.context import AuditContext, audit_context
from app.services import sod
from app.workflows import approval
from app.workflows.state_machine import StateMachine, Transition, transition
from tests.conftest import PW, login, make_user

from sqlalchemy.orm import Mapped, mapped_column


class DemoRecord(StatefulMixin, AuditedMixin, Base):
    __tablename__ = "demo_record"
    __audit_module__ = "demo"
    status: Mapped[str] = mapped_column(String(20), default="DRAFT")
    title: Mapped[str] = mapped_column(String(50), default="t")


MACHINE = StateMachine("demo", "DRAFT", {
    "DRAFT": {"SUBMITTED": Transition("SUBMITTED")},
    "SUBMITTED": {"APPROVED": Transition("APPROVED", "demo.approve"), "DRAFT": Transition("DRAFT")},
})


@pytest.fixture()
def demo(engine):
    Base.metadata.create_all(engine)
    s = db.new_session()
    with audit_context(AuditContext(user_id=None, user_name="t")):
        r = DemoRecord()
        s.add(r)
        s.commit()
    yield s, r
    s.close()


def test_legal_transition_records_history_and_audit(demo):
    s, r = demo
    with audit_context(AuditContext(user_name="t")):
        transition(s, MACHINE, r, "SUBMITTED")
        s.commit()
    assert r.status == "SUBMITTED"
    assert s.execute(select(StatusHistory).where(StatusHistory.entity == "demo_record")).scalars().one().to_status == "SUBMITTED"


def test_illegal_transition_blocked(demo):
    s, r = demo
    with pytest.raises(IllegalTransition):
        transition(s, MACHINE, r, "APPROVED")
    assert r.status == "DRAFT"


def test_missing_permission_blocks_transition(demo):
    s, r = demo
    with audit_context(AuditContext(user_name="t")):
        transition(s, MACHINE, r, "SUBMITTED")
        with pytest.raises(PermissionDenied):
            transition(s, MACHINE, r, "APPROVED", user_permissions=set())


def test_direct_status_assignment_refused_BR_SEC_001(demo):
    s, r = demo
    r.status = "APPROVED"  # attempt to bypass the engine
    with pytest.raises(ImmutableRecordError):
        s.flush()


def _def(s, process, steps, author_id):
    with audit_context(AuditContext(user_id=author_id, user_name="author", reason="setup")):
        d = approval.create_definition(s, process, "Test chain", steps)
        s.commit()
        return d


def _approve_def(s, d, user, password=PW):
    with audit_context(AuditContext(user_id=user.id, user_name=user.username, reason="approved for use")):
        approval.approve_definition(s, d, user, password, "approved for use",
                                    {"workflow.definition.approve"})
        s.commit()


def test_definition_needs_qa_signature_and_sod_author_neq_approver(engine):
    author = make_user("auth1", ["SYSTEM_ADMIN"])
    qa = make_user("qa_h", ["QA_HEAD"])
    s = db.new_session()
    d = _def(s, "demo.chain", [{"seq": 1, "name": "QC", "role_code": "QC_HEAD"}], author)
    with audit_context(AuditContext(user_id=author, user_name="author")):
        sod.record_action(s, "workflow_definition", d.id, "workflow.definition.author", author)
        s.commit()
    # author (admin) cannot approve: wrong password? no - SoD / permission
    u_author = s.get(User, author)
    with pytest.raises((SegregationOfDutiesError, PermissionDenied)):
        _approve_def(s, d, u_author)
    # wrong password for the real approver is refused
    u_qa = s.get(User, qa)
    with pytest.raises(AuthenticationError):
        _approve_def(s, d, u_qa, "wrong-Password-1!")
    s.rollback()
    _approve_def(s, d, u_qa)
    assert d.status == "APPROVED" and d.approved_signature_id
    sig = s.get(ESignature, d.approved_signature_id)
    assert sig.meaning == "APPROVED_BY" and sig.user_id == qa and sig.printed_name == u_qa.full_name
    assert len(sig.record_hash) == 64 and sig.entity == "workflow_definition"


def test_approved_definition_is_versioned_not_overwritten(engine):
    qa = make_user("qa_v", ["QA_HEAD"])
    author = make_user("auth_v", ["SYSTEM_ADMIN"])
    s = db.new_session()
    u = s.get(User, qa)
    d1 = _def(s, "demo.v", [{"seq": 1, "name": "A", "role_code": "QC_HEAD"}], author)
    _approve_def(s, d1, u)
    d2 = _def(s, "demo.v", [{"seq": 1, "name": "A", "role_code": "QC_HEAD"},
                            {"seq": 2, "name": "B", "role_code": "QA_HEAD"}], author)
    assert d2.version_no == 2
    _approve_def(s, d2, u)
    s.refresh(d1)
    assert d1.status == "SUPERSEDED" and d2.status == "APPROVED"


def test_two_step_chain_with_signatures_and_sod(engine):
    qa = make_user("qa_c", ["QA_HEAD"])
    qch = make_user("qc_c", ["QC_HEAD"])
    initiator = make_user("prod_c", ["PRODUCTION_MANAGER"])
    author = make_user("auth_c", ["SYSTEM_ADMIN"])
    s = db.new_session()
    s.add(SodRule(sod_id="T", action_code="demo.chain.approve", conflicts_with_action_code="demo.chain.submit"))
    s.commit()
    d = _def(s, "demo.chain", [{"seq": 1, "name": "QC review", "role_code": "QC_HEAD", "meaning": "REVIEWED_BY"},
                               {"seq": 2, "name": "QA", "role_code": "QA_HEAD", "meaning": "QA_RELEASED"}], author)
    _approve_def(s, d, s.get(User, qa))
    ui, uq, ua = s.get(User, initiator), s.get(User, qch), s.get(User, qa)
    with audit_context(AuditContext(user_id=ui.id, user_name=ui.username)):
        inst = approval.start(s, "demo.chain", "demo_record", 7, ui)
        s.commit()
    snap = {"rec": 7}
    # QA cannot act on step 1 (wrong role)
    with audit_context(AuditContext(user_id=ua.id, user_name=ua.username)):
        with pytest.raises(PermissionDenied):
            approval.act(s, inst, ua, "APPROVE", password=PW, comment=None, record_snapshot=snap)
    s.rollback()
    with audit_context(AuditContext(user_id=uq.id, user_name=uq.username)):
        approval.act(s, inst, uq, "APPROVE", password=PW, comment="ok", record_snapshot=snap)
        s.commit()
    assert inst.current_seq == 2 and inst.status == "IN_PROGRESS"
    with audit_context(AuditContext(user_id=ua.id, user_name=ua.username)):
        approval.act(s, inst, ua, "APPROVE", password=PW, comment="released", record_snapshot=snap)
        s.commit()
    assert inst.status == "APPROVED"
    meanings = [x.meaning for x in s.execute(select(ESignature).where(ESignature.entity == "demo_record")).scalars()]
    assert meanings == ["REVIEWED_BY", "QA_RELEASED"]


def test_initiator_cannot_approve_own_submission(engine):
    qa = make_user("qa_s", ["QA_HEAD"])
    author = make_user("auth_s", ["SYSTEM_ADMIN"])
    s = db.new_session()
    s.add(SodRule(sod_id="T2", action_code="demo.self.approve", conflicts_with_action_code="demo.self.submit"))
    s.commit()
    d = _def(s, "demo.self", [{"seq": 1, "name": "QA", "role_code": "QA_HEAD"}], author)
    uqa = s.get(User, qa)
    _approve_def(s, d, uqa)
    with audit_context(AuditContext(user_id=uqa.id, user_name=uqa.username)):
        inst = approval.start(s, "demo.self", "demo_record", 1, uqa)  # QA submits...
        s.commit()
        with pytest.raises(SegregationOfDutiesError):               # ...and tries to approve
            approval.act(s, inst, uqa, "APPROVE", password=PW, comment=None, record_snapshot={})


def test_rejection_is_terminal_and_requires_reason(engine):
    qa = make_user("qa_r", ["QA_HEAD"])
    ini = make_user("ini_r", ["PRODUCTION_MANAGER"])
    author = make_user("auth_r", ["SYSTEM_ADMIN"])
    s = db.new_session()
    d = _def(s, "demo.rej", [{"seq": 1, "name": "QA", "role_code": "QA_HEAD"}], author)
    uqa = s.get(User, qa)
    _approve_def(s, d, uqa)
    ui = s.get(User, ini)
    with audit_context(AuditContext(user_id=ui.id, user_name="i")):
        inst = approval.start(s, "demo.rej", "demo_record", 9, ui)
        s.commit()
    with audit_context(AuditContext(user_id=uqa.id, user_name="q")):
        from app.core.errors import ValidationFailed
        with pytest.raises(ValidationFailed):
            approval.act(s, inst, uqa, "REJECT", password=PW, comment=None, record_snapshot={})
        s.rollback()
        approval.act(s, inst, uqa, "REJECT", password=PW, comment="spec mismatch", record_snapshot={})
        s.commit()
    assert inst.status == "REJECTED"


def test_signature_failure_counts_toward_lockout(engine):
    qa = make_user("qa_l", ["QA_HEAD"])
    from app.services import esign
    s = db.new_session()
    u = s.get(User, qa)
    for _ in range(5):
        with pytest.raises(AuthenticationError):
            esign.sign(s, u, "wrong-Password-1!", meaning="APPROVED_BY", entity="x", record_id=1, record_snapshot={})
    s2 = db.new_session()
    assert s2.get(User, qa).locked_until is not None


def test_workflow_definition_api_end_to_end(client):
    make_user("adm_w", ["SYSTEM_ADMIN"])
    make_user("qa_w", ["QA_HEAD"])
    h = login(client, "adm_w")
    r = client.post("/api/v1/workflows/definitions", headers=h, json={
        "process_code": "material.release", "name": "Material release", "reason": "initial",
        "steps": [{"seq": 1, "name": "QC Analyst", "role_code": "QC_ANALYST", "meaning": "TESTED_BY"},
                  {"seq": 2, "name": "QC Head", "role_code": "QC_HEAD", "meaning": "REVIEWED_BY"},
                  {"seq": 3, "name": "QA Officer", "role_code": "QA_OFFICER", "meaning": "VERIFIED_BY"},
                  {"seq": 4, "name": "QA Head", "role_code": "QA_HEAD", "meaning": "QA_RELEASED"}]})
    assert r.status_code == 201, r.text
    did = r.json()["id"]
    # admin has no approval authority
    assert client.post(f"/api/v1/workflows/definitions/{did}/approve", headers=h,
                       json={"password": PW, "reason": "x"}).status_code == 403
    client.post("/api/v1/auth/logout", headers=h)
    h2 = login(client, "qa_w")
    ok = client.post(f"/api/v1/workflows/definitions/{did}/approve", headers=h2,
                     json={"password": PW, "reason": "reviewed and approved"})
    assert ok.status_code == 200 and ok.json()["status"] == "APPROVED"
    sigs = client.get("/api/v1/esignatures", params={"entity": "workflow_definition", "record_id": did}).json()
    assert sigs and sigs[0]["meaning"] == "APPROVED_BY" and sigs[0]["reason"] == "reviewed and approved"


def test_training_gate_blocks_signing_until_trained(engine):
    from datetime import date
    from app.models import TrainingRecord
    from app.services import config_service, esign
    qa = make_user("qa_t", ["QA_HEAD"])
    s = db.new_session()
    with audit_context(AuditContext(user_name="t", reason="enable gate")):
        from app.models import SystemConfiguration
        row = s.execute(select(SystemConfiguration).where(SystemConfiguration.config_key == "training.gate")).scalar_one()
        row.value = "true"
        s.commit()
    u = s.get(User, qa)
    kw = dict(meaning="APPROVED_BY", entity="x", record_id=1, record_snapshot={}, training_code="SOP-001")
    with pytest.raises(PermissionDenied):
        esign.sign(s, u, PW, **kw)
    s.rollback()
    with audit_context(AuditContext(user_name="t")):
        s.add(TrainingRecord(user_id=qa, training_code="SOP-001", trained_on=date.today()))
        s.commit()
    assert esign.sign(s, u, PW, **kw).id


def test_signer_without_permission_refused(engine):
    from app.services import esign
    wh = make_user("wh_s", ["WAREHOUSE_USER"])
    s = db.new_session()
    with pytest.raises(PermissionDenied):
        esign.sign(s, s.get(User, wh), PW, meaning="APPROVED_BY", entity="x", record_id=1, record_snapshot={},
                   required_permission="workflow.definition.approve")


def test_ledger_style_append_only_tables_refuse_update(engine):
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError
    qa = make_user("qa_ao", ["QA_HEAD"])
    from app.services import esign
    s = db.new_session()
    sig = esign.sign(s, s.get(User, qa), PW, meaning="APPROVED_BY", entity="x", record_id=1, record_snapshot={})
    s.commit()
    with pytest.raises(DBAPIError):
        s.execute(text("UPDATE e_signature SET meaning='QA_RELEASED'"))
