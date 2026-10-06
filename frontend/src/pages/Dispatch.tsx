import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { DataList, useLookup } from "../components/DataList";
import { Alert, Modal, PageHeader, ReasonDialog, StatusBadge } from "../components/ui";
import { useAuth } from "../hooks/useAuth";
import { api, errText } from "../services/api";
import { PrintButton } from "./Reports";

/* ------------------------------------------------------------------ Dispatch */
export function Dispatches() {
  const { can } = useAuth();
  const [sel, setSel] = useState<number | null>(null); const [creating, setCreating] = useState(false); const [reload, setReload] = useState<() => void>(() => () => {});
  return (<>
    <DataList title="Dispatch" crumbs={["Dispatch", "Orders"]} path="/dispatches" exportable={false}
      extraActions={can("dispatch.order.create") && <button className="btn btn-primary" onClick={() => setCreating(true)}><i className="bi bi-plus-lg" /> New dispatch</button>}
      filters={[{ key: "status", label: "Status", options: ["DRAFT", "VALIDATED", "APPROVED", "DISPATCHED", "DELIVERED", "CANCELLED"] }]}
      cols={[{ key: "dispatch_no", label: "Dispatch" }, { key: "dispatch_date", label: "Date" }, { key: "customer_name", label: "Customer" }, { key: "invoice_no", label: "Invoice" }, { key: "status", label: "Status", badge: true }]}
      onRow={(r, load) => { setSel(r.id); setReload(() => load); }} />
    {creating && <DispatchForm onClose={() => { setCreating(false); reload(); }} onCreated={(id) => { setCreating(false); setSel(id); }} />}
    {sel && <DispatchDetail id={sel} onClose={() => { setSel(null); reload(); }} />}
  </>);
}

function DispatchForm({ onClose, onCreated }: { onClose: () => void; onCreated: (id: number) => void }) {
  const custs = useLookup("/customers?is_active=true", "name", "id", "customer_code");
  const [stock, setStock] = useState<any[]>([]); const [err, setErr] = useState("");
  const [h, setH] = useState<any>({}); const [lines, setLines] = useState<Record<string, number>>({});
  useEffect(() => { api("/fg/available").then(setStock).catch((e) => setErr(errText(e))); }, []);
  const save = async () => {
    try {
      const r = await api("/dispatches", { method: "POST", body: { customer_id: Number(h.customer_id), invoice_no: h.invoice_no || null, transporter: h.transporter || null, vehicle_no: h.vehicle_no || null, reason: "Dispatch created",
        lines: Object.entries(lines).filter(([, q]) => q > 0).map(([k, q]) => { const [lot, loc] = k.split(":"); return { material_batch_id: Number(lot), location_id: Number(loc), quantity: q }; }) } });
      onCreated(r.id);
    } catch (e) { setErr(errText(e)); }
  };
  return (<Modal title="New dispatch" onClose={onClose} footer={<><button className="btn btn-outline-secondary" onClick={onClose}>Cancel</button><button className="btn btn-primary" disabled={!h.customer_id} onClick={save}>Save draft</button></>}>
    <Alert>{err}</Alert>
    <select className="form-select mb-2" onChange={(e) => setH({ ...h, customer_id: e.target.value })}><option value="">Customer…</option>{custs.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}</select>
    <div className="row g-2 mb-2">{[["invoice_no", "Invoice no."], ["transporter", "Transporter"], ["vehicle_no", "Vehicle no."]].map(([k, l]) => <div className="col-4" key={k}><input className="form-control" placeholder={l} onChange={(e) => setH({ ...h, [k]: e.target.value })} /></div>)}</div>
    <h6>Released finished goods</h6>
    <table className="table table-sm small"><thead><tr><th>Batch</th><th>Product</th><th>Expiry</th><th>Available</th><th style={{ width: 110 }}>Dispatch qty</th></tr></thead>
      <tbody>{stock.map((s) => (<tr key={`${s.lot_id}:${s.location_id}`}><td>{s.lot_no}</td><td>{s.material_code} {s.material_name}</td><td>{s.expiry_date ?? "—"}</td><td>{s.available}</td>
        <td><input type="number" className="form-control form-control-sm" max={s.available} onChange={(e) => setLines({ ...lines, [`${s.lot_id}:${s.location_id}`]: Number(e.target.value) })} /></td></tr>))}
        {stock.length === 0 && <tr><td colSpan={5} className="text-muted">No released, unheld finished-goods stock is available.</td></tr>}</tbody></table>
  </Modal>);
}

