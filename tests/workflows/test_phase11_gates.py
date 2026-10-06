"""Phase 11: instrument gate and window rules shared by EM and stability."""
import pytest

from tests.workflows import test_phase11_em as emt
from tests.workflows import test_phase11_stability as stab

pytestmark = pytest.mark.filterwarnings("ignore")


def test_em_sampling_refuses_an_unqualified_or_uncalibrated_instrument(app):
    w = emt.w.__wrapped__(app)
    emt.approved_limits(w)
    loc = emt.location(w)
    eq = w["qo"].post("/api/v1/equipment", headers=w["hqo"], json={"name": "Particle counter", "reason": "register"}).json()["id"]
    r = w["qc"].post("/api/v1/em/samples", headers=w["hqc"], json={"em_location_id": loc, "sample_type": "NONVIABLE_05", "equipment_id": eq, "reason": "x"})
    assert r.status_code == 409 and "BR-QC-002" in r.text
    # without an instrument (e.g. settle plate) sampling is fine
    assert w["qc"].post("/api/v1/em/samples", headers=w["hqc"], json={"em_location_id": loc, "sample_type": "SETTLE_PLATE", "reason": "x"}).status_code == 201


def test_stability_result_refuses_an_unqualified_instrument(app):
    w = stab.w.__wrapped__(app)
    st = stab.study(w, stab.protocol(w))
    pull = next(p for p in st["pulls"] if p["month"] == 0)
    w["qc"].post(f"/api/v1/stability/pulls/{pull['id']}/pull", headers=w["hqc"], json={"reason": "pulled"})
    eq = w["qo"].post("/api/v1/equipment", headers=w["hqo"], json={"name": "HPLC", "reason": "register"}).json()["id"]
    r = w["qc"].post(f"/api/v1/stability/pulls/{pull['id']}/results", headers=w["hqc"], json={"results": [{"parameter_id": w["assay"], "value": 100.0, "equipment_id": eq}], "reason": "x"})
    assert r.status_code == 409 and "BR-QC-002" in r.text
