import { useEffect, useState } from "react";
import { DataList, useLookup } from "../components/DataList";
import { Alert, Modal, PageHeader, ReasonDialog, StatusBadge } from "../components/ui";
import { useAuth } from "../hooks/useAuth";
import { api, errText } from "../services/api";
import { PrintButton } from "./Reports";

/* ------------------------------------------------------------------ BOM */
export function BOMs() {
  const { can } = useAuth();
  const [sel, setSel] = useState<number | null>(null); const [creating, setCreating] = useState(false); const [reload, setReload] = useState<() => void>(() => () => {});
  return (<>
    <DataList title="Bills of Material" crumbs={["Manufacturing", "BOM"]} path="/boms"
      extraActions={can("md.bom.create") && <button className="btn btn-primary" onClick={() => setCreating(true)}><i className="bi bi-plus-lg" /> New BOM</button>}
      filters={[{ key: "status", label: "Status", options: ["DRAFT", "UNDER_REVIEW", "APPROVED", "SUPERSEDED"] }]}
      cols={[{ key: "bom_no", label: "BOM" }, { key: "version_no", label: "Ver" }, { key: "product_code", label: "Product", render: (r) => `${r.product_code} ${r.product_name}` }, { key: "batch_size", label: "Batch size" }, { key: "status", label: "Status", badge: true }]}
      onRow={(r, load) => { setSel(r.id); setReload(() => load); }} />
    {creating && <BOMForm onClose={() => { setCreating(false); reload(); }} onCreated={(id) => { setCreating(false); setSel(id); }} />}
    {sel && <BOMDetail id={sel} onClose={() => { setSel(null); reload(); }} />}
  </>);
}

function BOMForm({ onClose, onCreated }: { onClose: () => void; onCreated: (id: number) => void }) {
  const products = useLookup("/materials?type_code=SFG,FG", "name", "id", "material_code");
  const mats = useLookup("/materials?master_status=ACTIVE", "name", "id", "material_code");
  const units = useLookup("/units", "name", "id", "code");
  const [h, setH] = useState<any>({ batch_size: "", unit_id: "", product_material_id: "", yield_min_pct: 90, yield_max_pct: 105 });
  const [lines, setLines] = useState<any[]>([{ material_id: "", quantity: "", overage_pct: 0 }]); const [steps, setSteps] = useState<any[]>([{ instruction: "", requires_verification: true }]); const [err, setErr] = useState("");
  const save = async () => {
    try {
      const r = await api("/boms", { method: "POST", body: { product_material_id: Number(h.product_material_id), batch_size: Number(h.batch_size), unit_id: Number(h.unit_id), yield_min_pct: Number(h.yield_min_pct), yield_max_pct: Number(h.yield_max_pct), reason: "New BOM",
        lines: lines.filter((l) => l.material_id).map((l) => ({ material_id: Number(l.material_id), quantity: Number(l.quantity), overage_pct: Number(l.overage_pct || 0) })),
        steps: steps.filter((s) => s.instruction).map((s) => ({ instruction: s.instruction, stage: s.stage || null, requires_verification: !!s.requires_verification })) } });
      onCreated(r.id);
    } catch (e) { setErr(errText(e)); }
  };
  return (<Modal title="New BOM (draft)" onClose={onClose} footer={<><button className="btn btn-outline-secondary" onClick={onClose}>Cancel</button><button className="btn btn-primary" onClick={save}>Save draft</button></>}>
    <Alert>{err}</Alert>
    <div className="row g-2 mb-2">
      <div className="col-6"><select className="form-select" onChange={(e) => setH({ ...h, product_material_id: e.target.value })}><option value="">Product (SFG / FG)…</option>{products.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}</select></div>
      <div className="col-3"><input type="number" className="form-control" placeholder="Batch size" onChange={(e) => setH({ ...h, batch_size: e.target.value })} /></div>
      <div className="col-3"><select className="form-select" onChange={(e) => setH({ ...h, unit_id: e.target.value })}><option value="">Unit…</option>{units.map((u) => <option key={u.value} value={u.value}>{u.label}</option>)}</select></div>
      <div className="col-3"><input type="number" className="form-control" placeholder="Yield min %" value={h.yield_min_pct} onChange={(e) => setH({ ...h, yield_min_pct: e.target.value })} /></div>
      <div className="col-3"><input type="number" className="form-control" placeholder="Yield max %" value={h.yield_max_pct} onChange={(e) => setH({ ...h, yield_max_pct: e.target.value })} /></div></div>
    <h6>Components</h6>
    {lines.map((l, i) => (<div className="row g-1 mb-1" key={i}>
      <div className="col-6"><select className="form-select form-select-sm" value={l.material_id} onChange={(e) => setLines(lines.map((x, j) => j === i ? { ...x, material_id: e.target.value } : x))}><option value="">Material…</option>{mats.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}</select></div>
      <div className="col-3"><input type="number" className="form-control form-control-sm" placeholder="Qty" onChange={(e) => setLines(lines.map((x, j) => j === i ? { ...x, quantity: e.target.value } : x))} /></div>
      <div className="col-3"><input type="number" className="form-control form-control-sm" placeholder="Overage %" onChange={(e) => setLines(lines.map((x, j) => j === i ? { ...x, overage_pct: e.target.value } : x))} /></div></div>))}
    <button className="btn btn-sm btn-link" onClick={() => setLines([...lines, { material_id: "", quantity: "" }])}>+ component</button>
    <h6 className="mt-2">Master batch record steps</h6>
    {steps.map((s, i) => (<div className="row g-1 mb-1" key={i}>
      <div className="col-9"><input className="form-control form-control-sm" placeholder={`Step ${i + 1} instruction`} onChange={(e) => setSteps(steps.map((x, j) => j === i ? { ...x, instruction: e.target.value } : x))} /></div>
      <div className="col-3"><label className="small"><input type="checkbox" checked={s.requires_verification} onChange={(e) => setSteps(steps.map((x, j) => j === i ? { ...x, requires_verification: e.target.checked } : x))} /> second-person check</label></div></div>))}
    <button className="btn btn-sm btn-link" onClick={() => setSteps([...steps, { instruction: "", requires_verification: true }])}>+ step</button>
  </Modal>);
}

