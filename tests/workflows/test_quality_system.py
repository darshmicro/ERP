import io
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.core import db
from app.models import Deviation, QualityHold
from tests.conftest import PW
from tests.helpers import PDF, as_user, assign, build_qc_world, submit_pass_results, take_sample
from tests.workflows.test_dispatch import build_dispatch_world, finish_dispatch
from tests.workflows.test_manufacturing import API, build_mfg_world, complete_steps, finish_production, get, issue, make_bom, new_batch, run_to_in_process

pytestmark = pytest.mark.filterwarnings("ignore")


@pytest.fixture()
def q(app):
    w = build_qc_world(app)
    w["qch"], w["hqch"] = as_user(app, "qc_head", ["QC_HEAD"])
    w["pr"], w["hpr"] = as_user(app, "prod1", ["PRODUCTION_USER"])
    w["qa2"], w["hqa2"] = as_user(app, "qa_head2", ["QA_HEAD"])
    return w


def dev_body(**kw):
    return {"title": "Pallet damaged on receipt", "description": "Outer cartons crushed", "severity": "MINOR", "reason": "raised", **kw}


def ready_for_release(w):
    sm = take_sample(w)
    assign(w, sm["id"])
    submit_pass_results(w, sm["id"])


def advance(w, did, who="qo", h="hqo"):
    for step in ("investigate",):
        r = w[who].post(f"{API}/deviations/{did}/{step}", headers=w[h], json={"reason": "go"})
        assert r.status_code == 200, r.text


# ------------------------------------------------------------------ deviation
def test_open_deviation_blocks_release_until_closed_with_independent_qa_signature(q):
    w = q
    ready_for_release(w)
    d = w["pr"].post(f"{API}/deviations", headers=w["hpr"], json=dev_body(severity="MAJOR", entity_type="MATERIAL_BATCH", record_id=w["lot"]))
    assert d.status_code == 201, d.text
    d = d.json()
    assert d["dev_no"].startswith("DEV-") and d["status"] == "OPEN" and d["ref_label"]
    r = w["qc"].post(f"{API}/lots/{w['lot']}/submit-release", headers=w["hqc"])
    assert r.status_code == 409 and any("BR-DEV-001" in x for x in r.json()["details"])           # open deviation blocks QA release
    # production user cannot investigate / close
    assert w["pr"].post(f"{API}/deviations/{d['id']}/investigate", headers=w["hpr"], json={"reason": "x"}).status_code == 403
    advance(w, d["id"])
    # cannot skip stages
    assert w["qo"].post(f"{API}/deviations/{d['id']}/submit-review", headers=w["hqo"], json={"reason": "x"}).status_code == 409
    p = w["qo"].post(f"{API}/deviations/{d['id']}/propose-capa", headers=w["hqo"], json={"reason": "x"})
    assert p.status_code == 422                                                                    # root cause missing
    assert w["qo"].patch(f"{API}/deviations/{d['id']}", headers=w["hqo"], json={"root_cause": "Forklift impact", "impact_assessment": "Primary containers intact", "reason": "inv"}).status_code == 200
    p = w["qo"].post(f"{API}/deviations/{d['id']}/propose-capa", headers=w["hqo"], json={"reason": "x"})
    assert p.status_code == 409 and p.json()["rule_id"] == "BR-DEV-002"                            # MAJOR needs a CAPA or justification
    w["qo"].patch(f"{API}/deviations/{d['id']}", headers=w["hqo"], json={"no_capa_justification": "Isolated handling error; retraining done", "reason": "j"})
    assert w["qo"].post(f"{API}/deviations/{d['id']}/propose-capa", headers=w["hqo"], json={"reason": "x"}).status_code == 200
    assert w["qo"].post(f"{API}/deviations/{d['id']}/submit-review", headers=w["hqo"], json={"reason": "x"}).status_code == 200
    # locked after review submission
    assert w["qo"].patch(f"{API}/deviations/{d['id']}", headers=w["hqo"], json={"title": "changed", "reason": "x"}).status_code in (409, 422)
    assert w["qa"].post(f"{API}/deviations/{d['id']}/close", headers=w["hqa"], json={"password": "wrong", "reason": "ok"}).status_code == 401
    c = w["qa"].post(f"{API}/deviations/{d['id']}/close", headers=w["hqa"], json={"password": PW, "reason": "Accepted; no product impact"})
    assert c.status_code == 200 and c.json()["status"] == "CLOSED" and c.json()["close_signature_id"]
    assert w["qc"].post(f"{API}/lots/{w['lot']}/submit-release", headers=w["hqc"]).status_code == 200      # no longer blocked


