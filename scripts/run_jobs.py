"""Run the scheduled jobs once (use from cron / Windows Task Scheduler, e.g. hourly)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.audit import hooks  # noqa: E402
from app.core import db  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.jobs.runner import run_daily_jobs  # noqa: E402

if __name__ == "__main__":
    db.configure(get_settings().database_url)
    hooks.install()
    import app.models  # noqa: F401
    print(run_daily_jobs())
