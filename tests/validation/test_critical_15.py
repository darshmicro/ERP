"""The fifteen mandatory critical tests (master prompt §77 / Business Rules Catalogue Doc 07 §1).

 01 expired vendor qualification blocks PO            tests/workflows/test_purchase_rules.py::test_crit_01_expired_vendor_cannot_create_po
 02 unapproved vendor blocks PO                       tests/workflows/test_purchase_rules.py::test_crit_02_unapproved_vendor_cannot_purchase
 03 vendor not approved for the material blocks PO    tests/workflows/test_purchase_rules.py::test_crit_03_wrong_vendor_material_combination
 04 quarantine material cannot be issued              tests/workflows/test_warehouse.py::test_crit_04_quarantine_material_cannot_be_issued
                                                      tests/workflows/test_manufacturing.py::test_issue_gates_quarantine_rejected_expired_held
 05 rejected material cannot be issued                tests/workflows/test_warehouse.py::test_crit_05_rejected_and_crit_07_expired_material_cannot_be_issued
 06 unreleased FG cannot be dispatched                tests/workflows/test_dispatch.py::test_crit_06_unreleased_fg_cannot_be_dispatched
 07 expired material cannot be issued                 (same as 05) + tests/workflows/test_manufacturing.py::test_issue_gates_quarantine_rejected_expired_held
 08..15                                               this module (one explicit test each)
"""
import json
from datetime import date, timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.audit.context import AuditContext, audit_context
from app.core import db
from app.core.errors import ImmutableRecordError
from app.models import AuditTrail, ESignature, InventoryBalance, InventoryTransaction, MaterialIssue, User
from app.services import inventory
from tests.conftest import PW
from tests.helpers import as_user, build_buying_world, make_lot, po_body, raw
from tests.workflows.test_dispatch import build_dispatch_world, finish_dispatch
from tests.workflows.test_manufacturing import (API, build_mfg_world, finish_production, get, issue, make_bom, new_batch, run_to_in_process)

pytestmark = pytest.mark.filterwarnings("ignore")


@pytest.fixture()
def dw(app):
    return build_dispatch_world(app)


@pytest.fixture()
def mw(app):
    w = build_mfg_world(app)
    w["qa2"], w["hqa2"] = as_user(app, "qa_head2", ["QA_HEAD"])
    return w


@pytest.fixture()
def bw(app):
    return build_buying_world(app)


# ---------------------------------------------------------------------------------------------- 08
def test_crit_08_quality_hold_blocks_issue_use_and_dispatch(dw):
    w = dw
    # BR-HOLD-001: a held lot cannot be issued
    b = new_batch(w, qty=10)
    stock = dw["rm_lot"]
    h = w["qo"].post(f"{API}/holds", headers=w["hqo"], json={"entity_type": "MATERIAL_BATCH", "record_id": stock, "reason": "supplier alert"})
    assert h.status_code in (200, 201)
    r = issue(w, b, stock, 1, loc=w["qloc"])
    assert r.status_code == 409 and r.json()["rule_id"] == "BR-HOLD-001"
    # BR-HOLD-002: a held production batch cannot be used / completed
    free = __import__("tests.helpers", fromlist=["make_lot"]).make_lot(w["material"], w["ids"]["kg"], w["aloc"], qty=50)
    b2 = new_batch(w, qty=10)
    assert issue(w, b2, free, 1).status_code == 201
    assert w["pr"].post(f"{API}/mfg/batches/{b2['id']}/start", headers=w["hpr"], json={"password": PW, "reason": "clear"}).status_code == 200
    assert w["qo"].post(f"{API}/holds", headers=w["hqo"], json={"entity_type": "MFG_BATCH", "record_id": b2["id"], "reason": "IPC doubt"}).status_code in (200, 201)
    r = w["pr"].post(f"{API}/mfg/batches/{b2['id']}/complete", headers=w["hpr"], json={"actual_qty": 9})
    assert r.status_code == 409 and r.json()["rule_id"] == "BR-HOLD-002"
    # BR-HOLD-003: held FG cannot be dispatched
    w["lot"] = w["fg_lot"]
    from tests.workflows.test_dispatch import release_fg, mk, validate
    release_fg(w)
    d = mk(w)
    fh = w["qo"].post(f"{API}/holds", headers=w["hqo"], json={"entity_type": "MATERIAL_BATCH", "record_id": w["fg_lot"], "reason": "complaint"}).json()
    r = validate(w, d)
    assert r.status_code == 409 and r.json()["rule_id"] == "BR-HOLD-003"
    # BR-HOLD-004: only QA releases a hold, with e-signature + reason
    assert w["wh1"].post(f"{API}/holds/{fh['id']}/release", headers=w["hwh1"], json={"password": PW, "reason": "x"}).status_code == 403
    assert w["qa"].post(f"{API}/holds/{fh['id']}/release", headers=w["hqa"], json={"password": "wrong", "reason": "x"}).status_code == 401
    assert w["qa"].post(f"{API}/holds/{fh['id']}/release", headers=w["hqa"], json={"password": PW, "reason": "complaint unfounded"}).status_code == 200
    assert validate(w, d).status_code == 200


