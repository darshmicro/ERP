"""Phase 11a: environmental monitoring."""
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.core import db
from app.models import Deviation, EMResultAmendment, EMSample
from tests.conftest import PW
from tests.helpers import as_user, bootstrap_basics, raw

pytestmark = pytest.mark.filterwarnings("ignore")
API = "/api/v1/em"


@pytest.fixture()
def w(app):
    bootstrap_basics(app)
    w = {}
    w["qo"], w["hqo"] = as_user(app, "qa_off", ["QA_OFFICER"])
    w["qa"], w["hqa"] = as_user(app, "qa_head", ["QA_HEAD"])
    w["qc"], w["hqc"] = as_user(app, "qc_an", ["QC_ANALYST"])
    w["both"], w["hboth"] = as_user(app, "qa_qc", ["QA_OFFICER", "QC_ANALYST"])
    return w


def approved_limits(w, **over):
    lim = {"grade": "B", "sample_type": "VIABLE_AIR", "state": "OPERATIONAL", "alert_high": 5, "action_high": 10, "unit": "cfu/m3", **over}
    r = w["qo"].post(f"{API}/limit-sets", headers=w["hqo"], json={"title": "Site limits", "limits": [lim], "reason": "new"})
    assert r.status_code == 201, r.text
    ls = r.json()
    assert w["qo"].post(f"{API}/limit-sets/{ls['id']}/submit", headers=w["hqo"]).status_code == 200
    a = w["qa"].post(f"{API}/limit-sets/{ls['id']}/approve", headers=w["hqa"], json={"password": PW, "reason": "approved"})
    assert a.status_code == 200, a.text
    return a.json()


