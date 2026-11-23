import { useEffect, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import { useRefresh } from "../../api/hooks";
import type { PermissionRow } from "../../api/types";
import { Tabs, useToast, PageHeader } from "../../ui/kit";

type Grants = Record<string, "all" | "own">;
type RoleRow = { role: string; locked: boolean; permissions: Grants };

/** Next grant for one permission: off -> own -> all -> off (unscoped permissions: off <-> all). */
export function nextGrant(scoped: boolean, now: "own" | "all" | undefined): "own" | "all" | undefined {
  if (!now) return scoped ? "own" : "all";
  if (now === "own") return "all";
  return undefined;
}

export function Roles() {
  const { say, fail } = useToast();
  const refresh = useRefresh();
  const perms = useQuery({ queryKey: ["permissions"], queryFn: () => api<PermissionRow[]>("permissions") });
  const roles = useQuery({ queryKey: ["roles"], queryFn: () => api<RoleRow[]>("roles") });
  const [role, setRole] = useState<"ops" | "expert">("ops");
  const [draft, setDraft] = useState<Grants>({});
  useEffect(() => {
    const r = roles.data?.find((x) => x.role === role);
    if (r) setDraft(r.permissions);
  }, [roles.data, role]);
  const save = useMutation({
    mutationFn: () => api(`roles/${role}/permissions`, { method: "PUT", body: { permissions: draft } }),
    onSuccess: () => { say("Permissions saved."); void refresh("roles"); },
    onError: fail,
  });
  const groups = [...new Set((perms.data ?? []).map((p) => p.group))];
  return (
    <>
      <PageHeader title="Roles &amp; permissions" subtitle="Decide what Ops and Experts may do. Admin always has everything."
        tip="Click a button to cycle: off → own → all. “Own” means only bookings assigned to that person; “all” means every booking. Changes apply to everyone in that role as soon as you save.">
        <button className="primary" onClick={() => save.mutate()}>Save changes</button></PageHeader>
      <Tabs tabs={[{ id: "ops", label: "Ops" }, { id: "expert", label: "Expert" }]} value={role} onChange={setRole} />
      {groups.map((g) => (
        <div className="card" key={g}>
          <h3>{g}</h3>
          <table>
            <tbody>
              {(perms.data ?? []).filter((p) => p.group === g).map((p) => {
                const v = draft[p.key];
                return (
                  <tr key={p.key}>
                    <td>{p.label}</td>
                    <td style={{ width: 140, textAlign: "right" }}>
                      {p.grantable ? (
                        <button aria-label={`${p.label}: ${v ?? "off"}`} onClick={() => {
                          const n = nextGrant(p.scoped, v);
                          const copy = { ...draft };
                          if (n) copy[p.key] = n; else delete copy[p.key];
                          setDraft(copy);
                        }}>{v ?? "off"}</button>
                      ) : <span className="muted">Admin only</span>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ))}
    </>
  );
}
