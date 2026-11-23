import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth";
import { Layout } from "./Layout";
import { homeFor, RequireAuth } from "./guards";
import { Login } from "./pages/Login";
import { ChangePassword } from "./pages/ChangePassword";

const Users = lazy(() => import("./pages/admin/Users").then((m) => ({ default: m.Users })));
const Roles = lazy(() => import("./pages/admin/Roles").then((m) => ({ default: m.Roles })));
const MasterLists = lazy(() => import("./pages/admin/MasterLists").then((m) => ({ default: m.MasterLists })));
const Audit = lazy(() => import("./pages/admin/Audit").then((m) => ({ default: m.Audit })));
const Forms = lazy(() => import("./pages/admin/Forms").then((m) => ({ default: m.Forms })));
const Library = lazy(() => import("./pages/admin/Library").then((m) => ({ default: m.Library })));
const LibraryEditor = lazy(() => import("./pages/admin/LibraryEditor").then((m) => ({ default: m.LibraryEditor })));
const PdfDesigner = lazy(() => import("./pages/admin/PdfDesigner").then((m) => ({ default: m.PdfDesigner })));
const Integrations = lazy(() => import("./pages/admin/Integrations").then((m) => ({ default: m.Integrations })));
const ApiKeys = lazy(() => import("./pages/admin/ApiKeys").then((m) => ({ default: m.ApiKeys })));
const Promote = lazy(() => import("./pages/admin/Promote").then((m) => ({ default: m.Promote })));
const MyJobs = lazy(() => import("./pages/expert/MyJobs").then((m) => ({ default: m.MyJobs })));
const Job = lazy(() => import("./pages/expert/Job").then((m) => ({ default: m.Job })));
const JobBoard = lazy(() => import("./pages/ops/JobBoard").then((m) => ({ default: m.JobBoard })));
const BookingPage = lazy(() => import("./pages/ops/Booking").then((m) => ({ default: m.BookingPage })));
const Problems = lazy(() => import("./pages/ops/Problems").then((m) => ({ default: m.Problems })));
const Bookings = lazy(() => import("./pages/ops/Bookings").then((m) => ({ default: m.Bookings })));
const Dashboards = lazy(() => import("./pages/ops/Dashboards").then((m) => ({ default: m.Dashboards })));
const VerifyPage = lazy(() => import("./pages/Public").then((m) => ({ default: m.VerifyPage })));
const ZipPage = lazy(() => import("./pages/Public").then((m) => ({ default: m.ZipPage })));
const FormBuilder = lazy(() => import("./pages/admin/FormBuilder").then((m) => ({ default: m.FormBuilder })));

function Home() {
  const { me, loading } = useAuth();
  if (loading) return <p className="muted pad">Loading…</p>;
  return <Navigate to={me ? homeFor(me.role) : "/login"} replace />;
}

export function App() {
  return (
    <Suspense fallback={<p className="muted pad">Loading…</p>}>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/verify/:token" element={<VerifyPage />} />
        <Route path="/zip/:token" element={<ZipPage />} />
        <Route path="/change-password" element={<RequireAuth><ChangePassword /></RequireAuth>} />
        <Route element={<RequireAuth><Layout /></RequireAuth>}>
          <Route path="/" element={<Home />} />
          <Route path="/board" element={<RequireAuth perm="bookings.view" not="expert"><JobBoard /></RequireAuth>} />
          <Route path="/booking/:id" element={<RequireAuth perm="bookings.view" not="expert"><BookingPage /></RequireAuth>} />
          <Route path="/problems" element={<RequireAuth perm="bookings.view" not="expert"><Problems /></RequireAuth>} />
          <Route path="/bookings" element={<RequireAuth perm="bookings.view" not="expert"><Bookings /></RequireAuth>} />
          <Route path="/dashboards" element={<RequireAuth perm="dashboards.view"><Dashboards /></RequireAuth>} />
          <Route path="/jobs" element={<RequireAuth perm="submissions.fill"><MyJobs /></RequireAuth>} />
          <Route path="/jobs/:id" element={<RequireAuth perm="submissions.fill"><Job /></RequireAuth>} />
          <Route path="/users" element={<RequireAuth adminOnly perm="users.view"><Users /></RequireAuth>} />
          <Route path="/roles" element={<RequireAuth adminOnly perm="roles.manage"><Roles /></RequireAuth>} />
          <Route path="/lists" element={<RequireAuth adminOnly perm="forms.view"><MasterLists /></RequireAuth>} />
          <Route path="/audit" element={<RequireAuth adminOnly perm="audit.view"><Audit /></RequireAuth>} />
          <Route path="/library" element={<RequireAuth adminOnly perm="library.view"><Library /></RequireAuth>} />
          <Route path="/library/:id" element={<RequireAuth adminOnly perm="library.view"><LibraryEditor /></RequireAuth>} />
          <Route path="/pdf" element={<RequireAuth adminOnly perm="pdf_templates.view"><PdfDesigner /></RequireAuth>} />
          <Route path="/integrations" element={<RequireAuth adminOnly perm="integrations.manage"><Integrations /></RequireAuth>} />
          <Route path="/api-keys" element={<RequireAuth adminOnly perm="api_keys.manage"><ApiKeys /></RequireAuth>} />
          <Route path="/promote" element={<RequireAuth adminOnly perm="forms.promote"><Promote /></RequireAuth>} />
          <Route path="/forms" element={<RequireAuth adminOnly perm="forms.view"><Forms /></RequireAuth>} />
          <Route path="/forms/:id" element={<RequireAuth adminOnly perm="forms.view"><FormBuilder /></RequireAuth>} />
        </Route>
        <Route path="*" element={<Home />} />
      </Routes>
    </Suspense>
  );
}
