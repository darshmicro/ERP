"""Controlled business documents as PDF: purchase order, GRN, dispatch note, batch manufacturing record."""
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.audit import ESignature
from app.models.dispatch import Dispatch
from app.models.manufacturing import (BatchStepExecution, BOMHeader, IPCResult, ManufacturingBatch, MaterialIssue, BatchReconciliation)
from app.models.master import Customer, Location, Material, Unit, Vendor
from app.models.org import Company
from app.models.purchase import PurchaseOrder, PurchaseOrderLine
from app.models.warehouse import GRN, GRNLine, MaterialBatch
from app.reports import pdf
from app.services import dispatch as dsp, manufacturing as mfg


def _company(s: Session) -> tuple[str, bytes | None]:
    c = s.execute(select(Company)).scalars().first()
    logo = None
    if c is not None and getattr(c, "logo_document_id", None):
        try:
            from app.models.platform import Document
            from app.services import documents
            logo = documents.read_raw(s.get(Document, c.logo_document_id))
        except Exception:  # noqa: BLE001
            logo = None
    return (c.name if c else "GMP-MERP"), logo


def signatures(s: Session, entity: str, ids: list[int]) -> list[dict]:
    if not ids:
        return []
    rows = s.execute(select(ESignature).where(ESignature.entity == entity, ESignature.record_id.in_([str(i) for i in ids])).order_by(ESignature.id)).scalars().all()
    return [{"printed_name": r.printed_name, "meaning": r.meaning, "signed_at": r.signed_at.strftime("%d-%b-%Y %H:%M:%S"), "reason": r.reason} for r in rows]


def po_pdf(s: Session, po: PurchaseOrder, user: str, copy_no: str) -> bytes:
    name, logo = _company(s)
    v = s.get(Vendor, po.vendor_id)
    lines = []
    for l in s.execute(select(PurchaseOrderLine).where(PurchaseOrderLine.po_id == po.id).order_by(PurchaseOrderLine.line_no)).scalars():
        m = s.get(Material, l.material_id)
        lines.append([l.line_no, f"{m.material_code} {m.name}", l.quantity, s.get(Unit, l.unit_id).code, l.rate, l.tax_pct, l.delivery_date or ""])
    return pdf.business_document("Purchase Order", name, po.po_no, [("Vendor", f"{v.vendor_code} {v.name}"), ("PO date", po.po_date), ("Delivery date", po.delivery_date), ("Payment terms", po.payment_terms),
                                                                 ("Quality requirements", po.quality_requirements), ("Status", po.status)],
                                 [("Order lines", ["#", "Material", "Qty", "UoM", "Rate", "Tax %", "Delivery"], lines)], signatures(s, "purchase_order", [po.id]), user, copy_no, logo)


def grn_pdf(s: Session, g: GRN, user: str, copy_no: str) -> bytes:
    name, logo = _company(s)
    v = s.get(Vendor, g.vendor_id)
    po = s.get(PurchaseOrder, g.po_id)
    lines = []
    for l in s.execute(select(GRNLine).where(GRNLine.grn_id == g.id).order_by(GRNLine.line_no)).scalars():
        m = s.get(Material, l.material_id)
        lot = s.execute(select(MaterialBatch.lot_no).where(MaterialBatch.grn_line_id == l.id)).scalar()
        lines.append([l.line_no, f"{m.material_code} {m.name}", l.vendor_batch_no, l.quantity_received, l.pack_count, l.mfg_date or "", l.expiry_date or "", "Yes" if l.coa_received else "No", lot or ""])
    return pdf.business_document("Goods Receipt Note", name, g.grn_no, [("Vendor", f"{v.vendor_code} {v.name}"), ("PO", po.po_no), ("GRN date", g.grn_date), ("Invoice", g.invoice_no), ("Vehicle", g.vehicle_no), ("Status", g.status)],
                                 [("Received items", ["#", "Material", "Vendor batch", "Qty", "Packs", "Mfg", "Expiry", "CoA", "Lot"], lines)], signatures(s, "grn", [g.id]), user, copy_no, logo, landscape_mode=True)


