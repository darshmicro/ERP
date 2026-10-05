import { useEffect, useState } from "react";
import { Alert, PageHeader, ReasonDialog, StatusBadge } from "../components/ui";
import { useAuth } from "../hooks/useAuth";
import { api, errText } from "../services/api";

export default function Workflows() {
  const { can } = useAuth();
  const [defs, setDefs] = useState<any[]>([]); const [err, setErr] = useState(""); const [sign, setSign] = useState<any>(null);
  const load = () => api("/workflows/definitions").then(setDefs).catch((e) => setErr(errText(e)));
  useEffect(() => { load(); }, []);
  return (<>
    <PageHeader title="Approval Workflows" crumbs={["Administration", "Workflows"]} />
    <Alert>{err}</Alert>
    <p className="text-muted small">Approval chains are versioned configuration. A new version must be approved by QA with an electronic signature before it takes effect; approved versions are never edited.</p>
    {defs.map((d) => (<div className="card mb-3" key={d.id}><div className="card-header d-flex justify-content-between">
      <span><b>{d.process_code}</b> v{d.version_no} — {d.name}</span>
      <span className="d-flex gap-2 align-items-center"><StatusBadge status={d.status} />
        {d.status === "DRAFT" && can("workflow.definition.approve") && <button className="btn btn-sm btn-success" onClick={() => setSign(d)}><i className="bi bi-pen" /> Approve (e-sign)</button>}</span></div>
      <ol className="list-group list-group-numbered list-group-flush">{d.steps.map((s: any) => (
        <li className="list-group-item small" key={s.seq}>{s.name} — role <b>{s.role_code}</b>, {s.min_approvals} approval(s){s.esig_required ? `, e-signature (${s.meaning})` : ""}{s.sla_hours ? `, SLA ${s.sla_hours}h` : ""}</li>))}</ol></div>))}
    {!defs.length && <div className="text-muted">No workflows defined yet.</div>}
    {sign && <ReasonDialog title={`Approve ${sign.process_code} v${sign.version_no}`} needPassword meaning="APPROVED_BY" onClose={() => setSign(null)}
      onSubmit={async (reason, password) => { try { await api(`/workflows/definitions/${sign.id}/approve`, { method: "POST", body: { password, reason } }); load(); } catch (e) { throw new Error(errText(e)); } }} />}
  </>);
}
