"""Table-driven CRUD router factory for simple, audited master data."""
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Callable

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, create_model
from sqlalchemy import String, func, inspect as sa_inspect, or_, select
from sqlalchemy.orm import Session

from app.api.deps import Principal, get_db, require
from app.api.helpers import page_args, use_reason
from app.audit import service as audit
from app.core.errors import NotFound
from app.models.org import Company
from app.schemas.common import Reasoned
from app.services import exports, masters

TECH = {"row_version", "updated_at", "updated_by_id", "created_by_id"}


def to_dict(obj: Any, exclude: set[str] | None = None) -> dict:
    skip = TECH | (exclude or set()) | set(getattr(type(obj), "__audit_sensitive__", ()))
    out: dict[str, Any] = {}
    for attr in sa_inspect(obj).mapper.column_attrs:
        if attr.key in skip:
            continue
        v = getattr(obj, attr.key)
        if isinstance(v, Decimal):
            v = float(v)
        elif isinstance(v, (datetime, date)):
            v = v.isoformat()
        out[attr.key] = v
    return out


class _Strict(Reasoned):
    model_config = ConfigDict(extra="forbid")


def make_models(name: str, fields: list[tuple[str, Any, bool]]) -> tuple[type[BaseModel], type[BaseModel]]:
    """fields: (name, python type, required_on_create). Update model = all optional."""
    create_f = {n: (t if req else t | None, ... if req else None) for n, t, req in fields}
    upd_f = {n: (t | None, None) for n, t, _r in fields}
    return (create_model(f"{name}Create", __base__=_Strict, **create_f),
            create_model(f"{name}Update", __base__=_Strict, **upd_f))


def company_name(s: Session) -> str:
    return s.execute(select(Company.name)).scalars().first() or ""


def xlsx_response(s: Session, p: Principal, title: str, filters: dict, columns: list[tuple[str, str]],
                  rows: list[dict], entity: str) -> Response:
    data = exports.build_xlsx(title, filters, columns, rows, p.user.username, company_name(s))
    audit.log_event(s, module="export", entity=entity, record_id=None, action="EXPORT", new=f"{len(rows)} rows")
    s.commit()
    return Response(content=data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{entity}.xlsx"'})


def crud_router(*, prefix: str, tag: str, Model: type, perm: str, fields: list[tuple[str, Any, bool]],
                search_cols: list[str], code_field: str | None = None, doc_type: str | None = None,
                filters: list[str] | None = None, unique: list[str] | None = None,
                before_save: Callable[[Session, dict, Any], None] | None = None,
                after_create: Callable[[Session, Any], None] | None = None,
                export_perm: str = "md.master.export") -> APIRouter:
    router = APIRouter(prefix=prefix, tags=[tag])
    Create, Update = make_models(Model.__name__, fields)
    filters = filters or []
    unique = unique or []
    columns = [(c.name, c.name.replace("_", " ").title()) for c in Model.__table__.columns
               if c.name not in TECH | {"created_by_id"} and c.name not in getattr(Model, "__audit_sensitive__", ())]

    def _query(request: Request, q: str | None):
        stmt = select(Model)
        if q:
            like = f"%{q.lower()}%"
            stmt = stmt.where(or_(*[func.lower(getattr(Model, c)).like(like) for c in search_cols]))
        for f in filters:
            v = request.query_params.get(f)
            if v not in (None, ""):
                col = getattr(Model, f)
                if str(col.type).upper().startswith("BOOL"):
                    v = v.lower() in ("1", "true", "yes")
                stmt = stmt.where(col == v)
        return stmt

    @router.get("")
    def list_(request: Request, q: str | None = None, limit: int = Query(50), offset: int = Query(0),
              p: Principal = Depends(require(f"{perm}.read")), s: Session = Depends(get_db)):
        limit, offset = page_args(limit, offset)
        stmt = _query(request, q)
        total = s.execute(select(func.count()).select_from(stmt.subquery())).scalar()
        rows = s.execute(stmt.order_by(Model.id).limit(limit).offset(offset)).scalars().all()
        return {"items": [to_dict(r) for r in rows], "total": total, "limit": limit, "offset": offset}

    @router.get("/export")
    def export(request: Request, q: str | None = None, p: Principal = Depends(require(f"{perm}.read", export_perm)),
               s: Session = Depends(get_db)):
        rows = [to_dict(r) for r in s.execute(_query(request, q).order_by(Model.id).limit(50_000)).scalars()]
        flt = {"search": q, **{f: request.query_params.get(f) for f in filters}}
        return xlsx_response(s, p, f"{tag} list", flt, columns, rows, Model.__tablename__)

    @router.post("", status_code=201)
    def create(body: Create, p: Principal = Depends(require(f"{perm}.create")), s: Session = Depends(get_db)):  # type: ignore[valid-type]
        use_reason(body.reason)
        data = body.model_dump(exclude={"reason"}, exclude_none=True)
        if code_field and not data.get(code_field):
            from app.services import numbering
            data[code_field] = numbering.next_number(s, numbering.default_plant_id(s), doc_type or "")
        for u in unique:
            if data.get(u) is not None:
                masters.ensure_unique(s, Model, u, data[u])
        masters.check_foreign_keys(s, Model, data)
        if before_save:
            before_save(s, data, None)
        obj = Model(**data)
        s.add(obj)
        s.flush()
        if after_create:
            after_create(s, obj)
        s.commit()
        return to_dict(obj)

    @router.get("/{record_id}")
    def get(record_id: int, p: Principal = Depends(require(f"{perm}.read")), s: Session = Depends(get_db)):
        return to_dict(masters.get_or_404(s, Model, record_id, tag))

    @router.patch("/{record_id}")
    def update(record_id: int, body: Update, p: Principal = Depends(require(f"{perm}.update")),  # type: ignore[valid-type]
               s: Session = Depends(get_db)):
        use_reason(body.reason)
        obj = masters.get_or_404(s, Model, record_id, tag)
        data = body.model_dump(exclude={"reason"}, exclude_unset=True)
        for u in unique:
            if data.get(u) is not None:
                masters.ensure_unique(s, Model, u, data[u], exclude_id=obj.id)
        masters.check_foreign_keys(s, Model, data)
        if before_save:
            before_save(s, data, obj)
        for k, v in data.items():
            setattr(obj, k, v)
        s.commit()
        return to_dict(obj)

    return router
