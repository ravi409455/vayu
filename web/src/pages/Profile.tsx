import { useRef, useState } from "react";
import { api, ApiError, explain, uploadFile } from "../api/client";
import { useAuth } from "../auth";
import { applyTheme, type ThemeChoice } from "../lib/theme";
import { Avatar } from "../ui/Avatar";
import { PageHeader, useToast } from "../ui/kit";
import { PasswordForm } from "../ui/PasswordForm";

export const MAX_PICTURE = 5 * 1024 * 1024;
const ROLE: Record<string, string> = { admin: "Admin", ops: "Ops", expert: "Expert" };
const THEMES: { id: ThemeChoice; label: string; note: string }[] = [
  { id: "light", label: "Light", note: "Bright background." },
  { id: "dark", label: "Dark", note: "Easier on the eyes at night." },
  { id: "system", label: "Match my device", note: "Follows this device's own setting." },
];

/** Your own page: picture, theme and password. Name, email, role and phone are shown but only an Admin changes them. */
export function Profile() {
  const { me, refresh } = useAuth();
  const { say, fail } = useToast();
  const file = useRef<HTMLInputElement>(null);
  const [pictureError, setPictureError] = useState("");
  const [busy, setBusy] = useState(false);
  if (!me) return null;

  async function pick(f: File | undefined) {
    if (!f) return;
    setPictureError("");
    if (!/^image\//.test(f.type)) return setPictureError("Choose a picture (JPEG, PNG or WebP).");
    if (f.size > MAX_PICTURE) return setPictureError("That picture is too big. The limit is 5 MB.");
    setBusy(true);
    try {
      await uploadFile("auth/me/picture", f, "PUT");
      await refresh();
      say("Picture saved.");
    } catch (e) {
      setPictureError(e instanceof ApiError && e.status !== 429 && e.status < 500 ? e.message : explain(e));
    } finally { setBusy(false); }
  }
  async function remove() {
    setBusy(true);
    try { await api("auth/me/picture", { method: "DELETE" }); await refresh(); say("Picture removed."); } catch (e) { fail(e); } finally { setBusy(false); }
  }
  async function chooseTheme(t: ThemeChoice) {
    applyTheme(t);                                           // at once, then saved
    try { await api("auth/me/profile", { method: "PATCH", body: { theme: t } }); await refresh(); } catch (e) { applyTheme(me!.theme ?? "light"); fail(e); }
  }
  const theme = me.theme ?? "light";
  return (
    <div style={{ maxWidth: 720 }}>
      <PageHeader title="Your profile" subtitle="Your picture, how the app looks, and your password."
        tip="Your name, email, role and phone number are set by an Admin. Your picture is shown to you, to Ops and to Admins (for example next to your name on the job board). It is never shown to customers or in reports." />
      <section className="card" aria-label="Picture">
        <h2>Picture</h2>
        <div className="bar" style={{ gap: 16 }}>
          <Avatar who={me} size={96} />
          <div>
            <input ref={file} type="file" accept="image/jpeg,image/png,image/webp" aria-label="Upload a picture" hidden onChange={(e) => { void pick(e.target.files?.[0]); e.target.value = ""; }} />
            <button onClick={() => file.current?.click()} disabled={busy}>{me.avatar_url ? "Change picture" : "Upload a picture"}</button>{" "}
            {me.avatar_url && <button onClick={remove} disabled={busy}>Remove picture</button>}
            <p className="muted small">It is cropped to a square from the middle. JPEG, PNG or WebP, up to 5 MB.</p>
          </div>
        </div>
        {pictureError && <p className="error" role="alert">{pictureError}</p>}
      </section>
      <section className="card" aria-label="Look">
        <h2>How the app looks</h2>
        <div role="radiogroup" aria-label="Theme">
          {THEMES.map((t) => (
            <label className="check" key={t.id} style={{ alignItems: "flex-start" }}>
              <input type="radio" name="theme" checked={theme === t.id} onChange={() => void chooseTheme(t.id)} />
              <span><strong>{t.label}</strong><br /><span className="muted small">{t.note}</span></span>
            </label>))}
        </div>
      </section>
      <section className="card" aria-label="Details">
        <h2>Your details</h2>
        <dl className="details">
          <dt>Name</dt><dd>{me.name || "—"}</dd>
          <dt>Username</dt><dd>{me.username}</dd>
          <dt>Email</dt><dd>{me.email || "—"}</dd>
          <dt>Role</dt><dd>{ROLE[me.role] ?? me.role}</dd>
          <dt>Phone</dt><dd>{me.phone || "—"}</dd>
        </dl>
        <p className="muted small">To change these, ask an Admin.</p>
      </section>
      <section className="card" aria-label="Password">
        <h2>Password</h2>
        <PasswordForm onDone={() => { say("Password changed. Other devices were signed out."); }} />
      </section>
    </div>
  );
}
