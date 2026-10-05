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
import { Samples, ReleaseQueue, OOSPage, ConditionalReleases, Trends } from "./pages/QC";
import { GRNs, Inventory } from "./pages/Warehouse";
import { BOMs, Batches, Returns, Antisera } from "./pages/Manufacturing";
import { Dispatches, Trace } from "./pages/Dispatch";
import VendorQualification from "./pages/VendorQualification";
import VendorMaterials from "./pages/VendorMaterials";
import { PurchaseRequests, PurchaseOrders } from "./pages/Purchasing";

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
        <Route path="vendor-qualification" element={<VendorQualification />} />
        <Route path="vendor-materials" element={<VendorMaterials />} />
        <Route path="purchase-requests" element={<PurchaseRequests />} />
        <Route path="purchase-orders" element={<PurchaseOrders />} />
        <Route path="grn" element={<GRNs />} />
        <Route path="inventory" element={<Inventory />} />
        <Route path="samples" element={<Samples />} />
        <Route path="release" element={<ReleaseQueue />} />
        <Route path="oos" element={<OOSPage />} />
        <Route path="conditional-release" element={<ConditionalReleases />} />
        <Route path="trends" element={<Trends />} />
        <Route path="dispatch" element={<Dispatches />} />
        <Route path="trace" element={<Trace />} />
        <Route path="boms" element={<BOMs />} />
        <Route path="batches" element={<Batches />} />
        <Route path="returns" element={<Returns />} />
        <Route path="antisera" element={<Antisera />} />
        <Route path="password" element={<ChangePassword />} />
        <Route path="*" element={<Navigate to="/" />} />
      </Route>
    </Routes>
  );
}
