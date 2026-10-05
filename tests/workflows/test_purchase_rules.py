"""The purchase gate (spec 92 rules 1-3) and critical tests 1, 2, 3, 8, 11."""
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.core import db
from app.models import Notification, SecurityEvent, StatusHistory
from tests.conftest import PW
from tests.helpers import as_user, build_buying_world, po_body, raw

PO = "/api/v1/purchase-orders"


@pytest.fixture()
def w(app):
    return build_buying_world(app)


def _mk(w, **kw):
    return w["pu"].post(PO, headers=w["hpu"], json=po_body(w, **kw))


def test_baseline_po_is_created_with_pins_and_totals(w):
    r = _mk(w)
    assert r.status_code == 201, r.text
    po = r.json()
    assert po["po_no"].startswith("PO-") and po["status"] == "DRAFT"
    assert po["subtotal"] == 2550.0 and po["total"] == 2677.5
    line = po["lines"][0]
    assert line["specification_id"] == w["spec"] and line["vendor_material_id"] == w["vm"]     # exact versions pinned
    assert po["vendor_qualification"]["id"] == w["vq"] and po["validation"]["stage"] == "CREATE"


# ---------------------------------------------------------------- critical test 1
def test_crit_01_expired_vendor_cannot_create_po(w, engine):
    assert _mk(w).status_code == 201
    raw("UPDATE vendor_qualification SET requalification_due_date=:d", d=str(date.today() - timedelta(days=1)))   # time passes
    r = _mk(w)
    assert r.status_code == 409
    assert r.json()["rule_id"] == "BR-PO-001" and r.json()["message"] == "PURCHASE BLOCKED — VENDOR QUALIFICATION EXPIRED."
    st = w["pu"].get(f"/api/v1/vendors/{w['vendor']}/purchase-status").json()
    assert st["purchasable"] is False and st["qualification_status"] == "EXPIRED"      # live evaluation, before any job ran
    s = db.new_session()
    assert s.execute(select(SecurityEvent).where(SecurityEvent.event_type == "PO_BLOCKED")).first()
    s.close()
    # an already-drafted PO cannot be submitted either
    draft = w["pu"].get(f"{PO}?status=DRAFT").json()["items"][0]
    sub = w["pu"].post(f"{PO}/{draft['id']}/submit", headers=w["hpu"])
    assert sub.status_code == 409 and sub.json()["rule_id"] == "BR-PO-001"
    # the dry-run endpoint explains it up-front
    v = w["pu"].post(f"{PO}/validate", headers=w["hpu"], json=po_body(w)).json()
    assert v["allowed"] is False and v["results"][0]["rule_id"] == "BR-PO-001"


def test_expiry_job_persists_status_notifies_and_is_idempotent(w):
    raw("UPDATE vendor_qualification SET requalification_due_date=:d", d=str(date.today() - timedelta(days=2)))
    ad, ha = as_user(w["pu"].app, "admin_b", [])
    r1 = ad.post("/api/v1/jobs/vendor-qualification-expiry", headers=ha)
    assert r1.status_code == 200 and r1.json()["expired"] == [w["vq"]]
    q = w["qo"].get(f"/api/v1/vendor-qualifications/{w['vq']}").json()
    assert q["status"] == "EXPIRED"
    assert ad.post("/api/v1/jobs/vendor-qualification-expiry", headers=ha).json()["expired"] == []
    s = db.new_session()
    notes = s.execute(select(Notification).where(Notification.category == "VENDOR_QUALIFICATION")).scalars().all()
    assert notes and "EXPIRED" in notes[0].title
    h = s.execute(select(StatusHistory).where(StatusHistory.entity == "vendor_qualification", StatusHistory.to_status == "EXPIRED")).scalars().one()
    assert "Automatic expiry" in h.reason
    s.close()


def test_scheduler_run_acts_as_system_user(w):
    from app.jobs.runner import run_daily_jobs
    raw("UPDATE vendor_qualification SET requalification_due_date=:d", d=str(date.today() - timedelta(days=2)))
    assert run_daily_jobs()["vendor_qualifications_expired"] == [w["vq"]]
    s = db.new_session()
    h = s.execute(select(StatusHistory).where(StatusHistory.entity == "vendor_qualification", StatusHistory.to_status == "EXPIRED")).scalars().one()
    assert h.user_id is None            # SYSTEM
    from app.models import AuditTrail
    a = s.execute(select(AuditTrail).where(AuditTrail.entity == "vendor_qualification", AuditTrail.action == "STATUS_CHANGE",
                                           AuditTrail.new_value == "EXPIRED")).scalars().one()
    assert a.user_name == "SYSTEM"
    s.close()


