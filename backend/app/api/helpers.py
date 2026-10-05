from app.audit.context import get_context, set_reason


def use_reason(body_reason: str | None) -> None:
    """Body `reason` overrides the X-Change-Reason header for this request's audit context."""
    if body_reason and body_reason.strip():
        set_reason(body_reason)


def page_args(limit: int, offset: int) -> tuple[int, int]:
    return max(1, min(limit, 200)), max(0, offset)