function BOMDetail({ id, onClose }: { id: number; onClose: () => void }) {
  const { can } = useAuth(); const [d, setD] = useState<any>(null); const [err, setErr] = useState(""); const [act, setAct] = useState<string | null>(null);
  const load = () => api(`/boms/${id}`).then(setD).catch((e) => setErr(errText(e)));
  useEffect(() => { load(); }, []);
  if (!d) return <Modal title="BOM" onClose={onClose}><Alert>{err}</Alert>Loading…</Modal>;
  const post = async (p: string, body?: any) => { try { await api(`/boms/${id}/${p}`, { method: "POST", body }); setErr(""); load(); } catch (e) { setErr(errText(e)); } };
  return (<Modal title={`${d.bom_no} v${d.version_no} — ${d.product_name}`} onClose={onClose}>
    <Alert>{err}</Alert>
    <div className="mb-2"><StatusBadge status={d.status} /> batch size {d.batch_size} · yield {d.yield_min_pct ?? "—"}–{d.yield_max_pct ?? "—"} %</div>
    <table className="table table-sm small"><thead><tr><th>#</th><th>Material</th><th>Qty</th><th>Overage %</th></tr></thead>
      <tbody>{d.lines.map((l: any) => <tr key={l.id}><td>{l.line_no}</td><td>{l.material_code} {l.material_name}</td><td>{l.quantity}</td><td>{l.overage_pct}</td></tr>)}</tbody></table>
    <ol className="small">{d.steps.map((s: any) => <li key={s.id}>{s.instruction}{s.requires_verification && <span className="badge text-bg-secondary ms-1">verify</span>}</li>)}</ol>
    <div className="d-flex gap-2">
      {d.status === "DRAFT" && can("md.bom.update") && <button className="btn btn-sm btn-primary" onClick={() => post("submit")}>Submit for approval</button>}
      {d.status === "UNDER_REVIEW" && can("md.bom.approve") && <button className="btn btn-sm btn-success" onClick={() => setAct("approve")}><i className="bi bi-pen" /> Approve</button>}
      {d.status === "APPROVED" && can("md.bom.create") && <button className="btn btn-sm btn-outline-primary" onClick={() => setAct("new-version")}>New version</button>}</div>
    {act && <ReasonDialog title={act === "approve" ? "Approve BOM" : "New BOM version"} needPassword={act === "approve"} meaning="APPROVED_BY" onClose={() => setAct(null)}
      onSubmit={async (reason, password) => { try { await api(`/boms/${id}/${act}`, { method: "POST", body: { reason, password } }); load(); } catch (e) { throw new Error(errText(e)); } }} />}
  </Modal>);
}

