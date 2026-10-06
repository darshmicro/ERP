import { useEffect, useState } from "react";
import { DataList, useLookup } from "../components/DataList";
import { Alert, Modal, PageHeader, ReasonDialog, StatusBadge, fmt } from "../components/ui";
import { useAuth } from "../hooks/useAuth";
import { api, errText } from "../services/api";
import { PrintButton } from "./Reports";

function Chain({ wf }: { wf: any }) {
  if (!wf) return null;
  return (<div className="mb-2"><div className="small fw-bold">Approval chain</div>
    <div className="d-flex gap-2 flex-wrap align-items-center small">{wf.steps.map((s: any) => (<span key={s.seq} className={"badge " + (wf.status === "APPROVED" || s.seq < wf.current_seq ? "text-bg-success" : s.seq === wf.current_seq && wf.status === "IN_PROGRESS" ? "text-bg-warning" : "text-bg-secondary")}>{s.seq}. {s.name} ({s.role}){s.esig ? " ✍" : ""}</span>))}</div>
    <ul className="small mb-0 mt-1">{wf.history.map((h: any, i: number) => <li key={i}>{h.decision} by {h.by} {h.signed && "(e-signed)"} — {fmt(h.at)} {h.comment && `· ${h.comment}`}</li>)}</ul></div>);
}

/* ------------------------------------------------------------------ Purchase requests */
export function PurchaseRequests() {
  const { can } = useAuth();
  const mats = useLookup("/materials?master_status=ACTIVE", "name", "id", "material_code");
  const [sel, setSel] = useState<number | null>(null); const [reload, setReload] = useState<() => void>(() => () => {}); const [creating, setCreating] = useState(false);
  return (<>
    <DataList title="Purchase Requests" crumbs={["Purchase", "Purchase requests"]} path="/purchase-requests" exportable
      extraActions={can("pr.request.create") && <button className="btn btn-primary" onClick={() => setCreating(true)}><i className="bi bi-plus-lg" /> New request</button>}
      filters={[{ key: "status", label: "Status", options: ["DRAFT", "SUBMITTED", "DEPARTMENT_APPROVED", "APPROVED", "CONVERTED", "REJECTED", "CANCELLED"] }, { key: "priority", label: "Priority", options: ["LOW", "NORMAL", "HIGH", "URGENT"] }]}
      cols={[{ key: "pr_no", label: "PR no." }, { key: "request_date", label: "Date" }, { key: "requested_by", label: "Requested by" }, { key: "priority", label: "Priority" }, { key: "purpose", label: "Purpose" }, { key: "status", label: "Status", badge: true }]}
      onRow={(r, load) => { setSel(r.id); setReload(() => load); }} />
    {creating && <PRForm mats={mats} onClose={() => { setCreating(false); reload(); }} onCreated={(id) => { setCreating(false); setSel(id); }} />}
    {sel && <PRDetail id={sel} onClose={() => { setSel(null); reload(); }} />}
  </>);
}

function PRForm({ mats, onClose, onCreated }: { mats: any[]; onClose: () => void; onCreated: (id: number) => void }) {
  const [h, setH] = useState<any>({ priority: "NORMAL" }); const [lines, setLines] = useState<any[]>([{}]); const [err, setErr] = useState("");
  const save = async () => {
    try { const r = await api("/purchase-requests", { method: "POST", body: { ...h, reason: "Purchase request created", lines: lines.filter((l) => l.material_id).map((l) => ({ material_id: Number(l.material_id), quantity: Number(l.quantity), required_date: l.required_date || null, remarks: l.remarks || null })) } }); onCreated(r.id); }
    catch (e) { setErr(errText(e)); }
  };
  return (<Modal title="New purchase request" onClose={onClose} footer={<><button className="btn btn-outline-secondary" onClick={onClose}>Cancel</button><button className="btn btn-primary" onClick={save}>Save draft</button></>}>
    <Alert>{err}</Alert>
    <div className="row g-2 mb-2"><div className="col-8"><input className="form-control" placeholder="Purpose" onChange={(e) => setH({ ...h, purpose: e.target.value })} /></div>
      <div className="col-4"><select className="form-select" value={h.priority} onChange={(e) => setH({ ...h, priority: e.target.value })}>{["LOW", "NORMAL", "HIGH", "URGENT"].map((x) => <option key={x}>{x}</option>)}</select></div></div>
    {lines.map((l, i) => (<div className="row g-1 mb-1" key={i}>
      <div className="col-5"><select className="form-select form-select-sm" value={l.material_id ?? ""} onChange={(e) => setLines(lines.map((x, j) => (j === i ? { ...x, material_id: e.target.value } : x)))}><option value="">Material…</option>{mats.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}</select></div>
      <div className="col-3"><input className="form-control form-control-sm" type="number" placeholder="Qty" onChange={(e) => setLines(lines.map((x, j) => (j === i ? { ...x, quantity: e.target.value } : x)))} /></div>
      <div className="col-4"><input className="form-control form-control-sm" type="date" onChange={(e) => setLines(lines.map((x, j) => (j === i ? { ...x, required_date: e.target.value } : x)))} /></div></div>))}
    <button className="btn btn-sm btn-outline-secondary" onClick={() => setLines([...lines, {}])}>+ line</button>
    <div className="form-text">Only ACTIVE materials can be requested. The request goes to your department head, then Purchase review.</div>
  </Modal>);
}

