import { useEffect, useState } from "react";
import { DataList, useLookup } from "../components/DataList";
import { Alert, Modal, PageHeader, ReasonDialog, StatusBadge, fmt } from "../components/ui";
import { useAuth } from "../hooks/useAuth";
import { api, errText } from "../services/api";
import { PrintButton } from "./Reports";

async function openPdf(path: string, body: any) {
  const res: any = await api(path, { method: "POST", body, raw: true });
  const blob = await res.blob();
  window.open(URL.createObjectURL(blob), "_blank");
}

/* ------------------------------------------------------------------ GRN */
export function GRNs() {
  const { can } = useAuth();
  const [sel, setSel] = useState<number | null>(null); const [reload, setReload] = useState<() => void>(() => () => {}); const [creating, setCreating] = useState(false);
  return (<>
    <DataList title="Goods Receipt (GRN)" crumbs={["Warehouse", "GRN"]} path="/grn" exportable
      extraActions={can("grn.receipt.create") && <button className="btn btn-primary" onClick={() => setCreating(true)}><i className="bi bi-plus-lg" /> New GRN</button>}
      filters={[{ key: "status", label: "Status", options: ["DRAFT", "SUBMITTED", "QUARANTINE", "REJECTED", "CANCELLED"] }]}
      cols={[{ key: "grn_no", label: "GRN" }, { key: "grn_date", label: "Date" }, { key: "po_no", label: "PO" }, { key: "vendor_name", label: "Vendor" }, { key: "invoice_no", label: "Invoice" }, { key: "status", label: "Status", badge: true }]}
      onRow={(r, load) => { setSel(r.id); setReload(() => load); }} />
    {creating && <GRNForm onClose={() => { setCreating(false); reload(); }} onCreated={(id) => { setCreating(false); setSel(id); }} />}
    {sel && <GRNDetail id={sel} onClose={() => { setSel(null); reload(); }} />}
  </>);
}

function GRNForm({ onClose, onCreated }: { onClose: () => void; onCreated: (id: number) => void }) {
  const pos = useLookup("/purchase-orders?open=1", "po_no", "id");
  const [poId, setPoId] = useState(""); const [po, setPo] = useState<any>(null); const [h, setH] = useState<any>({}); const [lines, setLines] = useState<any[]>([]); const [err, setErr] = useState("");
  useEffect(() => { if (poId) api(`/purchase-orders/${poId}`).then((p) => { setPo(p); setLines(p.lines.map((l: any) => ({ po_line_id: l.id, material: `${l.material_code} ${l.material_name}`, ordered: l.quantity, received: l.received_quantity, pack_count: 1, coa_received: false }))); }); }, [poId]);
  const upd = (i: number, k: string, v: any) => setLines(lines.map((l, j) => (j === i ? { ...l, [k]: v } : l)));
  const save = async () => {
    try { const r = await api("/grn", { method: "POST", body: { po_id: Number(poId), ...h, reason: "GRN created", lines: lines.filter((l) => l.quantity_received).map((l) => ({ po_line_id: l.po_line_id, vendor_batch_no: l.vendor_batch_no, quantity_received: Number(l.quantity_received), pack_count: Number(l.pack_count), mfg_date: l.mfg_date || null, expiry_date: l.expiry_date || null, retest_date: l.retest_date || null, coa_received: !!l.coa_received })) } }); onCreated(r.id); }
    catch (e) { setErr(errText(e)); }
  };
  return (<Modal title="New GRN" onClose={onClose} footer={<><button className="btn btn-outline-secondary" onClick={onClose}>Cancel</button><button className="btn btn-primary" disabled={!poId} onClick={save}>Save draft</button></>}>
    <Alert>{err}</Alert>
    <select className="form-select mb-2" value={poId} onChange={(e) => setPoId(e.target.value)}><option value="">Purchase order…</option>{pos.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}</select>
    <div className="row g-2 mb-2"><div className="col-6"><input className="form-control" placeholder="Invoice no." onChange={(e) => setH({ ...h, invoice_no: e.target.value })} /></div><div className="col-6"><input className="form-control" placeholder="Vehicle no." onChange={(e) => setH({ ...h, vehicle_no: e.target.value })} /></div></div>
    {po && lines.map((l, i) => (<div key={i} className="border rounded p-2 mb-2 small"><b>{l.material}</b> — ordered {l.ordered}, received {l.received}
      <div className="row g-1 mt-1"><div className="col-4"><input className="form-control form-control-sm" placeholder="Vendor batch *" onChange={(e) => upd(i, "vendor_batch_no", e.target.value)} /></div>
        <div className="col-3"><input type="number" className="form-control form-control-sm" placeholder="Qty received" onChange={(e) => upd(i, "quantity_received", e.target.value)} /></div>
        <div className="col-2"><input type="number" className="form-control form-control-sm" placeholder="Packs" value={l.pack_count} onChange={(e) => upd(i, "pack_count", e.target.value)} /></div>
        <div className="col-3"><div className="form-check"><input type="checkbox" className="form-check-input" onChange={(e) => upd(i, "coa_received", e.target.checked)} /><label className="form-check-label">CoA</label></div></div>
        {[["mfg_date", "Mfg"], ["expiry_date", "Expiry"], ["retest_date", "Retest"]].map(([k, lab]) => <div className="col-4" key={k}><label className="form-label mb-0">{lab}</label><input type="date" className="form-control form-control-sm" onChange={(e) => upd(i, k, e.target.value)} /></div>)}</div></div>))}
  </Modal>);
}

