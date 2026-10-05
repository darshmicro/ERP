import { useEffect, useState } from "react";
import { DataList, FormModal, useLookup } from "../components/DataList";
import { Alert, Modal, PageHeader, ReasonDialog, StatusBadge } from "../components/ui";
import { useAuth } from "../hooks/useAuth";
import { api, errText } from "../services/api";

export default function VendorQualification() {
  const { can } = useAuth();
  const vendors = useLookup("/vendors?approval_status=APPROVED", "name", "id", "vendor_code");
  const [tab, setTab] = useState("list"); const [sel, setSel] = useState<number | null>(null); const [reload, setReload] = useState<() => void>(() => () => {});
  return (<>
    <ul className="nav nav-tabs mb-3">{[["list", "Qualifications"], ["expiry", "Expiry report"]].map(([k, l]) => (<li className="nav-item" key={k}><button className={"nav-link" + (tab === k ? " active" : "")} onClick={() => setTab(k)}>{l}</button></li>))}</ul>
    {tab === "list" ? <DataList title="Vendor Qualification" crumbs={["Purchase", "Vendor qualification"]} path="/vendor-qualifications" canCreate={can("vq.qualification.create")}
        fields={[{ key: "vendor_id", label: "Vendor", type: "select", options: vendors, required: true }, { key: "qualified_on", label: "Qualified on", type: "date" },
          { key: "requalification_due_date", label: "Requalification due", type: "date" }, { key: "risk_class", label: "Risk class (blank = vendor's)", type: "select", options: ["CRITICAL", "HIGH", "MEDIUM", "LOW"].map((x) => ({ value: x, label: x })) },
          { key: "basis", label: "Basis (audit / questionnaire summary)", type: "textarea" }, { key: "audit_report_ref", label: "Audit report ref." },
          { key: "change_reason", label: "Change reason (required for requalification)" }]}
        filters={[{ key: "status", label: "Status", options: ["DRAFT", "UNDER_REVIEW", "APPROVED", "CONDITIONAL", "SUSPENDED", "EXPIRED", "DISQUALIFIED", "SUPERSEDED"] }]}
        cols={[{ key: "qualification_no", label: "No." }, { key: "version_no", label: "Ver" }, { key: "vendor_code", label: "Vendor", render: (r) => `${r.vendor_code} ${r.vendor_name}` },
          { key: "risk_class", label: "Risk" }, { key: "requalification_due_date", label: "Due", render: (r) => <span className={r.days_to_due != null && r.days_to_due < 0 ? "text-danger fw-bold" : r.days_to_due != null && r.days_to_due < 60 ? "text-warning fw-bold" : ""}>{r.requalification_due_date ?? "—"}</span> },
          { key: "effective_status", label: "Status", badge: true }]}
        onRow={(r, load) => { setSel(r.id); setReload(() => load); }} /> : <Expiry />}
    {sel && <VQDetail id={sel} onClose={() => { setSel(null); reload(); }} onOpen={setSel} />}
  </>);
}

function Expiry() {
  const [rows, setRows] = useState<any[]>([]); const [days, setDays] = useState(90);
  useEffect(() => { api(`/vendor-qualifications/expiry-report?within_days=${days}`).then(setRows); }, [days]);
  return (<>
    <PageHeader title="Vendor Qualification Expiry" crumbs={["Purchase", "Expiry report"]} actions={<a className="btn btn-outline-primary" href={`/api/v1/vendor-qualifications/expiry-report/export?within_days=${days}`}><i className="bi bi-file-earmark-excel" /> Excel</a>} />
    <div className="mb-2"><select className="form-select" style={{ maxWidth: 220 }} value={days} onChange={(e) => setDays(Number(e.target.value))}>{[30, 60, 90, 180, 365].map((d) => <option key={d} value={d}>Due within {d} days</option>)}</select></div>
    <table className="table table-sm bg-white"><thead><tr><th>Vendor</th><th>Risk</th><th>Status</th><th>Due</th><th>Days</th><th>Purchasable</th></tr></thead>
      <tbody>{rows.map((r) => (<tr key={r.vendor_id} className={r.purchasable ? "" : "table-danger"}><td>{r.vendor_code} {r.vendor}</td><td>{r.risk_class}</td><td><StatusBadge status={r.status} /></td><td>{r.due ?? "—"}</td><td>{r.days_to_due ?? "—"}</td><td>{r.purchasable ? "Yes" : <b>BLOCKED</b>}</td></tr>))}</tbody></table>
  </>);
}

