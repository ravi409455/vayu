import { useEffect, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import { useRefresh } from "../../api/hooks";
import type { PermissionRow } from "../../api/types";
import { useToast, PageHeader } from "../../ui/kit";
import { keys } from "../../api/keys";

type Grants = Record<string, "all" | "own">;
type RoleRow = { role: string; locked: boolean; permissions: Grants };

/** Next grant for one permission: off -> own -> all -> off (unscoped permissions: off <-> all). */
export function nextGrant(scoped: boolean, now: "own" | "all" | undefined): "own" | "all" | undefined {
  if (!now) return scoped ? "own" : "all";
  if (now === "own") return "all";
  return undefined;
}

const ROLES = ["ops", "expert"] as const;
/** Permissions nothing on the web shows Ops (their pages are Today, Bookings, Needs you, Dashboards,
 *  Settings; the rest are Admin pages), so the screen does not offer them to Ops (F-224). The
 *  server makes the Admin-only ones (keys, integrations, templates, lists) not grantable. A grant Ops
 *  already hold is still shown, so the Admin can see it and take it away. */
export const OPS_NOT_ON_WEB = new Set(["users.sign_out_devices", "audit.view", "master_lists.manage", "integrations.manage", "api_keys.manage",
  "forms.edit", "forms.publish", "forms.promote", "library.view", "pdf_templates.view", "pdf_templates.edit"]);
type R = (typeof ROLES)[number];

export function Roles() {
  const { say, fail } = useToast();
  const refresh = useRefresh();
  const perms = useQuery({ queryKey: keys.permissions(), queryFn: ({ signal }) => api<PermissionRow[]>("permissions", { signal }) });
  const roles = useQuery({ queryKey: keys.roles(), queryFn: ({ signal }) => api<RoleRow[]>("roles", { signal }) });
  const saved = (r: R): Grants => roles.data?.find((x) => x.role === r)?.permissions ?? {};
  const [draft, setDraft] = useState<Record<R, Grants>>({ ops: {}, expert: {} });
  useEffect(() => { if (roles.data) setDraft({ ops: saved("ops"), expert: saved("expert") }); }, [roles.data]); // eslint-disable-line react-hooks/exhaustive-deps
  const dirty = ROLES.filter((r) => JSON.stringify(draft[r]) !== JSON.stringify(saved(r)));
  const save = useMutation({
    mutationFn: () => Promise.all(dirty.map((r) => api(`roles/${r}/permissions`, { method: "PUT", body: { permissions: draft[r] } }))),
    onSuccess: () => { say("Permissions saved."); void refresh(keys.roles()); },
    onError: fail,
  });
  const set = (r: R, key: string, v: "own" | "all" | undefined) => {
    const copy = { ...draft[r] };
    if (v) copy[key] = v; else delete copy[key];
    setDraft({ ...draft, [r]: copy });
  };
  const groups = [...new Set((perms.data ?? []).map((p) => p.group))];
  return (
    <>
      <PageHeader title="Roles &amp; permissions" subtitle="What Ops and Experts may do. “Own” means only bookings assigned to that person; “All” means every booking. Admin always has everything." />
      <div className="table-card">
        <table className="rows perm-matrix">
          <thead><tr><th>Permission</th><th>Ops</th><th>Expert</th></tr></thead>
          {groups.map((g) => (
            <tbody key={g}>
              <tr className="group-row"><th colSpan={3}>{g}</th></tr>
              {(perms.data ?? []).filter((p) => p.group === g).map((p) => (
                <tr key={p.key}>
                  <td>{p.label}</td>
                  {ROLES.map((r) => (
                    <td key={r}>{r === "ops" && OPS_NOT_ON_WEB.has(p.key) && !draft.ops[p.key] ? <span className="muted small">Not for Ops</span> : p.grantable ? (
                      <div className="seg" role="radiogroup" aria-label={`${p.label} (${r === "ops" ? "Ops" : "Expert"})`}>
                        {(["off", ...(p.scoped ? ["own"] : []), "all"] as ("off" | "own" | "all")[]).map((o) => {
                          const v = draft[r][p.key] ?? "off";
                          return <button key={o} role="radio" aria-checked={v === o} onClick={() => set(r, p.key, o === "off" ? undefined : o)}>{o[0]!.toUpperCase() + o.slice(1)}</button>;
                        })}
                      </div>) : <span className="muted small">Admin only</span>}</td>))}
                </tr>))}
            </tbody>))}
        </table>
      </div>
      {dirty.length > 0 && (
        <div className="save-bar" role="region" aria-label="Unsaved changes">
          <span className="grow">Unsaved changes for {dirty.map((r) => (r === "ops" ? "Ops" : "Expert")).join(" and ")}. They apply to everyone in that role.</span>
          <button onClick={() => setDraft({ ops: saved("ops"), expert: saved("expert") })}>Undo</button>
          <button className="primary" disabled={save.isPending} onClick={() => save.mutate()}>Save changes</button>
        </div>)}
    </>
  );
}
