import { useEffect, useState } from "react";
import { DataList, FormModal, useLookup } from "../components/DataList";
import { Alert, Modal, PageHeader, ReasonDialog, StatusBadge, fmt } from "../components/ui";
import { useAuth } from "../hooks/useAuth";
import { api, errText } from "../services/api";

/* ------------------------------------------------------------------ Samples & tests */
export function Samples() {
  const { can } = useAuth();
  const lots = useLookup("/lots?disposition=QUARANTINE", "lot_no", "id");
  const [sel, setSel] = useState<number | null>(null); const [reload, setReload] = useState<() => void>(() => () => {}); const [creating, setCreating] = useState(false);
  return (<>
    <DataList title="Samples & QC testing" crumbs={["QC", "Samples"]} path="/samples" filters={[{ key: "status", label: "Status", options: ["CREATED", "TESTING", "COMPLETED", "RETAINED", "DISPOSED"] }]}
      extraActions={can("qc.sample.create") && <button className="btn btn-primary" onClick={() => setCreating(true)}><i className="bi bi-plus-lg" /> New sample</button>}
      cols={[{ key: "sample_no", label: "Sample" }, { key: "lot_no", label: "Lot" }, { key: "material_name", label: "Material" }, { key: "quantity_sampled", label: "Qty" }, { key: "containers_sampled", label: "Containers" }, { key: "sampled_at", label: "Sampled", date: true }, { key: "status", label: "Status", badge: true }]}
      onRow={(r, load) => { setSel(r.id); setReload(() => load); }} />
    {creating && <FormModal title="New sample" initial={{}} fields={[{ key: "material_batch_id", label: "Lot", type: "select", options: lots, required: true }, { key: "quantity_sampled", label: "Quantity sampled", type: "number", required: true },
      { key: "containers_sampled", label: "Containers sampled", type: "number", required: true, help: "Plan: √N+1 containers (see lot sampling requirements)" }, { key: "sampling_location_id", label: "Sampling location id", type: "number", required: true }, { key: "remarks", label: "Remarks" }]}
      onClose={() => setCreating(false)} onSave={async (b) => { const r = await api("/samples", { method: "POST", body: b }); setCreating(false); setSel(r.id); }} />}
    {sel && <SampleDetail id={sel} onClose={() => { setSel(null); reload(); }} />}
  </>);
}

function SampleDetail({ id, onClose }: { id: number; onClose: () => void }) {
  const { can } = useAuth();
  const [d, setD] = useState<any>(null); const [err, setErr] = useState(""); const [res, setRes] = useState<any>(null); const [eq, setEq] = useState<any>({});
  const load = () => api(`/samples/${id}`).then(setD).catch((e) => setErr(errText(e)));
  useEffect(() => { load(); }, []);
  if (!d) return <Modal title="Sample" onClose={onClose}><Alert>{err}</Alert>Loading…</Modal>;
  const assign = async () => { try { await api(`/samples/${id}/assign`, { method: "POST", body: { reason: "Tests assigned" } }); load(); } catch (e) { setErr(errText(e)); } };
  const start = async (t: any) => { try { await api(`/qc/tests/${t.id}/start`, { method: "POST", body: { equipment_id: eq[t.id] ? Number(eq[t.id]) : null } }); setErr(""); load(); } catch (e) { setErr(errText(e)); } };
  return (<Modal title={`${d.sample_no} — ${d.material_name ?? ""}`} onClose={onClose}>
    <Alert>{err}</Alert>
    <div className="mb-2"><StatusBadge status={d.status} /> lot {d.lot_no} · {d.quantity_sampled} sampled from {d.containers_sampled} container(s)</div>
    {d.tests.length === 0 && can("qc.test.assign") && <button className="btn btn-sm btn-primary mb-2" onClick={assign}>Assign tests from specification</button>}
    <table className="table table-sm small"><thead><tr><th>Test</th><th>Analyst</th><th>Status</th><th>Result</th><th /></tr></thead><tbody>{d.tests.map((t: any) => (<tr key={t.id}>
      <td>{t.test_name}</td><td>{t.analyst ?? "—"}</td><td><StatusBadge status={t.status} /></td>
      <td>{t.result ? <>{t.result.effective.value} {t.result.unit} <span className={`badge text-bg-${t.result.effective.pass_fail === "PASS" ? "success" : "danger"}`}>{t.result.effective.pass_fail}</span> {t.result.effective.amended && <span className="badge text-bg-warning">amended</span>}</> : "—"}</td>
      <td className="text-nowrap">{["ASSIGNED", "STARTED"].includes(t.status) && can("qc.test.enter") && <>
        <input className="form-control form-control-sm d-inline-block me-1" style={{ width: 90 }} placeholder="Equip. id" onChange={(e) => setEq({ ...eq, [t.id]: e.target.value })} />
        {t.status === "ASSIGNED" && <button className="btn btn-sm btn-outline-secondary me-1" onClick={() => start(t)}>Start</button>}
        <button className="btn btn-sm btn-primary" onClick={() => setRes(t)}>Enter result</button></>}</td></tr>))}</tbody></table>
    {can("label.lot.print") && <button className="btn btn-sm btn-outline-secondary" onClick={async () => { const r: any = await api(`/samples/${id}/label`, { method: "POST", raw: true }); window.open(URL.createObjectURL(await r.blob()), "_blank"); }}><i className="bi bi-printer" /> Sample label</button>}
    {res && <FormModal title={`Result: ${res.test_name}`} initial={{}} fields={[{ key: "value", label: "Numeric result", type: "number" }, { key: "conforms", label: "Conforms (text / pass-fail tests)", type: "bool" }, { key: "remarks", label: "Remarks" }]}
      onClose={() => setRes(null)} onSave={async (b) => { await api(`/qc/tests/${res.id}/result`, { method: "POST", body: b }); setRes(null); load(); }} />}
  </Modal>);
}