def test_deviation_raiser_cannot_close_and_non_blocking_flag(q):
    w = q
    d = w["qa"].post(f"{API}/deviations", headers=w["hqa"], json=dev_body(blocks_release=False, entity_type="MATERIAL_BATCH", record_id=w["lot"])).json()
    ready_for_release(w)
    assert w["qc"].post(f"{API}/lots/{w['lot']}/submit-release", headers=w["hqc"]).status_code == 200      # non-blocking deviation does not hold release
    w["qa"].post(f"{API}/deviations/{d['id']}/investigate", headers=w["hqa"], json={"reason": "go"})
    w["qa"].patch(f"{API}/deviations/{d['id']}", headers=w["hqa"], json={"root_cause": "x cause", "impact_assessment": "none", "reason": "i"})
    w["qa"].post(f"{API}/deviations/{d['id']}/propose-capa", headers=w["hqa"], json={"reason": "x"})
    w["qa"].post(f"{API}/deviations/{d['id']}/submit-review", headers=w["hqa"], json={"reason": "x"})
    r = w["qa"].post(f"{API}/deviations/{d['id']}/close", headers=w["hqa"], json={"password": PW, "reason": "self close"})
    assert r.status_code == 409 and r.json()["rule_id"] == "SOD-31"
    assert w["qa2"].post(f"{API}/deviations/{d['id']}/close", headers=w["hqa2"], json={"password": PW, "reason": "independent QA closure"}).status_code == 200


def test_temperature_excursion_raises_deviation_and_hold(q):
    w = q
    r = w["wh1"].post(f"{API}/locations/{w['qloc']}/temperature", headers=w["hwh1"], json={"reading": 40, "remarks": "chiller failure"})
    assert r.status_code in (200, 201), r.text
    devs = w["qa"].get(f"{API}/deviations?source=TEMPERATURE").json()
    assert devs["total"] == 1 and devs["items"][0]["entity_type"] == "MATERIAL_BATCH" and devs["items"][0]["record_id"] == w["lot"]
    # idempotent per lot while open
    w["wh1"].post(f"{API}/locations/{w['qloc']}/temperature", headers=w["hwh1"], json={"reading": 41})
    assert w["qa"].get(f"{API}/deviations?source=TEMPERATURE").json()["total"] == 1


