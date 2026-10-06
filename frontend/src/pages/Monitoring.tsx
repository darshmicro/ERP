import { useEffect, useState } from "react";
import { useLookup } from "../components/DataList";
import { Alert, PageHeader } from "../components/ui";
import { useAuth } from "../hooks/useAuth";
import { api, errText } from "../services/api";
import { CreateDialog, Page, RecordDialog } from "./Quality";

const GRADES = ["A", "B", "C", "D", "NC"];
const TYPES = ["VIABLE_AIR", "SETTLE_PLATE", "CONTACT_PLATE", "GLOVE_PRINT", "NONVIABLE_05", "NONVIABLE_5", "DIFF_PRESSURE", "TEMPERATURE", "HUMIDITY"];
const STATES = ["AT_REST", "OPERATIONAL"];
const OUTCOME = (r: any) => (r.outcome ? <span className={"badge text-bg-" + ({ WITHIN: "success", ALERT: "warning", ACTION: "danger" } as any)[r.outcome]}>{r.outcome}</span> : "");

/* ------------------------------------------------------------------ EM samples / results */
export function EMSamples() {
  const locs = useLookup("/em/locations?active=true", "name", "id", "code");
  return <Page group="Environmental monitoring" title="EM samples & results" crumb="Samples" path="/em/samples" createPerm="em.sample.create"
    filters={[{ key: "status", label: "Status", options: ["SAMPLED", "RESULT_ENTERED", "REVIEWED", "CANCELLED"] }, { key: "outcome", label: "Outcome", options: ["WITHIN", "ALERT", "ACTION"] }, { key: "grade", label: "Grade", options: GRADES }]}
    cols={[{ key: "sample_no", label: "Sample" }, { key: "location_code", label: "Location" }, { key: "grade", label: "Grade" }, { key: "sample_type", label: "Type" }, { key: "state", label: "State" }, { key: "result_value", label: "Result" }, { key: "result_unit", label: "Unit" }, { key: "outcome", label: "Outcome", render: OUTCOME }, { key: "status", label: "Status", badge: true }]}
    create={(close: any, created: any) => <CreateDialog title="Record EM sampling" path="/em/samples" onClose={close} onCreated={created}
      fields={[{ key: "em_location_id", label: "Location", choices: locs }, { key: "sample_type", label: "Sample type", options: TYPES }, { key: "state", label: "State", options: STATES }, { key: "sample_point", label: "Sample point" }, { key: "remarks", label: "Remarks" }]} transform={(b) => ({ state: "OPERATIONAL", ...b })} />}
    detail={(id: number, close: any) => <EMSampleDetail id={id} onClose={close} />} />;
}

function EMSampleDetail({ id, onClose }: { id: number; onClose: () => void }) {
  const { can } = useAuth(); const [err, setErr] = useState(""); const [v, setV] = useState<any>({}); const [iso, setIso] = useState("");
  const post = async (path: string, body: any, reload: () => void) => { try { await api(`/em/samples/${id}/${path}`, { method: "POST", body }); setErr(""); reload(); } catch (e) { setErr(errText(e)); } };
  return <RecordDialog base="/em/samples" id={id} onClose={onClose} title={(d) => `${d.sample_no} — ${d.location_code} ${d.sample_type}`}
    fields={[["Location", (d) => `${d.location_code} ${d.location_name} (grade ${d.grade})`], ["Result", (d) => (d.result_value == null ? null : `${d.result_value} ${d.result_unit ?? ""}`)], ["Outcome", (d) => d.outcome], ["Alert / action limit", (d) => `${d.alert_high ?? "—"} / ${d.action_high ?? "—"}`],
      ["Deviation id", (d) => d.deviation_id], ["Organisms", (d) => (d.isolates || []).map((i: any) => `${i.organism} (${i.cfu_count})`).join(", ")], ["Amendments", (d) => (d.amendments || []).map((a: any) => `${a.old_value}→${a.new_value}: ${a.reason}`).join("; ")]]}
    extra={(d, reload) => (<div className="mb-2"><Alert>{err}</Alert>
      {d.status === "SAMPLED" && can("em.sample.enter") && <div className="row g-1"><div className="col-4"><input type="number" step="any" className="form-control form-control-sm" placeholder="Result" onChange={(e) => setV({ ...v, value: Number(e.target.value) })} /></div>
        <div className="col-5"><input className="form-control form-control-sm" placeholder="Organism (optional)" onChange={(e) => setIso(e.target.value)} /></div>
        <div className="col-3"><button className="btn btn-sm btn-primary w-100" onClick={() => post("result", { value: v.value, reason: "Result entered", isolates: iso ? [{ organism: iso }] : [] }, reload)}>Enter result</button></div></div>}
      {d.status === "RESULT_ENTERED" && can("em.sample.enter") && <div className="row g-1"><div className="col-3"><input type="number" step="any" className="form-control form-control-sm" placeholder="Corrected" onChange={(e) => setV({ ...v, value: Number(e.target.value) })} /></div>
        <div className="col-6"><input className="form-control form-control-sm" placeholder="Reason for amendment" onChange={(e) => setV({ ...v, why: e.target.value })} /></div>
        <div className="col-3"><button className="btn btn-sm btn-outline-secondary w-100" onClick={() => post("amend", { value: v.value, reason: v.why }, reload)}>Amend</button></div></div>}</div>)}
    actions={[
      { label: "QA review (e-signature)", path: "review", perm: "em.sample.review", show: (d) => d.status === "RESULT_ENTERED", sign: true, cls: "btn-success" },
      { label: "Cancel sample", path: "cancel", perm: "em.sample.enter", show: (d) => d.status === "SAMPLED", reason: true, cls: "btn-outline-danger" }]} />;
}