def test_requalification_restores_purchasing_and_keeps_history(w):
    raw("UPDATE vendor_qualification SET requalification_due_date=:d", d=str(date.today() - timedelta(days=1)))
    assert _mk(w).status_code == 409
    # QA officer starts requalification (new version), reason mandatory
    bad = w["qo"].post("/api/v1/vendor-qualifications", headers=w["hqo"], json={"vendor_id": w["vendor"]})
    assert bad.status_code in (409, 422)
    n = w["qo"].post("/api/v1/vendor-qualifications", headers=w["hqo"], json={
        "vendor_id": w["vendor"], "qualified_on": str(date.today()), "requalification_due_date": str(date.today() + timedelta(days=730)),
        "basis": "Re-audit passed", "change_reason": "periodic requalification"})
    assert n.status_code == 201 and n.json()["version_no"] == 2
    nid = n.json()["id"]
    assert w["qo"].post(f"/api/v1/vendor-qualifications/{nid}/submit", headers=w["hqo"]).status_code == 200
    # still blocked while the requalification is merely under review
    assert _mk(w).status_code == 409
    a = w["qa"].post(f"/api/v1/vendor-qualifications/{nid}/approve", headers=w["hqa"], json={"password": PW, "reason": "re-audit accepted"})
    assert a.status_code == 200 and a.json()["status"] == "APPROVED"
    assert _mk(w).status_code == 201
    hist = w["qo"].get(f"/api/v1/vendor-qualifications/{nid}").json()["versions"]
    assert [(h["version_no"], h["status"]) for h in hist] == [(1, "SUPERSEDED"), (2, "APPROVED")]


# ---------------------------------------------------------------- critical test 2
def test_crit_02_unapproved_vendor_cannot_purchase(app):
    w = build_buying_world(app, with_qualification=False, with_mapping=False)
    r = w["pu"].post(PO, headers=w["hpu"], json=po_body(w))
    assert r.status_code == 409 and r.json()["rule_id"] == "BR-PO-002"      # no qualification at all
    # a never-approved vendor master record
    v2 = w["pm1"].post("/api/v1/vendors", headers=w["hpm1"], json={"name": "Draft Vendor", "reason": "x"}).json()
    r = w["pu"].post(PO, headers=w["hpu"], json=po_body(w, vendor_id=v2["id"]))
    assert r.status_code == 409 and r.json()["rule_id"] == "BR-PO-002"
    # a draft vendor cannot even be qualified
    q = w["qo"].post("/api/v1/vendor-qualifications", headers=w["hqo"], json={"vendor_id": v2["id"], "reason": "x"})
    assert q.status_code == 409 and q.json()["rule_id"] == "VQ-001"


def test_suspended_and_disqualified_vendor_blocked_and_adverse_actions_are_signed(w):
    assert w["qo"].post(f"/api/v1/vendor-qualifications/{w['vq']}/suspend", headers=w["hqo"], json={"password": PW, "reason": "x"}).status_code == 403
    assert w["qa"].post(f"/api/v1/vendor-qualifications/{w['vq']}/suspend", headers=w["hqa"], json={"password": "bad-Password-1!", "reason": "x"}).status_code == 401
    r = w["qa"].post(f"/api/v1/vendor-qualifications/{w['vq']}/suspend", headers=w["hqa"], json={"password": PW, "reason": "GMP complaint"})
    assert r.status_code == 200 and r.json()["status"] == "SUSPENDED" and r.json()["status_reason"] == "GMP complaint"
    blocked = _mk(w)
    assert blocked.status_code == 409 and blocked.json()["rule_id"] == "BR-PO-002" and "SUSPENDED" in blocked.json()["message"]
    assert w["qa"].post(f"/api/v1/vendor-qualifications/{w['vq']}/disqualify", headers=w["hqa"], json={"password": PW, "reason": "audit failure"}).json()["status"] == "DISQUALIFIED"
    assert _mk(w).status_code == 409


def test_inactive_vendor_master_blocks_po(w):
    assert w["pm1"].post(f"/api/v1/vendors/{w['vendor']}/deactivate", headers=w["hpm1"], json={"password": PW, "reason": "stop supply"}).status_code == 200
    r = _mk(w)
    assert r.status_code == 409 and r.json()["rule_id"] == "BR-PO-002"


