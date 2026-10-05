#!/usr/bin/env python
"""DEMO / TRAINING data for GMP-MERP (never run on a production database).

Creates, through the real API and services (so every rule, audit row and e-signature is genuine):
  * one user per role (password printed at the end; must be changed in any real use),
  * Vendors A/B/C (documents + qualification), materials (Sodium Chloride IP, Glycine IP, Caprylic Acid, packing, SFG, FG) with specifications,
  * warehouse locations, a customer, approved vendor-material mappings,
  * a purchase order → GRN → QC testing → QA release for Sodium Chloride; Glycine received and left in QUARANTINE;
  * an approved BOM, a manufacturing batch IN PROCESS, an open deviation and a CAPA.

Usage:   MERP_DATABASE_URL=... python database/seeds/demo_data.py        (after `alembic upgrade head` and scripts/bootstrap_admin.py)
The script refuses to run when MERP_ENV=production or when demo data already exists."""
import os
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

os.environ.setdefault("MERP_COOKIE_SECURE", "false")      # in-process HTTP client (no TLS)
DEMO_PASSWORD = os.environ.get("MERP_DEMO_PASSWORD", "Gmp!Training#2026x")
PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"
USERS = {  # username: (role, full name)
    "demo_purchase": ("PURCHASE_USER", "Priya Purchase"), "demo_pmgr": ("PURCHASE_MANAGER", "Pavan Purchase-Manager"), "demo_pmgr2": ("PURCHASE_MANAGER", "Parth Purchase-Manager 2"),
    "demo_wh": ("WAREHOUSE_USER", "Wasim Warehouse"), "demo_wh2": ("WAREHOUSE_USER", "Wanda Warehouse 2"), "demo_qc": ("QC_ANALYST", "Qadir QC-Analyst"), "demo_qchead": ("QC_HEAD", "Qiana QC-Head"),
    "demo_qao": ("QA_OFFICER", "Olivia QA-Officer"), "demo_qahead": ("QA_HEAD", "Harsh QA-Head"), "demo_qahead2": ("QA_HEAD", "Hema QA-Head 2"), "demo_prod": ("PRODUCTION_USER", "Pooja Production"),
    "demo_prodmgr": ("PRODUCTION_MANAGER", "Manoj Production-Manager"), "demo_dispatch": ("DISPATCH_USER", "Dinesh Dispatch"), "demo_mgmt": ("MANAGEMENT", "Meera Management"),
    "demo_auditor": ("AUDITOR", "Arun Auditor"), "demo_dept": ("DEPARTMENT_HEAD", "Deepa Department-Head"),
}


