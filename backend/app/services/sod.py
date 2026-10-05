"""Segregation of duties (spec 8, Doc 04). Driven by sod_rule + record_action history."""
from sqlalchemy import false as sa_false, true as sa_true
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.context import get_context
from app.core.errors import SegregationOfDutiesError
from app.core.logging import security_log
from app.models.audit import RecordAction, SecurityEvent
from app.models.iam import SodRule


def record_action(session: Session, entity: str, record_id, action_code: str, user_id: int | None = None) -> None:
    uid = user_id or get_context().user_id
    if uid is None:
        raise ValueError("record_action requires a user")
    session.add(RecordAction(entity=entity, record_id=str(record_id), action_code=action_code, user_id=uid))


def check(session: Session, user_id: int, entity: str, record_id, action_code: str) -> list[str]:
    """Raise if user previously performed a conflicting action on the same record.
    Returns warnings for WARN-level rules."""
    rules = session.execute(select(SodRule).where(SodRule.action_code == action_code,
                                                  SodRule.is_active == sa_true())).scalars().all()
    warnings: list[str] = []
    for r in rules:
        done = session.execute(select(RecordAction.id).where(
            RecordAction.entity == entity, RecordAction.record_id == str(record_id),
            RecordAction.action_code == r.conflicts_with_action_code,
            RecordAction.user_id == user_id).limit(1)).first()
        if not done:
            continue
        msg = (f"Segregation of duties ({r.sod_id}): you already performed "
               f"'{r.conflicts_with_action_code}' on this record and cannot '{action_code}' it.")
        if r.enforcement == "BLOCK":
            _log_violation(user_id, msg, r.sod_id)
            raise SegregationOfDutiesError(msg, rule_id=r.sod_id)
        warnings.append(msg)
    return warnings


def _log_violation(user_id: int, msg: str, rule_id: str) -> None:
    from app.core import db
    ctx = get_context()
    security_log.warning(msg, extra={"event": "SOD_VIOLATION", "rule_id": rule_id, "user": ctx.user_name})
    s = db.new_session()
    try:
        s.add(SecurityEvent(event_type="SOD_VIOLATION", user_id=user_id, username=ctx.user_name,
                            ip_address=ctx.ip_address, detail=msg, correlation_id=ctx.correlation_id))
        s.commit()
    finally:
        s.close()
