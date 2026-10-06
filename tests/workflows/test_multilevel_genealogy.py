"""SFG -> FG production: a released semi-finished lot is a legitimate input of a finished-goods batch, and the genealogy spans both levels."""
from datetime import date

import pytest

from tests.conftest import PW
from tests.helpers import as_user, assign, build_qc_world, release_lot, submit_pass_results, take_sample
from tests.workflows.test_manufacturing import API, complete_steps

pytestmark = pytest.mark.filterwarnings("ignore")


def product(w, name, type_id, ad, ha):
    p = w["qc"].post(f"{API}/materials", headers=w["hqc"], json={"name": name, "type_id": type_id, "base_unit_id": w["ids"]["kg"], "shelf_life_days": 365, "reason": "new"}).json()["id"]
    w["qa"].post(f"{API}/materials/{p}/approve", headers=w["hqa"], json={"password": PW, "reason": "ok"})
    w["qa"].post(f"{API}/materials/{p}/activate", headers=w["hqa"], json={"password": PW, "reason": "ok"})
    sp = w["qc"].post(f"{API}/specifications", headers=w["hqc"], json={"material_id": p, "reason": "x"}).json()["id"]
    w["qc"].post(f"{API}/specifications/{sp}/parameters", headers=w["hqc"], json={"test_name": "Assay", "lsl": 99, "usl": 101, "unit": "%", "decimal_places": 1})
    w["qc"].post(f"{API}/specifications/{sp}/parameters", headers=w["hqc"], json={"test_name": "Appearance", "spec_type": "PASS_FAIL", "acceptance_criteria": "Clear"})
    w["qc"].post(f"{API}/specifications/{sp}/submit", headers=w["hqc"])
    assert w["qa"].post(f"{API}/specifications/{sp}/approve", headers=w["hqa"], json={"password": PW, "reason": "ok"}).status_code == 200
    return p


def bom(w, product_id, component, qty, batch_size=100):
    b = w["pr"].post(f"{API}/boms", headers=w["hpr"], json={"product_material_id": product_id, "batch_size": batch_size, "unit_id": w["ids"]["kg"], "yield_min_pct": 90, "yield_max_pct": 105,
                                                           "lines": [{"material_id": component, "quantity": qty}], "steps": [{"instruction": "Process", "requires_verification": True}, {"instruction": "Fill", "requires_verification": False}], "reason": "bom"})
    assert b.status_code == 201, b.text
    w["pr"].post(f"{API}/boms/{b.json()['id']}/submit", headers=w["hpr"])
    assert w["qa"].post(f"{API}/boms/{b.json()['id']}/approve", headers=w["hqa"], json={"password": PW, "reason": "ok"}).status_code == 200


def release_lot_of(w, lot_id, loc):
    w["lot"] = lot_id
    saved, w["qloc"] = w["qloc"], loc
    sm = take_sample(w, qty=1, containers=1)
    w["qloc"] = saved
    assign(w, sm["id"])
    submit_pass_results(w, sm["id"])
    assert w["qc"].post(f"{API}/lots/{lot_id}/submit-release", headers=w["hqc"]).status_code == 200
    for who, h in (("qch", "hqch"), ("qo", "hqo"), ("qa", "hqa")):
        assert w[who].post(f"{API}/lots/{lot_id}/release-decision", headers=w[h], json={"decision": "APPROVE", "password": PW, "comment": "ok"}).status_code == 200


def run_batch(w, product_id, component_lot, loc, qty=100):
    b = w["pr"].post(f"{API}/mfg/batches", headers=w["hpr"], json={"product_material_id": product_id, "planned_qty": qty, "reason": "plan"}).json()
    bm = b["materials"][0]
    return b, bm


