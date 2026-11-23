import { useState, type FormEvent } from "react";
import { api, explain } from "../api/client";
import { Field } from "./kit";

/** Change your own password. Shared by the profile page and the forced "choose a new password" screen. */
export function PasswordForm({ onDone, secondary }: { onDone: () => void | Promise<void>; secondary?: React.ReactNode }) {
  const [o, setO] = useState("");
  const [n, setN] = useState("");
  const [n2, setN2] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setErr("");
    if (n !== n2) return setErr("The two new passwords are different.");
    setBusy(true);
    try {
      await api("auth/change-password", { body: { old_password: o, new_password: n } });
      setO(""); setN(""); setN2("");
      await onDone();
    } catch (e2) {
      setErr(explain(e2));
    } finally { setBusy(false); }
  }
  return (
    <form onSubmit={submit}>
      <Field label="Current password"><input type="password" autoComplete="current-password" value={o} onChange={(e) => setO(e.target.value)} /></Field>
      <Field label="New password" help="At least 8 characters."><input type="password" autoComplete="new-password" value={n} onChange={(e) => setN(e.target.value)} /></Field>
      <Field label="New password again"><input type="password" autoComplete="new-password" value={n2} onChange={(e) => setN2(e.target.value)} /></Field>
      {err && <p className="error" role="alert">{err}</p>}
      <button className="primary" disabled={!o || !n || busy}>Change password</button>{secondary && <> {secondary}</>}
    </form>
  );
}
