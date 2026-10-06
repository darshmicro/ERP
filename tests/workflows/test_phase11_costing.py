"""Phase 11c: costing."""
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core import db
from app.core.errors import BusinessRuleError
from app.models import LotCost, MaterialBatch
from tests.conftest import PW
from tests.helpers import as_user, make_lot, raw
from tests.workflows.test_dispatch import build_dispatch_world

pytestmark = pytest.mark.filterwarnings("ignore")
API = "/api/v1/costing"


@pytest.fixture()
def w(app):
    w = build_dispatch_world(app)
    w["ca"], w["hca"] = as_user(app, "cost1", ["COSTING_ANALYST"])
    w["fh"], w["hfh"] = as_user(app, "fin1", ["FINANCE_HEAD"])
    w["both"], w["hboth"] = as_user(app, "cost_both", ["COSTING_ANALYST", "FINANCE_HEAD"])
    return w


def approved_card(w, **over):
    body = {"title": "FY rates", "labour_rate_per_hour": 100, "machine_rate_per_hour": 50, "overhead_pct": 10, "reason": "annual rates", **over}
    r = w["ca"].post(f"{API}/rate-cards", headers=w["hca"], json=body)
    assert r.status_code == 201, r.text
    c = r.json()
    assert w["ca"].post(f"{API}/rate-cards/{c['id']}/submit", headers=w["hca"]).status_code == 200
    a = w["fh"].post(f"{API}/rate-cards/{c['id']}/approve", headers=w["hfh"], json={"password": PW, "reason": "approved"})
    assert a.status_code == 200, a.text
    return a.json()


def calc(w, labour=10, machine=5, who="ca"):
    return w[who].post(f"{API}/batches/{w['batch']['id']}/calculate", headers=w["h" + who], json={"labour_hours": labour, "machine_hours": machine, "reason": "month-end"})


def test_rate_card_is_controlled_and_needed_for_costing(w):
    assert calc(w).status_code == 409                                    # BR-COST-003: no approved card
    c = w["ca"].post(f"{API}/rate-cards", headers=w["hca"], json={"title": "Draft rates", "labour_rate_per_hour": 80, "machine_rate_per_hour": 40, "overhead_pct": 5, "reason": "n"}).json()
    assert w["ca"].post(f"{API}/rate-cards/{c['id']}/approve", headers=w["hca"], json={"password": PW, "reason": "x"}).status_code == 403   # analyst cannot approve
    w["both"].post(f"{API}/rate-cards/{c['id']}/submit", headers=w["hboth"])
    own = w["both"].post(f"{API}/rate-cards", headers=w["hboth"], json={"title": "Own rates", "labour_rate_per_hour": 1, "machine_rate_per_hour": 1, "reason": "n"}).json()
    w["both"].post(f"{API}/rate-cards/{own['id']}/submit", headers=w["hboth"])
    r = w["both"].post(f"{API}/rate-cards/{own['id']}/approve", headers=w["hboth"], json={"password": PW, "reason": "self"})
    assert r.status_code in (403, 409) and "SOD-41" in r.text
    card = approved_card(w)
    assert card["status"] == "APPROVED" and card["card_no"].startswith("CRC-")
    assert w["ca"].patch(f"{API}/rate-cards/{card['id']}", headers=w["hca"], json={"labour_rate_per_hour": 1, "reason": "tamper"}).status_code in (409, 422)   # approved = immutable


