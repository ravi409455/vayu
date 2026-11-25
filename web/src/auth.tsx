import { createContext, useCallback, useContext, useEffect, useMemo, type ReactNode } from "react";
import { useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { api, ApiError, setApiHandlers } from "./api/client";
import type { Me } from "./api/types";
import * as uploads from "./lib/uploadManager";
import { setPerson } from "./lib/monitor";
import { wipeWork } from "./lib/store";
import { keys } from "./api/keys";

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

/** Forget everything cached except the "who am I" query itself (removing that one would leave
 *  the screens watching a query that no longer exists). */
function wipe(qc: QueryClient): void {
  qc.removeQueries({ predicate: (q) => q.queryKey[0] !== keys.me()[0] });
  uploads.reset(); // nothing keeps sending (or retrying) under the next person
}

const LAST_PERSON = "vayu:last-person";
const SIGNED_OUT = "vayu:signed-out"; // written on Sign out: every other tab signs out too

/** Wipe the unsent work in this browser when it belongs to someone else than [id]. */
export async function forgetOthersWork(id: number): Promise<void> {
  let last: string | null = null;
  try {
    last = localStorage.getItem(LAST_PERSON);
  } catch {
    /* storage off: nothing was kept either */
  }
  if (last !== null && last !== String(id)) await wipeWork();
  try {
    localStorage.setItem(LAST_PERSON, String(id));
  } catch {
    /* private window */
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: keys.me(),
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
    // Whenever the identity changes, nothing cached for the previous person may stay.
    setApiHandlers({
      onUnauthorized: () => {
        // only when someone WAS signed in: the first "who am I" call is allowed to be a 401
        if (qc.getQueryData(["me"])) {
          wipe(qc);
          qc.setQueryData(["me"], null);
        }
      },
    });
    // Sign out in another tab: this one stops at once, so it never saves a draft again after the wipe
    const other = (e: StorageEvent) => {
      if (e.key !== SIGNED_OUT || !qc.getQueryData(["me"])) return;
      wipe(qc);
      qc.setQueryData(["me"], null);
    };
    window.addEventListener("storage", other);
    return () => window.removeEventListener("storage", other);
  }, [qc]);
  const me = q.data ?? null;
  useEffect(() => setPerson(me?.id ?? null), [me?.id]);
  // a session that ended by itself (idle time-out) skips Sign out: the next person to sign in on this
  // browser must not find the last one's drafts and queued photos (the same person keeps theirs)
  useEffect(() => {
    if (me) void forgetOthersWork(me.id);
  }, [me]);
  const scope = useCallback((p: string) => (me ? (me.permissions[p] ?? null) : null), [me]);
  const value = useMemo<Auth>(
    () => ({
      me,
      loading: q.isLoading,
      scope,
      can: (p) => scope(p) !== null,
      login: async (username, password) => {
        wipe(qc);
        await api("auth/login", { body: { username, password, client: "web" } });
        const next = await api<Me>("auth/me");
        await forgetOthersWork(next.id);
        qc.setQueryData(["me"], next);
        return next;
      },
      logout: async () => {
        try {
          await api("auth/logout", { method: "POST", body: {} });
        } finally {
          // even if the call fails, this browser forgets the person and their work
          wipe(qc);
          await wipeWork();
          try {
            localStorage.setItem(SIGNED_OUT, String(Date.now()));
          } catch {
            /* storage off: other tabs find out at their next request */
          }
          qc.setQueryData(["me"], null);
        }
      },
      refresh: () => qc.invalidateQueries({ queryKey: keys.me() }),
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
