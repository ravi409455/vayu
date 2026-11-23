import { createContext, useCallback, useContext, useEffect, useMemo, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError, setApiHandlers } from "./api/client";
import type { Me } from "./api/types";

type Auth = {
  me: Me | null;
  loading: boolean;
  can: (perm: string) => boolean;
  scope: (perm: string) => "all" | "own" | null;
  login: (username: string, password: string) => Promise<Me>;
  logout: () => Promise<void>;
  refresh: () => Promise<unknown>;
};
const Ctx = createContext<Auth | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["me"],
    retry: false,
    staleTime: 60_000,
    queryFn: async () => {
      try {
        return await api<Me>("auth/me");
      } catch (e) {
        if (e instanceof ApiError && (e.status === 401 || e.status === 403)) return null;
        throw e;
      }
    },
  });
  useEffect(() => {
    setApiHandlers({ onUnauthorized: () => qc.setQueryData(["me"], null) });
  }, [qc]);
  const me = q.data ?? null;
  const scope = useCallback((p: string) => (me ? (me.permissions[p] ?? null) : null), [me]);
  const value = useMemo<Auth>(
    () => ({
      me,
      loading: q.isLoading,
      scope,
      can: (p) => scope(p) !== null,
      login: async (username, password) => {
        await api("auth/login", { body: { username, password, client: "web" } });
        const next = await api<Me>("auth/me");
        qc.setQueryData(["me"], next);
        return next;
      },
      logout: async () => {
        await api("auth/logout", { method: "POST", body: {} });
        qc.clear();
        qc.setQueryData(["me"], null);
      },
      refresh: () => qc.invalidateQueries({ queryKey: ["me"] }),
    }),
    [me, q.isLoading, scope, qc],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth(): Auth {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAuth outside AuthProvider");
  return v;
}
