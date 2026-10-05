"""Report catalogue (spec 50). Each report is read-only, permission-gated and exposes only business columns (no credentials, hashes of secrets or internal ids beyond references)."""
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.audit import AuditTrail, ESignature, SecurityEvent
from app.models.dispatch import Dispatch, DispatchLine
from app.models.iam import Role, User, UserRole
from app.models.manufacturing import (BatchMaterial, BatchReconciliation, IPCResult, ManufacturingBatch, MaterialIssue)
from app.models.master import Calibration, Customer, Equipment, Location, Material, Unit, Vendor
from app.models.purchase import PurchaseOrder, PurchaseOrderLine, PurchaseRequest, VendorMaterial, VendorQualification
from app.models.qc import COA, ConditionalRelease, OOSInvestigation, OOTEvent, QCResult, QCTest, Sample
from app.models.quality import CAPA, ChangeControl, Complaint, Deviation, Recall, SOP
from app.models.warehouse import (GRN, DestructionRecord, InventoryBalance, InventoryTransaction, MaterialBatch, QualityHold, StorageTemperatureLog)
from app.reports.engine import Param, register
from app.services import inventory, lots

D_FROM = Param("date_from", "From date", "date")
D_TO = Param("date_to", "To date", "date")
STATUS = lambda opts: Param("status", "Status", "select", opts)
MAT = Param("material_code", "Material code contains", "text")


def _between(col, p: dict, lo="date_from", hi="date_to"):
    c = []
    if p.get(lo):
        c.append(col >= p[lo])
    if p.get(hi):
        c.append(col < p[hi] + timedelta(days=1) if hasattr(p[hi], "isoformat") else col <= p[hi])
    return c


def _dt_between(col, p: dict):
    """Date range on a DATETIME column (inclusive of the whole 'to' day)."""
    from datetime import datetime, time, timezone
    c = []
    if p.get("date_from"):
        c.append(col >= datetime.combine(p["date_from"], time.min, tzinfo=timezone.utc))
    if p.get("date_to"):
        c.append(col < datetime.combine(p["date_to"] + timedelta(days=1), time.min, tzinfo=timezone.utc))
    return c


def _like(col, v):
    return func.lower(col).like(f"%{str(v).lower()}%")


# ============================================================ vendors & purchase
@register("vendor-list", "Vendor master list", "Purchase", "md.vendor.read", [("vendor_code", "Code"), ("name", "Name"), ("vendor_type", "Type"), ("country", "Country"), ("risk_class", "Risk"),
          ("criticality", "Criticality"), ("quality_agreement_status", "Quality agreement"), ("vendor_audit_status", "Audit"), ("approval_status", "Approval")], [STATUS(["APPROVED", "PENDING", "SUSPENDED", "DISQUALIFIED", "DRAFT"])])
def vendor_list(s: Session, p: dict):
    q = select(Vendor).order_by(Vendor.vendor_code)
    if p.get("status"):
        q = q.where(Vendor.approval_status == p["status"])
    return [{c: getattr(v, c) for c in ("vendor_code", "name", "vendor_type", "country", "risk_class", "criticality", "quality_agreement_status", "vendor_audit_status", "approval_status")}
            for v in s.execute(q).scalars()]


@register("vendor-qualification-status", "Vendor qualification status and expiry", "Purchase", "vq.qualification.read",
          [("vendor", "Vendor"), ("qualification_no", "Qualification"), ("version_no", "Ver"), ("status", "Status"), ("qualified_on", "Qualified on"), ("requalification_due_date", "Due"), ("days_left", "Days left")],
          [Param("within_days", "Due within (days)", "int")])
def vq_status(s: Session, p: dict):
    today = date.today()
    q = select(VendorQualification, Vendor.name).join(Vendor, Vendor.id == VendorQualification.vendor_id).where(VendorQualification.status.in_(("APPROVED", "CONDITIONAL", "EXPIRED", "SUSPENDED")))
    out = []
    for vq, name in s.execute(q.order_by(VendorQualification.requalification_due_date)).all():
        left = (vq.requalification_due_date - today).days
        if p.get("within_days") is not None and left > p["within_days"]:
            continue
        out.append({"vendor": name, "qualification_no": vq.qualification_no, "version_no": vq.version_no, "status": vq.status, "qualified_on": vq.qualified_on,
                    "requalification_due_date": vq.requalification_due_date, "days_left": left})
    return out


@register("approved-vendor-list", "Approved vendor – material list (AVL)", "Purchase", "vm.mapping.read",
          [("vendor", "Vendor"), ("material", "Material"), ("primary", "Primary"), ("site", "Manufacturer site"), ("approved_to", "Approved to"), ("version_no", "Ver")])
def avl(s: Session, p: dict):
    q = select(VendorMaterial, Vendor.name, Material.material_code, Material.name).join(Vendor, Vendor.id == VendorMaterial.vendor_id).join(Material, Material.id == VendorMaterial.material_id).where(
        VendorMaterial.status == "APPROVED").order_by(Material.material_code, Vendor.name)
    return [{"vendor": v, "material": f"{mc} {mn}", "primary": vm.is_primary, "site": vm.manufacturer_site, "approved_to": vm.approved_to, "version_no": vm.version_no} for vm, v, mc, mn in s.execute(q).all()]


