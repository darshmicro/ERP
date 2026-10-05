import { useCallback, useEffect, useState } from "react";
import { Alert, PageHeader, fmt } from "../components/ui";
import { useAuth } from "../hooks/useAuth";
import { api, errText } from "../services/api";

export default function Audit() {
  const { can } = useAuth();
  const [f, setF] = useState<any>({ entity: "", record_id: "", module: "", user_name: "", action: "" });
  const [rows, setRows] = useState<any[]>([]); const [next, setNext] = useState<number | null>(null); const [err, setErr] = useState(""); const [ver, setVer] = useState<any>(null);
  const qs = (extra: Record<string, any> = {}) => new URLSearchParams(Object.entries({ ...f, ...extra }).filter(([, v]) => v !== "" && v != null) as any).toString();
  const load = useCallback(async (append = false, before?: number | null) => {
    try { const r = await api(`/audit-trail?${qs(before ? { before_id: before } : {})}`); setRows(append ? (p) => [...p, ...r.items] : r.items); setNext(r.next_before_id); setErr(""); }
    catch (e) { setErr(errText(e)); }
  }, [f]);
  useEffect(() => { load(); }, []);
  const set = (k: string) => (e: any) => setF({ ...f, [k]: e.target.value });
  return (
    <>
      <PageHeader title="Audit Trail" crumbs={["Quality", "Audit trail"]} actions={<>
        {can("audit.trail.verify") && <button className="btn btn-outline-secondary" onClick={async () => setVer(await api("/audit-trail/verify"))}><i className="bi bi-shield-check" /> Verify integrity</button>}
        {can("audit.trail.export") && <a className="btn btn-outline-primary" href={`/api/v1/audit-trail/export?${qs()}`}><i className="bi bi-download" /> Export CSV</a>}</>} />
      <Alert>{err}</Alert>
      {ver && <Alert kind={ver.ok ? "success" : "danger"}>{ver.ok ? `Hash chain verified: ${ver.checked} records intact.` : `INTEGRITY FAILURE near audit id ${ver.first_bad_audit_id ?? "tail"} — ${ver.detail ?? "record altered"}`}</Alert>}
      <div className="row g-2 mb-2">{[["entity", "Entity"], ["record_id", "Record ID"], ["module", "Module"], ["user_name", "User"], ["action", "Action"]].map(([k, l]) => (
        <div className="col-6 col-md-2" key={k}><input className="form-control form-control-sm" placeholder={l} value={f[k]} onChange={set(k)} /></div>))}
        <div className="col-auto"><button className="btn btn-sm btn-primary" onClick={() => load()}>Search</button></div></div>
      <div className="table-responsive"><table className="table table-sm table-striped bg-white">
        <thead><tr><th>When</th><th>User</th><th>Role</th><th>Module</th><th>Entity</th><th>Rec</th><th>Action</th><th>Field</th><th>Old</th><th>New</th><th>Reason</th><th>IP</th></tr></thead>
        <tbody>{rows.map((r) => <tr key={r.id}><td className="text-nowrap">{fmt(r.occurred_at)}</td><td>{r.user_name}</td><td className="small">{r.role_name}</td><td>{r.module}</td><td>{r.entity}</td><td>{r.record_id}</td>
          <td>{r.action}{r.signature_id && <i className="bi bi-pen ms-1" title="e-signature" />}</td><td>{r.field_name}</td><td className="mono text-break">{r.old_value}</td><td className="mono text-break">{r.new_value}</td><td>{r.reason}</td><td>{r.ip_address}</td></tr>)}</tbody></table></div>
      {next && <button className="btn btn-outline-secondary" onClick={() => load(true, next)}>Load more</button>}
    </>
  );
}