/* ------------------------------------------------------------------ Release queue */
export function ReleaseQueue() {
  const { can } = useAuth(); const [sel, setSel] = useState<number | null>(null); const [reload, setReload] = useState<() => void>(() => () => {});
  return (<>
    <DataList title="Material & product release" crumbs={["QA", "Release"]} path="/lots" filters={[{ key: "disposition", label: "Disposition", options: ["QUARANTINE", "QC_TESTING", "QC_APPROVED", "QA_REVIEW", "APPROVED", "REJECTED"] }]}
      cols={[{ key: "lot_no", label: "Lot" }, { key: "material_name", label: "Material" }, { key: "vendor_batch_no", label: "Vendor batch" }, { key: "qc_no", label: "QC no." }, { key: "qa_release_no", label: "QA release" }, { key: "status", label: "Status", badge: true }]}
      onRow={(r, load) => { setSel(r.id); setReload(() => load); }} />
    {sel && <ReleaseDetail id={sel} onClose={() => { setSel(null); reload(); }} />}
  </>);
}

function ReleaseDetail({ id, onClose }: { id: number; onClose: () => void }) {
  const { can } = useAuth();
  const [r, setR] = useState<any>(null); const [coas, setCoas] = useState<any[]>([]); const [err, setErr] = useState(""); const [act, setAct] = useState<string | null>(null);
  const load = () => { api(`/lots/${id}/release`).then(setR).catch((e) => setErr(errText(e))); api(`/lots/${id}/coa`).then(setCoas).catch(() => {}); };
  useEffect(load, []);
  if (!r) return <Modal title="Release" onClose={onClose}><Alert>{err}</Alert>Loading…</Modal>;
  const wf = r.workflow; const cur = wf?.steps.find((s: any) => s.seq === wf.current_seq);
  const submit = async () => { try { await api(`/lots/${id}/submit-release`, { method: "POST" }); setErr(""); load(); } catch (e) { setErr(errText(e)); } };
  return (<Modal title={`Release review — lot ${id}`} onClose={onClose}>
    <Alert>{err}</Alert>
    <div className="mb-2">Disposition <StatusBadge status={r.disposition} /> {r.qc_no && <span className="ms-2">QC {r.qc_no}</span>} {r.qa_release_no && <span className="ms-2">QA release {r.qa_release_no}</span>}</div>
    {r.readiness.length > 0 && <Alert kind="warning"><b>Not ready for release:</b><ul className="mb-0">{r.readiness.map((x: string) => <li key={x}>{x}</li>)}</ul></Alert>}
    {wf && <div className="mb-2"><div className="d-flex gap-2 flex-wrap small">{wf.steps.map((s: any) => <span key={s.seq} className={"badge " + (wf.status === "APPROVED" || s.seq < wf.current_seq ? "text-bg-success" : s.seq === wf.current_seq && wf.status === "IN_PROGRESS" ? "text-bg-warning" : "text-bg-secondary")}>{s.seq}. {s.name} ({s.role}) ✍</span>)}</div>
      <ul className="small mt-1">{wf.history.map((h: any, i: number) => <li key={i}>{h.decision} — {h.by} {h.signed && "(e-signed)"} · {fmt(h.at)} {h.comment && `· ${h.comment}`}</li>)}</ul></div>}
    <div className="d-flex gap-2 flex-wrap">
      {r.disposition === "QC_TESTING" && !wf?.status?.startsWith("IN_") && can("qc.release.submit") && <button className="btn btn-sm btn-primary" onClick={submit}>Submit for release review</button>}
      {wf?.status === "IN_PROGRESS" && can("qc.release.approve") && <><button className="btn btn-sm btn-success" onClick={() => setAct("APPROVE")}><i className="bi bi-pen" /> Approve step: {cur?.name}</button><button className="btn btn-sm btn-outline-danger" onClick={() => setAct("REJECT")}>Reject</button></>}</div>
    {coas.length > 0 && <div className="mt-3"><h6>Certificates of analysis</h6>{coas.map((c) => <div key={c.id} className="small">{c.coa_no} v{c.version_no} — {c.conclusion} · <a href={`/api/v1/coa/${c.id}/pdf`}>PDF</a> · <a href={`/api/v1/coa/${c.id}/xlsx`}>Excel</a></div>)}</div>}
    {act && <ReasonDialog title={`${act === "APPROVE" ? "Approve" : "Reject"} — ${cur?.name}`} needPassword meaning={cur?.name} onClose={() => setAct(null)} onSubmit={async (comment, password) => { try { await api(`/lots/${id}/release-decision`, { method: "POST", body: { decision: act, comment, password } }); load(); } catch (e) { throw new Error(errText(e)); } }} />}
  </Modal>);
}

