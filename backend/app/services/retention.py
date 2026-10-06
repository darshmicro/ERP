"""Record retention and non-destructive archival (spec 81, BR-RET-001/002).

The application NEVER deletes GMP records. A retention policy states how long a record type must remain online; records older than the cut-off are
*eligible* for archival, and an archive package (XLSX + SHA-256, stored as a write-once controlled document) can be produced for them. Legal hold freezes a type.
Physical removal from the live database, if a site ever chooses it, is a separate DBA activity under change control after the archive is verified."""
import hashlib
import io
from datetime import date, datetime, time, timedelta, timezone

from openpyxl import Workbook
from sqlalchemy import func, inspect as sa_inspect, select
from sqlalchemy.orm import Session

from app.core.errors import BusinessRuleError, NotFound, ValidationFailed
from app.models.audit import AuditTrail, ESignature, SecurityEvent
from app.models.costing import BatchCost
from app.models.em import EMSample
from app.models.stability import StabilityResult
from app.models.dispatch import Dispatch
from app.models.manufacturing import ManufacturingBatch
from app.models.platform import Document
from app.models.qc import COA, QCResult
from app.models.quality import CAPA, Deviation
from app.models.reporting import ArchiveBatch, RetentionPolicy
from app.models.warehouse import InventoryTransaction, MaterialBatch
from app.services import documents, exports, numbering

# record type -> (label, model, date column, default years, regulatory basis)
SOURCES = {
    "audit_trail": ("Audit trail", AuditTrail, AuditTrail.occurred_at, 10, "21 CFR 11.10(e): at least as long as the underlying record"),
    "e_signature": ("Electronic signatures", ESignature, ESignature.signed_at, 10, "Linked to the signed record"),
    "security_event": ("Security events", SecurityEvent, SecurityEvent.occurred_at, 3, "Site IT security policy"),
    "inventory_transaction": ("Inventory ledger", InventoryTransaction, InventoryTransaction.txn_ts, 10, "EU GMP Ch.4: batch-related records"),
    "qc_result": ("QC results", QCResult, QCResult.entered_at, 10, "EU GMP Ch.6: at least 1 year after expiry / 5 years after certification"),
    "coa": ("Certificates of analysis", COA, COA.generated_at, 10, "EU GMP Ch.6"),
    "manufacturing_batch": ("Batch manufacturing records", ManufacturingBatch, ManufacturingBatch.created_at, 10, "EU GMP Ch.4.11: 1 year after expiry / 5 years after certification"),
    "dispatch": ("Distribution records", Dispatch, Dispatch.created_at, 10, "EU GDP Ch.4"),
    "deviation": ("Deviations", Deviation, Deviation.created_at, 10, "EU GMP Ch.1"),
    "capa": ("CAPA", CAPA, CAPA.created_at, 10, "EU GMP Ch.1"),
    "em_sample": ("Environmental monitoring samples", EMSample, EMSample.sampled_at, 10, "EU GMP Annex 1: monitoring records are batch-related evidence"),
    "stability_result": ("Stability results", StabilityResult, StabilityResult.entered_at, 10, "EU GMP Ch.6.30 / ICH Q1A: for the shelf life plus one year"),
    "batch_cost": ("Batch costs", BatchCost, BatchCost.created_at, 10, "Financial record retention per site policy"),
}


def seed_defaults(session: Session) -> None:
    for code, (label, _m, _c, years, basis) in SOURCES.items():
        if session.execute(select(RetentionPolicy.id).where(RetentionPolicy.record_type == code)).first() is None:
            session.add(RetentionPolicy(record_type=code, retention_years=years, basis=basis))


def policies(session: Session) -> list[dict]:
    out = []
    for p in session.execute(select(RetentionPolicy).order_by(RetentionPolicy.record_type)).scalars():
        src = SOURCES.get(p.record_type)
        if src is None:
            continue
        _label, Model, col, _y, _b = src
        cutoff = _cutoff(p)
        total = session.execute(select(func.count()).select_from(Model)).scalar()
        eligible = session.execute(select(func.count()).select_from(Model).where(col < cutoff, Model.id > _last_id(session, p.record_type))).scalar()
        arch = session.execute(select(func.coalesce(func.sum(ArchiveBatch.row_count), 0)).where(ArchiveBatch.record_type == p.record_type)).scalar()
        out.append({"id": p.id, "record_type": p.record_type, "label": src[0], "retention_years": p.retention_years, "legal_hold": p.legal_hold, "legal_hold_reason": p.legal_hold_reason, "basis": p.basis,
                    "cutoff": cutoff.date().isoformat(), "total_records": total, "eligible_for_archive": 0 if p.legal_hold else eligible, "archived_rows": int(arch), "last_archived_cutoff": p.last_archived_cutoff})
    return out


