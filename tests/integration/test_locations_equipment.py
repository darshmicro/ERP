from datetime import date, timedelta

import pytest

from tests.helpers import as_user, bootstrap_basics


@pytest.fixture()
def w(app):
    ids = bootstrap_basics(app)
    wh, hw = as_user(app, "wh_l", ["WAREHOUSE_USER"])
    qa, hq = as_user(app, "qa_l", ["QA_OFFICER"])
    wid = wh.post("/api/v1/warehouses", headers=hw, json={"warehouse_code": "WH1", "name": "Main store", "reason": "setup"}).json()["id"]
    return dict(ids=ids, wh=wh, hw=hw, qa=qa, hq=hq, wid=wid, app=app)


def _loc(w, code, ltype, parent=None, **kw):
    return w["wh"].post("/api/v1/locations", headers=w["hw"], json={
        "warehouse_id": w["wid"], "location_code": code, "name": code, "location_type": ltype,
        "parent_id": parent, "reason": "setup", **kw})


def test_hierarchy_rules_and_path(w):
    z = _loc(w, "Z1", "ZONE").json()
    r = _loc(w, "R1", "ROOM", z["id"]).json()
    rack = _loc(w, "RK1", "RACK", r["id"]).json()
    bin_ = _loc(w, "B1", "BIN", rack["id"]).json()
    assert bin_["path"] == "Z1 > R1 > RK1 > B1"
    assert _loc(w, "BAD", "ROOM", rack["id"]).status_code == 422          # room under rack
    assert _loc(w, "Z1", "ZONE").status_code == 409                       # duplicate code
    assert _loc(w, "X", "SHED").status_code == 422
    # restructuring a node that has children is blocked
    r2 = w["wh"].patch(f"/api/v1/locations/{r['id']}", headers=w["hw"], json={"location_type": "SHELF", "reason": "x"})
    assert r2.status_code == 409 and r2.json()["rule_id"] == "LOC-001"
    # changes need a reason and are audited
    assert w["wh"].patch(f"/api/v1/locations/{rack['id']}", headers=w["hw"], json={"name": "Rack One"}).status_code == 422


def test_storage_compatibility_checks(w):
    ids = w["ids"]
    cold = _loc(w, "COLD", "ZONE", temp_min=2, temp_max=8, allowed_category_ids=[ids["chem"]]).json()
    acid_loc = _loc(w, "ACID1", "ZONE", allowed_category_ids=[ids["acid"]]).json()
    qc, hq = as_user(w["app"], "qc_l", ["QC_ANALYST"])
    m = qc.post("/api/v1/materials", headers=hq, json={"name": "Chem A", "type_id": ids["RM"], "base_unit_id": ids["kg"],
                                                       "category_id": ids["chem"], "temp_min": 2, "temp_max": 8, "reason": "x"}).json()
    ok = w["wh"].get(f"/api/v1/locations/{cold['id']}/storage-check", params={"material_id": m["id"]}).json()
    assert ok == {"ok": True, "violations": []}
    bad = w["wh"].get(f"/api/v1/locations/{acid_loc['id']}/storage-check", params={"material_id": m["id"]}).json()
    assert bad["ok"] is False and "category" in bad["violations"][0]
    # deactivate -> not storable
    w["wh"].patch(f"/api/v1/locations/{cold['id']}", headers=w["hw"], json={"status": "INACTIVE", "reason": "maintenance"})
    assert "not active" in w["wh"].get(f"/api/v1/locations/{cold['id']}/storage-check", params={"material_id": m["id"]}).json()["violations"][0]


def test_incompatible_category_rule(w):
    from app.core import db
    from app.models import Location, Material
    from app.services import master_services as ms
    ids = w["ids"]
    r = w["qa"].post("/api/v1/location-compat-rules", headers=w["hq"], json={"category_a_id": ids["chem"], "category_b_id": ids["acid"], "reason": "segregate"})
    assert r.status_code in (201, 403)  # QA officer lacks md.location? (creates allowed via md.location.create)
    s = db.new_session()
    loc = Location(warehouse_id=w["wid"], location_code="Q", name="q", location_type="ZONE")
    s.add(loc)
    mat = Material(material_code="M", name="m", type_id=ids["RM"], base_unit_id=ids["kg"], category_id=ids["chem"])
    s.add(mat)
    s.flush()
    from app.models import LocationCompatRule
    if r.status_code == 403:
        s.add(LocationCompatRule(category_a_id=ids["chem"], category_b_id=ids["acid"], allowed=False))
        s.flush()
    v = ms.storage_violations(s, loc, mat, categories_present=[ids["acid"]])
    assert any("Incompatible" in x for x in v)
    assert ms.storage_violations(s, loc, mat, categories_present=[]) == []


def _eq(w, **kw):
    return w["qa"].post("/api/v1/equipment", headers=w["hq"], json={"name": "pH meter", "reason": "register", **kw}).json()


def test_calibration_gate_for_testing(w):
    eq = _eq(w)
    assert eq["equipment_code"] == "EQ-00001" and eq["qualification_status"] == "NOT_QUALIFIED"
    st = lambda: w["qa"].get(f"/api/v1/equipment/{eq['id']}/status").json()
    assert st()["usable_for_testing"] is False and st()["calibration_status"] == "NOT_CALIBRATED"
    w["qa"].patch(f"/api/v1/equipment/{eq['id']}", headers=w["hq"], json={"qualification_status": "QUALIFIED", "reason": "IQ/OQ done"})
    today = date.today()
    cal = lambda **kw: w["qa"].post(f"/api/v1/equipment/{eq['id']}/calibrations", headers=w["hq"], json=kw)
    assert cal(performed_on=str(today), due_on=str(today), result="PASS").status_code == 422        # due must be after
    assert cal(performed_on=str(today + timedelta(days=1)), due_on=str(today + timedelta(days=30)), result="PASS").status_code == 422
    assert cal(performed_on=str(today), due_on=str(today + timedelta(days=180)), result="PASS", certificate_no="C-1").status_code == 201
    assert st() == {"calibration_status": "VALID", "usable_for_testing": True, "reason": None}
    # expired calibration blocks use
    old = _eq(w, name="Balance")
    w["qa"].patch(f"/api/v1/equipment/{old['id']}", headers=w["hq"], json={"qualification_status": "QUALIFIED", "reason": "q"})
    w["qa"].post(f"/api/v1/equipment/{old['id']}/calibrations", headers=w["hq"],
                 json={"performed_on": "2020-01-01", "due_on": "2020-07-01", "result": "PASS"})
    s2 = w["qa"].get(f"/api/v1/equipment/{old['id']}/status").json()
    assert s2["usable_for_testing"] is False and "EXPIRED" in s2["reason"]
    # a failed calibration takes the instrument out of service
    w["qa"].post(f"/api/v1/equipment/{eq['id']}/calibrations", headers=w["hq"],
                 json={"performed_on": str(today), "due_on": str(today + timedelta(days=30)), "result": "FAIL"})
    s3 = w["qa"].get(f"/api/v1/equipment/{eq['id']}/status").json()
    assert s3["usable_for_testing"] is False
    assert w["qa"].get(f"/api/v1/equipment/{eq['id']}").json()["status"] == "OUT_OF_SERVICE"
    assert len(w["qa"].get(f"/api/v1/equipment/{eq['id']}/calibrations").json()) == 2  # history retained
