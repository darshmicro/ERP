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