/* ------------------------------------------------------------------ Batches */
export function Batches() {
  const { can } = useAuth();
  const [sel, setSel] = useState<number | null>(null); const [creating, setCreating] = useState(false); const [reload, setReload] = useState<() => void>(() => () => {});
  return (<>
    <DataList title="Manufacturing batches" crumbs={["Manufacturing", "Batches"]} path="/mfg/batches"
      extraActions={can("mfg.batch.create") && <button className="btn btn-primary" onClick={() => setCreating(true)}><i className="bi bi-plus-lg" /> New batch</button>}
      filters={[{ key: "status", label: "Status", options: ["CREATED", "MATERIAL_ISSUED", "IN_PROCESS", "PRODUCTION_COMPLETE", "RECONCILED", "QC_QA", "RELEASED", "REJECTED", "CANCELLED"] }]}
      cols={[{ key: "batch_no", label: "Batch" }, { key: "batch_type", label: "Type" }, { key: "product_code", label: "Product", render: (r) => `${r.product_code} ${r.product_name}` }, { key: "planned_qty", label: "Planned" }, { key: "actual_qty", label: "Actual" }, { key: "yield_pct", label: "Yield %" },
        { key: "on_hold", label: "Hold", render: (r) => (r.on_hold ? <span className="badge text-bg-danger">HOLD</span> : "") }, { key: "status", label: "Status", badge: true }]}
      onRow={(r, load) => { setSel(r.id); setReload(() => load); }} />
    {creating && <BatchForm onClose={() => { setCreating(false); reload(); }} onCreated={(id) => { setCreating(false); setSel(id); }} />}
    {sel && <BatchDetail id={sel} onClose={() => { setSel(null); reload(); }} />}
  </>);
}

function BatchForm({ onClose, onCreated }: { onClose: () => void; onCreated: (id: number) => void }) {
  const products = useLookup("/materials?type_code=SFG,FG&master_status=ACTIVE", "name", "id", "material_code");
  const [p, setP] = useState(""); const [q, setQ] = useState(""); const [no, setNo] = useState(""); const [reason, setReason] = useState("Batch planned"); const [err, setErr] = useState("");
  const { can } = useAuth();
  const save = async () => { try { const r = await api("/mfg/batches", { method: "POST", body: { product_material_id: Number(p), planned_qty: Number(q), batch_no: no || null, reason } }); onCreated(r.id); } catch (e) { setErr(errText(e)); } };
  return (<Modal title="New manufacturing batch" onClose={onClose} footer={<><button className="btn btn-outline-secondary" onClick={onClose}>Cancel</button><button className="btn btn-primary" disabled={!p || !q} onClick={save}>Create</button></>}>
    <Alert>{err}</Alert>
    <select className="form-select mb-2" value={p} onChange={(e) => setP(e.target.value)}><option value="">Product…</option>{products.map((x) => <option key={x.value} value={x.value}>{x.label}</option>)}</select>
    <input type="number" className="form-control mb-2" placeholder="Planned quantity" value={q} onChange={(e) => setQ(e.target.value)} />
    {can("mfg.batch.override_number") && <input className="form-control mb-2" placeholder="Manual batch number (override — leave blank for automatic)" value={no} onChange={(e) => setNo(e.target.value)} />}
    <input className="form-control" placeholder="Reason" value={reason} onChange={(e) => setReason(e.target.value)} />
    <div className="form-text">The approved BOM version in force is pinned to the batch and requirements are scaled from it.</div>
  </Modal>);
}

