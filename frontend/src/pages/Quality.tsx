import { useEffect, useState } from "react";
import { DataList, useLookup } from "../components/DataList";
import { Alert, Modal, PageHeader, ReasonDialog, StatusBadge } from "../components/ui";
import { useAuth } from "../hooks/useAuth";
import { api, errText } from "../services/api";

type Act = { label: string; path: string; perm: string; show: (d: any) => boolean; sign?: boolean; reason?: boolean; cls?: string; body?: (d: any) => any; confirm?: string };

/** Generic record dialog: shows fields + workflow action buttons; signed actions open the e-signature dialog. */
function RecordDialog({ base, id, title, fields, actions, onClose, extra }: { base: string; id: number; title: (d: any) => string; fields: [string, (d: any) => any][]; actions: Act[]; onClose: () => void; extra?: (d: any, reload: () => void) => any }) {
  const { can } = useAuth(); const [d, setD] = useState<any>(null); const [err, setErr] = useState(""); const [dlg, setDlg] = useState<Act | null>(null);
  const load = () => api(`${base}/${id}`).then(setD).catch((e) => setErr(errText(e)));
  useEffect(() => { load(); }, []);
  if (!d) return <Modal title="Loading" onClose={onClose}><Alert>{err}</Alert></Modal>;
  const run = async (a: Act, reason = "", password = "") => { await api(`${base}/${id}/${a.path}`, { method: "POST", body: { reason, password, ...(a.body ? a.body(d) : {}) } }); load(); };
  return (<Modal title={title(d)} onClose={onClose}>
    <Alert>{err}</Alert>
    <div className="mb-2"><StatusBadge status={d.status} /></div>
    <dl className="row small">{fields.map(([k, f]) => <div className="col-12 mb-1" key={k}><b>{k}:</b> {String(f(d) ?? "—")}</div>)}</dl>
    {extra && extra(d, load)}
    <div className="d-flex gap-2 flex-wrap">{actions.filter((a) => can(a.perm) && a.show(d)).map((a) => (
      <button key={a.path} className={"btn btn-sm " + (a.cls || "btn-outline-primary")} onClick={() => (a.sign || a.reason ? setDlg(a) : run(a).catch((e) => setErr(errText(e))))}>{a.sign && <i className="bi bi-pen me-1" />}{a.label}</button>))}</div>
    {dlg && <ReasonDialog title={dlg.label} needPassword={!!dlg.sign} onClose={() => setDlg(null)} onSubmit={async (reason, pw) => { try { await run(dlg, reason, pw); } catch (e) { throw new Error(errText(e)); } }} />}
  </Modal>);
}

function CreateDialog({ title, path, fields, onClose, onCreated, transform }: { title: string; path: string; fields: { key: string; label: string; type?: string; options?: string[]; area?: boolean }[]; onClose: () => void; onCreated: (id: number) => void; transform?: (b: any) => any }) {
  const [v, setV] = useState<any>({}); const [err, setErr] = useState("");
  const save = async () => { try { const r = await api(path, { method: "POST", body: { ...(transform ? transform(v) : v), reason: "Created" } }); onCreated(r.id); } catch (e) { setErr(errText(e)); } };
  return (<Modal title={title} onClose={onClose} footer={<><button className="btn btn-outline-secondary" onClick={onClose}>Cancel</button><button className="btn btn-primary" onClick={save}>Save</button></>}>
    <Alert>{err}</Alert>
    {fields.map((f) => (<div className="mb-2" key={f.key}><label className="form-label small mb-0">{f.label}</label>
      {f.options ? <select className="form-select" onChange={(e) => setV({ ...v, [f.key]: e.target.value })}><option value="">…</option>{f.options.map((o) => <option key={o}>{o}</option>)}</select>
        : f.area ? <textarea className="form-control" rows={3} onChange={(e) => setV({ ...v, [f.key]: e.target.value })} />
          : <input type={f.type || "text"} className="form-control" onChange={(e) => setV({ ...v, [f.key]: f.type === "number" ? Number(e.target.value) : e.target.value })} />}</div>))}
  </Modal>);
}

