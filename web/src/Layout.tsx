import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "./auth";

type Item = { to: string; label: string; perm?: string; role?: string };
const GROUPS: { title: string; items: Item[] }[] = [
  { title: "Work", items: [
    { to: "/jobs", label: "My jobs", role: "expert" },
    { to: "/board", label: "Job board", perm: "bookings.view", role: "ops-admin" },
    { to: "/problems", label: "Problems", perm: "bookings.view", role: "ops-admin" },
    { to: "/search", label: "Search", perm: "bookings.view", role: "ops-admin" },
    { to: "/dashboards", label: "Dashboards", perm: "dashboards.view" },
  ] },
  { title: "Templates", items: [
    { to: "/forms", label: "Forms", perm: "forms.view" },
    { to: "/library", label: "Library", perm: "library.view" },
    { to: "/lists", label: "Master lists", perm: "forms.view" },
    { to: "/pdf", label: "PDF templates", perm: "pdf_templates.view" },
  ] },
  { title: "Settings", items: [
    { to: "/users", label: "Users", perm: "users.view" },
    { to: "/roles", label: "Roles & permissions", perm: "roles.manage" },
    { to: "/integrations", label: "Integrations", perm: "integrations.manage" },
    { to: "/api-keys", label: "API keys", perm: "api_keys.manage" },
    { to: "/promote", label: "Promote", perm: "forms.promote" },
    { to: "/audit", label: "Audit log", perm: "audit.view" },
  ] },
];

/** Which links a person sees: by permission, and a few by role (the expert has a different home). */
export function visibleNav(role: string, can: (p: string) => boolean): { title: string; items: Item[] }[] {
  return GROUPS.map((g) => ({
    title: g.title,
    items: g.items.filter((i) => {
      if (i.role === "expert") return role === "expert";
      if (i.role === "ops-admin" && role === "expert") return false;
      return !i.perm || can(i.perm);
    }),
  })).filter((g) => g.items.length > 0);
}

export function Layout() {
  const { me, can, logout } = useAuth();
  if (!me) return null;
  return (
    <div className="shell">
      <nav className="side" aria-label="Main">
        <div className="brand">VAYU</div>
        {visibleNav(me.role, can).map((g) => (
          <div key={g.title}>
            <div className="group">{g.title}</div>
            {g.items.map((i) => <NavLink key={i.to} to={i.to}>{i.label}</NavLink>)}
          </div>
        ))}
        <div className="who">
          <div>{me.name || me.username}</div>
          <div className="muted">{me.role}</div>
          <NavLink to="/change-password">Change password</NavLink>
          <button className="link" onClick={() => logout()}>Sign out</button>
        </div>
      </nav>
      <main className="main"><Outlet /></main>
    </div>
  );
}
