import { useState } from "react";
import { DataList, useLookup } from "../components/DataList";
import { Alert, Modal, ReasonDialog, StatusBadge } from "../components/ui";
import { useAuth } from "../hooks/useAuth";
import { api, errText } from "../services/api";

export default function Materials() {
  const { can } = useAuth();
  const types = useLookup("/material-types", "name", "id", "code");
  const units = useLookup("/units", "name", "id", "code");
  const cats = useLookup("/categories", "name", "id", "code");
  const [sel, setSel] = useState<any>(null); const [reload, setReload] = useState<() => void>(() => () => {});
  const fields = [
    { key: "name", label: "Material name", required: true }, { key: "generic_name", label: "Generic name" },
    { key: "type_id", label: "Material type", type: "select" as const, options: types, required: true },
    { key: "category_id", label: "Category", type: "select" as const, options: cats },
    { key: "base_unit_id", label: "Unit", type: "select" as const, options: units, required: true },
    { key: "grade", label: "Grade" }, { key: "pharmacopoeial_standard", label: "Pharmacopoeial standard" }, { key: "manufacturer", label: "Manufacturer" },
    { key: "pack_size", label: "Pack size" }, { key: "storage_condition", label: "Storage condition" },
    { key: "temp_min", label: "Temp min (°C)", type: "number" as const }, { key: "temp_max", label: "Temp max (°C)", type: "number" as const },
    { key: "shelf_life_days", label: "Shelf life (days)", type: "number" as const }, { key: "retest_days", label: "Retest period (days)", type: "number" as const },
    { key: "gmp_criticality", label: "GMP criticality", type: "select" as const, options: ["CRITICAL", "MAJOR", "MINOR"].map((x) => ({ value: x, label: x })) },
    { key: "fefo_mode", label: "Issue rule", type: "select" as const, options: ["FEFO", "FIFO"].map((x) => ({ value: x, label: x })) },
    { key: "hazard_class", label: "Hazard class" },
  ];
  return (<>
    <DataList title="Materials" crumbs={["Master data", "Materials"]} path="/materials" exportable canCreate={can("md.material.create")} fields={fields}
      filters={[{ key: "master_status", label: "Status", options: ["DRAFT", "APPROVED", "ACTIVE", "OBSOLETE"] }]}
      cols={[{ key: "material_code", label: "Code" }, { key: "name", label: "Name" }, { key: "grade", label: "Grade" }, { key: "storage_condition", label: "Storage" },
        { key: "gmp_criticality", label: "Criticality" }, { key: "master_status", label: "Status", badge: true }]}
      onRow={(r, load) => { setSel(r); setReload(() => load); }} />
    {sel && <MaterialDetail m={sel} fields={fields} onClose={() => { setSel(null); reload(); }} />}
  </>);
}

function MaterialDetail({ m: initial, fields, onClose }: { m: any; fields: any[]; onClose: () => void }) {
  const { can } = useAuth();
  const [m, setM] = useState<any>(initial); const [err, setErr] = useState(""); const [act, setAct] = useState<null | { title: string; path: string }>(null);
  const [edit, setEdit] = useState(false); const [vals, setVals] = useState<any>(initial); const [reason, setReason] = useState("");
  const save = async () => {
    const body: any = { reason };
    fields.forEach((f) => { if (vals[f.key] !== m[f.key]) body[f.key] = f.type === "number" && vals[f.key] !== "" && vals[f.key] != null ? Number(vals[f.key]) : vals[f.key] === "" ? null : vals[f.key]; });
    try { setM(await api(`/materials/${m.id}`, { method: "PATCH", body })); setEdit(false); setErr(""); } catch (e) { setErr(errText(e)); }
  };
  return (<Modal title={`${m.material_code} — ${m.name}`} onClose={onClose}>
    <Alert>{err}</Alert>
    <div className="mb-2">Status: <StatusBadge status={m.master_status} /> {m.barcode && <span className="mono ms-2">barcode {m.barcode}</span>}</div>
    {!edit ? <dl className="row small">{fields.map((f) => (<><dt className="col-5" key={f.key + "t"}>{f.label}</dt><dd className="col-7" key={f.key}>{String(m[f.key] ?? "—")}</dd></>))}</dl>
      : <>{fields.map((f) => (<div className="mb-1" key={f.key}><label className="form-label small mb-0">{f.label}</label>
        {f.type === "select" ? <select className="form-select form-select-sm" value={vals[f.key] ?? ""} onChange={(e) => setVals({ ...vals, [f.key]: e.target.value === "" ? null : Number(e.target.value) || e.target.value })}><option value="">—</option>{f.options.map((o: any) => <option key={o.value} value={o.value}>{o.label}</option>)}</select>
          : <input className="form-control form-control-sm" value={vals[f.key] ?? ""} onChange={(e) => setVals({ ...vals, [f.key]: e.target.value })} />}</div>))}
        <input className="form-control mt-2" placeholder="Reason for change *" value={reason} onChange={(e) => setReason(e.target.value)} />
        <button className="btn btn-primary mt-2" disabled={!reason.trim()} onClick={save}>Save</button></>}
    <div className="d-flex gap-2 flex-wrap mt-2">
      {m.master_status !== "OBSOLETE" && can("md.material.update") && <button className="btn btn-sm btn-outline-secondary" onClick={() => setEdit(!edit)}>{edit ? "Cancel edit" : "Edit"}</button>}
      {m.master_status === "DRAFT" && can("md.material.approve") && <button className="btn btn-sm btn-success" onClick={() => setAct({ title: "Approve material", path: "approve" })}><i className="bi bi-pen" /> Approve</button>}
      {m.master_status === "APPROVED" && can("md.material.approve") && <button className="btn btn-sm btn-success" onClick={() => setAct({ title: "Activate material", path: "activate" })}><i className="bi bi-pen" /> Activate</button>}
      {["APPROVED", "ACTIVE"].includes(m.master_status) && can("md.material.deactivate") && <button className="btn btn-sm btn-outline-danger" onClick={() => setAct({ title: "Mark obsolete", path: "obsolete" })}><i className="bi bi-pen" /> Obsolete</button>}
    </div>
    {act && <ReasonDialog title={act.title} needPassword meaning="QA_APPROVED / APPROVED_BY" onClose={() => setAct(null)}
      onSubmit={async (reason, password) => { try { setM(await api(`/materials/${m.id}/${act.path}`, { method: "POST", body: { password, reason } })); } catch (e) { throw new Error(errText(e)); } }} />}
  </Modal>);
}