def dispatch_pdf(s: Session, d: Dispatch, user: str, copy_no: str) -> bytes:
    name, logo = _company(s)
    c = s.get(Customer, d.customer_id)
    lines = []
    for l in dsp.dispatch_lines(s, d.id):
        lot = s.get(MaterialBatch, l.material_batch_id)
        m = s.get(Material, lot.material_id)
        lines.append([l.line_no, f"{m.material_code} {m.name}", lot.lot_no, lot.expiry_date or "", l.quantity, s.get(Unit, l.unit_id).code, l.coa_id or "—"])
    return pdf.business_document("Dispatch Note", name, d.dispatch_no, [("Customer", f"{c.customer_code} {c.name}"), ("Address", d.shipping_address or c.address), ("Licence", c.licence_no), ("Invoice", d.invoice_no),
                                                                       ("Transporter / vehicle", f"{d.transporter or ''} {d.vehicle_no or ''}".strip()), ("Dispatch date", d.dispatch_date), ("Status", d.status)],
                                 [("Dispatched goods", ["#", "Product", "Batch", "Expiry", "Qty", "UoM", "CoA ref"], lines)], signatures(s, "dispatch", [d.id]), user, copy_no, logo)


def batch_record_pdf(s: Session, b: ManufacturingBatch, user: str, copy_no: str) -> bytes:
    name, logo = _company(s)
    prod = s.get(Material, b.product_material_id)
    bom = s.get(BOMHeader, b.bom_id)
    mats = [[f"{s.get(Material, m.material_id).material_code} {s.get(Material, m.material_id).name}", m.required_qty, m.issued_qty, m.returned_qty, m.consumed_qty, m.sample_qty, m.waste_qty]
            for m in mfg.batch_materials(s, b.id)]
    iss = []
    for i in s.execute(select(MaterialIssue).where(MaterialIssue.batch_id == b.id).order_by(MaterialIssue.id)).scalars():
        lot = s.get(MaterialBatch, i.material_batch_id)
        iss.append([i.issue_no, lot.lot_no, i.quantity, s.get(Location, i.location_id).location_code, i.fefo_override_reason or "", "Cond. release" if i.conditional_release_id else ""])
    steps = []
    from app.models.iam import User
    for st in s.execute(select(BatchStepExecution).where(BatchStepExecution.batch_id == b.id).order_by(BatchStepExecution.step_no)).scalars():
        by = s.get(User, st.performed_by_id).full_name if st.performed_by_id else ""
        vb = s.get(User, st.verified_by_id).full_name if st.verified_by_id else ""
        steps.append([st.step_no, st.instruction, st.recorded_value or "", f"{by} {st.performed_at.strftime('%d-%b %H:%M') if st.performed_at else ''}", f"{vb} {st.verified_at.strftime('%d-%b %H:%M') if st.verified_at else ''}"])
    ipc = [[r.stage, r.parameter, r.value_numeric if r.value_numeric is not None else r.value_text, f"{r.lsl if r.lsl is not None else '–'} to {r.usl if r.usl is not None else '–'}", r.pass_fail]
           for r in s.execute(select(IPCResult).where(IPCResult.batch_id == b.id).order_by(IPCResult.id)).scalars()]
    secs = [("Materials", ["Material", "Required", "Issued", "Returned", "Consumed", "Sampled", "Waste"], mats), ("Material issues", ["Issue", "Lot", "Qty", "Location", "FEFO deviation", "Note"], iss),
            ("Process steps", ["#", "Instruction", "Value", "Performed by", "Verified by"], steps), ("In-process controls", ["Stage", "Parameter", "Value", "Limits", "Result"], ipc)]
    rec = s.execute(select(BatchReconciliation).where(BatchReconciliation.batch_id == b.id)).scalar_one_or_none()
    sig_ids = [(("manufacturing_batch", b.id))]
    sigs = signatures(s, "manufacturing_batch", [b.id])
    if rec is not None:
        data = json.loads(rec.summary_json)
        secs.append(("Reconciliation", ["Material", "Issued", "Consumed", "Sampled", "Waste", "Returned", "Unaccounted", "Var %", "In tolerance"],
                     [[l["material"], l["issued"], l["consumed"], l["sampled"], l["waste"], l["returned"], l["unaccounted"], l["variance_pct"], "Yes" if l["within_tolerance"] else "NO"] for l in data["lines"]]))
        sigs += signatures(s, "batch_reconciliation", [rec.id])
    sigs += signatures(s, "batch_step_execution", [x.id for x in s.execute(select(BatchStepExecution).where(BatchStepExecution.batch_id == b.id)).scalars()])
    del sig_ids
    return pdf.business_document("Batch Manufacturing Record", name, b.batch_no, [("Product", f"{prod.material_code} {prod.name}"), ("BOM", f"{bom.bom_no} v{bom.version_no}"), ("Planned qty", b.planned_qty), ("Actual qty", b.actual_qty),
                                                                                  ("Yield %", b.yield_pct), ("Status", b.status), ("Start", b.start_at), ("End", b.end_at)], secs, sigs, user, copy_no, logo, landscape_mode=True)
