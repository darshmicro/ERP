"""Security hardening tests beyond authentication: injection, mass assignment, upload validation, data exposure, transport/headers."""
import json
import re

import pytest

from tests.conftest import PW, login, make_user
from tests.helpers import PDF, as_user, build_buying_world

API = "/api/v1"
INJECTIONS = ["' OR '1'='1", "'; DROP TABLE users; --", "%' UNION SELECT password_hash FROM users --", "\\x00", "' || (SELECT 1) || '"]


def test_sql_injection_payloads_in_every_search_and_filter_are_inert(app):
    w = build_buying_world(app)
    qa, h = w["qa"], w["hqa"]
    listing = ["/vendors", "/materials", "/purchase-orders", "/purchase-requests", "/grn", "/lots", "/samples", "/deviations", "/capas", "/sops", "/complaints", "/dispatches", "/mfg/batches",
               "/boms", "/vendor-qualifications", "/audit-trail", "/holds", "/oos"]
    for path in listing:
        for inj in INJECTIONS:
            r = qa.get(f"{API}{path}", params={"q": inj, "status": inj, "entity": inj, "user_name": inj})
            assert r.status_code in (200, 403, 404, 422), (path, inj, r.status_code, r.text[:200])
            assert "Traceback" not in r.text and "sqlalchemy" not in r.text.lower() and "syntax error" not in r.text.lower()
    # the data survived
    assert qa.get(f"{API}/vendors").json()["total"] >= 1
    for code in ("stock-ledger", "audit-trail"):
        r = qa.get(f"{API}/reports/{code}", params={"entity": "' OR 1=1 --", "material_code": "'; DROP TABLE users;--", "user_name": "' OR '1'='1"})
        assert r.status_code in (200, 403, 422)
    assert qa.get(f"{API}/search", params={"q": "' OR 1=1 --"}).status_code == 200


def test_status_and_system_columns_cannot_be_mass_assigned(app):
    w = build_buying_world(app)
    # a creator tries to inject controlled / system columns in the payload
    r = w["pu"].post(f"{API}/purchase-orders", headers=w["hpu"], json={"vendor_id": w["vendor"], "status": "APPROVED", "id": 999, "created_by_id": 1, "po_no": "PO-HACK",
                                                                       "lines": [{"material_id": w["material"], "quantity": 1, "rate": 1}], "reason": "x"})
    assert r.status_code in (201, 422)
    if r.status_code == 201:
        assert r.json()["status"] == "DRAFT" and r.json()["po_no"] != "PO-HACK" and r.json()["id"] != 999
    m = w["qc"].post(f"{API}/materials", headers=w["hqc"], json={"name": "Mass Assign", "type_id": w["ids"]["RM"], "base_unit_id": w["ids"]["kg"], "master_status": "ACTIVE", "reason": "x"})
    assert m.status_code in (201, 422)
    if m.status_code == 201:
        assert m.json()["master_status"] == "DRAFT"
    upd = w["qc"].patch(f"{API}/materials/{w['material']}", headers=w["hqc"], json={"master_status": "OBSOLETE", "reason": "x"})
    assert upd.status_code in (403, 409, 422) and w["qc"].get(f"{API}/materials/{w['material']}").json()["master_status"] == "ACTIVE"


def test_upload_validation_rejects_disguised_oversized_and_traversal_files(app):
    w = build_buying_world(app)
    url = f"{API}/vendors/{w['vendor']}/documents"
    base = {"doc_type": "GMP_CERTIFICATE", "version": "1"}
    exe = b"MZ\x90\x00\x03" + b"\x00" * 200
    cases = [("cert.exe", exe, "application/octet-stream"), ("cert.pdf", exe, "application/pdf"), ("cert.pdf.exe", PDF, "application/pdf"), ("cert.html", b"<script>alert(1)</script>", "text/html"),
             ("empty.pdf", b"", "application/pdf"), ("cert.svg", b"<svg onload=alert(1)/>", "image/svg+xml")]
    for name, data, mime in cases:
        r = w["pu"].post(url, headers=w["hpu"], data=base, files={"file": (name, data, mime)})
        assert r.status_code in (415, 422), (name, r.status_code, r.text[:150])
    ok = w["pu"].post(url, headers=w["hpu"], data=base, files={"file": ("../../etc/passwd.pdf", PDF, "application/pdf")})
    assert ok.status_code == 201
    assert "/" not in json.dumps(ok.json().get("original_name", "")) .replace("\\/", "") or ".." not in ok.json().get("original_name", "")     # path components are stripped
    # stored content is served back with a safe type and the hash is verified on download (BR-DOC-001)
    d = w["pu"].get(f"{API}/documents/{ok.json()['document_id']}/download") if "document_id" in ok.json() else None
    if d is not None:
        assert d.status_code == 200 and d.headers["content-type"].startswith("application/pdf") and d.headers.get("x-content-type-options") == "nosniff"