function VQDetail({ id, onClose, onOpen }: { id: number; onClose: () => void; onOpen: (id: number) => void }) {
  const { can } = useAuth();
  const [q, setQ] = useState<any>(null); const [err, setErr] = useState(""); const [act, setAct] = useState<null | { title: string; path: string; sign: boolean; extra?: any }>(null); const [edit, setEdit] = useState(false);
  const load = () => api(`/vendor-qualifications/${id}`).then(setQ).catch((e) => setErr(errText(e)));
  useEffect(() => { load(); }, [id]);
  if (!q) return <Modal title="Qualification" onClose={onClose}><Alert>{err}</Alert>Loading…</Modal>;
  const st = q.effective_status;
  const call = async (path: string) => { try { await api(`/vendor-qualifications/${id}/${path}`, { method: "POST" }); setErr(""); load(); } catch (e) { setErr(errText(e)); } };
  return (<Modal title={`${q.qualification_no} v${q.version_no} — ${q.vendor_name}`} onClose={onClose}>
    <Alert>{err}</Alert>
    {st === "EXPIRED" && <Alert>PURCHASE BLOCKED — VENDOR QUALIFICATION EXPIRED. Start a requalification to restore purchasing.</Alert>}
    <div className="mb-2"><StatusBadge status={st} /> risk <b>{q.risk_class}</b> · qualified {q.qualified_on ?? "—"} · requalification due <b>{q.requalification_due_date ?? "—"}</b> {q.days_to_due != null && `(${q.days_to_due} d)`}</div>
    {q.status_reason && <div className="small">Reason: {q.status_reason}</div>}
    {q.basis && <div className="small mb-2" style={{ whiteSpace: "pre-wrap" }}>{q.basis}</div>}
    {q.document_gaps.length > 0 && <Alert kind="warning">Required documents not satisfied: {q.document_gaps.join("; ")}</Alert>}
    <div className="small mb-2">Versions: {q.versions.map((v: any) => <a key={v.id} href="#" className="me-2" onClick={(e) => { e.preventDefault(); onOpen(v.id); }}>v{v.version_no} <StatusBadge status={v.status} /></a>)}</div>
    <div className="d-flex gap-2 flex-wrap">
      {q.status === "DRAFT" && can("vq.qualification.update") && <><button className="btn btn-sm btn-outline-secondary" onClick={() => setEdit(true)}>Edit</button><button className="btn btn-sm btn-primary" onClick={() => call("submit")}>Submit for QA approval</button></>}
      {q.status === "UNDER_REVIEW" && can("vq.qualification.approve") && <>
        <button className="btn btn-sm btn-success" onClick={() => setAct({ title: "Approve qualification", path: "approve", sign: true, extra: { conditional: false } })}><i className="bi bi-pen" /> Approve</button>
        <button className="btn btn-sm btn-warning" onClick={() => setAct({ title: "Approve CONDITIONALLY", path: "approve", sign: true, extra: { conditional: true } })}><i className="bi bi-pen" /> Conditional</button></>}
      {q.status === "UNDER_REVIEW" && can("vq.qualification.update") && <button className="btn btn-sm btn-outline-warning" onClick={() => setAct({ title: "Return to draft", path: "return", sign: false })}>Return</button>}
      {["APPROVED", "CONDITIONAL"].includes(q.status) && can("vq.qualification.suspend") && <button className="btn btn-sm btn-outline-danger" onClick={() => setAct({ title: "Suspend vendor", path: "suspend", sign: true })}><i className="bi bi-pen" /> Suspend</button>}
      {["APPROVED", "CONDITIONAL", "SUSPENDED"].includes(q.status) && can("vq.qualification.disqualify") && <button className="btn btn-sm btn-danger" onClick={() => setAct({ title: "Disqualify vendor", path: "disqualify", sign: true })}><i className="bi bi-pen" /> Disqualify</button>}
    </div>
    {act && <ReasonDialog title={act.title} needPassword={act.sign} meaning="QA_APPROVED" onClose={() => setAct(null)} onSubmit={async (reason, password) => { try {
      await api(`/vendor-qualifications/${id}/${act.path}`, { method: "POST", body: { reason, ...(act.sign ? { password } : {}), ...act.extra } }); load(); } catch (e) { throw new Error(errText(e)); } }} />}
    {edit && <FormModal title="Edit draft" initial={q} onClose={() => setEdit(false)} onSave={async (b) => { await api(`/vendor-qualifications/${id}`, { method: "PATCH", body: b }); setEdit(false); load(); }}
      fields={[{ key: "qualified_on", label: "Qualified on", type: "date" }, { key: "requalification_due_date", label: "Requalification due", type: "date" }, { key: "basis", label: "Basis", type: "textarea" }, { key: "audit_report_ref", label: "Audit report ref." }]} />}
  </Modal>);
}