# ------------------------------------------------------------------ CAPA
def test_capa_lifecycle_effectiveness_and_sod(q):
    w = q
    d = w["pr"].post(f"{API}/deviations", headers=w["hpr"], json=dev_body()).json()
    me = w["qo"].get(f"{API}/auth/me").json()["user"]["id"]
    due = str(date.today() + timedelta(days=30))
    body = {"title": "Retrain forklift operators", "description": "Handling", "capa_type": "CORRECTIVE", "source": "DEVIATION", "source_ref": d["dev_no"], "owner_id": me, "due_date": due, "reason": "c"}
    assert w["qo"].post(f"{API}/capas", headers=w["hqo"], json={**body, "due_date": str(date.today() - timedelta(days=1))}).status_code == 422
    assert w["qo"].post(f"{API}/capas", headers=w["hqo"], json={**body, "source_ref": "DEV-0000"}).status_code == 422
    c = w["qo"].post(f"{API}/capas", headers=w["hqo"], json=body)
    assert c.status_code == 201, c.text
    c = c.json()
    assert c["capa_no"].startswith("CAPA-") and c["status"] == "OPEN"
    assert w["qo"].get(f"{API}/deviations/{d['id']}").json()["capa_no"] == c["capa_no"]            # deviation <-> CAPA link
    assert w["qo"].post(f"{API}/capas/{c['id']}/effectiveness-check", headers=w["hqo"], json={"effectiveness_due": due, "reason": "x"}).status_code == 409   # no actions yet
    a = w["qo"].post(f"{API}/capas/{c['id']}/actions", headers=w["hqo"], json={"description": "Run forklift training", "owner_id": me, "due_date": due})
    assert a.status_code == 201
    assert w["qo"].get(f"{API}/capas/{c['id']}").json()["status"] == "IN_PROGRESS"
    assert w["qo"].post(f"{API}/capas/{c['id']}/effectiveness-check", headers=w["hqo"], json={"effectiveness_due": due, "reason": "x"}).status_code == 409   # action open
    assert w["qo"].post(f"{API}/capas/{c['id']}/actions/{a.json()['id']}/complete", headers=w["hqo"], json={"notes": "12 operators trained", "reason": "done"}).status_code == 200
    assert w["qo"].post(f"{API}/capas/{c['id']}/effectiveness-check", headers=w["hqo"], json={"effectiveness_due": due, "reason": "x"}).status_code == 200
    ine = w["qa"].post(f"{API}/capas/{c['id']}/close", headers=w["hqa"], json={"password": PW, "effective": False, "reason": "damage recurred"})
    assert ine.status_code == 200 and ine.json()["status"] == "IN_PROGRESS" and ine.json()["effectiveness_result"] == "INEFFECTIVE"
    assert w["qo"].post(f"{API}/capas/{c['id']}/effectiveness-check", headers=w["hqo"], json={"effectiveness_due": due, "reason": "x"}).status_code == 200
    # creator (QA officer) cannot hold close right; QA head closes with e-signature
    assert w["qo"].post(f"{API}/capas/{c['id']}/close", headers=w["hqo"], json={"password": PW, "reason": "x"}).status_code == 403
    ok = w["qa"].post(f"{API}/capas/{c['id']}/close", headers=w["hqa"], json={"password": PW, "effective": True, "reason": "no recurrence in 60 days"})
    assert ok.status_code == 200 and ok.json()["status"] == "CLOSED" and ok.json()["close_signature_id"]


def test_capa_creator_cannot_close_own_capa(q):
    w = q
    me = w["qa"].get(f"{API}/auth/me").json()["user"]["id"]
    due = str(date.today() + timedelta(days=10))
    cr = w["qa"].post(f"{API}/capas", headers=w["hqa"], json={"title": "Preventive review", "description": "Review all receiving SOPs", "capa_type": "PREVENTIVE", "source": "OTHER", "owner_id": me, "due_date": due, "reason": "c"})
    assert cr.status_code == 201, cr.text
    c = cr.json()
    a = w["qa"].post(f"{API}/capas/{c['id']}/actions", headers=w["hqa"], json={"description": "Review SOP", "owner_id": me, "due_date": due}).json()
    w["qa"].post(f"{API}/capas/{c['id']}/actions/{a['id']}/complete", headers=w["hqa"], json={"notes": "reviewed", "reason": "d"})
    w["qa"].post(f"{API}/capas/{c['id']}/effectiveness-check", headers=w["hqa"], json={"effectiveness_due": due, "reason": "x"})
    r = w["qa"].post(f"{API}/capas/{c['id']}/close", headers=w["hqa"], json={"password": PW, "effective": True, "reason": "ok"})
    assert r.status_code == 409 and r.json()["rule_id"] == "SOD-34"
    assert w["qa2"].post(f"{API}/capas/{c['id']}/close", headers=w["hqa2"], json={"password": PW, "effective": True, "reason": "verified independently"}).status_code == 200


# ------------------------------------------------------------------ change control wired to versioned masters
def set_config(key, value):
    from app.audit.context import AuditContext, audit_context
    from app.models.platform import SystemConfiguration
    s = db.new_session()
    with audit_context(AuditContext(user_name="TEST", reason="cfg")):
        row = s.execute(select(SystemConfiguration).where(SystemConfiguration.config_key == key)).scalars().first()
        if row:
            row.value = value
        else:
            s.add(SystemConfiguration(config_key=key, value=value, description="test"))
        s.commit()
    s.close()


