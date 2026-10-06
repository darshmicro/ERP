import { useEffect, useState } from "react";
import { useLookup } from "../components/DataList";
import { Alert, Modal, PageHeader } from "../components/ui";
import { useAuth } from "../hooks/useAuth";
import { api, errText } from "../services/api";
import { CreateDialog, Page, RecordDialog } from "./Quality";

export function RateCards() {
  return <Page group="Costing" title="Cost rate cards" crumb="Rate cards" path="/costing/rate-cards" createPerm="costing.rate.create"
    filters={[{ key: "status", label: "Status", options: ["DRAFT", "UNDER_REVIEW", "APPROVED", "SUPERSEDED"] }]}
    cols={[{ key: "card_no", label: "Card" }, { key: "version_no", label: "Ver" }, { key: "title", label: "Title" }, { key: "labour_rate_per_hour", label: "Labour /h" }, { key: "machine_rate_per_hour", label: "Machine /h" }, { key: "overhead_pct", label: "Overhead %" }, { key: "status", label: "Status", badge: true }]}
    create={(close: any, created: any) => <CreateDialog title="New cost rate card" path="/costing/rate-cards" onClose={close} onCreated={created}
      fields={[{ key: "title", label: "Title" }, { key: "currency", label: "Currency (3 letters)" }, { key: "labour_rate_per_hour", label: "Labour rate per hour", type: "number" }, { key: "machine_rate_per_hour", label: "Machine rate per hour", type: "number" }, { key: "overhead_pct", label: "Overhead % of conversion cost", type: "number" }]} />}
    detail={(id: number, close: any) => <RecordDialog base="/costing/rate-cards" id={id} onClose={close} title={(d) => `${d.card_no} v${d.version_no} — ${d.title}`}
      fields={[["Currency", (d) => d.currency], ["Labour / hour", (d) => d.labour_rate_per_hour], ["Machine / hour", (d) => d.machine_rate_per_hour], ["Overhead %", (d) => d.overhead_pct]]}
      actions={[{ label: "Submit for review", path: "submit", perm: "costing.rate.update", show: (d) => d.status === "DRAFT" },
        { label: "Approve (e-signature)", path: "approve", perm: "costing.rate.approve", show: (d) => d.status === "UNDER_REVIEW", sign: true, cls: "btn-success" },
        { label: "New version", path: "new-version", perm: "costing.rate.create", show: (d) => d.status === "APPROVED", reason: true }]} />} />;
}

export function BatchCosts() {
  const { can } = useAuth(); const [calc, setCalc] = useState(false);
  const batches = useLookup("/mfg/batches", "batch_no", "id");
  return (<><Page group="Costing" title="Batch costs" crumb="Batch costs" path="/costing/batch-costs"
    filters={[{ key: "status", label: "Status", options: ["DRAFT", "APPROVED"] }]}
    cols={[{ key: "batch_no", label: "Batch" }, { key: "material_cost", label: "Material" }, { key: "labour_cost", label: "Labour" }, { key: "machine_cost", label: "Machine" }, { key: "overhead_cost", label: "Overhead" }, { key: "total_cost", label: "Total" }, { key: "unit_cost", label: "Unit cost" }, { key: "variance_pct", label: "Var %" }, { key: "status", label: "Status", badge: true }]}
    detail={(id: number, close: any) => <RecordDialog base="/costing/batch-costs" id={id} onClose={close} title={(d) => `Batch cost ${d.batch_no}`}
      fields={[["Total", (d) => `${d.total_cost} ${d.currency}`], ["Output quantity", (d) => d.output_qty], ["Unit cost", (d) => d.unit_cost], ["Standard unit cost", (d) => d.standard_unit_cost], ["Variance", (d) => d.variance], ["Labour / machine hours", (d) => `${d.labour_hours} / ${d.machine_hours}`]]}
      extra={(d) => <table className="table table-sm small"><thead><tr><th>Lot</th><th>Net qty</th><th>Unit cost</th><th>Basis</th><th>Amount</th></tr></thead><tbody>{(d.lines || []).map((l: any) => <tr key={l.lot_id}><td>{l.lot_no}</td><td>{l.net_qty}</td><td>{l.unit_cost}</td><td>{l.basis}</td><td>{l.amount}</td></tr>)}</tbody></table>}
      actions={[{ label: "Approve (e-signature)", path: "approve", perm: "costing.batch.approve", show: (d) => d.status === "DRAFT", sign: true, cls: "btn-success" }]} />} />
    {can("costing.batch.calculate") && <div className="position-fixed bottom-0 end-0 p-3" style={{ zIndex: 1000 }}><button className="btn btn-primary" onClick={() => setCalc(true)}>Calculate batch cost</button></div>}
    {calc && <CalcDialog batches={batches} onClose={() => setCalc(false)} />}</>);
}

