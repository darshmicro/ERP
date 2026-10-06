"""Printable labels (spec 22, 29, 52): company logo/name, status banner, Code128 + QR, controlled numbering,
template version, copy limits, reprint reasons, every print audited."""
import io
from datetime import date

from reportlab.graphics import renderPDF
from reportlab.graphics.barcode import code128, qr
from reportlab.graphics.shapes import Drawing
from reportlab.lib.colors import HexColor, black, white
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit import service as audit
from app.core.errors import BusinessRuleError, ValidationFailed
from app.models.master import Location, Material, Unit, Vendor
from app.models.org import Company
from app.models.platform import Document
from app.models.warehouse import MaterialBatch, MaterialLabel
from app.services import config_service, documents, lots, numbering
from app.audit.context import get_context

TEMPLATE_VERSION = "1"
W, H = 100 * mm, 70 * mm
BANNERS = {"QUARANTINE": "#d97706", "APPROVED": "#15803d", "SAMPLE": "#1d4ed8", "LOCATION": "#334155", "FG": "#15803d", "REJECTED": "#b91c1c"}


def _logo(session: Session) -> tuple[str, bytes | None]:
    c = session.execute(select(Company)).scalars().first()
    name = c.name if c else "GMP-MERP"
    data = None
    if c and c.logo_document_id:
        doc = session.get(Document, c.logo_document_id)
        if doc:
            try:
                data = documents.read_raw(doc)
            except Exception:  # noqa: BLE001
                data = None
    return name, data


def draw_label(c: canvas.Canvas, *, company: str, logo: bytes | None, banner: str, rows: list[tuple[str, str]],
               barcode_text: str, qr_text: str, footer: str) -> None:
    c.setFillColor(HexColor(BANNERS.get(banner, "#334155")))
    c.rect(0, H - 14 * mm, W, 14 * mm, stroke=0, fill=1)
    x = 3 * mm
    if logo:
        try:
            c.drawImage(ImageReader(io.BytesIO(logo)), x, H - 12.5 * mm, 11 * mm, 11 * mm, preserveAspectRatio=True, mask="auto")
            x += 13 * mm
        except Exception:  # noqa: BLE001
            pass
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(x, H - 5.5 * mm, company[:48])
    c.setFont("Helvetica-Bold", 14)
    c.drawString(x, H - 11.5 * mm, banner)
    c.setFillColor(black)
    y = H - 19 * mm
    for k, v in rows:
        c.setFont("Helvetica", 6.5)
        c.drawString(3 * mm, y, k)
        c.setFont("Helvetica-Bold", 7.5)
        c.drawString(27 * mm, y, (v or "—")[:38])
        y -= 4.2 * mm
    bc = code128.Code128(barcode_text, barHeight=9 * mm, barWidth=0.32 * mm, humanReadable=False)
    bc.drawOn(c, 3 * mm, 6 * mm)
    c.setFont("Helvetica", 6)
    c.drawString(3 * mm, 3.6 * mm, barcode_text)
    widget = qr.QrCodeWidget(qr_text)
    b = widget.getBounds()
    size = 20 * mm
    d = Drawing(size, size, transform=[size / (b[2] - b[0]), 0, 0, size / (b[3] - b[1]), 0, 0])
    d.add(widget)
    renderPDF.draw(d, c, W - size - 3 * mm, 3 * mm)
    c.setFont("Helvetica", 5.5)
    c.drawString(3 * mm, 1.2 * mm, footer)
    c.showPage()


def _fmt(d: date | None) -> str:
    return d.strftime("%d-%b-%Y") if d else "—"


def lot_rows(session: Session, lot: MaterialBatch, banner: str, extra: list[tuple[str, str]] | None = None) -> list[tuple[str, str]]:
    mat = session.get(Material, lot.material_id)
    unit = session.get(Unit, lot.unit_id)
    vendor = session.get(Vendor, lot.vendor_id) if lot.vendor_id else None
    rows = [("Material", mat.name), ("Material code", mat.material_code), ("Internal batch", lot.lot_no),
            ("Vendor", vendor.name if vendor else "—"), ("Vendor batch", lot.vendor_batch_no or "—"),
            ("Mfg / Expiry", f"{_fmt(lot.mfg_date)}  /  {_fmt(lot.expiry_date)}"), ("Retest date", _fmt(lot.retest_date)),
            ("Quantity", f"{float(lot.quantity):g} {unit.code}")]
    return rows + (extra or [])


