import struct
import zlib

from tests.conftest import login, make_user


def _png():
    def chunk(t, d):
        c = struct.pack(">I", len(d)) + t + d
        return c + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    raw = zlib.compress(b"\x00\xff\x00\x00")
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", raw) + chunk(b"IEND", b""))


def test_branding_is_public_and_logo_upload_validated(client, admin):
    assert client.get("/api/v1/company/branding").json()["name"] == "Acme Biologicals"
    bad = client.post("/api/v1/company/logo", headers=admin, params={"reason": "brand"},
                      files={"file": ("evil.png", b"MZ not an image", "image/png")})
    assert bad.status_code == 422
    exe = client.post("/api/v1/company/logo", headers=admin, params={"reason": "brand"},
                      files={"file": ("x.exe", b"MZ", "application/octet-stream")})
    assert exe.status_code == 422
    ok = client.post("/api/v1/company/logo", headers=admin, params={"reason": "brand"},
                     files={"file": ("logo.png", _png(), "image/png")})
    assert ok.status_code == 200 and len(ok.json()["sha256"]) == 64
    assert client.get("/api/v1/company/branding").json()["logo_url"]
    got = client.get("/api/v1/company/logo")
    assert got.status_code == 200 and got.headers["content-type"] == "image/png"


def test_numbering_config_change_audited_and_validated(client, admin):
    r = client.put("/api/v1/numbering/PO", headers=admin,
                   json={"prefix": "PUR", "format": "{prefix}/{yy}/{seq:05d}", "reset_policy": "YEARLY",
                         "reason": "site convention"})
    assert r.status_code == 200 and r.json()["prefix"] == "PUR"
    bad = client.put("/api/v1/numbering/PO", headers=admin,
                     json={"prefix": "PUR", "format": "{evil.__class__}", "reset_policy": "YEARLY", "reason": "x"})
    assert bad.status_code == 422


def test_system_config_requires_reason(client, admin):
    r = client.put("/api/v1/config/training.gate", headers=admin, json={"value": "true"})
    assert r.status_code == 422
    r = client.put("/api/v1/config/training.gate", headers=admin, json={"value": "true", "reason": "go-live policy"})
    assert r.status_code == 200


def test_dashboard_cards(client):
    make_user("mgr", ["MANAGEMENT"])
    login(client, "mgr")
    d = client.get("/api/v1/dashboard/summary").json()
    assert d["cards"]["pending_approvals"]["available"] is True
    assert d["cards"]["fg_available"] == {"label": "FG Batches Available", "value": 0, "available": True}