function PRDetail({ id, onClose }: { id: number; onClose: () => void }) {
  const { can, me } = useAuth();
  const [d, setD] = useState<any>(null); const [err, setErr] = useState(""); const [act, setAct] = useState<null | { title: string; kind: string; sign: boolean }>(null);
  const load = () => api(`/purchase-requests/${id}`).then(setD).catch((e) => setErr(errText(e)));
  useEffect(() => { load(); }, []);
  if (!d) return <Modal title="Purchase request" onClose={onClose}><Alert>{err}</Alert>Loading…</Modal>;
  const mine = d.requested_by_id === me?.user.id;
  const wf = d.workflow; const step = wf?.steps.find((s: any) => s.seq === wf.current_seq);
  return (<Modal title={`${d.pr_no} — ${d.status}`} onClose={onClose}>
    <Alert>{err}</Alert>
    <div className="mb-2"><StatusBadge status={d.status} /> {d.priority} · {d.requested_by} · {d.request_date} <div className="small">{d.purpose}</div></div>
    <table className="table table-sm small"><thead><tr><th>#</th><th>Material</th><th>Qty</th><th>Required</th></tr></thead><tbody>{d.lines.map((l: any) => <tr key={l.id}><td>{l.line_no}</td><td>{l.material_id}</td><td>{l.quantity}</td><td>{l.required_date ?? ""}</td></tr>)}</tbody></table>
    <Chain wf={wf} />
    <div className="d-flex gap-2 flex-wrap">
      {d.status === "DRAFT" && mine && <button className="btn btn-sm btn-primary" onClick={async () => { try { await api(`/purchase-requests/${id}/submit`, { method: "POST" }); load(); } catch (e) { setErr(errText(e)); } }}>Submit</button>}
      {["SUBMITTED", "DEPARTMENT_APPROVED"].includes(d.status) && can("pr.request.approve") && <>
        <button className="btn btn-sm btn-success" onClick={() => setAct({ title: "Approve request", kind: "APPROVE", sign: !!step?.esig })}>Approve</button>
        <button className="btn btn-sm btn-outline-danger" onClick={() => setAct({ title: "Reject request", kind: "REJECT", sign: !!step?.esig })}>Reject</button></>}
      {["DRAFT", "SUBMITTED", "DEPARTMENT_APPROVED", "APPROVED"].includes(d.status) && can("pr.request.cancel") && <button className="btn btn-sm btn-outline-secondary" onClick={() => setAct({ title: "Cancel request", kind: "CANCEL", sign: false })}>Cancel</button>}
    </div>
    {act && <ReasonDialog title={act.title} needPassword={act.sign} meaning="APPROVED_BY" onClose={() => setAct(null)} onSubmit={async (reason, password) => { try {
      if (act.kind === "CANCEL") await api(`/purchase-requests/${id}/cancel`, { method: "POST", body: { reason } });
      else await api(`/purchase-requests/${id}/decision`, { method: "POST", body: { decision: act.kind, comment: reason, password: act.sign ? password : undefined } });
      load(); } catch (e) { throw new Error(errText(e)); } }} />}
  </Modal>);
}