@register("purchase-requests", "Purchase request register", "Purchase", "pr.request.read", [("pr_no", "PR"), ("request_date", "Date"), ("priority", "Priority"), ("purpose", "Purpose"), ("status", "Status")],
          [D_FROM, D_TO, STATUS(["DRAFT", "SUBMITTED", "DEPARTMENT_APPROVED", "APPROVED", "CONVERTED", "REJECTED", "CANCELLED"])])
def pr_register(s: Session, p: dict):
    q = select(PurchaseRequest).where(*_between(PurchaseRequest.request_date, p))
    if p.get("status"):
        q = q.where(PurchaseRequest.status == p["status"])
    return [{c: getattr(r, c) for c in ("pr_no", "request_date", "priority", "purpose", "status")} for r in s.execute(q.order_by(PurchaseRequest.id.desc())).scalars()]


@register("purchase-orders", "Purchase order register", "Purchase", "po.order.read", [("po_no", "PO"), ("po_date", "Date"), ("vendor", "Vendor"), ("lines", "Lines"), ("value", "Value (excl. tax)"), ("status", "Status")],
          [D_FROM, D_TO, STATUS(["DRAFT", "PENDING_APPROVAL", "APPROVED", "PARTIALLY_RECEIVED", "CLOSED", "CANCELLED", "REJECTED"])])
def po_register(s: Session, p: dict):
    q = select(PurchaseOrder, Vendor.name).join(Vendor, Vendor.id == PurchaseOrder.vendor_id).where(*_between(PurchaseOrder.po_date, p))
    if p.get("status"):
        q = q.where(PurchaseOrder.status == p["status"])
    out = []
    for po, vn in s.execute(q.order_by(PurchaseOrder.id.desc())).all():
        ls = s.execute(select(PurchaseOrderLine).where(PurchaseOrderLine.po_id == po.id)).scalars().all()
        out.append({"po_no": po.po_no, "po_date": po.po_date, "vendor": vn, "lines": len(ls), "value": sum((l.quantity * l.rate for l in ls), Decimal(0)), "status": po.status})
    return out


@register("po-pending-receipt", "Open purchase orders – pending receipt", "Purchase", "po.order.read",
          [("po_no", "PO"), ("vendor", "Vendor"), ("material", "Material"), ("ordered", "Ordered"), ("received", "Received"), ("pending", "Pending"), ("delivery_date", "Delivery date"), ("overdue", "Overdue")])
def po_pending(s: Session, p: dict):
    q = select(PurchaseOrder, PurchaseOrderLine, Vendor.name, Material.material_code, Material.name).join(PurchaseOrderLine, PurchaseOrderLine.po_id == PurchaseOrder.id).join(
        Vendor, Vendor.id == PurchaseOrder.vendor_id).join(Material, Material.id == PurchaseOrderLine.material_id).where(PurchaseOrder.status.in_(("APPROVED", "PARTIALLY_RECEIVED")))
    out = []
    for po, l, vn, mc, mn in s.execute(q.order_by(PurchaseOrder.po_no)).all():
        pend = l.quantity - l.received_quantity
        if pend > 0:
            dd = l.delivery_date or po.delivery_date
            out.append({"po_no": po.po_no, "vendor": vn, "material": f"{mc} {mn}", "ordered": l.quantity, "received": l.received_quantity, "pending": pend, "delivery_date": dd,
                        "overdue": "YES" if dd and dd < date.today() else ""})
    return out


@register("grn-register", "GRN register", "Warehouse", "grn.receipt.read", [("grn_no", "GRN"), ("grn_date", "Date"), ("vendor", "Vendor"), ("po_no", "PO"), ("invoice_no", "Invoice"), ("checklist_passed", "Checklist"), ("status", "Status")],
          [D_FROM, D_TO, STATUS(["DRAFT", "SUBMITTED", "QUARANTINE", "REJECTED", "CANCELLED"])])
def grn_register(s: Session, p: dict):
    q = select(GRN, Vendor.name, PurchaseOrder.po_no).join(Vendor, Vendor.id == GRN.vendor_id).join(PurchaseOrder, PurchaseOrder.id == GRN.po_id).where(*_between(GRN.grn_date, p))
    if p.get("status"):
        q = q.where(GRN.status == p["status"])
    return [{"grn_no": g.grn_no, "grn_date": g.grn_date, "vendor": v, "po_no": po, "invoice_no": g.invoice_no, "checklist_passed": g.checklist_passed, "status": g.status}
            for g, v, po in s.execute(q.order_by(GRN.id.desc())).all()]


# ============================================================ inventory
def _lot_rows(s: Session, extra=()):
    q = select(MaterialBatch, Material.material_code, Material.name, Unit.code).join(Material, Material.id == MaterialBatch.material_id).join(Unit, Unit.id == MaterialBatch.unit_id).where(*extra)
    return s.execute(q.order_by(Material.material_code, MaterialBatch.expiry_date)).all()


@register("stock-status", "Stock status by lot and location", "Inventory", "inventory.stock.read",
          [("material", "Material"), ("lot_no", "Lot"), ("location", "Location"), ("on_hand", "On hand"), ("reserved", "Reserved"), ("unit", "UoM"), ("expiry_date", "Expiry"), ("status", "Status")],
          [MAT, Param("status", "Derived status", "select", ["QUARANTINE", "QC_TESTING", "APPROVED", "HOLD", "EXPIRED", "RETEST_DUE", "REJECTED"])])