function Page({ title, crumb, path, cols, filters, create, createPerm, detail }: any) {
  const { can } = useAuth(); const [sel, setSel] = useState<number | null>(null); const [creating, setCreating] = useState(false); const [reload, setReload] = useState<() => void>(() => () => {});
  return (<>
    <DataList title={title} crumbs={["Quality", crumb]} path={path} filters={filters} cols={cols}
      extraActions={create && can(createPerm) && <button className="btn btn-primary" onClick={() => setCreating(true)}><i className="bi bi-plus-lg" /> New</button>}
      onRow={(r, load) => { setSel(r.id); setReload(() => load); }} />
    {creating && create(() => { setCreating(false); reload(); }, (id: number) => { setCreating(false); setSel(id); })}
    {sel && detail(sel, () => { setSel(null); reload(); })}
  </>);
}

const SEV = ["MINOR", "MAJOR", "CRITICAL"];

/* ------------------------------------------------------------------ Deviations */
export function Deviations() {
  return <Page title="Deviations" crumb="Deviations" path="/deviations" createPerm="quality.deviation.create"
    filters={[{ key: "status", label: "Status", options: ["OPEN", "INVESTIGATION", "CAPA_PROPOSED", "QA_REVIEW", "CLOSED", "CANCELLED"] }, { key: "severity", label: "Severity", options: SEV }]}
    cols={[{ key: "dev_no", label: "Deviation" }, { key: "title", label: "Title" }, { key: "severity", label: "Severity" }, { key: "source", label: "Source" }, { key: "ref_label", label: "Linked" }, { key: "status", label: "Status", badge: true }]}
    create={(close: any, created: any) => <CreateDialog title="Raise deviation" path="/deviations" onClose={close} onCreated={created}
      fields={[{ key: "title", label: "Title" }, { key: "description", label: "Description", area: true }, { key: "severity", label: "Severity", options: SEV }, { key: "category", label: "Category", options: ["PROCESS", "MATERIAL", "EQUIPMENT", "DOCUMENTATION", "QC", "OTHER"] }]} transform={(b) => ({ severity: "MINOR", ...b })} />}
    detail={(id: number, close: any) => <DeviationDetail id={id} onClose={close} />} />;
}

function DeviationDetail({ id, onClose }: { id: number; onClose: () => void }) {
  const [form, setForm] = useState<any>({}); const [err, setErr] = useState("");
  return <RecordDialog base="/deviations" id={id} onClose={onClose} title={(d) => `${d.dev_no} — ${d.title}`}
    fields={[["Severity", (d) => d.severity], ["Source", (d) => d.source], ["Linked record", (d) => d.ref_label], ["Description", (d) => d.description], ["Root cause", (d) => d.root_cause], ["Impact", (d) => d.impact_assessment], ["CAPA", (d) => d.capa_no], ["Blocks release/dispatch of linked lot", (d) => (d.blocks_release ? "yes" : "no")]]}
    extra={(d, reload) => ["OPEN", "INVESTIGATION"].includes(d.status) && <div className="border rounded p-2 mb-2"><Alert>{err}</Alert>
      {[["root_cause", "Root cause"], ["impact_assessment", "Impact assessment"], ["no_capa_justification", "Justification if no CAPA"]].map(([k, l]) => <textarea key={k} className="form-control form-control-sm mb-1" rows={2} placeholder={l} defaultValue={d[k] ?? ""} onChange={(e) => setForm({ ...form, [k]: e.target.value })} />)}
      <button className="btn btn-sm btn-outline-secondary" onClick={async () => { try { await api(`/deviations/${id}`, { method: "PATCH", body: { ...form, reason: "Investigation updated" } }); setErr(""); reload(); } catch (e) { setErr(errText(e)); } }}>Save investigation</button></div>}
    actions={[
      { label: "Start investigation", path: "investigate", perm: "quality.deviation.investigate", show: (d) => d.status === "OPEN" },
      { label: "Propose CAPA / conclude", path: "propose-capa", perm: "quality.deviation.investigate", show: (d) => d.status === "INVESTIGATION" },
      { label: "Submit to QA review", path: "submit-review", perm: "quality.deviation.investigate", show: (d) => d.status === "CAPA_PROPOSED" },
      { label: "Return to investigation", path: "return", perm: "quality.deviation.close", show: (d) => d.status === "QA_REVIEW", reason: true },
      { label: "Close (QA e-signature)", path: "close", perm: "quality.deviation.close", show: (d) => d.status === "QA_REVIEW", sign: true, cls: "btn-success" },
      { label: "Cancel", path: "cancel", perm: "quality.deviation.cancel", show: (d) => ["OPEN", "INVESTIGATION"].includes(d.status), reason: true, cls: "btn-outline-danger" }]} />;
}

