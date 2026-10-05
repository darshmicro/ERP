import { useEffect, useState } from "react";
import { Alert, Modal, PageHeader, ReasonDialog, StatusBadge, fmt } from "../components/ui";
import { useAuth } from "../hooks/useAuth";
import { api, errText } from "../services/api";

const ENTITIES = ["vendor", "material", "location", "stp", "specification"];

export default function Import() {
  const { can } = useAuth();
  const [jobs, setJobs] = useState<any[]>([]); const [entity, setEntity] = useState("vendor"); const [file, setFile] = useState<File | null>(null);
  const [err, setErr] = useState(""); const [sel, setSel] = useState<any>(null); const [sign, setSign] = useState<any>(null); const [msg, setMsg] = useState("");
  const load = () => api("/imports").then(setJobs).catch((e) => setErr(errText(e)));
  useEffect(() => { load(); }, []);
  const upload = async () => {
    const fd = new FormData(); fd.append("entity", entity); fd.append("file", file!);
    try { const j = await api("/imports", { method: "POST", form: fd }); setFile(null); setErr(""); load(); openJob(j.id); } catch (e) { setErr(errText(e)); }
  };
  const openJob = (id: number) => api(`/imports/${id}`).then(setSel).catch((e) => setErr(errText(e)));
  const step = async (id: number, path: string) => { try { const r = await api(`/imports/${id}/${path}`, { method: "POST" }); setMsg(path === "execute" ? `Imported: ${r.created} record(s) created as DRAFT.` : ""); load(); openJob(id); } catch (e) { setErr(errText(e)); } };
  return (<>
    <PageHeader title="Controlled Excel Import" crumbs={["Master data", "Import"]} />
    <Alert>{err}</Alert><Alert kind="success">{msg}</Alert>
    <div className="card p-3 mb-3"><div className="row g-2 align-items-end">
      <div className="col-md-3"><label className="form-label">Record type</label><select className="form-select" value={entity} onChange={(e) => setEntity(e.target.value)}>{ENTITIES.map((x) => <option key={x}>{x}</option>)}</select></div>
      <div className="col-md-3"><a className="btn btn-outline-secondary w-100" href={`/api/v1/imports/templates/${entity}`}><i className="bi bi-download" /> Template</a></div>
      <div className="col-md-4"><input type="file" accept=".xlsx" className="form-control" onChange={(e) => setFile(e.target.files?.[0] ?? null)} /></div>
      <div className="col-md-2"><button className="btn btn-primary w-100" disabled={!file || !can("import.job.create")} onClick={upload}>Upload & validate</button></div></div>
      <div className="form-text">Upload → validate → preview → submit → QA approval (e-signature) → import. Records are created as DRAFT and still need their normal approval.</div></div>
    <table className="table table-sm bg-white"><thead><tr><th>#</th><th>Type</th><th>File</th><th>Rows</th><th>Errors</th><th>Status</th><th>Uploaded</th></tr></thead>
      <tbody>{jobs.map((j) => (<tr key={j.id} role="button" onClick={() => openJob(j.id)}><td>{j.id}</td><td>{j.entity}</td><td>{j.filename}</td><td>{j.total_rows}</td><td className={j.error_rows ? "text-danger" : ""}>{j.error_rows}</td><td><StatusBadge status={j.status} /></td><td>{fmt(j.created_at)}</td></tr>))}</tbody></table>
    {sel && <Modal title={`Import job #${sel.job.id} — ${sel.job.entity}`} onClose={() => setSel(null)}>
      <div className="mb-2"><StatusBadge status={sel.job.status} /> {sel.job.total_rows} rows, {sel.job.error_rows} with errors
        {sel.job.error_rows > 0 && <a className="ms-2" href={`/api/v1/imports/${sel.job.id}/error-report`}>error report (xlsx)</a>}</div>
      <div style={{ maxHeight: 260, overflow: "auto" }}><table className="table table-sm small"><thead><tr><th>Row</th><th>Status</th><th>Data / errors</th></tr></thead>
        <tbody>{sel.rows.map((r: any) => (<tr key={r.row_no} className={r.status === "ERROR" ? "table-danger" : ""}><td>{r.row_no}</td><td>{r.status}</td>
          <td><span className="mono">{Object.entries(r.data).filter(([k, v]) => v != null && !k.startsWith("_")).map(([k, v]) => `${k}=${v}`).join("; ")}</span>{r.errors.map((e: string) => <div key={e} className="text-danger">{e}</div>)}</td></tr>))}</tbody></table></div>
      <div className="d-flex gap-2 mt-2">
        {sel.job.status === "VALIDATED" && !sel.job.error_rows && can("import.job.create") && <button className="btn btn-primary" onClick={() => step(sel.job.id, "submit")}>Submit for approval</button>}
        {sel.job.status === "SUBMITTED" && can("import.job.approve") && <button className="btn btn-success" onClick={() => setSign(sel.job)}><i className="bi bi-pen" /> Approve / reject</button>}
        {sel.job.status === "APPROVED" && can("import.job.create") && <button className="btn btn-primary" onClick={() => step(sel.job.id, "execute")}>Execute import</button>}</div>
      {sign && <ReasonDialog title="Approve import (e-signature)" needPassword meaning="APPROVED_BY" onClose={() => setSign(null)}
        onSubmit={async (reason, password) => { try { await api(`/imports/${sign.id}/decision`, { method: "POST", body: { approve: true, reason, password } }); load(); openJob(sign.id); } catch (e) { throw new Error(errText(e)); } }} />}
    </Modal>}
  </>);
}