def test_change_control_gates_new_master_versions(q):
    w = q
    v2 = w["qc"].post(f"{API}/specifications/{w['spec']}/new-version", headers=w["hqc"], json={"reason": "tighter limits"}).json()
    w["qc"].post(f"{API}/specifications/{v2['id']}/submit", headers=w["hqc"])
    set_config("cc.required_for_master_changes", "true")
    r = w["qa"].post(f"{API}/specifications/{v2['id']}/approve", headers=w["hqa"], json={"password": PW, "reason": "ok"})
    assert r.status_code == 409 and r.json()["rule_id"] == "BR-CC-001"
    cc = w["qo"].post(f"{API}/change-controls", headers=w["hqo"], json={"title": "Tighten NaCl assay limits", "description": "New supplier data", "change_type": "MASTER_DATA", "reason": "cc"})
    assert cc.status_code == 201, cc.text
    cc = cc.json()
    assert cc["cc_no"].startswith("CC-") and cc["status"] == "DRAFT"
    assert w["qo"].post(f"{API}/change-controls/{cc['id']}/links", headers=w["hqo"], json={"entity": "specification", "record_id": w["spec"], "reason": "x"}).status_code == 409   # approved version cannot be linked
    assert w["qo"].post(f"{API}/change-controls/{cc['id']}/links", headers=w["hqo"], json={"entity": "specification", "record_id": v2["id"], "reason": "x"}).status_code == 201
    assert w["qo"].post(f"{API}/change-controls/{cc['id']}/links", headers=w["hqo"], json={"entity": "widget", "record_id": 1, "reason": "x"}).status_code == 422
    assert w["qo"].post(f"{API}/change-controls/{cc['id']}/submit", headers=w["hqo"]).status_code == 200
    assert w["qo"].post(f"{API}/change-controls/{cc['id']}/assess", headers=w["hqo"], json={"impact_assessment": "Affects incoming testing of 1 material", "risk_level": "LOW", "reason": "a"}).status_code == 200
    still = w["qa"].post(f"{API}/specifications/{v2['id']}/approve", headers=w["hqa"], json={"password": PW, "reason": "ok"})
    assert still.status_code == 409 and still.json()["rule_id"] == "BR-CC-001"                     # CC not yet approved
    assert w["qo"].post(f"{API}/change-controls/{cc['id']}/decision", headers=w["hqo"], json={"password": PW, "reason": "ok"}).status_code == 403
    d = w["qa"].post(f"{API}/change-controls/{cc['id']}/decision", headers=w["hqa"], json={"password": PW, "approve": True, "reason": "risk acceptable"})
    assert d.status_code == 200 and d.json()["status"] == "IMPLEMENTATION" and d.json()["approved_signature_id"]
    assert w["qo"].post(f"{API}/change-controls/{cc['id']}/implemented", headers=w["hqo"], json={"notes": "done", "reason": "x"}).status_code == 409   # master still not approved
    ok = w["qa"].post(f"{API}/specifications/{v2['id']}/approve", headers=w["hqa"], json={"password": PW, "reason": "approved under CC"})
    assert ok.status_code == 200, ok.text
    assert w["qo"].post(f"{API}/change-controls/{cc['id']}/implemented", headers=w["hqo"], json={"notes": "New limits effective; QC briefed", "reason": "x"}).status_code == 200
    cl = w["qa"].post(f"{API}/change-controls/{cc['id']}/close", headers=w["hqa"], json={"password": PW, "notes": "No issues after 3 lots", "reason": "x"})
    assert cl.status_code == 200 and cl.json()["status"] == "CLOSED"
    assert w["qo"].get(f"{API}/change-controls/{cc['id']}").json()["links"][0]["status"] == "APPROVED"


def test_change_control_requester_cannot_approve_and_rejection(q):
    w = q
    cc = w["qa"].post(f"{API}/change-controls", headers=w["hqa"], json={"title": "Equipment change", "description": "Replace mixer", "change_type": "EQUIPMENT", "reason": "cc"}).json()
    w["qa"].post(f"{API}/change-controls/{cc['id']}/submit", headers=w["hqa"])
    w["qa"].post(f"{API}/change-controls/{cc['id']}/assess", headers=w["hqa"], json={"impact_assessment": "Requalification needed", "risk_level": "HIGH", "reason": "a"})
    r = w["qa"].post(f"{API}/change-controls/{cc['id']}/decision", headers=w["hqa"], json={"password": PW, "reason": "self"})
    assert r.status_code == 409 and r.json()["rule_id"] == "SOD-32"
    rj = w["qa2"].post(f"{API}/change-controls/{cc['id']}/decision", headers=w["hqa2"], json={"password": PW, "approve": False, "reason": "insufficient justification"})
    assert rj.status_code == 200 and rj.json()["status"] == "REJECTED"
    assert w["qa"].post(f"{API}/change-controls/{cc['id']}/cancel", headers=w["hqa"], json={"reason": "x"}).status_code == 409


