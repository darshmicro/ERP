from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.core import db
from app.models import (AuditTrail, BatchMaterial, InventoryTransaction, ManufacturingBatch, MaterialBatch, MaterialIssue, QualityHold)
from app.services import manufacturing as mfg_svc
from app.services import qc as qc_svc
from tests.conftest import PW
from tests.helpers import as_user, build_qc_world, make_lot, raw

pytestmark = pytest.mark.filterwarnings("ignore")
API = "/api/v1"


def build_mfg_world(app):
    w = build_qc_world(app)
    w["pr"], w["hpr"] = as_user(app, "prod1", ["PRODUCTION_USER"])
    w["pm"], w["hpm"] = as_user(app, "prod_mgr", ["PRODUCTION_MANAGER"])
    ad, ha = as_user(app, "admin_b", [])
    w["sfg_type"] = ad.post(f"{API}/material-types", headers=ha, json={"code": "SFG", "name": "Semi-finished", "reason": "setup"}).json()["id"]
    w["fg_type"] = ad.post(f"{API}/material-types", headers=ha, json={"code": "FG", "name": "Finished", "reason": "setup"}).json()["id"]
    prod = w["qc"].post(f"{API}/materials", headers=w["hqc"], json={"name": "Antiserum SFG", "type_id": w["sfg_type"], "base_unit_id": w["ids"]["kg"], "shelf_life_days": 365, "reason": "new"})
    assert prod.status_code == 201, prod.text
    w["product"] = prod.json()["id"]
    w["qa"].post(f"{API}/materials/{w['product']}/approve", headers=w["hqa"], json={"password": PW, "reason": "ok"})
    w["qa"].post(f"{API}/materials/{w['product']}/activate", headers=w["hqa"], json={"password": PW, "reason": "ok"})
    w["stock"] = make_lot(w["material"], w["ids"]["kg"], w["aloc"], qty=100)
    return w


@pytest.fixture()
def w(app):
    return build_mfg_world(app)


def make_bom(w, approve=True, qty=10, batch_size=100):
    r = w["pr"].post(f"{API}/boms", headers=w["hpr"], json={
        "product_material_id": w["product"], "batch_size": batch_size, "unit_id": w["ids"]["kg"], "yield_min_pct": 90, "yield_max_pct": 105,
        "lines": [{"material_id": w["material"], "quantity": qty, "overage_pct": 0}],
        "steps": [{"stage": "Mixing", "instruction": "Charge and mix 30 min", "requires_verification": True},
                  {"stage": "Fill", "instruction": "Fill into bulk container", "requires_verification": False}], "reason": "new BOM"})
    assert r.status_code == 201, r.text
    bom = r.json()
    if approve:
        assert w["pr"].post(f"{API}/boms/{bom['id']}/submit", headers=w["hpr"]).status_code == 200
        a = w["qa"].post(f"{API}/boms/{bom['id']}/approve", headers=w["hqa"], json={"password": PW, "reason": "approved"})
        assert a.status_code == 200, a.text
    return bom


def new_batch(w, qty=100, **kw):
    r = w["pr"].post(f"{API}/mfg/batches", headers=w["hpr"], json={"product_material_id": w["product"], "planned_qty": qty, "reason": "plan", **kw})
    assert r.status_code == 201, r.text
    return r.json()


def issue(w, b, lot, qty=None, loc=None, **kw):
    bm = b["materials"][0]
    return w["wh1"].post(f"{API}/mfg/batches/{b['id']}/issue", headers=w["hwh1"], json={
        "batch_material_id": bm["id"], "material_batch_id": lot, "location_id": loc or w["aloc"], "quantity": qty or bm["required_qty"], "reason": "issue", **kw})


def get(w, b):
    return w["pr"].get(f"{API}/mfg/batches/{b['id']}").json()


