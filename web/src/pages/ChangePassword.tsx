import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth";
import { homeFor } from "../guards";
import { PasswordForm } from "../ui/PasswordForm";

/** The forced "choose your own password" screen (first sign-in, or after an Admin reset). */
export function ChangePassword() {
  const { me, refresh, logout } = useAuth();
  const nav = useNavigate();
  return (
    <div style={{ maxWidth: 420, margin: "10vh auto", padding: 16 }}>
      <h1>Choose a new password</h1>
      {me?.must_change_password && <p className="muted">You must set your own password before you continue.</p>}
      <div className="card">
        <PasswordForm onDone={async () => { await refresh(); nav(homeFor(me?.role ?? "expert"), { replace: true }); }}
          secondary={<button type="button" onClick={() => logout()}>Sign out</button>} />
      </div>
    </div>
  );
}