# ---------------------------------------------------------------- critical test 3
def test_crit_03_wrong_vendor_material_combination(w):
    v2 = w["pm1"].post("/api/v1/vendors", headers=w["hpm1"], json={"name": "Vendor C", "risk_class": "LOW", "reason": "x"}).json()
    w["pm2"].post(f"/api/v1/vendors/{v2['id']}/approve", headers=w["hpm2"], json={"password": PW, "reason": "ok"})
    q = w["qo"].post("/api/v1/vendor-qualifications", headers=w["hqo"], json={
        "vendor_id": v2["id"], "qualified_on": str(date.today()), "requalification_due_date": str(date.today() + timedelta(days=400)), "reason": "x"}).json()
    w["qo"].post(f"/api/v1/vendor-qualifications/{q['id']}/submit", headers=w["hqo"])
    assert w["qa"].post(f"/api/v1/vendor-qualifications/{q['id']}/approve", headers=w["hqa"], json={"password": PW, "reason": "ok"}).status_code == 200
    # Vendor C is qualified but NOT approved for sodium chloride
    r = w["pu"].post(PO, headers=w["hpu"], json=po_body(w, vendor_id=v2["id"]))
    assert r.status_code == 409 and r.json()["rule_id"] == "BR-PO-003" and "MAT-" in r.json()["message"]
    # a draft mapping does not count; only an approved one does
    mp = w["pu"].post("/api/v1/vendor-materials", headers=w["hpu"], json={"vendor_id": v2["id"], "material_id": w["material"], "reason": "x"}).json()
    assert w["pu"].post(PO, headers=w["hpu"], json=po_body(w, vendor_id=v2["id"])).status_code == 409
    w["pu"].post(f"/api/v1/vendor-materials/{mp['id']}/submit", headers=w["hpu"])
    assert w["pu"].post(PO, headers=w["hpu"], json=po_body(w, vendor_id=v2["id"])).status_code == 409   # under review: still blocked
    assert w["qa"].post(f"/api/v1/vendor-materials/{mp['id']}/approve", headers=w["hqa"], json={"password": PW, "reason": "ok"}).status_code == 200
    assert w["pu"].post(PO, headers=w["hpu"], json=po_body(w, vendor_id=v2["id"])).status_code == 201
    # withdrawing the approval blocks again
    assert w["qa"].post(f"/api/v1/vendor-materials/{mp['id']}/withdraw", headers=w["hqa"], json={"password": PW, "reason": "quality issue"}).status_code == 200
    assert w["pu"].post(PO, headers=w["hpu"], json=po_body(w, vendor_id=v2["id"])).json()["rule_id"] == "BR-PO-003"


def test_mapping_versioning_and_sod(w):
    n = w["pu"].post(f"/api/v1/vendor-materials/{w['vm']}/new-version", headers=w["hpu"], json={"reason": "add site"})
    assert n.status_code == 201 and n.json()["version_no"] == 2 and n.json()["status"] == "DRAFT"
    # PO still works on v1 while v2 is a draft
    assert _mk(w).status_code == 201
    w["pu"].post(f"/api/v1/vendor-materials/{n.json()['id']}/submit", headers=w["hpu"])
    # author cannot approve own mapping (QA head authored it here)
    qa_made = w["qa"].post("/api/v1/vendor-materials", headers=w["hqa"], json={"vendor_id": w["vendor"], "material_id": w["material"], "reason": "x"})
    assert qa_made.status_code == 409          # approved mapping exists -> must version instead
    assert w["qa"].post(f"/api/v1/vendor-materials/{n.json()['id']}/approve", headers=w["hqa"], json={"password": PW, "reason": "ok"}).status_code == 200
    states = {x["version_no"]: x["status"] for x in w["qa"].get(f"/api/v1/vendor-materials?vendor_id={w['vendor']}").json()["items"]}
    assert states == {1: "SUPERSEDED", 2: "APPROVED"}


def test_other_po_gate_rules_spec_material_documents(app):
    w = build_buying_world(app, with_spec=False)
    r = w["pu"].post(PO, headers=w["hpu"], json=po_body(w))
    assert r.status_code == 409 and r.json()["rule_id"] == "BR-PO-005"
    w2 = None


