import { Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth";
import { Layout } from "./Layout";
import { homeFor, RequireAuth } from "./guards";
import { Login } from "./pages/Login";
import { ChangePassword } from "./pages/ChangePassword";
import { Profile } from "./pages/Profile";
import { ErrorBoundary, lazyPage } from "./ui/ErrorBoundary";

const Users = lazyPage(() => import("./pages/admin/Users").then((m) => ({ default: m.Users })));
const Roles = lazyPage(() => import("./pages/admin/Roles").then((m) => ({ default: m.Roles })));
const MasterLists = lazyPage(() => import("./pages/admin/MasterLists").then((m) => ({ default: m.MasterLists })));
const Settings = lazyPage(() => import("./pages/admin/Settings").then((m) => ({ default: m.Settings })));
const Audit = lazyPage(() => import("./pages/admin/Audit").then((m) => ({ default: m.Audit })));
const Forms = lazyPage(() => import("./pages/admin/Forms").then((m) => ({ default: m.Forms })));
const Library = lazyPage(() => import("./pages/admin/Library").then((m) => ({ default: m.Library })));
const LibraryEditor = lazyPage(() => import("./pages/admin/LibraryEditor").then((m) => ({ default: m.LibraryEditor })));
const PdfDesigner = lazyPage(() => import("./pages/admin/PdfDesigner").then((m) => ({ default: m.PdfDesigner })));
const Integrations = lazyPage(() => import("./pages/admin/Integrations").then((m) => ({ default: m.Integrations })));
const IntegrationEditor = lazyPage(() => import("./pages/admin/integrations/IntegrationEditor").then((m) => ({ default: m.IntegrationEditor })));
const ApiKeys = lazyPage(() => import("./pages/admin/ApiKeys").then((m) => ({ default: m.ApiKeys })));
const Promote = lazyPage(() => import("./pages/admin/Promote").then((m) => ({ default: m.Promote })));
const MyJobs = lazyPage(() => import("./pages/expert/MyJobs").then((m) => ({ default: m.MyJobs })));
const Job = lazyPage(() => import("./pages/expert/Job").then((m) => ({ default: m.Job })));
const Today = lazyPage(() => import("./pages/ops/Today").then((m) => ({ default: m.Today })));
const BookingPage = lazyPage(() => import("./pages/ops/Booking").then((m) => ({ default: m.BookingPage })));
const Problems = lazyPage(() => import("./pages/ops/Problems").then((m) => ({ default: m.Problems })));
const Bookings = lazyPage(() => import("./pages/ops/Bookings").then((m) => ({ default: m.Bookings })));
const Dashboards = lazyPage(() => import("./pages/ops/Dashboards").then((m) => ({ default: m.Dashboards })));
const VerifyPage = lazyPage(() => import("./pages/Public").then((m) => ({ default: m.VerifyPage })));
const ReportMediaPage = lazyPage(() => import("./pages/Public").then((m) => ({ default: m.ReportMediaPage })));
const ZipPage = lazyPage(() => import("./pages/Public").then((m) => ({ default: m.ZipPage })));
const AppDownload = lazyPage(() => import("./pages/AppDownload").then((m) => ({ default: m.AppDownload })));
const FormBuilder = lazyPage(() => import("./pages/admin/FormBuilder").then((m) => ({ default: m.FormBuilder })));

function Home() {
  const { me, loading } = useAuth();
  if (loading) return <p className="muted pad">Loading…</p>;
  return <Navigate to={me ? homeFor(me.role) : "/login"} replace />;
}

export function App() {
  return (
    <ErrorBoundary>
    <Suspense fallback={<p className="muted pad">Loading…</p>}>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/verify/:token" element={<VerifyPage />} />
        <Route path="/verify/:token/:link" element={<ReportMediaPage />} />
        <Route path="/zip/:token" element={<ZipPage />} />
        <Route path="/change-password" element={<RequireAuth><ChangePassword /></RequireAuth>} />
        <Route element={<RequireAuth><Layout /></RequireAuth>}>
          <Route path="/" element={<Home />} />
          <Route path="/profile" element={<Profile />} />
          <Route path="/app" element={<AppDownload />} />
          <Route path="/today" element={<RequireAuth perm="bookings.view" not="expert"><Today /></RequireAuth>} />
          <Route path="/board" element={<Navigate to="/bookings" replace />} />
          <Route path="/booking/:id" element={<RequireAuth perm="bookings.view" not="expert"><BookingPage /></RequireAuth>} />
          <Route path="/problems" element={<RequireAuth perm="bookings.view" not="expert"><Problems /></RequireAuth>} />
          <Route path="/bookings" element={<RequireAuth perm="bookings.view" not="expert"><Bookings /></RequireAuth>} />
          <Route path="/dashboards" element={<RequireAuth perm="dashboards.view"><Dashboards /></RequireAuth>} />
          <Route path="/jobs" element={<RequireAuth perm="submissions.fill"><MyJobs /></RequireAuth>} />
          <Route path="/jobs/:id" element={<RequireAuth perm="submissions.fill"><Job /></RequireAuth>} />
          <Route path="/users" element={<RequireAuth adminOnly perm="users.view"><Users /></RequireAuth>} />
          <Route path="/roles" element={<RequireAuth adminOnly perm="roles.manage"><Roles /></RequireAuth>} />
          <Route path="/lists" element={<RequireAuth adminOnly perm="forms.view"><MasterLists /></RequireAuth>} />
          <Route path="/settings" element={<RequireAuth perm="settings.view" not="expert"><Settings /></RequireAuth>} />
          <Route path="/audit" element={<RequireAuth adminOnly perm="audit.view"><Audit /></RequireAuth>} />
          <Route path="/library" element={<RequireAuth adminOnly perm="library.view"><Library /></RequireAuth>} />
          <Route path="/library/:id" element={<RequireAuth adminOnly perm="library.view"><LibraryEditor /></RequireAuth>} />
          <Route path="/pdf" element={<RequireAuth adminOnly perm="pdf_templates.view"><PdfDesigner /></RequireAuth>} />
          <Route path="/integrations" element={<RequireAuth adminOnly perm="integrations.manage"><Integrations /></RequireAuth>} />
          <Route path="/integrations/:id" element={<RequireAuth adminOnly perm="integrations.manage"><IntegrationEditor /></RequireAuth>} />
          <Route path="/api-keys" element={<RequireAuth adminOnly perm="api_keys.manage"><ApiKeys /></RequireAuth>} />
          <Route path="/promote" element={<RequireAuth adminOnly perm="forms.promote"><Promote /></RequireAuth>} />
          <Route path="/forms" element={<RequireAuth adminOnly perm="forms.view"><Forms /></RequireAuth>} />
          <Route path="/forms/:id" element={<RequireAuth adminOnly perm="forms.view"><FormBuilder /></RequireAuth>} />
        </Route>
        <Route path="*" element={<Home />} />
      </Routes>
    </Suspense>
    </ErrorBoundary>
  );
}
