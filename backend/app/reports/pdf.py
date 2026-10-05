"""PDF rendering (reportlab): generic tabular reports and controlled business documents (PO, GRN, dispatch note, batch record).

Every page carries company name, the printed-by user, the generation time and the controlled-copy number (spec 11.10(b), Annex 11 §8)."""
import io
from datetime import datetime, timezone
from typing import Any, Sequence

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

STY = getSampleStyleSheet()
SMALL = STY["BodyText"].clone("small", fontSize=7, leading=8.5)
CELL = STY["BodyText"].clone("cell", fontSize=7.5, leading=9)
HDR = "#1F3A5F"


def _footer(user: str, copy_no: str, company: str):
    now = datetime.now(timezone.utc).strftime("%d-%b-%Y %H:%M:%S UTC")

    def draw(c, doc):
        c.saveState()
        c.setFont("Helvetica", 7)
        c.setFillColor(colors.grey)
        w, _h = doc.pagesize
        c.drawString(12 * mm, 8 * mm, f"{company}  |  Controlled copy {copy_no}  |  Printed by {user} on {now}")
        c.drawRightString(w - 12 * mm, 8 * mm, f"Page {doc.page}")
        c.restoreState()
    return draw


def _header(title: str, company: str, logo: bytes | None, kv: Sequence[tuple[str, Any]] = ()):
    story: list = []
    head = [[Image(io.BytesIO(logo), width=22 * mm, height=12 * mm, kind="proportional") if logo else "",
             Paragraph(f"<b>{company}</b><br/><font size=11>{title}</font>", STY["Title"].clone("t", fontSize=13, leading=15, alignment=0))]]
    t = Table(head, colWidths=[26 * mm, None])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LINEBELOW", (0, 0), (-1, 0), 0.8, colors.HexColor(HDR))]))
    story += [t, Spacer(1, 3 * mm)]
    if kv:
        rows = [[Paragraph(f"<b>{k}</b>", CELL), Paragraph(str("" if v is None else v), CELL)] for k, v in kv]
        kt = Table(rows, colWidths=[40 * mm, None])
        kt.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey), ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        story += [kt, Spacer(1, 3 * mm)]
    return story


def _table(columns: Sequence[str], rows: Sequence[Sequence[Any]], widths=None, repeat=True):
    data = [[Paragraph(f"<b>{c}</b>", CELL) for c in columns]] + [[Paragraph(str("" if v is None else v), CELL) for v in r] for r in rows]
    t = Table(data, colWidths=widths, repeatRows=1 if repeat else 0)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DCE6F2")), ("GRID", (0, 0), (-1, -1), 0.25, colors.grey), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7F9FC")])]))
    return t


def table_report(title: str, company: str, params: dict, columns: Sequence[tuple[str, str]], rows: Sequence[dict], user: str, copy_no: str, logo: bytes | None = None) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=12 * mm, rightMargin=12 * mm, topMargin=12 * mm, bottomMargin=16 * mm, title=title)
    flt = ", ".join(f"{k}={v}" for k, v in params.items() if v not in (None, "")) or "none"
    story = _header(title, company, logo, [("Filters", flt), ("Records", len(rows))])
    story.append(_table([l for _k, l in columns], [[r.get(k) for k, _l in columns] for r in rows]))
    if not rows:
        story.append(Paragraph("No records match the selected filters.", CELL))
    f = _footer(user, copy_no, company)
    doc.build(story, onFirstPage=f, onLaterPages=f)
    return buf.getvalue()


def business_document(title: str, company: str, doc_no: str, header: Sequence[tuple[str, Any]], sections: Sequence[tuple[str, Sequence[str], Sequence[Sequence[Any]]]],
                      signatures: Sequence[dict], user: str, copy_no: str, logo: bytes | None = None, landscape_mode: bool = False) -> bytes:
    buf = io.BytesIO()
    size = landscape(A4) if landscape_mode else A4
    doc = SimpleDocTemplate(buf, pagesize=size, leftMargin=12 * mm, rightMargin=12 * mm, topMargin=12 * mm, bottomMargin=16 * mm, title=f"{title} {doc_no}")
    story = _header(f"{title} — {doc_no}", company, logo, header)
    for name, cols, rows in sections:
        story += [Paragraph(f"<b>{name}</b>", STY["Heading4"]), _table(cols, rows) if rows else Paragraph("—", CELL), Spacer(1, 3 * mm)]
    if signatures:
        story += [Paragraph("<b>Electronic signatures</b>", STY["Heading4"]),
                  _table(["Printed name", "Meaning", "Signed (UTC)", "Reason"], [[s["printed_name"], s["meaning"], s["signed_at"], s.get("reason") or ""] for s in signatures])]
    story += [Spacer(1, 4 * mm), Paragraph("This printout is a controlled copy; the electronic record in the system is the original.", SMALL)]
    f = _footer(user, copy_no, company)
    doc.build(story, onFirstPage=f, onLaterPages=f)
    return buf.getvalue()