/* ------------------------------------------------------------------ CAPA */
export function CAPAs() {
  const users = useLookup("/users", "full_name", "id", "username");
  return <Page title="CAPA" crumb="CAPA" path="/capas" createPerm="quality.capa.create"
    filters={[{ key: "status", label: "Status", options: ["OPEN", "IN_PROGRESS", "EFFECTIVENESS_CHECK", "CLOSED", "CANCELLED"] }]}
    cols={[{ key: "capa_no", label: "CAPA" }, { key: "title", label: "Title" }, { key: "source_ref", label: "Source" }, { key: "owner", label: "Owner" }, { key: "due_date", label: "Due" }, { key: "overdue", label: "", render: (r: any) => (r.overdue ? <span className="badge text-bg-danger">OVERDUE</span> : "") }, { key: "status", label: "Status", badge: true }]}
    create={(close: any, created: any) => <CreateDialog title="New CAPA" path="/capas" onClose={close} onCreated={created}
      fields={[{ key: "title", label: "Title" }, { key: "description", label: "Description", area: true }, { key: "capa_type", label: "Type", options: ["CORRECTIVE", "PREVENTIVE"] }, { key: "source", label: "Source", options: ["DEVIATION", "OOS", "COMPLAINT", "AUDIT", "OTHER"] },
        { key: "source_ref", label: "Source reference (e.g. DEV-…)" }, { key: "owner_id", label: `Owner user id (${users.slice(0, 5).map((u) => `${u.label}=${u.value}`).join(", ")}…)`, type: "number" }, { key: "due_date", label: "Due date", type: "date" }]} />}
    detail={(id: number, close: any) => <CapaDetail id={id} onClose={close} />} />;
}

function CapaDetail({ id, onClose }: { id: number; onClose: () => void }) {
  const { can } = useAuth(); const [err, setErr] = useState(""); const [a, setA] = useState<any>({});
  return <RecordDialog base="/capas" id={id} onClose={onClose} title={(d) => `${d.capa_no} — ${d.title}`}
    fields={[["Type", (d) => d.capa_type], ["Owner", (d) => d.owner], ["Due", (d) => d.due_date], ["Effectiveness", (d) => d.effectiveness_result]]}
    extra={(d, reload) => (<div className="mb-2"><Alert>{err}</Alert>
      <table className="table table-sm small"><tbody>{d.actions.map((x: any) => <tr key={x.id}><td>{x.seq}. {x.description}</td><td>{x.due_date}</td><td>{x.status === "DONE" ? <span className="badge text-bg-success">done</span> : can("quality.capa.update") && <button className="btn btn-sm btn-outline-success" onClick={async () => { const notes = prompt("Completion notes"); if (!notes) return; try { await api(`/capas/${id}/actions/${x.id}/complete`, { method: "POST", body: { notes, reason: "Action completed" } }); reload(); } catch (e) { setErr(errText(e)); } }}>Complete</button>}</td></tr>)}</tbody></table>
      {["OPEN", "IN_PROGRESS"].includes(d.status) && can("quality.capa.update") && <div className="row g-1"><div className="col-5"><input className="form-control form-control-sm" placeholder="New action" onChange={(e) => setA({ ...a, description: e.target.value })} /></div>
        <div className="col-3"><input type="number" className="form-control form-control-sm" placeholder="Owner id" onChange={(e) => setA({ ...a, owner_id: Number(e.target.value) })} /></div><div className="col-3"><input type="date" className="form-control form-control-sm" onChange={(e) => setA({ ...a, due_date: e.target.value })} /></div>
        <div className="col-1"><button className="btn btn-sm btn-outline-primary" onClick={async () => { try { await api(`/capas/${id}/actions`, { method: "POST", body: a }); setErr(""); reload(); } catch (e) { setErr(errText(e)); } }}>+</button></div></div>}</div>)}
    actions={[
      { label: "Start effectiveness check", path: "effectiveness-check", perm: "quality.capa.update", show: (d) => d.status === "IN_PROGRESS", body: () => ({ effectiveness_due: new Date(Date.now() + 90 * 864e5).toISOString().slice(0, 10) }), reason: true },
      { label: "Close — effective (e-sign)", path: "close", perm: "quality.capa.close", show: (d) => d.status === "EFFECTIVENESS_CHECK", sign: true, cls: "btn-success", body: () => ({ effective: true }) },
      { label: "Mark ineffective", path: "close", perm: "quality.capa.close", show: (d) => d.status === "EFFECTIVENESS_CHECK", sign: true, cls: "btn-outline-warning", body: () => ({ effective: false }) }]} />;
}