function DispatchDetail({ id, onClose }: { id: number; onClose: () => void }) {
  const { can } = useAuth(); const nav = useNavigate();
  const [d, setD] = useState<any>(null); const [err, setErr] = useState(""); const [chk, setChk] = useState<any>(null); const [sign, setSign] = useState<any>(null);
  const load = () => api(`/dispatches/${id}`).then(setD).catch((e) => setErr(errText(e)));
  useEffect(() => { load(); }, []);
  if (!d) return <Modal title="Dispatch" onClose={onClose}><Alert>{err}</Alert>Loading…</Modal>;
  const post = async (p: string, body?: any) => { try { await api(`/dispatches/${id}/${p}`, { method: "POST", body }); setErr(""); setChk(null); load(); } catch (e: any) { setErr(errText(e)); if (e?.details) setChk({ violations: e.details }); } };
  const check = async () => { try { setChk(await api(`/dispatches/${id}/check`)); } catch (e) { setErr(errText(e)); } };
  const s = d.status;
  return (<Modal title={`${d.dispatch_no} — ${d.customer_name}`} onClose={onClose}>
    <Alert>{err}</Alert>
    <div className="mb-2"><StatusBadge status={s} /> invoice {d.invoice_no ?? "—"} · {d.transporter ?? ""} {d.vehicle_no ?? ""}</div>
    <table className="table table-sm small"><thead><tr><th>Batch</th><th>Product</th><th>Qty</th><th>Expiry</th><th>CoA</th></tr></thead>
      <tbody>{d.lines.map((l: any) => <tr key={l.id}><td>{l.lot_no} <button className="btn btn-link btn-sm p-0" onClick={() => nav(`/trace?type=LOT&ref=${l.lot_no}`)}>trace</button></td><td>{l.material_code} {l.material_name}</td><td>{l.quantity}</td><td>{l.expiry_date}</td><td>{l.coa_id ?? "—"}</td></tr>)}</tbody></table>
    {chk && <div className="mb-2">{chk.violations.length === 0 ? <div className="alert alert-success py-1">All dispatch rules satisfied.</div> : chk.violations.map((v: any, i: number) => <div key={i} className={"alert py-1 mb-1 " + (v.severity === "BLOCK" ? "alert-danger" : "alert-warning")}><b>{v.rule_id}</b> {v.message}</div>)}</div>}
    <div className="d-flex gap-2 flex-wrap">
      <button className="btn btn-sm btn-outline-secondary" onClick={check}>Check rules</button>
      {can("reports.export.run") && <PrintButton path={`/dispatches/${id}/pdf`} label="Dispatch note (PDF)" />}
      {s === "DRAFT" && can("dispatch.order.validate") && <button className="btn btn-sm btn-primary" onClick={() => post("validate")}>Validate & reserve stock</button>}
      {s === "VALIDATED" && can("dispatch.order.update") && <button className="btn btn-sm btn-outline-secondary" onClick={() => setSign({ title: "Re-open for editing", path: "reopen", noPw: true })}>Re-open</button>}
      {s === "VALIDATED" && can("dispatch.order.approve") && <button className="btn btn-sm btn-success" onClick={() => setSign({ title: "Approve dispatch", path: "approve" })}><i className="bi bi-pen" /> Approve</button>}
      {s === "APPROVED" && can("dispatch.order.dispatch") && <button className="btn btn-sm btn-success" onClick={() => post("dispatch")}><i className="bi bi-truck" /> Dispatch</button>}
      {s === "DISPATCHED" && can("dispatch.order.deliver") && <button className="btn btn-sm btn-outline-success" onClick={() => post("deliver", { remarks: prompt("Delivery remarks") || null })}>Mark delivered</button>}
      {["DRAFT", "VALIDATED", "APPROVED"].includes(s) && can("dispatch.order.cancel") && <button className="btn btn-sm btn-outline-danger" onClick={() => setSign({ title: "Cancel dispatch", path: "cancel", noPw: true })}>Cancel</button>}</div>
    {sign && <ReasonDialog title={sign.title} needPassword={!sign.noPw} meaning="APPROVED_BY" onClose={() => setSign(null)}
      onSubmit={async (reason, password) => { try { await api(`/dispatches/${id}/${sign.path}`, { method: "POST", body: { reason, password } }); load(); } catch (e) { throw new Error(errText(e)); } }} />}
  </Modal>);
}

