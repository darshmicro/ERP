import { FormEvent, useState } from "react";
import { useAuth } from "../hooks/useAuth";
import { Alert, PageHeader } from "../components/ui";
import { api, errText, setCsrf } from "../services/api";

export default function ChangePassword({ forced = false }: { forced?: boolean }) {
  const { refresh, logout } = useAuth();
  const [cur, setCur] = useState(""); const [nw, setNw] = useState(""); const [nw2, setNw2] = useState("");
  const [err, setErr] = useState(""); const [done, setDone] = useState(false);
  const submit = async (e: FormEvent) => {
    e.preventDefault(); setErr("");
    if (nw !== nw2) return setErr("New passwords do not match.");
    try {
      await api("/auth/change-password", { method: "POST", body: { current_password: cur, new_password: nw } });
      setCsrf(null); setDone(true); await refresh();
    } catch (x) { setErr(errText(x)); }
  };
  const body = (
    <form onSubmit={submit} className="card p-4" style={{ maxWidth: 420 }}>
      {forced && <Alert kind="warning">You must set a new password before continuing.</Alert>}
      <Alert>{err}</Alert>
      {done && <Alert kind="success">Password changed. Please log in again.</Alert>}
      <label className="form-label">Current password</label>
      <input type="password" className="form-control mb-2" value={cur} onChange={(e) => setCur(e.target.value)} autoComplete="current-password" />
      <label className="form-label">New password</label>
      <input type="password" className="form-control mb-2" value={nw} onChange={(e) => setNw(e.target.value)} autoComplete="new-password" />
      <label className="form-label">Repeat new password</label>
      <input type="password" className="form-control mb-2" value={nw2} onChange={(e) => setNw2(e.target.value)} autoComplete="new-password" />
      <div className="form-text mb-3">At least 12 characters with upper/lower case, a digit and a symbol; not reused from recent passwords.</div>
      <div className="d-flex gap-2"><button className="btn btn-primary">Change password</button>
        {forced && <button type="button" className="btn btn-outline-secondary" onClick={logout}>Log out</button>}</div>
    </form>
  );
  return forced ? <div className="min-vh-100 d-flex align-items-center justify-content-center bg-body-tertiary">{body}</div>
    : <><PageHeader title="Change password" crumbs={["Account"]} />{body}</>;
}
