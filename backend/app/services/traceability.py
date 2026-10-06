"""Genealogy / traceability graph (spec 48, 53): forward (where did this go?) and backward (what is it made of?).

Flow of material:  VENDOR -> PO -> GRN -> LOT -(issue)-> BATCH -(output)-> LOT -(dispatch)-> DISPATCH -> CUSTOMER
                   ANIMAL -> BLEED -> POOL -> LOT
"""
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFound, ValidationFailed
from app.models.dispatch import Dispatch, DispatchLine
from app.models.manufacturing import Animal, BleedRecord, ManufacturingBatch, MaterialIssue, PlasmaPool
from app.models.master import Customer, Material, Vendor
from app.models.purchase import PurchaseOrder
from app.models.warehouse import GRN, GRNLine, MaterialBatch

MAX_NODES = 500
Edge = tuple[str, str, float | None]          # (neighbour key, label, quantity)


def key(kind: str, rid: int) -> str:
    return f"{kind}:{rid}"


def _split(k: str) -> tuple[str, int]:
    kind, rid = k.split(":")
    return kind, int(rid)


def _f(x) -> float | None:
    return None if x is None else float(x)


# ------------------------------------------------------------------ neighbours
def forward(s: Session, k: str) -> list[Edge]:
    kind, i = _split(k)
    out: list[Edge] = []
    if kind == "VENDOR":
        out += [(key("PO", r), "SUPPLIED_ON", None) for r in s.execute(select(PurchaseOrder.id).where(PurchaseOrder.vendor_id == i)).scalars()]
    elif kind == "PO":
        out += [(key("GRN", r), "RECEIVED_IN", None) for r in s.execute(select(GRN.id).where(GRN.po_id == i)).scalars()]
    elif kind == "GRN":
        out += [(key("LOT", r), "BECAME_LOT", None) for r in s.execute(select(MaterialBatch.id).join(GRNLine, GRNLine.id == MaterialBatch.grn_line_id).where(GRNLine.grn_id == i)).scalars()]
    elif kind == "LOT":
        issued: dict[int, Decimal] = {}
        for bid, q in s.execute(select(MaterialIssue.batch_id, MaterialIssue.quantity).where(MaterialIssue.material_batch_id == i)):
            issued[bid] = issued.get(bid, Decimal(0)) + q
        out += [(key("BATCH", b), "ISSUED_TO", _f(q)) for b, q in issued.items()]
        sent: dict[int, Decimal] = {}
        for did, q in s.execute(select(DispatchLine.dispatch_id, DispatchLine.quantity).join(Dispatch, Dispatch.id == DispatchLine.dispatch_id)
                                .where(DispatchLine.material_batch_id == i, Dispatch.status.in_(("DISPATCHED", "DELIVERED")))):
            sent[did] = sent.get(did, Decimal(0)) + q
        out += [(key("DISPATCH", d), "DISPATCHED_IN", _f(q)) for d, q in sent.items()]
    elif kind == "BATCH":
        b = s.get(ManufacturingBatch, i)
        if b and b.output_lot_id:
            out.append((key("LOT", b.output_lot_id), "PRODUCED", _f(b.actual_qty)))
    elif kind == "DISPATCH":
        d = s.get(Dispatch, i)
        out.append((key("CUSTOMER", d.customer_id), "SENT_TO", None))
    elif kind == "ANIMAL":
        out += [(key("BLEED", r), "BLED", None) for r in s.execute(select(BleedRecord.id).where(BleedRecord.animal_id == i)).scalars()]
    elif kind == "BLEED":
        bl = s.get(BleedRecord, i)
        if bl and bl.pool_id:
            out.append((key("POOL", bl.pool_id), "POOLED_INTO", _f(bl.volume_l)))
    elif kind == "POOL":
        p = s.get(PlasmaPool, i)
        if p and p.material_batch_id:
            out.append((key("LOT", p.material_batch_id), "BECAME_LOT", _f(p.total_volume_l)))
    return out


