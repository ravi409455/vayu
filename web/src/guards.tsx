import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "./auth";

/** Where a person lands, and what they may open. Pure so it can be tested without a browser. */
export function homeFor(role: string): string {
  return role === "expert" ? "/jobs" : role === "ops" ? "/today" : "/forms";
}

export function RequireAuth({ children, perm, not, adminOnly }: { children: ReactNode; perm?: string; not?: string; adminOnly?: boolean }) {
  const { me, loading, can } = useAuth();
  const loc = useLocation();
  if (loading) return <p className="muted pad">Loading…</p>;
  if (!me) return <Navigate to="/login" state={{ from: loc.pathname }} replace />;
  if (me.must_change_password && loc.pathname !== "/change-password") return <Navigate to="/change-password" replace />;
  if ((perm && !can(perm)) || (not && me.role === not) || (adminOnly && me.role !== "admin"))
    return <Navigate to={homeFor(me.role)} replace />;
  return <>{children}</>;
}
