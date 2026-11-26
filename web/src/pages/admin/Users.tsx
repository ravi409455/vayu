import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import { useList, useRefresh } from "../../api/hooks";
import type { User } from "../../api/types";
import { useAuth } from "../../auth";
import { Avatar } from "../../ui/Avatar";
import { Confirm, Empty, Field, LoadError, Modal, PageHeader, Pill, useToast } from "../../ui/kit";
import { MoreMenu } from "../../ui/Menu";
import { fmtStamp } from "../../lib/format";
import { keys } from "../../api/keys";

const ROLE: Record<string, string> = { admin: "Admin", ops: "Ops", expert: "Expert" };

/** What their phones last reported (server: users/{id}/phone): signed-in phones, and phones that
 * signed out still holding unsent work (signed_out_holding). */
type PhoneState = {
  devices: number;
  drafts: number;
  files: number;
  unknown: boolean;
  signed_out_holding: number;
  last_seen_at: string | null;
};
const n = (k: number, one: string) => `${k} ${one}${k === 1 ? "" : "s"}`;

/** What signing this person out would lose, from their phone's own report (F-243). */
export function phoneWords(p: PhoneState | undefined): string {
  if (!p) return "Checking their phone…";
  if (p.devices === 0 && !p.signed_out_holding) return "They have no phone signed in, so nothing on a phone is lost.";
  const seen = p.last_seen_at ? ` (last heard from ${fmtStamp(p.last_seen_at)})` : "";
  if (p.drafts || p.files) {
    const what = [p.drafts ? n(p.drafts, "unfinished booking") : "", p.files ? n(p.files, "file") : ""].filter(Boolean).join(" and ");
    const phone = p.devices === 0 ? "Their phone signed out but still holds" : "Their phone still holds";
    return `${phone} ${what} not yet on the server${seen}. These are lost.${p.unknown ? " Another phone has not said what it holds." : ""}`;
  }
  if (p.unknown) return "Their phone has not said what it holds: anything not yet sent may be lost.";
  return `Their phone has sent everything${seen}. Nothing is lost.`;
}

function PhoneWarning({ user }: { user: User }) {
  const q = useQuery({
    queryKey: keys.userPhone(user.id),
    staleTime: 0,
    retry: false,
    queryFn: ({ signal }) => api<PhoneState>(`users/${user.id}/phone`, { signal }),
  });
  return <p>{q.isError ? "Could not check their phone: anything not yet sent may be lost." : phoneWords(q.data)}</p>;
}

