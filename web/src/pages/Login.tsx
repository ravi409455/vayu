import { Eye, EyeOff } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth";
import { homeFor } from "../guards";
import { explain } from "../api/client";
import { Field, usePageTitle } from "../ui/kit";
import { envName, Logo } from "../ui/Logo";

export function Login() {
  usePageTitle("Sign in");
  const { login } = useAuth();
  const nav = useNavigate();
  const loc = useLocation();
  const [u, setU] = useState("");
  const [p, setP] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [show, setShow] = useState(false);
  const [caps, setCaps] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr("");
    try {
      const me = await login(u.trim(), p);
      const from = (loc.state as { from?: string } | null)?.from;
      nav(me.must_change_password ? "/change-password" : (from ?? homeFor(me.role)), { replace: true });
    } catch (e2) {
      setErr(explain(e2));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login">
      <aside className="login-brand" aria-hidden="true">
        <Logo />
        <div className="login-pitch">
          <p className="login-big">Every car inspection, from booking to report.</p>
          <p className="login-sub">Book, assign, inspect, review and send the report, all in one place.</p>
        </div>
        <div className="login-lanes">
          {[
            ["Booked", 22, 30],
            ["On site", 46, 24],
            ["Report sent", 70, 18],
          ].map(([t, l, w]) => (
            <div key={String(t)} className="login-lane">
              <span className="login-lane-label">{t}</span>
              <span className="login-lane-bar" style={{ marginLeft: `${l}%`, width: `${w}%` }} />
            </div>
          ))}
        </div>
        <p className="login-foot">Car C.I.D. · for the team only</p>
      </aside>
      <main className="login-main">
        <div className="login-box">
          <p className="login-logo">
            <Logo big />
          </p>
          <h1 className="login-title">Sign in to Vayu</h1>
          <p className="muted" style={{ margin: "0 0 20px" }}>
            Use the username your Admin gave you. {envName() && <span className="env">{envName()}</span>}
          </p>
          <form onSubmit={submit} noValidate>
            <Field label="Username">
              <input
                className="big-input"
                value={u}
                onChange={(e) => setU(e.target.value)}
                autoComplete="username"
                autoFocus
                spellCheck={false}
                autoCapitalize="none"
              />
            </Field>
            <div className="field">
              <span className="label-row">
                <label htmlFor="pw">Password</label>
              </span>
              <div className="pw-wrap">
                <input
                  id="pw"
                  className="big-input"
                  type={show ? "text" : "password"}
                  value={p}
                  onChange={(e) => setP(e.target.value)}
                  autoComplete="current-password"
                  onKeyUp={(e) => setCaps(e.getModifierState?.("CapsLock") ?? false)}
                />
                <button
                  type="button"
                  className="pw-toggle"
                  aria-label={show ? "Hide what I typed" : "Show what I typed"}
                  aria-pressed={show}
                  onClick={() => setShow(!show)}
                >
                  {show ? <EyeOff size={16} aria-hidden /> : <Eye size={16} aria-hidden />}
                </button>
              </div>
              {caps && (
                <span className="help" style={{ color: "var(--warn)" }}>
                  Caps Lock is on.
                </span>
              )}
            </div>
            {err && (
              <div className="banner bad" role="alert">
                {err}
              </div>
            )}
            <button className="primary bigbtn" disabled={busy || !u || !p}>
              {busy ? "Signing in…" : "Sign in"}
            </button>
          </form>
          <p className="muted small" style={{ marginTop: 16 }}>
            Forgot your password? Ask an Admin to reset it.
          </p>
        </div>
      </main>
    </div>
  );
}