/* ------------------------------------------------------------------ Traceability */
const COLS = ["ANIMAL", "BLEED", "POOL", "VENDOR", "PO", "GRN", "LOT", "BATCH", "DISPATCH", "CUSTOMER"];
const COLOR: Record<string, string> = { LOT: "#0d6efd", BATCH: "#6f42c1", DISPATCH: "#198754", CUSTOMER: "#fd7e14", VENDOR: "#20c997", PO: "#6c757d", GRN: "#6c757d", POOL: "#d63384", BLEED: "#d63384", ANIMAL: "#d63384" };

function layout(nodes: any[]) {
  // ranks follow the material flow; nodes of the same rank are stacked
  const rank: Record<string, number> = { VENDOR: 0, ANIMAL: 0, PO: 1, BLEED: 1, GRN: 2, POOL: 2, LOT: 3, BATCH: 4, DISPATCH: 5, CUSTOMER: 6 };
  const byRank: Record<number, any[]> = {}; nodes.forEach((n) => { (byRank[rank[n.type] ?? 3] ||= []).push(n); });
  const pos: Record<string, { x: number; y: number }> = {};
  Object.entries(byRank).forEach(([r, list]) => list.forEach((n, i) => { pos[n.id] = { x: 20 + Number(r) * 200, y: 30 + i * 70 }; }));
  return pos;
}

