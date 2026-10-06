from datetime import date, timedelta

import pytest

from app.core import db
from app.models import InventoryBalance, InventoryTransaction
from sqlalchemy import select
from tests.conftest import PW
from tests.helpers import as_user, assign, build_qc_world, release_lot, submit_pass_results, take_sample
from tests.workflows.test_manufacturing import API, finish_production, issue, make_bom, new_batch

pytestmark = pytest.mark.filterwarnings("ignore")


def build_dispatch_world(app):
    w = build_qc_world(app)
    w["pr"], w["hpr"] = as_user(app, "prod1", ["PRODUCTION_USER"])
    w["pm"], w["hpm"] = as_user(app, "prod_mgr", ["PRODUCTION_MANAGER"])
    w["ds"], w["hds"] = as_user(app, "disp1", ["DISPATCH_USER"])
    ad, ha = as_user(app, "admin_b", [])
    sfg = ad.post(f"{API}/material-types", headers=ha, json={"code": "SFG", "name": "Semi-finished", "reason": "setup"}).json()["id"]
    fg = ad.post(f"{API}/material-types", headers=ha, json={"code": "FG", "name": "Finished", "reason": "setup"}).json()["id"]
    w["fg_type"] = fg
    prod = w["qc"].post(f"{API}/materials", headers=w["hqc"], json={"name": "Antiserum FG", "type_id": fg, "base_unit_id": w["ids"]["kg"], "shelf_life_days": 730, "reason": "new"}).json()["id"]
    w["product"] = prod
    w["qa"].post(f"{API}/materials/{prod}/approve", headers=w["hqa"], json={"password": PW, "reason": "ok"})
    w["qa"].post(f"{API}/materials/{prod}/activate", headers=w["hqa"], json={"password": PW, "reason": "ok"})
    sp = w["qc"].post(f"{API}/specifications", headers=w["hqc"], json={"material_id": prod, "reason": "x"}).json()["id"]
    w["qc"].post(f"{API}/specifications/{sp}/parameters", headers=w["hqc"], json={"test_name": "Assay", "lsl": 99, "usl": 101, "unit": "%", "decimal_places": 1})
    w["qc"].post(f"{API}/specifications/{sp}/parameters", headers=w["hqc"], json={"test_name": "Appearance", "spec_type": "PASS_FAIL", "acceptance_criteria": "Clear"})
    w["qc"].post(f"{API}/specifications/{sp}/submit", headers=w["hqc"])
    assert w["qa"].post(f"{API}/specifications/{sp}/approve", headers=w["hqa"], json={"password": PW, "reason": "ok"}).status_code == 200
    # release the raw-material lot (so the FG genealogy is complete) and make the FG batch
    w["rm_lot"] = w["lot"]
    release_lot(w)
    make_bom(w, qty=10, batch_size=100)
    b = new_batch(w, qty=100)
    assert issue(w, b, w["rm_lot"], loc=w["qloc"]).status_code == 201
    assert w["pr"].post(f"{API}/mfg/batches/{b['id']}/start", headers=w["hpr"], json={"password": PW, "reason": "clear"}).status_code == 200
    finish_production(w, b, actual=98, consumed=9.96, sampled=0.02, waste=0.02)
    w["pm"].post(f"{API}/mfg/batches/{b['id']}/reconciliation/approve", headers=w["hpm"], json={"password": PW, "reason": "ok"})
    o = w["pr"].post(f"{API}/mfg/batches/{b['id']}/output", headers=w["hpr"], json={"quarantine_location_id": w["qloc"]})
    assert o.status_code == 201, o.text
    w["batch"], w["fg_lot"] = b, o.json()["lot_id"]
    c = w["ds"].post(f"{API}/customers", headers=w["hds"], json={"name": "Hospital A", "licence_no": "LIC-1", "licence_expiry": str(date.today() + timedelta(days=400)), "reason": "new"})
    assert c.status_code == 201, c.text
    w["cust"] = c.json()["id"]
    return w


@pytest.fixture()
def w(app):
    return build_dispatch_world(app)