# ------------------------------------------------------------------ BOM
def test_bom_lifecycle_and_immutability(w):
    bom = make_bom(w, approve=False)
    assert bom["status"] == "DRAFT" and bom["bom_no"].startswith("BOM-") and len(bom["lines"]) == 1 and len(bom["steps"]) == 2
    assert w["pr"].post(f"{API}/boms/{bom['id']}/approve", headers=w["hpr"], json={"password": PW, "reason": "x"}).status_code == 403   # production cannot approve
    assert w["pr"].post(f"{API}/boms/{bom['id']}/submit", headers=w["hpr"]).status_code == 200
    a = w["qa"].post(f"{API}/boms/{bom['id']}/approve", headers=w["hqa"], json={"password": PW, "reason": "approved"})
    assert a.status_code == 200 and a.json()["status"] == "APPROVED"
    # approved version is immutable (BR-HIS-001)
    assert w["pr"].put(f"{API}/boms/{bom['id']}/lines", headers=w["hpr"], json={"lines": [{"material_id": w["material"], "quantity": 99}], "reason": "x"}).status_code == 409
    assert w["pr"].patch(f"{API}/boms/{bom['id']}", headers=w["hpr"], json={"batch_size": 5, "reason": "x"}).status_code in (409, 422)
    v2 = w["pr"].post(f"{API}/boms/{bom['id']}/new-version", headers=w["hpr"], json={"reason": "yield change"})
    assert v2.status_code == 201 and v2.json()["version_no"] == 2 and len(v2.json()["lines"]) == 1 and len(v2.json()["steps"]) == 2
    assert w["pr"].get(f"{API}/products/{w['product']}/bom-in-force").json()["id"] == bom["id"]


def test_bom_validation(w):
    bad = lambda **kw: w["pr"].post(f"{API}/boms", headers=w["hpr"], json={"product_material_id": kw.pop("product", w["product"]), "batch_size": 10, "unit_id": w["ids"]["kg"],
                                                                         "lines": kw.pop("lines", [{"material_id": w["material"], "quantity": 1}]), "reason": "x"})
    assert bad(product=w["material"]).status_code == 422                                  # raw material cannot have a BOM
    assert bad(lines=[{"material_id": w["product"], "quantity": 1}]).status_code == 422   # product in its own BOM
    assert bad(lines=[{"material_id": w["material"], "quantity": 1}, {"material_id": w["material"], "quantity": 2}]).status_code == 422
    assert bad(lines=[{"material_id": w["material"], "quantity": 0}]).status_code == 422


# ------------------------------------------------------------------ batch creation
def test_batch_requires_approved_bom_and_scales_requirements(w):
    r = w["pr"].post(f"{API}/mfg/batches", headers=w["hpr"], json={"product_material_id": w["product"], "planned_qty": 100, "reason": "plan"})
    assert r.status_code == 409 and r.json()["rule_id"] == "BR-BOM-001"
    make_bom(w, qty=10, batch_size=100)
    b = new_batch(w, qty=250)
    assert b["status"] == "CREATED" and b["batch_no"].startswith("SFG-") and b["batch_type"] == "SFG"
    assert b["materials"][0]["required_qty"] == 25.0 and b["indent"]["indent_no"].startswith("IND-")
    assert b["bom"]["version_no"] == 1


def test_duplicate_batch_number_prevented_and_override_controlled(w):
    make_bom(w)
    b1 = new_batch(w)
    b2 = new_batch(w)
    assert b1["batch_no"] != b2["batch_no"]
    ov = lambda c, h, no, reason="manual numbering": c.post(f"{API}/mfg/batches", headers=h, json={"product_material_id": w["product"], "planned_qty": 10, "batch_no": no, "reason": reason})
    assert ov(w["pr"], w["hpr"], "AS-2026-001").status_code == 403                       # production user lacks override permission
    assert ov(w["qa"], w["hqa"], "AS-2026-001", "").status_code == 403                   # QA head holds override but not batch.create
    s = db.new_session()
    with pytest.raises(Exception):
        s.execute(ManufacturingBatch.__table__.insert().values(batch_no=b1["batch_no"], batch_type="SFG", product_material_id=w["product"], bom_id=1, planned_qty=1,
                                                              unit_id=w["ids"]["kg"], status="CREATED", created_by_user_id=1, row_version=1))
        s.commit()
    s.close()
    # cancelled numbers stay on record and cannot be reused
    c = w["pm"].post(f"{API}/mfg/batches/{b2['id']}/cancel", headers=w["hpm"], json={"reason": "planning error"})
    assert c.status_code == 200 and c.json()["status"] == "CANCELLED"
    assert w["pr"].get(f"{API}/mfg/batches?q={b2['batch_no']}").json()["total"] == 1


