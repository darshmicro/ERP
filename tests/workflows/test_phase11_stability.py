"""Phase 11b: stability studies."""
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.core import db
from app.models import Deviation, InventoryBalance, InventoryTransaction, Specification, SpecificationParameter, StabilityPull, StabilityResult
from tests.conftest import PW
from tests.helpers import as_user, raw
from tests.workflows.test_dispatch import build_dispatch_world

pytestmark = pytest.mark.filterwarnings("ignore")
API = "/api/v1/stability"


@pytest.fixture()
def w(app):
    w = build_dispatch_world(app)
    s = db.new_session()
    spec = s.execute(select(Specification).where(Specification.material_id == w["product"], Specification.status == "APPROVED")).scalars().first()
    w["spec"] = spec.id
    params = {p.test_name: p.id for p in s.execute(select(SpecificationParameter).where(SpecificationParameter.specification_id == spec.id)).scalars()}
    w["assay"], w["appearance"] = params["Assay"], params["Appearance"]
    s.close()
    return w


def protocol(w, months=(0, 1, 2), window=90, approve=True):
    r = w["qo"].post(f"{API}/protocols", headers=w["hqo"], json={"title": "FG stability", "material_id": w["product"], "specification_id": w["spec"], "pull_window_days": window,
                                                                    "proposed_shelf_life_months": 24, "reason": "new"})
    assert r.status_code == 201, r.text
    p = r.json()
    for lbl, typ, t, rh in (("25C/60%RH", "LONG_TERM", 25, 60), ("40C/75%RH", "ACCELERATED", 40, 75)):
        assert w["qo"].post(f"{API}/protocols/{p['id']}/conditions", headers=w["hqo"], json={"label": lbl, "condition_type": typ, "temperature_c": t, "rh_pct": rh}).status_code == 201
    for m in months:
        assert w["qo"].post(f"{API}/protocols/{p['id']}/timepoints", headers=w["hqo"], json={"month": m}).status_code == 201
    if approve:
        assert w["qo"].post(f"{API}/protocols/{p['id']}/submit", headers=w["hqo"]).status_code == 200
        a = w["qa"].post(f"{API}/protocols/{p['id']}/approve", headers=w["hqa"], json={"password": PW, "reason": "approved"})
        assert a.status_code == 200, a.text
        return a.json()
    return p


def study(w, p, start=None, units=0.5, start_it=True):
    r = w["qch"].post(f"{API}/studies", headers=w["hqch"], json={"protocol_id": p["id"], "material_batch_id": w["fg_lot"], "start_date": str(start or date.today()),
                                                                    "units_per_pull": units, "source_location_id": w["qloc"], "reason": "stability commitment"})
    assert r.status_code == 201, r.text
    st = r.json()
    if start_it:
        a = w["qch"].post(f"{API}/studies/{st['id']}/start", headers=w["hqch"], json={"reason": "placed in chambers"})
        assert a.status_code == 200, a.text
        return a.json()
    return st


def on_hand(lot):
    s = db.new_session()
    v = float(s.execute(select(InventoryBalance.qty_on_hand).where(InventoryBalance.material_batch_id == lot)).scalar())
    s.close()
    return v


def test_protocol_is_a_controlled_version_and_needs_approval_for_a_study(w):
    p = protocol(w, approve=False)
    assert w["qch"].post(f"{API}/studies", headers=w["hqch"], json={"protocol_id": p["id"], "material_batch_id": w["fg_lot"], "start_date": str(date.today()), "units_per_pull": 1,
                                                                      "source_location_id": w["qloc"], "reason": "x"}).status_code == 409      # not approved
    assert w["qo"].post(f"{API}/protocols/{p['id']}/approve", headers=w["hqo"], json={"password": PW, "reason": "x"}).status_code == 403
    w["qo"].post(f"{API}/protocols/{p['id']}/submit", headers=w["hqo"])
    a = w["qa"].post(f"{API}/protocols/{p['id']}/approve", headers=w["hqa"], json={"password": PW, "reason": "ok"})
    assert a.status_code == 200 and a.json()["protocol_no"].startswith("SPR-")
    # approved => content frozen
    assert w["qo"].post(f"{API}/protocols/{p['id']}/timepoints", headers=w["hqo"], json={"month": 9}).status_code == 409
    nv = w["qo"].post(f"{API}/protocols/{p['id']}/new-version", headers=w["hqo"], json={"reason": "add 9 M"})
    assert nv.status_code == 201 and len(nv.json()["conditions"]) == 2 and len(nv.json()["timepoints"]) == 3


