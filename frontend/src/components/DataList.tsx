import { ReactNode, useCallback, useEffect, useState } from "react";
import { Alert, Modal, PageHeader, StatusBadge, fmt } from "./ui";
import { api, errText } from "../services/api";

export type Col = { key: string; label: string; badge?: boolean; date?: boolean; render?: (r: any) => ReactNode };
export type Field = { key: string; label: string; type?: "text" | "number" | "date" | "bool" | "select" | "textarea"; required?: boolean;
  options?: { value: any; label: string }[]; help?: string };

/** Reusable server-paginated list with search, filters, export, create/edit dialog. */
export function DataList({ title, crumbs, path, cols, fields, canCreate, canEdit, exportable, filters, onRow, extraActions, createExtra }: {
  title: string; crumbs: string[]; path: string; cols: Col[]; fields?: Field[]; canCreate?: boolean; canEdit?: boolean;
  exportable?: boolean; filters?: { key: string; label: string; options: string[] }[]; onRow?: (r: any, reload: () => void) => void;
  extraActions?: ReactNode; createExtra?: Record<string, any>;
}) {
  const [q, setQ] = useState(""); const [offset, setOffset] = useState(0); const [f, setF] = useState<Record<string, string>>({});
  const [data, setData] = useState<any>({ items: [], total: 0 }); const [err, setErr] = useState(""); const [edit, setEdit] = useState<any>(null);
  const limit = 25;
  const qs = (extra = "") => `q=${encodeURIComponent(q)}&${Object.entries(f).filter(([, v]) => v).map(([k, v]) => `${k}=${encodeURIComponent(v)}`).join("&")}${extra}`;
  const load = useCallback(() => api(`${path}?${qs(`&limit=${limit}&offset=${offset}`)}`).then(setData).catch((e) => setErr(errText(e))), [path, q, f, offset]);
  useEffect(() => { load(); }, [load]);
  return (<>
    <PageHeader title={title} crumbs={crumbs} actions={<>{extraActions}
      {exportable && <a className="btn btn-outline-primary" href={`/api/v1${path}/export?${qs()}`}><i className="bi bi-file-earmark-excel" /> Excel</a>}
      {canCreate && fields && <button className="btn btn-primary" onClick={() => setEdit({})}><i className="bi bi-plus-lg" /> New</button>}</>} />
    <Alert>{err}</Alert>
    <div className="d-flex gap-2 mb-2 flex-wrap">
      <input className="form-control" style={{ maxWidth: 280 }} placeholder="Search…" value={q} onChange={(e) => { setOffset(0); setQ(e.target.value); }} />
      {filters?.map((fl) => (<select key={fl.key} className="form-select" style={{ maxWidth: 200 }} value={f[fl.key] ?? ""} onChange={(e) => { setOffset(0); setF({ ...f, [fl.key]: e.target.value }); }}>
        <option value="">{fl.label}: all</option>{fl.options.map((o) => <option key={o}>{o}</option>)}</select>))}
    </div>
    <div className="table-responsive"><table className="table table-sm table-hover bg-white">
      <thead><tr>{cols.map((c) => <th key={c.key}>{c.label}</th>)}</tr></thead>
      <tbody>{data.items.map((r: any) => (<tr key={r.id} role={onRow || canEdit ? "button" : undefined}
        onClick={() => (onRow ? onRow(r, load) : canEdit && fields ? setEdit(r) : null)}>
        {cols.map((c) => <td key={c.key}>{c.render ? c.render(r) : c.badge ? <StatusBadge status={String(r[c.key])} /> : c.date ? fmt(r[c.key]) : typeof r[c.key] === "boolean" ? (r[c.key] ? "Yes" : "No") : r[c.key] ?? "—"}</td>)}</tr>))}</tbody></table></div>
    <div className="d-flex justify-content-between small"><span>{data.total} records</span>
      <div className="btn-group btn-group-sm"><button className="btn btn-outline-secondary" disabled={!offset} onClick={() => setOffset(Math.max(0, offset - limit))}>Prev</button>
        <button className="btn btn-outline-secondary" disabled={offset + limit >= data.total} onClick={() => setOffset(offset + limit)}>Next</button></div></div>
    {edit && fields && <FormModal title={edit.id ? `Edit ${title}` : `New ${title}`} fields={fields} initial={edit} extra={createExtra}
      onClose={() => setEdit(null)} onSave={async (body) => { await api(edit.id ? `${path}/${edit.id}` : path, { method: edit.id ? "PATCH" : "POST", body }); setEdit(null); load(); }} />}
  </>);
}

