from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.core import db
from app.models import AuditTrail, Specification
from tests.conftest import PW
from tests.helpers import as_user, bootstrap_basics


@pytest.fixture()
def world(app):
    ids = bootstrap_basics(app)
    qc, hq = as_user(app, "qc_v", ["QC_ANALYST"])
    qa, ha = as_user(app, "qa_v", ["QA_HEAD"])
    m = qc.post("/api/v1/materials", headers=hq, json={"name": "Glycine", "type_id": ids["RM"], "base_unit_id": ids["kg"],
                                                       "reason": "new"}).json()
    return dict(ids=ids, qc=qc, hq=hq, qa=qa, ha=ha, material=m)


def _stp(w, **kw):
    body = {"title": "Assay by titration", "procedure": "Weigh 1 g ...", "reason": "new STP", **kw}
    return w["qc"].post("/api/v1/stps", headers=w["hq"], json=body)


def _approve(client, h, path, rid, reason="reviewed and approved", pw=PW):
    return client.post(f"/api/v1/{path}/{rid}/approve", headers=h, json={"password": pw, "reason": reason})


def test_stp_requires_procedure_then_approve_with_signature_and_sod(world):
    w = world
    r = w["qc"].post("/api/v1/stps", headers=w["hq"], json={"title": "No procedure", "reason": "x"})
    assert r.status_code == 201 and r.json()["stp_no"] == "STP-00001" and r.json()["version_no"] == 1
    assert w["qc"].post(f"/api/v1/stps/{r.json()['id']}/submit", headers=w["hq"]).status_code == 422
    stp = _stp(w).json()
    assert w["qc"].post(f"/api/v1/stps/{stp['id']}/submit", headers=w["hq"]).json()["status"] == "UNDER_REVIEW"
    # not approvable by author's role, and cannot approve a DRAFT
    assert _approve(w["qc"], w["hq"], "stps", stp["id"]).status_code == 403
    assert _approve(w["qa"], w["ha"], "stps", stp["id"], pw="wrong-Password-1!").status_code == 401
    ok = _approve(w["qa"], w["ha"], "stps", stp["id"])
    assert ok.status_code == 200 and ok.json()["status"] == "APPROVED" and ok.json()["approved_signature_id"]
    assert ok.json()["effective_from"]


def test_author_cannot_approve_own_stp_sod16(world):
    w = world
    stp = w["qa"].post("/api/v1/stps", headers=w["ha"], json={"title": "QA authored", "procedure": "p", "reason": "x"}).json()
    w["qa"].post(f"/api/v1/stps/{stp['id']}/submit", headers=w["ha"])
    r = _approve(w["qa"], w["ha"], "stps", stp["id"])
    assert r.status_code == 409 and r.json()["rule_id"] == "SOD-16"


def test_approved_version_is_immutable_and_new_version_supersedes(world):
    w = world
    stp = _stp(w).json()
    w["qc"].post(f"/api/v1/stps/{stp['id']}/submit", headers=w["hq"])
    _approve(w["qa"], w["ha"], "stps", stp["id"])
    # editing an approved version is refused (BR-HIS-001)
    r = w["qc"].patch(f"/api/v1/stps/{stp['id']}", headers=w["hq"], json={"procedure": "silently changed", "reason": "oops"})
    assert r.status_code == 409 and r.json()["rule_id"] == "BR-HIS-001"
    # controlled change: new version needs a reason
    assert w["qc"].post(f"/api/v1/stps/{stp['id']}/new-version", headers=w["hq"], json={}).status_code == 422
    v2 = w["qc"].post(f"/api/v1/stps/{stp['id']}/new-version", headers=w["hq"], json={"reason": "titrant changed"})
    assert v2.status_code == 201 and v2.json()["version_no"] == 2 and v2.json()["stp_no"] == stp["stp_no"]
    assert v2.json()["status"] == "DRAFT" and v2.json()["procedure"] == "Weigh 1 g ..."
    # only one open draft at a time
    assert w["qc"].post(f"/api/v1/stps/{stp['id']}/new-version", headers=w["hq"], json={"reason": "again"}).status_code in (409, 422)
    w["qc"].patch(f"/api/v1/stps/{v2.json()['id']}", headers=w["hq"], json={"procedure": "Weigh 2 g", "reason": "edit draft"})
    w["qc"].post(f"/api/v1/stps/{v2.json()['id']}/submit", headers=w["hq"])
    assert _approve(w["qa"], w["ha"], "stps", v2.json()["id"]).status_code == 200
    h = w["qc"].get(f"/api/v1/stps/{stp['id']}").json()["versions"]
    assert [(x["version_no"], x["status"]) for x in h] == [(1, "SUPERSEDED"), (2, "APPROVED")]
    # the old version row still holds its original content
    assert w["qc"].get(f"/api/v1/stps/{stp['id']}").json()["procedure"] == "Weigh 1 g ..."


def _spec(w, with_stp_id=None):
    s = w["qc"].post("/api/v1/specifications", headers=w["hq"], json={"material_id": w["material"]["id"], "title": "Glycine spec", "reason": "new"}).json()
    p = w["qc"].post(f"/api/v1/specifications/{s['id']}/parameters", headers=w["hq"],
                     json={"test_name": "Assay", "lsl": 98.5, "usl": 101.0, "target": 99.8, "unit": "%", "stp_id": with_stp_id})
    assert p.status_code == 201, p.text
    w["qc"].post(f"/api/v1/specifications/{s['id']}/parameters", headers=w["hq"],
                 json={"test_name": "Appearance", "spec_type": "TEXT", "acceptance_criteria": "White crystalline powder"})
    return s


