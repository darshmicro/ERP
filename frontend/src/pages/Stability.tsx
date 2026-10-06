import { useEffect, useState } from "react";
import { useLookup } from "../components/DataList";
import { Alert, Modal, PageHeader, ReasonDialog } from "../components/ui";
import { useAuth } from "../hooks/useAuth";
import { api, errText } from "../services/api";
import { CreateDialog, Page, RecordDialog } from "./Quality";

const CTYPES = ["LONG_TERM", "INTERMEDIATE", "ACCELERATED", "STRESS", "REFRIGERATED", "FROZEN"];

export function StabilityProtocols() {
  const mats = useLookup("/materials?status=ACTIVE", "name", "id", "material_code"); const specs = useLookup("/specifications?status=APPROVED", "spec_no", "id");
  return <Page group="Stability" title="Stability protocols" crumb="Protocols" path="/stability/protocols" createPerm="stability.protocol.create"
    filters={[{ key: "status", label: "Status", options: ["DRAFT", "UNDER_REVIEW", "APPROVED", "SUPERSEDED"] }]}
    cols={[{ key: "protocol_no", label: "Protocol" }, { key: "version_no", label: "Ver" }, { key: "title", label: "Title" }, { key: "material_name", label: "Product" }, { key: "status", label: "Status", badge: true }]}
    create={(close: any, created: any) => <CreateDialog title="New stability protocol" path="/stability/protocols" onClose={close} onCreated={created}
      fields={[{ key: "title", label: "Title" }, { key: "material_id", label: "Product", choices: mats }, { key: "specification_id", label: "Approved specification", choices: specs }, { key: "container_closure", label: "Container closure" }, { key: "proposed_shelf_life_months", label: "Proposed shelf life (months)", type: "number" }, { key: "pull_window_days", label: "Pull window ± days", type: "number" }, { key: "objective", label: "Objective", area: true }]} />}
    detail={(id: number, close: any) => <ProtocolDetail id={id} onClose={close} />} />;
}

function ProtocolDetail({ id, onClose }: { id: number; onClose: () => void }) {
  const { can } = useAuth(); const [err, setErr] = useState(""); const [c, setC] = useState<any>({ condition_type: "LONG_TERM" }); const [m, setM] = useState<any>({});
  const add = async (path: string, body: any, reload: () => void) => { try { await api(`/stability/protocols/${id}/${path}`, { method: "POST", body }); setErr(""); reload(); } catch (e) { setErr(errText(e)); } };
  return <RecordDialog base="/stability/protocols" id={id} onClose={onClose} title={(d) => `${d.protocol_no} v${d.version_no} — ${d.title}`}
    fields={[["Product", (d) => d.material_name], ["Container closure", (d) => d.container_closure], ["Proposed shelf life", (d) => d.proposed_shelf_life_months && `${d.proposed_shelf_life_months} months`], ["Pull window", (d) => `± ${d.pull_window_days} days`]]}
    extra={(d, reload) => (<div className="mb-2"><Alert>{err}</Alert>
      <b className="small">Storage conditions</b><ul className="small">{d.conditions.map((x: any) => <li key={x.id}>{x.label} — {x.condition_type} {x.temperature_c} °C{x.rh_pct != null ? ` / ${x.rh_pct} %RH` : ""}</li>)}</ul>
      <b className="small">Time points (months)</b><div className="small mb-2">{d.timepoints.map((x: any) => x.month).join(", ") || "—"}</div>
      {d.status === "DRAFT" && can("stability.protocol.update") && <><div className="row g-1 mb-1"><div className="col-4"><input className="form-control form-control-sm" placeholder="Label e.g. 25C/60%RH" onChange={(e) => setC({ ...c, label: e.target.value })} /></div>
        <div className="col-3"><select className="form-select form-select-sm" onChange={(e) => setC({ ...c, condition_type: e.target.value })}>{CTYPES.map((t) => <option key={t}>{t}</option>)}</select></div>
        <div className="col-2"><input type="number" className="form-control form-control-sm" placeholder="°C" onChange={(e) => setC({ ...c, temperature_c: Number(e.target.value) })} /></div>
        <div className="col-2"><input type="number" className="form-control form-control-sm" placeholder="%RH" onChange={(e) => setC({ ...c, rh_pct: e.target.value === "" ? null : Number(e.target.value) })} /></div>
        <div className="col-1"><button className="btn btn-sm btn-outline-primary" onClick={() => add("conditions", c, reload)}>+</button></div></div>
        <div className="row g-1"><div className="col-4"><input type="number" className="form-control form-control-sm" placeholder="Month" onChange={(e) => setM({ month: Number(e.target.value) })} /></div><div className="col-1"><button className="btn btn-sm btn-outline-primary" onClick={() => add("timepoints", m, reload)}>+</button></div></div></>}</div>)}
    actions={[
      { label: "Submit for review", path: "submit", perm: "stability.protocol.update", show: (d) => d.status === "DRAFT" },
      { label: "Approve (e-signature)", path: "approve", perm: "stability.protocol.approve", show: (d) => d.status === "UNDER_REVIEW", sign: true, cls: "btn-success" },
      { label: "New version", path: "new-version", perm: "stability.protocol.create", show: (d) => d.status === "APPROVED", reason: true }]} />;
}