function CalcDialog({ batches, onClose }: { batches: { value: any; label: string }[]; onClose: () => void }) {
  const [v, setV] = useState<any>({ labour_hours: 0, machine_hours: 0 }); const [err, setErr] = useState("");
  const go = async () => { try { await api(`/costing/batches/${v.batch}/calculate`, { method: "POST", body: { labour_hours: v.labour_hours, machine_hours: v.machine_hours, reason: "Batch cost calculated" } }); onClose(); } catch (e) { setErr(errText(e)); } };
  return (<Modal title="Calculate batch cost" onClose={onClose} footer={<button className="btn btn-primary" onClick={go}>Calculate</button>}><Alert>{err}</Alert>
    <label className="form-label small mb-0">Batch</label><select className="form-select mb-2" onChange={(e) => setV({ ...v, batch: e.target.value })}><option value="">…</option>{batches.map((b) => <option key={b.value} value={b.value}>{b.label}</option>)}</select>
    <label className="form-label small mb-0">Labour hours</label><input type="number" className="form-control mb-2" onChange={(e) => setV({ ...v, labour_hours: Number(e.target.value) })} />
    <label className="form-label small mb-0">Machine hours</label><input type="number" className="form-control" onChange={(e) => setV({ ...v, machine_hours: Number(e.target.value) })} /></Modal>);
}

export function StandardCosts() {
  const { can } = useAuth(); const mats = useLookup("/materials", "name", "id", "material_code"); const [rows, setRows] = useState<any[]>([]); const [err, setErr] = useState(""); const [v, setV] = useState<any>({});
  const load = () => api("/costing/standards?limit=200").then((r) => setRows(r.items)).catch((e) => setErr(errText(e)));
  useEffect(() => { load(); }, []);
  return (<><PageHeader title="Standard costs" crumbs={["Costing", "Standards"]} /><Alert>{err}</Alert>
    {can("costing.standard.update") && <div className="row g-1 mb-3"><div className="col-5"><select className="form-select form-select-sm" onChange={(e) => setV({ ...v, material_id: Number(e.target.value) })}><option value="">Material…</option>{mats.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}</select></div>
      <div className="col-2"><input type="number" step="any" className="form-control form-control-sm" placeholder="Std unit cost" onChange={(e) => setV({ ...v, std_unit_cost: Number(e.target.value) })} /></div>
      <div className="col-4"><input className="form-control form-control-sm" placeholder="Reason for the change" onChange={(e) => setV({ ...v, reason: e.target.value })} /></div>
      <div className="col-1"><button className="btn btn-sm btn-primary" onClick={async () => { try { await api("/costing/standards", { method: "PUT", body: v }); setErr(""); load(); } catch (e) { setErr(errText(e)); } }}>Set</button></div></div>}
    <table className="table table-sm"><thead><tr><th>Material</th><th>Standard unit cost</th><th>Currency</th></tr></thead><tbody>{rows.map((r) => <tr key={r.id}><td>{r.material_name}</td><td>{r.std_unit_cost}</td><td>{r.currency}</td></tr>)}</tbody></table></>);
}

export function Valuation() {
  const [d, setD] = useState<any>(null); const [err, setErr] = useState("");
  useEffect(() => { api("/costing/valuation").then(setD).catch((e) => setErr(errText(e))); }, []);
  return (<><PageHeader title="Inventory valuation" crumbs={["Costing", "Valuation"]} /><Alert>{err}</Alert>
    {d && <><div className="mb-2">Total value of costed lots: <b>{d.total_value}</b> · lots on stock: {d.lots} · <span className={d.uncosted_lots ? "text-danger" : ""}>without cost: {d.uncosted_lots}</span></div>
      <table className="table table-sm"><thead><tr><th>Lot</th><th>Disposition</th><th>Qty on hand</th><th>Unit cost</th><th>Basis</th><th>Value</th></tr></thead><tbody>{d.items.map((i: any) => <tr key={i.lot_id} className={i.unit_cost ? "" : "table-warning"}><td>{i.lot_no}</td><td>{i.disposition}</td><td>{i.qty_on_hand}</td><td>{i.unit_cost ?? "NO COST"}</td><td>{i.basis}</td><td>{i.value}</td></tr>)}</tbody></table></>}</>);
}