def stock_status(s: Session, p: dict):
    q = select(MaterialBatch, InventoryBalance, Material.material_code, Material.name, Unit.code, Location.location_code).join(InventoryBalance, InventoryBalance.material_batch_id == MaterialBatch.id).join(
        Material, Material.id == MaterialBatch.material_id).join(Unit, Unit.id == MaterialBatch.unit_id).join(Location, Location.id == InventoryBalance.location_id).where(InventoryBalance.qty_on_hand > 0)
    if p.get("material_code"):
        q = q.where(_like(Material.material_code, p["material_code"]))
    out = []
    for lot, bal, mc, mn, u, lc in s.execute(q.order_by(Material.material_code, MaterialBatch.expiry_date)).all():
        st = lots.derived_status(s, lot)
        if p.get("status") and st != p["status"]:
            continue
        out.append({"material": f"{mc} {mn}", "lot_no": lot.lot_no, "location": lc, "on_hand": bal.qty_on_hand, "reserved": bal.qty_reserved, "unit": u, "expiry_date": lot.expiry_date, "status": st})
    return out


@register("stock-ledger", "Inventory ledger (transactions)", "Inventory", "inventory.ledger.read",
          [("txn_ts", "Date/time (UTC)"), ("txn_type", "Type"), ("material", "Material"), ("lot_no", "Lot"), ("from_location", "From"), ("to_location", "To"), ("quantity", "Qty"), ("ref", "Reference"), ("reason", "Reason")],
          [D_FROM, D_TO, Param("txn_type", "Transaction type", "select", ["RECEIPT", "TRANSFER", "SAMPLE", "ISSUE", "RETURN", "REJECT_MOVE", "DESTROY", "ADJUST_IN", "ADJUST_OUT", "DISPATCH", "OUTPUT"]), MAT])
def stock_ledger(s: Session, p: dict):
    fl, tl = Location.__table__.alias("fl"), Location.__table__.alias("tl")
    q = (select(InventoryTransaction, MaterialBatch.lot_no, Material.material_code, fl.c.location_code, tl.c.location_code).join(MaterialBatch, MaterialBatch.id == InventoryTransaction.material_batch_id)
         .join(Material, Material.id == MaterialBatch.material_id).outerjoin(fl, fl.c.id == InventoryTransaction.from_location_id).outerjoin(tl, tl.c.id == InventoryTransaction.to_location_id)
         .where(*_dt_between(InventoryTransaction.txn_ts, p)))
    if p.get("txn_type"):
        q = q.where(InventoryTransaction.txn_type == p["txn_type"])
    if p.get("material_code"):
        q = q.where(_like(Material.material_code, p["material_code"]))
    return [{"txn_ts": t.txn_ts, "txn_type": t.txn_type, "material": mc, "lot_no": ln, "from_location": f, "to_location": to, "quantity": t.quantity,
             "ref": f"{t.ref_doc_type or ''} {t.ref_doc_id or ''}".strip(), "reason": t.reason} for t, ln, mc, f, to in s.execute(q.order_by(InventoryTransaction.id)).all()]


@register("ledger-reconciliation", "Ledger vs balance reconciliation (integrity check)", "Inventory", "inventory.ledger.verify",
          [("lot_id", "Lot id"), ("location_id", "Location id"), ("balance", "Balance table"), ("ledger", "Ledger sum"), ("difference", "Difference")])
def ledger_recon(s: Session, p: dict):
    return [{"lot_id": d["material_batch_id"], "location_id": d["location_id"], "balance": d["balance"], "ledger": d["ledger"], "difference": round(d["ledger"] - d["balance"], 6)}
            for d in inventory.verify_ledger(s)]


@register("quarantine-ageing", "Quarantine / unreleased lots ageing", "Inventory", "inventory.lot.read",
          [("material", "Material"), ("lot_no", "Lot"), ("disposition", "Disposition"), ("received", "Received"), ("age_days", "Age (days)"), ("quantity", "Qty")])
def quarantine_ageing(s: Session, p: dict):
    out = []
    for lot, mc, mn, _u in _lot_rows(s, [MaterialBatch.disposition.in_(("QUARANTINE", "QC_TESTING", "QC_APPROVED", "QA_REVIEW"))]):
        d = lot.created_at.date()
        out.append({"material": f"{mc} {mn}", "lot_no": lot.lot_no, "disposition": lot.disposition, "received": d, "age_days": (date.today() - d).days, "quantity": lot.quantity})
    return sorted(out, key=lambda r: -r["age_days"])


@register("expiry-forecast", "Near-expiry and retest-due lots", "Inventory", "inventory.lot.read",
          [("material", "Material"), ("lot_no", "Lot"), ("expiry_date", "Expiry"), ("retest_date", "Retest"), ("days_to_expiry", "Days to expiry"), ("on_hand", "On hand")], [Param("within_days", "Within (days, default 90)", "int")])
