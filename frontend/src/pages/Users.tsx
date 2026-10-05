import { useCallback, useEffect, useState } from "react";
import { Alert, Modal, PageHeader, ReasonDialog, StatusBadge, fmt } from "../components/ui";
import { useAuth } from "../hooks/useAuth";
import { api, errText } from "../services/api";

export default function Users() {
  const { can } = useAuth();
  const [q, setQ] = useState(""); const [offset, setOffset] = useState(0); const [data, setData] = useState<any>({ items: [], total: 0 });
  const [err, setErr] = useState(""); const [sel, setSel] = useState<any>(null); const [creating, setCreating] = useState(false);
  const [secret, setSecret] = useState<string | null>(null);
  const limit = 25;
  const load = useCallback(() => api(`/users?q=${encodeURIComponent(q)}&limit=${limit}&offset=${offset}`).then(setData).catch((e) => setErr(errText(e))), [q, offset]);
  useEffect(() => { load(); }, [load]);
  return (
    <>
      <PageHeader title="Users" crumbs={["Administration", "Users"]}
        actions={can("iam.user.create") && <button className="btn btn-primary" onClick={() => setCreating(true)}><i className="bi bi-plus-lg" /> New user</button>} />
      <Alert>{err}</Alert>
      <input className="form-control mb-2" style={{ maxWidth: 320 }} placeholder="Search user ID or name…" value={q} onChange={(e) => { setOffset(0); setQ(e.target.value); }} />
      <table className="table table-sm table-hover bg-white">
        <thead><tr><th>User ID</th><th>Name</th><th>Source</th><th>Status</th><th>Last login</th><th>Access expiry</th></tr></thead>
        <tbody>{data.items.map((u: any) => (
          <tr key={u.id} role="button" onClick={() => setSel(u)}>
            <td>{u.username}</td><td>{u.full_name}</td><td>{u.auth_source}</td>
            <td><StatusBadge status={u.locked_until && new Date(u.locked_until) > new Date() ? "LOCKED" : u.is_active ? "ACTIVE" : "INACTIVE"} /></td>
            <td>{fmt(u.last_login_at)}</td><td>{u.access_expiry ?? "—"}</td></tr>))}</tbody>
      </table>
      <div className="d-flex justify-content-between small">
        <span>{data.total} users</span>
        <div className="btn-group btn-group-sm">
          <button className="btn btn-outline-secondary" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - limit))}>Prev</button>
          <button className="btn btn-outline-secondary" disabled={offset + limit >= data.total} onClick={() => setOffset(offset + limit)}>Next</button>
        </div>
      </div>
      {creating && <CreateUser onClose={() => setCreating(false)} onDone={(pw) => { setCreating(false); setSecret(pw); load(); }} />}
      {sel && <UserDetail id={sel.id} onClose={() => { setSel(null); load(); }} onSecret={setSecret} />}
      {secret && <Modal title="Temporary password" onClose={() => setSecret(null)}>
        <p>Give this to the user securely. It is shown <b>once</b>; they must change it at first login.</p>
        <div className="mono p-2 bg-light border">{secret}</div></Modal>}
    </>
  );
}

function CreateUser({ onClose, onDone }: { onClose: () => void; onDone: (pw: string | null) => void }) {
  const [f, setF] = useState<any>({ username: "", full_name: "", email: "", designation: "", auth_source: "LOCAL", reason: "" });
  const [err, setErr] = useState("");
  const set = (k: string) => (e: any) => setF({ ...f, [k]: e.target.value });
  const save = async () => {
    try { const r = await api("/users", { method: "POST", body: { ...f, email: f.email || null, designation: f.designation || null } }); onDone(r.temporary_password); }
    catch (e) { setErr(errText(e)); }
  };
  return (
    <Modal title="New user" onClose={onClose} footer={<><button className="btn btn-outline-secondary" onClick={onClose}>Cancel</button><button className="btn btn-primary" onClick={save}>Create</button></>}>
      <Alert>{err}</Alert>
      {[["username", "User ID"], ["full_name", "Full name"], ["email", "Email"], ["designation", "Designation"]].map(([k, l]) => (
        <div className="mb-2" key={k}><label className="form-label">{l}</label><input className="form-control" value={f[k]} onChange={set(k)} /></div>))}
      <div className="mb-2"><label className="form-label">Authentication</label>
        <select className="form-select" value={f.auth_source} onChange={set("auth_source")}><option value="LOCAL">Local</option><option value="LDAP">Active Directory / LDAP</option></select></div>
      <div className="mb-2"><label className="form-label">Reason *</label><input className="form-control" value={f.reason} onChange={set("reason")} /></div>
    </Modal>
  );
}

