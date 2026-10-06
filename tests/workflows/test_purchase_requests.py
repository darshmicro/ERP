from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.core import db
from app.models import PurchaseRequestLine
from tests.conftest import PW
from tests.helpers import as_user, build_buying_world, set_user_department

PR = "/api/v1/purchase-requests"


@pytest.fixture()
def w(app):
    return build_buying_world(app)


def _pr(w, **kw):
    body = {"purpose": "Batch production", "priority": "HIGH", "reason": "need",
            "lines": [{"material_id": w["material"], "quantity": 50, "required_date": str(date.today() + timedelta(days=10))}]}
    body.update(kw)
    return w["qc"].post(PR, headers=w["hqc"], json=body)


def test_pr_full_flow_department_then_purchase_review_then_po(w):
    r = _pr(w)
    assert r.status_code == 201, r.text
    pr = r.json()
    assert pr["pr_no"].startswith("PR-") and pr["status"] == "DRAFT" and pr["lines"][0]["unit_id"] == w["ids"]["kg"]
    # draft edit: replace lines
    up = w["qc"].put(f"{PR}/{pr['id']}/lines", headers=w["hqc"], json={"reason": "qty change", "lines": [{"material_id": w["material"], "quantity": 80}]})
    assert up.status_code == 200 and float(up.json()["lines"][0]["quantity"]) == 80
    # only the requester submits
    assert w["dh"].post(f"{PR}/{pr['id']}/submit", headers=w["hdh"]).status_code == 403
    sub = w["qc"].post(f"{PR}/{pr['id']}/submit", headers=w["hqc"])
    assert sub.status_code == 200 and sub.json()["status"] == "SUBMITTED"
    # submitted PR is locked
    assert w["qc"].put(f"{PR}/{pr['id']}/lines", headers=w["hqc"], json={"reason": "x", "lines": [{"material_id": w["material"], "quantity": 1}]}).status_code == 409
    assert w["qc"].patch(f"{PR}/{pr['id']}", headers=w["hqc"], json={"purpose": "changed", "reason": "x"}).status_code == 409
    # the department head of ANOTHER department cannot approve step 1
    other, ho = as_user(w["qc"].app, "other_head", ["DEPARTMENT_HEAD"])
    set_user_department("other_head", w["dept2"])
    assert other.post(f"{PR}/{pr['id']}/decision", headers=ho, json={"decision": "APPROVE"}).status_code == 403
    # purchase manager cannot skip the department step
    assert w["pm1"].post(f"{PR}/{pr['id']}/decision", headers=w["hpm1"], json={"decision": "APPROVE", "password": PW}).status_code == 403
    d1 = w["dh"].post(f"{PR}/{pr['id']}/decision", headers=w["hdh"], json={"decision": "APPROVE", "comment": "needed for batch"})
    assert d1.status_code == 200 and d1.json()["status"] == "DEPARTMENT_APPROVED"
    d2 = w["pm1"].post(f"{PR}/{pr['id']}/decision", headers=w["hpm1"], json={"decision": "APPROVE", "password": PW})
    assert d2.status_code == 200 and d2.json()["status"] == "APPROVED"
    assert [h["decision"] for h in d2.json()["workflow"]["history"]] == ["SUBMIT", "APPROVE", "APPROVE"]
    # convert to PO (lines come from the PR; gate rules apply)
    lid = d2.json()["lines"][0]["id"]
    po = w["pu"].post("/api/v1/purchase-orders/from-pr", headers=w["hpu"], json={
        "pr_id": pr["id"], "vendor_id": w["vendor"], "payment_terms": "30 days", "reason": "convert",
        "lines": [{"pr_line_id": lid, "rate": 20, "tax_pct": 5}]})
    assert po.status_code == 201, po.text
    assert po.json()["lines"][0]["quantity"] == 80.0 and po.json()["pr_id"] == pr["id"]
    assert w["pu"].get(f"{PR}/{pr['id']}").json()["status"] == "CONVERTED"
    again = w["pu"].post("/api/v1/purchase-orders/from-pr", headers=w["hpu"], json={
        "pr_id": pr["id"], "vendor_id": w["vendor"], "reason": "x", "lines": [{"pr_line_id": lid, "rate": 1}]})
    assert again.status_code == 409


