"""Phase 11: reports, dashboards and exports for EM, stability and costing."""
import pytest

from tests.conftest import PW
from tests.workflows import test_phase11_em as emt
from tests.workflows import test_phase11_stability as stab

pytestmark = pytest.mark.filterwarnings("ignore")
R = "/api/v1/reports"


def test_reports_and_dashboards_for_new_modules(app):
    w = stab.w.__wrapped__(app)
    from tests.helpers import as_user
    w["ca"], w["hca"] = as_user(app, "cost1", ["COSTING_ANALYST"])
    w["fh"], w["hfh"] = as_user(app, "fin1", ["FINANCE_HEAD"])
    st = stab.study(w, stab.protocol(w))
    pull = next(p for p in st["pulls"] if p["month"] == 0)
    w["qc"].post(f"/api/v1/stability/pulls/{pull['id']}/pull", headers=w["hqc"], json={"reason": "pulled"})
    stab.enter_pass(w, pull["id"], assay=97.0)                                 # OOS -> deviation
    rows = w["qo"].get(f"{R}/stability-schedule").json()["rows"]
    assert len(rows) == 6 and {r["status"] for r in rows} == {"SCHEDULED", "PULLED"}
    res = w["qo"].get(f"{R}/stability-results").json()["rows"]
    assert {r["pass_fail"] for r in res} == {"PASS", "FAIL"}
    # EM: needs limits + a sample; reuse the EM helpers with this world's QA users
    emw = {"qo": w["qo"], "hqo": w["hqo"], "qa": w["qa"], "hqa": w["hqa"], "qc": w["qc"], "hqc": w["hqc"]}
    emt.approved_limits(emw)
    loc = emt.location(emw)
    emt.result(emw, emt.sample(emw, loc)["id"], 12)
    em_rows = w["qo"].get(f"{R}/em-results?outcome=ACTION").json()["rows"]
    assert len(em_rows) == 1 and em_rows[0]["outcome"] == "ACTION" and em_rows[0]["grade"] == "B"
    assert w["qo"].get(f"{R}/em-schedule").status_code == 200
    # exports work and are logged
    assert w["qo"].get(f"{R}/em-results/export?format=csv").status_code == 200
    # costing reports are visible to finance only
    assert w["qo"].get(f"{R}/batch-cost").status_code == 403
    assert w["fh"].get(f"{R}/inventory-valuation").status_code == 200
    # dashboards
    mon = w["qa"].get(f"/api/v1/dashboards/monitoring").json()
    assert "cards" in mon, mon
    cards = {c["label"]: c["value"] for c in mon["cards"]}
    assert cards["EM action-limit results (30 d)"] == 1 and cards["Active stability studies"] == 1 and cards["Stability pulls awaiting QA review"] == 0
    assert w["qc"].get(f"/api/v1/dashboards/costing").status_code == 403
    assert w["fh"].get(f"/api/v1/dashboards/costing").status_code == 200
    assert "monitoring" in w["qa"].get(f"/api/v1/dashboards").json() and "costing" not in w["qa"].get(f"/api/v1/dashboards").json()