/* ------------------------------------------------------------------ Change control */
export function ChangeControls() {
  return <Page title="Change control" crumb="Change control" path="/change-controls" createPerm="quality.cc.create"
    filters={[{ key: "status", label: "Status", options: ["DRAFT", "ASSESSMENT", "APPROVAL", "IMPLEMENTATION", "EFFECTIVENESS", "CLOSED", "REJECTED", "CANCELLED"] }]}
    cols={[{ key: "cc_no", label: "CC" }, { key: "title", label: "Title" }, { key: "change_type", label: "Type" }, { key: "risk_level", label: "Risk" }, { key: "status", label: "Status", badge: true }]}
    create={(close: any, created: any) => <CreateDialog title="Raise change control" path="/change-controls" onClose={close} onCreated={created}
      fields={[{ key: "title", label: "Title" }, { key: "description", label: "Description", area: true }, { key: "change_type", label: "Type", options: ["MASTER_DATA", "PROCESS", "EQUIPMENT", "DOCUMENT", "SYSTEM", "OTHER"] }]} />}
    detail={(id: number, close: any) => <CCDetail id={id} onClose={close} />} />;
}

function CCDetail({ id, onClose }: { id: number; onClose: () => void }) {
  const [err, setErr] = useState(""); const [l, setL] = useState<any>({ entity: "specification" }); const [as, setAs] = useState<any>({ risk_level: "LOW" });
  return <RecordDialog base="/change-controls" id={id} onClose={onClose} title={(d) => `${d.cc_no} — ${d.title}`}
    fields={[["Description", (d) => d.description], ["Impact assessment", (d) => d.impact_assessment], ["Risk", (d) => d.risk_level], ["Decision", (d) => d.decision_comment], ["Implementation", (d) => d.implementation_notes]]}
    extra={(d, reload) => (<div className="mb-2"><Alert>{err}</Alert>
      <b className="small">Linked master versions</b><ul className="small">{d.links.map((x: any) => <li key={x.id}>{x.entity} {x.number} v{x.version_no} — {x.status}</li>)}</ul>
      {["DRAFT", "ASSESSMENT", "APPROVAL", "IMPLEMENTATION"].includes(d.status) && <div className="row g-1 mb-2"><div className="col-4"><select className="form-select form-select-sm" onChange={(e) => setL({ ...l, entity: e.target.value })}>{["specification", "stp", "sampling_plan", "bom_header", "vendor_material", "sop"].map((x) => <option key={x}>{x}</option>)}</select></div>
        <div className="col-4"><input type="number" className="form-control form-control-sm" placeholder="Draft version id" onChange={(e) => setL({ ...l, record_id: Number(e.target.value) })} /></div>
        <div className="col-4"><button className="btn btn-sm btn-outline-primary" onClick={async () => { try { await api(`/change-controls/${id}/links`, { method: "POST", body: { ...l, reason: "Linked" } }); setErr(""); reload(); } catch (e) { setErr(errText(e)); } }}>Link</button></div></div>}
      {d.status === "ASSESSMENT" && <div className="border rounded p-2"><textarea className="form-control form-control-sm mb-1" placeholder="Impact assessment" onChange={(e) => setAs({ ...as, impact_assessment: e.target.value })} />
        <select className="form-select form-select-sm mb-1" onChange={(e) => setAs({ ...as, risk_level: e.target.value })}>{["LOW", "MEDIUM", "HIGH"].map((x) => <option key={x}>{x}</option>)}</select>
        <button className="btn btn-sm btn-primary" onClick={async () => { try { await api(`/change-controls/${id}/assess`, { method: "POST", body: { ...as, reason: "Assessment completed" } }); setErr(""); reload(); } catch (e) { setErr(errText(e)); } }}>Complete assessment</button></div>}</div>)}
    actions={[
      { label: "Submit for assessment", path: "submit", perm: "quality.cc.update", show: (d) => d.status === "DRAFT" },
      { label: "Approve (e-sign)", path: "decision", perm: "quality.cc.approve", show: (d) => d.status === "APPROVAL", sign: true, cls: "btn-success", body: () => ({ approve: true }) },
      { label: "Reject (e-sign)", path: "decision", perm: "quality.cc.approve", show: (d) => d.status === "APPROVAL", sign: true, cls: "btn-outline-danger", body: () => ({ approve: false }) },
      { label: "Mark implemented", path: "implemented", perm: "quality.cc.update", show: (d) => d.status === "IMPLEMENTATION", reason: true, body: () => ({ notes: "Implemented" }) },
      { label: "Close (e-sign)", path: "close", perm: "quality.cc.close", show: (d) => d.status === "EFFECTIVENESS", sign: true, cls: "btn-success", body: () => ({ notes: "Effectiveness verified" }) },
      { label: "Cancel", path: "cancel", perm: "quality.cc.update", show: (d) => ["DRAFT", "ASSESSMENT", "APPROVAL", "IMPLEMENTATION"].includes(d.status), reason: true, cls: "btn-outline-danger" }]} />;
}