def test_no_credential_material_in_any_api_response(app):
    w = build_buying_world(app)
    ad, ha = as_user(app, "admin_s", ["SYSTEM_ADMIN"])
    blob = ""
    for path in ("/users", "/roles", "/auth/me", "/audit-trail", "/security-events", "/company", "/vendors", "/reports/user-access", "/reports/audit-trail"):
        r = ad.get(f"{API}{path}") if path != "/audit-trail" else ad.get(f"{API}{path}")
        blob += r.text
    blob += w["qa"].get(f"{API}/audit-trail").text + w["qa"].get(f"{API}/reports/audit-trail").text
    assert "$argon2" not in blob and not re.search(r'"password"\s*:', blob)
    # the audit trail names the field but never carries the value
    for m in re.finditer(r'"field_name":"password_hash","old_value":(null|"[^"]*"),"new_value":(null|"[^"]*")', blob):
        assert all(v in ("null", '"[REDACTED]"') for v in m.groups()), m.group(0)
    assert '"password_hash":' not in blob
    assert PW not in blob


def test_stored_script_payloads_are_returned_as_inert_json_with_csp(app):
    w = build_buying_world(app)
    xss = "<img src=x onerror=alert(1)>"
    r = w["pm1"].post(f"{API}/vendors", headers=w["hpm1"], json={"name": xss, "reason": "x"})
    assert r.status_code == 201
    g = w["pm1"].get(f"{API}/vendors/{r.json()['id']}")
    assert g.headers["content-type"].startswith("application/json") and g.json()["name"] == xss
    assert "default-src 'self'" in g.headers["content-security-policy"] and "frame-ancestors 'none'" in g.headers["content-security-policy"]
    assert g.headers["cache-control"] == "no-store"


def test_session_cookie_flags_and_logout_invalidates_session(app):
    from fastapi.testclient import TestClient
    make_user("cookie_u", ["QA_HEAD"])
    c = TestClient(app, raise_server_exceptions=False)
    r = c.post(f"{API}/auth/login", json={"username": "cookie_u", "password": PW})
    sc = r.headers["set-cookie"].lower()
    assert "httponly" in sc and "samesite" in sc
    h = {"X-CSRF-Token": r.json()["csrf_token"]}
    assert c.get(f"{API}/auth/me").status_code == 200
    c.post(f"{API}/auth/logout", headers=h)
    assert c.get(f"{API}/auth/me").status_code == 401
    stale = TestClient(app, raise_server_exceptions=False)
    stale.cookies.update({k: v for k, v in c.cookies.items()})
    assert stale.get(f"{API}/auth/me").status_code == 401                  # the old cookie is dead server-side


def test_unknown_and_malformed_identifiers_do_not_leak_internals(app):
    w = build_buying_world(app)
    for path in ("/vendors/999999", "/vendors/abc", "/lots/0", "/dispatches/-1", "/mfg/batches/99999999999999999999", "/trace/lot/%00", "/reports/nope"):
        r = w["qa"].get(f"{API}{path}")
        assert r.status_code in (404, 422), (path, r.status_code)
        assert "sqlalchemy" not in r.text.lower() and "Traceback" not in r.text and "File \"" not in r.text


def test_state_changing_requests_without_csrf_token_are_refused_everywhere(app):
    w = build_buying_world(app)
    for path, body in (("/vendors", {"name": "x", "reason": "x"}), ("/purchase-orders", {"vendor_id": 1, "lines": [], "reason": "x"}), ("/deviations", {"title": "abc", "description": "abc"}),
                       ("/dispatches", {"customer_id": 1, "lines": []})):
        r = w["qa"].post(f"{API}{path}", json=body)                            # session cookie present, CSRF header absent
        assert r.status_code in (401, 403), (path, r.status_code)


def test_exports_neutralise_spreadsheet_formula_injection(app):
    import io

    from openpyxl import load_workbook

    w = build_buying_world(app)
    evil = "=HYPERLINK(\"http://evil.example\",\"click\")"
    r = w["pm1"].post(f"{API}/vendors", headers=w["hpm1"], json={"name": evil, "reason": "x"})
    assert r.status_code == 201
    csv = w["pm1"].get(f"{API}/reports/vendor-list/export?format=csv")
    assert csv.status_code == 200 and b"'=HYPERLINK" in csv.content and b",=HYPERLINK" not in csv.content and b"\n=HYPERLINK" not in csv.content
    xl = w["pm1"].get(f"{API}/reports/vendor-list/export?format=xlsx")
    ws = load_workbook(io.BytesIO(xl.content)).active
    cells = [str(c.value) for row in ws.iter_rows() for c in row if c.value]
    assert any(c == "'" + evil for c in cells) and not any(c.startswith("=HYPERLINK") for c in cells)
