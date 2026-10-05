import { useEffect, useState } from "react";
import { Alert, PageHeader, ReasonDialog } from "../components/ui";
import { useAuth } from "../hooks/useAuth";
import { api, errText } from "../services/api";

export default function Roles() {
  const { can } = useAuth();
  const [roles, setRoles] = useState<any[]>([]); const [perms, setPerms] = useState<any[]>([]);
  const [code, setCode] = useState(""); const [granted, setGranted] = useState<Set<string>>(new Set()); const [err, setErr] = useState(""); const [dlg, setDlg] = useState(false);
  useEffect(() => { api("/roles").then(setRoles); api("/permissions").then(setPerms); }, []);
  const pick = async (c: string) => { setCode(c); setErr(""); if (c) { const r = await api(`/roles/${c}`); setGranted(new Set(r.permissions)); } };
  const mods = Array.from(new Set(perms.map((p) => p.module)));
  const toggle = (c: string) => { const n = new Set(granted); n.has(c) ? n.delete(c) : n.add(c); setGranted(n); };
  return (
    <>
      <PageHeader title="Roles & Permissions" crumbs={["Administration", "Roles"]} />
      <Alert>{err}</Alert>
      <select className="form-select mb-3" style={{ maxWidth: 360 }} value={code} onChange={(e) => pick(e.target.value)}>
        <option value="">Select role…</option>{roles.map((r) => <option key={r.role_code} value={r.role_code}>{r.name}{r.is_admin_role ? " (admin)" : ""}</option>)}</select>
      {code && <>
        <div className="row g-3">{mods.map((m) => (
          <div className="col-md-6 col-xl-4" key={m}><div className="card"><div className="card-header py-1 text-uppercase small">{m}</div>
            <div className="card-body py-2">{perms.filter((p) => p.module === m).map((p) => (
              <div className="form-check" key={p.perm_code}><input className="form-check-input" type="checkbox" id={p.perm_code} disabled={!can("iam.role.update")}
                checked={granted.has(p.perm_code)} onChange={() => toggle(p.perm_code)} /><label className="form-check-label small" htmlFor={p.perm_code}>{p.resource}.{p.action}</label></div>))}</div></div></div>))}</div>
        {can("iam.role.update") && <button className="btn btn-primary mt-3" onClick={() => setDlg(true)}>Save permissions</button>}
      </>}
      {dlg && <ReasonDialog title={`Change permissions of ${code}`} onClose={() => setDlg(false)}
        onSubmit={async (reason) => { try { await api(`/roles/${code}/permissions`, { method: "PUT", body: { permissions: Array.from(granted), reason } }); } catch (e) { throw new Error(errText(e)); } }} />}
    </>
  );
}
