import { useEffect, useState } from "react";
import { Alert, PageHeader, ReasonDialog } from "../components/ui";
import { useAuth } from "../hooks/useAuth";
import { api, errText } from "../services/api";

const FIELDS: [string, string][] = [["name", "Company name"], ["app_display_name", "Application name"], ["address", "Address"], ["gst_no", "GST no."],
  ["manufacturing_licence_no", "Manufacturing licence"], ["drug_licence_no", "Drug licence"], ["contact_person", "Contact person"], ["email", "Email"],
  ["phone", "Phone"], ["website", "Website"], ["document_header", "Document header"], ["document_footer", "Document footer"], ["date_format", "Date format"], ["time_format", "Time format"]];

export default function Company() {
  const { can } = useAuth();
  const [c, setC] = useState<any>(null); const [orig, setOrig] = useState<any>(null); const [err, setErr] = useState(""); const [ok, setOk] = useState(""); const [dlg, setDlg] = useState(false);
  const [logo, setLogo] = useState<File | null>(null); const [logoDlg, setLogoDlg] = useState(false);
  const load = () => api("/company").then((r) => { setC(r); setOrig(r); }).catch((e) => setErr(errText(e)));
  useEffect(() => { load(); }, []);
  if (!c) return <Alert>{err}</Alert>;
  const editable = can("org.company.update");
  const changes = () => Object.fromEntries(FIELDS.filter(([k]) => c[k] !== orig[k]).map(([k]) => [k, c[k] ?? null]));
  return (<>
    <PageHeader title="Company & Document Settings" crumbs={["Administration", "Company"]} />
    <Alert>{err}</Alert><Alert kind="success">{ok}</Alert>
    <div className="card p-3 mb-3" style={{ maxWidth: 720 }}>
      {FIELDS.map(([k, l]) => (<div className="row mb-2" key={k}><label className="col-sm-4 col-form-label">{l}</label>
        <div className="col-sm-8"><input className="form-control" disabled={!editable} value={c[k] ?? ""} onChange={(e) => setC({ ...c, [k]: e.target.value })} /></div></div>))}
      {editable && <div><button className="btn btn-primary" disabled={!Object.keys(changes()).length} onClick={() => setDlg(true)}>Save changes</button></div>}
    </div>
    {editable && <div className="card p-3" style={{ maxWidth: 720 }}><h6>Company logo (PNG/JPG)</h6>
      <div className="input-group"><input type="file" accept=".png,.jpg,.jpeg" className="form-control" onChange={(e) => setLogo(e.target.files?.[0] ?? null)} />
        <button className="btn btn-outline-primary" disabled={!logo} onClick={() => setLogoDlg(true)}>Upload</button></div>
      <div className="form-text">The logo and name appear on the dashboard, labels, COAs and all GMP documents.</div></div>}
    {dlg && <ReasonDialog title="Save company settings" onClose={() => setDlg(false)} onSubmit={async (reason) => {
      try { await api("/company", { method: "PUT", body: { ...changes(), reason } }); setOk("Saved."); load(); } catch (e) { throw new Error(errText(e)); } }} />}
    {logoDlg && <ReasonDialog title="Upload logo" onClose={() => setLogoDlg(false)} onSubmit={async (reason) => {
      try { const fd = new FormData(); fd.append("file", logo!); await api(`/company/logo?reason=${encodeURIComponent(reason)}`, { method: "POST", form: fd }); setOk("Logo updated — reload to see it."); } catch (e) { throw new Error(errText(e)); } }} />}
  </>);
}
