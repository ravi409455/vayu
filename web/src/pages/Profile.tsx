import { useRef, useState } from "react";
import { api, ApiError, explain, uploadFile } from "../api/client";
import { useAuth } from "../auth";
import { applyTheme, type ThemeChoice } from "../lib/theme";
import { Avatar } from "../ui/Avatar";
import { PageHeader, useToast } from "../ui/kit";
import { PasswordForm } from "../ui/PasswordForm";
import { fmtPhone } from "../lib/format";

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
    <>
      <PageHeader title="Your profile" />
      <div className="profile-grid">
        <div className="stack">
          <section className="card" aria-label="Picture">
            <h2 style={{ marginTop: 0 }}>Picture</h2>
            <div className="bar" style={{ gap: 16, marginBottom: 0 }}>
              <Avatar who={me} size={88} />
              <div className="grow">
                <input ref={file} type="file" accept="image/jpeg,image/png,image/webp" aria-label="Upload a picture" hidden onChange={(e) => { void pick(e.target.files?.[0]); e.target.value = ""; }} />
                <div className="bar" style={{ margin: 0 }}>
                  <button onClick={() => file.current?.click()} disabled={busy}>{me.avatar_url ? "Change picture" : "Upload a picture"}</button>
                  {me.avatar_url && <button onClick={remove} disabled={busy}>Remove picture</button>}
                </div>
                <p className="muted small" style={{ marginBottom: 0 }}>Cropped to a square from the middle. JPEG, PNG or WebP, up to 5 MB.</p>
              </div>
            </div>
            {pictureError && <p className="error" role="alert">{pictureError}</p>}
          </section>
          <section className="card" aria-label="Look">
            <h2 style={{ marginTop: 0 }}>How the app looks</h2>
            <div role="radiogroup" aria-label="Theme" className="theme-tiles">
              {THEMES.map((t) => (
                <label key={t.id} className="theme-tile" aria-checked={theme === t.id}>
                  <input className="sr-only" type="radio" name="theme" checked={theme === t.id} onChange={() => void chooseTheme(t.id)} />
                  <span className="swatch" aria-hidden="true" style={{ background: t.id === "dark" ? "#0a0f1a" : t.id === "light" ? "#f6f7f9" : "linear-gradient(90deg, #f6f7f9 50%, #0a0f1a 50%)" }}>
                    <span style={{ width: 18, background: t.id === "dark" ? "#121a2a" : "#fff" }} /><span style={{ flex: 1, background: t.id === "dark" ? "#1b2538" : "#fff", border: "1px solid rgba(127,127,127,.25)" }} />
                  </span>
                  <span><strong>{t.label}</strong><br /><span className="muted small">{t.note}</span></span>
                </label>))}
            </div>
          </section>
          <section className="card" aria-label="Details">
            <h2 style={{ marginTop: 0 }}>Your details</h2>
            <dl className="details">
              <dt>Name</dt><dd>{me.name || "—"}</dd>
              <dt>Username</dt><dd>{me.username}</dd>
              <dt>Email</dt><dd>{me.email || "—"}</dd>
              <dt>Role</dt><dd>{ROLE[me.role] ?? me.role}</dd>
              <dt>Phone</dt><dd>{me.phone ? fmtPhone(me.phone) : "—"}</dd>
            </dl>
            <p className="muted small" style={{ marginBottom: 0 }}>To change these, ask an Admin.</p>
          </section>
        </div>
        <section className="card" aria-label="Password">
          <h2 style={{ marginTop: 0 }}>Password</h2>
          <p className="muted small">Changing it signs you out on your other devices.</p>
          <PasswordForm onDone={() => { say("Password changed. Other devices were signed out."); }} />
        </section>
      </div>
    </>
  );
}
