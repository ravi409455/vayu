import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { api, explain } from "../api/client";
import { useAuth } from "../auth";
import { homeFor } from "../guards";
import { Field } from "../ui/kit";

export function ChangePassword() {
  const { me, refresh, logout } = useAuth();
  const nav = useNavigate();
  const [o, setO] = useState("");
  const [n, setN] = useState("");
  const [n2, setN2] = useState("");
  const [err, setErr] = useState("");

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (n !== n2) return setErr("The two new passwords are different.");
    try {
      await api("auth/change-password", { body: { old_password: o, new_password: n } });
      await refresh();
      nav(homeFor(me?.role ?? "expert"), { replace: true });
    } catch (e2) {
      setErr(explain(e2));
    }
  }
  return (
    <div style={{ maxWidth: 420, margin: "10vh auto", padding: 16 }}>
      <h1>Choose a new password</h1>
      {me?.must_change_password && <p className="muted">You must set your own password before you continue.</p>}
      <form className="card" onSubmit={submit}>
        <Field label="Current password"><input type="password" value={o} onChange={(e) => setO(e.target.value)} /></Field>
        <Field label="New password" help="At least 8 characters."><input type="password" value={n} onChange={(e) => setN(e.target.value)} /></Field>
        <Field label="New password again"><input type="password" value={n2} onChange={(e) => setN2(e.target.value)} /></Field>
        {err && <p className="error" role="alert">{err}</p>}
        <button className="primary" disabled={!o || !n}>Change password</button>{" "}
        <button type="button" onClick={() => logout()}>Sign out</button>
      </form>
    </div>
  );
}
