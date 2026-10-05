import { useEffect, useMemo, useState } from "react";
import { Alert, Modal, PageHeader, StatusBadge } from "../components/ui";
import { useAuth } from "../hooks/useAuth";
import { api, errText } from "../services/api";

export async function downloadFile(path: string, fallbackName: string, open = false) {
  const res: any = await api(path, { raw: true });
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  if (open) { window.open(url, "_blank"); return res.headers.get("X-Controlled-Copy"); }
  const a = document.createElement("a");
  a.href = url; a.download = fallbackName; document.body.appendChild(a); a.click(); a.remove();
  return res.headers.get("X-Controlled-Copy");
}

export function PrintButton({ path, label = "Print PDF" }: { path: string; label?: string }) {
  const [copy, setCopy] = useState<string | null>(null); const [err, setErr] = useState("");
  return (<span><button className="btn btn-sm btn-outline-secondary" onClick={async () => { try { setCopy(await downloadFile(path, "document.pdf", true)); setErr(""); } catch (e) { setErr(errText(e)); } }}><i className="bi bi-printer" /> {label}</button>
    {copy && <span className="small text-muted ms-2">controlled copy {copy}</span>}{err && <span className="small text-danger ms-2">{err}</span>}</span>);
}

/* ------------------------------------------------------------------ Reports */
export function Reports() {
  const { can } = useAuth();
  const [cat, setCat] = useState<any[]>([]); const [sel, setSel] = useState<any>(null); const [vals, setVals] = useState<Record<string, string>>({}); const [res, setRes] = useState<any>(null); const [err, setErr] = useState(""); const [copy, setCopy] = useState("");
  useEffect(() => { api("/reports").then(setCat).catch((e) => setErr(errText(e))); }, []);
  const groups = useMemo(() => cat.reduce<Record<string, any[]>>((m, r) => ((m[r.group] ||= []).push(r), m), {}), [cat]);
  const qs = () => new URLSearchParams(Object.entries(vals).filter(([, v]) => v)).toString();
  const run = async () => { try { setRes(await api(`/reports/${sel.code}?${qs()}`)); setErr(""); } catch (e) { setRes(null); setErr(errText(e)); } };
  const exp = async (fmt: string) => { try { setCopy((await downloadFile(`/reports/${sel.code}/export?format=${fmt}&${qs()}`, `${sel.code}.${fmt}`, fmt === "pdf")) || ""); setErr(""); } catch (e) { setErr(errText(e)); } };
  return (<>
    <PageHeader title="Reports" crumbs={["Reports"]} />
    <div className="row g-3">
      <div className="col-md-3">{Object.entries(groups).map(([g, list]) => (<div key={g} className="mb-3"><div className="fw-bold small text-uppercase text-muted">{g}</div>
        <div className="list-group">{list.map((r) => <button key={r.code} className={"list-group-item list-group-item-action py-1 small" + (sel?.code === r.code ? " active" : "")} onClick={() => { setSel(r); setVals({}); setRes(null); setCopy(""); }}>{r.title}</button>)}</div></div>))}
        {cat.length === 0 && <div className="text-muted small">No reports are available for your role.</div>}</div>
      <div className="col-md-9">{sel && (<div className="card"><div className="card-body">
        <h5>{sel.title}</h5>
        <Alert>{err}</Alert>
        <div className="row g-2 mb-2">{sel.params.map((p: any) => (<div className="col-md-3" key={p.name}><label className="form-label small mb-0">{p.label}{p.required && " *"}</label>
          {p.type === "select" ? <select className="form-select form-select-sm" value={vals[p.name] ?? ""} onChange={(e) => setVals({ ...vals, [p.name]: e.target.value })}><option value="">any</option>{p.options.map((o: string) => <option key={o}>{o}</option>)}</select>
            : <input type={p.type === "date" ? "date" : p.type === "int" ? "number" : "text"} className="form-control form-control-sm" value={vals[p.name] ?? ""} onChange={(e) => setVals({ ...vals, [p.name]: e.target.value })} />}</div>))}</div>
        <div className="d-flex gap-2 mb-2"><button className="btn btn-primary btn-sm" onClick={run}><i className="bi bi-play-fill" /> Run</button>
          {can("reports.export.run") && ["xlsx", "csv", "pdf"].map((f) => <button key={f} className="btn btn-outline-secondary btn-sm" onClick={() => exp(f)}><i className="bi bi-download" /> {f.toUpperCase()}</button>)}
          {copy && <span className="small text-muted align-self-center">controlled copy <b>{copy}</b></span>}</div>
        {res && <><div className="small text-muted mb-1">{res.count} record(s){res.truncated && " (preview truncated — export for the full set)"}</div>
          <div style={{ overflow: "auto", maxHeight: 520 }}><table className="table table-sm table-striped small"><thead className="sticky-top bg-white"><tr>{res.columns.map((c: any) => <th key={c.key}>{c.label}</th>)}</tr></thead>
            <tbody>{res.rows.map((r: any, i: number) => <tr key={i}>{res.columns.map((c: any) => <td key={c.key}>{r[c.key] === true ? "Yes" : r[c.key] === false ? "No" : String(r[c.key] ?? "")}</td>)}</tr>)}</tbody></table></div></>}
      </div></div>)}</div>
    </div></>);
}