def release_fg(w):
    w["lot"] = w["fg_lot"]
    sm = take_sample(w, qty=1, containers=1)
    assign(w, sm["id"])
    submit_pass_results(w, sm["id"])
    assert w["qc"].post(f"{API}/lots/{w['lot']}/submit-release", headers=w["hqc"]).status_code == 200
    for who, h in (("qch", "hqch"), ("qo", "hqo"), ("qa", "hqa")):
        d = w[who].post(f"{API}/lots/{w['lot']}/release-decision", headers=w[h], json={"decision": "APPROVE", "password": PW, "comment": "ok"})
        assert d.status_code == 200, d.text
    return d.json()


def dsp_body(w, qty=10, **kw):
    return {"customer_id": w["cust"], "invoice_no": "INV-1", "transporter": "Cold chain Co", "vehicle_no": "MH12AB1234", "reason": "order",
            "lines": [{"material_batch_id": w["fg_lot"], "location_id": w["qloc"], "quantity": qty}], **kw}


def mk(w, **kw):
    r = w["ds"].post(f"{API}/dispatches", headers=w["hds"], json=dsp_body(w, **kw))
    assert r.status_code == 201, r.text
    return r.json()


def validate(w, d):
    return w["ds"].post(f"{API}/dispatches/{d['id']}/validate", headers=w["hds"])


# ------------------------------------------------------------------ critical test 6
def test_crit_06_unreleased_fg_cannot_be_dispatched(w):
    d = mk(w)
    r = validate(w, d)
    assert r.status_code == 409 and r.json()["rule_id"] == "BR-DSP-001" and "QA release is required" in r.json()["message"]
    chk = w["ds"].get(f"{API}/dispatches/{d['id']}/check").json()
    assert chk["allowed"] is False and any(v["rule_id"] == "BR-FGR-002" for v in chk["violations"])       # no CoA before release either
    # even forcing the approval path directly is impossible: still DRAFT
    assert w["ds"].get(f"{API}/dispatches/{d['id']}").json()["status"] == "DRAFT"
    assert w["qa"].post(f"{API}/dispatches/{d['id']}/approve", headers=w["hqa"], json={"password": PW, "reason": "x"}).status_code == 409
    assert w["ds"].post(f"{API}/dispatches/{d['id']}/dispatch", headers=w["hds"]).status_code == 409
    rel = w["wh1"].get(f"{API}/lots/{w['fg_lot']}").json()
    assert rel["on_hand"] == 98.0 and rel["disposition"] == "QUARANTINE"


