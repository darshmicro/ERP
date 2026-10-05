import io

from fastapi.testclient import TestClient
from openpyxl import Workbook

from tests.conftest import PW, login, make_user

PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"


def as_user(app, username: str, roles: list[str]):
    """Create the user (if missing) and return (client, csrf-headers)."""
    from sqlalchemy import select
    from app.core import db
    from app.models import User
    s = db.new_session()
    exists = s.execute(select(User.id).where(User.username == username)).first()
    s.close()
    if not exists:
        make_user(username, roles)
    c = TestClient(app, raise_server_exceptions=False)
    return c, login(c, username)


def j(h: dict, reason: str = "test") -> dict:
    return {"X-CSRF-Token": h["X-CSRF-Token"]}


def xlsx(header: list[str], rows: list[list]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Data"
    ws.append(header)
    for r in rows:
        ws.append(r)
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


def bootstrap_basics(app):
    """Admin creates unit/type/category; returns ids."""
    c, h = as_user(app, "admin_b", ["SYSTEM_ADMIN"])
    ids = {}
    ids["kg"] = c.post("/api/v1/units", headers=h, json={"code": "kg", "name": "Kilogram", "dimension": "MASS", "reason": "setup"}).json()["id"]
    ids["L"] = c.post("/api/v1/units", headers=h, json={"code": "L", "name": "Litre", "dimension": "VOLUME", "reason": "setup"}).json()["id"]
    ids["RM"] = c.post("/api/v1/material-types", headers=h, json={"code": "RM", "name": "Raw Material", "reason": "setup"}).json()["id"]
    ids["PM"] = c.post("/api/v1/material-types", headers=h, json={"code": "PM", "name": "Packing Material", "reason": "setup"}).json()["id"]
    ids["chem"] = c.post("/api/v1/categories", headers=h, json={"code": "CHEM", "name": "Chemicals", "reason": "setup"}).json()["id"]
    ids["acid"] = c.post("/api/v1/categories", headers=h, json={"code": "ACID", "name": "Acids", "reason": "setup"}).json()["id"]
    return ids


def set_user_department(username: str, dept_id: int):
    from sqlalchemy import select
    from app.audit.context import AuditContext, audit_context
    from app.core import db
    from app.models import User
    s = db.new_session()
    with audit_context(AuditContext(user_name="TEST", reason="test dept")):
        u = s.execute(select(User).where(User.username == username)).scalar_one()
        u.department_id = dept_id
        s.commit()
    s.close()


def raw(sql: str, **params):
    from sqlalchemy import text
    from app.core import db
    with db.get_engine().begin() as c:
        c.execute(text(sql), params)


def build_buying_world(app, *, with_mapping=True, with_spec=True, with_qualification=True, risk="HIGH"):
    """Admin lookups, a department, an approved vendor with approved documents, an ACTIVE material with an approved
    specification, an approved qualification and an approved vendor-material mapping."""
    from datetime import date, timedelta
    ids = bootstrap_basics(app)
    w = {"ids": ids}
    ad, ha = as_user(app, "admin_b", [])
    w["dept"] = ad.post("/api/v1/departments", headers=ha, json={"code": "QC", "name": "Quality Control", "reason": "setup"}).json()["id"]
    w["dept2"] = ad.post("/api/v1/departments", headers=ha, json={"code": "PRD", "name": "Production", "reason": "setup"}).json()["id"]
    w["pm1"], w["hpm1"] = as_user(app, "pm1", ["PURCHASE_MANAGER"])
    w["pm2"], w["hpm2"] = as_user(app, "pm2", ["PURCHASE_MANAGER"])
    w["pu"], w["hpu"] = as_user(app, "pu1", ["PURCHASE_USER"])
    w["qa"], w["hqa"] = as_user(app, "qa_head", ["QA_HEAD"])
    w["qo"], w["hqo"] = as_user(app, "qa_off", ["QA_OFFICER"])
    w["qc"], w["hqc"] = as_user(app, "qc_an", ["QC_ANALYST"])
    w["dh"], w["hdh"] = as_user(app, "dept_head", ["DEPARTMENT_HEAD"])
    for u in ("qc_an", "dept_head"):
        set_user_department(u, w["dept"])
    # vendor
    v = w["pm1"].post("/api/v1/vendors", headers=w["hpm1"], json={"name": "Vendor A", "risk_class": risk, "reason": "new"}).json()
    w["vendor"] = v["id"]
    assert w["pm2"].post(f"/api/v1/vendors/{v['id']}/approve", headers=w["hpm2"], json={"password": PW, "reason": "ok"}).status_code == 200
    for dt in ("GMP_CERTIFICATE", "MANUFACTURING_LICENCE", "QUALITY_AGREEMENT", "COA_SAMPLE"):
        r = w["pu"].post(f"/api/v1/vendors/{v['id']}/documents", headers=w["hpu"], data={"doc_type": dt, "version": "1", "expiry_date": str(date.today() + timedelta(days=700))},
                         files={"file": (f"{dt}.pdf", PDF, "application/pdf")})
        assert r.status_code == 201, r.text
        assert w["qo"].post(f"/api/v1/vendor-documents/{r.json()['id']}/review", headers=w["hqo"], json={"approve": True, "comment": "valid"}).status_code == 200
    # material
    m = w["qc"].post("/api/v1/materials", headers=w["hqc"], json={"name": "Sodium Chloride IP", "type_id": ids["RM"], "base_unit_id": ids["kg"], "reason": "new"}).json()
    w["material"] = m["id"]
    w["qa"].post(f"/api/v1/materials/{m['id']}/approve", headers=w["hqa"], json={"password": PW, "reason": "ok"})
    w["qa"].post(f"/api/v1/materials/{m['id']}/activate", headers=w["hqa"], json={"password": PW, "reason": "ok"})
    if with_spec:
        sp = w["qc"].post("/api/v1/specifications", headers=w["hqc"], json={"material_id": m["id"], "reason": "x"}).json()
        w["qc"].post(f"/api/v1/specifications/{sp['id']}/parameters", headers=w["hqc"], json={"test_name": "Assay", "lsl": 99, "usl": 101, "unit": "%", "decimal_places": 1, "alert_high": 100.8})
        w["qc"].post(f"/api/v1/specifications/{sp['id']}/parameters", headers=w["hqc"], json={"test_name": "Appearance", "spec_type": "PASS_FAIL", "acceptance_criteria": "White crystalline powder"})
        w["qc"].post(f"/api/v1/specifications/{sp['id']}/submit", headers=w["hqc"])
        assert w["qa"].post(f"/api/v1/specifications/{sp['id']}/approve", headers=w["hqa"], json={"password": PW, "reason": "ok"}).status_code == 200
        w["spec"] = sp["id"]
    if with_qualification:
        q = w["qo"].post("/api/v1/vendor-qualifications", headers=w["hqo"], json={
            "vendor_id": v["id"], "qualified_on": str(date.today() - timedelta(days=1)),
            "requalification_due_date": str(date.today() + timedelta(days=365)), "basis": "Audit + documents", "reason": "initial"})
        assert r_ok(r := q), q.text
        w["vq"] = q.json()["id"]
        assert w["qo"].post(f"/api/v1/vendor-qualifications/{w['vq']}/submit", headers=w["hqo"]).status_code == 200
        a = w["qa"].post(f"/api/v1/vendor-qualifications/{w['vq']}/approve", headers=w["hqa"], json={"password": PW, "reason": "qualified"})
        assert a.status_code == 200, a.text
    if with_mapping:
        mp = w["pu"].post("/api/v1/vendor-materials", headers=w["hpu"], json={"vendor_id": v["id"], "material_id": m["id"], "is_primary": True, "reason": "x"})
        assert mp.status_code == 201, mp.text
        w["vm"] = mp.json()["id"]
        w["pu"].post(f"/api/v1/vendor-materials/{w['vm']}/submit", headers=w["hpu"])
        assert w["qa"].post(f"/api/v1/vendor-materials/{w['vm']}/approve", headers=w["hqa"], json={"password": PW, "reason": "ok"}).status_code == 200
    return w


def r_ok(r):
    return r.status_code == 201


def po_body(w, **kw):
    body = {"vendor_id": w["vendor"], "payment_terms": "30 days", "delivery_date": None,
            "lines": [{"material_id": w["material"], "quantity": 100, "rate": 25.5, "tax_pct": 5}], "reason": "order"}
    body.update(kw)
    return body


def build_warehouse_world(app, **kw):
    """Buying world + warehouse locations (quarantine / approved / rejected) + two warehouse users + an APPROVED PO."""
    from datetime import date, timedelta
    w = build_buying_world(app, **kw)
    w["wh1"], w["hwh1"] = as_user(app, "wh1", ["WAREHOUSE_USER"])
    w["wh2"], w["hwh2"] = as_user(app, "wh2", ["WAREHOUSE_USER"])
    wid = w["wh1"].post("/api/v1/warehouses", headers=w["hwh1"], json={"warehouse_code": "WH1", "name": "Main store", "reason": "setup"}).json()["id"]
    def loc(code, **extra):
        r = w["wh1"].post("/api/v1/locations", headers=w["hwh1"], json={"warehouse_id": wid, "location_code": code, "name": code, "location_type": "ZONE", "reason": "setup", **extra})
        assert r.status_code == 201, r.text
        return r.json()["id"]
    w["qloc"] = loc("QZ1", is_quarantine=True, temp_min=15, temp_max=25)
    w["qloc2"] = loc("QZ2", is_quarantine=True)
    w["aloc"] = loc("AZ1", temp_min=15, temp_max=25)
    w["rloc"] = loc("RZ1", is_rejected_area=True)
    w["wid"] = wid
    r = w["pu"].post("/api/v1/purchase-orders", headers=w["hpu"], json=po_body(w))
    assert r.status_code == 201, r.text
    w["po"] = r.json()["id"]
    w["po_line"] = r.json()["lines"][0]["id"]
    assert w["pu"].post(f"/api/v1/purchase-orders/{w['po']}/submit", headers=w["hpu"]).status_code == 200
    a = w["pm1"].post(f"/api/v1/purchase-orders/{w['po']}/decision", headers=w["hpm1"], json={"decision": "APPROVE", "password": PW})
    assert a.status_code == 200, a.text
    return w


def grn_body(w, qty=100, **kw):
    from datetime import date, timedelta
    line = {"po_line_id": w["po_line"], "vendor_batch_no": "VB-001", "quantity_received": qty, "pack_count": 4,
            "mfg_date": str(date.today() - timedelta(days=30)), "expiry_date": str(date.today() + timedelta(days=700)), "coa_received": True}
    line.update(kw.pop("line", {}))
    body = {"po_id": w["po"], "invoice_no": "INV-1", "vehicle_no": "MH12AB1234", "lines": [line], "reason": "received"}
    body.update(kw)
    return body


def answer_all(w, client, h, grn_id, answer="YES", overrides=None):
    items = client.get("/api/v1/grn-checklist-items").json()
    overrides = overrides or {}
    answers = [{"item_id": i["id"], "answer": overrides.get(i["code"], answer), "comment": "checked" if overrides.get(i["code"]) == "NO" else None} for i in items]
    r = client.put(f"/api/v1/grn/{grn_id}/checklist", headers=h, json={"answers": answers, "reason": "verification"})
    assert r.status_code == 200, r.text
    return r.json()


def received_lot(w, qty=100):
    """Full receipt: GRN created, submitted, checklist YES, verified by a second user. Returns (grn_json)."""
    g = w["wh1"].post("/api/v1/grn", headers=w["hwh1"], json=grn_body(w, qty))
    assert g.status_code == 201, g.text
    gid = g.json()["id"]
    assert w["wh1"].post(f"/api/v1/grn/{gid}/submit", headers=w["hwh1"]).status_code == 200
    answer_all(w, w["wh2"], w["hwh2"], gid)
    v = w["wh2"].post(f"/api/v1/grn/{gid}/verify", headers=w["hwh2"], json={"quarantine_location_id": w["qloc"], "password": PW, "reason": "ok"})
    assert v.status_code == 200, v.text
    return v.json()


def make_lot(material_id, unit_id, location_id, qty=100, disposition="APPROVED", expiry=None, retest=None, lot_no=None):
    """Create a lot directly (test fixture) and post its receipt to the ledger."""
    from datetime import date, timedelta
    from app.audit.context import AuditContext, audit_context
    from app.core import db
    from app.models import MaterialBatch, Location
    from app.services import inventory, numbering
    s = db.new_session()
    with audit_context(AuditContext(user_name="TEST", reason="fixture")):
        lot = MaterialBatch(lot_no=lot_no or numbering.next_number(s, numbering.default_plant_id(s), "LOT"), material_id=material_id,
                            quantity=qty, unit_id=unit_id, disposition=disposition,
                            expiry_date=expiry if expiry is not None else date.today() + timedelta(days=365), retest_date=retest)
        s.add(lot)
        s.flush()
        inventory.post(s, txn_type="RECEIPT", batch=lot, quantity=qty, to_location_id=location_id, ref_doc_type="TEST")
        s.commit()
        out = lot.id
    s.close()
    return out


def build_qc_world(app, **kw):
    """Warehouse world + QC people + a received lot in quarantine."""
    w = build_warehouse_world(app, **kw)
    w["qc2"], w["hqc2"] = as_user(app, "qc_an2", ["QC_ANALYST"])
    w["qch"], w["hqch"] = as_user(app, "qc_head", ["QC_HEAD"])
    out = received_lot(w)
    w["lot"] = out["lots"][0]["id"]
    return w


def take_sample(w, qty=5, containers=3):
    r = w["qc"].post("/api/v1/samples", headers=w["hqc"], json={"material_batch_id": w["lot"], "quantity_sampled": qty, "containers_sampled": containers,
                                                                  "sampling_location_id": w["qloc"], "reason": "sampling"})
    assert r.status_code == 201, r.text
    return r.json()


def assign(w, sample_id, analyst_id=None):
    r = w["qch"].post(f"/api/v1/samples/{sample_id}/assign", headers=w["hqch"], json={"analyst_id": analyst_id, "reason": "assign"})
    assert r.status_code == 200, r.text
    return {t["test_name"]: t for t in r.json()["tests"]}


def submit_pass_results(w, sample_id, assay=100.2, client=None, h=None):
    client, h = client or w["qc"], h or w["hqc"]
    tests = {t["test_name"]: t for t in client.get(f"/api/v1/samples/{sample_id}").json()["tests"] if t["status"] in ("ASSIGNED", "STARTED")}
    out = {}
    for name, t in tests.items():
        body = {"value": assay} if name == "Assay" else {"conforms": True}
        r = client.post(f"/api/v1/qc/tests/{t['id']}/result", headers=h, json={**body, "reason": "result"})
        assert r.status_code == 201, r.text
        out[name] = r.json()
    return out


def release_lot(w):
    """Run the full QC->QA release chain; returns the final release status."""
    s = take_sample(w)
    assign(w, s["id"])
    submit_pass_results(w, s["id"])
    r = w["qc"].post(f"/api/v1/lots/{w['lot']}/submit-release", headers=w["hqc"])
    assert r.status_code == 200, r.text
    for who, h in (("qch", "hqch"), ("qo", "hqo"), ("qa", "hqa")):
        d = w[who].post(f"/api/v1/lots/{w['lot']}/release-decision", headers=w[h], json={"decision": "APPROVE", "password": PW, "comment": "ok"})
        assert d.status_code == 200, d.text
    return d.json()