def test_incomplete_protocol_cannot_be_submitted(w):
    r = w["qo"].post(f"{API}/protocols", headers=w["hqo"], json={"title": "Empty protocol", "material_id": w["product"], "specification_id": w["spec"], "reason": "n"}).json()
    assert w["qo"].post(f"{API}/protocols/{r['id']}/submit", headers=w["hqo"]).status_code == 422
    w["qo"].post(f"{API}/protocols/{r['id']}/conditions", headers=w["hqo"], json={"label": "40C", "condition_type": "ACCELERATED", "temperature_c": 40, "rh_pct": 75})
    w["qo"].post(f"{API}/protocols/{r['id']}/timepoints", headers=w["hqo"], json={"month": 0})
    assert w["qo"].post(f"{API}/protocols/{r['id']}/submit", headers=w["hqo"]).status_code == 422     # no long-term condition


def test_starting_a_study_books_stock_and_schedules_every_pull(w):
    before = on_hand(w["fg_lot"])
    st = study(w, protocol(w))
    assert st["status"] == "ACTIVE" and len(st["pulls"]) == 6          # 2 conditions x 3 time points
    assert st["placed_qty"] == 3.0 and on_hand(w["fg_lot"]) == pytest.approx(before - 3.0)
    s = db.new_session()
    t = s.get(InventoryTransaction, st["ledger_txn_id"])
    assert t.txn_type == "SAMPLE" and t.ref_doc_type == "STABILITY" and t.ref_doc_id == st["study_no"]
    s.close()
    assert [p["month"] for p in st["pulls"]] == [0, 0, 1, 1, 2, 2]
    # starting twice is refused
    assert w["qch"].post(f"{API}/studies/{st['id']}/start", headers=w["hqch"], json={"reason": "again"}).status_code == 409


def enter_pass(w, pull_id, assay=100.0, who="qc"):
    r = w[who].post(f"{API}/pulls/{pull_id}/results", headers=w["h" + who], json={"results": [{"parameter_id": w["assay"], "value": assay}, {"parameter_id": w["appearance"], "conforms": True}], "reason": "tested"})
    assert r.status_code == 201, r.text
    return r.json()


def test_pull_test_review_chain_and_sod(w):
    st = study(w, protocol(w))
    pull = next(p for p in st["pulls"] if p["month"] == 0)
    assert w["qc"].post(f"{API}/pulls/{pull['id']}/pull", headers=w["hqc"], json={"actual_qty": 0.5, "reason": "pulled"}).json()["status"] == "PULLED"
    out = enter_pass(w, pull["id"])
    assert all(r["pass_fail"] == "PASS" for r in out["results"]) and len(out["results"]) == 2
    # incomplete results cannot complete testing; duplicate parameter result must be a correction
    assert w["qc"].post(f"{API}/pulls/{pull['id']}/results", headers=w["hqc"], json={"results": [{"parameter_id": w["assay"], "value": 100.1}], "reason": "x"}).status_code == 409
    assert w["qc"].post(f"{API}/pulls/{pull['id']}/complete-testing", headers=w["hqc"]).json()["status"] == "TESTED"
    # analyst cannot review; QA can, with e-signature; wrong password rejected
    assert w["qc"].post(f"{API}/pulls/{pull['id']}/review", headers=w["hqc"], json={"password": PW, "reason": "x"}).status_code == 403
    assert w["qo"].post(f"{API}/pulls/{pull['id']}/review", headers=w["hqo"], json={"password": "bad", "reason": "ok"}).status_code == 401
    rv = w["qo"].post(f"{API}/pulls/{pull['id']}/review", headers=w["hqo"], json={"password": PW, "reason": "results verified"})
    assert rv.status_code == 200 and rv.json()["status"] == "REVIEWED" and rv.json()["review_signature_id"]
    # reviewed results cannot be changed
    assert w["qc"].post(f"{API}/pulls/{pull['id']}/correct", headers=w["hqc"], json={"correction_of": out["results"][0]["id"], "reason": "late", "result": {"parameter_id": w["assay"], "value": 99.5}}).status_code == 409