/* ------------------------------------------------------------------ Risk (FMEA) */
export function Risks() {
  return <Page title="Risk assessments (FMEA)" crumb="Risk" path="/risk-assessments" createPerm="quality.risk.create"
    filters={[{ key: "status", label: "Status", options: ["DRAFT", "APPROVED"] }]}
    cols={[{ key: "ra_no", label: "RA" }, { key: "title", label: "Title" }, { key: "max_rpn", label: "Max RPN" }, { key: "high_items", label: "HIGH items" }, { key: "status", label: "Status", badge: true }]}
    create={(close: any, created: any) => <CreateDialog title="New risk assessment" path="/risk-assessments" onClose={close} onCreated={created}
      fields={[{ key: "title", label: "Title" }, { key: "scope", label: "Scope", area: true }]} transform={(b) => ({ ...b, items: [] })} />}
    detail={(id: number, close: any) => <RiskDetail id={id} onClose={close} />} />;
}

function RiskDetail({ id, onClose }: { id: number; onClose: () => void }) {
  const { can } = useAuth(); const [err, setErr] = useState(""); const [n, setN] = useState<any>({ severity: 5, occurrence: 5, detection: 5 });
  const [items, setItems] = useState<any[] | null>(null);
  return <RecordDialog base="/risk-assessments" id={id} onClose={onClose} title={(d) => `${d.ra_no} — ${d.title}`} fields={[["Scope", (d) => d.scope], ["Max RPN", (d) => d.max_rpn]]}
    extra={(d, reload) => { const rows = items ?? d.items; return (<div className="mb-2"><Alert>{err}</Alert>
      <table className="table table-sm small"><thead><tr><th>Step</th><th>Failure mode</th><th>S</th><th>O</th><th>D</th><th>RPN</th><th>Level</th><th>Mitigation</th><th>Residual</th></tr></thead>
        <tbody>{rows.map((i: any, k: number) => <tr key={k} className={i.risk_level === "HIGH" ? "table-danger" : i.risk_level === "MEDIUM" ? "table-warning" : ""}><td>{i.function_step}</td><td>{i.failure_mode}</td><td>{i.severity}</td><td>{i.occurrence}</td><td>{i.detection}</td><td>{i.rpn ?? i.severity * i.occurrence * i.detection}</td><td>{i.risk_level ?? ""}</td><td>{i.mitigation}</td><td>{i.residual_rpn ?? ""}</td></tr>)}</tbody></table>
      {d.status === "DRAFT" && can("quality.risk.update") && <div className="row g-1"><div className="col-3"><input className="form-control form-control-sm" placeholder="Function / step" onChange={(e) => setN({ ...n, function_step: e.target.value })} /></div><div className="col-3"><input className="form-control form-control-sm" placeholder="Failure mode" onChange={(e) => setN({ ...n, failure_mode: e.target.value })} /></div>
        {["severity", "occurrence", "detection"].map((k) => <div className="col-1" key={k}><input type="number" min={1} max={10} className="form-control form-control-sm" placeholder={k[0].toUpperCase()} onChange={(e) => setN({ ...n, [k]: Number(e.target.value) })} /></div>)}
        <div className="col-2"><input className="form-control form-control-sm" placeholder="Mitigation" onChange={(e) => setN({ ...n, mitigation: e.target.value })} /></div>
        <div className="col-1"><button className="btn btn-sm btn-outline-primary" onClick={async () => { try { await api(`/risk-assessments/${id}/items`, { method: "PUT", body: { items: [...d.items.map(({ rpn, risk_level, residual_rpn, residual_level, id: _i, ra_id, seq, created_at, ...r }: any) => r), n], reason: "FMEA updated" } }); setItems(null); setErr(""); reload(); } catch (e) { setErr(errText(e)); } }}>+</button></div></div>}</div>); }}
    actions={[{ label: "Approve (e-sign)", path: "approve", perm: "quality.risk.approve", show: (d) => d.status === "DRAFT", sign: true, cls: "btn-success" }]} />;
}

