import csv
import io
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import Principal, get_db, require
from app.api.helpers import page_args
from app.audit import service as audit
from app.models.audit import AuditTrail, ESignature, SecurityEvent

router = APIRouter(tags=["audit"])

COLS = ["id", "occurred_at", "tz_name", "module", "entity", "record_id", "action", "field_name", "old_value",
        "new_value", "user_id", "user_name", "role_name", "session_id", "ip_address", "device_info", "reason",
        "signature_id", "correlation_id"]


def _filtered(entity, record_id, module, user_name, action, date_from, date_to):
    stmt = select(AuditTrail)
    if entity:
        stmt = stmt.where(AuditTrail.entity == entity)
    if record_id:
        stmt = stmt.where(AuditTrail.record_id == record_id)
    if module:
        stmt = stmt.where(AuditTrail.module == module)
    if user_name:
        stmt = stmt.where(AuditTrail.user_name == user_name)
    if action:
        stmt = stmt.where(AuditTrail.action == action)
    if date_from:
        stmt = stmt.where(AuditTrail.occurred_at >= date_from)
    if date_to:
        stmt = stmt.where(AuditTrail.occurred_at <= date_to)
    return stmt


def _row(r: AuditTrail) -> dict:
    d = {c: getattr(r, c) for c in COLS}
    d["occurred_at"] = r.occurred_at.isoformat()
    return d


@router.get("/audit-trail")
def list_audit(entity: str | None = None, record_id: str | None = None, module: str | None = None,
               user_name: str | None = None, action: str | None = None, date_from: datetime | None = None,
               date_to: datetime | None = None, before_id: int | None = None, limit: int = Query(100),
               p: Principal = Depends(require("audit.trail.read")), s: Session = Depends(get_db)):
    """Keyset pagination (before_id) - the audit trail is large."""
    limit, _ = page_args(limit, 0)
    stmt = _filtered(entity, record_id, module, user_name, action, date_from, date_to)
    if before_id:
        stmt = stmt.where(AuditTrail.id < before_id)
    rows = s.execute(stmt.order_by(AuditTrail.id.desc()).limit(limit + 1)).scalars().all()
    more = len(rows) > limit
    rows = rows[:limit]
    return {"items": [_row(r) for r in rows], "next_before_id": rows[-1].id if more and rows else None}


@router.get("/audit-trail/export")
def export_audit(entity: str | None = None, record_id: str | None = None, module: str | None = None,
                 user_name: str | None = None, action: str | None = None, date_from: datetime | None = None,
                 date_to: datetime | None = None, p: Principal = Depends(require("audit.trail.export")),
                 s: Session = Depends(get_db)):
    stmt = _filtered(entity, record_id, module, user_name, action, date_from, date_to)
    rows = s.execute(stmt.order_by(AuditTrail.id.desc()).limit(100_000)).scalars().all()
    buf = io.StringIO()
    buf.write(f"# GMP-MERP audit trail export; generated {datetime.utcnow().isoformat()}Z by {p.user.username}\n")
    buf.write(f"# filters: entity={entity} record_id={record_id} module={module} user={user_name} "
              f"action={action} from={date_from} to={date_to}\n")
    w = csv.DictWriter(buf, fieldnames=COLS)
    w.writeheader()
    for r in rows:
        w.writerow({k: ("" if v is None else v) for k, v in _row(r).items()})
    audit.log_event(s, module="audit", entity="audit_trail", record_id=None, action="EXPORT",
                    new=f"{len(rows)} rows")
    s.commit()
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=audit_trail.csv"})


@router.get("/audit-trail/verify")
def verify(p: Principal = Depends(require("audit.trail.verify")), s: Session = Depends(get_db)):
    return audit.verify_chain(s)


@router.get("/security-events")
def security_events(event_type: str | None = None, before_id: int | None = None, limit: int = 100,
                    p: Principal = Depends(require("security.event.read")), s: Session = Depends(get_db)):
    limit, _ = page_args(limit, 0)
    stmt = select(SecurityEvent)
    if event_type:
        stmt = stmt.where(SecurityEvent.event_type == event_type)
    if before_id:
        stmt = stmt.where(SecurityEvent.id < before_id)
    rows = s.execute(stmt.order_by(SecurityEvent.id.desc()).limit(limit)).scalars().all()
    return {"items": [{"id": r.id, "occurred_at": r.occurred_at.isoformat(), "event_type": r.event_type,
                       "username": r.username, "ip_address": r.ip_address, "detail": r.detail} for r in rows]}


@router.get("/esignatures")
def signatures(entity: str, record_id: str, p: Principal = Depends(require("esign.record.read")),
               s: Session = Depends(get_db)):
    rows = s.execute(select(ESignature).where(ESignature.entity == entity, ESignature.record_id == record_id)
                     .order_by(ESignature.id)).scalars().all()
    return [{"id": r.id, "printed_name": r.printed_name, "username": r.username, "role": r.role_name,
             "meaning": r.meaning, "signed_at": r.signed_at.isoformat(), "tz": r.tz_name, "reason": r.reason,
             "record_hash": r.record_hash, "manifest_hash": r.manifest_hash} for r in rows]