# ------------------------------------------------------------------ issue gates
def test_issue_gates_quarantine_rejected_expired_held(w):
    make_bom(w)
    b = new_batch(w)
    qlot = w["lot"]                                                    # QUARANTINE (received, untested)
    r = issue(w, b, qlot, 10, loc=w["qloc"])
    assert r.status_code == 409 and r.json()["rule_id"] == "BR-ISS-001"
    rej = make_lot(w["material"], w["ids"]["kg"], w["aloc"], qty=50, disposition="REJECTED")
    r = issue(w, b, rej, 10)
    assert r.status_code == 409 and r.json()["rule_id"] == "BR-ISS-002"
    exp = make_lot(w["material"], w["ids"]["kg"], w["aloc"], qty=50, expiry=date.today() - timedelta(days=1))
    r = issue(w, b, exp, 10)
    assert r.status_code == 409 and r.json()["rule_id"] == "BR-ISS-004"
    held = make_lot(w["material"], w["ids"]["kg"], w["aloc"], qty=50)
    assert w["qo"].post(f"{API}/holds", headers=w["hqo"], json={"entity_type": "MATERIAL_BATCH", "record_id": held, "reason": "investigation"}).status_code in (200, 201)
    r = issue(w, b, held, 10)
    assert r.status_code == 409 and r.json()["rule_id"] == "BR-HOLD-001"
    assert w["wh1"].get(f"{API}/lots/{rej}").json()["on_hand"] == 50.0       # nothing moved


def test_issue_links_lot_and_batch_and_posts_ledger(w):
    make_bom(w)
    b = new_batch(w)
    other = w["wh1"].post(f"{API}/mfg/batches/{b['id']}/issue", headers=w["hwh1"], json={"batch_material_id": b["materials"][0]["id"], "material_batch_id": make_lot(
        w["product"], w["ids"]["kg"], w["aloc"]), "location_id": w["aloc"], "quantity": 1, "reason": "x"})
    assert other.status_code == 409 and other.json()["rule_id"] == "BR-ISS-003"
    over = issue(w, b, w["stock"], 150)
    assert over.status_code == 409 and over.json()["rule_id"] == "BR-ISS-006"
    assert w["pr"].post(f"{API}/mfg/batches/{b['id']}/issue", headers=w["hpr"], json={"batch_material_id": 1, "material_batch_id": w["stock"], "location_id": w["aloc"], "quantity": 1}).status_code == 403
    r = issue(w, b, w["stock"])
    assert r.status_code == 201, r.text
    iss = r.json()
    assert iss["issue_no"].startswith("ISS-") and iss["batch_id"] == b["id"] and iss["material_batch_id"] == w["stock"] and iss["inventory_txn_id"]
    assert get(w, b)["status"] == "MATERIAL_ISSUED" and get(w, b)["indent"]["status"] == "ISSUED"
    assert w["wh1"].get(f"{API}/lots/{w['stock']}").json()["on_hand"] == 90.0
    s = db.new_session()
    t = s.get(InventoryTransaction, iss["inventory_txn_id"])
    assert t.txn_type == "ISSUE" and t.ref_doc_id == b["batch_no"]
    s.close()
    # issues are append-only (BR-ISS-007)
    with pytest.raises(Exception):
        raw("UPDATE material_issue SET quantity = 1")
    with pytest.raises(Exception):
        raw("DELETE FROM material_issue")