/* ------------------------------------------------------------------ SOP */
export function SOPs() {
  return <Page title="SOP control" crumb="SOPs" path="/sops" createPerm="quality.sop.create"
    filters={[{ key: "status", label: "Status", options: ["DRAFT", "UNDER_REVIEW", "APPROVED", "SUPERSEDED"] }]}
    cols={[{ key: "sop_no", label: "SOP" }, { key: "version_no", label: "Ver" }, { key: "title", label: "Title" }, { key: "review_due_date", label: "Review due" }, { key: "review_overdue", label: "", render: (r: any) => (r.review_overdue ? <span className="badge text-bg-danger">REVIEW OVERDUE</span> : "") }, { key: "status", label: "Status", badge: true }]}
    create={(close: any, created: any) => <CreateDialog title="New SOP" path="/sops" onClose={close} onCreated={created} fields={[{ key: "title", label: "Title" }, { key: "review_period_months", label: "Review period (months)", type: "number" }]} />}
    detail={(id: number, close: any) => <SopDetail id={id} onClose={close} />} />;
}

function SopDetail({ id, onClose }: { id: number; onClose: () => void }) {
  const [err, setErr] = useState("");
  const upload = async (f: File, reload: () => void) => { const fd = new FormData(); fd.append("file", f); try { await api(`/sops/${id}/document`, { method: "POST", form: fd }); reload(); } catch (e) { setErr(errText(e)); } };
  return <RecordDialog base="/sops" id={id} onClose={onClose} title={(d) => `${d.sop_no} v${d.version_no} — ${d.title}`}
    fields={[["Document", (d) => (d.document ? `${d.document.name} (sha256 ${d.document.sha256.slice(0, 12)}…)` : "none attached")], ["Effective from", (d) => d.effective_from], ["Review due", (d) => d.review_due_date], ["Acknowledged by", (d) => d.acknowledgements], ["Acknowledged by me", (d) => (d.acknowledged_by_me ? "yes" : "no")]]}
    extra={(d, reload) => d.status === "DRAFT" && <div className="mb-2"><Alert>{err}</Alert><input type="file" accept=".pdf" className="form-control form-control-sm" onChange={(e) => e.target.files && upload(e.target.files[0], reload)} /></div>}
    actions={[
      { label: "Submit for approval", path: "submit", perm: "quality.sop.update", show: (d) => d.status === "DRAFT" },
      { label: "Approve (e-sign)", path: "approve", perm: "quality.sop.approve", show: (d) => d.status === "UNDER_REVIEW", sign: true, cls: "btn-success" },
      { label: "New version", path: "new-version", perm: "quality.sop.create", show: (d) => d.status === "APPROVED", reason: true },
      { label: "I have read and understood", path: "acknowledge", perm: "quality.sop.acknowledge", show: (d) => d.status === "APPROVED" && !d.acknowledged_by_me }]} />;
}

