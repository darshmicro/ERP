"""Report engine: a registry of permissioned, parameterised reports with JSON / CSV / XLSX / PDF output and controlled-copy logging (spec 50, 66)."""
import csv
import hashlib
import io
import json
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.core.errors import NotFound, ValidationFailed
from app.models.reporting import ReportRun
from app.services import exports, numbering

MAX_ROWS = 50000


@dataclass
class Param:
    name: str
    label: str
    type: str = "text"                  # text / date / int / select
    options: list[str] = field(default_factory=list)
    required: bool = False


@dataclass
class Report:
    code: str
    title: str
    group: str
    perm: str
    columns: list[tuple[str, str]]
    fn: Callable[[Session, dict], list[dict]]
    params: list[Param] = field(default_factory=list)
    description: str = ""


REGISTRY: dict[str, Report] = {}


def register(code: str, title: str, group: str, perm: str, columns: list[tuple[str, str]], params: list[Param] | None = None, description: str = ""):
    def deco(fn):
        REGISTRY[code] = Report(code, title, group, perm, columns, fn, params or [], description)
        return fn
    return deco


def _clean(v: Any) -> Any:
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, datetime):
        return (v.astimezone(timezone.utc) if v.tzinfo else v).strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(v, date):
        return v.isoformat()
    return v


def parse_params(rep: Report, raw: dict[str, str]) -> dict:
    out: dict[str, Any] = {}
    for p in rep.params:
        v = raw.get(p.name)
        if v in (None, ""):
            if p.required:
                raise ValidationFailed(f"Parameter '{p.label}' is required", code="PARAM_REQUIRED")
            continue
        if p.type == "date":
            try:
                out[p.name] = date.fromisoformat(v)
            except ValueError:
                raise ValidationFailed(f"Parameter '{p.label}' must be a date (YYYY-MM-DD)")
        elif p.type == "int":
            try:
                out[p.name] = int(v)
            except ValueError:
                raise ValidationFailed(f"Parameter '{p.label}' must be a number")
        elif p.type == "select":
            if p.options and v not in p.options:
                raise ValidationFailed(f"Parameter '{p.label}' must be one of {p.options}")
            out[p.name] = v
        else:
            out[p.name] = v.strip()
    return out


def run(session: Session, code: str, raw_params: dict[str, str], limit: int | None = None) -> tuple[Report, dict, list[dict], bool]:
    rep = REGISTRY.get(code)
    if rep is None:
        raise NotFound(f"Unknown report '{code}'")
    params = parse_params(rep, raw_params)
    rows = rep.fn(session, params)
    truncated = False
    cap = limit if limit is not None else MAX_ROWS
    if len(rows) > cap:
        rows, truncated = rows[:cap], True
    rows = [{k: _clean(v) for k, v in r.items()} for r in rows]
    return rep, params, rows, truncated


def to_csv(rep: Report, rows: list[dict]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([label for _k, label in rep.columns])
    for r in rows:
        w.writerow([("" if r.get(k) is None else exports.safe_text(r.get(k))) for k, _l in rep.columns])
    return ("﻿" + buf.getvalue()).encode("utf-8")


def to_xlsx(rep: Report, params: dict, rows: list[dict], user: str, company: str) -> bytes:
    return exports.build_xlsx(rep.title, {k: _clean(v) for k, v in params.items()}, rep.columns, rows, user, company)


def to_pdf(rep: Report, params: dict, rows: list[dict], user: str, company: str, copy_no: str, logo: bytes | None = None) -> bytes:
    from app.reports.pdf import table_report
    return table_report(rep.title, company, {k: _clean(v) for k, v in params.items()}, rep.columns, rows, user, copy_no, logo)


def next_copy_no(session: Session) -> str:
    return numbering.next_number(session, numbering.default_plant_id(session), "REPORTCOPY")


def log_run(session: Session, *, copy_no: str, code: str, title: str, params: dict, fmt: str, rows: int | None, data: bytes, user, ref_entity: str | None = None,
            ref_id: str | None = None) -> ReportRun:
    r = ReportRun(copy_no=copy_no, report_code=code, title=title, params_json=json.dumps({k: _clean(v) for k, v in params.items()}, default=str), output_format=fmt, row_count=rows,
                  sha256=hashlib.sha256(data).hexdigest(), user_id=user.id, username=user.username, ref_entity=ref_entity, ref_id=ref_id)
    session.add(r)
    session.flush()
    return r