# ------------------------------------------------------------------ risk assessment
def test_fmea_rpn_levels_and_approval_rules(q):
    w = q
    items = [{"function_step": "Sterile filtration", "failure_mode": "Filter integrity failure", "severity": 9, "occurrence": 4, "detection": 6},     # RPN 216 HIGH
             {"function_step": "Labelling", "failure_mode": "Wrong label", "severity": 6, "occurrence": 3, "detection": 3}]                              # RPN 54 LOW
    r = w["qo"].post(f"{API}/risk-assessments", headers=w["hqo"], json={"title": "Filling process FMEA", "items": items, "reason": "ra"})
    assert r.status_code == 201, r.text
    ra = r.json()
    assert [i["rpn"] for i in ra["items"]] == [216, 54] and [i["risk_level"] for i in ra["items"]] == ["HIGH", "LOW"] and ra["max_rpn"] == 216 and ra["ra_no"].startswith("RA-")
    assert w["qo"].post(f"{API}/risk-assessments", headers=w["hqo"], json={"title": "bad", "items": [{**items[0], "severity": 11}], "reason": "x"}).status_code == 422
    blocked = w["qa"].post(f"{API}/risk-assessments/{ra['id']}/approve", headers=w["hqa"], json={"password": PW, "reason": "ok"})
    assert blocked.status_code == 409 and blocked.json()["rule_id"] == "BR-RSK-001"                  # HIGH risk without mitigation/residual
    items[0].update(mitigation="Pre-use integrity test + redundant filter", residual_severity=9, residual_occurrence=2, residual_detection=3)
    upr = w["qo"].put(f"{API}/risk-assessments/{ra['id']}/items", headers=w["hqo"], json={"items": items, "reason": "mitigated"})
    assert upr.status_code == 200, upr.text
    up = upr.json()
    assert up["items"][0]["residual_rpn"] == 54 and up["items"][0]["residual_level"] == "LOW"
    assert w["qo"].post(f"{API}/risk-assessments/{ra['id']}/approve", headers=w["hqo"], json={"password": PW, "reason": "x"}).status_code == 403
    ok = w["qa"].post(f"{API}/risk-assessments/{ra['id']}/approve", headers=w["hqa"], json={"password": PW, "reason": "residual risk acceptable"})
    assert ok.status_code == 200 and ok.json()["status"] == "APPROVED"
    assert w["qo"].put(f"{API}/risk-assessments/{ra['id']}/items", headers=w["hqo"], json={"items": items, "reason": "x"}).status_code == 409   # approved => immutable