def test_fefo_deviation_needs_reason(w):
    make_bom(w)
    b = new_batch(w, qty=10)             # requires 1 kg
    early = make_lot(w["material"], w["ids"]["kg"], w["aloc"], qty=20, expiry=date.today() + timedelta(days=30))
    r = issue(w, b, w["stock"], 1)       # w["stock"] expires in 365 days; 'early' must go first
    assert r.status_code == 409 and r.json()["rule_id"] == "BR-ISS-005"
    assert issue(w, b, w["stock"], 1, fefo_override_reason="Early lot reserved for retest").status_code == 201
    assert w["wh1"].get(f"{API}/mfg/batches/{b['id']}/fefo-suggestion?batch_material_id={b['materials'][0]['id']}&quantity=1", headers=w["hwh1"]).status_code in (200, 403, 409)
    assert early


# ------------------------------------------------------------------ returns
def test_return_workflow_and_sod(w):
    make_bom(w)
    b = new_batch(w)
    iss = issue(w, b, w["stock"], 10).json()
    rq = lambda **kw: w["pr"].post(f"{API}/mfg/returns", headers=w["hpr"], json={"issue_id": iss["id"], "returned_qty": 2, "used_qty": 8, "location_id": w["aloc"], "reason": "unused", **kw})
    assert rq(returned_qty=5, used_qty=8).status_code == 409           # 5 + 8 > 10
    r = rq()
    assert r.status_code == 201 and r.json()["status"] == "REQUESTED"
    rid = r.json()["id"]
    assert w["pr"].post(f"{API}/mfg/returns/{rid}/decide", headers=w["hpr"], json={"accept": True, "comment": "ok"}).status_code == 403
    d = w["wh1"].post(f"{API}/mfg/returns/{rid}/decide", headers=w["hwh1"], json={"accept": True, "comment": "counted"})
    assert d.status_code == 200 and d.json()["status"] == "ACCEPTED" and d.json()["ledger_txn_id"]
    assert w["wh1"].get(f"{API}/lots/{w['stock']}").json()["on_hand"] == 92.0
    assert get(w, b)["materials"][0]["returned_qty"] == 2.0


# ------------------------------------------------------------------ process, IPC, reconciliation, output
def run_to_in_process(w, b):
    assert issue(w, b, w["stock"]).status_code == 201
    st = w["pr"].post(f"{API}/mfg/batches/{b['id']}/start", headers=w["hpr"], json={"password": PW, "reason": "Line clearance done"})
    assert st.status_code == 200, st.text
    return st.json()


def complete_steps(w, b):
    assert w["pr"].post(f"{API}/mfg/batches/{b['id']}/steps/1/execute", headers=w["hpr"], json={"value": "30 min"}).status_code == 200
    assert w["pr"].post(f"{API}/mfg/batches/{b['id']}/steps/2/execute", headers=w["hpr"], json={}).status_code == 200
    v = w["pm"].post(f"{API}/mfg/batches/{b['id']}/steps/1/verify", headers=w["hpm"], json={"password": PW})
    assert v.status_code == 200, v.text


def test_process_execution_controls(w):
    make_bom(w)
    b = new_batch(w)
    early = w["pr"].post(f"{API}/mfg/batches/{b['id']}/start", headers=w["hpr"], json={"password": PW, "reason": "x"})
    assert early.status_code == 409                                    # nothing issued yet
    iss = issue(w, b, w["stock"], 5)
    assert iss.status_code == 201
    part = w["pr"].post(f"{API}/mfg/batches/{b['id']}/start", headers=w["hpr"], json={"password": PW, "reason": "x"})
    assert part.status_code == 409 and part.json()["rule_id"] == "BR-MFG-002"
    assert issue(w, b, w["stock"], 5).status_code == 201
    assert w["pr"].post(f"{API}/mfg/batches/{b['id']}/start", headers=w["hpr"], json={"password": "wrong", "reason": "x"}).status_code == 401
    d = run = w["pr"].post(f"{API}/mfg/batches/{b['id']}/start", headers=w["hpr"], json={"password": PW, "reason": "Line clearance done"})
    assert d.status_code == 200 and d.json()["status"] == "IN_PROCESS" and d.json()["line_clearance_signature_id"] and len(d.json()["steps"]) == 2
    assert w["pr"].post(f"{API}/mfg/batches/{b['id']}/steps/2/execute", headers=w["hpr"], json={}).status_code == 409    # out of order
    assert w["pr"].post(f"{API}/mfg/batches/{b['id']}/steps/1/execute", headers=w["hpr"], json={"value": "30"}).status_code == 200
    assert w["pr"].post(f"{API}/mfg/batches/{b['id']}/steps/1/execute", headers=w["hpr"], json={"value": "31"}).status_code == 409   # no overwrite
    assert w["pr"].post(f"{API}/mfg/batches/{b['id']}/steps/1/verify", headers=w["hpr"], json={"password": PW}).status_code == 403   # no verify right
    assert w["pm"].post(f"{API}/mfg/batches/{b['id']}/steps/1/verify", headers=w["hpm"], json={"password": PW}).status_code == 200
    assert w["pr"].post(f"{API}/mfg/batches/{b['id']}/complete", headers=w["hpr"], json={"actual_qty": 99}).status_code == 409   # step 2 pending


