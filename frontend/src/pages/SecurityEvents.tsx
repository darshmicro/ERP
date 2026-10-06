import { useEffect, useState } from "react";
import { Alert, PageHeader, fmt } from "../components/ui";
import { api, errText } from "../services/api";

export default function SecurityEvents() {
  const [rows, setRows] = useState<any[]>([]); const [t, setT] = useState(""); const [err, setErr] = useState("");
  const load = () => api(`/security-events${t ? `?event_type=${t}` : ""}`).then((r) => setRows(r.items)).catch((e) => setErr(errText(e)));
  useEffect(() => { load(); }, []);
  return (<>
    <PageHeader title="Security Events" crumbs={["Quality", "Security log"]} />
    <Alert>{err}</Alert>
    <div className="input-group mb-2" style={{ maxWidth: 420 }}>
      <select className="form-select" value={t} onChange={(e) => setT(e.target.value)}><option value="">All events</option>
        {["LOGIN_FAILED", "LOGIN_REJECTED", "ACCOUNT_LOCKED", "AUTHZ_DENIED", "SOD_VIOLATION", "CSRF_REJECTED", "RATE_LIMITED"].map((x) => <option key={x}>{x}</option>)}</select>
      <button className="btn btn-primary" onClick={load}>Filter</button></div>
    <table className="table table-sm table-striped bg-white"><thead><tr><th>When</th><th>Event</th><th>User</th><th>IP</th><th>Detail</th></tr></thead>
      <tbody>{rows.map((r) => <tr key={r.id}><td>{fmt(r.occurred_at)}</td><td>{r.event_type}</td><td>{r.username}</td><td>{r.ip_address}</td><td>{r.detail}</td></tr>)}</tbody></table>
  </>);
}