/* ------------------------------------------------------------------ OOS / OOT / conditional release */
export function OOSPage() {
  const { can } = useAuth(); const [sel, setSel] = useState<any>(null); const [reload, setReload] = useState<() => void>(() => () => {}); const [act, setAct] = useState<string | null>(null); const [err, setErr] = useState("");
  return (<>
    <DataList title="OOS investigations" crumbs={["Quality", "OOS"]} path="/oos" filters={[{ key: "status", label: "Status", options: ["RAISED", "PHASE1", "PHASE2", "DECIDED", "CLOSED"] }]}
      cols={[{ key: "oos_no", label: "OOS" }, { key: "description", label: "Description" }, { key: "decision", label: "Decision" }, { key: "status", label: "Status", badge: true }]} onRow={(r, load) => { setSel(r); setReload(() => load); }} />
    {sel && <Modal title={`${sel.oos_no} — ${sel.status}`} onClose={() => { setSel(null); reload(); }}>
      <Alert>{err}</Alert><p>{sel.description}</p><dl className="row small"><dt className="col-4">Phase I</dt><dd className="col-8">{sel.phase1_findings ?? "—"}</dd><dt className="col-4">Phase II</dt><dd className="col-8">{sel.phase2_findings ?? "—"}</dd><dt className="col-4">Root cause</dt><dd className="col-8">{sel.root_cause ?? "—"}</dd></dl>
      <div className="d-flex gap-2">{sel.status !== "CLOSED" && can("oos.investigation.update") && <button className="btn btn-sm btn-outline-primary" onClick={() => setAct("investigate")}>Record findings</button>}
        {["PHASE1", "PHASE2"].includes(sel.status) && can("oos.investigation.decide") && <button className="btn btn-sm btn-success" onClick={() => setAct("decide")}><i className="bi bi-pen" /> QA decision</button>}</div>
      {act === "investigate" && <FormModal title="Investigation findings" initial={{ phase: sel.status === "PHASE1" ? "PHASE2" : "PHASE1" }} fields={[{ key: "phase", label: "Phase", type: "select", options: [{ value: "PHASE1", label: "Phase I (laboratory)" }, { value: "PHASE2", label: "Phase II (full)" }] }, { key: "findings", label: "Findings", type: "textarea", required: true }]} onClose={() => setAct(null)} onSave={async (b) => { setSel(await api(`/oos/${sel.id}/investigate`, { method: "POST", body: b })); setAct(null); }} />}
      {act === "decide" && <ReasonDialog title="QA decision (e-signature)" needPassword meaning="QA_APPROVED" onClose={() => setAct(null)} onSubmit={async (reason, password) => { const decision = prompt("CONFIRMED_FAIL or INVALIDATED?", "INVALIDATED"); const root = prompt("Root cause"); if (!decision || !root) throw new Error("Decision and root cause required"); try { setSel(await api(`/oos/${sel.id}/decide`, { method: "POST", body: { decision, root_cause: root, password, reason } })); } catch (e) { throw new Error(errText(e)); } }} />}
    </Modal>}
  </>);
}

