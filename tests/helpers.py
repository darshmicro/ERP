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
        w["qc"].post(f"/api/v1/specifications/{sp['id']}/parameters", headers=w["hqc"], json={"test_name": "Assay", "lsl": 99, "usl": 101})
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
