import { useState } from "react";
import { DataList, useLookup } from "../components/DataList";
import { Alert, Modal, ReasonDialog, StatusBadge } from "../components/ui";
import { useAuth } from "../hooks/useAuth";
import { api, errText } from "../services/api";

export default function VendorMaterials() {
  const { can } = useAuth();
  const vendors = useLookup("/vendors?approval_status=APPROVED", "name", "id", "vendor_code");
  const mats = useLookup("/materials", "name", "id", "material_code");
  const [sel, setSel] = useState<any>(null); const [reload, setReload] = useState<() => void>(() => () => {});
  return (<>
    <DataList title="Approved Vendors per Material" crumbs={["Purchase", "Vendor–material mapping"]} path="/vendor-materials" exportable canCreate={can("vm.mapping.create")}
      fields={[{ key: "vendor_id", label: "Vendor", type: "select", options: vendors, required: true }, { key: "material_id", label: "Material", type: "select", options: mats, required: true },
        { key: "is_primary", label: "Primary source", type: "bool" }, { key: "manufacturer_site", label: "Manufacturing site" }, { key: "change_control_ref", label: "Change control ref." }, { key: "approved_to", label: "Approved until", type: "date" }]}
      filters={[{ key: "status", label: "Status", options: ["DRAFT", "UNDER_REVIEW", "APPROVED", "SUPERSEDED", "WITHDRAWN"] }]}
      cols={[{ key: "material_code", label: "Material", render: (r) => `${r.material_code} ${r.material_name}` }, { key: "vendor_code", label: "Vendor", render: (r) => `${r.vendor_code} ${r.vendor_name}` },
        { key: "version_no", label: "Ver" }, { key: "is_primary", label: "Primary" }, { key: "approved_to", label: "Until" }, { key: "status", label: "Status", badge: true }]}
      onRow={(r, load) => { setSel(r); setReload(() => load); }} />
    {sel && <Detail m={sel} onClose={() => { setSel(null); reload(); }} />}
  </>);
}

function Detail({ m: initial, onClose }: { m: any; onClose: () => void }) {
  const { can } = useAuth();
  const [m, setM] = useState<any>(initial); const [err, setErr] = useState(""); const [act, setAct] = useState<null | { title: string; path: string; sign: boolean }>(null);
  const call = async (path: string, body?: any) => { try { setM(await api(`/vendor-materials/${m.id}/${path}`, { method: "POST", body })); setErr(""); } catch (e) { setErr(errText(e)); } };
  return (<Modal title={`${m.material_code} ← ${m.vendor_code} (v${m.version_no})`} onClose={onClose}>
    <Alert>{err}</Alert>
    <div className="mb-2"><StatusBadge status={m.status} /> {m.material_name} / {m.vendor_name}</div>
    <div className="small text-muted mb-2">A purchase order can only be raised for a vendor–material pair with an APPROVED mapping. Changes are made as a new version approved by QA (e-signature).</div>
    <div className="d-flex gap-2 flex-wrap">
      {m.status === "DRAFT" && can("vm.mapping.update") && <button className="btn btn-sm btn-primary" onClick={() => call("submit")}>Submit for QA approval</button>}
      {m.status === "UNDER_REVIEW" && can("vm.mapping.approve") && <button className="btn btn-sm btn-success" onClick={() => setAct({ title: "Approve vendor for material", path: "approve", sign: true })}><i className="bi bi-pen" /> Approve</button>}
      {m.status === "APPROVED" && can("vm.mapping.create") && <button className="btn btn-sm btn-outline-primary" onClick={() => setAct({ title: "New version", path: "new-version", sign: false })}>New version</button>}
      {m.status === "APPROVED" && can("vm.mapping.withdraw") && <button className="btn btn-sm btn-outline-danger" onClick={() => setAct({ title: "Withdraw approval", path: "withdraw", sign: true })}><i className="bi bi-pen" /> Withdraw</button>}</div>
    {act && <ReasonDialog title={act.title} needPassword={act.sign} meaning="QA_APPROVED" onClose={() => setAct(null)} onSubmit={async (reason, password) => { try {
      const r = await api(`/vendor-materials/${m.id}/${act.path}`, { method: "POST", body: { reason, ...(act.sign ? { password } : {}) } }); setM(r); } catch (e) { throw new Error(errText(e)); } }} />}
  </Modal>);
}
