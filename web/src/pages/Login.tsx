import { useState, type FormEvent } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth";
import { homeFor } from "../guards";
import { explain } from "../api/client";
import { Field } from "../ui/kit";
import { envName, Logo } from "../ui/Logo";

export function Login() {
  const { login } = useAuth();
  const nav = useNavigate();
  const loc = useLocation();
  const [u, setU] = useState("");
  const [p, setP] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr("");
    try {
      const me = await login(u.trim(), p);
      const from = (loc.state as { from?: string } | null)?.from;
      nav(me.must_change_password ? "/change-password" : from ?? homeFor(me.role), { replace: true });
    } catch (e2) {
      setErr(explain(e2));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ maxWidth: 380, margin: "12vh auto", padding: 16 }}>
      <h1 style={{ margin: "0 0 4px" }}><Logo big /></h1>
      <p className="muted" style={{ margin: "0 0 16px" }}>Sign in to continue. {envName() && <span className="env">{envName()}</span>}</p>
      <form className="card" onSubmit={submit}>
        <Field label="Username"><input value={u} onChange={(e) => setU(e.target.value)} autoComplete="username" autoFocus /></Field>
        <Field label="Password"><input type="password" value={p} onChange={(e) => setP(e.target.value)} autoComplete="current-password" /></Field>
        {err && <p className="error" role="alert">{err}</p>}
        <button className="primary bigbtn" disabled={busy || !u || !p}>Sign in</button>
      </form>
      <p className="muted small" style={{ textAlign: "center" }}>Forgot your password? Ask an Admin to reset it.</p>
    </div>
  );
}