# ------------------------------------------------------------------ SOP control
def test_sop_versioning_acknowledgement_and_review_due(q):
    w = q
    r = w["qo"].post(f"{API}/sops", headers=w["hqo"], json={"title": "Receipt of raw materials", "review_period_months": 12, "reason": "draft"})
    assert r.status_code == 201, r.text
    sop = r.json()
    assert sop["sop_no"].startswith("SOP-") and sop["status"] == "DRAFT"
    w["qo"].post(f"{API}/sops/{sop['id']}/submit", headers=w["hqo"])
    nodoc = w["qa"].post(f"{API}/sops/{sop['id']}/approve", headers=w["hqa"], json={"password": PW, "reason": "ok"})
    assert nodoc.status_code in (409, 422)                                                          # no document attached / not submitted
    sop = w["qo"].post(f"{API}/sops", headers=w["hqo"], json={"title": "Sampling of raw materials", "review_period_months": 12, "reason": "draft"}).json()
    up = w["qo"].post(f"{API}/sops/{sop['id']}/document", headers={"X-CSRF-Token": w["hqo"]["X-CSRF-Token"]}, files={"file": ("sop.pdf", PDF, "application/pdf")})
    assert up.status_code == 200, up.text
    assert up.json()["document"]["sha256"]
    assert w["qo"].post(f"{API}/sops/{sop['id']}/submit", headers=w["hqo"]).status_code == 200
    assert w["qo"].post(f"{API}/sops/{sop['id']}/approve", headers=w["hqo"], json={"password": PW, "reason": "x"}).status_code == 403
    ap = w["qa"].post(f"{API}/sops/{sop['id']}/approve", headers=w["hqa"], json={"password": PW, "reason": "approved for use"})
    assert ap.status_code == 200, ap.text
    assert ap.json()["status"] == "APPROVED" and ap.json()["effective_from"]
    due = date.fromisoformat(ap.json()["review_due_date"])
    assert date.today() + timedelta(days=360) <= due <= date.today() + timedelta(days=370)
    # acknowledgement once per user per version
    assert w["qc"].post(f"{API}/sops/{sop['id']}/acknowledge", headers=w["hqc"]).status_code == 200
    assert w["qc"].post(f"{API}/sops/{sop['id']}/acknowledge", headers=w["hqc"]).status_code == 409
    assert w["qc"].get(f"{API}/sops/{sop['id']}").json()["acknowledged_by_me"] is True
    # approved content is immutable; revise via new version, supersede on approval
    v2 = w["qo"].post(f"{API}/sops/{sop['id']}/new-version", headers=w["hqo"], json={"reason": "annual review"})
    assert v2.status_code == 201 and v2.json()["version_no"] == 2 and v2.json()["document_id"] == up.json()["document_id"]
    w["qo"].post(f"{API}/sops/{v2.json()['id']}/submit", headers=w["hqo"])
    assert w["qa"].post(f"{API}/sops/{v2.json()['id']}/approve", headers=w["hqa"], json={"password": PW, "reason": "v2 approved"}).status_code == 200
    assert w["qo"].get(f"{API}/sops/{sop['id']}").json()["status"] == "SUPERSEDED"
    # ack for the old (superseded) version no longer possible
    assert w["qc"].post(f"{API}/sops/{sop['id']}/acknowledge", headers=w["hqc"]).status_code == 409
    assert w["qo"].get(f"{API}/sops-review-due?days=400").json() != []


# ------------------------------------------------------------------ complaints
def test_critical_complaint_holds_lot_and_needs_closed_deviation(q):
    w = q
    ds, hds = as_user(w["qa"].app, "disp1", ["DISPATCH_USER"])
    c = ds.post(f"{API}/complaints", headers=hds, json={"material_batch_id": w["lot"], "category": "ADVERSE_EVENT", "severity": "CRITICAL", "description": "Reaction reported after use", "reason": "c"})
    assert c.status_code == 201, c.text
    c = c.json()
    assert c["complaint_no"].startswith("CMP-") and c["hold_id"]
    s = db.new_session()
    assert s.execute(select(QualityHold).where(QualityHold.entity_type == "MATERIAL_BATCH", QualityHold.record_id == w["lot"], QualityHold.status == "OPEN", QualityHold.source == "COMPLAINT")).first()
    s.close()
    assert ds.post(f"{API}/complaints/{c['id']}/close", headers=hds, json={"password": PW, "conclusion": "x"}).status_code == 403
    assert w["qa"].post(f"{API}/complaints/{c['id']}/close", headers=w["hqa"], json={"password": PW, "conclusion": "done"}).status_code == 409        # not investigated
    assert w["qo"].post(f"{API}/complaints/{c['id']}/investigate", headers=w["hqo"], json={"investigation": "Retention samples retested - conforming", "reason": "i"}).status_code == 200
    dv = w["qo"].post(f"{API}/complaints/{c['id']}/deviation", headers=w["hqo"])
    assert dv.status_code == 201 and dv.json()["source"] == "COMPLAINT"
    assert w["qo"].post(f"{API}/complaints/{c['id']}/deviation", headers=w["hqo"]).status_code == 409
    blocked = w["qa"].post(f"{API}/complaints/{c['id']}/close", headers=w["hqa"], json={"password": PW, "conclusion": "Not product related"})
    assert blocked.status_code == 409 and blocked.json()["rule_id"] == "BR-CMP-001"
    d = dv.json()
    w["qo"].post(f"{API}/deviations/{d['id']}/investigate", headers=w["hqo"], json={"reason": "go"})
    w["qo"].patch(f"{API}/deviations/{d['id']}", headers=w["hqo"], json={"root_cause": "Patient-specific", "impact_assessment": "None", "no_capa_justification": "Not product related", "reason": "i"})
    w["qo"].post(f"{API}/deviations/{d['id']}/propose-capa", headers=w["hqo"], json={"reason": "x"})
    w["qo"].post(f"{API}/deviations/{d['id']}/submit-review", headers=w["hqo"], json={"reason": "x"})
    assert w["qa"].post(f"{API}/deviations/{d['id']}/close", headers=w["hqa"], json={"password": PW, "reason": "closed"}).status_code == 200
    ok = w["qa"].post(f"{API}/complaints/{c['id']}/close", headers=w["hqa"], json={"password": PW, "conclusion": "Not product related"})
    assert ok.status_code == 200 and ok.json()["status"] == "CLOSED"