def _cutoff(p: RetentionPolicy) -> datetime:
    d = date.today() - timedelta(days=int(p.retention_years * 365.25))
    return datetime.combine(d, time.min, tzinfo=timezone.utc)


def update_policy(session: Session, p: RetentionPolicy, data: dict) -> None:
    if "retention_years" in data and data["retention_years"] < p.retention_years:
        raise BusinessRuleError("Retention periods may only be extended, never shortened, through the application (BR-RET-001); shortening needs a change control and DBA action", rule_id="BR-RET-001")
    if data.get("legal_hold") and not (data.get("legal_hold_reason") or p.legal_hold_reason or "").strip():
        raise ValidationFailed("A reason is required to place a legal hold", code="REASON_REQUIRED")
    for k, v in data.items():
        setattr(p, k, v)


MAX_ROWS_PER_PACKAGE = 100_000


def _last_id(session: Session, record_type: str) -> int:
    return int(session.execute(select(func.coalesce(func.max(ArchiveBatch.to_id), 0)).where(ArchiveBatch.record_type == record_type)).scalar() or 0)


def archive(session: Session, user, record_type: str) -> ArchiveBatch:
    """Package the next contiguous block (<= 100 000 rows) of records older than the cut-off that were not archived before. Re-run until nothing is left."""
    p = session.execute(select(RetentionPolicy).where(RetentionPolicy.record_type == record_type)).scalars().first()
    src = SOURCES.get(record_type)
    if p is None or src is None:
        raise NotFound("Unknown record type")
    if p.legal_hold:
        raise BusinessRuleError(f"{src[0]} are under LEGAL HOLD and cannot be archived (BR-RET-002)", rule_id="BR-RET-002")
    _label, Model, col, _y, _b = src
    cutoff = _cutoff(p)
    rows = session.execute(select(Model).where(col < cutoff, Model.id > _last_id(session, record_type)).order_by(Model.id).limit(MAX_ROWS_PER_PACKAGE)).scalars().all()
    if not rows:
        raise BusinessRuleError("No (further) records are older than the retention cut-off", rule_id="BR-RET-001")
    cols = [c.key for c in sa_inspect(Model).mapper.column_attrs if c.key not in set(getattr(Model, "__audit_sensitive__", ())) and c.key != "password_hash"]
    wb = Workbook(write_only=True)
    ws = wb.create_sheet(record_type[:31])
    ws.append([f"ARCHIVE PACKAGE — {src[0]} older than {cutoff.date().isoformat()}, ids {rows[0].id}–{rows[-1].id} (originals remain in the database)"])
    ws.append(cols)
    for r in rows:
        ws.append([_v(getattr(r, c)) for c in cols])
    buf = io.BytesIO()
    wb.save(buf)
    data = buf.getvalue()
    no = numbering.next_number(session, numbering.default_plant_id(session), "ARCHIVE")
    doc = documents.store(session, f"{no}-{record_type}.xlsx", data, allowed_ext={".xlsx"}, doc_no=no, version="1")
    ab = ArchiveBatch(archive_no=no, record_type=record_type, cutoff_date=cutoff.date(), row_count=len(rows), from_id=rows[0].id, to_id=rows[-1].id, document_id=doc.id,
                      sha256=hashlib.sha256(data).hexdigest(), created_by_id=user.id)
    session.add(ab)
    p.last_archived_cutoff = cutoff.date()
    session.flush()
    return ab


def _v(x):
    if isinstance(x, datetime):
        return (x.astimezone(timezone.utc) if x.tzinfo else x).replace(tzinfo=None)
    if hasattr(x, "__float__") and not isinstance(x, (int, float, bool)):
        return float(x)
    return exports.safe_text(x)