def expiry_forecast(s: Session, p: dict):
    horizon = date.today() + timedelta(days=p.get("within_days", 90))
    out = []
    for lot, mc, mn, _u in _lot_rows(s, [MaterialBatch.disposition.in_(("APPROVED", "QUARANTINE", "QC_TESTING", "QC_APPROVED", "QA_REVIEW"))]):
        oh = inventory.on_hand(s, lot.id)
        due = [d for d in (lot.expiry_date, lot.retest_date) if d]
        if oh > 0 and due and min(due) <= horizon:
            out.append({"material": f"{mc} {mn}", "lot_no": lot.lot_no, "expiry_date": lot.expiry_date, "retest_date": lot.retest_date,
                        "days_to_expiry": (lot.expiry_date - date.today()).days if lot.expiry_date else None, "on_hand": oh})
    return sorted(out, key=lambda r: (r["days_to_expiry"] is None, r["days_to_expiry"]))


@register("quality-holds", "Quality hold register", "Inventory", "qa.hold.read",
          [("hold_no", "Hold"), ("entity_type", "Type"), ("record", "Record"), ("source", "Source"), ("reason", "Reason"), ("status", "Status"), ("placed_at", "Placed (UTC)"), ("released_at", "Released (UTC)")], [STATUS(["OPEN", "RELEASED"])])
def holds(s: Session, p: dict):
    q = select(QualityHold)
    if p.get("status"):
        q = q.where(QualityHold.status == p["status"])
    out = []
    for h in s.execute(q.order_by(QualityHold.id.desc())).scalars():
        ref = s.get(MaterialBatch, h.record_id).lot_no if h.entity_type == "MATERIAL_BATCH" and s.get(MaterialBatch, h.record_id) else (
            s.get(ManufacturingBatch, h.record_id).batch_no if s.get(ManufacturingBatch, h.record_id) else h.record_id)
        out.append({"hold_no": h.hold_no, "entity_type": h.entity_type, "record": ref, "source": h.source, "reason": h.reason, "status": h.status, "placed_at": h.placed_at, "released_at": h.released_at})
    return out


@register("temperature-excursions", "Storage temperature log and excursions", "Inventory", "warehouse.temperature.read",
          [("recorded_at", "Recorded (UTC)"), ("location", "Location"), ("reading", "Reading °C"), ("range", "Range"), ("excursion", "Excursion"), ("remarks", "Remarks")], [D_FROM, D_TO, Param("only_excursions", "Excursions only (1)", "int")])
def temperature(s: Session, p: dict):
    q = select(StorageTemperatureLog, Location).join(Location, Location.id == StorageTemperatureLog.location_id).where(*_dt_between(StorageTemperatureLog.recorded_at, p))
    if p.get("only_excursions"):
        q = q.where(StorageTemperatureLog.excursion == True)  # noqa: E712
    return [{"recorded_at": t.recorded_at, "location": l.location_code, "reading": t.reading, "range": f"{l.temp_min}–{l.temp_max}", "excursion": t.excursion, "remarks": t.remarks}
            for t, l in s.execute(q.order_by(StorageTemperatureLog.id.desc())).all()]


@register("destruction-register", "Destruction register", "Inventory", "warehouse.destruction.read",
          [("destruction_no", "No."), ("lot_no", "Lot"), ("quantity", "Qty"), ("method", "Method"), ("reason", "Reason"), ("status", "Status"), ("executed_at", "Executed (UTC)")])
def destruction(s: Session, p: dict):
    q = select(DestructionRecord, MaterialBatch.lot_no).join(MaterialBatch, MaterialBatch.id == DestructionRecord.material_batch_id).order_by(DestructionRecord.id.desc())
    return [{"destruction_no": d.destruction_no, "lot_no": ln, "quantity": d.quantity, "method": d.method, "reason": d.reason, "status": d.status, "executed_at": d.executed_at} for d, ln in s.execute(q).all()]


# ============================================================ QC
@register("qc-pending", "QC samples and tests pending", "QC", "qc.sample.read",
          [("sample_no", "Sample"), ("material", "Material"), ("lot_no", "Lot"), ("status", "Status"), ("sampled_at", "Sampled (UTC)"), ("age_days", "Age (days)"), ("tests_open", "Tests open")])
def qc_pending(s: Session, p: dict):
    q = (select(Sample, MaterialBatch.lot_no, Material.material_code).join(MaterialBatch, MaterialBatch.id == Sample.material_batch_id).join(Material, Material.id == MaterialBatch.material_id)
         .where(Sample.status.in_(("CREATED", "TESTING"))).order_by(Sample.sampled_at))
    out = []
    for sm, ln, mc in s.execute(q).all():
        n = s.execute(select(func.count()).select_from(QCTest).where(QCTest.sample_id == sm.id, QCTest.status != "SUBMITTED")).scalar()
        out.append({"sample_no": sm.sample_no, "material": mc, "lot_no": ln, "status": sm.status, "sampled_at": sm.sampled_at, "age_days": (date.today() - sm.sampled_at.date()).days if sm.sampled_at else None, "tests_open": n})
    return out


@register("qc-results", "QC results register", "QC", "qc.sample.read",
          [("sample_no", "Sample"), ("lot_no", "Lot"), ("test_name", "Test"), ("value", "Result"), ("limits", "Limits"), ("pass_fail", "Pass/Fail"), ("entered_at", "Entered (UTC)")], [D_FROM, D_TO, MAT, Param("pass_fail", "Result", "select", ["PASS", "FAIL"])])