# ------------------------------------------------------------------ IPC / reconciliation raise deviations (manufacturing world)
@pytest.fixture()
def mw(app):
    w = build_mfg_world(app)
    w["qa2"], w["hqa2"] = as_user(app, "qa_head2", ["QA_HEAD"])
    return w


def test_ipc_failure_raises_deviation_on_batch(mw):
    w = mw
    make_bom(w)
    b = new_batch(w)
    run_to_in_process(w, b)
    w["pr"].post(f"{API}/mfg/batches/{b['id']}/ipc", headers=w["hpr"], json={"stage": "Mix", "parameter": "pH", "value": 9, "lsl": 6.5, "usl": 7.5})
    d = w["qo"].get(f"{API}/deviations?source=IPC").json()
    assert d["total"] == 1 and d["items"][0]["entity_type"] == "MFG_BATCH" and d["items"][0]["record_id"] == b["id"] and d["items"][0]["severity"] == "MAJOR"
    w["pr"].post(f"{API}/mfg/batches/{b['id']}/ipc", headers=w["hpr"], json={"stage": "Mix", "parameter": "pH", "value": 9.1, "lsl": 6.5, "usl": 7.5})
    assert w["qo"].get(f"{API}/deviations?source=IPC").json()["total"] == 1


def test_reconciliation_deviation_blocks_output_lot_release(mw):
    w = mw
    make_bom(w)
    b = new_batch(w)
    run_to_in_process(w, b)
    finish_production(w, b, actual=98, consumed=9.5)
    ref = get(w, b)["reconciliation"]["deviation_ref"]
    assert w["pm"].post(f"{API}/mfg/batches/{b['id']}/reconciliation/approve", headers=w["hpm"], json={"password": PW, "reason": "reviewed"}).status_code == 200
    assert w["qa"].post(f"{API}/mfg/batches/{b['id']}/reconciliation/qa-approve", headers=w["hqa"], json={"password": PW, "justification": "weighing loss documented"}).status_code == 200
    o = w["pr"].post(f"{API}/mfg/batches/{b['id']}/output", headers=w["hpr"], json={"quarantine_location_id": w["qloc"]}).json()
    s = db.new_session()
    from app.models import MaterialBatch
    from app.services import qc as qc_svc
    lot = s.get(MaterialBatch, o["lot_id"])
    assert any("BR-DEV-001" in p and ref in p for p in qc_svc.release_readiness(s, lot))             # still open => lot cannot be released
    s.close()


# ------------------------------------------------------------------ recall (dispatch world)
@pytest.fixture()
def dw(app):
    w = build_dispatch_world(app)
    w["qa2"], w["hqa2"] = as_user(app, "qa_head2", ["QA_HEAD"])
    return w


