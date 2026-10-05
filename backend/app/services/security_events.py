from app.audit.context import get_context
from app.core import db
from app.core.logging import security_log
from app.models.audit import SecurityEvent


def log_security_event(event_type: str, *, user_id: int | None = None, username: str | None = None,
                       detail: str | None = None, ip: str | None = None) -> None:
    """Independent transaction so the record persists even if the request rolls back."""
    ctx = get_context()
    security_log.warning(detail or event_type, extra={"event": event_type, "user": username or ctx.user_name,
                                                      "ip": ip or ctx.ip_address,
                                                      "correlation_id": ctx.correlation_id})
    s = db.new_session()
    try:
        s.add(SecurityEvent(event_type=event_type, user_id=user_id, username=username or ctx.user_name,
                            ip_address=ip or ctx.ip_address, detail=detail,
                            correlation_id=ctx.correlation_id))
        s.commit()
    finally:
        s.close()