def qc_results(s: Session, p: dict):
    q = (select(QCResult, QCTest.test_name, Sample.sample_no, MaterialBatch.lot_no, Material.material_code).join(QCTest, QCTest.id == QCResult.test_id).join(Sample, Sample.id == QCTest.sample_id)
         .join(MaterialBatch, MaterialBatch.id == Sample.material_batch_id).join(Material, Material.id == MaterialBatch.material_id).where(*_dt_between(QCResult.entered_at, p)))
    if p.get("material_code"):
        q = q.where(_like(Material.material_code, p["material_code"]))
    if p.get("pass_fail"):
        q = q.where(QCResult.pass_fail == p["pass_fail"])
    return [{"sample_no": sn, "lot_no": ln, "test_name": tn, "value": r.rounded_value if r.rounded_value is not None else r.value_text, "limits": f"{r.lsl if r.lsl is not None else '–'} to {r.usl if r.usl is not None else '–'}",
             "pass_fail": r.pass_fail, "entered_at": r.entered_at} for r, tn, sn, ln, mc in s.execute(q.order_by(QCResult.id.desc())).all()]


@register("oos-register", "OOS / OOT register", "QC", "oos.investigation.read",
          [("oos_no", "OOS"), ("lot_no", "Lot"), ("description", "Description"), ("status", "Status"), ("decision", "Decision"), ("raised_at", "Raised (UTC)"), ("closed_at", "Closed (UTC)")], [STATUS(["RAISED", "PHASE1", "PHASE2", "DECIDED", "CLOSED"])])
def oos_register(s: Session, p: dict):
    q = select(OOSInvestigation, MaterialBatch.lot_no).outerjoin(MaterialBatch, MaterialBatch.id == OOSInvestigation.material_batch_id)
    if p.get("status"):
        q = q.where(OOSInvestigation.status == p["status"])
    return [{"oos_no": o.oos_no, "lot_no": ln, "description": o.description, "status": o.status, "decision": o.decision, "raised_at": o.raised_at, "closed_at": o.closed_at}
            for o, ln in s.execute(q.order_by(OOSInvestigation.id.desc())).all()]


@register("oot-register", "OOT events", "QC", "oot.event.read", [("oot_no", "OOT"), ("test_name", "Test"), ("rule", "Rule"), ("detail", "Detail"), ("status", "Status")])
def oot_register(s: Session, p: dict):
    return [{"oot_no": o.oot_no, "test_name": o.test_name, "rule": o.rule, "detail": o.detail, "status": o.status} for o in s.execute(select(OOTEvent).order_by(OOTEvent.id.desc())).scalars()]


@register("coa-register", "Certificate of analysis register", "QC", "coa.document.read", [("coa_no", "CoA"), ("version_no", "Ver"), ("lot_no", "Lot"), ("conclusion", "Conclusion"), ("generated_at", "Generated (UTC)")])
def coa_register(s: Session, p: dict):
    q = select(COA, MaterialBatch.lot_no).outerjoin(MaterialBatch, MaterialBatch.id == COA.material_batch_id).order_by(COA.id.desc())
    return [{"coa_no": c.coa_no, "version_no": c.version_no, "lot_no": ln, "conclusion": c.conclusion, "generated_at": c.generated_at} for c, ln in s.execute(q).all()]


@register("conditional-releases", "Conditional release register", "QC", "conditional_release.request.read",
          [("cr_no", "No."), ("lot_no", "Lot"), ("quantity_authorised", "Authorised"), ("quantity_used", "Used"), ("intended_batch_ref", "Batch"), ("expires_at", "Expires"), ("status", "Status")])
def cond_rel(s: Session, p: dict):
    q = select(ConditionalRelease, MaterialBatch.lot_no).join(MaterialBatch, MaterialBatch.id == ConditionalRelease.material_batch_id).order_by(ConditionalRelease.id.desc())
    return [{"cr_no": c.cr_no, "lot_no": ln, "quantity_authorised": c.quantity_authorised, "quantity_used": c.quantity_used, "intended_batch_ref": c.intended_batch_ref, "expires_at": c.expires_at, "status": c.status}
            for c, ln in s.execute(q).all()]


@register("equipment-calibration", "Equipment qualification and calibration status", "QC", "md.equipment.read",
          [("equipment_code", "Code"), ("name", "Name"), ("qualification_status", "Qualification"), ("last_calibration", "Last calibration"), ("calibration_due", "Due"), ("days_left", "Days left"), ("status", "Status")],
          [Param("within_days", "Due within (days)", "int")])
def equipment_cal(s: Session, p: dict):
    out = []
    for e in s.execute(select(Equipment).order_by(Equipment.equipment_code)).scalars():
        last = s.execute(select(Calibration).where(Calibration.equipment_id == e.id).order_by(Calibration.performed_on.desc())).scalars().first()
        due = last.due_on if last else None
        left = (due - date.today()).days if due else None
        if p.get("within_days") is not None and (left is None or left > p["within_days"]):
            continue
        out.append({"equipment_code": e.equipment_code, "name": e.name, "qualification_status": e.qualification_status, "last_calibration": last.performed_on if last else None, "calibration_due": due,
                    "days_left": left, "status": e.status})
    return out


