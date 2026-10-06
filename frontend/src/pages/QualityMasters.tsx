import { useEffect, useState } from "react";
import { DataList, FormModal, useLookup } from "../components/DataList";
import { Alert, Modal, ReasonDialog, StatusBadge } from "../components/ui";
import { useAuth } from "../hooks/useAuth";
import { api, errText } from "../services/api";

type Kind = "stps" | "specifications" | "sampling-plans";
const CFG: Record<Kind, { title: string; perm: string; key: string }> = {
  stps: { title: "Standard Testing Procedures", perm: "md.stp", key: "stp_no" },
  specifications: { title: "Specifications", perm: "md.spec", key: "spec_no" },
  "sampling-plans": { title: "Sampling Plans", perm: "md.sampling_plan", key: "plan_no" },
};

export default function QualityMasters() {
  const { can } = useAuth();
  const [kind, setKind] = useState<Kind>("specifications"); const [sel, setSel] = useState<number | null>(null); const [reload, setReload] = useState<() => void>(() => () => {});
  const mats = useLookup("/materials", "name", "id", "material_code");
  const c = CFG[kind];
  const fields: Record<Kind, any[]> = {
    stps: [{ key: "title", label: "Title", required: true }, { key: "test_method", label: "Test method" }, { key: "equipment_required", label: "Equipment required", type: "textarea" }, { key: "reagents_required", label: "Reagents required", type: "textarea" },
      { key: "reference_standards", label: "Reference standards", type: "textarea" }, { key: "procedure", label: "Procedure", type: "textarea" }, { key: "calculation", label: "Calculation", type: "textarea" },
      { key: "acceptance_criteria", label: "Acceptance criteria", type: "textarea" }, { key: "safety_precautions", label: "Safety precautions", type: "textarea" }],
    specifications: [{ key: "material_id", label: "Material", type: "select", options: mats, required: true }, { key: "title", label: "Title" }, { key: "pharmacopoeial_reference", label: "Pharmacopoeial reference" }],
    "sampling-plans": [{ key: "material_id", label: "Material", type: "select", options: mats, required: true },
      { key: "sampling_rule", label: "Sampling rule", type: "select", options: ["SQRT_N_PLUS_1", "FIXED", "PERCENT", "ALL"].map((x) => ({ value: x, label: x })) }, { key: "fixed_qty", label: "Fixed quantity", type: "number" },
      { key: "percent", label: "Percent", type: "number" }, { key: "container_rule", label: "Container rule" }, { key: "remarks", label: "Remarks" }],
  };
  const cols = [{ key: c.key, label: "Number" }, { key: "version_no", label: "Ver" }, ...(kind === "stps" ? [{ key: "title", label: "Title" }] : [{ key: "material_id", label: "Material", render: (r: any) => mats.find((m) => m.value === r.material_id)?.label ?? r.material_id }]),
    { key: "status", label: "Status", badge: true }, { key: "effective_from", label: "Effective", date: true }];
  return (<>
    <ul className="nav nav-tabs mb-3">{(Object.keys(CFG) as Kind[]).map((k) => (<li className="nav-item" key={k}><button className={"nav-link" + (kind === k ? " active" : "")} onClick={() => setKind(k)}>{CFG[k].title}</button></li>))}</ul>
    <DataList key={kind} title={c.title} crumbs={["Quality masters", c.title]} path={`/${kind}`} canCreate={can(`${c.perm}.create`)} fields={fields[kind]}
      filters={[{ key: "status", label: "Status", options: ["DRAFT", "UNDER_REVIEW", "APPROVED", "SUPERSEDED"] }]} cols={cols}
      onRow={(r, load) => { setSel(r.id); setReload(() => load); }} />
    {sel && <VersionDetail kind={kind} id={sel} fields={fields[kind]} onOpen={setSel} onClose={() => { setSel(null); reload(); }} />}
  </>);
}