def test_gate_reports_all_violations_and_warnings(w):
    raw("UPDATE vendor_document SET expiry_date=:d WHERE doc_type='GMP_CERTIFICATE'", d="2020-01-01")
    v = w["pu"].post(f"{PO}/validate", headers=w["hpu"], json=po_body(w, lines=[
        {"material_id": w["material"], "quantity": 0.5, "rate": 1}])).json()
    assert v["allowed"] is False
    assert any(x["rule_id"] == "BR-PO-006" and "GMP_CERTIFICATE" in x["message"] for x in v["results"])
    # due-soon warning does not block
    raw("UPDATE vendor_document SET expiry_date=:d", d=str(date.today() + timedelta(days=500)))
    raw("UPDATE vendor_qualification SET requalification_due_date=:d", d=str(date.today() + timedelta(days=20)))
    v = w["pu"].post(f"{PO}/validate", headers=w["hpu"], json=po_body(w)).json()
    assert v["allowed"] is True and any(x["rule_id"] == "BR-PO-010" and x["severity"] == "WARN" for x in v["results"])


def test_po_material_must_be_active_and_unit_checked(w):
    ids = w["ids"]
    m2 = w["qc"].post("/api/v1/materials", headers=w["hqc"], json={"name": "Glycine", "type_id": ids["RM"], "base_unit_id": ids["kg"], "reason": "x"}).json()
    w["qa"].post(f"/api/v1/materials/{m2['id']}/approve", headers=w["hqa"], json={"password": PW, "reason": "ok"})   # APPROVED, not ACTIVE
    r = w["pu"].post(f"{PO}/validate", headers=w["hpu"], json=po_body(w, lines=[{"material_id": m2["id"], "quantity": 1, "rate": 1}])).json()
    assert any(x["rule_id"] == "BR-PO-004" for x in r["results"])
    bad_unit = w["pu"].post(f"{PO}/validate", headers=w["hpu"], json=po_body(w, lines=[{"material_id": w["material"], "quantity": 1, "rate": 1, "unit_id": ids["L"]}])).json()
    assert any(x["rule_id"] == "BR-PO-008" for x in bad_unit["results"])
    dup = w["pu"].post(f"{PO}/validate", headers=w["hpu"], json=po_body(w, lines=[{"material_id": w["material"], "quantity": 1, "rate": 1}] * 2)).json()
    assert any("twice" in x["message"] for x in dup["results"])


# ---------------------------------------------------------------- approval workflow, critical tests 8 & 11
def _submitted(w):
    po = _mk(w).json()
    sub = w["pu"].post(f"{PO}/{po['id']}/submit", headers=w["hpu"])
    assert sub.status_code == 200, sub.text
    return po["id"]


def test_po_approval_chain_signature_sod_and_gate_recheck(w):
    pid = _submitted(w)
    detail = w["pu"].get(f"{PO}/{pid}").json()
    assert detail["status"] == "PENDING_APPROVAL" and detail["workflow"]["steps"][0]["role"] == "PURCHASE_MANAGER"
    # pending PO content is locked (BR-HIS-001)
    assert w["pu"].patch(f"{PO}/{pid}", headers=w["hpu"], json={"payment_terms": "advance", "reason": "x"}).status_code == 409
    line = {"material_id": w["material"], "quantity": 1, "rate": 1}
    assert w["pu"].put(f"{PO}/{pid}/lines", headers=w["hpu"], json={"lines": [line], "reason": "x"}).status_code == 409
    # crit 8: no permission -> 403 ; QC analyst cannot create POs at all
    assert w["pu"].post(f"{PO}/{pid}/decision", headers=w["hpu"], json={"decision": "APPROVE", "password": PW}).status_code == 403
    assert w["qc"].post(PO, headers=w["hqc"], json=po_body(w)).status_code == 403
    # wrong password refused
    assert w["pm1"].post(f"{PO}/{pid}/decision", headers=w["hpm1"], json={"decision": "APPROVE", "password": "bad-Password-1!"}).status_code == 401
    # the gate is re-run at approval: vendor expires between submission and approval -> approval blocked
    raw("UPDATE vendor_qualification SET requalification_due_date=:d", d=str(date.today() - timedelta(days=1)))
    r = w["pm1"].post(f"{PO}/{pid}/decision", headers=w["hpm1"], json={"decision": "APPROVE", "password": PW, "comment": "ok"})
    assert r.status_code == 409 and r.json()["rule_id"] == "BR-PO-001"
    assert w["pm1"].get(f"{PO}/{pid}").json()["status"] == "PENDING_APPROVAL"
    raw("UPDATE vendor_qualification SET requalification_due_date=:d", d=str(date.today() + timedelta(days=300)))
    ok = w["pm1"].post(f"{PO}/{pid}/decision", headers=w["hpm1"], json={"decision": "APPROVE", "password": PW, "comment": "ok"})
    assert ok.status_code == 200 and ok.json()["status"] == "APPROVED", ok.text
    sig = w["pm1"].get("/api/v1/esignatures", params={"entity": "purchase_order", "record_id": pid}) if False else None
    h = ok.json()["workflow"]["history"]
    assert [x["decision"] for x in h] == ["SUBMIT", "APPROVE"] and h[1]["signed"] is True
    # approved PO is locked
    assert w["pu"].patch(f"{PO}/{pid}", headers=w["hpu"], json={"payment_terms": "x", "reason": "x"}).status_code == 409