export function ConditionalReleases() {
  const { can } = useAuth(); const lots = useLookup("/lots", "lot_no", "id"); const [sign, setSign] = useState<any>(null);
  return (<><DataList title="QA-authorised conditional release" crumbs={["QA", "Conditional release"]} path="/conditional-releases" canCreate={can("conditional_release.request.create")}
    fields={[{ key: "material_batch_id", label: "Lot", type: "select", options: lots, required: true }, { key: "quantity_authorised", label: "Quantity", type: "number", required: true }, { key: "intended_batch_ref", label: "Intended production batch", required: true },
      { key: "justification", label: "Justification", type: "textarea", required: true }, { key: "risk_assessment_ref", label: "Risk assessment ref.", required: true }, { key: "identity_confirmed", label: "Material identity confirmed", type: "bool" }, { key: "expires_at", label: "Authorisation expires", type: "date", required: true }]}
    cols={[{ key: "cr_no", label: "No." }, { key: "material_batch_id", label: "Lot id" }, { key: "quantity_authorised", label: "Qty" }, { key: "quantity_used", label: "Used" }, { key: "intended_batch_ref", label: "Batch" }, { key: "expires_at", label: "Expires" }, { key: "status", label: "Status", badge: true }]}
    onRow={(r) => r.status === "REQUESTED" && can("conditional_release.request.approve") && setSign(r)} />
    {sign && <ReasonDialog title={`Approve ${sign.cr_no} (e-signature)`} needPassword meaning="QA_APPROVED" onClose={() => setSign(null)} onSubmit={async (reason, password) => { try { await api(`/conditional-releases/${sign.id}/decision`, { method: "POST", body: { approve: true, password, reason } }); } catch (e) { throw new Error(errText(e)); } }} />}</>);
}

