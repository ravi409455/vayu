import {
  AlertTriangle, BarChart3, BookOpen, Briefcase, ChevronsLeft, ChevronsRight, FileOutput, FileText, KeyRound,
  ClipboardList, Home, List, Rocket, ScrollText, Shield, SlidersHorizontal, Users, Webhook, type LucideIcon,
} from "lucide-react";
import { useEffect, useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "./auth";
import { loadJSON, saveJSON } from "./lib/store";
import { useNeeds } from "./lib/problems";
import { CrumbProvider } from "./ui/crumb";
import { Logo } from "./ui/Logo";
import { TopBar } from "./ui/TopBar";

type Item = { to: string; label: string; icon: LucideIcon; perm?: string; role?: string };
const GROUPS: { title: string; items: Item[] }[] = [
  { title: "Work", items: [
    { to: "/jobs", label: "My jobs", icon: Briefcase, role: "expert" },
    { to: "/today", label: "Today", icon: Home, perm: "bookings.view", role: "ops-admin" },
    { to: "/bookings", label: "Bookings", icon: ClipboardList, perm: "bookings.view", role: "ops-admin" },
    { to: "/problems", label: "Needs you", icon: AlertTriangle, perm: "bookings.view", role: "ops-admin" },
    { to: "/dashboards", label: "Dashboard", icon: BarChart3, perm: "dashboards.view" },
  ] },
  { title: "Templates", items: [
    { to: "/forms", label: "Forms", icon: FileText, perm: "forms.view" },
    { to: "/library", label: "Library", icon: BookOpen, perm: "library.view" },
    { to: "/lists", label: "Master lists", icon: List, perm: "forms.view" },
    { to: "/pdf", label: "PDF templates", icon: FileOutput, perm: "pdf_templates.view" },
  ] },
  { title: "Settings", items: [
    { to: "/users", label: "Users", icon: Users, perm: "users.view" },
    { to: "/roles", label: "Roles & permissions", icon: Shield, perm: "roles.manage" },
    { to: "/integrations", label: "Integrations", icon: Webhook, perm: "integrations.manage" },
    { to: "/api-keys", label: "API keys", icon: KeyRound, perm: "api_keys.manage" },
    { to: "/promote", label: "Promote", icon: Rocket, perm: "forms.promote" },
    { to: "/settings", label: "Settings", icon: SlidersHorizontal, perm: "settings.view", role: "ops-admin" },
    { to: "/audit", label: "Audit log", icon: ScrollText, perm: "audit.view" },
  ] },
];

/** Ops only ever work with bookings: these pages and nothing else (no templates, lists,
 *  users), whatever permissions their role has behind the scenes. */
export const OPS_PAGES = ["/today", "/bookings", "/problems", "/dashboards", "/settings"];

/** Which links a person sees: by permission, and by role (the expert has a different home). */
export function visibleNav(role: string, can: (p: string) => boolean): { title: string; items: Item[] }[] {
  return GROUPS.map((g) => ({
    title: g.title,
    items: g.items.filter((i) => {
      if (i.role === "expert") return role === "expert";
      if (i.role === "ops-admin" && role === "expert") return false;
      if (role === "ops" && !OPS_PAGES.includes(i.to)) return false;
      return !i.perm || can(i.perm);
    }),
  })).filter((g) => g.items.length > 0);
}

export function Layout() {
  const { me, can } = useAuth();
  const { needs } = useNeeds();
  const [collapsed, setCollapsed] = useState(() => loadJSON<boolean>("vayu:nav:collapsed", false));
  useEffect(() => saveJSON("vayu:nav:collapsed", collapsed), [collapsed]);
  if (!me) return null;
  return (
    <CrumbProvider>
      <div className={`shell${collapsed ? " collapsed" : ""}`}>
        <nav className="side" aria-label="Main">
          <div className="side-top">
            <Logo markOnly={collapsed} />
            <button className="icon-btn dark side-toggle" aria-label={collapsed ? "Expand the menu" : "Collapse the menu"} aria-pressed={collapsed} title={collapsed ? "Expand" : "Collapse"}
              onClick={() => setCollapsed(!collapsed)}>{collapsed ? <ChevronsRight size={18} /> : <ChevronsLeft size={18} />}</button>
          </div>
          {visibleNav(me.role, can).map((g) => (
            <div key={g.title}>
              <div className="group">{collapsed ? "·" : g.title}</div>
              {g.items.map((i) => (
                <NavLink key={i.to} to={i.to} title={i.label} aria-label={i.label}>
                  <i.icon size={18} aria-hidden /><span className="nav-label">{i.label}</span>
                  {i.to === "/problems" && needs.length > 0 && <span className="nav-badge" aria-label={`${needs.length} need you`}>{needs.length}</span>}
                </NavLink>
              ))}
            </div>
          ))}
        </nav>
        <div className="body">
          <TopBar />
          <main className="main"><Outlet /></main>
        </div>
      </div>
    </CrumbProvider>
  );
}
