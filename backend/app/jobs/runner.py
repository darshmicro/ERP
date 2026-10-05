"""Scheduled jobs (system actions). Run from the in-process scheduler or `scripts/run_jobs.py` (cron / Task Scheduler).

Jobs are idempotent, run as the audit user "SYSTEM", and every status change they cause is audited and
written to the GMP status history.
"""
import threading

from app.audit.context import AuditContext, audit_context
from app.core import db
from app.core.logging import app_log
from app.services import lots, vendor_qualification as vqs


def run_daily_jobs() -> dict:
    s = db.new_session()
    try:
        with audit_context(AuditContext(user_name="SYSTEM", reason="Scheduled job")):
            expired = vqs.expire_due(s)
            alerts = vqs.alert_upcoming(s)
            lots_expired = lots.expire_lots(s)
            alerts += lots.alert_expiry(s)
            s.commit()
        app_log.info("daily jobs: %d vendor qualifications expired, %d alerts", len(expired), alerts)
        return {"vendor_qualifications_expired": expired, "lots_expired": lots_expired, "alerts": alerts}
    except Exception:  # noqa: BLE001
        s.rollback()
        app_log.exception("daily jobs failed")
        raise
    finally:
        s.close()


class Scheduler:
    """Minimal in-process scheduler. Run it in ONE instance only (or use cron); jobs are idempotent anyway."""

    def __init__(self, interval_seconds: int = 3600):
        self._stop = threading.Event()
        self._interval = interval_seconds
        self._thread = threading.Thread(target=self._loop, name="merp-scheduler", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.wait(self._interval):
            try:
                run_daily_jobs()
            except Exception:  # noqa: BLE001
                pass