def main() -> int:
    if os.environ.get("MERP_ENV", "").lower() == "production":
        print("Refusing to load demo data into a production environment.", file=sys.stderr)
        return 2
    from fastapi.testclient import TestClient
    from sqlalchemy import select
    from app.audit import hooks
    from app.audit.context import AuditContext, audit_context
    from app.core import db
    from app.core.config import get_settings
    from app.main import create_app
    from app.models import Role, User, UserRole, Vendor
    from app.services import auth_service, seed

    db.configure(get_settings().database_url)
    hooks.install()
    s = db.new_session()
    if s.execute(select(Vendor.id).where(Vendor.name == "Vendor A - Chemicals Ltd")).first():
        print("Demo data already present; nothing to do.")
        return 0
    with audit_context(AuditContext(user_name="DEMO-SEED", reason="Demo data load")):
        seed.seed_baseline(s)
        for uname, (role, full) in USERS.items():
            if s.execute(select(User.id).where(User.username == uname)).first():
                continue
            u = User(username=uname, full_name=full, auth_source="LOCAL", designation=role.replace("_", " ").title())
            s.add(u)
            s.flush()
            auth_service.set_password(s, u, DEMO_PASSWORD, must_change=False, enforce_history=False)
            s.add(UserRole(user_id=u.id, role_id=s.execute(select(Role.id).where(Role.role_code == role)).scalar_one(), valid_from=date.today() - timedelta(days=1), reason="demo"))
        # reference data needs an administrator; use a transient one
        if not s.execute(select(User.id).where(User.username == "demo_admin")).first():
            a = User(username="demo_admin", full_name="Demo Administrator", auth_source="LOCAL")
            s.add(a)
            s.flush()
            auth_service.set_password(s, a, DEMO_PASSWORD, must_change=False, enforce_history=False)
            s.add(UserRole(user_id=a.id, role_id=s.execute(select(Role.id).where(Role.role_code == "SYSTEM_ADMIN")).scalar_one(), valid_from=date.today() - timedelta(days=1), reason="demo"))
        s.commit()
    s.close()

    app = create_app(configure_db=False)
    clients: dict[str, tuple] = {}

    def U(name):
        if name not in clients:
            c = TestClient(app, raise_server_exceptions=False)
            r = c.post("/api/v1/auth/login", json={"username": name, "password": DEMO_PASSWORD})
            assert r.status_code == 200, r.text
            clients[name] = (c, {"X-CSRF-Token": r.json()["csrf_token"]})
        return clients[name]

    def call(user, method, path, expect=(200, 201), **kw):
        c, h = U(user)
        r = getattr(c, method)("/api/v1" + path, headers=h, **kw)
        if r.status_code not in expect:
            raise SystemExit(f"DEMO SEED FAILED: {user} {method.upper()} {path} -> {r.status_code} {r.text[:400]}")
        return r.json() if r.content and r.headers.get("content-type", "").startswith("application/json") else r

    sign = {"password": DEMO_PASSWORD}
    # ---- reference data
    unit = {k: call("demo_admin", "post", "/units", json={"code": k, "name": n, "dimension": d, "reason": "demo"})["id"] for k, n, d in
            (("kg", "Kilogram", "MASS"), ("g", "Gram", "MASS"), ("L", "Litre", "VOLUME"), ("mL", "Millilitre", "VOLUME"), ("nos", "Numbers", "COUNT"))}
    typ = {k: call("demo_admin", "post", "/material-types", json={"code": k, "name": n, "reason": "demo"})["id"] for k, n in (("RM", "Raw Material"), ("PM", "Packing Material"), ("SFG", "Semi-finished"), ("FG", "Finished Goods"))}
    call("demo_admin", "post", "/categories", json={"code": "CHEM", "name": "Chemicals", "reason": "demo"})
    call("demo_admin", "post", "/departments", json={"code": "QC", "name": "Quality Control", "reason": "demo"})
    wid = call("demo_wh", "post", "/warehouses", json={"warehouse_code": "WH1", "name": "Main store", "reason": "demo"})["id"]
    loc = {code: call("demo_wh", "post", "/locations", json={"warehouse_id": wid, "location_code": code, "name": name, "location_type": "ZONE", "reason": "demo", **extra})["id"] for code, name, extra in (
        ("QUAR-01", "Quarantine zone", {"is_quarantine": True, "temp_min": 15, "temp_max": 25}), ("RM-01", "Raw material store", {"temp_min": 15, "temp_max": 25}),
        ("REJ-01", "Rejected material cage", {"is_rejected_area": True}), ("FG-01", "FG cold store", {"temp_min": 2, "temp_max": 8}), ("QUAR-FG", "FG quarantine", {"is_quarantine": True, "temp_min": 2, "temp_max": 8}))}
    cust = call("demo_dispatch", "post", "/customers", json={"name": "City Hospital Pharmacy", "licence_no": "DL-2026-0451", "licence_expiry": str(date.today() + timedelta(days=500)), "reason": "demo"})["id"]

    # ---- vendors A/B/C
    vend = {}
    for key, name, risk in (("A", "Vendor A - Chemicals Ltd", "HIGH"), ("B", "Vendor B - Packaging Co", "MEDIUM"), ("C", "Vendor C - Reagents Inc", "LOW")):
        v = call("demo_pmgr", "post", "/vendors", json={"name": name, "risk_class": risk, "reason": "demo"})
        call("demo_pmgr2", "post", f"/vendors/{v['id']}/approve", json={**sign, "reason": "demo approval"})
        for dt in ("GMP_CERTIFICATE", "MANUFACTURING_LICENCE", "QUALITY_AGREEMENT", "COA_SAMPLE"):
            d = call("demo_purchase", "post", f"/vendors/{v['id']}/documents", data={"doc_type": dt, "version": "1", "expiry_date": str(date.today() + timedelta(days=700))}, files={"file": (f"{dt}.pdf", PDF, "application/pdf")})
            call("demo_qao", "post", f"/vendor-documents/{d['id']}/review", json={"approve": True, "comment": "valid"})
        q = call("demo_qao", "post", "/vendor-qualifications", json={"vendor_id": v["id"], "qualified_on": str(date.today() - timedelta(days=5)), "requalification_due_date": str(date.today() + timedelta(days=360 if key != "C" else 40)),
                                                                      "basis": "Documents reviewed; audit report on file", "reason": "demo"})
        call("demo_qao", "post", f"/vendor-qualifications/{q['id']}/submit")
        call("demo_qahead", "post", f"/vendor-qualifications/{q['id']}/approve", json={**sign, "reason": "qualified"})
        vend[key] = v["id"]

    # ---- materials & specs
    mats = {}

    def material(code_key, name, tkey, ukey, **kw):
        m = call("demo_qc", "post", "/materials", json={"name": name, "type_id": typ[tkey], "base_unit_id": unit[ukey], "reason": "demo", **kw})
        call("demo_qahead", "post", f"/materials/{m['id']}/approve", json={**sign, "reason": "demo"})
        call("demo_qahead", "post", f"/materials/{m['id']}/activate", json={**sign, "reason": "demo"})
        mats[code_key] = m["id"]
        return m["id"]

    for key, name, shelf in (("NACL", "Sodium Chloride IP", 1095), ("GLY", "Glycine IP", 1095), ("CAP", "Caprylic Acid", 730)):
        mid = material(key, name, "RM", "kg", shelf_life_days=shelf, retest_days=365)
        sp = call("demo_qc", "post", "/specifications", json={"material_id": mid, "title": f"{name} specification", "reason": "demo"})
        call("demo_qc", "post", f"/specifications/{sp['id']}/parameters", json={"test_name": "Assay", "lsl": 99.0, "usl": 101.0, "unit": "%", "decimal_places": 1, "alert_high": 100.8})
        call("demo_qc", "post", f"/specifications/{sp['id']}/parameters", json={"test_name": "Appearance", "spec_type": "PASS_FAIL", "acceptance_criteria": "White crystalline powder"})
        call("demo_qc", "post", f"/specifications/{sp['id']}/submit")
        call("demo_qahead", "post", f"/specifications/{sp['id']}/approve", json={**sign, "reason": "demo"})
    mat_pm = material("VIAL", "Glass Vial 10 mL", "PM", "nos")
    material("SFG", "Antiserum Bulk (SFG)", "SFG", "L", shelf_life_days=365)
    material("FG", "Antiserum 10 mL Vial (FG)", "FG", "nos", shelf_life_days=730)
    for vkey, mkeys in (("A", ("NACL", "GLY")), ("C", ("CAP",)), ("B", ("VIAL",))):
        for mk in mkeys:
            m = call("demo_purchase", "post", "/vendor-materials", json={"vendor_id": vend[vkey], "material_id": mats[mk], "is_primary": True, "reason": "demo"})
            call("demo_purchase", "post", f"/vendor-materials/{m['id']}/submit")
            call("demo_qahead", "post", f"/vendor-materials/{m['id']}/approve", json={**sign, "reason": "demo"})
    del mat_pm

    # ---- purchase → receipt → QC → release (Sodium Chloride); Glycine stays in quarantine
    def receive(mkey, qty, batch):
        po = call("demo_purchase", "post", "/purchase-orders", json={"vendor_id": vend["A"], "payment_terms": "30 days", "reason": "demo", "lines": [{"material_id": mats[mkey], "quantity": qty, "rate": 42.5, "tax_pct": 5}]})
        call("demo_purchase", "post", f"/purchase-orders/{po['id']}/submit")
        call("demo_pmgr", "post", f"/purchase-orders/{po['id']}/decision", json={"decision": "APPROVE", **sign})
        g = call("demo_wh", "post", "/grn", json={"po_id": po["id"], "invoice_no": f"INV-{batch}", "vehicle_no": "MH12AB1234", "reason": "demo", "lines": [
            {"po_line_id": po["lines"][0]["id"], "vendor_batch_no": batch, "quantity_received": qty, "pack_count": 4, "mfg_date": str(date.today() - timedelta(days=30)),
             "expiry_date": str(date.today() + timedelta(days=700)), "coa_received": True}]})
        call("demo_wh", "post", f"/grn/{g['id']}/submit")
        chk = call("demo_wh2", "get", f"/grn/{g['id']}")["checklist"]["items"]
        call("demo_wh2", "put", f"/grn/{g['id']}/checklist", json={"reason": "demo", "answers": [{"item_id": i["item_id"], "answer": "YES"} for i in chk]})
        v = call("demo_wh2", "post", f"/grn/{g['id']}/verify", json={"quarantine_location_id": loc["QUAR-01"], **sign, "reason": "receipt verified"})
        return v["lots"][0]["id"]

    nacl_lot = receive("NACL", 200, "NC-2026-001")
    gly_lot = receive("GLY", 100, "GL-2026-007")
    smp = call("demo_qc", "post", "/samples", json={"material_batch_id": nacl_lot, "quantity_sampled": 5, "containers_sampled": 3, "sampling_location_id": loc["QUAR-01"], "reason": "sampling"})
    tests = {t["test_name"]: t for t in call("demo_qchead", "post", f"/samples/{smp['id']}/assign", json={"reason": "assign"})["tests"]}
    for name, t in tests.items():
        call("demo_qc", "post", f"/qc/tests/{t['id']}/result", json={"value": 100.2, "reason": "result"} if name == "Assay" else {"conforms": True, "reason": "result"})
    call("demo_qc", "post", f"/lots/{nacl_lot}/submit-release")
    for who in ("demo_qchead", "demo_qao", "demo_qahead"):
        call(who, "post", f"/lots/{nacl_lot}/release-decision", json={"decision": "APPROVE", **sign, "comment": "demo release"})
    call("demo_wh", "post", f"/lots/{nacl_lot}/transfer", json={"from_location_id": loc["QUAR-01"], "to_location_id": loc["RM-01"], "quantity": 190, "reason": "put-away after release"})

    # ---- BOM + batch in process
    bom = call("demo_prod", "post", "/boms", json={"product_material_id": mats["SFG"], "batch_size": 100, "unit_id": unit["L"], "yield_min_pct": 90, "yield_max_pct": 105, "reason": "demo",
                                                    "lines": [{"material_id": mats["NACL"], "quantity": 0.9}], "steps": [{"stage": "Preparation", "instruction": "Dissolve sodium chloride in WFI", "requires_verification": True},
                                                                                                                      {"stage": "Filtration", "instruction": "Filter through 0.22 µm", "requires_verification": False}]})
    call("demo_prod", "post", f"/boms/{bom['id']}/submit")
    call("demo_qahead", "post", f"/boms/{bom['id']}/approve", json={**sign, "reason": "demo BOM approved"})
    b = call("demo_prod", "post", "/mfg/batches", json={"product_material_id": mats["SFG"], "planned_qty": 100, "reason": "demo batch"})
    bm = b["materials"][0]
    call("demo_wh", "post", f"/mfg/batches/{b['id']}/issue", json={"batch_material_id": bm["id"], "material_batch_id": nacl_lot, "location_id": loc["RM-01"], "quantity": bm["required_qty"], "reason": "issue"})
    call("demo_prod", "post", f"/mfg/batches/{b['id']}/start", json={**sign, "reason": "Line clearance done"})
    # ---- quality system sample records
    d = call("demo_prod", "post", "/deviations", json={"title": "Pallet damaged on receipt (demo)", "description": "Outer cartons crushed during unloading", "severity": "MINOR", "entity_type": "MATERIAL_BATCH", "record_id": gly_lot, "reason": "demo"})
    me = call("demo_qao", "get", "/auth/me")["user"]["id"]
    call("demo_qao", "post", "/capas", json={"title": "Retrain unloading staff (demo)", "description": "Forklift handling refresher", "capa_type": "CORRECTIVE", "source": "DEVIATION", "source_ref": d["dev_no"], "owner_id": me,
                                              "due_date": str(date.today() + timedelta(days=30)), "reason": "demo"})
    print("\nDEMO DATA LOADED.\n  Users (password for all: %s):" % DEMO_PASSWORD)
    for u, (role, full) in USERS.items():
        print(f"    {u:<14} {role:<20} {full}")
    print("    demo_admin     SYSTEM_ADMIN        Demo Administrator\n  Open lots: Sodium Chloride released; Glycine in QUARANTINE (open deviation); Antiserum SFG batch %s." % b["batch_no"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