def test_ipc_failure_places_batch_on_hold_and_blocks_completion(w):
    make_bom(w)
    b = new_batch(w)
    run_to_in_process(w, b)
    ok = w["pr"].post(f"{API}/mfg/batches/{b['id']}/ipc", headers=w["hpr"], json={"stage": "Mixing", "parameter": "pH", "value": 7.0, "lsl": 6.5, "usl": 7.5})
    assert ok.status_code == 201 and ok.json()["pass_fail"] == "PASS"
    assert not get(w, b)["on_hold"]
    bad = w["pr"].post(f"{API}/mfg/batches/{b['id']}/ipc", headers=w["hpr"], json={"stage": "Mixing", "parameter": "pH", "value": 8.2, "lsl": 6.5, "usl": 7.5})
    assert bad.json()["pass_fail"] == "FAIL"
    assert get(w, b)["on_hold"] is True
    complete_steps(w, b)
    r = w["pr"].post(f"{API}/mfg/batches/{b['id']}/complete", headers=w["hpr"], json={"actual_qty": 99})
    assert r.status_code == 409 and r.json()["rule_id"] == "BR-HOLD-002"
    with pytest.raises(Exception):
        raw("UPDATE ipc_result SET value_numeric = 7")


def test_equipment_gate(w):
    make_bom(w)
    b = new_batch(w)
    run_to_in_process(w, b)
    eq = w["qo"].post(f"{API}/equipment", headers=w["hqo"], json={"name": "Mixer", "reason": "register"}).json()["id"]
    r = w["pr"].post(f"{API}/mfg/batches/{b['id']}/equipment", headers=w["hpr"], json={"equipment_id": eq, "cleaning_confirmed": True})
    assert r.status_code == 409 and r.json()["rule_id"] == "BR-MFG-001"          # not qualified / calibrated
    w["qo"].patch(f"{API}/equipment/{eq}", headers=w["hqo"], json={"qualification_status": "QUALIFIED", "reason": "IQ/OQ"})
    today = date.today()
    w["qo"].post(f"{API}/equipment/{eq}/calibrations", headers=w["hqo"], json={"performed_on": str(today), "due_on": str(today + timedelta(days=180)), "result": "PASS"})
    assert w["pr"].post(f"{API}/mfg/batches/{b['id']}/equipment", headers=w["hpr"], json={"equipment_id": eq, "cleaning_confirmed": False}).status_code == 409
    assert w["pr"].post(f"{API}/mfg/batches/{b['id']}/equipment", headers=w["hpr"], json={"equipment_id": eq, "cleaning_confirmed": True}).status_code == 201


def finish_production(w, b, actual=98, consumed=9.96, sampled=0.0, waste=0.0):
    complete_steps(w, b)
    c = w["pr"].post(f"{API}/mfg/batches/{b['id']}/complete", headers=w["hpr"], json={"actual_qty": actual})
    assert c.status_code == 200, c.text
    bm = get(w, b)["materials"][0]
    k = w["pr"].put(f"{API}/mfg/batches/{b['id']}/consumption", headers=w["hpr"], json={"entries": [{"batch_material_id": bm["id"], "consumed": consumed, "sampled": sampled, "waste": waste}]})
    assert k.status_code == 200, k.text
    r = w["pr"].post(f"{API}/mfg/batches/{b['id']}/reconcile", headers=w["hpr"])
    assert r.status_code == 200, r.text
    return r.json()