def backward(s: Session, k: str) -> list[Edge]:
    kind, i = _split(k)
    out: list[Edge] = []
    if kind == "CUSTOMER":
        out += [(key("DISPATCH", r), "RECEIVED", None) for r in s.execute(select(Dispatch.id).where(Dispatch.customer_id == i, Dispatch.status.in_(("DISPATCHED", "DELIVERED")))).scalars()]
    elif kind == "DISPATCH":
        sent: dict[int, Decimal] = {}
        for lot, q in s.execute(select(DispatchLine.material_batch_id, DispatchLine.quantity).where(DispatchLine.dispatch_id == i)):
            sent[lot] = sent.get(lot, Decimal(0)) + q
        out += [(key("LOT", l), "CONTAINS", _f(q)) for l, q in sent.items()]
    elif kind == "LOT":
        lot = s.get(MaterialBatch, i)
        if lot.source_type == "GRN" and lot.grn_line_id:
            gl = s.get(GRNLine, lot.grn_line_id)
            out.append((key("GRN", gl.grn_id), "RECEIVED_ON", _f(lot.quantity)))
        elif lot.source_type == "MFG" and lot.manufacturing_batch_id:
            out.append((key("BATCH", lot.manufacturing_batch_id), "PRODUCED_BY", _f(lot.quantity)))
        elif lot.source_type == "POOL":
            p = s.execute(select(PlasmaPool.id).where(PlasmaPool.material_batch_id == i)).scalar()
            if p:
                out.append((key("POOL", p), "POOLED_AS", _f(lot.quantity)))
    elif kind == "BATCH":
        used: dict[int, Decimal] = {}
        for lot, q in s.execute(select(MaterialIssue.material_batch_id, MaterialIssue.quantity).where(MaterialIssue.batch_id == i)):
            used[lot] = used.get(lot, Decimal(0)) + q
        out += [(key("LOT", l), "CONSUMED", _f(q)) for l, q in used.items()]
    elif kind == "GRN":
        out.append((key("PO", s.get(GRN, i).po_id), "AGAINST", None))
    elif kind == "PO":
        out.append((key("VENDOR", s.get(PurchaseOrder, i).vendor_id), "ORDERED_FROM", None))
    elif kind == "POOL":
        out += [(key("BLEED", r), "FROM_BLEED", None) for r in s.execute(select(BleedRecord.id).where(BleedRecord.pool_id == i)).scalars()]
    elif kind == "BLEED":
        out.append((key("ANIMAL", s.get(BleedRecord, i).animal_id), "FROM_ANIMAL", None))
    return out


# ------------------------------------------------------------------ node description
def describe(s: Session, k: str) -> dict:
    kind, i = _split(k)
    n = {"id": k, "type": kind}
    if kind == "LOT":
        l = s.get(MaterialBatch, i)
        m = s.get(Material, l.material_id)
        n.update(label=l.lot_no, sub=f"{m.material_code} {m.name}", status=l.disposition, expiry=l.expiry_date.isoformat() if l.expiry_date else None, ref=l.id)
    elif kind == "BATCH":
        b = s.get(ManufacturingBatch, i)
        n.update(label=b.batch_no, sub=f"{b.batch_type} batch", status=b.status, ref=b.id)
    elif kind == "DISPATCH":
        d = s.get(Dispatch, i)
        n.update(label=d.dispatch_no, sub=f"invoice {d.invoice_no or '—'}", status=d.status, ref=d.id)
    elif kind == "CUSTOMER":
        c = s.get(Customer, i)
        n.update(label=c.customer_code, sub=c.name, status="ACTIVE" if c.is_active else "INACTIVE", ref=c.id)
    elif kind == "VENDOR":
        v = s.get(Vendor, i)
        n.update(label=v.vendor_code, sub=v.name, status=v.approval_status, ref=v.id)
    elif kind == "PO":
        p = s.get(PurchaseOrder, i)
        n.update(label=p.po_no, sub="purchase order", status=p.status, ref=p.id)
    elif kind == "GRN":
        g = s.get(GRN, i)
        n.update(label=g.grn_no, sub=f"invoice {g.invoice_no or '—'}", status=g.status, ref=g.id)
    elif kind == "POOL":
        p = s.get(PlasmaPool, i)
        n.update(label=p.pool_no, sub=f"{float(p.total_volume_l)} L", status="POOL", ref=p.id)
    elif kind == "BLEED":
        b = s.get(BleedRecord, i)
        n.update(label=b.bleed_no, sub=f"{float(b.volume_l)} L on {b.bled_on.isoformat()}", status="BLEED", ref=b.id)
    elif kind == "ANIMAL":
        a = s.get(Animal, i)
        n.update(label=a.animal_tag, sub=a.species, status=a.status, ref=a.id)
    return n