function VersionDetail({ kind, id, fields, onClose, onOpen }: { kind: Kind; id: number; fields: any[]; onClose: () => void; onOpen: (id: number) => void }) {
  const { can } = useAuth(); const c = CFG[kind];
  const [d, setD] = useState<any>(null); const [err, setErr] = useState(""); const [act, setAct] = useState<string | null>(null); const [editing, setEditing] = useState(false); const [param, setParam] = useState<any>(null);
  const load = () => api(`/${kind}/${id}`).then(setD).catch((e) => setErr(errText(e)));
  useEffect(() => { load(); }, [id]);
  const draft = d?.status === "DRAFT";
  const call = async (path: string, body?: any) => { try { await api(`/${kind}/${id}/${path}`, { method: "POST", body }); setErr(""); load(); } catch (e) { setErr(errText(e)); } };
  if (!d) return <Modal title={c.title} onClose={onClose}><Alert>{err}</Alert>Loading…</Modal>;
  return (<Modal title={`${d[c.key]} v${d.version_no}`} onClose={onClose}>
    <Alert>{err}</Alert>
    <div className="mb-2"><StatusBadge status={d.status} /> {d.effective_from && <span className="small text-muted">effective {new Date(d.effective_from).toLocaleString()}</span>}
      {d.change_reason && <div className="small">Change reason: {d.change_reason}</div>}</div>
    <div className="small mb-2">Versions: {d.versions.map((v: any) => (<a key={v.id} href="#" className="me-2" onClick={(e) => { e.preventDefault(); onOpen(v.id); }}>v{v.version_no} <StatusBadge status={v.status} /></a>))}</div>
    <dl className="row small">{fields.map((f) => (<><dt className="col-4">{f.label}</dt><dd className="col-8" style={{ whiteSpace: "pre-wrap" }}>{String(d[f.key] ?? "—")}</dd></>))}</dl>
    {kind === "specifications" && <>
      <h6>Test parameters</h6>
      <table className="table table-sm small"><thead><tr><th>#</th><th>Test</th><th>Type</th><th>LSL</th><th>USL</th><th>Target</th><th>Unit</th><th>Crit.</th></tr></thead>
        <tbody>{d.parameters.map((p: any) => (<tr key={p.id}><td>{p.seq}</td><td>{p.test_name}{p.acceptance_criteria && <div className="text-muted">{p.acceptance_criteria}</div>}</td><td>{p.spec_type}</td><td>{p.lsl ?? ""}</td><td>{p.usl ?? ""}</td><td>{p.target ?? ""}</td><td>{p.unit ?? ""}</td><td>{p.criticality}</td></tr>))}</tbody></table>
      {draft && can("md.spec.update") && <button className="btn btn-sm btn-outline-primary mb-2" onClick={() => setParam({})}>Add parameter</button>}</>}
    <div className="d-flex gap-2 flex-wrap">
      {draft && can(`${c.perm}.update`) && <button className="btn btn-sm btn-outline-secondary" onClick={() => setEditing(true)}>Edit</button>}
      {draft && can(`${c.perm}.update`) && <button className="btn btn-sm btn-primary" onClick={() => call("submit")}>Submit for review</button>}
      {d.status === "UNDER_REVIEW" && can(`${c.perm}.approve`) && <button className="btn btn-sm btn-success" onClick={() => setAct("approve")}><i className="bi bi-pen" /> Approve (e-sign)</button>}
      {d.status === "UNDER_REVIEW" && can(`${c.perm}.update`) && <button className="btn btn-sm btn-outline-warning" onClick={() => setAct("return")}>Return to draft</button>}
      {d.status === "APPROVED" && can(`${c.perm}.create`) && <button className="btn btn-sm btn-outline-primary" onClick={() => setAct("new-version")}>Create new version</button>}</div>
    <div className="small text-muted mt-2">Approved versions are immutable; changes create a new version that must be approved again.</div>
    {act && <ReasonDialog title={act === "approve" ? "Approve version" : act === "return" ? "Return to draft" : "Create new version"} needPassword={act === "approve"} meaning="QA_APPROVED" onClose={() => setAct(null)}
      onSubmit={async (reason, password) => { try {
        if (act === "new-version") { const nv = await api(`/${kind}/${id}/new-version`, { method: "POST", body: { reason } }); onOpen(nv.id); }
        else await api(`/${kind}/${id}/${act}`, { method: "POST", body: act === "approve" ? { password, reason } : { reason } });
        load(); } catch (e) { throw new Error(errText(e)); } }} />}
    {editing && <FormModal title="Edit draft" fields={fields.filter((f) => f.key !== "material_id")} initial={d} onClose={() => setEditing(false)} onSave={async (b) => { await api(`/${kind}/${id}`, { method: "PATCH", body: b }); setEditing(false); load(); }} />}
    {param && <FormModal title="Add test parameter" initial={param} extra={{}} onClose={() => setParam(null)} onSave={async (b) => { await api(`/specifications/${id}/parameters`, { method: "POST", body: b }); setParam(null); load(); }}
      fields={[{ key: "test_name", label: "Test name", required: true }, { key: "spec_type", label: "Type", type: "select", options: ["NUMERIC", "RANGE", "TEXT", "PASS_FAIL"].map((x) => ({ value: x, label: x })) },
        { key: "lsl", label: "LSL", type: "number" }, { key: "usl", label: "USL", type: "number" }, { key: "target", label: "Target", type: "number" }, { key: "unit", label: "Unit" },
        { key: "decimal_places", label: "Decimal places", type: "number" }, { key: "test_method", label: "Method" }, { key: "acceptance_criteria", label: "Acceptance criteria" },
        { key: "criticality", label: "Criticality", type: "select", options: ["CRITICAL", "MAJOR", "MINOR"].map((x) => ({ value: x, label: x })) }, { key: "frequency", label: "Frequency" }]} />}
  </Modal>);
}