def test_released_fg_full_dispatch_flow(w):
    release_fg(w)
    assert w["wh1"].get(f"{API}/lots/{w['fg_lot']}").json()["disposition"] == "APPROVED"
    d = mk(w, qty=30)
    assert d["dispatch_no"].startswith("DSP-") and d["status"] == "DRAFT"
    v = validate(w, d)
    assert v.status_code == 200 and v.json()["status"] == "VALIDATED"
    s = db.new_session()
    bal = s.execute(select(InventoryBalance).where(InventoryBalance.material_batch_id == w["fg_lot"])).scalars().first()
    assert float(bal.qty_reserved) == 30.0
    s.close()
    # validated dispatch is locked
    assert w["ds"].patch(f"{API}/dispatches/{d['id']}", headers=w["hds"], json={"remarks": "x"}).status_code in (409, 422)
    # another dispatch cannot take reserved stock
    d2 = mk(w, qty=80)
    over = validate(w, d2)
    assert over.status_code == 409 and over.json()["rule_id"] == "BR-DSP-003"
    # approval: dispatch user has no approve right; QA approves with e-signature
    assert w["ds"].post(f"{API}/dispatches/{d['id']}/approve", headers=w["hds"], json={"password": PW, "reason": "x"}).status_code == 403
    assert w["qa"].post(f"{API}/dispatches/{d['id']}/approve", headers=w["hqa"], json={"password": "bad", "reason": "ok"}).status_code == 401
    a = w["qa"].post(f"{API}/dispatches/{d['id']}/approve", headers=w["hqa"], json={"password": PW, "reason": "release verified"})
    assert a.status_code == 200 and a.json()["status"] == "APPROVED" and a.json()["approved_signature_id"]
    x = w["ds"].post(f"{API}/dispatches/{d['id']}/dispatch", headers=w["hds"])
    assert x.status_code == 200, x.text
    out = x.json()
    assert out["status"] == "DISPATCHED" and out["lines"][0]["ledger_txn_id"] and out["lines"][0]["coa_id"]
    lot = w["wh1"].get(f"{API}/lots/{w['fg_lot']}").json()
    assert lot["on_hand"] == 67.0 and lot["reconciliation"]["dispatched"] == 30.0
    s = db.new_session()
    t = s.get(InventoryTransaction, out["lines"][0]["ledger_txn_id"])
    assert t.txn_type == "DISPATCH" and t.ref_doc_id == d["dispatch_no"]
    bal = s.execute(select(InventoryBalance).where(InventoryBalance.material_batch_id == w["fg_lot"])).scalars().first()
    assert float(bal.qty_reserved) == 0.0
    s.close()
    dv = w["ds"].post(f"{API}/dispatches/{d['id']}/deliver", headers=w["hds"], json={"remarks": "received by consignee"})
    assert dv.status_code == 200 and dv.json()["status"] == "DELIVERED"
    assert w["ds"].post(f"{API}/dispatches/{d['id']}/cancel", headers=w["hds"], json={"reason": "late"}).status_code == 409
    from app.audit.context import AuditContext, audit_context
    from app.core.errors import ImmutableRecordError
    from app.models import DispatchLine
    s = db.new_session()
    with audit_context(AuditContext(user_name="TEST", reason="tamper")):
        ln = s.execute(select(DispatchLine)).scalars().first()
        ln.quantity = 1
        with pytest.raises(ImmutableRecordError):                          # a dispatched record cannot be edited (BR-HIS-001)
            s.flush()
    s.rollback()
    s.close()


def test_sod_creator_cannot_approve(w):
    release_fg(w)
    both, hb = as_user(w["ds"].app, "disp_qa", ["DISPATCH_USER", "QA_OFFICER"])
    d = both.post(f"{API}/dispatches", headers=hb, json=dsp_body(w)).json()
    assert both.post(f"{API}/dispatches/{d['id']}/validate", headers=hb).status_code == 200
    r = both.post(f"{API}/dispatches/{d['id']}/approve", headers=hb, json={"password": PW, "reason": "self"})
    assert r.status_code == 409 and r.json()["rule_id"] == "SOD-29"


def test_hold_expiry_customer_and_oos_blocks(w):
    release_fg(w)
    d = mk(w)
    # customer rules (BR-DSP-005)
    w["ds"].patch(f"{API}/customers/{w['cust']}", headers=w["hds"], json={"is_authorised": False, "reason": "licence suspended"})
    r = validate(w, d)
    assert r.status_code == 409 and r.json()["rule_id"] == "BR-DSP-005"
    w["ds"].patch(f"{API}/customers/{w['cust']}", headers=w["hds"], json={"is_authorised": True, "licence_expiry": str(date.today() - timedelta(days=1)), "reason": "x"})
    assert validate(w, d).json()["rule_id"] == "BR-DSP-005"
    w["ds"].patch(f"{API}/customers/{w['cust']}", headers=w["hds"], json={"licence_expiry": str(date.today() + timedelta(days=300)), "min_remaining_shelf_life_days": 9999, "reason": "x"})
    r = validate(w, d)
    assert r.status_code == 409 and r.json()["rule_id"] == "BR-DSP-002"                # customer shelf-life policy
    w["ds"].patch(f"{API}/customers/{w['cust']}", headers=w["hds"], json={"min_remaining_shelf_life_days": 90, "reason": "x"})
    # quality hold blocks (BR-HOLD-003)
    h = w["qo"].post(f"{API}/holds", headers=w["hqo"], json={"entity_type": "MATERIAL_BATCH", "record_id": w["fg_lot"], "reason": "complaint under review"})
    assert h.status_code in (200, 201)
    r = validate(w, d)
    assert r.status_code == 409 and r.json()["rule_id"] == "BR-HOLD-003"
    assert w["qa"].post(f"{API}/holds/{h.json()['id']}/release", headers=w["hqa"], json={"password": PW, "reason": "cleared"}).status_code == 200
    assert validate(w, d).status_code == 200