def print_lot_label(session: Session, lot: MaterialBatch, label_type: str, copies: int, user_id: int | None,
                    reprint_reason: str | None = None, location: Location | None = None, extra: list[tuple[str, str]] | None = None) -> tuple[bytes, MaterialLabel]:
    mx = int(config_service.get(session, "label.max_copies", "10") or 10)
    if copies < 1 or copies > mx:
        raise ValidationFailed(f"Copies must be between 1 and {mx}")
    if label_type == "QUARANTINE" and lot.disposition not in lots.UNRELEASED:
        raise BusinessRuleError("A quarantine label can only be printed for an unreleased lot", rule_id="BR-LBL-002")
    if label_type == "APPROVED" and lot.disposition != "APPROVED":
        raise BusinessRuleError("An APPROVED label can only be printed for a released lot", rule_id="BR-LBL-002")
    prior = session.execute(select(func.count()).select_from(MaterialLabel).where(
        MaterialLabel.material_batch_id == lot.id, MaterialLabel.label_type == label_type)).scalar()
    if prior and not (reprint_reason or "").strip():
        raise ValidationFailed("A reason is required to reprint a label", code="REASON_REQUIRED")
    company, logo = _logo(session)
    label_no = numbering.next_number(session, numbering.default_plant_id(session), "LABEL")
    extra_rows = list(extra or [])
    if label_type == "QUARANTINE":
        extra_rows += [("Status", "QUARANTINE — do not use"), ("Location", location.location_code if location else "—")]
    if label_type == "APPROVED":
        extra_rows += [("Release date", _fmt(lot.released_at.date() if lot.released_at else None)), ("QC no.", lot.qc_no or "—"),
                       ("QA release no.", lot.qa_release_no or "—"), ("Location", location.location_code if location else "—")]
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(W, H))
    c.setTitle(f"{label_type} label {label_no}")
    for i in range(copies):
        draw_label(c, company=company, logo=logo, banner=label_type, rows=lot_rows(session, lot, label_type, extra_rows),
                   barcode_text=lot.lot_no, qr_text=f"merp://lot/{lot.lot_no}",
                   footer=f"Label {label_no} v{TEMPLATE_VERSION} · copy {i + 1}/{copies} · printed {date.today().isoformat()}")
    c.save()
    row = MaterialLabel(label_no=label_no, label_type=label_type, material_batch_id=lot.id, copies=copies,
                        reprint_reason=reprint_reason, printed_by_id=user_id, template_version=TEMPLATE_VERSION)
    session.add(row)
    session.flush()
    audit.log_event(session, module="warehouse", entity="material_label", record_id=row.id, action="LABEL_PRINT",
                    new=f"{label_type} {lot.lot_no} x{copies} ({label_no})", reason=reprint_reason)
    return buf.getvalue(), row


def print_location_label(session: Session, loc: Location, copies: int, user_id: int | None) -> tuple[bytes, MaterialLabel]:
    company, logo = _logo(session)
    label_no = numbering.next_number(session, numbering.default_plant_id(session), "LABEL")
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(W, H))
    for i in range(copies):
        draw_label(c, company=company, logo=logo, banner="LOCATION",
                   rows=[("Location", loc.location_code), ("Name", loc.name), ("Type", loc.location_type),
                         ("Condition", loc.storage_condition or "—"), ("Quarantine area", "Yes" if loc.is_quarantine else "No")],
                   barcode_text=loc.location_code, qr_text=f"merp://location/{loc.location_code}",
                   footer=f"Label {label_no} v{TEMPLATE_VERSION} · copy {i + 1}/{copies}")
    c.save()
    row = MaterialLabel(label_no=label_no, label_type="LOCATION", ref_type="location", ref_id=str(loc.id), copies=copies, printed_by_id=user_id)
    session.add(row)
    session.flush()
    audit.log_event(session, module="warehouse", entity="material_label", record_id=row.id, action="LABEL_PRINT",
                    new=f"LOCATION {loc.location_code} x{copies}")
    return buf.getvalue(), row


def print_sample_label(session: Session, sample, lot: MaterialBatch, user_id: int | None) -> tuple[bytes, MaterialLabel]:
    company, logo = _logo(session)
    label_no = numbering.next_number(session, numbering.default_plant_id(session), "LABEL")
    rows = lot_rows(session, lot, "SAMPLE", [("Sample no.", sample.sample_no), ("Qty sampled", f"{float(sample.quantity_sampled):g}"),
                                              ("Sampled on", sample.sampled_at.strftime("%d-%b-%Y"))])
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(W, H))
    draw_label(c, company=company, logo=logo, banner="SAMPLE", rows=rows, barcode_text=sample.sample_no, qr_text=f"merp://sample/{sample.sample_no}",
               footer=f"Label {label_no} v{TEMPLATE_VERSION} · {sample.sample_no}")
    c.save()
    row = MaterialLabel(label_no=label_no, label_type="SAMPLE", material_batch_id=lot.id, ref_type="sample", ref_id=str(sample.id), copies=1, printed_by_id=user_id)
    session.add(row)
    session.flush()
    audit.log_event(session, module="qc", entity="material_label", record_id=row.id, action="LABEL_PRINT", new=f"SAMPLE {sample.sample_no}")
    return buf.getvalue(), row
