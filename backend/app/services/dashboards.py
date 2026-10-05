"""Role dashboards (spec 90): Management, QC, QA and Warehouse. Each returns KPI cards plus small data series the UI renders as charts/tables."""
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.dispatch import Dispatch
from app.models.manufacturing import ManufacturingBatch
from app.models.master import Material, MaterialType
from app.models.purchase import PurchaseOrder, VendorQualification
from app.models.qc import OOSInvestigation, OOTEvent, QCResult, QCTest, Sample
from app.models.quality import CAPA, SOP, ChangeControl, Complaint, Deviation, Recall
from app.models.warehouse import GRN, InventoryBalance, MaterialBatch, QualityHold, StorageTemperatureLog
from app.services import backup


def _n(s: Session, q) -> int:
    return int(s.execute(q).scalar() or 0)


def _count(s: Session, Model, *where) -> int:
    return _n(s, select(func.count()).select_from(Model).where(*where))


def _month_start() -> datetime:
    t = date.today().replace(day=1)
    return datetime.combine(t, time.min, tzinfo=timezone.utc)


def _group(s: Session, col, *where) -> list[dict]:
    return [{"label": str(k), "value": int(v)} for k, v in s.execute(select(col, func.count()).where(*where).group_by(col).order_by(col)).all()]


def card(label: str, value, tone: str = "") -> dict:
    return {"label": label, "value": value, "tone": tone}


def management(s: Session) -> dict:
    today = date.today()
    horizon = today + timedelta(days=60)
    cards = [
        card("Open purchase orders", _count(s, PurchaseOrder, PurchaseOrder.status.in_(("PENDING_APPROVAL", "APPROVED", "PARTIALLY_RECEIVED")))),
        card("Batches in progress", _count(s, ManufacturingBatch, ManufacturingBatch.status.in_(("CREATED", "MATERIAL_ISSUED", "IN_PROCESS", "PRODUCTION_COMPLETE", "RECONCILED", "QC_QA")))),
        card("Batches released (this month)", _count(s, ManufacturingBatch, ManufacturingBatch.status == "RELEASED", ManufacturingBatch.updated_at >= _month_start())),
        card("Dispatches (this month)", _count(s, Dispatch, Dispatch.status.in_(("DISPATCHED", "DELIVERED")), Dispatch.dispatched_at >= _month_start())),
        card("Open deviations", _count(s, Deviation, Deviation.status.notin_(("CLOSED", "CANCELLED"))), "warn"),
        card("Overdue CAPA", _count(s, CAPA, CAPA.status.in_(("OPEN", "IN_PROGRESS")), CAPA.due_date < today), "danger"),
        card("Open OOS", _count(s, OOSInvestigation, OOSInvestigation.status != "CLOSED"), "warn"),
        card("Vendor qualifications due (60 d)", _count(s, VendorQualification, VendorQualification.status.in_(("APPROVED", "CONDITIONAL", "EXPIRED")), VendorQualification.requalification_due_date <= horizon)),
        card("Open complaints", _count(s, Complaint, Complaint.status.in_(("RECEIVED", "INVESTIGATION")))),
        card("Active recalls", _count(s, Recall, Recall.status != "CLOSED"), "danger"),
    ]
    return {"cards": cards, "series": {"batches_by_status": _group(s, ManufacturingBatch.status), "deviations_by_severity": _group(s, Deviation.severity, Deviation.status.notin_(("CLOSED", "CANCELLED"))),
                                       "lots_by_disposition": _group(s, MaterialBatch.disposition)}}


def qc(s: Session) -> dict:
    now = datetime.now(timezone.utc)
    pending_tests = _count(s, QCTest, QCTest.status.in_(("ASSIGNED", "STARTED")))
    res_total = _count(s, QCResult)
    res_fail = _count(s, QCResult, QCResult.pass_fail == "FAIL")
    cards = [
        card("Samples awaiting testing", _count(s, Sample, Sample.status.in_(("CREATED", "TESTING")))),
        card("Tests pending", pending_tests),
        card("Open OOS", _count(s, OOSInvestigation, OOSInvestigation.status != "CLOSED"), "warn"),
        card("OOT events to review", _count(s, OOTEvent, OOTEvent.status == "OPEN")),
        card("Results entered (30 d)", _count(s, QCResult, QCResult.entered_at >= now - timedelta(days=30))),
        card("Failed results (all time)", res_fail, "warn" if res_fail else ""),
        card("Failure rate %", round(res_fail / res_total * 100, 2) if res_total else 0.0),
    ]
    return {"cards": cards, "series": {"samples_by_status": _group(s, Sample.status), "oos_by_status": _group(s, OOSInvestigation.status), "results_pass_fail": _group(s, QCResult.pass_fail)}}