export function StabilityStudies() {
  const protos = useLookup("/stability/protocols?status=APPROVED", "title", "id", "protocol_no"); const lots = useLookup("/lots", "lot_no", "id"); const locs = useLookup("/locations", "location_code", "id");
  return <Page group="Stability" title="Stability studies" crumb="Studies" path="/stability/studies" createPerm="stability.study.create"
    filters={[{ key: "status", label: "Status", options: ["PLANNED", "ACTIVE", "COMPLETED", "CONCLUDED", "TERMINATED"] }]}
    cols={[{ key: "study_no", label: "Study" }, { key: "protocol_no", label: "Protocol" }, { key: "lot_no", label: "Lot" }, { key: "start_date", label: "Start" }, { key: "shelf_life_months", label: "Shelf life (m)" }, { key: "status", label: "Status", badge: true }]}
    create={(close: any, created: any) => <CreateDialog title="New stability study" path="/stability/studies" onClose={close} onCreated={created}
      fields={[{ key: "protocol_id", label: "Approved protocol", choices: protos }, { key: "material_batch_id", label: "Lot", choices: lots }, { key: "start_date", label: "Start date", type: "date" }, { key: "units_per_pull", label: "Quantity per pull (lot unit)", type: "number" }, { key: "source_location_id", label: "Take stock from", choices: locs }]} />}
    detail={(id: number, close: any) => <StudyDetail id={id} onClose={close} />} />;
}

function StudyDetail({ id, onClose }: { id: number; onClose: () => void }) {
  const { can } = useAuth(); const [err, setErr] = useState(""); const [pull, setPull] = useState<any>(null); const [ev, setEv] = useState<any[] | null>(null); const [rv, setRv] = useState<{ p: any } | null>(null); const [key, setKey] = useState(0);
  const act = async (p: any, path: string, body: any = {}) => { try { await api(`/stability/pulls/${p.id}/${path}`, { method: "POST", body: { reason: "Stability update", ...body } }); setErr(""); setKey(key + 1); } catch (e) { setErr(errText(e)); } };
  return (<>
    <RecordDialog key={key} base="/stability/studies" id={id} onClose={onClose} title={(d) => `${d.study_no} — ${d.lot_no}`}
      fields={[["Protocol", (d) => `${d.protocol_no} v${d.protocol_version}`], ["Start", (d) => d.start_date], ["Placed quantity", (d) => d.placed_qty], ["Shelf life", (d) => d.shelf_life_months && `${d.shelf_life_months} months`], ["Conclusion", (d) => d.conclusion]]}
      extra={(d) => (<div className="mb-2"><Alert>{err}</Alert>
        {d.pulls && <table className="table table-sm small"><thead><tr><th>Month</th><th>Condition</th><th>Due</th><th>Status</th><th>Results</th><th /></tr></thead><tbody>{d.pulls.map((p: any) => <tr key={p.id}><td>{p.month}</td><td>{p.condition}</td><td>{p.due_date}</td><td>{p.status}</td>
          <td>{p.results.map((r: any) => <span key={r.id} className={"badge me-1 text-bg-" + (r.pass_fail === "PASS" ? "success" : "danger")}>{r.rounded_value ?? r.value_text}</span>)}</td>
          <td className="text-nowrap">{p.status === "SCHEDULED" && can("stability.pull.record") && <button className="btn btn-sm btn-outline-primary" onClick={() => act(p, "pull", { remarks: new Date().toISOString().slice(0, 10) <= p.due_date ? undefined : "Late pull" })}>Pull</button>}
            {p.status === "PULLED" && can("stability.result.enter") && <button className="btn btn-sm btn-outline-primary" onClick={() => setPull(p)}>Enter results</button>}
            {p.status === "PULLED" && can("stability.result.enter") && <button className="btn btn-sm btn-outline-secondary ms-1" onClick={() => act(p, "complete-testing")}>Testing done</button>}
            {p.status === "TESTED" && can("stability.pull.review") && <button className="btn btn-sm btn-success" onClick={() => setRv({ p })}>Review</button>}</td></tr>)}</tbody></table>}
        {ev && <div className="small">{ev.map((e, i) => <div key={i}><b>{e.condition} · {e.test_name}</b>: {e.status === "OK" ? `slope ${e.slope_per_month.toFixed(3)}/month, supported shelf life ≈ ${e.supported_shelf_life_months} months (n=${e.n})` : e.note}</div>)}{!ev.length && "No numeric parameters."}</div>}</div>)}
      actions={[
        { label: "Start study (book stock)", path: "start", perm: "stability.study.start", show: (d) => d.status === "PLANNED", reason: true },
        { label: "Mark completed", path: "complete", perm: "stability.study.update", show: (d) => d.status === "ACTIVE", reason: true },
        { label: "Terminate", path: "terminate", perm: "stability.study.terminate", show: (d) => ["PLANNED", "ACTIVE"].includes(d.status), reason: true, cls: "btn-outline-danger" },
        { label: "Conclude (e-signature)", path: "conclude", perm: "stability.study.conclude", show: (d) => d.status === "COMPLETED", sign: true, cls: "btn-success", body: () => ({ shelf_life_months: Number(prompt("Assigned shelf life (months)") || 0), conclusion: prompt("Conclusion text") || "" }) }]} />
    {pull && <ResultsDialog pull={pull} onClose={() => { setPull(null); setKey(key + 1); }} />}
    {rv && <ReasonDialog title="Review pull results" needPassword onClose={() => setRv(null)} onSubmit={async (reason, password) => { try { await api(`/stability/pulls/${rv.p.id}/review`, { method: "POST", body: { reason, password } }); setKey(key + 1); } catch (e) { throw new Error(errText(e)); } }} />}
    <div className="position-fixed bottom-0 end-0 p-3" style={{ zIndex: 2000 }}><button className="btn btn-sm btn-outline-light" onClick={() => api(`/stability/studies/${id}/evaluation`).then(setEv).catch((e) => setErr(errText(e)))}>Trend evaluation</button></div>
  </>);
}

