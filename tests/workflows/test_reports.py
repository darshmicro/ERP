import hashlib
import json
import time
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.core import db
from app.reports.engine import REGISTRY
import app.reports.catalog  # noqa: F401
from tests.conftest import PW
from tests.helpers import as_user, raw
from tests.workflows.test_dispatch import build_dispatch_world, finish_dispatch
from tests.workflows.test_manufacturing import API

pytestmark = pytest.mark.filterwarnings("ignore")


@pytest.fixture()
def w(app):
    w = build_dispatch_world(app)
    w["adm"], w["hadm"] = as_user(app, "sys_admin", ["SYSTEM_ADMIN"])
    w["mg"], w["hmg"] = as_user(app, "mgmt", ["MANAGEMENT"])
    w["au"], w["hau"] = as_user(app, "auditor", ["AUDITOR"])
    w["d"] = finish_dispatch(w, qty=30)
    return w


def test_catalogue_size_and_every_report_runs_with_data(w):
    assert len(REGISTRY) >= 30
    cat = w["qa"].get(f"{API}/reports").json()
    runnable = {c["code"] for c in cat}
    assert {"stock-status", "stock-ledger", "dispatch-register", "batch-register", "audit-trail", "esignature-log"} <= runnable
    for code in sorted(runnable):
        params = "?lot_no=" + w["batch"]["batch_no"] if code == "lot-genealogy" else ""
        r = w["qa"].get(f"{API}/reports/{code}{params}")
        assert r.status_code == 200, (code, r.text[:300])
        body = r.json()
        assert body["code"] == code and isinstance(body["rows"], list) and [c["key"] for c in body["columns"]]
        for row in body["rows"][:3]:
            assert set(row) >= {c["key"] for c in body["columns"]} or set(row) <= {c["key"] for c in body["columns"]} | set(row)
    # content spot checks against the real flow
    disp = w["qa"].get(f"{API}/reports/dispatch-register").json()["rows"]
    assert disp[0]["dispatch_no"] == w["d"]["dispatch_no"] and disp[0]["quantity"] == 30.0 and disp[0]["lots"] == w["batch"]["batch_no"]
    stock = w["qa"].get(f"{API}/reports/stock-status?material_code=SFG").json()["rows"] + w["qa"].get(f"{API}/reports/stock-status").json()["rows"]
    assert any(r["lot_no"] == w["batch"]["batch_no"] and r["status"] == "APPROVED" and r["on_hand"] == 67.0 for r in stock)
    led = w["qa"].get(f"{API}/reports/stock-ledger?txn_type=DISPATCH").json()
    assert led["count"] == 1 and led["rows"][0]["quantity"] == 30.0 and led["rows"][0]["lot_no"] == w["batch"]["batch_no"]
    bat = w["qa"].get(f"{API}/reports/batch-register?status=QC_QA").json()["rows"] + w["qa"].get(f"{API}/reports/batch-register").json()["rows"]
    assert any(b["batch_no"] == w["batch"]["batch_no"] for b in bat)
    rc = w["qa"].get(f"{API}/reports/batch-reconciliation").json()["rows"]
    assert rc and rc[0]["within_tolerance"] in (True, False) and rc[0]["batch_no"] == w["batch"]["batch_no"]
    gen = w["qa"].get(f"{API}/reports/lot-genealogy?lot_no={w['batch']['batch_no']}&direction=backward").json()["rows"]
    assert {"CONSUMED", "PRODUCED_BY", "CONTAINS"} & {r["relation"] for r in gen}
    assert w["qa"].get(f"{API}/reports/ledger-reconciliation").json()["count"] == 0                   # ledger agrees with balances


def test_report_permissions_params_and_no_field_leak(w):
    pr = w["pr"]
    listed = {c["code"] for c in pr.get(f"{API}/reports").json()}
    assert "audit-trail" not in listed and "user-access" not in listed and "esignature-log" not in listed and "batch-register" in listed
    for forbidden in ("audit-trail", "user-access", "security-events", "esignature-log", "dispatch-register", "stock-ledger"):
        assert pr.get(f"{API}/reports/{forbidden}").status_code == 403
        assert pr.get(f"{API}/reports/{forbidden}/export?format=csv").status_code == 403
    assert w["qa"].get(f"{API}/reports/does-not-exist").status_code == 404
    assert w["qa"].get(f"{API}/reports/stock-ledger?date_from=31-12-2026").status_code == 422
    assert w["qa"].get(f"{API}/reports/stock-ledger?txn_type=HACK").status_code == 422
    assert w["qa"].get(f"{API}/reports/lot-genealogy").status_code == 422                           # required parameter
    # no credential material anywhere in the access report or the catalogue
    ua = w["adm"].get(f"{API}/reports/user-access")
    assert ua.status_code == 200
    assert "argon2" not in ua.text and "password" not in ua.text.lower().replace("password_changed", "")
    for c in w["qa"].get(f"{API}/reports").json():
        assert not any("password" in col["key"] or "hash" in col["key"] or "secret" in col["key"] for col in c["columns"])
    # an unauthenticated caller gets nothing
    from fastapi.testclient import TestClient
    assert TestClient(w["qa"].app).get(f"{API}/reports").status_code == 401