export function FormModal({ title, fields, initial, extra, onClose, onSave }: {
  title: string; fields: Field[]; initial: any; extra?: Record<string, any>; onClose: () => void; onSave: (body: any) => Promise<void>;
}) {
  const [v, setV] = useState<any>(initial); const [reason, setReason] = useState(""); const [err, setErr] = useState("");
  const editing = !!initial.id;
  const save = async () => {
    setErr("");
    const body: any = { reason, ...extra };
    for (const fl of fields) {
      if (editing && v[fl.key] === initial[fl.key]) continue;
      let x = v[fl.key];
      if (x === "" || x === undefined) { if (!editing) continue; x = null; }
      if (fl.type === "number" && x !== null) x = Number(x);
      body[fl.key] = x;
    }
    try { await onSave(body); } catch (e) { setErr(errText(e)); }
  };
  return (<Modal title={title} onClose={onClose} footer={<><button className="btn btn-outline-secondary" onClick={onClose}>Cancel</button>
    <button className="btn btn-primary" disabled={!reason.trim()} onClick={save}>Save</button></>}>
    <Alert>{err}</Alert>
    {fields.filter((fl) => !(editing && fl.key.endsWith("_code") && initial[fl.key])).map((fl) => (<div className="mb-2" key={fl.key}>
      <label className="form-label mb-0">{fl.label}{fl.required && <span className="text-danger"> *</span>}</label>
      {fl.type === "select" ? <select className="form-select" value={v[fl.key] ?? ""} onChange={(e) => setV({ ...v, [fl.key]: e.target.value === "" ? "" : isNaN(Number(e.target.value)) ? e.target.value : Number(e.target.value) })}>
          <option value="">—</option>{fl.options?.map((o) => <option key={String(o.value)} value={o.value}>{o.label}</option>)}</select>
        : fl.type === "bool" ? <div><input type="checkbox" className="form-check-input" checked={!!v[fl.key]} onChange={(e) => setV({ ...v, [fl.key]: e.target.checked })} /></div>
        : fl.type === "textarea" ? <textarea className="form-control" rows={3} value={v[fl.key] ?? ""} onChange={(e) => setV({ ...v, [fl.key]: e.target.value })} />
        : <input className="form-control" type={fl.type ?? "text"} value={v[fl.key] ?? ""} onChange={(e) => setV({ ...v, [fl.key]: e.target.value })} />}
      {fl.help && <div className="form-text">{fl.help}</div>}</div>))}
    <label className="form-label mb-0 mt-2">Reason for {editing ? "change" : "creation"} <span className="text-danger">*</span></label>
    <input className="form-control" value={reason} onChange={(e) => setReason(e.target.value)} />
  </Modal>);
}

export function useLookup(path: string, label = "name", valueKey = "id", codeKey?: string) {
  const [opts, setOpts] = useState<{ value: any; label: string }[]>([]);
  useEffect(() => { api(`${path}${path.includes("?") ? "&" : "?"}limit=200`).then((r) => setOpts(r.items.map((x: any) => ({ value: x[valueKey], label: codeKey ? `${x[codeKey]} — ${x[label]}` : x[label] })))).catch(() => {}); }, [path]);
  return opts;
}