def test_hold_after_validation_blocks_approval_and_dispatch_and_cancel_releases_stock(w):
    release_fg(w)
    d = mk(w, qty=20)
    assert validate(w, d).status_code == 200
    h = w["qo"].post(f"{API}/holds", headers=w["hqo"], json={"entity_type": "MATERIAL_BATCH", "record_id": w["fg_lot"], "reason": "stability failure"}).json()
    r = w["qa"].post(f"{API}/dispatches/{d['id']}/approve", headers=w["hqa"], json={"password": PW, "reason": "ok"})
    assert r.status_code == 409 and r.json()["rule_id"] == "BR-HOLD-003"                # gate re-run at approval
    c = w["ds"].post(f"{API}/dispatches/{d['id']}/cancel", headers=w["hds"], json={"reason": "held"})
    assert c.status_code == 200 and c.json()["status"] == "CANCELLED"
    s = db.new_session()
    assert float(s.execute(select(InventoryBalance).where(InventoryBalance.material_batch_id == w["fg_lot"])).scalars().first().qty_reserved) == 0.0
    s.close()
    assert w["ds"].post(f"{API}/dispatches/{d['id']}/cancel", headers=w["hds"], json={"reason": ""}).status_code in (409, 422)
    assert h


def test_rm_and_wrong_type_cannot_be_dispatched(w):
    release_fg(w)
    r = w["ds"].post(f"{API}/dispatches", headers=w["hds"], json={**dsp_body(w), "lines": [{"material_batch_id": w["rm_lot"], "location_id": w["qloc"], "quantity": 1}]})
    assert r.status_code == 201
    v = validate(w, r.json())
    assert v.status_code == 409 and v.json()["rule_id"] == "BR-FGR-001"


def test_dispatch_is_audited_and_permissioned(w):
    release_fg(w)
    d = mk(w)
    assert w["qc"].get(f"{API}/dispatches").status_code == 200 and w["pr"].get(f"{API}/dispatches/{d['id']}").status_code == 403
    assert w["pr"].post(f"{API}/dispatches", headers=w["hpr"], json=dsp_body(w)).status_code == 403


# ------------------------------------------------------------------ traceability (forward/backward completeness)
def finish_dispatch(w, qty=30):
    release_fg(w)
    d = mk(w, qty=qty)
    assert validate(w, d).status_code == 200
    assert w["qa"].post(f"{API}/dispatches/{d['id']}/approve", headers=w["hqa"], json={"password": PW, "reason": "ok"}).status_code == 200
    assert w["ds"].post(f"{API}/dispatches/{d['id']}/dispatch", headers=w["hds"]).status_code == 200
    return d


def _labels(t, typ):
    return {n["label"] for n in t["nodes"] if n["type"] == typ}