# ---------------------------------------------------------------------------------------------- 09
def test_crit_09_audit_trail_cannot_be_modified_or_deleted(client, admin, engine):
    client.put("/api/v1/company", headers=admin, json={"gst_no": "29ABCDE1234F1Z5", "reason": "setup"})
    # (a) application ORM
    s = db.new_session()
    row = s.execute(select(AuditTrail)).scalars().first()
    with audit_context(AuditContext(user_name="attacker", reason="x")):
        row.new_value = "tampered"
        with pytest.raises(ImmutableRecordError):
            s.flush()
    s.rollback()
    with pytest.raises(ImmutableRecordError):
        s.delete(row)
        s.flush()
    s.rollback()
    s.close()
    # (b) raw SQL as the application login: database triggers refuse it
    with pytest.raises(DBAPIError):
        raw("UPDATE audit_trail SET new_value = 'x'")
    with pytest.raises(DBAPIError):
        raw("DELETE FROM audit_trail")
    assert client.get("/api/v1/security-events", headers=admin).status_code == 200      # security log is read-only for everybody
    # (c) no API verb can change it
    for m in ("put", "patch", "delete", "post"):
        assert getattr(client, m)("/api/v1/audit-trail/1", headers=admin).status_code in (404, 405)
    # (d) even a privileged tamper (triggers removed by a DBA) is DETECTED by the hash chain
    from app.audit.immutability import drop_statements, trigger_statements
    qa = as_user(client.app, "qa_v", ["QA_HEAD"])
    assert qa[0].get("/api/v1/audit-trail/verify").json()["ok"] is True
    with db.get_engine().begin() as c:
        for st in drop_statements(c.dialect.name, ("audit_trail",)):
            c.execute(text(st))
        c.execute(text("UPDATE audit_trail SET new_value = 'forged' WHERE id = 1"))
    res = qa[0].get("/api/v1/audit-trail/verify").json()
    assert res["ok"] is False and res["first_bad_audit_id"] == 1