/* ------------------------------------------------------------------ Trends */
export function Trends() {
  const mats = useLookup("/materials", "name", "id", "material_code");
  const [m, setM] = useState(""); const [test, setTest] = useState("Assay"); const [group, setGroup] = useState("batch"); const [d, setD] = useState<any>(null); const [err, setErr] = useState("");
  const run = async () => { try { setErr(""); setD(await api(`/qc/trends?material_id=${m}&test_name=${encodeURIComponent(test)}&group=${group}`)); } catch (e) { setErr(errText(e)); } };
  const pts = d?.points ?? []; const vals = pts.map((p: any) => p.value);
  const lo = Math.min(...vals, d?.lsl ?? Infinity, d?.control_limits?.lcl ?? Infinity), hi = Math.max(...vals, d?.usl ?? -Infinity, d?.control_limits?.ucl ?? -Infinity);
  const W = 760, H = 280, pad = 40; const x = (i: number) => pad + (pts.length > 1 ? (i / (pts.length - 1)) * (W - 2 * pad) : 0); const y = (v: number) => H - pad - ((v - lo) / (hi - lo || 1)) * (H - 2 * pad);
  const line = (v: number | null | undefined, color: string, dash = "") => v != null && isFinite(v) ? <g><line x1={pad} x2={W - pad} y1={y(v)} y2={y(v)} stroke={color} strokeDasharray={dash} /><text x={W - pad + 2} y={y(v) + 3} fontSize="9" fill={color}>{v.toFixed(2)}</text></g> : null;
  const viol = new Set((d?.nelson_violations ?? []).map((v: any) => v.index));
  return (<>
    <PageHeader title="QC trends & process capability" crumbs={["QC", "Trends"]} />
    <Alert>{err}</Alert>
    <div className="row g-2 mb-3"><div className="col-md-4"><select className="form-select" value={m} onChange={(e) => setM(e.target.value)}><option value="">Material…</option>{mats.map((x) => <option key={x.value} value={x.value}>{x.label}</option>)}</select></div>
      <div className="col-md-3"><input className="form-control" value={test} onChange={(e) => setTest(e.target.value)} placeholder="Test name" /></div>
      <div className="col-md-2"><select className="form-select" value={group} onChange={(e) => setGroup(e.target.value)}>{["batch", "month", "year", "vendor"].map((g) => <option key={g}>{g}</option>)}</select></div><div className="col-md-2"><button className="btn btn-primary" disabled={!m} onClick={run}>Analyse</button></div></div>
    {d && <>
      <div className="row g-2 mb-3">{[["n", d.descriptive.n], ["Mean", d.descriptive.mean?.toFixed(3)], ["SD", d.descriptive.sd?.toFixed(3)], ["CV %", d.descriptive.cv_pct?.toFixed(2)], ["Cpk", d.capability.cpk?.toFixed(2) ?? d.capability.status], ["Ppk", d.capability.ppk?.toFixed(2) ?? d.capability.status]].map(([k, v]) => <div className="col-4 col-md-2" key={k as string}><div className="card"><div className="card-body py-2"><div className="small text-muted">{k}</div><div className="fw-bold">{v ?? "—"}</div></div></div></div>)}</div>
      {d.capability.notes?.map((n: string) => <Alert key={n} kind="warning">{n}</Alert>)}
      <svg width={W} height={H} className="bg-white border rounded">
        {line(d.usl, "#b91c1c")}{line(d.lsl, "#b91c1c")}{line(d.control_limits?.ucl, "#d97706", "4 3")}{line(d.control_limits?.lcl, "#d97706", "4 3")}{line(d.control_limits?.cl, "#15803d", "2 2")}
        <polyline fill="none" stroke="#1d4ed8" strokeWidth="1.5" points={pts.map((p: any, i: number) => `${x(i)},${y(p.value)}`).join(" ")} />
        {pts.map((p: any, i: number) => <circle key={i} cx={x(i)} cy={y(p.value)} r={viol.has(i) ? 5 : 3} fill={viol.has(i) ? "#b91c1c" : p.pass_fail === "FAIL" ? "#b91c1c" : "#1d4ed8"}><title>{p.lot_no}: {p.value}</title></circle>)}
      </svg>
      <div className="small text-muted mt-1">Red = specification limits · orange = control limits (X̄ ± 2.66·MR̄) · green = mean · red points = Nelson rule violation. Alerts do not change lot status.</div>
      {d.nelson_violations.length > 0 && <ul className="small mt-2">{d.nelson_violations.map((v: any, i: number) => <li key={i}>Point {v.index + 1}: rule {v.rule} — {v.text}</li>)}</ul>}
      {d.groups && <table className="table table-sm bg-white mt-2" style={{ maxWidth: 520 }}><thead><tr><th>Group</th><th>n</th><th>Mean</th><th>SD</th></tr></thead><tbody>{d.groups.map((g: any) => <tr key={g.key}><td>{g.key}</td><td>{g.n}</td><td>{g.mean?.toFixed(3)}</td><td>{g.sd?.toFixed(3) ?? "—"}</td></tr>)}</tbody></table>}</>}
  </>);
}