# ============================================================ manufacturing & dispatch
@register("batch-register", "Manufacturing batch register", "Manufacturing", "mfg.batch.read",
          [("batch_no", "Batch"), ("product", "Product"), ("type", "Type"), ("planned_qty", "Planned"), ("actual_qty", "Actual"), ("yield_pct", "Yield %"), ("status", "Status"), ("start_at", "Start (UTC)"), ("end_at", "End (UTC)")],
          [D_FROM, D_TO, STATUS(["CREATED", "MATERIAL_ISSUED", "IN_PROCESS", "PRODUCTION_COMPLETE", "RECONCILED", "QC_QA", "RELEASED", "REJECTED", "CANCELLED"])])
def batch_register(s: Session, p: dict):
    q = select(ManufacturingBatch, Material.material_code, Material.name).join(Material, Material.id == ManufacturingBatch.product_material_id).where(*_dt_between(ManufacturingBatch.created_at, p))
    if p.get("status"):
        q = q.where(ManufacturingBatch.status == p["status"])
    return [{"batch_no": b.batch_no, "product": f"{mc} {mn}", "type": b.batch_type, "planned_qty": b.planned_qty, "actual_qty": b.actual_qty, "yield_pct": b.yield_pct, "status": b.status, "start_at": b.start_at, "end_at": b.end_at}
            for b, mc, mn in s.execute(q.order_by(ManufacturingBatch.id.desc())).all()]


@register("material-issues", "Material issue register (lot ↔ batch)", "Manufacturing", "mfg.issue.read",
          [("issue_no", "Issue"), ("batch_no", "Batch"), ("material", "Material"), ("lot_no", "Lot"), ("quantity", "Qty"), ("fefo_override_reason", "FEFO deviation"), ("conditional", "Cond. release"), ("issued_at", "Issued (UTC)")], [D_FROM, D_TO, MAT])
def issues(s: Session, p: dict):
    q = (select(MaterialIssue, ManufacturingBatch.batch_no, MaterialBatch.lot_no, Material.material_code).join(ManufacturingBatch, ManufacturingBatch.id == MaterialIssue.batch_id)
         .join(MaterialBatch, MaterialBatch.id == MaterialIssue.material_batch_id).join(Material, Material.id == MaterialBatch.material_id).where(*_dt_between(MaterialIssue.issued_at, p)))
    if p.get("material_code"):
        q = q.where(_like(Material.material_code, p["material_code"]))
    return [{"issue_no": i.issue_no, "batch_no": bn, "material": mc, "lot_no": ln, "quantity": i.quantity, "fefo_override_reason": i.fefo_override_reason, "conditional": "YES" if i.conditional_release_id else "",
             "issued_at": i.issued_at} for i, bn, ln, mc in s.execute(q.order_by(MaterialIssue.id.desc())).all()]


@register("batch-reconciliation", "Batch reconciliation and yield", "Manufacturing", "mfg.reconciliation.read",
          [("batch_no", "Batch"), ("material", "Material"), ("issued", "Issued"), ("consumed", "Consumed"), ("sampled", "Sampled"), ("waste", "Waste"), ("returned", "Returned"), ("unaccounted", "Unaccounted"), ("variance_pct", "Var %"),
           ("within_tolerance", "In tolerance"), ("yield_pct", "Yield %"), ("deviation_ref", "Deviation"), ("status", "Status")])
def batch_recon(s: Session, p: dict):
    import json
    out = []
    for rec, b in s.execute(select(BatchReconciliation, ManufacturingBatch).join(ManufacturingBatch, ManufacturingBatch.id == BatchReconciliation.batch_id).order_by(BatchReconciliation.id.desc())).all():
        for l in json.loads(rec.summary_json)["lines"]:
            out.append({"batch_no": b.batch_no, "material": l["material"], "issued": l["issued"], "consumed": l["consumed"], "sampled": l["sampled"], "waste": l["waste"], "returned": l["returned"],
                        "unaccounted": l["unaccounted"], "variance_pct": l["variance_pct"], "within_tolerance": l["within_tolerance"], "yield_pct": b.yield_pct, "deviation_ref": rec.deviation_ref, "status": rec.status})
    return out


@register("ipc-results", "In-process control results", "Manufacturing", "mfg.ipc.read",
          [("batch_no", "Batch"), ("stage", "Stage"), ("parameter", "Parameter"), ("value", "Value"), ("limits", "Limits"), ("pass_fail", "Result"), ("recorded_at", "Recorded (UTC)")], [D_FROM, D_TO])
def ipc(s: Session, p: dict):
    q = select(IPCResult, ManufacturingBatch.batch_no).join(ManufacturingBatch, ManufacturingBatch.id == IPCResult.batch_id).where(*_dt_between(IPCResult.recorded_at, p))
    return [{"batch_no": bn, "stage": r.stage, "parameter": r.parameter, "value": r.value_numeric if r.value_numeric is not None else r.value_text, "limits": f"{r.lsl if r.lsl is not None else '–'} to {r.usl if r.usl is not None else '–'}",
             "pass_fail": r.pass_fail, "recorded_at": r.recorded_at} for r, bn in s.execute(q.order_by(IPCResult.id.desc())).all()]