/* ------------------------------------------------------------------ Purchase orders */
export function PurchaseOrders() {
  const { can } = useAuth();
  const [sel, setSel] = useState<number | null>(null); const [reload, setReload] = useState<() => void>(() => () => {}); const [creating, setCreating] = useState(false);
  return (<>
    <DataList title="Purchase Orders" crumbs={["Purchase", "Purchase orders"]} path="/purchase-orders" exportable
      extraActions={can("po.order.create") && <button className="btn btn-primary" onClick={() => setCreating(true)}><i className="bi bi-plus-lg" /> New PO</button>}
      filters={[{ key: "status", label: "Status", options: ["DRAFT", "PENDING_APPROVAL", "APPROVED", "PARTIALLY_RECEIVED", "CLOSED", "REJECTED", "CANCELLED"] }]}
      cols={[{ key: "po_no", label: "PO no." }, { key: "po_date", label: "Date" }, { key: "vendor_code", label: "Vendor", render: (r) => `${r.vendor_code} ${r.vendor_name}` }, { key: "total", label: "Total", render: (r) => r.total?.toLocaleString() }, { key: "status", label: "Status", badge: true }]}
      onRow={(r, load) => { setSel(r.id); setReload(() => load); }} />
    {creating && <POForm onClose={() => { setCreating(false); reload(); }} onCreated={(id) => { setCreating(false); setSel(id); }} />}
    {sel && <PODetail id={sel} onClose={() => { setSel(null); reload(); }} />}
  </>);
}

function Gate({ res }: { res: any }) {
  if (!res) return null;
  return (<div className="mb-2">{res.allowed ? <Alert kind="success">All purchase rules satisfied.</Alert> : <Alert>{res.results.filter((r: any) => r.severity === "BLOCK")[0]?.message}</Alert>}
    <ul className="small mb-0">{res.results.map((r: any, i: number) => <li key={i} className={r.severity === "BLOCK" ? "text-danger" : "text-warning"}><b>{r.rule_id}</b> {r.message}</li>)}</ul></div>);
}

function POForm({ onClose, onCreated }: { onClose: () => void; onCreated: (id: number) => void }) {
  const vendors = useLookup("/vendors?approval_status=APPROVED", "name", "id", "vendor_code");
  const mats = useLookup("/materials?master_status=ACTIVE", "name", "id", "material_code");
  const [h, setH] = useState<any>({ currency: "INR" }); const [lines, setLines] = useState<any[]>([{}]); const [res, setRes] = useState<any>(null); const [err, setErr] = useState("");
  const body = () => ({ ...h, vendor_id: Number(h.vendor_id), delivery_date: h.delivery_date || null, reason: "Purchase order created", lines: lines.filter((l) => l.material_id).map((l) => ({ material_id: Number(l.material_id), quantity: Number(l.quantity), rate: Number(l.rate), tax_pct: Number(l.tax_pct || 0) })) });
  const check = async () => { try { setErr(""); setRes(await api("/purchase-orders/validate", { method: "POST", body: body() })); } catch (e) { setErr(errText(e)); } };
  const save = async () => { try { const r = await api("/purchase-orders", { method: "POST", body: body() }); onCreated(r.id); } catch (e: any) { setErr(errText(e)); if (e.body?.details) setRes({ allowed: false, results: e.body.details }); } };
  const set = (k: string) => (e: any) => setH({ ...h, [k]: e.target.value });
  return (<Modal title="New purchase order" onClose={onClose} footer={<><button className="btn btn-outline-secondary" onClick={check} disabled={!h.vendor_id}>Check purchase rules</button><button className="btn btn-primary" onClick={save} disabled={!h.vendor_id}>Save draft</button></>}>
    <Alert>{err}</Alert>
    <div className="row g-2 mb-2"><div className="col-12"><select className="form-select" onChange={set("vendor_id")}><option value="">Vendor…</option>{vendors.map((v) => <option key={v.value} value={v.value}>{v.label}</option>)}</select></div>
      <div className="col-6"><input className="form-control" placeholder="Payment terms" onChange={set("payment_terms")} /></div><div className="col-6"><input type="date" className="form-control" onChange={set("delivery_date")} /></div>
      <div className="col-12"><textarea className="form-control" rows={2} placeholder="Quality requirements" onChange={set("quality_requirements")} /></div></div>
    {lines.map((l, i) => (<div className="row g-1 mb-1" key={i}>
      <div className="col-5"><select className="form-select form-select-sm" onChange={(e) => setLines(lines.map((x, j) => (j === i ? { ...x, material_id: e.target.value } : x)))}><option value="">Material…</option>{mats.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}</select></div>
      {["quantity", "rate", "tax_pct"].map((k) => <div className="col-2" key={k}><input className="form-control form-control-sm" type="number" placeholder={k === "tax_pct" ? "Tax %" : k} onChange={(e) => setLines(lines.map((x, j) => (j === i ? { ...x, [k]: e.target.value } : x)))} /></div>)}</div>))}
    <button className="btn btn-sm btn-outline-secondary mb-2" onClick={() => setLines([...lines, {}])}>+ line</button>
    <Gate res={res} />
  </Modal>);
}

