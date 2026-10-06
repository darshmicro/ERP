import { useEffect, useState } from "react";
import { useAuth } from "../hooks/useAuth";
import { api } from "../services/api";
import { PageHeader } from "../components/ui";

export default function Home() {
  const { branding, me } = useAuth();
  const [d, setD] = useState<any>(null);
  useEffect(() => { api("/dashboard/summary").then(setD).catch(() => {}); }, []);
  return (
    <>
      <div className="text-center mb-4">
        {branding.logo_url && <img src={branding.logo_url} alt="logo" style={{ maxHeight: 80 }} className="mb-2" />}
        <h3 className="mb-0">{branding.name}</h3>
        <div className="text-muted">{branding.app_display_name}</div>
        <div className="small mt-1">Welcome, {me?.user.full_name}</div>
      </div>
      <PageHeader title="Dashboard" crumbs={["Home"]} />
      <div className="row g-3">
        {d && Object.entries<any>(d.cards).map(([k, c]) => (
          <div className="col-12 col-md-6 col-xl-3" key={k}>
            <div className={`card card-metric h-100 ${c.available ? "" : "opacity-50"}`}>
              <div className="card-body">
                <div className="text-muted small">{c.label}</div>
                <div className="value">{c.available ? c.value : "—"}</div>
                {!c.available && <div className="small text-muted">Available from Phase {c.phase}</div>}
              </div>
            </div>
          </div>))}
      </div>
    </>
  );
}