@register("dispatch-register", "Dispatch register", "Dispatch", "dispatch.order.read",
          [("dispatch_no", "Dispatch"), ("dispatch_date", "Date"), ("customer", "Customer"), ("invoice_no", "Invoice"), ("lots", "Batches"), ("quantity", "Total qty"), ("status", "Status")],
          [D_FROM, D_TO, STATUS(["DRAFT", "VALIDATED", "APPROVED", "DISPATCHED", "DELIVERED", "CANCELLED"])])
def dispatch_register(s: Session, p: dict):
    q = select(Dispatch, Customer.name).join(Customer, Customer.id == Dispatch.customer_id).where(*_between(Dispatch.dispatch_date, p))
    if p.get("status"):
        q = q.where(Dispatch.status == p["status"])
    out = []
    for d, cn in s.execute(q.order_by(Dispatch.id.desc())).all():
        ls = s.execute(select(DispatchLine.quantity, MaterialBatch.lot_no).join(MaterialBatch, MaterialBatch.id == DispatchLine.material_batch_id).where(DispatchLine.dispatch_id == d.id)).all()
        out.append({"dispatch_no": d.dispatch_no, "dispatch_date": d.dispatch_date, "customer": cn, "invoice_no": d.invoice_no, "lots": ", ".join(sorted({l for _q, l in ls})), "quantity": sum((q for q, _l in ls), Decimal(0)), "status": d.status})
    return out


@register("lot-genealogy", "Lot genealogy (traceability table)", "Dispatch", "trace.record.read",
          [("from_type", "From"), ("from", "From no."), ("relation", "Relation"), ("to_type", "To"), ("to", "To no."), ("quantity", "Qty")],
          [Param("lot_no", "Lot / batch number", "text", required=True), Param("direction", "Direction", "select", ["both", "forward", "backward"])])
def genealogy(s: Session, p: dict):
    from app.services import traceability
    key = traceability.resolve(s, "LOT", p["lot_no"])
    return traceability.trace(s, key, p.get("direction", "both"))["table"]


# ============================================================ quality system
@register("deviation-register", "Deviation register", "Quality", "quality.deviation.read",
          [("dev_no", "Deviation"), ("title", "Title"), ("severity", "Severity"), ("source", "Source"), ("status", "Status"), ("age_days", "Age (days)"), ("capa_no", "CAPA")],
          [STATUS(["OPEN", "INVESTIGATION", "CAPA_PROPOSED", "QA_REVIEW", "CLOSED", "CANCELLED"]), Param("severity", "Severity", "select", ["MINOR", "MAJOR", "CRITICAL"])])
def dev_register(s: Session, p: dict):
    q = select(Deviation)
    for f in ("status", "severity"):
        if p.get(f):
            q = q.where(getattr(Deviation, f) == p[f])
    out = []
    for d in s.execute(q.order_by(Deviation.id.desc())).scalars():
        c = s.get(CAPA, d.capa_id) if d.capa_id else None
        out.append({"dev_no": d.dev_no, "title": d.title, "severity": d.severity, "source": d.source, "status": d.status, "age_days": (date.today() - d.created_at.date()).days, "capa_no": c.capa_no if c else None})
    return out


@register("capa-register", "CAPA register", "Quality", "quality.capa.read", [("capa_no", "CAPA"), ("title", "Title"), ("capa_type", "Type"), ("source_ref", "Source"), ("owner", "Owner"), ("due_date", "Due"), ("overdue", "Overdue"), ("status", "Status")],
          [STATUS(["OPEN", "IN_PROGRESS", "EFFECTIVENESS_CHECK", "CLOSED", "CANCELLED"])])
def capa_register(s: Session, p: dict):
    q = select(CAPA, User.full_name).join(User, User.id == CAPA.owner_id)
    if p.get("status"):
        q = q.where(CAPA.status == p["status"])
    return [{"capa_no": c.capa_no, "title": c.title, "capa_type": c.capa_type, "source_ref": c.source_ref, "owner": o, "due_date": c.due_date,
             "overdue": "YES" if c.status in ("OPEN", "IN_PROGRESS") and c.due_date < date.today() else "", "status": c.status} for c, o in s.execute(q.order_by(CAPA.id.desc())).all()]


@register("change-control-register", "Change control register", "Quality", "quality.cc.read", [("cc_no", "CC"), ("title", "Title"), ("change_type", "Type"), ("risk_level", "Risk"), ("status", "Status")], [STATUS(["DRAFT", "ASSESSMENT", "APPROVAL", "IMPLEMENTATION", "EFFECTIVENESS", "CLOSED", "REJECTED", "CANCELLED"])])
def cc_register(s: Session, p: dict):
    q = select(ChangeControl)
    if p.get("status"):
        q = q.where(ChangeControl.status == p["status"])
    return [{c: getattr(x, c) for c in ("cc_no", "title", "change_type", "risk_level", "status")} for x in s.execute(q.order_by(ChangeControl.id.desc())).scalars()]