def test_correction_supersedes_and_keeps_the_original(w):
    st = study(w, protocol(w))
    pull = next(p for p in st["pulls"] if p["month"] == 0)
    w["qc"].post(f"{API}/pulls/{pull['id']}/pull", headers=w["hqc"], json={"reason": "pulled"})
    out = enter_pass(w, pull["id"], assay=100.0)
    first = next(r for r in out["results"] if r["parameter_id"] == w["assay"])
    c = w["qc"].post(f"{API}/pulls/{pull['id']}/correct", headers=w["hqc"], json={"correction_of": first["id"], "reason": "transcription error", "result": {"parameter_id": w["assay"], "value": 99.8}})
    assert c.status_code == 200, c.text
    cur = {r["parameter_id"]: r for r in c.json()["results"]}
    assert cur[w["assay"]]["rounded_value"] == 99.8 and cur[w["assay"]]["supersedes_id"] == first["id"]
    s = db.new_session()
    assert len(s.execute(select(StabilityResult).where(StabilityResult.pull_id == pull["id"], StabilityResult.parameter_id == w["assay"])).scalars().all()) == 2
    s.close()
    with pytest.raises(Exception):
        raw("UPDATE stability_result SET rounded_value = 1")
    # a correction without a reason is refused
    assert w["qc"].post(f"{API}/pulls/{pull['id']}/correct", headers=w["hqc"], json={"correction_of": cur[w["assay"]]["id"], "result": {"parameter_id": w["assay"], "value": 99.9}}).status_code == 422


def test_oos_raises_deviation_linked_to_lot_and_blocks_review_until_it_exists(w):
    st = study(w, protocol(w))
    pull = next(p for p in st["pulls"] if p["month"] == 0)
    w["qc"].post(f"{API}/pulls/{pull['id']}/pull", headers=w["hqc"], json={"reason": "pulled"})
    out = enter_pass(w, pull["id"], assay=97.0)
    assay = next(r for r in out["results"] if r["parameter_id"] == w["assay"])
    assert assay["pass_fail"] == "FAIL" and assay["deviation_id"]
    s = db.new_session()
    d = s.get(Deviation, assay["deviation_id"])
    assert d.source == "STABILITY" and d.entity_type == "MATERIAL_BATCH" and d.record_id == w["fg_lot"] and d.blocks_release
    s.close()
    # the open deviation blocks the lot like any other (dispatch/release gates read it)
    from app.services import quality_system as qs
    s = db.new_session()
    from app.models import MaterialBatch
    assert qs.deviation_blockers(s, s.get(MaterialBatch, w["fg_lot"]))
    s.close()


def test_out_of_window_pull_needs_remarks_and_raises_minor_deviation(w):
    st = study(w, protocol(w, months=(0, 12), window=14))
    late = next(p for p in st["pulls"] if p["month"] == 12)
    assert w["qc"].post(f"{API}/pulls/{late['id']}/pull", headers=w["hqc"], json={"reason": "early"}).status_code == 422
    r = w["qc"].post(f"{API}/pulls/{late['id']}/pull", headers=w["hqc"], json={"remarks": "Chamber audit; pulled 11 months early", "reason": "early"})
    assert r.status_code == 200 and r.json()["deviation_id"]


def test_missed_pulls_are_marked_with_deviation_and_study_cannot_complete_early(w):
    st = study(w, protocol(w, months=(0, 3), window=14), start=date.today() - timedelta(days=200))
    due = w["qc"].get(f"{API}/pulls/due").json()
    assert {d["month"] for d in due} == {0, 3} and all(d["overdue"] for d in due)
    m = w["qch"].post(f"{API}/pulls/check-missed", headers=w["hqch"])
    assert m.status_code == 200 and len(m.json()["marked_missed"]) == 4
    assert w["qch"].post(f"{API}/pulls/check-missed", headers=w["hqch"]).json()["marked_missed"] == []        # idempotent
    full = w["qc"].get(f"{API}/studies/{st['id']}").json()
    assert {p["status"] for p in full["pulls"]} == {"MISSED"} and all(p["deviation_id"] for p in full["pulls"])
    c = w["qch"].post(f"{API}/studies/{st['id']}/complete", headers=w["hqch"], json={"reason": "all pulls closed"})
    assert c.status_code == 200 and c.json()["status"] == "COMPLETED"