def test_pr_rejects_inactive_material_missing_department_and_duplicates(w):
    ids = w["ids"]
    m2 = w["qc"].post("/api/v1/materials", headers=w["hqc"], json={"name": "Draft Mat", "type_id": ids["RM"], "base_unit_id": ids["kg"], "reason": "x"}).json()
    r = _pr(w, lines=[{"material_id": m2["id"], "quantity": 1}])
    assert r.status_code == 409 and r.json()["rule_id"] == "BR-PR-002"
    assert _pr(w, lines=[{"material_id": w["material"], "quantity": 1}] * 2).status_code == 422
    nodept, hn = as_user(w["qc"].app, "no_dept", ["QC_ANALYST"])
    r = nodept.post(PR, headers=hn, json={"reason": "x", "lines": [{"material_id": w["material"], "quantity": 1}]})
    assert r.status_code == 422 and "department" in r.json()["message"]


def test_pr_rejection_and_cancellation(w):
    pr = _pr(w).json()
    w["qc"].post(f"{PR}/{pr['id']}/submit", headers=w["hqc"])
    rej = w["dh"].post(f"{PR}/{pr['id']}/decision", headers=w["hdh"], json={"decision": "REJECT", "comment": "budget"})
    assert rej.status_code == 200 and rej.json()["status"] == "REJECTED"
    assert w["qc"].post(f"{PR}/{pr['id']}/submit", headers=w["hqc"]).status_code == 409        # rejected is final
    pr2 = _pr(w).json()
    w["qc"].post(f"{PR}/{pr2['id']}/submit", headers=w["hqc"])
    assert w["qc"].post(f"{PR}/{pr2['id']}/cancel", headers=w["hqc"], json={}).status_code == 422
    c = w["qc"].post(f"{PR}/{pr2['id']}/cancel", headers=w["hqc"], json={"reason": "no longer needed"})
    assert c.json()["status"] == "CANCELLED" and c.json()["workflow"]["status"] == "CANCELLED"


def test_pr_listing_filters_and_export(w):
    import io
    from openpyxl import load_workbook
    _pr(w)
    assert w["pu"].get(f"{PR}?status=DRAFT").json()["total"] == 1
    assert w["pu"].get(f"{PR}?status=APPROVED").json()["total"] == 0
    r = w["pu"].get(f"{PR}/export")
    text = " ".join(str(c) for row in load_workbook(io.BytesIO(r.content)).active.iter_rows(values_only=True) for c in row if c)
    assert "Purchase requests" in text and "PR-" in text and "pu1" in text


def test_dashboard_purchase_cards(w):
    _pr(w)
    po = w["pu"].post("/api/v1/purchase-orders", headers=w["hpu"], json={"vendor_id": w["vendor"], "reason": "x",
                                                                          "lines": [{"material_id": w["material"], "quantity": 1, "rate": 1}]}).json()
    w["pu"].post(f"/api/v1/purchase-orders/{po['id']}/submit", headers=w["hpu"])
    d = w["pm1"].get("/api/v1/dashboard/summary").json()["cards"]
    assert d["open_purchase_orders"]["value"] == 1 and d["pending_approvals"]["value"] == 1
    assert d["vendor_qualification_due"]["available"] is True
    pend = w["pm1"].get("/api/v1/approvals/pending").json()
    assert pend[0]["process"] == "po.order"


