import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "./auth";

/** Where a person lands, and what they may open. Pure so it can be tested without a browser. */
export function homeFor(role: string): string {
  return role === "expert" ? "/jobs" : role === "ops" ? "/board" : "/forms";
}

export function RequireAuth({ children, perm }: { children: ReactNode; perm?: string }) {
  const { me, loading, can } = useAuth();
  const loc = useLocation();
  if (loading) return <p className="muted pad">Loading…</p>;
  if (!me) return <Navigate to="/login" state={{ from: loc.pathname }} replace />;
  if (me.must_change_password && loc.pathname !== "/change-password")
    return <Navigate to="/change-password" replace />;
  if (perm && !can(perm)) return <Navigate to={homeFor(me.role)} replace />;
  return <>{children}</>;
}
