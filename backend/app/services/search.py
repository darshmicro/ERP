"""Global search and QR resolution (spec 53, 54)."""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.dispatch import Dispatch
from app.models.manufacturing import ManufacturingBatch, PlasmaPool
from app.models.master import Customer, Material, Vendor
from app.models.purchase import PurchaseOrder
from app.models.qc import Sample
from app.models.warehouse import GRN, MaterialBatch

# (type, model, key column, label column or None, permission, ui route)
SOURCES = [
    ("LOT", MaterialBatch, "lot_no", "vendor_batch_no", "inventory.lot.read", "/inventory"),
    ("BATCH", ManufacturingBatch, "batch_no", None, "mfg.batch.read", "/batches"),
    ("DISPATCH", Dispatch, "dispatch_no", "invoice_no", "dispatch.order.read", "/dispatch"),
    ("GRN", GRN, "grn_no", "invoice_no", "grn.receipt.read", "/grn"),
    ("PO", PurchaseOrder, "po_no", None, "po.order.read", "/purchase-orders"),
    ("SAMPLE", Sample, "sample_no", None, "qc.sample.read", "/samples"),
    ("VENDOR", Vendor, "vendor_code", "name", "md.vendor.read", "/vendors"),
    ("MATERIAL", Material, "material_code", "name", "md.material.read", "/materials"),
    ("CUSTOMER", Customer, "customer_code", "name", "md.customer.read", "/customers"),
    ("POOL", PlasmaPool, "pool_no", None, "antisera.pool.read", "/antisera"),
]


def search(s: Session, q: str, perms: set[str], limit: int = 8) -> list[dict]:
    q = (q or "").strip().lower()
    if len(q) < 2:
        return []
    out = []
    for kind, Model, key, label, perm, route in SOURCES:
        if perm not in perms:
            continue
        conds = [func.lower(getattr(Model, key)).like(f"%{q}%")]
        if label:
            conds.append(func.lower(getattr(Model, label)).like(f"%{q}%"))
        for r in s.execute(select(Model).where(*[conds[0]] if len(conds) == 1 else [conds[0] | conds[1]]).limit(limit)).scalars():
            out.append({"type": kind, "id": r.id, "number": getattr(r, key), "label": getattr(r, label) if label else None, "route": route})
    return out


def resolve_qr(s: Session, code: str) -> dict | None:
    """`merp://lot/<lot_no>`, `merp://sample/<no>`, `merp://location/<code>`, or a bare lot / batch / dispatch number."""
    from app.models.master import Location
    from app.models.qc import Sample as Smp
    code = (code or "").strip()
    kind, ref = None, code
    if code.startswith("merp://"):
        kind, _, ref = code[len("merp://"):].partition("/")
    table = {"lot": (MaterialBatch, MaterialBatch.lot_no, "LOT"), "sample": (Smp, Smp.sample_no, "SAMPLE"), "location": (Location, Location.location_code, "LOCATION"),
             "batch": (ManufacturingBatch, ManufacturingBatch.batch_no, "BATCH"), "dispatch": (Dispatch, Dispatch.dispatch_no, "DISPATCH")}
    cands = [table[kind]] if kind in table else list(table.values())
    for Model, col, label in cands:
        row = s.execute(select(Model).where(col == ref)).scalars().first()
        if row:
            return {"type": label, "id": row.id, "number": ref}
    return None