@register("complaint-register", "Complaint and recall register", "Quality", "quality.complaint.read", [("no", "No."), ("kind", "Kind"), ("date", "Date"), ("severity", "Severity / class"), ("lot_no", "Lot"), ("status", "Status")])
def complaint_register(s: Session, p: dict):
    out = []
    for c, ln in s.execute(select(Complaint, MaterialBatch.lot_no).outerjoin(MaterialBatch, MaterialBatch.id == Complaint.material_batch_id)).all():
        out.append({"no": c.complaint_no, "kind": "Complaint", "date": c.received_on, "severity": c.severity, "lot_no": ln, "status": c.status})
    for r, ln in s.execute(select(Recall, MaterialBatch.lot_no).join(MaterialBatch, MaterialBatch.id == Recall.material_batch_id)).all():
        out.append({"no": r.recall_no, "kind": "Recall", "date": r.created_at.date(), "severity": f"Class {r.recall_class}", "lot_no": ln, "status": r.status})
    return sorted(out, key=lambda r: str(r["date"]), reverse=True)


@register("sop-register", "SOP register and review status", "Quality", "quality.sop.read", [("sop_no", "SOP"), ("version_no", "Ver"), ("title", "Title"), ("status", "Status"), ("effective_from", "Effective"), ("review_due_date", "Review due"), ("overdue", "Review overdue")])
def sop_register(s: Session, p: dict):
    return [{"sop_no": x.sop_no, "version_no": x.version_no, "title": x.title, "status": x.status, "effective_from": x.effective_from, "review_due_date": x.review_due_date,
             "overdue": "YES" if x.status == "APPROVED" and x.review_due_date and x.review_due_date < date.today() else ""} for x in s.execute(select(SOP).order_by(SOP.sop_no, SOP.version_no)).scalars()]


# ============================================================ system / compliance
@register("audit-trail", "Audit trail report", "System", "audit.trail.read",
          [("occurred_at", "When (UTC)"), ("user_name", "User"), ("module", "Module"), ("entity", "Entity"), ("record_id", "Record"), ("action", "Action"), ("field_name", "Field"), ("old_value", "Old"), ("new_value", "New"), ("reason", "Reason")],
          [D_FROM, D_TO, Param("entity", "Entity", "text"), Param("user_name", "User contains", "text"), Param("action", "Action", "text")])
def audit_report(s: Session, p: dict):
    q = select(AuditTrail).where(*_dt_between(AuditTrail.occurred_at, p))
    if p.get("entity"):
        q = q.where(AuditTrail.entity == p["entity"])
    if p.get("user_name"):
        q = q.where(_like(AuditTrail.user_name, p["user_name"]))
    if p.get("action"):
        q = q.where(AuditTrail.action == p["action"].upper())
    return [{c: getattr(a, c) for c in ("occurred_at", "user_name", "module", "entity", "record_id", "action", "field_name", "old_value", "new_value", "reason")}
            for a in s.execute(q.order_by(AuditTrail.id.desc()).limit(20000)).scalars()]


@register("esignature-log", "Electronic signature log", "System", "esign.record.read",
          [("signed_at", "Signed (UTC)"), ("printed_name", "Name"), ("username", "User ID"), ("role_name", "Role"), ("meaning", "Meaning"), ("entity", "Entity"), ("record_id", "Record"), ("reason", "Reason")], [D_FROM, D_TO, Param("meaning", "Meaning", "text")])
def esig_log(s: Session, p: dict):
    q = select(ESignature).where(*_dt_between(ESignature.signed_at, p))
    if p.get("meaning"):
        q = q.where(ESignature.meaning == p["meaning"].upper())
    return [{c: getattr(e, c) for c in ("signed_at", "printed_name", "username", "role_name", "meaning", "entity", "record_id", "reason")} for e in s.execute(q.order_by(ESignature.id.desc()).limit(20000)).scalars()]


@register("user-access", "User access and role report", "System", "iam.user.read",
          [("username", "User ID"), ("full_name", "Name"), ("roles", "Active roles"), ("is_active", "Active"), ("auth_source", "Auth"), ("last_login_at", "Last login (UTC)"), ("access_expiry", "Access expiry"), ("locked", "Locked")])
def user_access(s: Session, p: dict):
    out = []
    now = __import__("app.core.time", fromlist=["utcnow"]).utcnow()
    for u in s.execute(select(User).order_by(User.username)).scalars():
        roles = s.execute(select(Role.role_code).join(UserRole, UserRole.role_id == Role.id).where(UserRole.user_id == u.id, UserRole.revoked_at.is_(None), UserRole.is_disabled == False)).scalars().all()  # noqa: E712
        out.append({"username": u.username, "full_name": u.full_name, "roles": ", ".join(sorted(roles)), "is_active": u.is_active, "auth_source": u.auth_source, "last_login_at": u.last_login_at,
                    "access_expiry": u.access_expiry, "locked": "YES" if u.locked_until and u.locked_until > now else ""})
    return out


@register("security-events", "Security event log", "System", "security.event.read", [("occurred_at", "When (UTC)"), ("event_type", "Event"), ("username", "User"), ("ip_address", "IP"), ("detail", "Detail")], [D_FROM, D_TO, Param("event_type", "Event type", "text")])
def sec_events(s: Session, p: dict):
    q = select(SecurityEvent).where(*_dt_between(SecurityEvent.occurred_at, p))
    if p.get("event_type"):
        q = q.where(SecurityEvent.event_type == p["event_type"].upper())
    return [{c: getattr(e, c) for c in ("occurred_at", "event_type", "username", "ip_address", "detail")} for e in s.execute(q.order_by(SecurityEvent.id.desc()).limit(20000)).scalars()]