function UserDetail({ id, onClose, onSecret }: { id: number; onClose: () => void; onSecret: (s: string) => void }) {
  const { can } = useAuth();
  const [d, setD] = useState<any>(null); const [roles, setRoles] = useState<any[]>([]); const [err, setErr] = useState("");
  const [dlg, setDlg] = useState<null | { title: string; run: (reason: string) => Promise<void> }>(null); const [newRole, setNewRole] = useState("");
  const load = useCallback(() => { api(`/users/${id}`).then(setD).catch((e) => setErr(errText(e))); }, [id]);
  useEffect(() => { load(); if (can("iam.role.read")) api("/roles").then(setRoles); }, [load]);
  const ask = (title: string, run: (reason: string) => Promise<void>) => setDlg({ title, run });
  if (!d) return <Modal title="User" onClose={onClose}><Alert>{err}</Alert>Loading…</Modal>;
  const u = d.user;
  return (
    <Modal title={`${u.username} — ${u.full_name}`} onClose={onClose}>
      <Alert>{err}</Alert>
      <dl className="row small mb-2">
        <dt className="col-4">Source</dt><dd className="col-8">{u.auth_source}</dd>
        <dt className="col-4">Status</dt><dd className="col-8"><StatusBadge status={u.is_active ? "ACTIVE" : "INACTIVE"} /></dd>
        <dt className="col-4">Access expiry</dt><dd className="col-8">{u.access_expiry ?? "—"}</dd>
      </dl>
      <h6>Roles</h6>
      <ul className="list-group mb-2">{d.roles.map((r: any) => (
        <li className="list-group-item d-flex justify-content-between align-items-center py-1" key={r.role_code}>
          <span>{r.name} <span className="text-muted small">{r.valid_to ? `until ${r.valid_to}` : ""}</span></span>
          {can("iam.user.assign_role") && <button className="btn btn-sm btn-outline-danger" onClick={() => ask(`Remove role ${r.name}`, async (reason) => {
            await api(`/users/${id}/roles/${r.role_code}`, { method: "DELETE", body: { reason } }); load(); })}>Remove</button>}
        </li>))}</ul>
      {can("iam.user.assign_role") && <div className="input-group mb-3">
        <select className="form-select" value={newRole} onChange={(e) => setNewRole(e.target.value)}><option value="">Assign role…</option>
          {roles.filter((r) => !d.roles.find((x: any) => x.role_code === r.role_code)).map((r) => <option key={r.role_code} value={r.role_code}>{r.name}</option>)}</select>
        <button className="btn btn-outline-primary" disabled={!newRole} onClick={() => ask(`Assign ${newRole}`, async (reason) => {
          await api(`/users/${id}/roles`, { method: "POST", body: { role_code: newRole, reason } }); setNewRole(""); load(); })}>Assign</button></div>}
      <div className="d-flex flex-wrap gap-2">
        {can("iam.user.deactivate") && <button className="btn btn-sm btn-outline-warning" onClick={() => ask(u.is_active ? "Deactivate user" : "Activate user", async (reason) => {
          await api(`/users/${id}/active`, { method: "POST", body: { active: !u.is_active, reason } }); load(); })}>{u.is_active ? "Deactivate" : "Activate"}</button>}
        {can("iam.user.update") && <button className="btn btn-sm btn-outline-secondary" onClick={() => ask("Unlock account", async (reason) => { await api(`/users/${id}/unlock`, { method: "POST", body: { reason } }); load(); })}>Unlock</button>}
        {can("iam.user.reset_password") && u.auth_source === "LOCAL" && <button className="btn btn-sm btn-outline-danger" onClick={() => ask("Reset password", async (reason) => {
          const r = await api(`/users/${id}/reset-password`, { method: "POST", body: { reason } }); onSecret(r.temporary_password); })}>Reset password</button>}
      </div>
      {dlg && <ReasonDialog title={dlg.title} onClose={() => setDlg(null)} onSubmit={async (reason) => { try { await dlg.run(reason); } catch (e) { throw new Error(errText(e)); } }} />}
    </Modal>
  );
}