def test_batch_cost_is_derived_from_issues_and_rolls_into_the_output_lot(w):
    approved_card(w)
    assert w["ca"].put(f"{API}/standards", headers=w["hca"], json={"material_id": w["product"], "std_unit_cost": 3, "reason": "standard set"}).status_code == 200
    r = calc(w)
    assert r.status_code == 200, r.text
    bc = r.json()
    # 10 kg issued at the PO rate 25.50 (tax excluded) + 10 h x 100 + 5 h x 50 + 10 % overhead on conversion
    assert bc["material_cost"] == 255.0 and bc["labour_cost"] == 1000.0 and bc["machine_cost"] == 250.0 and bc["overhead_cost"] == 125.0
    assert bc["total_cost"] == 1630.0 and bc["output_qty"] == 98.0 and bc["unit_cost"] == pytest.approx(1630 / 98, abs=1e-6)
    assert bc["standard_unit_cost"] == 3.0 and bc["variance"] == pytest.approx(1630 - 3 * 98) and bc["status"] == "DRAFT"
    assert len(bc["lines"]) == 1 and bc["lines"][0]["basis"] == "PO_RATE" and bc["lines"][0]["unit_cost"] == "25.500000"
    # recalculation with new hours is allowed while DRAFT
    assert calc(w, labour=12).json()["labour_cost"] == 1200.0
    # approval: analyst cannot; the calculating person cannot (SOD-42); finance head can
    assert w["ca"].post(f"{API}/batch-costs/{bc['id']}/approve", headers=w["hca"], json={"password": PW, "reason": "x"}).status_code == 403
    assert calc(w, who="both").status_code == 200
    s = w["both"].post(f"{API}/batch-costs/{bc['id']}/approve", headers=w["hboth"], json={"password": PW, "reason": "self"})
    assert s.status_code in (403, 409) and "SOD-42" in s.text
    assert w["fh"].post(f"{API}/batch-costs/{bc['id']}/approve", headers=w["hfh"], json={"password": "bad", "reason": "x"}).status_code == 401
    ap = w["fh"].post(f"{API}/batch-costs/{bc['id']}/approve", headers=w["hfh"], json={"password": PW, "reason": "costs verified"})
    assert ap.status_code == 200 and ap.json()["status"] == "APPROVED" and ap.json()["approved_signature_id"]
    # the finished-goods lot now carries the batch cost; an approved cost is locked
    lot = w["fh"].get(f"{API}/lots/{w['fg_lot']}").json()
    assert lot["current"]["basis"] == "BATCH_COST" and lot["current"]["unit_cost"] == pytest.approx(ap.json()["unit_cost"])
    assert calc(w, who="both").status_code == 409
    # the cost history is append-only
    with pytest.raises(Exception):
        raw("UPDATE lot_cost SET unit_cost = 0")
    # valuation uses the current lot cost
    v = w["fh"].get(f"{API}/valuation").json()
    fg = next(i for i in v["items"] if i["lot_id"] == w["fg_lot"])
    assert fg["basis"] == "BATCH_COST" and float(fg["value"]) == pytest.approx(float(fg["qty_on_hand"]) * ap.json()["unit_cost"], abs=0.01) and float(v["total_value"]) > 0


def test_uncosted_lot_blocks_instead_of_being_valued_at_zero(w):
    from app.services import costing
    lot_id = make_lot(w["material"], w["ids"]["kg"], w["aloc"], qty=5)
    s = db.new_session()
    with pytest.raises(BusinessRuleError) as e:
        costing.ensure_lot_cost(s, s.get(MaterialBatch, lot_id), None)
    assert "BR-COST-001" in str(e.value.rule_id)
    s.close()
    # manual cost needs a reason and permission
    assert w["ca"].post(f"{API}/lots/{lot_id}/cost", headers=w["hca"], json={"unit_cost": 20}).status_code == 422
    ok = w["ca"].post(f"{API}/lots/{lot_id}/cost", headers=w["hca"], json={"unit_cost": 20, "reason": "invoice 4411"})
    assert ok.status_code == 201 and ok.json()["basis"] == "MANUAL"
    assert w["ca"].post(f"{API}/lots/{lot_id}/cost", headers=w["hca"], json={"unit_cost": -1, "reason": "x"}).status_code == 422
    v = w["ca"].get(f"{API}/valuation").json()
    assert next(i for i in v["items"] if i["lot_id"] == lot_id)["value"] == "100.0000"
    assert v["uncosted_lots"] >= 1          # other stock without a cost basis is reported, not valued


def test_cost_data_is_restricted(w):
    assert w["qo"].get(f"{API}/valuation").status_code == 403
    assert w["qa"].get(f"{API}/batch-costs").status_code == 403
    assert w["pr"].get(f"{API}/rate-cards").status_code == 403           # production sees no cost data
    assert w["ds"].get(f"{API}/valuation").status_code == 403
    # management and auditors read costs but cannot change them; admin holds no costing rights at all
    from app.models import Permission, Role, RolePermission
    s = db.new_session()

    def perms(role):
        return set(s.execute(select(Permission.perm_code).join(RolePermission, RolePermission.permission_id == Permission.id).join(Role, Role.id == RolePermission.role_id)
                             .where(Role.role_code == role, Permission.module == "costing")).scalars())
    assert "costing.valuation.read" in perms("MANAGEMENT") and not {p for p in perms("MANAGEMENT") if p.endswith((".update", ".approve", ".set", ".calculate"))}
    assert perms("AUDITOR") and perms("SYSTEM_ADMIN") == set()
    s.close()