def test_reconciliation_within_tolerance(w):
    make_bom(w)
    b = new_batch(w)
    run_to_in_process(w, b)
    rec = finish_production(w, b, actual=98, consumed=9.96, sampled=0.02, waste=0.02)       # issued 10 -> accounted 10.00
    line = rec["summary"]["lines"][0]
    assert rec["within_tolerance"] and rec["yield_ok"] and line["unaccounted"] == 0.0 and line["variance_pct"] == 0.0
    assert get(w, b)["yield_pct"] == 98.0
    assert w["pr"].post(f"{API}/mfg/batches/{b['id']}/reconciliation/approve", headers=w["hpr"], json={"password": PW, "reason": "ok"}).status_code == 403
    a = w["pm"].post(f"{API}/mfg/batches/{b['id']}/reconciliation/approve", headers=w["hpm"], json={"password": PW, "reason": "reviewed"})
    assert a.status_code == 200 and a.json()["status"] == "RECONCILED" and a.json()["reconciliation"]["status"] == "APPROVED"


def test_reconciliation_discrepancy_blocks_until_qa_deviation(w):
    make_bom(w)
    b = new_batch(w)
    run_to_in_process(w, b)
    rec = finish_production(w, b, actual=98, consumed=9.5)                                    # 0.5 kg (5%) unaccounted
    line = rec["summary"]["lines"][0]
    assert not rec["within_tolerance"] and line["unaccounted"] == pytest.approx(0.5) and line["variance_pct"] == pytest.approx(5.0) and not line["within_tolerance"]
    p = w["pm"].post(f"{API}/mfg/batches/{b['id']}/reconciliation/approve", headers=w["hpm"], json={"password": PW, "reason": "reviewed"})
    assert p.status_code == 200 and p.json()["status"] == "PRODUCTION_COMPLETE"
    assert p.json()["reconciliation"]["status"] == "PRODUCTION_APPROVED"           # still not reconciled: QA must accept the deviation
    out = w["pm"].post(f"{API}/mfg/batches/{b['id']}/output", headers=w["hpm"], json={"quarantine_location_id": w["qloc"]})
    assert out.status_code == 409
    assert w["qa"].post(f"{API}/mfg/batches/{b['id']}/reconciliation/qa-approve", headers=w["hqa"], json={"password": PW, "deviation_ref": "", "justification": "x"}).status_code == 422
    auto = get(w, b)["reconciliation"]["deviation_ref"]
    assert auto and auto.startswith("DEV-")                                           # the discrepancy raised a deviation automatically
    bogus = w["qa"].post(f"{API}/mfg/batches/{b['id']}/reconciliation/qa-approve", headers=w["hqa"], json={"password": PW, "deviation_ref": "DEV-9999-999999", "justification": "weighing loss on transfer lines"})
    assert bogus.status_code == 409 and bogus.json()["rule_id"] == "BR-REC-001"        # must reference a real deviation record
    q = w["qa"].post(f"{API}/mfg/batches/{b['id']}/reconciliation/qa-approve", headers=w["hqa"], json={"password": PW, "justification": "weighing loss on transfer lines"})
    assert q.status_code == 200 and q.json()["status"] == "RECONCILED" and q.json()["reconciliation"]["deviation_ref"] == auto