function ResultsDialog({ pull, onClose }: { pull: any; onClose: () => void }) {
  const [err, setErr] = useState(""); const [params, setParams] = useState<any[]>([]); const [v, setV] = useState<any>({});
  useEffect(() => { api(`/stability/pulls/${pull.id}`).then(() => {}); api(`/stability/studies/${pull.study_id}`).then((s) => api(`/stability/protocols/${s.protocol_id}`)).then((pr) => api(`/specifications/${pr.specification_id}`)).then((sp) => setParams(sp.parameters || [])).catch((e) => setErr(errText(e))); }, []);
  const save = async () => {
    const results = params.filter((p) => v[p.id] !== undefined && v[p.id] !== "").map((p) => (["NUMERIC", "RANGE"].includes(p.spec_type) ? { parameter_id: p.id, value: Number(v[p.id]) } : { parameter_id: p.id, conforms: v[p.id] === "conforms" }));
    try { await api(`/stability/pulls/${pull.id}/results`, { method: "POST", body: { results, reason: "Stability results entered" } }); onClose(); } catch (e) { setErr(errText(e)); }
  };
  return (<Modal title={`Results — month ${pull.month}, ${pull.condition}`} onClose={onClose} footer={<button className="btn btn-primary" onClick={save}>Save results</button>}><Alert>{err}</Alert>
    {params.map((p) => <div className="mb-2" key={p.id}><label className="form-label small mb-0">{p.test_name} {p.lsl != null || p.usl != null ? `(${p.lsl ?? ""}–${p.usl ?? ""} ${p.unit ?? ""})` : ""}</label>
      {["NUMERIC", "RANGE"].includes(p.spec_type) ? <input type="number" step="any" className="form-control" onChange={(e) => setV({ ...v, [p.id]: e.target.value })} /> : <select className="form-select" onChange={(e) => setV({ ...v, [p.id]: e.target.value })}><option value="">…</option><option value="conforms">Conforms</option><option value="fails">Does not conform</option></select>}</div>)}</Modal>);
}

export function StabilityDue() {
  const [rows, setRows] = useState<any[]>([]); const [err, setErr] = useState("");
  useEffect(() => { api("/stability/pulls/due?horizon_days=30").then(setRows).catch((e) => setErr(errText(e))); }, []);
  return (<><PageHeader title="Stability pulls due" crumbs={["Stability", "Due pulls"]} /><Alert>{err}</Alert>
    <table className="table table-sm"><thead><tr><th>Study</th><th>Condition</th><th>Month</th><th>Due</th><th>Window closes</th></tr></thead><tbody>{rows.map((r) => <tr key={r.pull_id} className={r.overdue ? "table-danger" : ""}><td>{r.study_no}</td><td>{r.condition}</td><td>{r.month}</td><td>{r.due_date}{r.overdue ? " (overdue)" : ""}</td><td>{r.missed_if_after}</td></tr>)}{!rows.length && <tr><td colSpan={5} className="text-muted">No pulls due within 30 days.</td></tr>}</tbody></table></>);
}
