import { Navigate, Route, Routes } from "react-router-dom";
import Layout from "./layouts/Layout";
import { useAuth } from "./hooks/useAuth";
import Login from "./pages/Login";
import Home from "./pages/Home";
import Users from "./pages/Users";
import Roles from "./pages/Roles";
import Audit from "./pages/Audit";
import SecurityEvents from "./pages/SecurityEvents";
import Company from "./pages/Company";
import Workflows from "./pages/Workflows";
import Settings from "./pages/Settings";
import ChangePassword from "./pages/ChangePassword";
import Lookups from "./pages/Lookups";
import Materials from "./pages/Materials";
import Vendors from "./pages/Vendors";
import QualityMasters from "./pages/QualityMasters";
import { Locations, Equipment, Customers } from "./pages/Facilities";
import Import from "./pages/Import";

export default function App() {
  const { me, loading } = useAuth();
  if (loading) return <div className="p-5 text-center">Loading…</div>;
  if (!me) return <Login />;
  if (me.user.must_change_password)
    return <ChangePassword forced />;
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Home />} />
        <Route path="users" element={<Users />} />
        <Route path="roles" element={<Roles />} />
        <Route path="workflows" element={<Workflows />} />
        <Route path="audit" element={<Audit />} />
        <Route path="security" element={<SecurityEvents />} />
        <Route path="company" element={<Company />} />
        <Route path="settings" element={<Settings />} />
        <Route path="materials" element={<Materials />} />
        <Route path="vendors" element={<Vendors />} />
        <Route path="quality-masters" element={<QualityMasters />} />
        <Route path="locations" element={<Locations />} />
        <Route path="equipment" element={<Equipment />} />
        <Route path="customers" element={<Customers />} />
        <Route path="lookups" element={<Lookups />} />
        <Route path="import" element={<Import />} />
        <Route path="password" element={<ChangePassword />} />
        <Route path="*" element={<Navigate to="/" />} />
      </Route>
    </Routes>
  );
}
