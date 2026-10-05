import { useEffect, useState } from "react";
import { Alert, PageHeader, ReasonDialog } from "../components/ui";
import { useAuth } from "../hooks/useAuth";
import { api, errText } from "../services/api";

export default function Settings() {
  const { can } = useAuth();
  const [num, setNum] = useState<any[]>([]); const [cfg, setCfg] = useState<any[]>([]); const [err, setErr] = useState("");
  const [edit, setEdit] = useState<null | { title: string; path: string; body: any }>(null);
  const load = () => { api("/numbering").then(setNum).catch((e) => setErr(errText(e))); if (can("config.system.read")) api("/config").then(setCfg); };
  useEffect(load, []);
  return (<>
    <PageHeader title="Numbering & System Configuration" crumbs={["Administration", "Configuration"]} />
    <Alert>{err}</Alert>
    <h6>Document numbering</h6>
    <table className="table table-sm bg-white mb-4"><thead><tr><th>Document</th><th>Prefix</th><th>Format</th><th>Reset</th><th /></tr></thead>
      <tbody>{num.map((n) => (<tr key={n.doc_type}><td>{n.doc_type}</td><td>{n.prefix}</td><td className="mono">{n.format}</td><td>{n.reset_policy}</td>
        <td>{can("config.numbering.update") && <button className="btn btn-sm btn-outline-primary" onClick={() => {
          const prefix = prompt("Prefix", n.prefix); if (!prefix) return;
          const format = prompt("Format ({prefix} {year} {yy} {seq:06d})", n.format); if (!format) return;
          setEdit({ title: `Change numbering for ${n.doc_type}`, path: `/numbering/${n.doc_type}`, body: { prefix, format, reset_policy: n.reset_policy } }); }}>Edit</button>}</td></tr>))}</tbody></table>
    <h6>System configuration</h6>
    <table className="table table-sm bg-white"><thead><tr><th>Key</th><th>Value</th><th>Description</th><th /></tr></thead>
      <tbody>{cfg.map((c) => (<tr key={c.config_key}><td className="mono">{c.config_key}</td><td>{c.value}</td><td>{c.description}</td>
        <td>{can("config.system.update") && <button className="btn btn-sm btn-outline-primary" onClick={() => { const v = prompt(c.config_key, c.value); if (v !== null) setEdit({ title: `Change ${c.config_key}`, path: `/config/${c.config_key}`, body: { value: v } }); }}>Edit</button>}</td></tr>))}</tbody></table>
    {edit && <ReasonDialog title={edit.title} onClose={() => setEdit(null)} onSubmit={async (reason) => {
      try { await api(edit.path, { method: "PUT", body: { ...edit.body, reason } }); load(); } catch (e) { throw new Error(errText(e)); } }} />}
  </>);
}
