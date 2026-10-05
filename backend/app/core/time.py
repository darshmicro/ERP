from datetime import datetime, timezone


def utcnow() -> datetime:
    """Server-generated, timezone-aware UTC time (ALCOA: contemporaneous)."""
    return datetime.now(timezone.utc)