function BatchDetail({ id, onClose }: { id: number; onClose: () => void }) {
  const { can } = useAuth();
  const [d, setD] = useState<any>(null); const [err, setErr] = useState(""); const [sign, setSign] = useState<any>(null);
  const locs = useLookup("/locations", "name", "id", "location_code"); const qlocs = useLookup("/locations?is_quarantine=1", "name", "id", "location_code");
  const [iss, setIss] = useState<any>({}); const [sugg, setSugg] = useState<any[]>([]); const [cons, setCons] = useState<Record<number, any>>({}); const [actual, setActual] = useState(""); const [ipc, setIpc] = useState<any>({}); const [qloc, setQloc] = useState("");
  const load = () => api(`/mfg/batches/${id}`).then(setD).catch((e) => setErr(errText(e)));
  useEffect(() => { load(); }, []);
  if (!d) return <Modal title="Batch" onClose={onClose}><Alert>{err}</Alert>Loading…</Modal>;
  const call = async (path: string, body?: any, method = "POST") => { try { await api(`/mfg/batches/${id}/${path}`, { method, body }); setErr(""); load(); } catch (e) { setErr(errText(e)); } };
  const suggest = async (bm: any) => { setIss({ ...iss, bm: bm.id }); try { setSugg(await api(`/mfg/batches/${id}/fefo-suggestion?batch_material_id=${bm.id}`)); setErr(""); } catch (e) { setSugg([]); setErr(errText(e)); } };
  const rec = d.reconciliation; const s = d.status;
  return (<Modal title={`${d.batch_no} — ${d.product_name}`} onClose={onClose}>
    <Alert>{err}</Alert>
    <div className="mb-2"><StatusBadge status={s} /> {d.on_hold && <span className="badge text-bg-danger">QUALITY HOLD</span>} {d.uses_conditional_release && <span className="badge text-bg-warning">USED UNDER QA-AUTHORIZED CONDITIONAL RELEASE</span>} · BOM {d.bom.bom_no} v{d.bom.version_no} · planned {d.planned_qty}</div>
    <h6>Materials</h6>
    <table className="table table-sm small"><thead><tr><th>Material</th><th>Required</th><th>Issued</th><th>Returned</th><th>Consumed</th><th /></tr></thead>
      <tbody>{d.materials.map((m: any) => (<tr key={m.id}><td>{m.material_code} {m.material_name}</td><td>{m.required_qty}</td><td>{m.issued_qty}</td><td>{m.returned_qty}</td>
        <td>{["IN_PROCESS", "PRODUCTION_COMPLETE"].includes(s) && can("mfg.consumption.record") ? <span className="d-flex gap-1">{["consumed", "sampled", "waste"].map((k) => <input key={k} type="number" style={{ width: 80 }} className="form-control form-control-sm" placeholder={k} onChange={(e) => setCons({ ...cons, [m.id]: { ...cons[m.id], [k]: Number(e.target.value) } })} />)}</span> : m.consumed_qty ?? "—"}</td>
        <td>{["CREATED", "MATERIAL_ISSUED"].includes(s) && can("mfg.issue.create") && <button className="btn btn-sm btn-outline-primary" onClick={() => suggest(m)}>Issue…</button>}</td></tr>))}</tbody></table>
    {iss.bm && <div className="border rounded p-2 mb-2 small"><b>FEFO/FIFO pick list</b>
      {sugg.map((x) => <div key={x.lot_id}>{x.lot_no} — take {x.take} (available {x.available}, expiry {x.expiry_date ?? "—"}) <button className="btn btn-sm btn-link" onClick={() => setIss({ ...iss, lot: x.lot_id, loc: x.location_id, qty: x.take })}>use</button></div>)}
      <div className="row g-1 mt-1"><div className="col-3"><input className="form-control form-control-sm" placeholder="Lot id" value={iss.lot ?? ""} onChange={(e) => setIss({ ...iss, lot: e.target.value })} /></div>
        <div className="col-3"><select className="form-select form-select-sm" value={iss.loc ?? ""} onChange={(e) => setIss({ ...iss, loc: e.target.value })}><option value="">Location…</option>{locs.map((l) => <option key={l.value} value={l.value}>{l.label}</option>)}</select></div>
        <div className="col-2"><input type="number" className="form-control form-control-sm" placeholder="Qty" value={iss.qty ?? ""} onChange={(e) => setIss({ ...iss, qty: e.target.value })} /></div>
        <div className="col-4"><input className="form-control form-control-sm" placeholder="FEFO deviation reason (if any)" onChange={(e) => setIss({ ...iss, dev: e.target.value })} /></div></div>
      <button className="btn btn-sm btn-primary mt-1" onClick={() => call("issue", { batch_material_id: iss.bm, material_batch_id: Number(iss.lot), location_id: Number(iss.loc), quantity: Number(iss.qty), fefo_override_reason: iss.dev || null, reason: "Material issue" }).then(() => setIss({}))}>Issue material</button></div>}
    {d.issues.length > 0 && <details className="mb-2 small"><summary>Issues ({d.issues.length})</summary>{d.issues.map((i: any) => <div key={i.id}>{i.issue_no}: lot {i.lot_no} × {i.quantity}{i.fefo_override_reason && ` (FEFO override: ${i.fefo_override_reason})`}</div>)}</details>}
    {d.steps.length > 0 && <><h6>Batch record</h6><table className="table table-sm small"><tbody>{d.steps.map((st: any) => (<tr key={st.id}><td>{st.step_no}. {st.instruction}</td><td>{st.performed_at ? `done ${st.recorded_value ?? ""}` : s === "IN_PROCESS" && can("mfg.step.execute") && <button className="btn btn-sm btn-outline-primary" onClick={() => call(`steps/${st.step_no}/execute`, { value: prompt("Recorded value (optional)") || null })}>Record</button>}</td>
      <td>{st.requires_verification && (st.verified_at ? <span className="badge text-bg-success">verified</span> : st.performed_at && can("mfg.step.verify") && <button className="btn btn-sm btn-outline-success" onClick={() => setSign({ title: `Verify step ${st.step_no}`, path: `steps/${st.step_no}/verify`, meaning: "VERIFIED_BY" })}><i className="bi bi-pen" /> Verify</button>)}</td></tr>))}</tbody></table></>}
    {d.ipc.length > 0 && <table className="table table-sm small"><thead><tr><th>IPC</th><th>Value</th><th>Limits</th><th /></tr></thead><tbody>{d.ipc.map((x: any) => <tr key={x.id} className={x.pass_fail === "FAIL" ? "table-danger" : ""}><td>{x.stage}: {x.parameter}</td><td>{x.value_numeric ?? x.value_text}</td><td>{x.lsl ?? "—"} – {x.usl ?? "—"}</td><td>{x.pass_fail}</td></tr>)}</tbody></table>}
    {s === "IN_PROCESS" && can("mfg.ipc.create") && <div className="row g-1 mb-2"><div className="col-3"><input className="form-control form-control-sm" placeholder="Parameter" onChange={(e) => setIpc({ ...ipc, parameter: e.target.value })} /></div>
      {["value", "lsl", "usl"].map((k) => <div className="col-2" key={k}><input type="number" className="form-control form-control-sm" placeholder={k} onChange={(e) => setIpc({ ...ipc, [k]: e.target.value === "" ? null : Number(e.target.value) })} /></div>)}
      <div className="col-3"><button className="btn btn-sm btn-outline-secondary" onClick={() => call("ipc", { stage: "In-process", ...ipc })}>Record IPC</button></div></div>}
    {rec && <div className={"alert " + (rec.within_tolerance && rec.yield_ok ? "alert-success" : "alert-danger")}><b>Reconciliation ({rec.status})</b> tolerance {rec.tolerance_pct}% · yield {rec.summary.yield_pct}%{!rec.yield_ok && " — OUTSIDE YIELD LIMITS"}
      <table className="table table-sm small mb-0"><thead><tr><th>Material</th><th>Issued</th><th>Consumed</th><th>Sampled</th><th>Waste</th><th>Returned</th><th>Unaccounted</th><th>Var %</th></tr></thead>
        <tbody>{rec.summary.lines.map((l: any) => <tr key={l.batch_material_id} className={l.within_tolerance ? "" : "table-danger fw-bold"}><td>{l.material}</td><td>{l.issued}</td><td>{l.consumed}</td><td>{l.sampled}</td><td>{l.waste}</td><td>{l.returned}</td><td>{l.unaccounted}</td><td>{l.variance_pct}</td></tr>)}</tbody></table>
      {rec.deviation_ref && <div>Deviation {rec.deviation_ref}: {rec.justification}</div>}</div>}
    <div className="d-flex gap-2 flex-wrap align-items-center">
      {s === "MATERIAL_ISSUED" && can("mfg.step.execute") && <button className="btn btn-sm btn-success" onClick={() => setSign({ title: "Confirm line clearance & start processing", path: "start", meaning: "VERIFIED_BY" })}><i className="bi bi-pen" /> Line clearance & start</button>}
      {s === "IN_PROCESS" && can("mfg.step.execute") && <><input type="number" style={{ width: 130 }} className="form-control form-control-sm" placeholder="Actual qty" value={actual} onChange={(e) => setActual(e.target.value)} /><button className="btn btn-sm btn-primary" disabled={!actual} onClick={() => call("complete", { actual_qty: Number(actual), reason: "Production complete" })}>Complete production</button></>}
      {["IN_PROCESS", "PRODUCTION_COMPLETE"].includes(s) && can("mfg.consumption.record") && <button className="btn btn-sm btn-outline-primary" onClick={() => call("consumption", { reason: "Consumption", entries: d.materials.map((m: any) => ({ batch_material_id: m.id, consumed: cons[m.id]?.consumed ?? m.consumed_qty ?? 0, sampled: cons[m.id]?.sampled ?? m.sample_qty ?? 0, waste: cons[m.id]?.waste ?? m.waste_qty ?? 0 })) }, "PUT")}>Save consumption</button>}
      {s === "PRODUCTION_COMPLETE" && !rec && can("mfg.reconciliation.read") && <button className="btn btn-sm btn-warning" onClick={() => call("reconcile")}>Reconcile</button>}
      {s === "PRODUCTION_COMPLETE" && rec?.status === "CALCULATED" && can("mfg.reconciliation.approve") && <button className="btn btn-sm btn-success" onClick={() => setSign({ title: "Approve reconciliation (production)", path: "reconciliation/approve", meaning: "APPROVED_BY" })}><i className="bi bi-pen" /> Approve reconciliation</button>}
      {s === "PRODUCTION_COMPLETE" && rec?.status === "PRODUCTION_APPROVED" && can("mfg.reconciliation.qa_approve") && <button className="btn btn-sm btn-danger" onClick={() => setSign({ title: "QA approval of out-of-tolerance reconciliation", path: "reconciliation/qa-approve", meaning: "QA_APPROVED", dev: true })}><i className="bi bi-pen" /> QA accept deviation</button>}
      {s === "RECONCILED" && can("mfg.output.create") && <><select className="form-select form-select-sm" style={{ width: 200 }} value={qloc} onChange={(e) => setQloc(e.target.value)}><option value="">Quarantine location…</option>{qlocs.map((l) => <option key={l.value} value={l.value}>{l.label}</option>)}</select><button className="btn btn-sm btn-primary" disabled={!qloc} onClick={() => call("output", { quarantine_location_id: Number(qloc), reason: "Output booked" })}>Book output to quarantine</button></>}
      {s === "CREATED" && can("mfg.batch.cancel") && <button className="btn btn-sm btn-outline-danger" onClick={() => setSign({ title: "Cancel batch", path: "cancel", noPw: true })}>Cancel batch</button>}</div>
    {can("reports.export.run") && <div className="mt-2"><PrintButton path={`/mfg/batches/${id}/pdf`} label="Batch record (PDF)" /></div>}
    {d.output_lot && <div className="mt-2 small">Output lot <b>{d.output_lot.lot_no}</b> — {d.output_lot.disposition}</div>}
    {sign && <ReasonDialog title={sign.title} needPassword={!sign.noPw} meaning={sign.meaning} onClose={() => setSign(null)}
      onSubmit={async (reason, password) => { try { const body: any = { reason, password }; if (sign.dev) { body.justification = reason; body.deviation_ref = prompt("Deviation reference") || ""; } await api(`/mfg/batches/${id}/${sign.path}`, { method: "POST", body }); load(); } catch (e) { throw new Error(errText(e)); } }} />}
  </Modal>);
}