def test_output_lot_flows_into_qc_and_release_marks_batch(w):
    make_bom(w)
    b = new_batch(w)
    run_to_in_process(w, b)
    finish_production(w, b, actual=98, consumed=9.96, sampled=0.02, waste=0.02)
    w["pm"].post(f"{API}/mfg/batches/{b['id']}/reconciliation/approve", headers=w["hpm"], json={"password": PW, "reason": "reviewed"})
    assert w["pr"].post(f"{API}/mfg/batches/{b['id']}/output", headers=w["hpr"], json={"quarantine_location_id": w["aloc"]}).status_code == 409   # not quarantine
    o = w["pr"].post(f"{API}/mfg/batches/{b['id']}/output", headers=w["hpr"], json={"quarantine_location_id": w["qloc"]})
    assert o.status_code == 201, o.text
    lot_id = o.json()["lot_id"]
    lot = w["wh1"].get(f"{API}/lots/{lot_id}").json()
    assert lot["lot_no"] == b["batch_no"] and lot["disposition"] == "QUARANTINE" and lot["on_hand"] == 98.0 and lot["source_type"] == "MFG"
    assert get(w, b)["status"] == "QC_QA" and get(w, b)["output_lot"]["id"] == lot_id
    # hand-off to Phase 5: the QC release chain finishing marks the production batch RELEASED
    s = db.new_session()
    from app.audit.context import AuditContext, audit_context
    with audit_context(AuditContext(user_name="TEST", reason="fixture")):
        lt = s.get(MaterialBatch, lot_id)
        mfg_svc.on_lot_released(s, lt, "APPROVED")
        s.commit()
    s.close()
    assert get(w, b)["status"] == "RELEASED"


def test_conditional_material_blocks_batch_release(w):
    make_bom(w)
    b = new_batch(w, qty=100)
    cl = w["lot"]                                                          # received lot still in QUARANTINE
    cr = w["qo"].post(f"{API}/conditional-releases", headers=w["hqo"], json={
        "material_batch_id": cl, "quantity_authorised": 10, "intended_batch_ref": b["batch_no"], "justification": "urgent, QC pending", "risk_assessment_ref": "RA-1",
        "identity_confirmed": True, "expires_at": str(date.today() + timedelta(days=30))})
    assert cr.status_code == 201, cr.text
    assert w["qa"].post(f"{API}/conditional-releases/{cr.json()['id']}/decision", headers=w["hqa"], json={"password": PW, "reason": "risk assessed"}).status_code == 200
    wrong = new_batch(w, qty=100)
    r = issue(w, wrong, cl, 10, loc=w["qloc"])
    assert r.status_code == 409 and r.json()["rule_id"] == "BR-CRL-003"             # only authorised batch may use it
    r = issue(w, b, cl, 10, loc=w["qloc"])
    assert r.status_code == 201, r.text
    assert get(w, b)["uses_conditional_release"] is True
    over = issue(w, b, cl, 1, loc=w["qloc"], additional=True)
    assert over.status_code in (403, 409)                                          # authorisation exhausted / extra right missing
    run = w["pr"].post(f"{API}/mfg/batches/{b['id']}/start", headers=w["hpr"], json={"password": PW, "reason": "x"})
    assert run.status_code == 200
    complete_steps(w, b)
    w["pr"].post(f"{API}/mfg/batches/{b['id']}/complete", headers=w["hpr"], json={"actual_qty": 99})
    bm = get(w, b)["materials"][0]
    w["pr"].put(f"{API}/mfg/batches/{b['id']}/consumption", headers=w["hpr"], json={"entries": [{"batch_material_id": bm["id"], "consumed": 10}]})
    w["pr"].post(f"{API}/mfg/batches/{b['id']}/reconcile", headers=w["hpr"])
    w["pm"].post(f"{API}/mfg/batches/{b['id']}/reconciliation/approve", headers=w["hpm"], json={"password": PW, "reason": "ok"})
    o = w["pr"].post(f"{API}/mfg/batches/{b['id']}/output", headers=w["hpr"], json={"quarantine_location_id": w["qloc"]})
    assert o.status_code == 201, o.text
    s = db.new_session()
    out_lot = s.get(MaterialBatch, o.json()["lot_id"])
    assert any("BR-CRL-004" in p for p in mfg_svc.conditional_material_problems(s, out_lot))
    assert any("BR-CRL-004" in p for p in qc_svc.release_readiness(s, out_lot))
    s.close()
    ready = w["qo"].get(f"{API}/mfg/batches/{b['id']}/release-readiness")
    assert ready.status_code == 200 and ready.json()["ready"] is False