def location(w, grade="B", code="EML-B1"):
    r = w["qo"].post(f"{API}/locations", headers=w["hqo"], json={"code": code, "name": "Filling room", "grade": grade, "reason": "new"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def sample(w, loc, **kw):
    r = w["qc"].post(f"{API}/samples", headers=w["hqc"], json={"em_location_id": loc, "sample_type": "VIABLE_AIR", "reason": "monitoring", **kw})
    assert r.status_code == 201, r.text
    return r.json()


def result(w, sid, value, who="qc", **kw):
    return w[who].post(f"{API}/samples/{sid}/result", headers=w["h" + who], json={"value": value, "reason": "read plates", **kw})


def test_limit_set_is_a_controlled_version(w):
    ls = approved_limits(w)
    assert ls["status"] == "APPROVED" and ls["limitset_no"].startswith("EML-")
    # approved content is immutable
    r = w["qo"].post(f"{API}/limit-sets/{ls['id']}/limits", headers=w["hqo"], json={"grade": "C", "sample_type": "VIABLE_AIR", "action_high": 100})
    assert r.status_code in (409, 422)
    # author cannot approve own version (SOD-36)
    r = w["qo"].post(f"{API}/limit-sets", headers=w["hqo"], json={"title": "Second set", "limits": [{"grade": "A", "sample_type": "VIABLE_AIR", "action_high": 0}], "reason": "n"})
    assert r.status_code == 201, r.text
    r = r.json()
    w["qo"].post(f"{API}/limit-sets/{r['id']}/submit", headers=w["hqo"])
    assert w["qo"].post(f"{API}/limit-sets/{r['id']}/approve", headers=w["hqo"], json={"password": PW, "reason": "self"}).status_code == 403   # QA officer lacks approve
    # new version supersedes on approval
    nv = w["qo"].post(f"{API}/limit-sets/{ls['id']}/new-version", headers=w["hqo"], json={"reason": "tighten alert"})
    assert nv.status_code == 201 and nv.json()["version_no"] == 2 and len(nv.json()["limits"]) == 1


def test_reference_limits_load_as_draft_requiring_approval(w):
    r = w["qo"].post(f"{API}/limit-sets/load-reference", headers=w["hqo"], json={"reason": "start from Annex 1 reference"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "DRAFT" and len(body["limits"]) >= 25
    # A DRAFT set is not "in force": no result can be judged against it
    loc = location(w, "B")
    s = sample(w, loc)
    assert result(w, s["id"], 3).status_code == 409


def test_result_is_judged_against_the_limit_set_and_action_raises_deviation(w):
    approved_limits(w)
    loc = location(w, "B")
    ok = result(w, sample(w, loc)["id"], 3)
    assert ok.status_code == 200 and ok.json()["outcome"] == "WITHIN" and ok.json()["status"] == "RESULT_ENTERED"
    al = result(w, sample(w, loc)["id"], 7)
    assert al.json()["outcome"] == "ALERT" and al.json()["deviation_id"] is None
    ac = result(w, sample(w, loc)["id"], 12, isolates=[{"organism": "Bacillus cereus", "gram_stain": "positive", "cfu_count": 12}])
    assert ac.status_code == 200, ac.text
    body = ac.json()
    assert body["outcome"] == "ACTION" and body["deviation_id"] and len(body["isolates"]) == 1
    s = db.new_session()
    d = s.get(Deviation, body["deviation_id"])
    assert d.source == "EM" and d.severity == "CRITICAL" and d.title.startswith("EM action limit exceeded")   # grade B excursion
    s.close()
    # the result cannot be entered twice
    assert result(w, body["id"], 1).status_code == 409
    # limits are snapshotted on the sample
    assert body["alert_high"] == 5.0 and body["action_high"] == 10.0 and body["limit_set_id"]


def test_amendment_keeps_original_and_review_locks_the_result(w):
    approved_limits(w)
    loc = location(w, "B")
    s = sample(w, loc)
    result(w, s["id"], 12)
    am = w["qc"].post(f"{API}/samples/{s['id']}/amend", headers=w["hqc"], json={"value": 2, "reason": "plate miscounted"})
    assert am.status_code == 200 and am.json()["result_value"] == 2.0 and am.json()["outcome"] == "WITHIN"
    assert len(am.json()["amendments"]) == 1 and am.json()["amendments"][0]["old_value"] == 12.0
    assert w["qc"].post(f"{API}/samples/{s['id']}/amend", headers=w["hqc"], json={"value": 3}).status_code == 422    # reason required
    # the appended amendment cannot be altered, even by raw SQL
    with pytest.raises(Exception):
        raw("UPDATE em_result_amendment SET reason = 'x'")
    # QA review is signed; wrong password rejected; analyst has no review right
    assert w["qc"].post(f"{API}/samples/{s['id']}/review", headers=w["hqc"], json={"password": PW, "reason": "ok"}).status_code == 403
    assert w["qa"].post(f"{API}/samples/{s['id']}/review", headers=w["hqa"], json={"password": "wrong", "reason": "ok"}).status_code == 401
    rv = w["qo"].post(f"{API}/samples/{s['id']}/review", headers=w["hqo"], json={"password": PW, "reason": "plates verified", "comment": "OK"})
    assert rv.status_code == 200 and rv.json()["status"] == "REVIEWED" and rv.json()["review_signature_id"]
    # after review the result is locked
    assert w["qc"].post(f"{API}/samples/{s['id']}/amend", headers=w["hqc"], json={"value": 1, "reason": "late"}).status_code == 409
    sess = db.new_session()
    assert sess.execute(select(EMSample.status).where(EMSample.id == s["id"])).scalar() == "REVIEWED"
    assert len(sess.execute(select(EMResultAmendment)).scalars().all()) == 1
    sess.close()


def test_entering_person_cannot_review_own_result(w):
    approved_limits(w)
    s = sample(w, location(w, "B"))
    assert result(w, s["id"], 1, who="both").status_code == 200
    r = w["both"].post(f"{API}/samples/{s['id']}/review", headers=w["hboth"], json={"password": PW, "reason": "self review"})
    assert r.status_code in (403, 409) and "SOD-37" in r.text


def test_schedule_flags_due_and_overdue_points(w):
    approved_limits(w)
    loc = location(w, "B")
    r = w["qo"].post(f"{API}/plans", headers=w["hqo"], json={"em_location_id": loc, "sample_type": "VIABLE_AIR", "frequency_days": 7, "start_date": str(date.today() - timedelta(days=3)), "reason": "programme"})
    assert r.status_code == 201, r.text
    plan = r.json()["id"]
    due = w["qc"].get(f"{API}/schedule").json()
    assert len(due) == 1 and due[0]["overdue"] is True
    sample(w, loc, plan_id=plan)
    assert w["qc"].get(f"{API}/schedule", params={"horizon_days": 3}).json() == []
    assert len(w["qc"].get(f"{API}/schedule", params={"horizon_days": 10}).json()) == 1       # next due in 7 days
    # a duplicate plan is refused
    assert w["qo"].post(f"{API}/plans", headers=w["hqo"], json={"em_location_id": loc, "sample_type": "VIABLE_AIR", "frequency_days": 7, "start_date": str(date.today()), "reason": "dup"}).status_code == 409


def test_trend_and_excursion_listing(w):
    approved_limits(w)
    loc = location(w, "B")
    for v in (1, 2, 1, 3, 2, 12):
        result(w, sample(w, loc)["id"], v)
    t = w["qc"].get(f"{API}/trend", params={"em_location_id": loc, "sample_type": "VIABLE_AIR"}).json()
    assert t["n"] == 6 and t["actions"] == 1 and t["stats"]["max"] == 12.0
    ex = w["qc"].get(f"{API}/excursions").json()
    assert len(ex) == 1 and ex[0]["outcome"] == "ACTION"


def test_non_qc_roles_cannot_enter_or_approve(w, app):
    approved_limits(w)
    s = sample(w, location(w, "B"))
    pr, hpr = as_user(app, "prod1", ["PRODUCTION_USER"])
    assert pr.post(f"{API}/samples/{s['id']}/result", headers=hpr, json={"value": 1, "reason": "x"}).status_code == 403
    assert pr.post(f"{API}/limit-sets", headers=hpr, json={"title": "x", "reason": "x"}).status_code == 403
    assert pr.get(f"{API}/samples").status_code == 200       # production can see and take samples
    assert pr.post(f"{API}/samples", headers=hpr, json={"em_location_id": s["em_location_id"], "sample_type": "SETTLE_PLATE", "reason": "operator sample"}).status_code == 201