/* ------------------------------------------------------------------ setup */
export function EMLocations() {
  return <Page group="Environmental monitoring" title="Monitoring locations" crumb="Locations" path="/em/locations" createPerm="em.location.create"
    cols={[{ key: "code", label: "Code" }, { key: "name", label: "Name" }, { key: "grade", label: "Grade" }, { key: "is_active", label: "Active", render: (r: any) => (r.is_active ? "yes" : "no") }]}
    create={(close: any, created: any) => <CreateDialog title="New monitoring location" path="/em/locations" onClose={close} onCreated={created}
      fields={[{ key: "code", label: "Code (blank = auto)" }, { key: "name", label: "Name" }, { key: "grade", label: "Cleanroom grade", options: GRADES }, { key: "description", label: "Description" }]} />}
    detail={(id: number, close: any) => <RecordDialog base="/em/locations" id={id} onClose={close} title={(d) => `${d.code} — ${d.name}`} fields={[["Grade", (d) => d.grade], ["Description", (d) => d.description]]} actions={[]} />} />;
}

export function EMLimitSets() {
  return <Page group="Environmental monitoring" title="Alert / action limit sets" crumb="Limits" path="/em/limit-sets" createPerm="em.limit.create"
    filters={[{ key: "status", label: "Status", options: ["DRAFT", "UNDER_REVIEW", "APPROVED", "SUPERSEDED"] }]}
    cols={[{ key: "limitset_no", label: "Limit set" }, { key: "version_no", label: "Ver" }, { key: "title", label: "Title" }, { key: "status", label: "Status", badge: true }]}
    create={(close: any, created: any) => <LimitSetCreate close={close} created={created} />}
    detail={(id: number, close: any) => <LimitSetDetail id={id} onClose={close} />} />;
}

function LimitSetCreate({ close, created }: { close: () => void; created: (id: number) => void }) {
  const [err, setErr] = useState("");
  return (<><Alert>{err}</Alert><CreateDialog title="New limit set (empty draft)" path="/em/limit-sets" onClose={close} onCreated={created} fields={[{ key: "title", label: "Title" }, { key: "basis", label: "Basis / reference" }]} />
    <div className="position-fixed bottom-0 end-0 p-3" style={{ zIndex: 2000 }}><button className="btn btn-sm btn-outline-light" onClick={async () => { try { const r = await api("/em/limit-sets/load-reference", { method: "POST", body: { reason: "Reference limits loaded" } }); created(r.id); } catch (e) { setErr(errText(e)); } }}>Load Annex 1 reference limits instead</button></div></>);
}