/* ------------------------------------------------------------------ Complaints & recalls */
export function Complaints() {
  return <Page title="Customer complaints" crumb="Complaints" path="/complaints" createPerm="quality.complaint.create"
    filters={[{ key: "status", label: "Status", options: ["RECEIVED", "INVESTIGATION", "CLOSED", "CANCELLED"] }, { key: "severity", label: "Severity", options: SEV }]}
    cols={[{ key: "complaint_no", label: "Complaint" }, { key: "received_on", label: "Received" }, { key: "category", label: "Category" }, { key: "severity", label: "Severity" }, { key: "material_batch_id", label: "Lot id" }, { key: "status", label: "Status", badge: true }]}
    create={(close: any, created: any) => <CreateDialog title="Record complaint" path="/complaints" onClose={close} onCreated={created}
      fields={[{ key: "description", label: "Description", area: true }, { key: "severity", label: "Severity", options: SEV }, { key: "category", label: "Category", options: ["QUALITY", "ADVERSE_EVENT", "PACKAGING", "DELIVERY", "OTHER"] }, { key: "material_batch_id", label: "Lot id", type: "number" }, { key: "dispatch_id", label: "Dispatch id (optional)", type: "number" }]} />}
    detail={(id: number, close: any) => <ComplaintDetail id={id} onClose={close} />} />;
}

function ComplaintDetail({ id, onClose }: { id: number; onClose: () => void }) {
  const { can } = useAuth(); const [inv, setInv] = useState(""); const [err, setErr] = useState("");
  return <RecordDialog base="/complaints" id={id} onClose={onClose} title={(d) => `${d.complaint_no} (${d.severity})`}
    fields={[["Description", (d) => d.description], ["Investigation", (d) => d.investigation], ["Conclusion", (d) => d.conclusion], ["Linked deviation id", (d) => d.deviation_id], ["Hold id", (d) => d.hold_id]]}
    extra={(d, reload) => ["RECEIVED", "INVESTIGATION"].includes(d.status) && can("quality.complaint.update") && <div className="mb-2"><Alert>{err}</Alert><textarea className="form-control form-control-sm mb-1" placeholder="Investigation notes" onChange={(e) => setInv(e.target.value)} />
      <button className="btn btn-sm btn-outline-primary me-2" onClick={async () => { try { await api(`/complaints/${id}/investigate`, { method: "POST", body: { investigation: inv, reason: "Investigation" } }); setErr(""); reload(); } catch (e) { setErr(errText(e)); } }}>Save investigation</button>
      {!d.deviation_id && can("quality.deviation.create") && <button className="btn btn-sm btn-outline-warning" onClick={async () => { try { await api(`/complaints/${id}/deviation`, { method: "POST" }); setErr(""); reload(); } catch (e) { setErr(errText(e)); } }}>Raise deviation</button>}</div>}
    actions={[{ label: "Close (e-sign)", path: "close", perm: "quality.complaint.close", show: (d) => d.status === "INVESTIGATION", sign: true, cls: "btn-success", body: (d) => ({ conclusion: d.conclusion || "Investigation complete" }) }]} />;
}