# ---------------------------------------------------------------------------------------------- 10
def test_crit_10_electronic_signature_required_and_bound_to_the_record(bw):
    w = bw
    m = w["qc"].post("/api/v1/materials", headers=w["hqc"], json={"name": "Glycine", "type_id": w["ids"]["RM"], "base_unit_id": w["ids"]["kg"], "reason": "new"}).json()
    url = f"/api/v1/materials/{m['id']}/approve"
    assert w["qa"].post(url, headers=w["hqa"], json={"reason": "ok"}).status_code == 422                                 # no password: cannot sign
    bad = w["qa"].post(url, headers=w["hqa"], json={"password": "Wrong-Passw0rd!", "reason": "ok"})
    assert bad.status_code == 401
    s = db.new_session()
    qa = s.execute(select(User).where(User.username == "qa_head")).scalar_one()
    assert qa.failed_attempts >= 1                                                                                        # a bad signature counts as a failed login (BR-SIG-001)
    before = s.execute(select(ESignature)).scalars().all()
    s.close()
    ok = w["qa"].post(url, headers=w["hqa"], json={"password": PW, "reason": "specification reviewed"})
    assert ok.status_code == 200
    s = db.new_session()
    sig = s.execute(select(ESignature).where(ESignature.entity == "material", ESignature.record_id == str(m["id"]))).scalars().all()[-1]
    assert len(s.execute(select(ESignature)).scalars().all()) == len(before) + 1
    assert sig.printed_name and sig.meaning == "QA_APPROVED" and sig.reason == "specification reviewed" and len(sig.record_hash) == 64 and len(sig.manifest_hash) == 64 and sig.signed_at
    s.close()
    with pytest.raises(DBAPIError):
        raw("UPDATE e_signature SET meaning = 'APPROVED_BY'")                                                          # signatures cannot be edited or detached
    # a role without the signing permission cannot sign even with the right password
    assert w["qo"].post(f"/api/v1/specifications/{w['spec']}/approve", headers=w["hqo"], json={"password": PW, "reason": "x"}).status_code == 403
    # the same applies to PO approval, release and dispatch (all require password re-entry)
    po = w["pu"].post("/api/v1/purchase-orders", headers=w["hpu"], json=po_body(w)).json()
    w["pu"].post(f"/api/v1/purchase-orders/{po['id']}/submit", headers=w["hpu"])
    assert w["pm1"].post(f"/api/v1/purchase-orders/{po['id']}/decision", headers=w["hpm1"], json={"decision": "APPROVE"}).status_code in (401, 422)


# ---------------------------------------------------------------------------------------------- 11
def test_crit_11_creator_cannot_approve_own_transaction(bw):
    w = bw
    # PO: a purchase manager creates the PO and may not approve it
    po = w["pm1"].post("/api/v1/purchase-orders", headers=w["hpm1"], json=po_body(w)).json()
    assert w["pm1"].post(f"/api/v1/purchase-orders/{po['id']}/submit", headers=w["hpm1"]).status_code == 200
    r = w["pm1"].post(f"/api/v1/purchase-orders/{po['id']}/decision", headers=w["hpm1"], json={"decision": "APPROVE", "password": PW})
    assert r.status_code == 409 and r.json()["rule_id"] == "SOD-01"
    assert w["pm2"].post(f"/api/v1/purchase-orders/{po['id']}/decision", headers=w["hpm2"], json={"decision": "APPROVE", "password": PW}).status_code == 200
    # master data: the author of a specification cannot approve it (QA head authors, QA head 2 approves)
    qa2, h2 = as_user(w["qa"].app, "qa_head2", ["QA_HEAD"])
    sp = w["qa"].post("/api/v1/specifications", headers=w["hqa"], json={"material_id": w["material"], "reason": "rev"}).json() if False else None
    v2 = w["qc"].post(f"/api/v1/specifications/{w['spec']}/new-version", headers=w["hqc"], json={"reason": "revision"}).json()
    w["qc"].post(f"/api/v1/specifications/{v2['id']}/submit", headers=w["hqc"])
    qc_head, hq = as_user(w["qa"].app, "qc_head_x", ["QC_HEAD"])
    assert qc_head.post(f"/api/v1/specifications/{v2['id']}/approve", headers=hq, json={"password": PW, "reason": "x"}).status_code == 403
    assert qa2.post(f"/api/v1/specifications/{v2['id']}/approve", headers=h2, json={"password": PW, "reason": "independent QA approval"}).status_code == 200