/* ------------------------------------------------------------------ Returns */
export function Returns() {
  const { can } = useAuth(); const [sign, setSign] = useState<any>(null);
  return (<><DataList title="Material returns" crumbs={["Manufacturing", "Returns"]} path="/mfg/returns" filters={[{ key: "status", label: "Status", options: ["REQUESTED", "ACCEPTED", "REJECTED"] }]}
    cols={[{ key: "return_no", label: "Return" }, { key: "batch_id", label: "Batch id" }, { key: "issued_qty", label: "Issued" }, { key: "used_qty", label: "Used" }, { key: "returned_qty", label: "Returned" }, { key: "damaged_qty", label: "Damaged" }, { key: "reason", label: "Reason" }, { key: "status", label: "Status", badge: true }]}
    onRow={(r) => r.status === "REQUESTED" && can("mfg.return.accept") && setSign(r)} />
    {sign && <ReasonDialog title={`Accept return ${sign.return_no}`} onClose={() => setSign(null)} onSubmit={async (reason) => { try { await api(`/mfg/returns/${sign.id}/decide`, { method: "POST", body: { accept: true, comment: reason } }); } catch (e) { throw new Error(errText(e)); } }} />}</>);
}

/* ------------------------------------------------------------------ Antisera */
export function Antisera() {
  const { can } = useAuth(); const [tab, setTab] = useState("animals"); const [adding, setAdding] = useState<string | null>(null); const [err, setErr] = useState(""); const [f, setF] = useState<any>({});
  const animals = useLookup("/antisera/animals", "animal_tag", "id");
  const submit = async (path: string, body: any) => { try { await api(path, { method: "POST", body }); setAdding(null); setF({}); setErr(""); } catch (e) { setErr(errText(e)); } };
  return (<>
    <PageHeader title="Antisera — animals, bleeds and plasma pools" crumbs={["Manufacturing", "Antisera"]} />
    <ul className="nav nav-tabs mb-3">{[["animals", "Animals"], ["bleeds", "Bleeds"], ["pools", "Plasma pools"]].map(([k, l]) => (<li className="nav-item" key={k}><button className={"nav-link" + (tab === k ? " active" : "")} onClick={() => setTab(k)}>{l}</button></li>))}</ul>
    <Alert>{err}</Alert>
    {tab === "animals" && <><DataList title="Donor animals" crumbs={[]} path="/antisera/animals" cols={[{ key: "animal_tag", label: "Tag" }, { key: "species", label: "Species" }, { key: "weight_kg", label: "Weight kg" }, { key: "min_bleed_interval_days", label: "Bleed interval (d)" }, { key: "status", label: "Status", badge: true }]}
      extraActions={can("antisera.animal.create") && <button className="btn btn-primary" onClick={() => setAdding("animal")}>Register animal</button>} /></>}
    {tab === "bleeds" && <DataList title="Bleeds" crumbs={[]} path="/antisera/bleeds" cols={[{ key: "bleed_no", label: "Bleed" }, { key: "animal_id", label: "Animal id" }, { key: "bled_on", label: "Date" }, { key: "volume_l", label: "Volume (L)" }, { key: "pool_id", label: "Pool id" }]}
      extraActions={can("antisera.bleed.create") && <button className="btn btn-primary" onClick={() => setAdding("bleed")}>Record bleed</button>} />}
    {tab === "pools" && <DataList title="Plasma pools" crumbs={[]} path="/antisera/pools" cols={[{ key: "pool_no", label: "Pool" }, { key: "total_volume_l", label: "Volume (L)" }, { key: "material_batch_id", label: "Lot id" }]} />}
    {adding === "animal" && <Modal title="Register animal" onClose={() => setAdding(null)} footer={<button className="btn btn-primary" onClick={() => submit("/antisera/animals", { animal_tag: f.tag, weight_kg: f.w ? Number(f.w) : null, reason: "Registered" })}>Save</button>}>
      <input className="form-control mb-2" placeholder="Tag / ID" onChange={(e) => setF({ ...f, tag: e.target.value })} /><input type="number" className="form-control" placeholder="Weight kg" onChange={(e) => setF({ ...f, w: e.target.value })} /></Modal>}
    {adding === "bleed" && <Modal title="Record bleed" onClose={() => setAdding(null)} footer={<button className="btn btn-primary" onClick={() => submit("/antisera/bleeds", { animal_id: Number(f.a), bled_on: f.d, volume_l: Number(f.v) })}>Save</button>}>
      <select className="form-select mb-2" onChange={(e) => setF({ ...f, a: e.target.value })}><option value="">Animal…</option>{animals.map((a) => <option key={a.value} value={a.value}>{a.label}</option>)}</select>
      <input type="date" className="form-control mb-2" onChange={(e) => setF({ ...f, d: e.target.value })} /><input type="number" className="form-control" placeholder="Volume (L)" onChange={(e) => setF({ ...f, v: e.target.value })} /></Modal>}
  </>);
}