/* ------------------------------------------------------------------ Dashboards */
function Bars({ title, data }: { title: string; data: { label: string; value: number }[] }) {
  const max = Math.max(1, ...data.map((d) => d.value));
  return (<div className="card h-100"><div className="card-body"><div className="small fw-bold mb-2">{title.replace(/_/g, " ")}</div>
    {data.length === 0 && <div className="text-muted small">No data</div>}
    {data.map((d) => (<div key={d.label} className="d-flex align-items-center small mb-1"><div style={{ width: 130 }} className="text-truncate">{d.label}</div>
      <div className="flex-grow-1 bg-light rounded" style={{ height: 14 }}><div className="rounded bg-primary" style={{ width: `${(d.value / max) * 100}%`, height: 14 }} /></div><div style={{ width: 50 }} className="text-end">{d.value}</div></div>))}</div></div>);
}

export function Dashboards() {
  const [names, setNames] = useState<string[]>([]); const [tab, setTab] = useState(""); const [d, setD] = useState<any>(null); const [err, setErr] = useState("");
  useEffect(() => { api("/dashboards").then((n) => { setNames(n); setTab(n[0] || ""); }).catch((e) => setErr(errText(e))); }, []);
  useEffect(() => { if (tab) api(`/dashboards/${tab}`).then(setD).catch((e) => setErr(errText(e))); }, [tab]);
  const tone: Record<string, string> = { danger: "border-danger", warn: "border-warning", "": "" };
  return (<>
    <PageHeader title="Dashboards" crumbs={["Reports", "Dashboards"]} /><Alert>{err}</Alert>
    <ul className="nav nav-tabs mb-3">{names.map((n) => <li className="nav-item" key={n}><button className={"nav-link" + (tab === n ? " active" : "")} onClick={() => setTab(n)}>{({ management: "Management", qc: "QC", qa: "QA", warehouse: "Warehouse" } as Record<string, string>)[n] ?? n}</button></li>)}</ul>
    {d && <><div className="row g-3 mb-3">{d.cards.map((c: any) => (<div className="col-6 col-md-4 col-xl-3" key={c.label}><div className={`card card-metric h-100 border-2 ${tone[c.tone] ?? ""}`}><div className="card-body"><div className="text-muted small">{c.label}</div><div className="value">{c.value}</div></div></div></div>))}</div>
      <div className="row g-3">{Object.entries<any[]>(d.series).map(([k, v]) => <div className="col-md-4" key={k}><Bars title={k} data={v} /></div>)}</div></>}
  </>);
}

/* ------------------------------------------------------------------ Compliance admin: retention, backup, controlled copies */
export function Compliance() {
  const { can } = useAuth(); const [tab, setTab] = useState("backup");
  return (<>
    <PageHeader title="Retention, backup and controlled copies" crumbs={["Administration", "Compliance"]} />
    <ul className="nav nav-tabs mb-3">{[["backup", "Backup status"], ["retention", "Retention & archive"], ["runs", "Controlled copies"]].map(([k, l]) => <li className="nav-item" key={k}><button className={"nav-link" + (tab === k ? " active" : "")} onClick={() => setTab(k)}>{l}</button></li>)}</ul>
    {tab === "backup" && <BackupPanel canRecord={can("backup.status.record")} />}
    {tab === "retention" && <RetentionPanel />}
    {tab === "runs" && <RunsPanel />}
  </>);
}