function PODetail({ id, onClose }: { id: number; onClose: () => void }) {
  const { can } = useAuth();
  const [d, setD] = useState<any>(null); const [err, setErr] = useState(""); const [act, setAct] = useState<null | { title: string; kind: string; sign: boolean }>(null);
  const load = () => api(`/purchase-orders/${id}`).then(setD).catch((e) => setErr(errText(e)));
  useEffect(() => { load(); }, []);
  if (!d) return <Modal title="Purchase order" onClose={onClose}><Alert>{err}</Alert>Loading…</Modal>;
  const run = async (path: string) => { try { await api(`/purchase-orders/${id}/${path}`, { method: "POST" }); setErr(""); load(); } catch (e) { setErr(errText(e)); } };
  return (<Modal title={`${d.po_no} — ${d.vendor_name}`} onClose={onClose}>
    <Alert>{err}</Alert>
    {["APPROVED", "PARTIALLY_RECEIVED", "CLOSED"].includes(d.status) && <div className="mb-2"><PrintButton path={`/purchase-orders/${id}/pdf`} label="Purchase order (PDF)" /></div>}
    <div className="mb-2"><StatusBadge status={d.status} /> {d.po_date} · {d.currency} <b>{d.total?.toLocaleString()}</b>
      {d.vendor_qualification && <span className="ms-2 small">Vendor qualification v{d.vendor_qualification.version_no} <StatusBadge status={d.vendor_qualification.status} /> due {d.vendor_qualification.due}</span>}</div>
    <table className="table table-sm small"><thead><tr><th>#</th><th>Material</th><th>Qty</th><th>Rate</th><th>Tax%</th><th>Total</th><th>Spec / mapping</th></tr></thead>
      <tbody>{d.lines.map((l: any) => <tr key={l.id}><td>{l.line_no}</td><td>{l.material_code} {l.material_name}</td><td>{l.quantity}</td><td>{l.rate}</td><td>{l.tax_pct}</td><td>{l.line_total}</td><td className="mono">spec#{l.specification_id} / map#{l.vendor_material_id}</td></tr>)}</tbody></table>
    {d.validation && <details className="mb-2"><summary className="small">Purchase-rule results at {d.validation.stage}</summary><ul className="small">{d.validation.results.map((r: any, i: number) => <li key={i}><b>{r.rule_id}</b> {r.severity} — {r.message}</li>)}</ul></details>}
    <Chain wf={d.workflow} />
    <div className="d-flex gap-2 flex-wrap">
      {d.status === "DRAFT" && can("po.order.submit") && <button className="btn btn-sm btn-primary" onClick={() => run("submit")}>Submit for approval</button>}
      {d.status === "PENDING_APPROVAL" && can("po.order.approve") && <>
        <button className="btn btn-sm btn-success" onClick={() => setAct({ title: "Approve purchase order", kind: "APPROVE", sign: true })}><i className="bi bi-pen" /> Approve</button>
        <button className="btn btn-sm btn-outline-danger" onClick={() => setAct({ title: "Reject purchase order", kind: "REJECT", sign: true })}>Reject</button></>}
      {["DRAFT", "PENDING_APPROVAL", "APPROVED"].includes(d.status) && can("po.order.cancel") && <button className="btn btn-sm btn-outline-secondary" onClick={() => setAct({ title: "Cancel purchase order", kind: "CANCEL", sign: d.status !== "DRAFT" })}>Cancel</button>}
    </div>
    {act && <ReasonDialog title={act.title} needPassword={act.sign} meaning="APPROVED_BY" onClose={() => setAct(null)} onSubmit={async (reason, password) => { try {
      if (act.kind === "CANCEL") await api(`/purchase-orders/${id}/cancel`, { method: "POST", body: { reason, password: act.sign ? password : undefined } });
      else await api(`/purchase-orders/${id}/decision`, { method: "POST", body: { decision: act.kind, comment: reason, password } });
      load(); } catch (e) { throw new Error(errText(e)); } }} />}
  </Modal>);
}