function GRNDetail({ id, onClose }: { id: number; onClose: () => void }) {
  const { can } = useAuth();
  const locs = useLookup("/locations?is_quarantine=1", "name", "id", "location_code");
  const [d, setD] = useState<any>(null); const [err, setErr] = useState(""); const [ans, setAns] = useState<Record<number, any>>({}); const [act, setAct] = useState<null | string>(null); const [loc, setLoc] = useState(""); const [exc, setExc] = useState<any>(null);
  const load = () => api(`/grn/${id}`).then((x) => { setD(x); const m: any = {}; x.checklist.items.forEach((i: any) => (m[i.item_id] = { answer: i.answer, comment: i.comment })); setAns(m); }).catch((e) => setErr(errText(e)));
  useEffect(() => { load(); }, []);
  if (!d) return <Modal title="GRN" onClose={onClose}><Alert>{err}</Alert>Loading…</Modal>;
  const call = async (path: string, body?: any) => { try { await api(`/grn/${id}/${path}`, { method: "POST", body }); setErr(""); load(); } catch (e) { setErr(errText(e)); } };
  const saveChecklist = async () => { try { await api(`/grn/${id}/checklist`, { method: "PUT", body: { reason: "Checklist completed", answers: Object.entries(ans).filter(([, a]: any) => a.answer).map(([k, a]: any) => ({ item_id: Number(k), answer: a.answer, comment: a.comment })) } }); setErr(""); load(); } catch (e) { setErr(errText(e)); } };
  const cs = d.checklist;
  return (<Modal title={`${d.grn_no} — ${d.vendor_name}`} onClose={onClose}>
    <Alert>{err}</Alert>
    <div className="mb-2"><StatusBadge status={d.status} /> PO {d.po_no} · invoice {d.invoice_no ?? "—"} · {d.vehicle_no ?? ""}</div>
    <table className="table table-sm small"><thead><tr><th>Material</th><th>Vendor batch</th><th>Qty</th><th>Expiry</th><th>Lot</th></tr></thead>
      <tbody>{d.lines.map((l: any) => <tr key={l.id}><td>{l.material_code} {l.material_name}</td><td>{l.vendor_batch_no}</td><td>{l.quantity_received}</td><td>{l.expiry_date}</td><td>{l.lot_no ?? "—"}</td></tr>)}</tbody></table>
    {["SUBMITTED", "DRAFT"].includes(d.status) && <>
      <h6>Receipt checklist {cs.critical_failures.length > 0 && <span className="badge text-bg-danger ms-1">critical failure</span>}</h6>
      <table className="table table-sm small"><tbody>{cs.items.map((i: any) => (<tr key={i.item_id} className={i.answer === "NO" && i.critical ? "table-danger" : ""}>
        <td>{i.text}{i.critical && <span className="text-danger"> *</span>}</td>
        <td style={{ width: 150 }}>{["YES", "NO", "NA"].map((a) => <label key={a} className="me-2"><input type="radio" name={`i${i.item_id}`} checked={ans[i.item_id]?.answer === a} onChange={() => setAns({ ...ans, [i.item_id]: { ...ans[i.item_id], answer: a } })} /> {a}</label>)}</td>
        <td><input className="form-control form-control-sm" placeholder="comment" value={ans[i.item_id]?.comment ?? ""} onChange={(e) => setAns({ ...ans, [i.item_id]: { ...ans[i.item_id], comment: e.target.value } })} /></td>
        <td>{i.exception_granted ? <span className="badge text-bg-warning">QA exception {i.exception_ref}</span> : i.answer === "NO" && i.critical && can("grn.receipt.exception") && d.status === "SUBMITTED" && <button className="btn btn-sm btn-outline-warning" onClick={() => setExc(i)}>Exception</button>}</td></tr>))}</tbody></table>
      {can("grn.receipt.verify") && d.status === "SUBMITTED" && <button className="btn btn-sm btn-outline-primary mb-2" onClick={saveChecklist}>Save checklist</button>}</>}
    <div className="d-flex gap-2 flex-wrap align-items-center">
      {can("reports.export.run") && <PrintButton path={`/grn/${id}/pdf`} label="GRN (PDF)" />}
      {d.status === "DRAFT" && can("grn.receipt.submit") && <button className="btn btn-sm btn-primary" onClick={() => call("submit")}>Submit</button>}
      {d.status === "SUBMITTED" && can("grn.receipt.verify") && <>
        <select className="form-select form-select-sm" style={{ width: 220 }} value={loc} onChange={(e) => setLoc(e.target.value)}><option value="">Quarantine location…</option>{locs.map((l) => <option key={l.value} value={l.value}>{l.label}</option>)}</select>
        <button className="btn btn-sm btn-success" disabled={!loc} onClick={() => setAct("verify")}><i className="bi bi-pen" /> Verify & quarantine</button></>}
      {d.status === "SUBMITTED" && can("grn.receipt.reject") && <button className="btn btn-sm btn-outline-danger" onClick={() => setAct("reject")}><i className="bi bi-pen" /> Reject receipt</button>}</div>
    {act && <ReasonDialog title={act === "verify" ? "Verify GRN" : "Reject receipt"} needPassword meaning={act === "verify" ? "VERIFIED_BY" : "REJECTED_BY"} onClose={() => setAct(null)}
      onSubmit={async (reason, password) => { try { await api(`/grn/${id}/${act}`, { method: "POST", body: act === "verify" ? { password, reason, quarantine_location_id: Number(loc) } : { password, reason } }); load(); } catch (e) { throw new Error(errText(e)); } }} />}
    {exc && <ReasonDialog title={`QA exception: ${exc.text}`} needPassword meaning="APPROVED_BY" onClose={() => setExc(null)}
      onSubmit={async (reason, password) => { const ref = prompt("Deviation / exception reference"); if (!ref) throw new Error("Reference required"); try { await api(`/grn/${id}/exception`, { method: "POST", body: { item_id: exc.item_id, exception_ref: ref, password, reason } }); load(); } catch (e) { throw new Error(errText(e)); } }} />}
  </Modal>);
}

