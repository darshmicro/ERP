import { useEffect, useState } from "react";
import { DataList } from "../components/DataList";
import { Alert, Modal, ReasonDialog, StatusBadge, fmt } from "../components/ui";
import { useAuth } from "../hooks/useAuth";
import { api, errText } from "../services/api";

const FIELDS = [
  { key: "name", label: "Vendor name", required: true },
  { key: "vendor_type", label: "Type", type: "select" as const, options: ["MANUFACTURER", "TRADER", "DISTRIBUTOR", "SERVICE"].map((x) => ({ value: x, label: x })) },
  { key: "address", label: "Address", type: "textarea" as const }, { key: "country", label: "Country" }, { key: "state", label: "State" }, { key: "city", label: "City" },
  { key: "gst_no", label: "GST" }, { key: "pan_no", label: "PAN" }, { key: "contact_person", label: "Contact person" }, { key: "email", label: "Email" }, { key: "phone", label: "Phone" },
  { key: "bank_name", label: "Bank" }, { key: "bank_account_no", label: "Account no." }, { key: "bank_ifsc", label: "IFSC" },
  { key: "material_categories", label: "Material categories supplied" },
  { key: "risk_class", label: "Risk class", type: "select" as const, options: ["CRITICAL", "HIGH", "MEDIUM", "LOW"].map((x) => ({ value: x, label: x })) },
  { key: "criticality", label: "Criticality" },
  { key: "quality_agreement_status", label: "Quality agreement", type: "select" as const, options: ["NONE", "PENDING", "SIGNED"].map((x) => ({ value: x, label: x })) },
];

export default function Vendors() {
  const { can } = useAuth();
  const [sel, setSel] = useState<number | null>(null); const [reload, setReload] = useState<() => void>(() => () => {});
  return (<>
    <DataList title="Vendors" crumbs={["Master data", "Vendors"]} path="/vendors" exportable canCreate={can("md.vendor.create")} fields={FIELDS}
      filters={[{ key: "approval_status", label: "Status", options: ["DRAFT", "APPROVED", "INACTIVE"] }, { key: "risk_class", label: "Risk", options: ["CRITICAL", "HIGH", "MEDIUM", "LOW"] }]}
      cols={[{ key: "vendor_code", label: "Code" }, { key: "name", label: "Name" }, { key: "city", label: "City" }, { key: "risk_class", label: "Risk" },
        { key: "quality_agreement_status", label: "Quality agreement" }, { key: "approval_status", label: "Status", badge: true }]}
      onRow={(r, load) => { setSel(r.id); setReload(() => load); }} />
    {sel && <VendorDetail id={sel} onClose={() => { setSel(null); reload(); }} />}
  </>);
}

