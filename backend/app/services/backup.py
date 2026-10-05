"""Backup / restore evidence and status (spec 82). The application records evidence and flags overdue backups; it does not execute backup tooling."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.errors import ValidationFailed
from app.core.time import utcnow
from app.models.reporting import BackupRecord
from app.services import config_service

TYPES = ("FULL", "DIFFERENTIAL", "LOG", "DOCUMENTS", "RESTORE_TEST")


def record(session: Session, user, data: dict) -> BackupRecord:
    if data["backup_type"] not in TYPES:
        raise ValidationFailed(f"backup_type must be one of {TYPES}")
    if data["performed_at"] > utcnow() + timedelta(minutes=5):
        raise ValidationFailed("performed_at cannot be in the future")
    b = BackupRecord(recorded_by_id=user.id, **data)
    session.add(b)
    session.flush()
    return b


def _last(session: Session, t: str, ok_only=True):
    q = select(BackupRecord).where(BackupRecord.backup_type == t)
    if ok_only:
        q = q.where(BackupRecord.result == "SUCCESS")
    return session.execute(q.order_by(BackupRecord.performed_at.desc())).scalars().first()


def _sqlserver_last_backup(session: Session):
    """Best effort: read msdb.dbo.backupset when the app login is allowed to (normally it is not; failure is ignored)."""
    if session.bind.dialect.name != "mssql":
        return None
    try:
        row = session.execute(text("SELECT TOP 1 backup_finish_date, type FROM msdb.dbo.backupset WHERE database_name = DB_NAME() ORDER BY backup_finish_date DESC")).first()
        return {"finished_at": row[0].isoformat(), "type": row[1]} if row else None
    except Exception:  # noqa: BLE001
        session.rollback()
        return None


def status(session: Session) -> dict:
    now = datetime.now(timezone.utc)
    rpo_h = int(config_service.get(session, "backup.max_age_hours", "26") or 26)
    full, diff, log, docs, rt = (_last(session, t) for t in ("FULL", "DIFFERENTIAL", "LOG", "DOCUMENTS", "RESTORE_TEST"))
    newest = max([x.performed_at for x in (full, diff, log) if x] or [None], default=None) if any((full, diff, log)) else None
    age_h = round((now - (newest if newest.tzinfo else newest.replace(tzinfo=timezone.utc))).total_seconds() / 3600, 1) if newest else None
    restore_days = int(config_service.get(session, "backup.restore_test_days", "180") or 180)
    rt_age = (now - (rt.performed_at if rt.performed_at.tzinfo else rt.performed_at.replace(tzinfo=timezone.utc))).days if rt else None

    def d(x):
        return None if x is None else {"type": x.backup_type, "performed_at": x.performed_at.isoformat(), "location": x.location, "size_mb": x.size_mb, "tool": x.tool, "audit_chain_verified": x.audit_chain_verified, "rto_minutes": x.rto_minutes}
    alerts = []
    if newest is None:
        alerts.append("No successful backup has been recorded.")
    elif age_h > rpo_h:
        alerts.append(f"Last successful backup is {age_h} h old (limit {rpo_h} h).")
    if rt is None:
        alerts.append("No restore test has ever been recorded.")
    elif rt_age > restore_days:
        alerts.append(f"Last restore test was {rt_age} days ago (limit {restore_days} days).")
    return {"ok": not alerts, "alerts": alerts, "max_age_hours": rpo_h, "last_backup_age_hours": age_h, "last_full": d(full), "last_differential": d(diff), "last_log": d(log), "last_documents": d(docs),
            "last_restore_test": d(rt), "database_reported": _sqlserver_last_backup(session)}