export function Trace() {
  const params = new URLSearchParams(window.location.search);
  const [type, setType] = useState(params.get("type") || "LOT"); const [ref, setRef] = useState(params.get("ref") || ""); const [dir, setDir] = useState("both");
  const [t, setT] = useState<any>(null); const [err, setErr] = useState(""); const [view, setView] = useState("graph");
  const go = async () => { try { setT(await api(`/trace/${type}/${encodeURIComponent(ref)}?direction=${dir}`)); setErr(""); } catch (e) { setT(null); setErr(errText(e)); } };
  useEffect(() => { if (ref) go(); }, []);
  const pos = useMemo(() => (t ? layout(t.nodes) : {}), [t]);
  const height = t ? Math.max(...(Object.values(pos) as any[]).map((p) => p.y), 60) + 80 : 100;
  return (<>
    <PageHeader title="Traceability" crumbs={["Quality", "Traceability"]} />
    <div className="d-flex gap-2 mb-3 flex-wrap">
      <select className="form-select" style={{ width: 150 }} value={type} onChange={(e) => setType(e.target.value)}>{["LOT", "BATCH", "DISPATCH", "GRN", "PO", "VENDOR", "CUSTOMER", "POOL", "ANIMAL"].map((x) => <option key={x}>{x}</option>)}</select>
      <input className="form-control" style={{ width: 260 }} placeholder="Number / code (e.g. lot or batch no.)" value={ref} onChange={(e) => setRef(e.target.value)} onKeyDown={(e) => e.key === "Enter" && go()} />
      <select className="form-select" style={{ width: 150 }} value={dir} onChange={(e) => setDir(e.target.value)}><option value="both">Both directions</option><option value="backward">Backward (sources)</option><option value="forward">Forward (where used)</option></select>
      <button className="btn btn-primary" onClick={go}><i className="bi bi-diagram-3" /> Trace</button>
      {t && <div className="btn-group"><button className={"btn btn-outline-secondary" + (view === "graph" ? " active" : "")} onClick={() => setView("graph")}>Graph</button><button className={"btn btn-outline-secondary" + (view === "table" ? " active" : "")} onClick={() => setView("table")}>Table</button></div>}</div>
    <Alert>{err}</Alert>
    {t?.truncated && <div className="alert alert-warning">Result truncated at 500 nodes.</div>}
    {t && view === "graph" && <div className="card"><div className="card-body" style={{ overflowX: "auto" }}>
      <div className="small text-muted mb-1">{COLS.filter((c) => t.nodes.some((n: any) => n.type === c)).join(" → ")}</div>
      <svg width={40 + 7 * 200} height={height}>
        {t.edges.map((e: any, i: number) => { const a = pos[e.from], b = pos[e.to]; if (!a || !b) return null; return (<g key={i}><line x1={a.x + 120} y1={a.y + 20} x2={b.x} y2={b.y + 20} stroke="#adb5bd" markerEnd="url(#arr)" />
          <text x={(a.x + 120 + b.x) / 2} y={(a.y + b.y) / 2 + 12} fontSize="8" fill="#6c757d" textAnchor="middle">{e.label}{e.quantity != null ? ` ${e.quantity}` : ""}</text></g>); })}
        <defs><marker id="arr" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto"><path d="M0,0 L0,6 L8,3 z" fill="#adb5bd" /></marker></defs>
        {t.nodes.map((n: any) => (<g key={n.id} transform={`translate(${pos[n.id].x},${pos[n.id].y})`}><rect width="120" height="40" rx="6" fill="#fff" stroke={COLOR[n.type] || "#999"} strokeWidth={n.id === t.root ? 3 : 1.5} />
          <text x="6" y="14" fontSize="10" fontWeight="bold" fill={COLOR[n.type]}>{n.type}</text><text x="6" y="28" fontSize="11">{String(n.label).slice(0, 18)}</text><title>{`${n.label} — ${n.sub ?? ""} (${n.status ?? ""})`}</title></g>))}
      </svg></div></div>}
    {t && view === "table" && <table className="table table-sm"><thead><tr><th>From</th><th>Relation</th><th>To</th><th>Qty</th></tr></thead>
      <tbody>{t.table.map((r: any, i: number) => <tr key={i}><td>{r.from_type} {r.from}</td><td>{r.relation}</td><td>{r.to_type} {r.to}</td><td>{r.quantity ?? ""}</td></tr>)}</tbody></table>}
  </>);
}

/* ------------------------------------------------------------------ global search (header) */
export function GlobalSearch() {
  const nav = useNavigate(); const [q, setQ] = useState(""); const [res, setRes] = useState<any[]>([]);
  useEffect(() => { const h = setTimeout(() => { if (q.trim().length >= 2) api(`/search?q=${encodeURIComponent(q)}`).then(setRes).catch(() => setRes([])); else setRes([]); }, 250); return () => clearTimeout(h); }, [q]);
  const open = async (r: any) => { setQ(""); setRes([]); if (["LOT", "BATCH", "DISPATCH", "VENDOR", "GRN", "PO", "POOL"].includes(r.type)) nav(`/trace?type=${r.type}&ref=${encodeURIComponent(r.number)}`); else nav(r.route); };
  return (<div className="position-relative"><input className="form-control form-control-sm" style={{ width: 280 }} placeholder="Search lots, batches, GRN, PO… or scan QR" value={q} onChange={(e) => setQ(e.target.value)}
    onKeyDown={async (e) => { if (e.key === "Enter" && q.startsWith("merp://")) { try { const r = await api(`/qr/resolve?code=${encodeURIComponent(q)}`); open({ ...r, route: "/inventory" }); } catch { /* ignore */ } } }} />
    {res.length > 0 && <div className="list-group position-absolute shadow" style={{ zIndex: 1000, width: 360, maxHeight: 360, overflowY: "auto" }}>{res.map((r) => <button key={`${r.type}${r.id}`} className="list-group-item list-group-item-action py-1 small" onClick={() => open(r)}><span className="badge text-bg-secondary me-2">{r.type}</span>{r.number} {r.label && <span className="text-muted">— {r.label}</span>}</button>)}</div>}</div>);
}
