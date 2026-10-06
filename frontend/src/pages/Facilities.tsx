import { useEffect, useState } from "react";
import { DataList, useLookup } from "../components/DataList";
import { Alert, Modal } from "../components/ui";
import { useAuth } from "../hooks/useAuth";
import { api, errText } from "../services/api";

export function Locations() {
  const { can } = useAuth();
  const whs = useLookup("/warehouses", "name", "id", "warehouse_code");
  const cats = useLookup("/categories", "name", "id", "code");
  const [tab, setTab] = useState("locations");
  const fields = [
    { key: "warehouse_id", label: "Warehouse", type: "select" as const, options: whs, required: true },
    { key: "location_code", label: "Location code", required: true }, { key: "name", label: "Name", required: true },
    { key: "location_type", label: "Type (Zone > Room > Rack > Shelf > Bin)", type: "select" as const, options: ["ZONE", "ROOM", "RACK", "SHELF", "BIN"].map((x) => ({ value: x, label: x })), required: true },
    { key: "parent_id", label: "Parent location id", type: "number" as const, help: "Id of the parent location (must be a higher level in the same warehouse)" },
    { key: "storage_condition", label: "Storage condition" }, { key: "temp_min", label: "Temp min", type: "number" as const }, { key: "temp_max", label: "Temp max", type: "number" as const },
    { key: "capacity", label: "Capacity", type: "number" as const }, { key: "is_quarantine", label: "Quarantine area", type: "bool" as const },
    { key: "is_rejected_area", label: "Rejected-material area", type: "bool" as const }, { key: "status", label: "Status", type: "select" as const, options: ["ACTIVE", "INACTIVE"].map((x) => ({ value: x, label: x })) },
  ];
  return (<>
    <ul className="nav nav-tabs mb-3">{["locations", "warehouses"].map((k) => (<li className="nav-item" key={k}><button className={"nav-link" + (tab === k ? " active" : "")} onClick={() => setTab(k)}>{k === "locations" ? "Locations" : "Warehouses"}</button></li>))}</ul>
    {tab === "locations" ? <DataList key="l" title="Locations" crumbs={["Master data", "Locations"]} path="/locations" exportable canCreate={can("md.location.create")} canEdit={can("md.location.update")} fields={fields}
        filters={[{ key: "location_type", label: "Type", options: ["ZONE", "ROOM", "RACK", "SHELF", "BIN"] }, { key: "status", label: "Status", options: ["ACTIVE", "INACTIVE"] }]}
        cols={[{ key: "location_code", label: "Code" }, { key: "path", label: "Path" }, { key: "location_type", label: "Type" }, { key: "storage_condition", label: "Condition" },
          { key: "temp_min", label: "Temp", render: (r) => (r.temp_min != null || r.temp_max != null ? `${r.temp_min ?? ""}–${r.temp_max ?? ""} °C` : "—") }, { key: "capacity", label: "Capacity" },
          { key: "utilisation_pct", label: "Utilisation", render: (r) => (r.utilisation_pct != null ? `${r.utilisation_pct}%` : "—") }, { key: "is_quarantine", label: "Quarantine" }, { key: "status", label: "Status", badge: true }]} />
      : <DataList key="w" title="Warehouses" crumbs={["Master data", "Warehouses"]} path="/warehouses" canCreate={can("md.warehouse.create")} canEdit={can("md.warehouse.update")}
        fields={[{ key: "warehouse_code", label: "Code", required: true }, { key: "name", label: "Name", required: true }, { key: "storage_condition", label: "Storage condition" }, { key: "is_active", label: "Active", type: "bool" }]}
        cols={[{ key: "warehouse_code", label: "Code" }, { key: "name", label: "Name" }, { key: "storage_condition", label: "Condition" }, { key: "is_active", label: "Active" }]} />}
  </>);
}

