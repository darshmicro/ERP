import { FormEvent, useState } from "react";
import { useAuth } from "../hooks/useAuth";
import { Alert } from "../components/ui";
import { errText } from "../services/api";

export default function Login() {
  const { login, branding } = useAuth();
  const [u, setU] = useState(""); const [p, setP] = useState(""); const [err, setErr] = useState(""); const [busy, setBusy] = useState(false);
  const submit = async (e: FormEvent) => {
    e.preventDefault(); setBusy(true); setErr("");
    try { await login(u, p); } catch (x) { setErr(errText(x)); } finally { setBusy(false); }
  };
  return (
    <div className="min-vh-100 d-flex align-items-center justify-content-center bg-body-tertiary">
      <form className="card shadow-sm p-4" style={{ width: 380 }} onSubmit={submit}>
        <div className="text-center mb-3">
          {branding.logo_url && <img src={branding.logo_url} alt="logo" style={{ maxHeight: 64 }} className="mb-2" />}
          <h5 className="mb-0">{branding.name}</h5>
          <div className="text-muted small">{branding.app_display_name}</div>
        </div>
        <Alert>{err}</Alert>
        <label className="form-label">User ID</label>
        <input className="form-control mb-2" autoFocus autoComplete="username" value={u} onChange={(e) => setU(e.target.value)} />
        <label className="form-label">Password</label>
        <input className="form-control mb-3" type="password" autoComplete="current-password" value={p} onChange={(e) => setP(e.target.value)} />
        <button className="btn btn-primary" disabled={busy || !u || !p}>Log in</button>
        <div className="small text-muted mt-3">Authorised users only. Activity is recorded in the audit trail.</div>
      </form>
    </div>
  );
}
