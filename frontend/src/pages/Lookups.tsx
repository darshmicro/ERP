import { useState } from "react";
import { DataList } from "../components/DataList";
import { useAuth } from "../hooks/useAuth";
import { useLookup } from "../components/DataList";

export default function Lookups() {
  const { can } = useAuth();
  const [tab, setTab] = useState("units");
  const cats = useLookup("/categories", "name", "id", "code");
  const units = useLookup("/units", "name", "id", "code");
  const tabs: Record<string, any> = {
    units: { title: "Units of measure", path: "/units", perm: "md.unit", cols: [{ key: "code", label: "Code" }, { key: "name", label: "Name" }, { key: "dimension", label: "Dimension" }, { key: "is_active", label: "Active" }],
      fields: [{ key: "code", label: "Code", required: true }, { key: "name", label: "Name", required: true }, { key: "dimension", label: "Dimension", type: "select", options: ["MASS", "VOLUME", "COUNT", "LENGTH", "OTHER"].map((x) => ({ value: x, label: x })) }, { key: "is_active", label: "Active", type: "bool" }] },
    types: { title: "Material types", path: "/material-types", perm: "md.material_type", cols: [{ key: "code", label: "Code" }, { key: "name", label: "Name" }, { key: "is_active", label: "Active" }],
      fields: [{ key: "code", label: "Code", required: true }, { key: "name", label: "Name", required: true }, { key: "is_stock_item", label: "Stock item", type: "bool" }, { key: "is_active", label: "Active", type: "bool" }] },
    categories: { title: "Categories", path: "/categories", perm: "md.category", cols: [{ key: "code", label: "Code" }, { key: "name", label: "Name" }, { key: "is_active", label: "Active" }],
      fields: [{ key: "code", label: "Code", required: true }, { key: "name", label: "Name", required: true }, { key: "parent_id", label: "Parent", type: "select", options: cats }, { key: "is_active", label: "Active", type: "bool" }] },
  };
  const t = tabs[tab];
  return (<>
    <ul className="nav nav-tabs mb-3">{Object.entries(tabs).map(([k, x]) => (<li className="nav-item" key={k}><button className={"nav-link" + (tab === k ? " active" : "")} onClick={() => setTab(k)}>{x.title}</button></li>))}</ul>
    <DataList key={tab} title={t.title} crumbs={["Master data", "Lookups"]} path={t.path} cols={t.cols} fields={t.fields} canCreate={can(`${t.perm}.create`)} canEdit={can(`${t.perm}.update`)} />
  </>);
}