export function Users() {
  const { can } = useAuth();
  const { say, fail } = useToast();
  const refresh = useRefresh();
  const users = useList<User>(keys.users(), "users");
  const [form, setForm] = useState<(Partial<User> & { password?: string }) | null>(null);
  const [reset, setReset] = useState<User | null>(null);
  const [pw, setPw] = useState("");
  const [signOut, setSignOut] = useState<User | null>(null);
  const [deactivate, setDeactivate] = useState<User | null>(null);
  const manage = can("users.manage");
  const [q, setQ] = useState("");
  const [role, setRole] = useState<"" | "admin" | "ops" | "expert">("");
  const [showOff, setShowOff] = useState(false);
  const needle = q.trim().toLowerCase();
  const shown = (users.data ?? []).filter(
    (u) =>
      u.username !== "api-key-service" &&
      (showOff || u.is_active) &&
      (!role || u.role === role) &&
      (!needle || [u.name, u.username, u.email].some((x) => (x ?? "").toLowerCase().includes(needle))),
  );

  const save = useMutation({
    mutationFn: (u: Partial<User> & { password?: string }) =>
      u.id
        ? api(`users/${u.id}`, { method: "PATCH", body: { name: u.name, email: u.email, role: u.role, phone: u.phone ?? "" } })
        : api("users", { body: u }),
    onSuccess: () => {
      setForm(null);
      say("Saved.");
      void refresh(keys.users());
    },
    onError: fail,
  });
  const toggle = useMutation({
    mutationFn: (u: User) => api(`users/${u.id}`, { method: "PATCH", body: { is_active: !u.is_active } }),
    onSuccess: () => {
      setDeactivate(null);
      say("Done.");
      void refresh(keys.users());
    },
    onError: (e) => {
      setDeactivate(null);
      fail(e);
    },
  });
  const resetPw = useMutation({
    mutationFn: () => api(`users/${reset!.id}/reset-password`, { body: { password: pw } }),
    onSuccess: () => {
      setReset(null);
      setPw("");
      say("Password reset. They must choose a new one at next sign-in.");
    },
    onError: fail,
  });
  const removePicture = useMutation({
    mutationFn: (u: User) => api(`users/${u.id}/picture`, { method: "DELETE" }),
    onSuccess: () => {
      setForm((f) => (f ? { ...f, avatar_url: null } : f));
      say("Picture removed. Their initials show instead.");
      void refresh(keys.users());
    },
    onError: fail,
  });
  const out = useMutation({
    mutationFn: () => api<{ revoked: number; warning: string }>(`users/${signOut!.id}/sign-out-devices`, { body: {} }),
    onSuccess: (r) => {
      setSignOut(null);
      say(`Signed out ${r.revoked} device(s). ${r.warning}`);
    },
    onError: fail,
  });

  return (
    <>
      <PageHeader title="Users" count={shown.length}>
        {manage && (
          <button className="primary" onClick={() => setForm({ role: "expert" })}>
            New user
          </button>
        )}
      </PageHeader>
      {users.isError && <LoadError error={users.error} what="users" onRetry={users.refetch} />}
      <div className="filters">
        <input
          aria-label="Find a user"
          className="filter-search"
          placeholder="Find by name, username or email"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <div className="seg" role="group" aria-label="Role">
          {(["", "admin", "ops", "expert"] as const).map((r) => (
            <button key={r} aria-pressed={role === r} onClick={() => setRole(r)}>
              {r ? ROLE[r] : "All"}
            </button>
          ))}
        </div>
        <label className="check small">
          <input type="checkbox" checked={showOff} onChange={(e) => setShowOff(e.target.checked)} /> Show deactivated
        </label>
      </div>
      <div className="table-card">
        <table className="rows">
          <thead>
            <tr>
              <th>Name</th>
              <th>Role</th>
              <th>Status</th>
              <th>Last sign-in</th>
              <th>
                <span className="sr-only">Actions</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {shown.map((u) => (
              <tr key={u.id} className={manage ? "click" : ""} onClick={() => manage && setForm(u)}>
                <td>
                  <span className="who-avatar">
                    <Avatar who={u} size={28} />
                    <span>
                      <span className="cell-main">{u.name || u.username}</span>
                      <div className="cell-sub mono">
                        {u.username}
                        {u.email ? ` · ${u.email}` : ""}
                      </div>
                    </span>
                  </span>
                </td>
                <td>
                  <span className="pill">{ROLE[u.role] ?? u.role}</span>
                </td>
                <td>
                  {u.is_active ? <Pill tone="ok">Active</Pill> : <Pill tone="bad">Deactivated</Pill>}
                  {u.must_change_password && (
                    <>
                      {" "}
                      <Pill tone="warn">Must change password</Pill>
                    </>
                  )}
                </td>
                <td className="muted small">{u.last_login ? fmtStamp(u.last_login) : "Never"}</td>
                <td style={{ textAlign: "right" }}>
                  <MoreMenu
                    label={`Actions for ${u.username}`}
                    items={[
                      { label: "Edit", onClick: () => setForm(u), hidden: !manage },
                      { label: "Reset password", onClick: () => setReset(u), hidden: !manage },
                      { label: "Sign out of every device", onClick: () => setSignOut(u), hidden: !can("users.sign_out_devices") },
                      {
                        label: u.is_active ? "Deactivate…" : "Reactivate",
                        danger: u.is_active,
                        onClick: () => setDeactivate(u),
                        hidden: !manage,
                      },
                    ]}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {users.data && shown.length === 0 && <Empty>No user matches.</Empty>}
      </div>

      {form && (
        <Modal
          title={form.id ? "Edit user" : "New user"}
          onClose={() => setForm(null)}
          actions={
            <>
              <button onClick={() => setForm(null)}>Cancel</button>
              <button
                className="primary"
                disabled={!form.name || (!form.username && !form.id) || save.isPending}
                onClick={() => save.mutate(form)}
              >
                Save
              </button>
            </>
          }
        >
          <Field label="Name">
            <input value={form.name ?? ""} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          </Field>
          {!form.id && (
            <Field label="Username" help="Cannot be changed later.">
              <input value={form.username ?? ""} onChange={(e) => setForm({ ...form, username: e.target.value })} />
            </Field>
          )}
          <Field label="Email">
            <input value={form.email ?? ""} onChange={(e) => setForm({ ...form, email: e.target.value })} />
          </Field>
          <Field label="Phone" help="An Indian mobile number. Ops, Admins and the person themselves can see it.">
            <input
              aria-label="Phone"
              inputMode="tel"
              value={form.phone ?? ""}
              onChange={(e) => setForm({ ...form, phone: e.target.value })}
            />
          </Field>
          {form.id && form.avatar_url && (
            <Field label="Picture" help="They upload their own picture. You can only remove it, for example if it is not suitable.">
              <div className="bar">
                <Avatar who={form as User} size={48} />
                <button className="danger" onClick={() => removePicture.mutate(form as User)}>
                  Remove picture
                </button>
              </div>
            </Field>
          )}
          <Field label="Role">
            <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value as User["role"] })}>
              <option value="expert">Expert</option>
              <option value="ops">Ops</option>
              <option value="admin">Admin</option>
            </select>
          </Field>
          {!form.id && (
            <Field label="First password" help="They must change it when they first sign in.">
              <input type="password" value={form.password ?? ""} onChange={(e) => setForm({ ...form, password: e.target.value })} />
            </Field>
          )}
        </Modal>
      )}
      {reset && (
        <Modal
          title={`Reset password for ${reset.username}`}
          onClose={() => setReset(null)}
          actions={
            <>
              <button onClick={() => setReset(null)}>Cancel</button>
              <button className="primary" disabled={pw.length < 8} onClick={() => resetPw.mutate()}>
                Reset
              </button>
            </>
          }
        >
          <p>They will be signed out everywhere and must choose a new password.</p>
          <Field label="Temporary password">
            <input type="password" value={pw} onChange={(e) => setPw(e.target.value)} />
          </Field>
        </Modal>
      )}
      {signOut && (
        <Confirm
          title={`Sign ${signOut.username} out of every device?`}
          confirmLabel="Sign out"
          danger
          onCancel={() => setSignOut(null)}
          onConfirm={() => out.mutate()}
        >
          <PhoneWarning user={signOut} />
        </Confirm>
      )}
      {deactivate && (
        <Confirm
          title={`${deactivate.is_active ? "Deactivate" : "Reactivate"} ${deactivate.username}?`}
          confirmLabel={deactivate.is_active ? "Deactivate" : "Reactivate"}
          danger={deactivate.is_active}
          onCancel={() => setDeactivate(null)}
          onConfirm={() => toggle.mutate(deactivate)}
        >
          {deactivate.is_active ? (
            <>
              <p>They are signed out of every device and cannot sign in.</p>
              <PhoneWarning user={deactivate} />
            </>
          ) : (
            <p>They can sign in again.</p>
          )}
        </Confirm>
      )}
    </>
  );
}