export function Recalls() {
  const { can } = useAuth(); const [sel, setSel] = useState<number | null>(null); const [creating, setCreating] = useState(false); const [reload, setReload] = useState<() => void>(() => () => {});
  const [f, setF] = useState<any>({ recall_class: "II" }); const [err, setErr] = useState(""); const [sign, setSign] = useState(false);
  return (<>
    <DataList title="Recalls" crumbs={["Quality", "Recalls"]} path="/recalls" filters={[{ key: "status", label: "Status", options: ["INITIATED", "IN_PROGRESS", "CLOSED"] }]}
      cols={[{ key: "recall_no", label: "Recall" }, { key: "lot_no", label: "Lot / batch" }, { key: "recall_class", label: "Class" }, { key: "reason", label: "Reason" }, { key: "status", label: "Status", badge: true }]}
      extraActions={can("quality.recall.create") && <button className="btn btn-danger" onClick={() => setCreating(true)}><i className="bi bi-exclamation-octagon" /> Initiate recall</button>}
      onRow={(r, load) => { setSel(r.id); setReload(() => load); }} />
    {creating && <Modal title="Initiate recall" onClose={() => setCreating(false)} footer={<button className="btn btn-danger" disabled={!f.material_batch_id || !f.reason} onClick={() => setSign(true)}><i className="bi bi-pen" /> Sign & initiate</button>}>
      <Alert>{err}</Alert><div className="alert alert-warning small">The lot is placed on quality hold immediately and affected shipments are derived from the dispatch ledger.</div>
      <input type="number" className="form-control mb-2" placeholder="Lot id" onChange={(e) => setF({ ...f, material_batch_id: Number(e.target.value) })} />
      <select className="form-select mb-2" value={f.recall_class} onChange={(e) => setF({ ...f, recall_class: e.target.value })}>{["I", "II", "III"].map((c) => <option key={c}>{c}</option>)}</select>
      <textarea className="form-control" placeholder="Reason" onChange={(e) => setF({ ...f, reason: e.target.value })} />
      {sign && <ReasonDialog title="Confirm recall initiation" needPassword onClose={() => setSign(false)} onSubmit={async (_r, password) => { try { const r = await api("/recalls", { method: "POST", body: { ...f, password } }); setCreating(false); setSel(r.id); } catch (e) { throw new Error(errText(e)); } }} />}</Modal>}
    {sel && <RecallDetail id={sel} onClose={() => { setSel(null); reload(); }} />}
  </>);
}

function RecallDetail({ id, onClose }: { id: number; onClose: () => void }) {
  const { can } = useAuth(); const [err, setErr] = useState("");
  const rlocs = useLookup("/locations?is_rejected_area=1", "name", "id", "location_code");
  return <RecordDialog base="/recalls" id={id} onClose={onClose} title={(d) => `${d.recall_no} — class ${d.recall_class} — ${d.lot_no}`}
    fields={[["Reason", (d) => d.reason], ["Reconciliation", (d) => d.reconciliation && `dispatched ${d.reconciliation.dispatched} · returned ${d.reconciliation.returned} · unrecoverable ${d.reconciliation.unrecoverable} · outstanding ${d.reconciliation.outstanding} (${d.reconciliation.recovery_pct}% recovered)`]]}
    extra={(d, reload) => (<div className="mb-2"><Alert>{err}</Alert><table className="table table-sm small"><thead><tr><th>Customer</th><th>Dispatch</th><th>Sent</th><th>Notified</th><th>Returned</th><th /></tr></thead>
      <tbody>{d.lines.map((l: any) => <tr key={l.id}><td>{l.customer}</td><td>{l.dispatch_no}</td><td>{l.quantity_dispatched}</td><td>{l.notified_at ? "yes" : "no"}</td><td>{l.quantity_returned} (+{l.quantity_consumed_or_unrecoverable} unrecoverable)</td>
        <td>{d.status !== "CLOSED" && can("quality.recall.update") && (!l.notified_at ? <button className="btn btn-sm btn-outline-primary" onClick={async () => { try { await api(`/recalls/${id}/lines/${l.id}/notify`, { method: "POST", body: { response: prompt("Customer response") || null, reason: "Notified" } }); setErr(""); reload(); } catch (e) { setErr(errText(e)); } }}>Notified</button>
          : <button className="btn btn-sm btn-outline-success" onClick={async () => { const ret = Number(prompt("Quantity returned") || 0), un = Number(prompt("Quantity unrecoverable") || 0); try { await api(`/recalls/${id}/lines/${l.id}/return`, { method: "POST", body: { returned: ret, unrecoverable: un, location_id: rlocs[0] ? Number(rlocs[0].value) : null, reason: "Recall return" } }); setErr(""); reload(); } catch (e) { setErr(errText(e)); } }}>Record return</button>)}</td></tr>)}</tbody></table></div>)}
    actions={[{ label: "Close recall (e-sign)", path: "close", perm: "quality.recall.close", show: (d) => d.status === "IN_PROGRESS", sign: true, cls: "btn-success", body: (d) => ({ summary: `Recovery ${d.reconciliation.recovery_pct}%` }) }]} />;
}