def test_vendor_qualification_readiness_and_sod(w):
    # new vendor: critical, no agreement/audit -> cannot submit
    v = w["pm1"].post("/api/v1/vendors", headers=w["hpm1"], json={"name": "Crit Vendor", "risk_class": "CRITICAL", "reason": "x"}).json()
    w["pm2"].post(f"/api/v1/vendors/{v['id']}/approve", headers=w["hpm2"], json={"password": PW, "reason": "ok"})
    q = w["qa"].post("/api/v1/vendor-qualifications", headers=w["hqa"], json={
        "vendor_id": v["id"], "qualified_on": str(date.today()), "requalification_due_date": str(date.today() + timedelta(days=365)), "reason": "x"}).json()
    r = w["qa"].post(f"/api/v1/vendor-qualifications/{q['id']}/submit", headers=w["hqa"])
    assert r.status_code == 422 and r.json()["code"] == "VQ_NOT_READY"
    msgs = " ".join(x for x in (r.json().get("details") or []))
    assert "GMP_CERTIFICATE" in msgs and "quality agreement" in msgs and "audit" in msgs
    # date validation
    bad = w["qa"].patch(f"/api/v1/vendor-qualifications/{q['id']}", headers=w["hqa"], json={"requalification_due_date": str(date.today() - timedelta(days=1)), "reason": "x"})
    assert w["qa"].post(f"/api/v1/vendor-qualifications/{q['id']}/submit", headers=w["hqa"]).status_code == 422
    # QA officer (no approve permission) cannot approve; purchase cannot create qualifications
    assert w["pu"].post("/api/v1/vendor-qualifications", headers=w["hpu"], json={"vendor_id": v["id"], "reason": "x"}).status_code == 403


def test_qualification_content_locked_after_submission_and_author_sod(w):
    vq = w["qo"].get(f"/api/v1/vendor-qualifications/{w['vq']}").json()
    assert vq["status"] == "APPROVED"
    r = w["qo"].patch(f"/api/v1/vendor-qualifications/{w['vq']}", headers=w["hqo"], json={"requalification_due_date": str(date.today() + timedelta(days=900)), "reason": "extend"})
    assert r.status_code == 409 and r.json()["rule_id"] == "BR-HIS-001"       # approved qualification cannot be silently extended
    # QA head authoring a requalification cannot approve it (SOD-21)
    n = w["qa"].post("/api/v1/vendor-qualifications", headers=w["hqa"], json={
        "vendor_id": w["vendor"], "qualified_on": str(date.today()), "requalification_due_date": str(date.today() + timedelta(days=800)),
        "change_reason": "periodic"}).json()
    w["qa"].post(f"/api/v1/vendor-qualifications/{n['id']}/submit", headers=w["hqa"])
    r = w["qa"].post(f"/api/v1/vendor-qualifications/{n['id']}/approve", headers=w["hqa"], json={"password": PW, "reason": "self"})
    assert r.status_code == 409 and r.json()["rule_id"] == "SOD-21"


def test_conditional_qualification_allows_purchase_with_warning(w):
    n = w["qo"].post("/api/v1/vendor-qualifications", headers=w["hqo"], json={
        "vendor_id": w["vendor"], "qualified_on": str(date.today()), "requalification_due_date": str(date.today() + timedelta(days=90)),
        "change_reason": "CAPA pending"}).json()
    w["qo"].post(f"/api/v1/vendor-qualifications/{n['id']}/submit", headers=w["hqo"])
    a = w["qa"].post(f"/api/v1/vendor-qualifications/{n['id']}/approve", headers=w["hqa"], json={"password": PW, "reason": "conditional until CAPA closure", "conditional": True})
    assert a.status_code == 200 and a.json()["status"] == "CONDITIONAL"
    v = w["pu"].post("/api/v1/purchase-orders/validate", headers=w["hpu"], json={"vendor_id": w["vendor"], "reason": "x", "lines": [{"material_id": w["material"], "quantity": 1, "rate": 1}]}).json()
    assert v["allowed"] is True and any("CONDITIONALLY" in x["message"] for x in v["results"])