function BackupPanel({ canRecord }: { canRecord: boolean }) {
  const [st, setSt] = useState<any>(null); const [err, setErr] = useState(""); const [adding, setAdding] = useState(false); const [f, setF] = useState<any>({ backup_type: "FULL", result: "SUCCESS" });
  const load = () => api("/backup/status").then(setSt).catch((e) => setErr(errText(e)));
  useEffect(() => { load(); }, []);
  const save = async () => { try { await api("/backup/records", { method: "POST", body: { ...f, performed_at: f.performed_at ? new Date(f.performed_at).toISOString() : new Date().toISOString(), size_mb: f.size_mb ? Number(f.size_mb) : null, rto_minutes: f.rto_minutes ? Number(f.rto_minutes) : null } }); setAdding(false); load(); } catch (e) { setErr(errText(e)); } };
  const row = (l: string, x: any) => <tr key={l}><td>{l}</td><td>{x ? new Date(x.performed_at).toLocaleString() : "—"}</td><td>{x?.location ?? ""}</td><td>{x?.size_mb ?? ""}</td><td>{x?.rto_minutes != null ? `RTO ${x.rto_minutes} min` : ""} {x?.audit_chain_verified ? "· audit chain verified" : ""}</td></tr>;
  return (<>
    <Alert>{err}</Alert>
    {st && <><div className={"alert " + (st.ok ? "alert-success" : "alert-danger")}>{st.ok ? "Backups and restore evidence are within policy." : st.alerts.map((a: string) => <div key={a}>{a}</div>)}</div>
      <table className="table table-sm"><thead><tr><th>Evidence</th><th>When</th><th>Location</th><th>MB</th><th>Notes</th></tr></thead><tbody>{row("Last full", st.last_full)}{row("Last differential", st.last_differential)}{row("Last log", st.last_log)}{row("Last documents", st.last_documents)}{row("Last restore test", st.last_restore_test)}</tbody></table>
      <div className="small text-muted mb-2">This page records evidence; backups themselves are executed by the site's backup tooling (see the Administrator manual). Limit: newest successful backup ≤ {st.max_age_hours} h.</div>
      {canRecord && <button className="btn btn-primary btn-sm" onClick={() => setAdding(true)}>Record backup / restore test</button>}</>}
    {adding && <Modal title="Record backup evidence" onClose={() => setAdding(false)} footer={<button className="btn btn-primary" onClick={save}>Save (append-only)</button>}>
      <select className="form-select mb-2" value={f.backup_type} onChange={(e) => setF({ ...f, backup_type: e.target.value })}>{["FULL", "DIFFERENTIAL", "LOG", "DOCUMENTS", "RESTORE_TEST"].map((t) => <option key={t}>{t}</option>)}</select>
      <input type="datetime-local" className="form-control mb-2" onChange={(e) => setF({ ...f, performed_at: e.target.value })} />
      <select className="form-select mb-2" value={f.result} onChange={(e) => setF({ ...f, result: e.target.value })}><option>SUCCESS</option><option>FAILED</option></select>
      {["location", "size_mb", "tool", "sha256", "rto_minutes", "notes"].map((k) => <input key={k} className="form-control mb-2" placeholder={k} onChange={(e) => setF({ ...f, [k]: e.target.value || null })} />)}
      <label className="small"><input type="checkbox" onChange={(e) => setF({ ...f, audit_chain_verified: e.target.checked })} /> Audit-trail hash chain verified on the restored copy</label></Modal>}
  </>);
}