function VendorDetail({ id, onClose }: { id: number; onClose: () => void }) {
  const { can } = useAuth();
  const [v, setV] = useState<any>(null); const [types, setTypes] = useState<string[]>([]); const [err, setErr] = useState(""); const [act, setAct] = useState<null | string>(null);
  const [up, setUp] = useState<any>({ doc_type: "GMP_CERTIFICATE", version: "1" }); const [file, setFile] = useState<File | null>(null);
  const load = () => api(`/vendors/${id}`).then(setV).catch((e) => setErr(errText(e)));
  useEffect(() => { load(); api("/vendor-document-types").then(setTypes).catch(() => {}); }, []);
  const upload = async () => {
    const fd = new FormData(); Object.entries(up).forEach(([k, x]) => x && fd.append(k, String(x))); fd.append("file", file!);
    try { await api(`/vendors/${id}/documents`, { method: "POST", form: fd }); setFile(null); setErr(""); load(); } catch (e) { setErr(errText(e)); }
  };
  const review = async (vd: any, approve: boolean) => {
    const comment = prompt(approve ? "Review comment (approve)" : "Reason for rejection"); if (!comment) return;
    try { await api(`/vendor-documents/${vd.id}/review`, { method: "POST", body: { approve, comment } }); load(); } catch (e) { setErr(errText(e)); }
  };
  if (!v) return <Modal title="Vendor" onClose={onClose}><Alert>{err}</Alert>Loading…</Modal>;
  return (<Modal title={`${v.vendor_code} — ${v.name}`} onClose={onClose}>
    <Alert>{err}</Alert>
    <div className="mb-2">Approval: <StatusBadge status={v.approval_status} /> · Risk <b>{v.risk_class}</b> · Quality agreement {v.quality_agreement_status}
      <div className="small text-muted">Qualification status and requalification due date are managed in the Vendor Qualification module (Phase 3).</div></div>
    <dl className="row small">{["vendor_type", "country", "state", "city", "gst_no", "pan_no", "contact_person", "email", "phone", "bank_name", "bank_account_masked"].map((k) => (<><dt className="col-4">{k.replace(/_/g, " ")}</dt><dd className="col-8">{v[k] ?? "—"}</dd></>))}</dl>
    <div className="d-flex gap-2 mb-3">
      {v.approval_status !== "APPROVED" && can("md.vendor.approve") && <button className="btn btn-sm btn-success" onClick={() => setAct("approve")}><i className="bi bi-pen" /> Approve</button>}
      {v.approval_status === "APPROVED" && can("md.vendor.deactivate") && <button className="btn btn-sm btn-outline-danger" onClick={() => setAct("deactivate")}><i className="bi bi-pen" /> Deactivate</button>}</div>
    <h6>Vendor documents</h6>
    <table className="table table-sm"><thead><tr><th>Type</th><th>No./Ver</th><th>Expiry</th><th>Review</th><th /></tr></thead>
      <tbody>{v.documents.map((d: any) => (<tr key={d.id} className={d.is_current ? "" : "text-muted"}><td>{d.doc_type}</td><td>{d.doc_no ?? ""} v{d.version}</td>
        <td className={d.expired ? "text-danger fw-bold" : ""}>{d.expiry_date ?? "—"}{d.expired && " EXPIRED"}</td><td><StatusBadge status={d.review_status} /></td>
        <td className="text-nowrap"><a href={`/api/v1/documents/${d.document_id}/download`}>download</a>
          {d.review_status === "PENDING" && can("md.vendor.review_document") && <> · <a href="#" onClick={(e) => { e.preventDefault(); review(d, true); }}>approve</a> · <a href="#" onClick={(e) => { e.preventDefault(); review(d, false); }}>reject</a></>}</td></tr>))}</tbody></table>
    {can("md.vendor.update") && can("doc.document.create") && <div className="border rounded p-2 bg-light"><div className="row g-2">
      <div className="col-6"><select className="form-select form-select-sm" value={up.doc_type} onChange={(e) => setUp({ ...up, doc_type: e.target.value })}>{types.map((t) => <option key={t}>{t}</option>)}</select></div>
      <div className="col-3"><input className="form-control form-control-sm" placeholder="Doc no." onChange={(e) => setUp({ ...up, doc_no: e.target.value })} /></div>
      <div className="col-3"><input className="form-control form-control-sm" placeholder="Version" value={up.version} onChange={(e) => setUp({ ...up, version: e.target.value })} /></div>
      <div className="col-6"><label className="small">Issue date</label><input type="date" className="form-control form-control-sm" onChange={(e) => setUp({ ...up, issue_date: e.target.value })} /></div>
      <div className="col-6"><label className="small">Expiry date</label><input type="date" className="form-control form-control-sm" onChange={(e) => setUp({ ...up, expiry_date: e.target.value })} /></div>
      <div className="col-9"><input type="file" className="form-control form-control-sm" accept=".pdf,.png,.jpg,.jpeg,.xlsx,.docx" onChange={(e) => setFile(e.target.files?.[0] ?? null)} /></div>
      <div className="col-3"><button className="btn btn-sm btn-primary w-100" disabled={!file} onClick={upload}>Upload</button></div></div></div>}
    {act && <ReasonDialog title={`${act === "approve" ? "Approve" : "Deactivate"} vendor`} needPassword meaning="APPROVED_BY" onClose={() => setAct(null)}
      onSubmit={async (reason, password) => { try { await api(`/vendors/${id}/${act}`, { method: "POST", body: { password, reason } }); load(); } catch (e) { throw new Error(errText(e)); } }} />}
  </Modal>);
}
