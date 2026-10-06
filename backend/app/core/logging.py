"""Four separated log streams (spec 63): application, security; audit and GMP history are DB tables."""
import json
import logging
import logging.handlers
import os
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for k in ("correlation_id", "user", "ip", "rule_id", "event"):
            if hasattr(record, k):
                data[k] = getattr(record, k)
        if record.exc_info:
            data["exc"] = self.formatException(record.exc_info)
        return json.dumps(data, default=str)


def setup_logging(log_dir: str) -> None:
    os.makedirs(log_dir, exist_ok=True)
    for name, fname in (("merp.app", "application.log"), ("merp.security", "security.log")):
        lg = logging.getLogger(name)
        lg.setLevel(logging.INFO)
        lg.propagate = False
        if not lg.handlers:
            h = logging.handlers.RotatingFileHandler(
                os.path.join(log_dir, fname), maxBytes=20_000_000, backupCount=20, encoding="utf-8")
            h.setFormatter(JsonFormatter())
            lg.addHandler(h)


app_log = logging.getLogger("merp.app")
security_log = logging.getLogger("merp.security")