def test_issue_is_audited_and_traceable(w):
    make_bom(w)
    b = new_batch(w)
    issue(w, b, w["stock"])
    s = db.new_session()
    assert s.execute(select(AuditTrail.id).where(AuditTrail.entity == "batch_material")).first()
    assert s.execute(select(MaterialIssue.id).where(MaterialIssue.batch_id == b["id"], MaterialIssue.material_batch_id == w["stock"])).first()
    s.close()


# ------------------------------------------------------------------ antisera (6b)
def test_antisera_animal_bleed_pool_genealogy(w):
    pr, h = w["pr"], w["hpr"]
    an = pr.post(f"{API}/antisera/animals", headers=h, json={"animal_tag": "H-001", "weight_kg": 450, "reason": "register"})
    assert an.status_code == 201, an.text
    aid = an.json()["id"]
    assert pr.post(f"{API}/antisera/animals", headers=h, json={"animal_tag": "H-001", "reason": "dup"}).status_code == 409
    im = pr.post(f"{API}/antisera/animals/{aid}/immunisations", headers=h, json={"antigen": "Venom antigen A", "administered_on": str(date.today() - timedelta(days=30))})
    assert im.status_code == 201
    with pytest.raises(Exception):
        raw("UPDATE immunisation_record SET antigen = 'x'")
    d0 = date.today() - timedelta(days=20)
    b1 = pr.post(f"{API}/antisera/bleeds", headers=h, json={"animal_id": aid, "bled_on": str(d0), "volume_l": 4.5})
    assert b1.status_code == 201 and b1.json()["bleed_no"].startswith("BLD-")
    early = pr.post(f"{API}/antisera/bleeds", headers=h, json={"animal_id": aid, "bled_on": str(d0 + timedelta(days=5)), "volume_l": 4})
    assert early.status_code == 409 and early.json()["rule_id"] == "BR-ANM-002"
    b2 = pr.post(f"{API}/antisera/bleeds", headers=h, json={"animal_id": aid, "bled_on": str(d0 + timedelta(days=15)), "volume_l": 5.5})
    assert b2.status_code == 201
    plasma = w["qc"].post(f"{API}/materials", headers=w["hqc"], json={"name": "Equine plasma", "type_id": w["ids"]["RM"], "base_unit_id": w["ids"]["L"], "reason": "new"}).json()["id"]
    p = pr.post(f"{API}/antisera/pools", headers=h, json={"bleed_ids": [b1.json()["id"], b2.json()["id"]], "material_id": plasma, "quarantine_location_id": w["aloc"], "reason": "pool"})
    assert p.status_code == 409                                                       # approved location is not quarantine
    p = pr.post(f"{API}/antisera/pools", headers=h, json={"bleed_ids": [b1.json()["id"], b2.json()["id"]], "material_id": plasma, "quarantine_location_id": w["qloc"], "reason": "pool"})
    assert p.status_code == 201, p.text
    g = p.json()
    assert g["total_volume_l"] == 10.0 and len(g["bleeds"]) == 2 and g["bleeds"][0]["animal_tag"] == "H-001"
    lot = w["wh1"].get(f"{API}/lots/{g['lot_id']}").json()
    assert lot["disposition"] == "QUARANTINE" and lot["source_type"] == "POOL" and lot["on_hand"] == 10.0
    again = pr.post(f"{API}/antisera/pools", headers=h, json={"bleed_ids": [b1.json()["id"]], "material_id": plasma, "quarantine_location_id": w["qloc"], "reason": "pool"})
    assert again.status_code == 409 and again.json()["rule_id"] == "BR-ANM-003"
    assert pr.patch(f"{API}/antisera/animals/{aid}", headers=h, json={"status": "DECEASED", "reason": "died"}).status_code == 200
    assert pr.post(f"{API}/antisera/bleeds", headers=h, json={"animal_id": aid, "bled_on": str(date.today()), "volume_l": 1}).status_code == 409