def test_specification_flow_historical_link_and_parameter_rules(world):
    w = world
    s = _spec(w)
    bad = w["qc"].post(f"/api/v1/specifications/{s['id']}/parameters", headers=w["hq"], json={"test_name": "pH", "lsl": 7, "usl": 5})
    assert bad.status_code == 422
    out_of = w["qc"].post(f"/api/v1/specifications/{s['id']}/parameters", headers=w["hq"], json={"test_name": "pH", "lsl": 5, "usl": 7, "target": 9})
    assert out_of.status_code == 422
    # a spec with no parameters cannot be submitted
    empty = w["qc"].post("/api/v1/specifications", headers=w["hq"], json={"material_id": w["material"]["id"], "reason": "x"}).json()
    assert w["qc"].post(f"/api/v1/specifications/{empty['id']}/submit", headers=w["hq"]).status_code == 422
    w["qc"].post(f"/api/v1/specifications/{s['id']}/submit", headers=w["hq"])
    assert _approve(w["qa"], w["ha"], "specifications", s["id"]).status_code == 200
    t_between_v1 = datetime.now(timezone.utc)
    # approved spec: parameters can no longer be added / changed / deleted
    detail = w["qc"].get(f"/api/v1/specifications/{s['id']}").json()
    pid = detail["parameters"][0]["id"]
    assert w["qc"].post(f"/api/v1/specifications/{s['id']}/parameters", headers=w["hq"], json={"test_name": "Late"}).status_code == 409
    assert w["qc"].patch(f"/api/v1/specifications/{s['id']}/parameters/{pid}", headers=w["hq"], json={"usl": 150}).status_code == 409
    assert w["qc"].request("DELETE", f"/api/v1/specifications/{s['id']}/parameters/{pid}", headers=w["hq"], json={"reason": "x"}).status_code == 409
    # revise: v2 with a tighter limit
    v2 = w["qc"].post(f"/api/v1/specifications/{s['id']}/new-version", headers=w["hq"], json={"reason": "tighter assay"}).json()
    d2 = w["qc"].get(f"/api/v1/specifications/{v2['id']}").json()
    assert len(d2["parameters"]) == 2 and d2["parameters"][0]["id"] != pid
    w["qc"].patch(f"/api/v1/specifications/{v2['id']}/parameters/{d2['parameters'][0]['id']}", headers=w["hq"], json={"lsl": 99.0})
    w["qc"].post(f"/api/v1/specifications/{v2['id']}/submit", headers=w["hq"])
    _approve(w["qa"], w["ha"], "specifications", v2["id"])
    # historical lookups return the version in force at that time
    now_spec = w["qc"].get(f"/api/v1/materials/{w['material']['id']}/specification-in-force").json()
    assert now_spec["version_no"] == 2 and float(now_spec["parameters"][0]["lsl"]) == 99.0
    old_spec = w["qc"].get(f"/api/v1/materials/{w['material']['id']}/specification-in-force",
                           params={"on": t_between_v1.isoformat()}).json()
    assert old_spec["version_no"] == 1 and float(old_spec["parameters"][0]["lsl"]) == 98.5
    assert w["qc"].get(f"/api/v1/materials/{w['material']['id']}/specification-in-force",
                       params={"on": (t_between_v1 - timedelta(days=1)).isoformat()}).status_code == 404


def test_draft_parameter_delete_is_audited_and_spec_requires_approved_stp(world):
    w = world
    stp = _stp(w).json()   # still DRAFT
    s = w["qc"].post("/api/v1/specifications", headers=w["hq"], json={"material_id": w["material"]["id"], "reason": "x"}).json()
    p = w["qc"].post(f"/api/v1/specifications/{s['id']}/parameters", headers=w["hq"],
                     json={"test_name": "Assay", "lsl": 1, "usl": 2, "stp_id": stp["id"]}).json()
    assert w["qc"].post(f"/api/v1/specifications/{s['id']}/submit", headers=w["hq"]).status_code == 422  # STP not approved
    assert w["qc"].request("DELETE", f"/api/v1/specifications/{s['id']}/parameters/{p['id']}", headers=w["hq"], json={"reason": "wrong test"}).status_code == 200
    d = db.new_session()
    row = d.execute(select(AuditTrail).where(AuditTrail.entity == "specification_parameter", AuditTrail.action == "DELETE")).scalars().one()
    assert "Assay" in row.old_value and row.reason == "wrong test"
    d.close()


def test_sampling_plan_rules_and_versions(world):
    w = world
    sp = w["qc"].post("/api/v1/sampling-plans", headers=w["hq"], json={"material_id": w["material"]["id"], "sampling_rule": "FIXED", "reason": "x"}).json()
    assert w["qc"].post(f"/api/v1/sampling-plans/{sp['id']}/submit", headers=w["hq"]).status_code == 422  # FIXED needs qty
    w["qc"].patch(f"/api/v1/sampling-plans/{sp['id']}", headers=w["hq"], json={"fixed_qty": 50, "reason": "qty"})
    assert w["qc"].post(f"/api/v1/sampling-plans/{sp['id']}/submit", headers=w["hq"]).status_code == 200
    assert _approve(w["qa"], w["ha"], "sampling-plans", sp["id"]).status_code == 200
    assert w["qc"].get(f"/api/v1/sampling-plans?current=1").json()["total"] == 1


def test_return_to_draft_needs_reason(world):
    w = world
    stp = _stp(w).json()
    w["qc"].post(f"/api/v1/stps/{stp['id']}/submit", headers=w["hq"])
    assert w["qa"].post(f"/api/v1/stps/{stp['id']}/return", headers=w["ha"], json={}).status_code == 422
    r = w["qa"].post(f"/api/v1/stps/{stp['id']}/return", headers=w["ha"], json={"reason": "method unclear"})
    assert r.status_code == 200 and r.json()["status"] == "DRAFT"
