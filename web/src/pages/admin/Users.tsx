import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { api } from "../../api/client";
import { useList, useRefresh } from "../../api/hooks";
import type { User } from "../../api/types";
import { useAuth } from "../../auth";
import { Confirm, Field, Modal, Pill, useToast } from "../../ui/kit";

export function Users() {
  const { can } = useAuth();
  const { say, fail } = useToast();
  const refresh = useRefresh();
  const users = useList<User>("users", "users");
  const [form, setForm] = useState<Partial<User> & { password?: string } | null>(null);
  const [reset, setReset] = useState<User | null>(null);
  const [pw, setPw] = useState("");
  const [signOut, setSignOut] = useState<User | null>(null);
  const [deactivate, setDeactivate] = useState<User | null>(null);
  const manage = can("users.manage");

  const save = useMutation({
    mutationFn: (u: Partial<User> & { password?: string }) =>
      u.id ? api(`users/${u.id}`, { method: "PATCH", body: { name: u.name, email: u.email, role: u.role } })
           : api("users", { body: u }),
    onSuccess: () => { setForm(null); say("Saved."); void refresh("users"); },
    onError: fail,
  });
  const toggle = useMutation({
    mutationFn: (u: User) => api(`users/${u.id}`, { method: "PATCH", body: { is_active: !u.is_active } }),
    onSuccess: () => { setDeactivate(null); say("Done."); void refresh("users"); },
    onError: (e) => { setDeactivate(null); fail(e); },
  });
  const resetPw = useMutation({
    mutationFn: () => api(`users/${reset!.id}/reset-password`, { body: { password: pw } }),
    onSuccess: () => { setReset(null); setPw(""); say("Password reset. They must choose a new one at next sign-in."); },
    onError: fail,
  });
  const out = useMutation({
    mutationFn: () => api<{ revoked: number; warning: string }>(`users/${signOut!.id}/sign-out-devices`, { body: {} }),
    onSuccess: (r) => { setSignOut(null); say(`Signed out ${r.revoked} device(s). ${r.warning}`); },
    onError: fail,
  });

  return (
    <>
      <div className="bar"><h1 className="grow">Users</h1>
        {manage && <button className="primary" onClick={() => setForm({ role: "expert" })}>New user</button>}</div>
      <table>
        <thead><tr><th>Name</th><th>Username</th><th>Role</th><th>Status</th><th /></tr></thead>
        <tbody>
          {(users.data ?? []).filter((u) => u.username !== "api-key-service").map((u) => (
            <tr key={u.id}>
              <td>{u.name}</td><td className="mono">{u.username}</td><td>{u.role}</td>
              <td>{u.is_active ? <Pill tone="ok">Active</Pill> : <Pill tone="bad">Disabled</Pill>}
                {u.must_change_password && <> <Pill tone="warn">Must change password</Pill></>}</td>
              <td style={{ textAlign: "right" }}>
                {manage && <>
                  <button className="link" onClick={() => setForm(u)}>Edit</button>
                  <button className="link" onClick={() => setReset(u)}>Reset password</button>
                  <button className="link" onClick={() => setDeactivate(u)}>{u.is_active ? "Deactivate" : "Reactivate"}</button>
                </>}
                {can("users.sign_out_devices") && <button className="link" onClick={() => setSignOut(u)}>Sign out devices</button>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {form && (
        <Modal title={form.id ? "Edit user" : "New user"} onClose={() => setForm(null)}
          actions={<><button onClick={() => setForm(null)}>Cancel</button>
            <button className="primary" disabled={!form.name || !form.username && !form.id} onClick={() => save.mutate(form)}>Save</button></>}>
          <Field label="Name"><input value={form.name ?? ""} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
          {!form.id && <Field label="Username" help="Cannot be changed later."><input value={form.username ?? ""} onChange={(e) => setForm({ ...form, username: e.target.value })} /></Field>}
          <Field label="Email"><input value={form.email ?? ""} onChange={(e) => setForm({ ...form, email: e.target.value })} /></Field>
          <Field label="Role">
            <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value as User["role"] })}>
              <option value="expert">Expert</option><option value="ops">Ops</option><option value="admin">Admin</option>
            </select>
          </Field>
          {!form.id && <Field label="First password" help="They must change it when they first sign in."><input type="password" value={form.password ?? ""} onChange={(e) => setForm({ ...form, password: e.target.value })} /></Field>}
        </Modal>
      )}
      {reset && (
        <Modal title={`Reset password for ${reset.username}`} onClose={() => setReset(null)}
          actions={<><button onClick={() => setReset(null)}>Cancel</button><button className="primary" disabled={pw.length < 8} onClick={() => resetPw.mutate()}>Reset</button></>}>
          <p>They will be signed out everywhere and must choose a new password.</p>
          <Field label="Temporary password"><input type="password" value={pw} onChange={(e) => setPw(e.target.value)} /></Field>
        </Modal>
      )}
      {signOut && (
        <Confirm title={`Sign ${signOut.username} out of every device?`} confirmLabel="Sign out" danger onCancel={() => setSignOut(null)} onConfirm={() => out.mutate()}>
          <p>Any data that was not yet synced from their phone may be lost.</p>
        </Confirm>
      )}
      {deactivate && (
        <Confirm title={`${deactivate.is_active ? "Deactivate" : "Reactivate"} ${deactivate.username}?`} confirmLabel={deactivate.is_active ? "Deactivate" : "Reactivate"}
          danger={deactivate.is_active} onCancel={() => setDeactivate(null)} onConfirm={() => toggle.mutate(deactivate)}>
          {deactivate.is_active ? <p>They are signed out of every device and cannot sign in. Unsynced data on their phone may be lost.</p> : <p>They can sign in again.</p>}
        </Confirm>
      )}
    </>
  );
}