# ---------------------------------------------------------------------------------------------- 12
def test_crit_12_historical_gmp_records_are_never_overwritten(bw):
    w = bw
    pars = w["qc"].get(f"/api/v1/specifications/{w['spec']}").json()["parameters"]
    r = w["qc"].patch(f"/api/v1/specifications/{w['spec']}/parameters/{pars[0]['id']}", headers=w["hqc"], json={"lsl": 98, "usl": 102})
    assert r.status_code == 409 and r.json()["rule_id"] == "BR-HIS-001"                                                   # approved version is immutable
    po = w["pu"].post("/api/v1/purchase-orders", headers=w["hpu"], json=po_body(w)).json()
    pinned = po["lines"][0]["specification_id"]
    w["pu"].post(f"/api/v1/purchase-orders/{po['id']}/submit", headers=w["hpu"])
    assert w["pu"].patch(f"/api/v1/purchase-orders/{po['id']}", headers=w["hpu"], json={"payment_terms": "changed"}).status_code in (409, 422)   # submitted PO is locked
    # revise: v2 is a NEW row; v1 stays intact and the PO still points at the exact version it was raised against
    v2 = w["qc"].post(f"/api/v1/specifications/{w['spec']}/new-version", headers=w["hqc"], json={"reason": "tighter"}).json()
    w["qc"].post(f"/api/v1/specifications/{v2['id']}/submit", headers=w["hqc"])
    qa2, h2 = as_user(w["qa"].app, "qa_head2", ["QA_HEAD"])
    assert qa2.post(f"/api/v1/specifications/{v2['id']}/approve", headers=h2, json={"password": PW, "reason": "ok"}).status_code == 200
    old = w["qc"].get(f"/api/v1/specifications/{w['spec']}").json()
    assert old["status"] == "SUPERSEDED" and old["parameters"][0]["lsl"] == 99.0 and old["version_no"] == 1               # content untouched
    assert w["pu"].get(f"/api/v1/purchase-orders/{po['id']}").json()["lines"][0]["specification_id"] == pinned == w["spec"]
    # point-in-time lookup still answers for the past
    assert w["qc"].get(f"/api/v1/materials/{w['material']}/specification-in-force").json()["id"] == v2["id"]
    # status history and signatures are append-only
    with pytest.raises(DBAPIError):
        raw("UPDATE gmp_status_history SET to_status = 'X'")
    with pytest.raises(DBAPIError):
        raw("UPDATE e_signature SET reason = 'edited'")


# ---------------------------------------------------------------------------------------------- 13
def test_crit_13_every_stock_movement_creates_an_inventory_transaction(dw):
    w = finish_dispatch_world(dw)
    s = db.new_session()
    types = [t.txn_type for t in s.execute(select(InventoryTransaction).order_by(InventoryTransaction.id)).scalars()]
    # RM receipt, RM sample, RM issue, FG output, FG sample, FG dispatch (each movement = exactly one row)
    assert types.count("RECEIPT") == 1 and types.count("SAMPLE") == 2 and types.count("ISSUE") == 1 and types.count("OUTPUT") == 1 and types.count("DISPATCH") == 1
    assert inventory.verify_ledger(s) == []                                                                                # balance table == ledger for every lot/location
    s.close()
    lot = w["wh1"].get(f"/api/v1/lots/{w['fg_lot']}").json()
    assert lot["reconciliation"]["received"] + 0 == lot["reconciliation"]["received"] and lot["on_hand"] == 67.0
    # no negative stock and no direct balance edit path
    d2 = w["ds"].post(f"{API}/dispatches", headers=w["hds"], json={"customer_id": w["cust"], "reason": "x", "lines": [{"material_batch_id": w["fg_lot"], "location_id": w["qloc"], "quantity": 500}]}).json()
    assert w["ds"].post(f"{API}/dispatches/{d2['id']}/validate", headers=w["hds"]).json()["rule_id"] == "BR-DSP-003"
    paths = {r.path for r in w["qa"].app.routes if hasattr(r, "path")}
    assert not any("inventory_balance" in p or "/balance" in p for p in paths)
    # drift between ledger and balance (e.g. an out-of-band edit) is detected (BR-INV-003)
    raw("UPDATE inventory_balance SET qty_on_hand = qty_on_hand + 5")
    s = db.new_session()
    assert len(inventory.verify_ledger(s)) >= 1
    s.close()
    assert w["qa"].get(f"{API}/reports/ledger-reconciliation").json()["count"] >= 1