/* ------------------------------------------------------------------ Inventory */
export function Inventory() {
  const { can } = useAuth();
  const [tab, setTab] = useState("stock"); const [lot, setLot] = useState<number | null>(null);
  return (<>
    <ul className="nav nav-tabs mb-3">{[["stock", "Stock"], ["lots", "Lots"], ["holds", "Quality holds"], ["destr", "Destruction"]].map(([k, l]) => (<li className="nav-item" key={k}><button className={"nav-link" + (tab === k ? " active" : "")} onClick={() => setTab(k)}>{l}</button></li>))}</ul>
    {tab === "stock" && <DataList title="Stock by lot and location" crumbs={["Warehouse", "Stock"]} path="/inventory/stock" exportable
      filters={[{ key: "status", label: "Status", options: ["QUARANTINE", "APPROVED", "HOLD", "EXPIRED", "RETEST_DUE", "REJECTED"] }]}
      cols={[{ key: "material_code", label: "Material", render: (r) => `${r.material_code} ${r.material_name}` }, { key: "lot_no", label: "Lot" }, { key: "location", label: "Location" }, { key: "on_hand", label: "On hand" },
        { key: "available", label: "Available" }, { key: "unit", label: "UoM" }, { key: "expiry_date", label: "Expiry" }, { key: "status", label: "Status", badge: true }]} onRow={(r) => setLot(r.lot_id)} />}
    {tab === "lots" && <DataList title="Lots" crumbs={["Warehouse", "Lots"]} path="/lots" filters={[{ key: "disposition", label: "Disposition", options: ["QUARANTINE", "QC_TESTING", "QC_APPROVED", "QA_REVIEW", "APPROVED", "REJECTED", "EXPIRED", "DESTROYED"] }]}
      cols={[{ key: "lot_no", label: "Lot" }, { key: "material_code", label: "Material", render: (r) => `${r.material_code} ${r.material_name}` }, { key: "vendor_batch_no", label: "Vendor batch" }, { key: "quantity", label: "Qty" }, { key: "on_hand", label: "On hand" }, { key: "expiry_date", label: "Expiry" }, { key: "status", label: "Status", badge: true }]} onRow={(r) => setLot(r.id)} />}
    {tab === "holds" && <Holds />}
    {tab === "destr" && <DataList title="Destruction records" crumbs={["Warehouse", "Destruction"]} path="/destructions" cols={[{ key: "destruction_no", label: "No." }, { key: "material_batch_id", label: "Lot id" }, { key: "quantity", label: "Qty" }, { key: "method", label: "Method" }, { key: "status", label: "Status", badge: true }]} />}
    {lot && <LotDetail id={lot} onClose={() => setLot(null)} />}
  </>);
}