def qa(s: Session) -> dict:
    today = date.today()
    cards = [
        card("Lots awaiting QA release", _count(s, MaterialBatch, MaterialBatch.disposition.in_(("QC_APPROVED", "QA_REVIEW")))),
        card("Open quality holds", _count(s, QualityHold, QualityHold.status == "OPEN"), "warn"),
        card("Open deviations", _count(s, Deviation, Deviation.status.notin_(("CLOSED", "CANCELLED"))), "warn"),
        card("Deviations in QA review", _count(s, Deviation, Deviation.status == "QA_REVIEW")),
        card("Open CAPA", _count(s, CAPA, CAPA.status.notin_(("CLOSED", "CANCELLED")))),
        card("Overdue CAPA", _count(s, CAPA, CAPA.status.in_(("OPEN", "IN_PROGRESS")), CAPA.due_date < today), "danger"),
        card("Change controls open", _count(s, ChangeControl, ChangeControl.status.notin_(("CLOSED", "REJECTED", "CANCELLED")))),
        card("SOP reviews due (30 d)", _count(s, SOP, SOP.status == "APPROVED", SOP.review_due_date <= today + timedelta(days=30))),
        card("Open complaints", _count(s, Complaint, Complaint.status.in_(("RECEIVED", "INVESTIGATION")))),
    ]
    return {"cards": cards, "series": {"deviations_by_status": _group(s, Deviation.status), "capa_by_status": _group(s, CAPA.status), "holds_by_source": _group(s, QualityHold.source, QualityHold.status == "OPEN")}}


def warehouse(s: Session) -> dict:
    today = date.today()
    now = datetime.now(timezone.utc)
    cards = [
        card("GRNs awaiting verification", _count(s, GRN, GRN.status == "SUBMITTED")),
        card("Lots in quarantine / QC", _count(s, MaterialBatch, MaterialBatch.disposition.in_(("QUARANTINE", "QC_TESTING", "QC_APPROVED", "QA_REVIEW")))),
        card("Approved lots expiring (90 d)", _count(s, MaterialBatch, MaterialBatch.disposition == "APPROVED", MaterialBatch.expiry_date <= today + timedelta(days=90), MaterialBatch.expiry_date >= today), "warn"),
        card("Expired lots on stock", _n(s, select(func.count(func.distinct(MaterialBatch.id))).select_from(MaterialBatch).join(InventoryBalance, InventoryBalance.material_batch_id == MaterialBatch.id).where(
            MaterialBatch.expiry_date < today, InventoryBalance.qty_on_hand > 0)), "danger"),
        card("Open quality holds", _count(s, QualityHold, QualityHold.status == "OPEN")),
        card("Temperature excursions (30 d)", _count(s, StorageTemperatureLog, StorageTemperatureLog.excursion == True, StorageTemperatureLog.recorded_at >= now - timedelta(days=30)), "warn"),  # noqa: E712
    ]
    by_type = [{"label": str(k), "value": float(v or 0)} for k, v in s.execute(
        select(MaterialType.code, func.sum(InventoryBalance.qty_on_hand)).select_from(InventoryBalance).join(MaterialBatch, MaterialBatch.id == InventoryBalance.material_batch_id).join(
            Material, Material.id == MaterialBatch.material_id).join(MaterialType, MaterialType.id == Material.type_id).group_by(MaterialType.code)).all()]
    return {"cards": cards, "series": {"lots_by_disposition": _group(s, MaterialBatch.disposition), "stock_by_material_type": by_type}}


def system_health(s: Session) -> dict:
    return {"backup": backup.status(s)}


DASHBOARDS = {"management": (management, "dashboard.management.read"), "qc": (qc, "dashboard.qc.read"), "qa": (qa, "dashboard.qa.read"), "warehouse": (warehouse, "dashboard.warehouse.read")}