def test_traceability_backward_and_forward_are_complete(w):
    d = finish_dispatch(w)
    qa = w["qa"]
    back = qa.get(f"{API}/trace/dispatch/{d['dispatch_no']}?direction=backward").json()
    assert d["dispatch_no"] in _labels(back, "DISPATCH")
    assert _labels(back, "LOT") >= {w["batch"]["batch_no"]}                                     # FG lot (same number as batch)
    assert _labels(back, "BATCH") == {w["batch"]["batch_no"]}
    assert len(_labels(back, "GRN")) == 1 and len(_labels(back, "PO")) == 1 and len(_labels(back, "VENDOR")) == 1                # complete chain to the vendor
    assert any(r["relation"] == "CONSUMED" for r in back["table"]) and any(r["relation"] == "CONTAINS" and r["quantity"] == 30.0 for r in back["table"])
    vendor_code = [n for n in back["nodes"] if n["type"] == "VENDOR"][0]["label"]
    fwd = qa.get(f"{API}/trace/vendor/{vendor_code}?direction=forward").json()
    assert len(_labels(fwd, "CUSTOMER")) == 1
    assert d["dispatch_no"] in _labels(fwd, "DISPATCH")
    both = qa.get(f"{API}/trace/lot/{w['rm_lot']}?direction=forward").json()
    assert d["dispatch_no"] in _labels(both, "DISPATCH") and len(_labels(both, "CUSTOMER")) == 1                 # RM lot -> batch -> FG lot -> dispatch -> customer
    cust_back = qa.get(f"{API}/trace/customer/{w['cust']}?direction=backward").json()
    assert len(_labels(cust_back, "VENDOR")) == 1
    assert w["pr"].get(f"{API}/trace/lot/{w['rm_lot']}").status_code == 403
    assert qa.get(f"{API}/trace/lot/NOPE").status_code == 404 and qa.get(f"{API}/trace/widget/1").status_code == 422
    assert qa.get(f"{API}/trace/lot/{w['rm_lot']}?direction=sideways").status_code == 422


def test_trace_excludes_undispatched_and_antisera_genealogy(w):
    release_fg(w)
    fwd = w["qa"].get(f"{API}/trace/lot/{w['fg_lot']}?direction=forward").json()
    assert not _labels(fwd, "DISPATCH") and not _labels(fwd, "CUSTOMER")                                     # nothing shipped yet
    pr, h = w["pr"], w["hpr"]
    aid = pr.post(f"{API}/antisera/animals", headers=h, json={"animal_tag": "H-7", "reason": "reg"}).json()["id"]
    bl = pr.post(f"{API}/antisera/bleeds", headers=h, json={"animal_id": aid, "bled_on": str(date.today() - timedelta(days=3)), "volume_l": 6}).json()
    plasma = w["qc"].post(f"{API}/materials", headers=w["hqc"], json={"name": "Plasma", "type_id": w["ids"]["RM"], "base_unit_id": w["ids"]["L"], "reason": "n"}).json()["id"]
    pool = pr.post(f"{API}/antisera/pools", headers=h, json={"bleed_ids": [bl["id"]], "material_id": plasma, "quarantine_location_id": w["qloc"], "reason": "pool"}).json()
    tl = w["qa"].get(f"{API}/trace/lot/{pool['lot_id']}?direction=backward").json()
    assert _labels(tl, "ANIMAL") == {"H-7"}
    t = w["qa"].get(f"{API}/trace/pool/{pool['pool_no']}?direction=backward").json()
    assert _labels(t, "ANIMAL") == {"H-7"} and len(_labels(t, "BLEED")) == 1


def test_global_search_respects_permissions_and_qr_resolve(w):
    release_fg(w)
    r = w["qa"].get(f"{API}/search?q={w['batch']['batch_no'][:6]}").json()
    types = {x["type"] for x in r}
    assert {"LOT", "BATCH"} <= types
    wh = w["wh1"].get(f"{API}/search?q={w['batch']['batch_no'][:6]}").json()
    assert "DISPATCH" not in {x["type"] for x in wh} and "BATCH" in {x["type"] for x in wh}
    assert w["qa"].get(f"{API}/search?q=a").json() == []                                         # too short
    q = w["qa"].get(f"{API}/qr/resolve?code=merp://lot/{w['batch']['batch_no']}").json()
    assert q["type"] == "LOT" and q["id"] == w["fg_lot"]
    assert w["qa"].get(f"{API}/qr/resolve?code={w['batch']['batch_no']}").json()["type"] in ("LOT", "BATCH")
    assert w["qa"].get(f"{API}/qr/resolve?code=merp://lot/NOPE").status_code == 404
    assert w["qa"].get(f"{API}/qr/resolve?code=merp://location/QZ1").json()["type"] == "LOCATION"
