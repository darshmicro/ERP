"""Phase 9 endpoints: report engine, controlled documents, dashboards, retention/archive, backup status."""
import json
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

import app.reports.catalog  # noqa: F401  (registers the reports)
from app.api.crud import to_dict
from app.api.deps import Principal, get_db, get_principal, require
from app.api.helpers import page_args, use_reason
from app.audit import service as audit
from app.core.errors import NotFound, PermissionDenied, ValidationFailed
from app.models.dispatch import Dispatch
from app.models.manufacturing import ManufacturingBatch
from app.models.org import Company
from app.models.platform import Document
from app.models.purchase import PurchaseOrder
from app.models.reporting import ArchiveBatch, BackupRecord, ReportRun, RetentionPolicy
from app.models.warehouse import GRN
from app.reports import engine
from app.schemas.common import Reasoned
from app.services import backup, dashboards, documents, masters, pdf_docs, retention

router = APIRouter()
MIME = {"xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "csv": "text/csv; charset=utf-8", "pdf": "application/pdf"}


def _company(s: Session) -> str:
    return s.execute(select(Company.name)).scalars().first() or "GMP-MERP"


def _logo(s: Session):
    return pdf_docs._company(s)[1]


# ============================================================ report engine
@router.get("/reports", tags=["Reports"])
def catalogue(p: Principal = Depends(require("reports.catalog.read"))):
    """Only reports the caller may run are listed (the report's own read permission is required in addition)."""
    return [{"code": r.code, "title": r.title, "group": r.group, "description": r.description, "can_export": "reports.export.run" in p.perms,
             "params": [{"name": x.name, "label": x.label, "type": x.type, "options": x.options, "required": x.required} for x in r.params],
             "columns": [{"key": k, "label": l} for k, l in r.columns]} for r in engine.REGISTRY.values() if r.perm in p.perms]


def _authorise(code: str, p: Principal):
    rep = engine.REGISTRY.get(code)
    if rep is None:
        raise NotFound(f"Unknown report '{code}'")
    if rep.perm not in p.perms:
        raise PermissionDenied("You are not authorised to run this report.")
    return rep


@router.get("/reports/{code}", tags=["Reports"])
def run_report(code: str, request: Request, limit: int = Query(500, ge=1, le=5000), p: Principal = Depends(require("reports.catalog.read")), s: Session = Depends(get_db)):
    _authorise(code, p)
    rep, params, rows, truncated = engine.run(s, code, {k: v for k, v in request.query_params.items() if k != "limit"}, limit)
    return {"code": rep.code, "title": rep.title, "columns": [{"key": k, "label": l} for k, l in rep.columns], "rows": rows, "count": len(rows), "truncated": truncated}


@router.get("/reports/{code}/export", tags=["Reports"])
def export_report(code: str, request: Request, format: str = Query("xlsx", pattern="^(xlsx|csv|pdf)$"), p: Principal = Depends(require("reports.catalog.read", "reports.export.run")),
                  s: Session = Depends(get_db)):
    _authorise(code, p)
    raw = {k: v for k, v in request.query_params.items() if k != "format"}
    rep, params, rows, truncated = engine.run(s, code, raw)
    copy_no = engine.next_copy_no(s)
    company = _company(s)
    data = (engine.to_xlsx(rep, params, rows, p.user.username, company) if format == "xlsx" else engine.to_csv(rep, rows) if format == "csv"
            else engine.to_pdf(rep, params, rows, p.user.username, company, copy_no, _logo(s)))
    run = engine.log_run(s, copy_no=copy_no, code=code, title=rep.title, params=params, fmt=format, rows=len(rows), data=data, user=p.user)
    audit.log_event(s, module="report", entity="report_run", record_id=run.id, action="EXPORT", new=f"{code} {format} {len(rows)} rows copy {copy_no}")
    s.commit()
    return Response(data, media_type=MIME[format], headers={"Content-Disposition": f'attachment; filename="{code}-{copy_no}.{format}"', "X-Controlled-Copy": copy_no,
                                                          "X-Content-SHA256": run.sha256, "X-Truncated": str(truncated).lower()})


@router.get("/report-runs", tags=["Reports"])
def report_runs(limit: int = Query(50), offset: int = Query(0), report_code: str | None = None, p: Principal = Depends(require("reports.run.read")), s: Session = Depends(get_db)):
    limit, offset = page_args(limit, offset)
    stmt = select(ReportRun)
    if report_code:
        stmt = stmt.where(ReportRun.report_code == report_code)
    total = s.execute(select(func.count()).select_from(stmt.subquery())).scalar()
    rows = s.execute(stmt.order_by(ReportRun.id.desc()).limit(limit).offset(offset)).scalars().all()
    return {"items": [to_dict(r) for r in rows], "total": total, "limit": limit, "offset": offset}


@router.get("/reports-verify", tags=["Reports"])
def verify_copy(copy_no: str, sha256: str, p: Principal = Depends(require("reports.run.read")), s: Session = Depends(get_db)):
    """Check a printout: does the copy number exist and does the supplied SHA-256 match the hash recorded when it was produced?"""
    r = s.execute(select(ReportRun).where(ReportRun.copy_no == copy_no)).scalars().first()
    if r is None:
        raise NotFound("Unknown controlled-copy number")
    return {"copy_no": copy_no, "report": r.title, "printed_by": r.username, "run_at": r.run_at.isoformat(), "matches": r.sha256.lower() == sha256.strip().lower()}


# ============================================================ controlled business documents (PDF)
def _doc_response(s: Session, p: Principal, code: str, title: str, data: bytes, copy_no: str, ref_entity: str, ref_id: int) -> Response:
    run = engine.log_run(s, copy_no=copy_no, code=code, title=title, params={}, fmt="pdf", rows=None, data=data, user=p.user, ref_entity=ref_entity, ref_id=str(ref_id))
    audit.log_event(s, module="report", entity=ref_entity, record_id=ref_id, action="PRINT", new=f"{title} copy {copy_no}")
    s.commit()
    return Response(data, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{code}-{copy_no}.pdf"', "X-Controlled-Copy": copy_no, "X-Content-SHA256": run.sha256})


@router.get("/purchase-orders/{rid}/pdf", tags=["Documents"])
def po_pdf(rid: int, p: Principal = Depends(require("po.order.read", "reports.export.run")), s: Session = Depends(get_db)):
    po = masters.get_or_404(s, PurchaseOrder, rid, "Purchase order")
    c = engine.next_copy_no(s)
    return _doc_response(s, p, "po-pdf", f"Purchase Order {po.po_no}", pdf_docs.po_pdf(s, po, p.user.username, c), c, "purchase_order", po.id)


@router.get("/grn/{rid}/pdf", tags=["Documents"])
def grn_pdf(rid: int, p: Principal = Depends(require("grn.receipt.read", "reports.export.run")), s: Session = Depends(get_db)):
    g = masters.get_or_404(s, GRN, rid, "GRN")
    c = engine.next_copy_no(s)
    return _doc_response(s, p, "grn-pdf", f"GRN {g.grn_no}", pdf_docs.grn_pdf(s, g, p.user.username, c), c, "grn", g.id)


@router.get("/dispatches/{rid}/pdf", tags=["Documents"])
def dispatch_pdf(rid: int, p: Principal = Depends(require("dispatch.order.read", "reports.export.run")), s: Session = Depends(get_db)):
    d = masters.get_or_404(s, Dispatch, rid, "Dispatch")
    c = engine.next_copy_no(s)
    return _doc_response(s, p, "dispatch-pdf", f"Dispatch note {d.dispatch_no}", pdf_docs.dispatch_pdf(s, d, p.user.username, c), c, "dispatch", d.id)


@router.get("/mfg/batches/{rid}/pdf", tags=["Documents"])
def batch_pdf(rid: int, p: Principal = Depends(require("mfg.batch.read", "reports.export.run")), s: Session = Depends(get_db)):
    b = masters.get_or_404(s, ManufacturingBatch, rid, "Batch")
    c = engine.next_copy_no(s)
    return _doc_response(s, p, "batch-record-pdf", f"Batch record {b.batch_no}", pdf_docs.batch_record_pdf(s, b, p.user.username, c), c, "manufacturing_batch", b.id)


# ============================================================ dashboards
@router.get("/dashboards/{name}", tags=["Dashboards"])
def dashboard(name: str, p: Principal = Depends(get_principal), s: Session = Depends(get_db)):
    d = dashboards.DASHBOARDS.get(name)
    if d is None:
        raise NotFound("Unknown dashboard")
    fn, perm = d
    if perm not in p.perms:
        raise PermissionDenied("You are not authorised to view this dashboard.")
    return {"name": name, **fn(s)}


@router.get("/dashboards", tags=["Dashboards"])
def dashboard_list(p: Principal = Depends(get_principal)):
    return [n for n, (_f, perm) in dashboards.DASHBOARDS.items() if perm in p.perms]


# ============================================================ retention / archive
@router.get("/retention/policies", tags=["Retention"])
def list_policies(p: Principal = Depends(require("retention.policy.read")), s: Session = Depends(get_db)):
    return retention.policies(s)


class PolicyUpdate(Reasoned):
    model_config = {"extra": "forbid"}
    retention_years: int | None = Field(default=None, ge=1, le=100)
    legal_hold: bool | None = None
    legal_hold_reason: str | None = None
    basis: str | None = None


@router.patch("/retention/policies/{pid}", tags=["Retention"])
def update_policy(pid: int, body: PolicyUpdate, p: Principal = Depends(require("retention.policy.update")), s: Session = Depends(get_db)):
    use_reason(body.reason)
    pol = masters.get_or_404(s, RetentionPolicy, pid, "Retention policy")
    retention.update_policy(s, pol, body.model_dump(exclude={"reason"}, exclude_unset=True))
    s.commit()
    return to_dict(pol)


@router.post("/retention/archive/{record_type}", status_code=201, tags=["Retention"])
def create_archive(record_type: str, p: Principal = Depends(require("retention.archive.create")), s: Session = Depends(get_db)):
    use_reason("Archive package created")
    ab = retention.archive(s, p.user, record_type)
    audit.log_event(s, module="retention", entity="archive_batch", record_id=ab.id, action="ARCHIVE", new=f"{record_type} {ab.row_count} rows {ab.archive_no}")
    s.commit()
    return to_dict(ab)


@router.get("/retention/archives", tags=["Retention"])
def list_archives(p: Principal = Depends(require("retention.archive.read")), s: Session = Depends(get_db)):
    return [to_dict(a) for a in s.execute(select(ArchiveBatch).order_by(ArchiveBatch.id.desc())).scalars()]


@router.get("/retention/archives/{aid}/download", tags=["Retention"])
def download_archive(aid: int, p: Principal = Depends(require("retention.archive.read")), s: Session = Depends(get_db)):
    ab = masters.get_or_404(s, ArchiveBatch, aid, "Archive")
    doc = s.get(Document, ab.document_id)
    data = documents.read(s, doc)          # verifies the stored hash (BR-DOC-001)
    return Response(data, media_type=MIME["xlsx"], headers={"Content-Disposition": f'attachment; filename="{ab.archive_no}.xlsx"', "X-Content-SHA256": ab.sha256})


# ============================================================ backup status
class BackupIn(BaseModel):
    backup_type: str
    performed_at: datetime
    result: str = Field(default="SUCCESS", pattern="^(SUCCESS|FAILED)$")
    location: str | None = None
    size_mb: int | None = Field(default=None, ge=0)
    sha256: str | None = Field(default=None, min_length=64, max_length=64)
    tool: str | None = None
    notes: str | None = None
    audit_chain_verified: bool | None = None
    rto_minutes: int | None = Field(default=None, ge=0)


@router.get("/backup/status", tags=["Backup"])
def backup_status(p: Principal = Depends(require("backup.status.read")), s: Session = Depends(get_db)):
    return backup.status(s)


@router.post("/backup/records", status_code=201, tags=["Backup"])
def record_backup(body: BackupIn, p: Principal = Depends(require("backup.status.record")), s: Session = Depends(get_db)):
    data = body.model_dump()
    if data["performed_at"].tzinfo is None:
        from datetime import timezone
        data["performed_at"] = data["performed_at"].replace(tzinfo=timezone.utc)
    b = backup.record(s, p.user, data)
    audit.log_event(s, module="backup", entity="backup_record", record_id=b.id, action="RECORD", new=f"{b.backup_type} {b.result}")
    s.commit()
    return to_dict(b)


@router.get("/backup/records", tags=["Backup"])
def backup_records(limit: int = Query(50), p: Principal = Depends(require("backup.status.read")), s: Session = Depends(get_db)):
    return [to_dict(b) for b in s.execute(select(BackupRecord).order_by(BackupRecord.performed_at.desc()).limit(min(limit, 200))).scalars()]