def test_recall_derives_affected_customers_and_reconciles_returns(dw):
    w = dw
    d = finish_dispatch(w, qty=30)
    rc = w["qa"].post(f"{API}/recalls", headers=w["hqa"], json={"material_batch_id": w["fg_lot"], "recall_class": "II", "password": "bad", "reason": "Potency complaint"})
    assert rc.status_code == 401
    assert w["qo"].post(f"{API}/recalls", headers=w["hqo"], json={"material_batch_id": w["fg_lot"], "password": PW, "reason": "x"}).status_code == 403
    rc = w["qa"].post(f"{API}/recalls", headers=w["hqa"], json={"material_batch_id": w["fg_lot"], "recall_class": "II", "password": PW, "reason": "Potency complaint"})
    assert rc.status_code == 201, rc.text
    rc = rc.json()
    assert rc["recall_no"].startswith("RCL-") and rc["status"] == "INITIATED" and len(rc["lines"]) == 1
    line = rc["lines"][0]
    assert line["dispatch_no"] == d["dispatch_no"] and line["quantity_dispatched"] == 30.0 and line["customer"] == "Hospital A"
    # stock is frozen: lot on hold -> no further dispatch (BR-HOLD-003)
    d2 = w["ds"].post(f"{API}/dispatches", headers=w["hds"], json={"customer_id": w["cust"], "reason": "o", "lines": [{"material_batch_id": w["fg_lot"], "location_id": w["qloc"], "quantity": 5}]}).json()
    v = w["ds"].post(f"{API}/dispatches/{d2['id']}/validate", headers=w["hds"])
    assert v.status_code == 409 and v.json()["rule_id"] == "BR-HOLD-003"
    # steps must follow: return before notification is refused; close before notification is refused
    assert w["qo"].post(f"{API}/recalls/{rc['id']}/lines/{line['id']}/return", headers=w["hqo"], json={"returned": 10, "location_id": w["rloc"], "reason": "x"}).status_code == 409
    assert w["qa"].post(f"{API}/recalls/{rc['id']}/close", headers=w["hqa"], json={"password": PW, "summary": "closing too early"}).status_code == 409
    n = w["qo"].post(f"{API}/recalls/{rc['id']}/lines/{line['id']}/notify", headers=w["hqo"], json={"response": "Acknowledged by pharmacy", "reason": "x"})
    assert n.status_code == 200 and n.json()["status"] == "IN_PROGRESS"
    bad = w["qo"].post(f"{API}/recalls/{rc['id']}/lines/{line['id']}/return", headers=w["hqo"], json={"returned": 40, "location_id": w["rloc"], "reason": "x"})
    assert bad.status_code == 409 and bad.json()["rule_id"] == "BR-RCL-002"
    wrongloc = w["qo"].post(f"{API}/recalls/{rc['id']}/lines/{line['id']}/return", headers=w["hqo"], json={"returned": 10, "location_id": w["aloc"], "reason": "x"})
    assert wrongloc.status_code == 409 and wrongloc.json()["rule_id"] == "BR-RCL-003"
    r = w["qo"].post(f"{API}/recalls/{rc['id']}/lines/{line['id']}/return", headers=w["hqo"], json={"returned": 20, "unrecoverable": 5, "location_id": w["rloc"], "reason": "received back"})
    assert r.status_code == 200
    rec = r.json()["reconciliation"]
    assert rec == {"dispatched": 30.0, "returned": 20.0, "unrecoverable": 5.0, "outstanding": 5.0, "recovery_pct": 66.67}
    assert w["wh1"].get(f"{API}/lots/{w['fg_lot']}").json()["on_hand"] == 67.0 + 20.0                  # returned stock is back in the ledger (rejected area)
    cl = w["qa"].post(f"{API}/recalls/{rc['id']}/close", headers=w["hqa"], json={"password": PW, "summary": "20 returned, 5 unrecoverable, 5 outstanding (used)"})
    assert cl.status_code == 200 and cl.json()["status"] == "CLOSED" and cl.json()["close_signature_id"]
    assert w["qa"].get(f"{API}/trace/lot/{w['fg_lot']}?direction=forward").status_code == 200


def test_quality_endpoints_are_permissioned_and_listed(q):
    w = q
    for path in ("deviations", "capas", "change-controls", "risk-assessments", "sops", "complaints", "recalls"):
        assert w["qa"].get(f"{API}/{path}").status_code == 200
    assert w["pr"].get(f"{API}/capas").status_code == 200 and w["pr"].post(f"{API}/capas", headers=w["hpr"], json={}).status_code in (403, 422)
    assert w["pr"].post(f"{API}/change-controls", headers=w["hpr"], json={"title": "x y z", "description": "d"}).status_code == 403