function Holds() {
  const { can } = useAuth(); const [sign, setSign] = useState<any>(null);
  return (<><DataList title="Quality holds" crumbs={["Quality", "Holds"]} path="/holds" filters={[{ key: "status", label: "Status", options: ["OPEN", "RELEASED"] }]}
    cols={[{ key: "hold_no", label: "Hold" }, { key: "entity_type", label: "Type" }, { key: "record_id", label: "Record" }, { key: "source", label: "Source" }, { key: "reason", label: "Reason" }, { key: "status", label: "Status", badge: true }]}
    onRow={(r) => r.status === "OPEN" && can("qa.hold.release") && setSign(r)} />
    {sign && <ReasonDialog title={`Release hold ${sign.hold_no}`} needPassword meaning="RELEASED_BY" onClose={() => setSign(null)} onSubmit={async (reason, password) => { try { await api(`/holds/${sign.id}/release`, { method: "POST", body: { password, reason } }); } catch (e) { throw new Error(errText(e)); } }} />}</>);
}

function LotDetail({ id, onClose }: { id: number; onClose: () => void }) {
  const { can } = useAuth();
  const [d, setD] = useState<any>(null); const [led, setLed] = useState<any[]>([]); const [err, setErr] = useState(""); const [hold, setHold] = useState(false); const [xfer, setXfer] = useState<any>(null);
  const load = () => { api(`/lots/${id}`).then(setD).catch((e) => setErr(errText(e))); if (can("inventory.ledger.read")) api(`/lots/${id}/ledger`).then(setLed).catch(() => {}); };
  useEffect(load, []);
  if (!d) return <Modal title="Lot" onClose={onClose}><Alert>{err}</Alert>Loading…</Modal>;
  const print = async (label_type: string) => { try { await openPdf(`/lots/${id}/labels`, { label_type, copies: 1, reprint_reason: "Reprint" }); load(); } catch (e) { setErr(errText(e)); } };
  return (<Modal title={`${d.lot_no} — ${d.material_name}`} onClose={onClose}>
    <Alert>{err}</Alert>
    <div className="mb-2"><StatusBadge status={d.status} /> disposition <b>{d.disposition}</b> · {d.on_hand} {d.unit} on hand · expiry {d.expiry_date ?? "—"} · retest {d.retest_date ?? "—"}</div>
    {d.holds.map((h: any) => <Alert key={h.id} kind="warning">HOLD {h.hold_no}: {h.reason}</Alert>)}
    {d.issue_violations.length > 0 && <Alert kind="secondary">Not issuable: {d.issue_violations.map((v: any) => v.message).join(" ")}</Alert>}
    <dl className="row small"><dt className="col-4">Vendor / batch</dt><dd className="col-8">{d.vendor_name ?? "—"} / {d.vendor_batch_no ?? "—"}</dd><dt className="col-4">GRN / PO</dt><dd className="col-8">{d.grn ? `${d.grn.grn_no} / ${d.grn.po_no}` : "—"}</dd>
      <dt className="col-4">Locations</dt><dd className="col-8">{d.balances.map((b: any) => `${b.location}: ${b.on_hand}`).join(", ") || "—"}</dd><dt className="col-4">Containers</dt><dd className="col-8">{d.containers.length}</dd></dl>
    <details className="mb-2"><summary className="small">Lot reconciliation</summary><pre className="small mono">{JSON.stringify(d.reconciliation, null, 1)}</pre></details>
    <div className="d-flex gap-2 flex-wrap mb-2">
      {can("label.lot.print") && <><button className="btn btn-sm btn-outline-secondary" onClick={() => print("QUARANTINE")}><i className="bi bi-printer" /> Quarantine label</button>
        {d.disposition === "APPROVED" && <button className="btn btn-sm btn-outline-secondary" onClick={() => print("APPROVED")}><i className="bi bi-printer" /> Approved label</button>}</>}
      {can("qa.hold.place") && <button className="btn btn-sm btn-outline-danger" onClick={() => setHold(true)}>Place hold</button>}
      {can("inventory.stock.transfer") && d.balances[0] && <button className="btn btn-sm btn-outline-primary" onClick={() => setXfer({ from: d.balances[0].location_id })}>Transfer</button>}</div>
    {led.length > 0 && <table className="table table-sm small"><thead><tr><th>#</th><th>Type</th><th>Qty</th><th>From</th><th>To</th><th>Ref</th><th>When</th></tr></thead><tbody>{led.map((t) => <tr key={t.id}><td>{t.id}</td><td>{t.txn_type}</td><td>{t.quantity}</td><td>{t.from_location_id ?? ""}</td><td>{t.to_location_id ?? ""}</td><td>{t.ref_doc_type} {t.ref_doc_id}</td><td>{fmt(t.txn_ts)}</td></tr>)}</tbody></table>}
    {hold && <ReasonDialog title="Place quality hold" onClose={() => setHold(false)} onSubmit={async (reason) => { try { await api("/holds", { method: "POST", body: { entity_type: "MATERIAL_BATCH", record_id: id, reason } }); load(); } catch (e) { throw new Error(errText(e)); } }} />}
    {xfer && <ReasonDialog title="Transfer stock" onClose={() => setXfer(null)} onSubmit={async (reason) => { const to = prompt("Destination location id"); const q = prompt("Quantity"); if (!to || !q) throw new Error("Destination and quantity required"); try { await api(`/lots/${id}/transfer`, { method: "POST", body: { from_location_id: xfer.from, to_location_id: Number(to), quantity: Number(q), reason } }); load(); } catch (e) { throw new Error(errText(e)); } }} />}
  </Modal>);
}