function LimitSetDetail({ id, onClose }: { id: number; onClose: () => void }) {
  const { can } = useAuth(); const [err, setErr] = useState(""); const [l, setL] = useState<any>({ state: "OPERATIONAL" });
  return <RecordDialog base="/em/limit-sets" id={id} onClose={onClose} title={(d) => `${d.limitset_no} v${d.version_no} — ${d.title}`}
    fields={[["Basis", (d) => d.basis], ["Change reason", (d) => d.change_reason]]}
    extra={(d, reload) => (<div className="mb-2"><Alert>{err}</Alert>
      <table className="table table-sm small"><thead><tr><th>Grade</th><th>Type</th><th>State</th><th>Alert</th><th>Action</th><th>Unit</th></tr></thead><tbody>{d.limits.map((x: any) => <tr key={x.id}><td>{x.grade}</td><td>{x.sample_type}</td><td>{x.state}</td><td>{x.alert_low ?? ""}–{x.alert_high ?? ""}</td><td>{x.action_low ?? ""}–{x.action_high ?? ""}</td><td>{x.unit}</td></tr>)}</tbody></table>
      {d.status === "DRAFT" && can("em.limit.update") && <div className="row g-1">
        <div className="col-2"><select className="form-select form-select-sm" onChange={(e) => setL({ ...l, grade: e.target.value })}><option value="">Grade</option>{GRADES.map((g) => <option key={g}>{g}</option>)}</select></div>
        <div className="col-3"><select className="form-select form-select-sm" onChange={(e) => setL({ ...l, sample_type: e.target.value })}><option value="">Type</option>{TYPES.map((g) => <option key={g}>{g}</option>)}</select></div>
        <div className="col-2"><input type="number" className="form-control form-control-sm" placeholder="Alert" onChange={(e) => setL({ ...l, alert_high: e.target.value === "" ? null : Number(e.target.value) })} /></div>
        <div className="col-2"><input type="number" className="form-control form-control-sm" placeholder="Action" onChange={(e) => setL({ ...l, action_high: e.target.value === "" ? null : Number(e.target.value) })} /></div>
        <div className="col-2"><input className="form-control form-control-sm" placeholder="Unit" onChange={(e) => setL({ ...l, unit: e.target.value })} /></div>
        <div className="col-1"><button className="btn btn-sm btn-outline-primary" onClick={async () => { try { await api(`/em/limit-sets/${id}/limits`, { method: "POST", body: l }); setErr(""); reload(); } catch (e) { setErr(errText(e)); } }}>+</button></div></div>}</div>)}
    actions={[
      { label: "Submit for review", path: "submit", perm: "em.limit.update", show: (d) => d.status === "DRAFT" },
      { label: "Approve (e-signature)", path: "approve", perm: "em.limit.approve", show: (d) => d.status === "UNDER_REVIEW", sign: true, cls: "btn-success" },
      { label: "New version", path: "new-version", perm: "em.limit.create", show: (d) => d.status === "APPROVED", reason: true }]} />;
}

/* ------------------------------------------------------------------ schedule, excursions, trend */
export function EMOverview() {
  const [sched, setSched] = useState<any[]>([]); const [exc, setExc] = useState<any[]>([]); const [err, setErr] = useState(""); const [trend, setTrend] = useState<any>(null);
  useEffect(() => { api("/em/schedule?horizon_days=14").then(setSched).catch((e) => setErr(errText(e))); api("/em/excursions?days=90").then(setExc).catch(() => {}); }, []);
  const show = async (r: any) => { try { setTrend({ ...(await api(`/em/trend?em_location_id=${r.em_location_id}&sample_type=${r.sample_type}&state=${r.state}`)), title: `${r.location_code} ${r.sample_type}` }); } catch (e) { setErr(errText(e)); } };
  return (<><PageHeader title="Monitoring schedule & excursions" crumbs={["Environmental monitoring", "Overview"]} /><Alert>{err}</Alert>
    <h6>Due within 14 days</h6>
    <table className="table table-sm"><thead><tr><th>Location</th><th>Grade</th><th>Type</th><th>State</th><th>Due</th><th /></tr></thead><tbody>{sched.map((r, i) => <tr key={i} className={r.overdue ? "table-danger" : ""}><td>{r.location_code}</td><td>{r.grade}</td><td>{r.sample_type}</td><td>{r.state}</td><td>{r.due_date}{r.overdue ? " (overdue)" : ""}</td><td><button className="btn btn-sm btn-link" onClick={() => show(r)}>trend</button></td></tr>)}{!sched.length && <tr><td colSpan={6} className="text-muted">Nothing due.</td></tr>}</tbody></table>
    {trend && <div className="border rounded p-2 mb-3 small"><b>{trend.title}</b> — n={trend.n}, alerts {trend.alerts}, actions {trend.actions}{trend.signals?.length ? `, ${trend.signals.length} Nelson signal(s): ${[...new Set(trend.signals.map((s: any) => s.text))].join("; ")}` : ""}
      <div>{trend.points.map((p: any) => <span key={p.sample_no} className={"badge me-1 text-bg-" + ({ WITHIN: "success", ALERT: "warning", ACTION: "danger" } as any)[p.outcome]}>{p.value}</span>)}</div>{trend.note && <div className="text-muted">{trend.note}</div>}</div>}
    <h6>Alert / action results (90 days)</h6>
    <table className="table table-sm"><thead><tr><th>Sample</th><th>Location</th><th>Type</th><th>Result</th><th>Outcome</th><th>Deviation</th></tr></thead><tbody>{exc.map((r) => <tr key={r.id}><td>{r.sample_no}</td><td>{r.location_code}</td><td>{r.sample_type}</td><td>{r.result_value} {r.result_unit}</td><td>{OUTCOME(r)}</td><td>{r.deviation_id ?? ""}</td></tr>)}{!exc.length && <tr><td colSpan={6} className="text-muted">None.</td></tr>}</tbody></table></>);
}
