"""Audit trail writer with HMAC hash chain.

Entries are queued on the Session and written in the *same transaction* as the business change
(before_commit). The chain head row is updated first, which serialises writers so the chain is
linear. If audit writing fails, the whole transaction rolls back (BR-AUD-002).
"""
import hashlib
import hmac
import json
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Iterable

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.audit.context import get_context
from app.core import db
from app.core.config import get_settings
from app.core.time import utcnow
from app.models.audit import AuditChainHead, AuditTrail

GENESIS = "GENESIS"
_HASH_FIELDS = ("occurred_at", "tz_name", "module", "entity", "record_id", "action", "field_name",
                "old_value", "new_value", "user_id", "user_name", "role_name", "session_id",
                "ip_address", "device_info", "reason", "signature_id", "correlation_id")


def to_text(v: Any) -> str | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, Enum):
        return str(v.value)
    if isinstance(v, (Decimal, int, float, bool, str)):
        return str(v)
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return json.dumps(v, default=str, sort_keys=True)


def _canonical(fields: dict) -> str:
    out = {}
    for k in _HASH_FIELDS:
        v = fields.get(k)
        out[k] = v.isoformat() if isinstance(v, datetime) else v
    return json.dumps(out, sort_keys=True, separators=(",", ":"), default=str)


def compute_hash(prev_hash: str, fields: dict) -> str:
    key = get_settings().audit_hmac_key.encode()
    return hmac.new(key, (prev_hash + "|" + _canonical(fields)).encode(), hashlib.sha256).hexdigest()


def _pending(session: Session) -> list[dict]:
    return session.info.setdefault("audit_pending", [])


def log_event(session: Session, *, module: str, entity: str, record_id: Any, action: str,
              field_name: str | None = None, old: Any = None, new: Any = None,
              reason: str | None = None, signature_id: int | None = None) -> None:
    """Queue an audit entry for the current transaction."""
    ctx = get_context()
    _pending(session).append({
        "occurred_at": utcnow(), "tz_name": "UTC", "module": module, "entity": entity,
        "record_id": None if record_id is None else str(record_id), "action": action,
        "field_name": field_name, "old_value": to_text(old), "new_value": to_text(new),
        "user_id": ctx.user_id, "user_name": ctx.user_name, "role_name": ctx.role_name,
        "session_id": ctx.session_id, "ip_address": ctx.ip_address, "device_info": ctx.device_info,
        "reason": reason if reason is not None else ctx.reason, "signature_id": signature_id,
        "correlation_id": ctx.correlation_id,
    })


def log_event_independent(**kwargs: Any) -> None:
    """Write an audit entry in its own transaction (e.g. failed login that must persist)."""
    s = db.new_session()
    try:
        log_event(s, **kwargs)
        s.commit()
    finally:
        s.close()


def flush_pending(session: Session) -> None:
    entries: list[dict] = session.info.get("audit_pending") or []
    if not entries:
        return
    session.info["audit_pending"] = []
    _write_chain(session, entries)


def _write_chain(session: Session, entries: Iterable[dict]) -> None:
    # 1) take the head row lock (UPDATE first => exclusive row lock until commit)
    session.execute(update(AuditChainHead).where(AuditChainHead.id == 1)
                    .values(lock_counter=AuditChainHead.lock_counter + 1))
    head = session.execute(select(AuditChainHead).where(AuditChainHead.id == 1)).scalar_one_or_none()
    if head is None:  # first ever write (seed normally creates it)
        head = AuditChainHead(id=1, lock_counter=1, last_hash=GENESIS, row_count=0)
        session.add(head)
        session.flush()
    prev = head.last_hash
    n = 0
    for e in entries:
        h = compute_hash(prev, e)
        session.add(AuditTrail(**e, prev_hash=prev, row_hash=h))
        session.flush()  # keep identity order == chain order
        prev = h
        n += 1
    head.last_hash = prev
    head.row_count = (head.row_count or 0) + n


def verify_chain(session: Session, batch: int = 1000) -> dict:
    prev = GENESIS
    checked = 0
    last_id = 0
    while True:
        rows = session.execute(select(AuditTrail).where(AuditTrail.id > last_id)
                               .order_by(AuditTrail.id).limit(batch)).scalars().all()
        if not rows:
            break
        for r in rows:
            fields = {k: getattr(r, k) for k in _HASH_FIELDS}
            if r.prev_hash != prev or compute_hash(prev, fields) != r.row_hash:
                return {"ok": False, "checked": checked, "first_bad_audit_id": r.id}
            prev = r.row_hash
            checked += 1
            last_id = r.id
    head = session.execute(select(AuditChainHead).where(AuditChainHead.id == 1)).scalar_one_or_none()
    if head is not None and (head.last_hash != prev or head.row_count != checked):
        return {"ok": False, "checked": checked, "first_bad_audit_id": None,
                "detail": "chain head does not match table tail (rows removed or appended out-of-band)"}
    return {"ok": True, "checked": checked, "first_bad_audit_id": None}