def test_fg_batch_consumes_a_released_sfg_lot_and_trace_spans_both_levels(app):
    w = build_qc_world(app)
    w["pr"], w["hpr"] = as_user(app, "prod1", ["PRODUCTION_USER"])
    w["pm"], w["hpm"] = as_user(app, "prod_mgr", ["PRODUCTION_MANAGER"])
    ad, ha = as_user(app, "admin_b", [])
    sfg_t = ad.post(f"{API}/material-types", headers=ha, json={"code": "SFG", "name": "Semi-finished", "reason": "s"}).json()["id"]
    fg_t = ad.post(f"{API}/material-types", headers=ha, json={"code": "FG", "name": "Finished", "reason": "s"}).json()["id"]
    rm_lot = w["lot"]
    release_lot(w)                                                    # raw material released (sits in the quarantine-type location after release)
    sfg, fg = product(w, "Bulk antiserum", sfg_t, ad, ha), product(w, "Antiserum vials", fg_t, ad, ha)
    bom(w, sfg, w["material"], 10)                                    # SFG <- raw material
    bom(w, fg, sfg, 50)                                               # FG  <- SFG
    # --- SFG batch from the released raw-material lot
    b1, bm1 = run_batch(w, sfg, rm_lot, w["qloc"])
    assert w["wh1"].post(f"{API}/mfg/batches/{b1['id']}/issue", headers=w["hwh1"], json={"batch_material_id": bm1["id"], "material_batch_id": rm_lot, "location_id": w["qloc"], "quantity": bm1["required_qty"], "reason": "i"}).status_code == 201
    assert w["pr"].post(f"{API}/mfg/batches/{b1['id']}/start", headers=w["hpr"], json={"password": PW, "reason": "clear"}).status_code == 200
    complete_steps(w, b1)
    assert w["pr"].post(f"{API}/mfg/batches/{b1['id']}/complete", headers=w["hpr"], json={"actual_qty": 98}).status_code == 200
    w["pr"].put(f"{API}/mfg/batches/{b1['id']}/consumption", headers=w["hpr"], json={"entries": [{"batch_material_id": bm1["id"], "consumed": 10}]})
    w["pr"].post(f"{API}/mfg/batches/{b1['id']}/reconcile", headers=w["hpr"])
    w["pm"].post(f"{API}/mfg/batches/{b1['id']}/reconciliation/approve", headers=w["hpm"], json={"password": PW, "reason": "ok"})
    out = w["pr"].post(f"{API}/mfg/batches/{b1['id']}/output", headers=w["hpr"], json={"quarantine_location_id": w["qloc2"]})
    assert out.status_code == 201, out.text
    sfg_lot = out.json()["lot_id"]
    # --- an unreleased SFG lot cannot feed the FG batch
    b2, bm2 = run_batch(w, fg, sfg_lot, w["qloc2"], qty=100)
    early = w["wh1"].post(f"{API}/mfg/batches/{b2['id']}/issue", headers=w["hwh1"], json={"batch_material_id": bm2["id"], "material_batch_id": sfg_lot, "location_id": w["qloc2"], "quantity": 1, "reason": "i"})
    assert early.status_code == 409 and early.json()["rule_id"] == "BR-ISS-001"
    # --- release the SFG lot, then issue it to the FG batch
    release_lot_of(w, sfg_lot, w["qloc2"])
    assert w["wh1"].get(f"{API}/lots/{sfg_lot}").json()["disposition"] == "APPROVED"
    ok = w["wh1"].post(f"{API}/mfg/batches/{b2['id']}/issue", headers=w["hwh1"], json={"batch_material_id": bm2["id"], "material_batch_id": sfg_lot, "location_id": w["qloc2"], "quantity": bm2["required_qty"], "reason": "i"})
    assert ok.status_code == 201, ok.text
    assert b2["batch_type"] == "FG" and b1["batch_type"] == "SFG" and b2["batch_no"].startswith("FG-") and b1["batch_no"].startswith("SFG-")
    # --- genealogy spans both production levels
    back = w["qa"].get(f"{API}/trace/batch/{b2['batch_no']}?direction=backward").json()
    labels = {(n["type"], n["label"]) for n in back["nodes"]}
    assert ("BATCH", b1["batch_no"]) in labels and ("BATCH", b2["batch_no"]) in labels and any(t == "VENDOR" for t, _ in labels) and any(t == "GRN" for t, _ in labels)
    fwd = w["qa"].get(f"{API}/trace/lot/{rm_lot}?direction=forward").json()
    assert {("BATCH", b1["batch_no"]), ("BATCH", b2["batch_no"])} <= {(n["type"], n["label"]) for n in fwd["nodes"]}