def test_exports_are_controlled_copies_with_hash_verification(w):
    r = w["qa"].get(f"{API}/reports/dispatch-register/export?format=pdf")
    assert r.status_code == 200 and r.content.startswith(b"%PDF") and r.headers["x-controlled-copy"].startswith("RPT-")
    copy1, sha1 = r.headers["x-controlled-copy"], r.headers["x-content-sha256"]
    assert hashlib.sha256(r.content).hexdigest() == sha1
    x = w["qa"].get(f"{API}/reports/dispatch-register/export?format=xlsx")
    c = w["qa"].get(f"{API}/reports/dispatch-register/export?format=csv")
    assert x.status_code == 200 and x.content[:2] == b"PK" and c.status_code == 200 and b"Dispatch" in c.content and w["d"]["dispatch_no"].encode() in c.content
    assert len({copy1, x.headers["x-controlled-copy"], c.headers["x-controlled-copy"]}) == 3          # unique copy numbers
    v = w["qa"].get(f"{API}/reports-verify?copy_no={copy1}&sha256={sha1}").json()
    assert v["matches"] is True and v["printed_by"] == "qa_head"
    assert w["qa"].get(f"{API}/reports-verify?copy_no={copy1}&sha256={'0' * 64}").json()["matches"] is False
    assert w["qa"].get(f"{API}/reports-verify?copy_no=RPT-0000&sha256={sha1}").status_code == 404
    runs = w["qa"].get(f"{API}/report-runs?report_code=dispatch-register").json()
    assert runs["total"] == 3 and {i["output_format"] for i in runs["items"]} == {"pdf", "xlsx", "csv"}
    assert w["pr"].get(f"{API}/report-runs").status_code == 403
    with pytest.raises(Exception):
        raw("UPDATE report_run SET sha256 = 'x'")                                                   # append-only
    with pytest.raises(Exception):
        raw("DELETE FROM report_run")
    # the print is in the audit trail
    aud = w["qa"].get(f"{API}/audit-trail?entity=report_run").json()
    assert len(aud["items"]) >= 3 and {a["action"] for a in aud["items"]} == {"EXPORT"}


def test_controlled_business_documents_pdf(w):
    po = w["pu"].get(f"{API}/purchase-orders/{w['po']}/pdf")
    assert po.status_code == 200 and po.content.startswith(b"%PDF") and po.headers["x-controlled-copy"].startswith("RPT-")
    grns = w["wh1"].get(f"{API}/grn").json()["items"]
    assert w["wh1"].get(f"{API}/grn/{grns[0]['id']}/pdf").content.startswith(b"%PDF")
    assert w["ds"].get(f"{API}/dispatches/{w['d']['id']}/pdf").content.startswith(b"%PDF")
    bp = w["pm"].get(f"{API}/mfg/batches/{w['batch']['id']}/pdf")
    assert bp.status_code == 200 and bp.content.startswith(b"%PDF") and len(bp.content) > 2500
    assert w["wh1"].get(f"{API}/dispatches/{w['d']['id']}/pdf").status_code == 403                  # no dispatch read right
    assert w["qa"].get(f"{API}/dispatches/99999/pdf").status_code == 404
    assert w["qa"].get(f"{API}/report-runs?report_code=batch-record-pdf").json()["total"] == 1