function RetentionPanel() {
  const { can } = useAuth(); const [pol, setPol] = useState<any[]>([]); const [arch, setArch] = useState<any[]>([]); const [err, setErr] = useState("");
  const load = () => { api("/retention/policies").then(setPol).catch((e) => setErr(errText(e))); api("/retention/archives").then(setArch).catch(() => {}); };
  useEffect(() => { load(); }, []);
  return (<><Alert>{err}</Alert>
    <div className="alert alert-info small">The application never deletes GMP records. Archive packages are hashed copies of records older than their retention period; legal hold freezes a record type.</div>
    <table className="table table-sm small"><thead><tr><th>Record type</th><th>Years</th><th>Cut-off</th><th>Total</th><th>Eligible</th><th>Archived rows</th><th>Hold</th><th>Basis</th><th /></tr></thead>
      <tbody>{pol.map((p) => (<tr key={p.id}><td>{p.label}</td><td>{p.retention_years}</td><td>{p.cutoff}</td><td>{p.total_records}</td><td>{p.eligible_for_archive}</td><td>{p.archived_rows}</td><td>{p.legal_hold ? <StatusBadge status="HOLD" /> : ""}</td><td className="text-muted">{p.basis}</td>
        <td className="text-nowrap">{can("retention.archive.create") && p.eligible_for_archive > 0 && <button className="btn btn-sm btn-outline-primary me-1" onClick={async () => { try { await api(`/retention/archive/${p.record_type}`, { method: "POST" }); setErr(""); load(); } catch (e) { setErr(errText(e)); } }}>Archive</button>}
          {can("retention.policy.update") && <button className="btn btn-sm btn-outline-secondary" onClick={async () => { const y = prompt("Retention years (can only be extended)", String(p.retention_years)); if (!y) return; try { await api(`/retention/policies/${p.id}`, { method: "PATCH", body: { retention_years: Number(y), reason: "Retention period extended" } }); setErr(""); load(); } catch (e) { setErr(errText(e)); } }}>Extend</button>}
          {can("retention.policy.update") && <button className="btn btn-sm btn-outline-warning ms-1" onClick={async () => { const why = p.legal_hold ? "Legal hold released" : prompt("Legal hold reason"); if (!why) return; try { await api(`/retention/policies/${p.id}`, { method: "PATCH", body: { legal_hold: !p.legal_hold, legal_hold_reason: p.legal_hold ? null : why, reason: why } }); setErr(""); load(); } catch (e) { setErr(errText(e)); } }}>{p.legal_hold ? "Release hold" : "Legal hold"}</button>}</td></tr>))}</tbody></table>
    <h6>Archive packages</h6>
    <table className="table table-sm small"><tbody>{arch.map((a) => <tr key={a.id}><td>{a.archive_no}</td><td>{a.record_type}</td><td>{a.row_count} rows</td><td className="text-muted">sha256 {a.sha256.slice(0, 16)}…</td><td><button className="btn btn-link btn-sm p-0" onClick={() => downloadFile(`/retention/archives/${a.id}/download`, `${a.archive_no}.xlsx`)}>Download (verified)</button></td></tr>)}</tbody></table></>);
}

function RunsPanel() {
  const [rows, setRows] = useState<any[]>([]); const [v, setV] = useState<any>({}); const [res, setRes] = useState<any>(null); const [err, setErr] = useState("");
  useEffect(() => { api("/report-runs?limit=100").then((r) => setRows(r.items)).catch((e) => setErr(errText(e))); }, []);
  return (<><Alert>{err}</Alert>
    <div className="card mb-3"><div className="card-body"><div className="fw-bold small mb-2">Verify a printout</div><div className="d-flex gap-2"><input className="form-control form-control-sm" placeholder="Controlled copy no. (RPT-…)" onChange={(e) => setV({ ...v, c: e.target.value })} />
      <input className="form-control form-control-sm" placeholder="SHA-256 of the file" onChange={(e) => setV({ ...v, h: e.target.value })} />
      <button className="btn btn-sm btn-primary" onClick={async () => { try { setRes(await api(`/reports-verify?copy_no=${encodeURIComponent(v.c)}&sha256=${encodeURIComponent(v.h)}`)); setErr(""); } catch (e) { setRes(null); setErr(errText(e)); } }}>Verify</button></div>
      {res && <div className={"mt-2 alert py-1 " + (res.matches ? "alert-success" : "alert-danger")}>{res.matches ? "Genuine copy" : "HASH DOES NOT MATCH"} — {res.report}, printed by {res.printed_by} at {res.run_at}</div>}</div></div>
    <table className="table table-sm small"><thead><tr><th>Copy no.</th><th>Report</th><th>Format</th><th>Rows</th><th>User</th><th>When (UTC)</th></tr></thead><tbody>{rows.map((r) => <tr key={r.id}><td>{r.copy_no}</td><td>{r.title}</td><td>{r.output_format}</td><td>{r.row_count ?? ""}</td><td>{r.username}</td><td>{r.run_at}</td></tr>)}</tbody></table></>);
}