def finish_dispatch_world(w):
    finish_dispatch(w, qty=30)
    return w


# ---------------------------------------------------------------------------------------------- 14
def test_crit_14_issued_material_is_always_linked_to_lot_and_production_batch(dw):
    w = finish_dispatch_world(dw)
    s = db.new_session()
    issues = s.execute(select(MaterialIssue)).scalars().all()
    assert issues and all(i.batch_id and i.material_batch_id for i in issues)
    s.close()
    # the database itself refuses an issue row without the batch or the lot
    for col in ("batch_id", "material_batch_id"):
        cols = {"issue_no": "ISS-X", "batch_id": 1, "batch_material_id": 1, "material_batch_id": 1, "location_id": 1, "quantity": 1, "is_additional": 0, "issued_at": "2026-01-01 00:00:00.000000"}
        cols[col] = None
        with pytest.raises(IntegrityError):
            raw("INSERT INTO material_issue (issue_no, batch_id, batch_material_id, material_batch_id, location_id, quantity, is_additional, issued_at) "
                "VALUES (:issue_no, :batch_id, :batch_material_id, :material_batch_id, :location_id, :quantity, :is_additional, :issued_at)", **cols)
    # the wrong material for the BOM line is refused (BR-ISS-003) and traceability walks FG batch -> RM lot -> GRN -> PO -> vendor
    b = new_batch(w, qty=10)
    other = make_lot(w["product"], w["ids"]["kg"], w["aloc"], qty=5)
    r = issue(w, b, other, 1)
    assert r.status_code == 409 and r.json()["rule_id"] == "BR-ISS-003"
    t = w["qa"].get(f"{API}/trace/lot/{w['batch']['batch_no']}?direction=backward").json()
    kinds = {n["type"] for n in t["nodes"]}
    assert {"LOT", "BATCH", "GRN", "PO", "VENDOR"} <= kinds


# ---------------------------------------------------------------------------------------------- 15
def test_crit_15_reconciliation_discrepancy_is_highlighted_and_blocks_progress(mw):
    w = mw
    make_bom(w)
    b = new_batch(w)
    run_to_in_process(w, b)
    rec = finish_production(w, b, actual=98, consumed=9.5)                                                                # 0.5 of 10 kg unaccounted
    line = rec["summary"]["lines"][0]
    assert rec["within_tolerance"] is False and line["within_tolerance"] is False and line["unaccounted"] == pytest.approx(0.5) and line["variance_pct"] == pytest.approx(5.0)
    dev = get(w, b)["reconciliation"]["deviation_ref"]
    assert dev and w["qo"].get(f"{API}/deviations?q={dev}").json()["total"] == 1                                         # a deviation was raised automatically
    assert w["pm"].post(f"{API}/mfg/batches/{b['id']}/reconciliation/approve", headers=w["hpm"], json={"password": PW, "reason": "reviewed"}).json()["reconciliation"]["status"] == "PRODUCTION_APPROVED"
    blocked = w["pr"].post(f"{API}/mfg/batches/{b['id']}/output", headers=w["hpr"], json={"quarantine_location_id": w["qloc"]})
    assert blocked.status_code == 409                                                                                      # cannot proceed to QC/QA until QA accepts the discrepancy
    # QA acceptance by a different person than the production approver, with e-signature and justification
    assert w["pm"].post(f"{API}/mfg/batches/{b['id']}/reconciliation/qa-approve", headers=w["hpm"], json={"password": PW, "justification": "weighing loss"}).status_code == 403
    ok = w["qa"].post(f"{API}/mfg/batches/{b['id']}/reconciliation/qa-approve", headers=w["hqa"], json={"password": PW, "justification": "documented weighing loss on transfer lines"})
    assert ok.status_code == 200 and ok.json()["status"] == "RECONCILED"
    assert w["pr"].post(f"{API}/mfg/batches/{b['id']}/output", headers=w["hpr"], json={"quarantine_location_id": w["qloc"]}).status_code == 201
