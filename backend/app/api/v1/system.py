from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.api.deps import Principal, current_user, get_db, require
from app.core.errors import NotFound
from app.core.time import utcnow
from app.models.platform import Notification
from app.schemas.platform import NotificationOut
from app.workflows import approval

router = APIRouter(tags=["system"])


@router.get("/health/live")
def live():
    return {"status": "ok"}


@router.get("/health/ready")
def ready(s: Session = Depends(get_db)):
    s.execute(text("SELECT 1"))
    return {"status": "ready"}


@router.get("/dashboard/summary")
def dashboard(p: Principal = Depends(require("dashboard.view.read")), s: Session = Depends(get_db)):
    """Home cards (spec 90). Cards backed by later phases report available=false until built."""
    pending = len(approval.pending_for_user(s, p.user.id))
    unread = s.execute(select(func.count()).select_from(Notification).where(
        Notification.user_id == p.user.id, Notification.read_at.is_(None))).scalar()

    def later(label, phase):
        return {"label": label, "value": None, "available": False, "phase": phase}

    return {"cards": {
        "pending_approvals": {"label": "Pending Approvals", "value": pending, "available": True},
        "quarantine_materials": later("Quarantine Materials", 4),
        "qc_pending": later("QC Pending", 5), "qa_pending": later("QA Pending", 5),
        "vendor_qualification_due": later("Vendor Qualification Due", 3),
        "near_expiry": later("Near Expiry", 4), "open_purchase_orders": later("Open Purchase Orders", 3),
        "active_production_batches": later("Active Production Batches", 6),
        "fg_available": later("FG Available", 7), "dispatch_pending": later("Dispatch Pending", 7)},
        "unread_notifications": unread}


@router.get("/notifications", response_model=list[NotificationOut])
def notifications(unread_only: bool = False, p: Principal = Depends(require("notification.own.read")),
                  s: Session = Depends(get_db)):
    stmt = select(Notification).where(Notification.user_id == p.user.id)
    if unread_only:
        stmt = stmt.where(Notification.read_at.is_(None))
    return s.execute(stmt.order_by(Notification.id.desc()).limit(100)).scalars().all()


@router.post("/notifications/{nid}/read")
def mark_read(nid: int, p: Principal = Depends(require("notification.own.read")), s: Session = Depends(get_db)):
    n = s.get(Notification, nid)
    if n is None or n.user_id != p.user.id:
        raise NotFound("Notification not found")
    n.read_at = utcnow()
    s.commit()
    return {"ok": True}