# ------------------------------------------------------------------ resolve + traverse
def resolve(s: Session, kind: str, ref: str) -> str:
    """Accept a numeric id or a business number (lot no, batch no, dispatch no, GRN no, PO no, vendor code...)."""
    kind = kind.upper()
    q = {"LOT": (MaterialBatch, MaterialBatch.lot_no), "BATCH": (ManufacturingBatch, ManufacturingBatch.batch_no), "DISPATCH": (Dispatch, Dispatch.dispatch_no),
         "GRN": (GRN, GRN.grn_no), "PO": (PurchaseOrder, PurchaseOrder.po_no), "VENDOR": (Vendor, Vendor.vendor_code), "CUSTOMER": (Customer, Customer.customer_code),
         "POOL": (PlasmaPool, PlasmaPool.pool_no), "ANIMAL": (Animal, Animal.animal_tag)}.get(kind)
    if q is None:
        raise ValidationFailed(f"Unknown entity type '{kind}'")
    Model, col = q
    obj = s.get(Model, int(ref)) if ref.isdigit() else s.execute(select(Model).where(col == ref)).scalars().first()
    if obj is None:
        raise NotFound(f"{kind} '{ref}' not found")
    return key(kind, obj.id)


def trace(s: Session, root: str, direction: str = "both", max_depth: int = 12) -> dict:
    if direction not in ("forward", "backward", "both"):
        raise ValidationFailed("direction must be forward, backward or both")
    nodes: dict[str, dict] = {root: describe(s, root)}
    edges: list[dict] = []
    seen_edges: set[tuple] = set()
    truncated = False
    for fn, rev in ((forward, False), (backward, True)):
        if (direction == "forward" and rev) or (direction == "backward" and not rev):
            continue
        frontier, depth, visited = [root], 0, {root}
        while frontier and depth < max_depth:
            nxt = []
            for k in frontier:
                for nb, label, qty in fn(s, k):
                    a, b = (nb, k) if rev else (k, nb)
                    if (a, b, label) not in seen_edges:
                        seen_edges.add((a, b, label))
                        edges.append({"from": a, "to": b, "label": label, "quantity": qty})
                    if nb not in nodes:
                        if len(nodes) >= MAX_NODES:
                            truncated = True
                            continue
                        nodes[nb] = describe(s, nb)
                    if nb not in visited:
                        visited.add(nb)
                        nxt.append(nb)
            frontier, depth = nxt, depth + 1
    table = [{"from": nodes[e["from"]]["label"], "from_type": nodes[e["from"]]["type"], "relation": e["label"], "to": nodes[e["to"]]["label"],
              "to_type": nodes[e["to"]]["type"], "quantity": e["quantity"]} for e in edges if e["from"] in nodes and e["to"] in nodes]
    return {"root": root, "direction": direction, "nodes": list(nodes.values()), "edges": edges, "table": table, "truncated": truncated}
