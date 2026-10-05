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

    from datetime import date, timedelta
    from app.models.purchase import PurchaseOrder, PurchaseRequest, VendorQualification
    horizon = date.today() + timedelta(days=60)
    vq_due = s.execute(select(func.count()).select_from(VendorQualification).where(
        VendorQualification.status.in_(("APPROVED", "CONDITIONAL", "EXPIRED")),
        VendorQualification.requalification_due_date <= horizon)).scalar()
    open_po = s.execute(select(func.count()).select_from(PurchaseOrder).where(
        PurchaseOrder.status.in_(("PENDING_APPROVAL", "APPROVED", "PARTIALLY_RECEIVED")))).scalar()
    open_pr = s.execute(select(func.count()).select_from(PurchaseRequest).where(
        PurchaseRequest.status.in_(("SUBMITTED", "DEPARTMENT_APPROVED", "APPROVED")))).scalar()

    from app.models.warehouse import InventoryBalance, MaterialBatch
    quarantine = s.execute(select(func.count(func.distinct(MaterialBatch.id))).select_from(MaterialBatch).join(
        InventoryBalance, InventoryBalance.material_batch_id == MaterialBatch.id).where(
        MaterialBatch.disposition.in_(("QUARANTINE", "QC_TESTING", "QC_APPROVED", "QA_REVIEW")), InventoryBalance.qty_on_hand > 0)).scalar()
    near_exp = s.execute(select(func.count()).select_from(MaterialBatch).where(
        MaterialBatch.disposition == "APPROVED", MaterialBatch.expiry_date <= date.today() + timedelta(days=90))).scalar()

    from app.models.dispatch import Dispatch
    from app.models.manufacturing import ManufacturingBatch
    from app.models.master import Material, MaterialType

    def lots_in(*disp):
        return s.execute(select(func.count()).select_from(MaterialBatch).where(MaterialBatch.disposition.in_(disp))).scalar()
    active_batches = s.execute(select(func.count()).select_from(ManufacturingBatch).where(
        ManufacturingBatch.status.in_(("CREATED", "MATERIAL_ISSUED", "IN_PROCESS", "PRODUCTION_COMPLETE", "RECONCILED", "QC_QA")))).scalar()
    fg_avail = s.execute(select(func.count(func.distinct(MaterialBatch.id))).select_from(MaterialBatch).join(
        InventoryBalance, InventoryBalance.material_batch_id == MaterialBatch.id).join(Material, Material.id == MaterialBatch.material_id).join(
        MaterialType, MaterialType.id == Material.type_id).where(MaterialType.code == "FG", MaterialBatch.disposition == "APPROVED",
                                                                 InventoryBalance.qty_on_hand > 0)).scalar()
    disp_pending = s.execute(select(func.count()).select_from(Dispatch).where(Dispatch.status.in_(("DRAFT", "VALIDATED", "APPROVED")))).scalar()

    from app.models.quality import CAPA, Deviation
    open_dev = s.execute(select(func.count()).select_from(Deviation).where(Deviation.status.notin_(("CLOSED", "CANCELLED")))).scalar()
    open_capa = s.execute(select(func.count()).select_from(CAPA).where(CAPA.status.notin_(("CLOSED", "CANCELLED")))).scalar()
    overdue_capa = s.execute(select(func.count()).select_from(CAPA).where(CAPA.status.in_(("OPEN", "IN_PROGRESS")), CAPA.due_date < date.today())).scalar()

    def card(label, value):
        return {"label": label, "value": value, "available": True}

    return {"cards": {
        "pending_approvals": {"label": "Pending Approvals", "value": pending, "available": True},
        "quarantine_materials": {"label": "Quarantine Lots", "value": quarantine, "available": True},
        "qc_pending": card("QC Pending (lots)", lots_in("QUARANTINE", "QC_TESTING")), "qa_pending": card("QA Pending (lots)", lots_in("QC_APPROVED", "QA_REVIEW")),
        "vendor_qualification_due": {"label": "Vendor Qualification Due (60 d)", "value": vq_due, "available": True},
        "near_expiry": {"label": "Near Expiry (90 d)", "value": near_exp, "available": True}, "open_purchase_orders": {"label": "Open Purchase Orders", "value": open_po, "available": True},
        "open_purchase_requests": {"label": "Open Purchase Requests", "value": open_pr, "available": True},
        "active_production_batches": card("Active Production Batches", active_batches),
        "fg_available": card("FG Batches Available", fg_avail), "dispatch_pending": card("Dispatch Pending", disp_pending),
        "open_deviations": card("Open Deviations", open_dev), "open_capa": card("Open CAPA", open_capa), "overdue_capa": card("Overdue CAPA", overdue_capa)},
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
