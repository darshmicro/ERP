"""In-app notifications (email delivery is a later step; rows carry emailed_at for the mailer)."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.iam import Role, User, UserRole
from app.models.platform import Notification
from datetime import date


def users_with_roles(session: Session, role_codes: list[str]) -> list[int]:
    today = date.today()
    q = (select(User.id).join(UserRole, UserRole.user_id == User.id).join(Role, Role.id == UserRole.role_id)
         .where(Role.role_code.in_(role_codes), UserRole.revoked_at.is_(None), UserRole.is_disabled == False,  # noqa: E712
                UserRole.valid_from <= today, (UserRole.valid_to.is_(None)) | (UserRole.valid_to >= today),
                User.is_active == True))  # noqa: E712
    return sorted(set(session.execute(q).scalars().all()))


def notify_roles(session: Session, role_codes: list[str], *, category: str, title: str, body: str | None = None,
                 ref_entity: str | None = None, ref_id: str | None = None) -> int:
    """Create one notification per user unless an identical unread one exists (job runs are idempotent)."""
    n = 0
    for uid in users_with_roles(session, role_codes):
        dup = session.execute(select(Notification.id).where(
            Notification.user_id == uid, Notification.category == category, Notification.title == title,
            Notification.ref_entity == ref_entity, Notification.ref_id == ref_id,
            Notification.read_at.is_(None)).limit(1)).first()
        if not dup:
            session.add(Notification(user_id=uid, category=category, title=title, body=body,
                                     ref_entity=ref_entity, ref_id=ref_id))
            n += 1
    return n