export function Equipment() {
  const { can } = useAuth();
  const [sel, setSel] = useState<any>(null);
  return (<>
    <DataList title="Equipment & Instruments" crumbs={["Master data", "Equipment"]} path="/equipment" exportable canCreate={can("md.equipment.create")} canEdit={false}
      fields={[{ key: "name", label: "Name", required: true }, { key: "equipment_code", label: "Equipment ID (blank = auto)" },
        { key: "equipment_type", label: "Type", type: "select", options: ["INSTRUMENT", "PRODUCTION", "UTILITY"].map((x) => ({ value: x, label: x })) },
        { key: "manufacturer", label: "Manufacturer" }, { key: "model", label: "Model" }, { key: "serial_no", label: "Serial no." }, { key: "location_id", label: "Location id", type: "number" },
        { key: "calibration_required", label: "Calibration required", type: "bool" }, { key: "maintenance_due", label: "Maintenance due", type: "date" }]}
      filters={[{ key: "status", label: "Status", options: ["ACTIVE", "UNDER_MAINTENANCE", "OUT_OF_SERVICE", "RETIRED"] }, { key: "qualification_status", label: "Qualification", options: ["NOT_QUALIFIED", "QUALIFIED", "REQUALIFICATION_DUE", "DISQUALIFIED"] }]}
      cols={[{ key: "equipment_code", label: "ID" }, { key: "name", label: "Name" }, { key: "model", label: "Model" }, { key: "serial_no", label: "Serial" }, { key: "qualification_status", label: "Qualification", badge: true },
        { key: "calibration_due", label: "Calibration due", render: (r) => <span className={r.calibration_due && r.calibration_due < new Date().toISOString().slice(0, 10) ? "text-danger fw-bold" : ""}>{r.calibration_due ?? "—"}</span> },
        { key: "status", label: "Status", badge: true }]}
      onRow={(r) => setSel(r)} />
    {sel && <EquipmentDetail e={sel} onClose={() => setSel(null)} />}
  </>);
}

function EquipmentDetail({ e, onClose }: { e: any; onClose: () => void }) {
  const { can } = useAuth();
  const [st, setSt] = useState<any>(null); const [cals, setCals] = useState<any[]>([]); const [err, setErr] = useState(""); const [f, setF] = useState<any>({ result: "PASS" }); const [reason, setReason] = useState("");
  const load = () => { api(`/equipment/${e.id}/status`).then(setSt).catch((x) => setErr(errText(x))); api(`/equipment/${e.id}/calibrations`).then(setCals).catch(() => {}); };
  useEffect(load, []);
  const add = async () => { try { await api(`/equipment/${e.id}/calibrations`, { method: "POST", body: { ...f, reason: reason || "Calibration recorded" } }); setErr(""); load(); } catch (x) { setErr(errText(x)); } };
  return (<Modal title={`${e.equipment_code} — ${e.name}`} onClose={onClose}>
    <Alert>{err}</Alert>
    {st && <Alert kind={st.usable_for_testing ? "success" : "warning"}>{st.usable_for_testing ? "Usable for testing" : `Not usable: ${st.reason}`} · Calibration: {st.calibration_status}</Alert>}
    <h6>Calibration history</h6>
    <table className="table table-sm small"><thead><tr><th>Performed</th><th>Due</th><th>Result</th><th>Certificate</th></tr></thead>
      <tbody>{cals.map((c) => <tr key={c.id}><td>{c.performed_on}</td><td>{c.due_on}</td><td>{c.result}</td><td>{c.certificate_no ?? ""}</td></tr>)}</tbody></table>
    {can("md.calibration.create") && <div className="row g-2"><div className="col-4"><input type="date" className="form-control form-control-sm" onChange={(x) => setF({ ...f, performed_on: x.target.value })} /></div>
      <div className="col-4"><input type="date" className="form-control form-control-sm" onChange={(x) => setF({ ...f, due_on: x.target.value })} /></div>
      <div className="col-4"><select className="form-select form-select-sm" value={f.result} onChange={(x) => setF({ ...f, result: x.target.value })}><option>PASS</option><option>FAIL</option></select></div>
      <div className="col-6"><input className="form-control form-control-sm" placeholder="Certificate no." onChange={(x) => setF({ ...f, certificate_no: x.target.value })} /></div>
      <div className="col-6"><button className="btn btn-sm btn-primary w-100" disabled={!f.performed_on || !f.due_on} onClick={add}>Record calibration</button></div></div>}
  </Modal>);
}

export function Customers() {
  const { can } = useAuth();
  return <DataList title="Customers" crumbs={["Master data", "Customers"]} path="/customers" exportable canCreate={can("md.customer.create")} canEdit={can("md.customer.update")}
    fields={[{ key: "name", label: "Name", required: true }, { key: "customer_code", label: "Code (blank = auto)" }, { key: "address", label: "Address", type: "textarea" }, { key: "state", label: "State" },
      { key: "gst_no", label: "GST" }, { key: "licence_no", label: "Licence no." }, { key: "licence_expiry", label: "Licence expiry", type: "date" }, { key: "contact_person", label: "Contact" },
      { key: "email", label: "Email" }, { key: "phone", label: "Phone" }, { key: "is_authorised", label: "Authorised to receive products", type: "bool" }, { key: "is_active", label: "Active", type: "bool" }]}
    cols={[{ key: "customer_code", label: "Code" }, { key: "name", label: "Name" }, { key: "state", label: "State" }, { key: "licence_no", label: "Licence" }, { key: "licence_expiry", label: "Licence expiry" },
      { key: "is_authorised", label: "Authorised" }, { key: "is_active", label: "Active" }]} />;
}