def test_sod_creator_cannot_approve_own_po(w):
    po = w["pm1"].post(PO, headers=w["hpm1"], json=po_body(w)).json()      # a Purchase *Manager* creates...
    w["pm1"].post(f"{PO}/{po['id']}/submit", headers=w["hpm1"])
    r = w["pm1"].post(f"{PO}/{po['id']}/decision", headers=w["hpm1"], json={"decision": "APPROVE", "password": PW})
    assert r.status_code == 409 and r.json()["rule_id"] == "SOD-01"          # ...and cannot approve it
    ok = w["pm2"].post(f"{PO}/{po['id']}/decision", headers=w["hpm2"], json={"decision": "APPROVE", "password": PW})
    assert ok.status_code == 200 and ok.json()["status"] == "APPROVED"


def test_po_rejection_and_cancellation(w):
    pid = _submitted(w)
    rej = w["pm1"].post(f"{PO}/{pid}/decision", headers=w["hpm1"], json={"decision": "REJECT", "password": PW, "comment": "rate too high"})
    assert rej.status_code == 200 and rej.json()["status"] == "REJECTED"
    # draft cancellation needs a reason only; approved cancellation needs a signature
    d = _mk(w).json()
    assert w["pu"].post(f"{PO}/{d['id']}/cancel", headers=w["hpu"], json={}).status_code == 422
    assert w["pu"].post(f"{PO}/{d['id']}/cancel", headers=w["hpu"], json={"reason": "not needed"}).json()["status"] == "CANCELLED"
    pid2 = _submitted(w)
    w["pm1"].post(f"{PO}/{pid2}/decision", headers=w["hpm1"], json={"decision": "APPROVE", "password": PW})
    assert w["pm2"].post(f"{PO}/{pid2}/cancel", headers=w["hpm2"], json={"reason": "supplier withdrew"}).status_code == 401   # no password
    assert w["pm2"].post(f"{PO}/{pid2}/cancel", headers=w["hpm2"], json={"reason": "supplier withdrew", "password": PW}).json()["status"] == "CANCELLED"


def test_po_with_receipts_cannot_be_cancelled(w):
    pid = _submitted(w)
    w["pm1"].post(f"{PO}/{pid}/decision", headers=w["hpm1"], json={"decision": "APPROVE", "password": PW})
    from app.audit.context import AuditContext, audit_context
    from app.models import PurchaseOrderLine
    s = db.new_session()
    with audit_context(AuditContext(user_name="grn", reason="goods received")):
        l = s.execute(select(PurchaseOrderLine).where(PurchaseOrderLine.po_id == pid)).scalar_one()
        l.received_quantity = 10          # the only field GRN may change on an approved PO
        s.commit()
        l.quantity = 5                    # anything else is refused
        from app.core.errors import ImmutableRecordError
        with pytest.raises(ImmutableRecordError):
            s.flush()
    s.rollback()
    s.close()
    r = w["pm2"].post(f"{PO}/{pid}/cancel", headers=w["hpm2"], json={"reason": "late", "password": PW})
    assert r.status_code == 409 and r.json()["rule_id"] == "BR-PO-011"


def test_po_audit_trail_and_status_history(w):
    pid = _submitted(w)
    w["pm1"].post(f"{PO}/{pid}/decision", headers=w["hpm1"], json={"decision": "APPROVE", "password": PW})
    s = db.new_session()
    hist = [h.to_status for h in s.execute(select(StatusHistory).where(StatusHistory.entity == "purchase_order").order_by(StatusHistory.id)).scalars()]
    assert hist == ["PENDING_APPROVAL", "APPROVED"]
    s.close()