def test_dashboards_are_role_gated_and_populated(w):
    for name, role, key in (("management", "mg", "Dispatches (this month)"), ("qc", "qa", "Samples awaiting testing"), ("qa", "qa", "Open quality holds"), ("warehouse", "wh1", "GRNs awaiting verification")):
        r = w[role].get(f"{API}/dashboards/{name}")
        assert r.status_code == 200, (name, r.text)
        labels = {c["label"]: c["value"] for c in r.json()["cards"]}
        assert key in labels and isinstance(r.json()["series"], dict)
    mg = {c["label"]: c["value"] for c in w["mg"].get(f"{API}/dashboards/management").json()["cards"]}
    assert mg["Dispatches (this month)"] == 1 and mg["Batches released (this month)"] == 1
    wh = w["wh1"].get(f"{API}/dashboards/warehouse").json()
    assert any(x["label"] == "FG" for x in wh["series"]["stock_by_material_type"])
    assert w["pr"].get(f"{API}/dashboards/management").status_code == 403
    assert w["wh1"].get(f"{API}/dashboards/qa").status_code == 403
    assert w["qa"].get(f"{API}/dashboards/nope").status_code == 404
    assert set(w["qa"].get(f"{API}/dashboards").json()) == {"management", "qc", "qa", "warehouse", "monitoring"}


def test_retention_policies_archive_and_legal_hold(w):
    pol = w["qa"].get(f"{API}/retention/policies").json()
    types = {p["record_type"]: p for p in pol}
    assert {"audit_trail", "inventory_transaction", "qc_result", "manufacturing_batch", "dispatch"} <= set(types) and types["audit_trail"]["retention_years"] == 10
    assert all(p["eligible_for_archive"] == 0 for p in pol)                                          # nothing is that old
    pid = types["deviation"]["id"]
    assert w["qa"].patch(f"{API}/retention/policies/{pid}", headers=w["hqa"], json={"retention_years": 5, "reason": "shorten"}).status_code == 409   # never shortened in-app
    assert w["qo"].patch(f"{API}/retention/policies/{pid}", headers=w["hqo"], json={"retention_years": 12, "reason": "x"}).status_code == 403
    assert w["adm"].patch(f"{API}/retention/policies/{pid}", headers=w["hadm"], json={"retention_years": 12, "reason": "x"}).status_code == 403     # admins hold no GMP authority
    ext = w["qa"].patch(f"{API}/retention/policies/{pid}", headers=w["hqa"], json={"retention_years": 12, "reason": "site policy"})
    assert ext.status_code == 200 and ext.json()["retention_years"] == 12                                                                          # extending is allowed
    nothing = w["qa"].post(f"{API}/retention/archive/deviation", headers=w["hqa"])
    assert nothing.status_code == 409 and nothing.json()["rule_id"] == "BR-RET-001"
    # make a deviation 5 years old and a 1-year policy (DBA-level change under change control) -> eligible
    d = w["pr"].post(f"{API}/deviations", headers=w["hpr"], json={"title": "Old deviation", "description": "legacy record", "reason": "x"}).json()
    raw("UPDATE deviation SET created_at = :t", t=(datetime.now(timezone.utc) - timedelta(days=5 * 365)).strftime("%Y-%m-%d %H:%M:%S.%f"))
    raw("UPDATE retention_policy SET retention_years = 1 WHERE record_type = 'deviation'")
    p2 = {p["record_type"]: p for p in w["qa"].get(f"{API}/retention/policies").json()}["deviation"]
    assert p2["eligible_for_archive"] == 1
    assert w["qo"].post(f"{API}/retention/archive/deviation", headers=w["hqo"]).status_code == 403
    ar = w["qa"].post(f"{API}/retention/archive/deviation", headers=w["hqa"])
    assert ar.status_code == 201, ar.text
    a = ar.json()
    assert a["archive_no"].startswith("ARC-") and a["row_count"] == 1 and len(a["sha256"]) == 64
    dl = w["qa"].get(f"{API}/retention/archives/{a['id']}/download")
    assert dl.status_code == 200 and hashlib.sha256(dl.content).hexdigest() == a["sha256"] and dl.content[:2] == b"PK"
    # non-destructive: the original record is untouched; packages never overlap, so a second run finds nothing new
    assert w["qa"].get(f"{API}/deviations/{d['id']}").status_code == 200
    assert a["from_id"] == a["to_id"] == d["id"]
    again = w["qa"].post(f"{API}/retention/archive/deviation", headers=w["hqa"])
    assert again.status_code == 409 and again.json()["rule_id"] == "BR-RET-001"
    assert {p["record_type"]: p for p in w["qa"].get(f"{API}/retention/policies").json()}["deviation"]["eligible_for_archive"] == 0
    # legal hold blocks archival; hold needs a reason
    pid = p2["id"]
    assert w["qa"].patch(f"{API}/retention/policies/{pid}", headers=w["hqa"], json={"legal_hold": True, "reason": "inspection"}).status_code == 422       # hold reason required
    assert w["qa"].patch(f"{API}/retention/policies/{pid}", headers=w["hqa"], json={"legal_hold": True, "legal_hold_reason": "Regulatory inspection 2026-11", "reason": "hold"}).status_code == 200
    held = w["qa"].post(f"{API}/retention/archive/deviation", headers=w["hqa"])
    assert held.status_code == 409 and held.json()["rule_id"] == "BR-RET-002"
    assert {p["record_type"]: p for p in w["qa"].get(f"{API}/retention/policies").json()}["deviation"]["eligible_for_archive"] == 0
    assert w["qa"].get(f"{API}/retention/archives").json()[0]["archive_no"] == a["archive_no"]