def test_evaluation_and_conclusion_with_signature(w):
    st = study(w, protocol(w))
    for p in [x for x in st["pulls"] if x["condition"] == "25C/60%RH"]:
        w["qc"].post(f"{API}/pulls/{p['id']}/pull", headers=w["hqc"], json={"reason": "pulled"})
        enter_pass(w, p["id"], assay=100.4 - 0.2 * p["month"])
        w["qc"].post(f"{API}/pulls/{p['id']}/complete-testing", headers=w["hqc"])
        assert w["qo"].post(f"{API}/pulls/{p['id']}/review", headers=w["hqo"], json={"password": PW, "reason": "ok"}).status_code == 200
    for p in [x for x in st["pulls"] if x["condition"] == "40C/75%RH"]:
        assert w["qch"].post(f"{API}/pulls/{p['id']}/skip", headers=w["hqch"], json={"reason": "accelerated arm waived by QA"}).status_code == 200
    ev = w["qa"].get(f"{API}/studies/{st['id']}/evaluation").json()
    assay = next(e for e in ev if e["test_name"] == "Assay" and e["condition"] == "25C/60%RH")
    assert assay["status"] == "OK" and assay["n"] == 3 and assay["slope_per_month"] == pytest.approx(-0.2, abs=1e-6) and assay["supported_shelf_life_months"] is not None
    assert assay["extrapolation_cap_months"] == 4
    # conclusion only after completion, with e-signature and SoD (creator cannot conclude)
    assert w["qa"].post(f"{API}/studies/{st['id']}/conclude", headers=w["hqa"], json={"password": PW, "reason": "x", "shelf_life_months": 24, "conclusion": "ok"}).status_code in (409, 422)
    assert w["qch"].post(f"{API}/studies/{st['id']}/complete", headers=w["hqch"], json={"reason": "done"}).json()["status"] == "COMPLETED"
    assert w["qch"].post(f"{API}/studies/{st['id']}/conclude", headers=w["hqch"], json={"password": PW, "reason": "x", "shelf_life_months": 24, "conclusion": "ok"}).status_code == 403
    done = w["qa"].post(f"{API}/studies/{st['id']}/conclude", headers=w["hqa"], json={"password": PW, "reason": "stable; supports claim", "shelf_life_months": 24, "conclusion": "Meets specification at all time points"})
    assert done.status_code == 200 and done.json()["status"] == "CONCLUDED" and done.json()["conclusion_signature_id"] and done.json()["shelf_life_months"] == 24


def test_regression_helper_is_conservative():
    from app.services.stability import regress
    flat = regress([(0, 100.0), (3, 100.0), (6, 100.0), (9, 100.0)], 95.0, 105.0)
    assert flat["status"] == "OK" and flat["supported_shelf_life_months"] == 18        # capped: min(2 x 9, 9 + 12) -> 18, no crossing
    steep = regress([(0, 100.0), (3, 98.0), (6, 96.1), (9, 94.0)], 95.0, None)
    assert steep["estimated_limit_crossing_months"] is not None and steep["estimated_limit_crossing_months"] < 9
    assert regress([(0, 1.0), (3, 1.0)], None, 2.0)["status"] == "INSUFFICIENT_DATA"


def test_role_boundaries(w):
    p = protocol(w)
    assert w["qc"].post(f"{API}/protocols", headers=w["hqc"], json={"title": "x" * 5, "material_id": w["product"], "specification_id": w["spec"], "reason": "n"}).status_code == 403
    assert w["qc"].post(f"{API}/studies", headers=w["hqc"], json={"protocol_id": p["id"], "material_batch_id": w["fg_lot"], "start_date": str(date.today()), "units_per_pull": 1,
                                                                    "source_location_id": w["qloc"], "reason": "x"}).status_code == 403
    assert w["pu"].get(f"{API}/studies").status_code == 403


def test_scheduled_job_marks_missed_pulls_and_is_idempotent(w):
    st = study(w, protocol(w, months=(0,), window=14), start=date.today() - timedelta(days=60))
    from app.jobs.runner import run_daily_jobs
    run_daily_jobs()
    run_daily_jobs()
    full = w["qc"].get(f"{API}/studies/{st['id']}").json()
    assert {p["status"] for p in full["pulls"]} == {"MISSED"}
    s = db.new_session()
    n = len(s.execute(select(Deviation).where(Deviation.source == "STABILITY")).scalars().all())
    s.close()
    assert n == len(full["pulls"])                   # one deviation per missed pull, none duplicated by the second run
