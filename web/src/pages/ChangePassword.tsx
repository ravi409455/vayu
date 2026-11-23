import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth";
import { homeFor } from "../guards";
import { PasswordForm } from "../ui/PasswordForm";
import { Logo } from "../ui/Logo";

/** The forced "choose your own password" screen (first sign-in, or after an Admin reset). */
export function ChangePassword() {
  const { me, refresh, logout } = useAuth();
  const nav = useNavigate();
  return (
    <div style={{ maxWidth: 420, margin: "10vh auto", padding: 16 }}>
      <p style={{ margin: "0 0 18px" }}><Logo /></p>
      <h1 style={{ fontSize: 22, margin: "0 0 4px" }}>Choose a new password</h1>
      {me?.must_change_password && <p className="muted" style={{ marginTop: 0 }}>Welcome{me.name ? `, ${me.name.split(" ")[0]}` : ""}. Set your own password before you continue.</p>}
      <div className="card">
        <PasswordForm onDone={async () => { await refresh(); nav(homeFor(me?.role ?? "expert"), { replace: true }); }}
          secondary={<button type="button" onClick={() => logout()}>Sign out</button>} />
      </div>
    </div>
  );
}