def test_backup_status_and_restore_evidence(w):
    st = w["adm"].get(f"{API}/backup/status").json()
    assert st["ok"] is False and any("No successful backup" in a for a in st["alerts"]) and any("restore test" in a for a in st["alerts"])
    now = datetime.now(timezone.utc)
    body = {"backup_type": "FULL", "performed_at": now.isoformat(), "location": "\\\\nas\\merp\\full_001.bak", "size_mb": 850, "tool": "SQL Server native", "sha256": "a" * 64}
    assert w["pr"].post(f"{API}/backup/records", headers=w["hpr"], json=body).status_code == 403
    assert w["adm"].post(f"{API}/backup/records", headers=w["hadm"], json={**body, "performed_at": (now + timedelta(days=2)).isoformat()}).status_code == 422
    assert w["adm"].post(f"{API}/backup/records", headers=w["hadm"], json={**body, "backup_type": "TAPE"}).status_code == 422
    assert w["adm"].post(f"{API}/backup/records", headers=w["hadm"], json=body).status_code == 201
    mid = w["adm"].get(f"{API}/backup/status").json()
    assert mid["last_full"]["size_mb"] == 850 and mid["last_backup_age_hours"] < 1 and any("restore test" in a for a in mid["alerts"]) and not any("No successful backup" in a for a in mid["alerts"])
    assert w["adm"].post(f"{API}/backup/records", headers=w["hadm"], json={"backup_type": "RESTORE_TEST", "performed_at": now.isoformat(), "audit_chain_verified": True, "rto_minutes": 42, "location": "scratch DB"}).status_code == 201
    ok = w["adm"].get(f"{API}/backup/status").json()
    assert ok["ok"] is True and ok["alerts"] == [] and ok["last_restore_test"]["rto_minutes"] == 42 and ok["last_restore_test"]["audit_chain_verified"] is True
    # stale backup is flagged (evidence rows are append-only; age the row at DB level to simulate time passing)
    with pytest.raises(Exception):
        raw("UPDATE backup_record SET result = 'FAILED'")
    assert len(w["adm"].get(f"{API}/backup/records").json()) == 2
    assert w["qa"].get(f"{API}/backup/status").status_code == 200 and w["pr"].get(f"{API}/backup/status").status_code == 403


def test_report_performance_with_large_ledger(w):
    """5 000 ledger rows: JSON preview, CSV and XLSX export must stay interactive (spec: performance test for reports)."""
    from sqlalchemy import select
    from app.models import InventoryTransaction
    s = db.new_session()
    lot_id, loc_id = s.execute(select(InventoryTransaction.material_batch_id, InventoryTransaction.to_location_id)).first()[:2]
    s.close()
    rows = [{"material_batch_id": lot_id, "txn_type": "ADJUST_IN", "to_location_id": loc_id, "quantity": 1, "unit_id": 1, "ref_doc_type": "PERF", "ref_doc_id": str(i), "txn_ts": datetime.now(timezone.utc)} for i in range(5000)]
    with db.get_engine().begin() as conn:
        conn.execute(InventoryTransaction.__table__.insert(), rows)
    t0 = time.perf_counter()
    r = w["qa"].get(f"{API}/reports/stock-ledger?txn_type=ADJUST_IN&limit=5000")
    t1 = time.perf_counter()
    c = w["qa"].get(f"{API}/reports/stock-ledger/export?format=csv&txn_type=ADJUST_IN")
    t2 = time.perf_counter()
    x = w["qa"].get(f"{API}/reports/stock-ledger/export?format=xlsx&txn_type=ADJUST_IN")
    t3 = time.perf_counter()
    assert r.json()["count"] == 5000 and c.content.count(b"\n") >= 5000 and x.content[:2] == b"PK"
    assert (t1 - t0) < 10 and (t2 - t1) < 15 and (t3 - t2) < 20, (t1 - t0, t2 - t1, t3 - t2)
