import { GlobalSearch } from "../pages/Dispatch";
import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";

const NAV: { to: string; label: string; icon: string; perm?: string }[] = [
  { to: "/", label: "Home", icon: "speedometer2" },
  { to: "/purchase-requests", label: "Purchase Requests", icon: "cart-plus", perm: "pr.request.read" },
  { to: "/purchase-orders", label: "Purchase Orders", icon: "receipt", perm: "po.order.read" },
  { to: "/vendor-qualification", label: "Vendor Qualification", icon: "patch-check", perm: "vq.qualification.read" },
  { to: "/vendor-materials", label: "Approved Vendors", icon: "link-45deg", perm: "vm.mapping.read" },
  { to: "/grn", label: "Goods Receipt (GRN)", icon: "box-arrow-in-down", perm: "grn.receipt.read" },
  { to: "/inventory", label: "Inventory & Lots", icon: "boxes", perm: "inventory.lot.read" },
  { to: "/samples", label: "Samples & QC Tests", icon: "eyedropper", perm: "qc.sample.read" },
  { to: "/release", label: "Release (QC/QA)", icon: "patch-check-fill", perm: "inventory.lot.read" },
  { to: "/oos", label: "OOS / OOT", icon: "exclamation-triangle", perm: "oos.investigation.read" },
  { to: "/conditional-release", label: "Conditional Release", icon: "shield-exclamation", perm: "conditional_release.request.read" },
  { to: "/trends", label: "QC Trends / Cpk", icon: "graph-up", perm: "stats.trend.read" },
  { to: "/boms", label: "BOM", icon: "list-check", perm: "md.bom.read" },
  { to: "/batches", label: "Manufacturing Batches", icon: "gear-wide-connected", perm: "mfg.batch.read" },
  { to: "/returns", label: "Material Returns", icon: "arrow-return-left", perm: "mfg.return.read" },
  { to: "/antisera", label: "Antisera (animals/pools)", icon: "droplet-half", perm: "antisera.animal.read" },
  { to: "/dispatch", label: "Dispatch", icon: "truck-flatbed", perm: "dispatch.order.read" },
  { to: "/trace", label: "Traceability", icon: "diagram-3-fill", perm: "trace.record.read" },
  { to: "/materials", label: "Materials", icon: "box-seam", perm: "md.material.read" },
  { to: "/vendors", label: "Vendors", icon: "truck", perm: "md.vendor.read" },
  { to: "/quality-masters", label: "Specs, STPs & Plans", icon: "clipboard-data", perm: "md.spec.read" },
  { to: "/locations", label: "Warehouse & Locations", icon: "grid-3x3-gap", perm: "md.location.read" },
  { to: "/equipment", label: "Equipment", icon: "speedometer", perm: "md.equipment.read" },
  { to: "/customers", label: "Customers", icon: "people-fill", perm: "md.customer.read" },
  { to: "/lookups", label: "Units & Categories", icon: "tags", perm: "md.unit.read" },
  { to: "/import", label: "Excel Import", icon: "file-earmark-arrow-up", perm: "import.job.read" },
  { to: "/users", label: "Users", icon: "people", perm: "iam.user.read" },
  { to: "/roles", label: "Roles & Permissions", icon: "shield-lock", perm: "iam.role.read" },
  { to: "/workflows", label: "Workflows", icon: "diagram-3", perm: "workflow.definition.read" },
  { to: "/audit", label: "Audit Trail", icon: "journal-check", perm: "audit.trail.read" },
  { to: "/security", label: "Security Events", icon: "exclamation-octagon", perm: "security.event.read" },
  { to: "/company", label: "Company", icon: "building", perm: "org.company.read" },
  { to: "/settings", label: "Numbering & Config", icon: "gear", perm: "config.numbering.read" },
];

export default function Layout() {
  const { me, branding, logout, can } = useAuth();
  return (
    <div className="d-flex min-vh-100">
      <aside className="bg-dark text-white p-3" style={{ width: 250 }}>
        <div className="text-center mb-3">
          {branding.logo_url && <img src={branding.logo_url} alt="logo" style={{ maxWidth: 120, maxHeight: 60 }} className="mb-2 bg-white p-1 rounded" />}
          <div className="fw-bold">{branding.name}</div>
          <div className="small text-secondary">{branding.app_display_name}</div>
        </div>
        <ul className="nav nav-pills flex-column gap-1">
          {NAV.filter((n) => !n.perm || can(n.perm)).map((n) => (
            <li className="nav-item" key={n.to}>
              <NavLink end={n.to === "/"} to={n.to} className={({ isActive }) => "nav-link text-white" + (isActive ? " active" : "")}>
                <i className={`bi bi-${n.icon} me-2`} />{n.label}</NavLink>
            </li>))}
        </ul>
      </aside>
      <div className="flex-grow-1 d-flex flex-column">
        <header className="navbar bg-light border-bottom px-3 justify-content-between">
          <span className="text-muted small">{me?.roles.join(", ")}</span>
          <GlobalSearch />
          <div className="d-flex align-items-center gap-3">
            <NavLink to="/password" className="small">Change password</NavLink>
            <span className="small"><i className="bi bi-person-circle me-1" />{me?.user.full_name}</span>
            <button className="btn btn-sm btn-outline-secondary" onClick={logout}>Log out</button>
          </div>
        </header>
        <main className="p-4 flex-grow-1 bg-body-tertiary"><Outlet /></main>
        <footer className="small text-muted px-4 py-2 border-top">
          GMP-MERP · Supports GMP/Part 11 controls; compliance requires site validation and procedures.
        </footer>
      </div>
    </div>
  );
}
