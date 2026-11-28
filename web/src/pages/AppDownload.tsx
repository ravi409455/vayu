import { useQuery } from "@tanstack/react-query";
import { Copy, Download, ShieldCheck, Smartphone } from "lucide-react";
import { api } from "../api/client";
import { LoadError, PageHeader, Pill, useToast } from "../ui/kit";
import { keys } from "../api/keys";

type Latest = { version_code: number | null; version_name?: string; size?: number; sha256?: string; notes?: string[]; min_version: number };

const mb = (n: number) => `${(n / 1024 / 1024).toFixed(1)} MB`;

/** The Android app page (Admin only; experts get it from /welcome or the app itself): the newest
 *  build, straight from our server, with its checksum so it can be checked before installing. */
export function AppDownload() {
  const q = useQuery({ queryKey: keys.appLatest(), queryFn: ({ signal }) => api<Latest>("app/latest", { signal }) });
  const { say } = useToast();
  const r = q.data;
  const welcome = `${window.location.origin}/welcome/engineers`;

  async function copy(text: string, what: string) {
    try {
      if (!navigator.clipboard) throw new Error("no clipboard");
      await navigator.clipboard.writeText(text);
      say(`${what} copied.`);
    } catch {
      say("Could not copy here. Select it and copy it yourself.", true);
    }
  }

  return (
    <div className="app-dl">
      <PageHeader title="Android app" subtitle="The newest build published from GitHub." />
      {q.isError && <LoadError error={q.error} what="the app download" onRetry={q.refetch} />}
      {q.isLoading && <p className="muted">Loading…</p>}
      {r && !r.version_code && (
        <div className="card app-dl-empty" role="status">
          <span className="app-dl-icon" aria-hidden>
            <Smartphone size={22} />
          </span>
          <div>
            <strong>No app build has been published yet.</strong>
            <p className="muted">Publish one from GitHub: Actions → publish app. It shows here at once.</p>
          </div>
        </div>
      )}
      {r?.version_code && (
        <>
          <section className="card app-dl-hero">
            <span className="app-dl-icon" aria-hidden>
              <Smartphone size={26} />
            </span>
            <div className="app-dl-title">
              <h2>
                Version {r.version_name} <Pill tone="ok">Newest</Pill>
              </h2>
              <p className="muted small">
                Build {r.version_code}
                {r.size ? ` · ${mb(r.size)}` : ""}
              </p>
            </div>
            <a className="btn primary app-dl-btn" href="/api/v1/app/download" download>
              <Download size={16} aria-hidden /> Download the app
            </a>
          </section>

          <div className="app-dl-grid">
            <section className="card">
              <h3>What's new</h3>
              {r.notes && r.notes.length > 0 ? (
                <ul className="app-dl-notes">
                  {r.notes.map((n) => (
                    <li key={n}>{n}</li>
                  ))}
                </ul>
              ) : (
                <p className="muted small">No notes for this build.</p>
              )}
            </section>
            <section className="card">
              <h3>Install on a phone</h3>
              <ol className="app-dl-steps">
                <li>
                  Open the downloaded file on the phone. Android may ask to allow installs from your browser: allow it for this install.
                </li>
                <li>Open Vayu and sign in with your own username.</li>
              </ol>
            </section>
          </div>

          {r.sha256 && (
            <section className="card app-dl-row">
              <ShieldCheck size={18} aria-hidden className="app-dl-row-icon" />
              <div className="app-dl-row-body">
                <div className="small muted">SHA-256 checksum</div>
                <code className="mono app-dl-code">{r.sha256}</code>
              </div>
              <button className="sm" onClick={() => copy(r.sha256!, "Checksum")}>
                <Copy size={14} aria-hidden /> Copy
              </button>
            </section>
          )}
          <section className="card app-dl-row">
            <Smartphone size={18} aria-hidden className="app-dl-row-icon" />
            <div className="app-dl-row-body">
              <div className="small muted">Download link for experts</div>
              <code className="mono app-dl-code">{welcome}</code>
            </div>
            <button className="sm" onClick={() => copy(welcome, "Link")}>
              <Copy size={14} aria-hidden /> Copy
            </button>
          </section>
        </>
      )}
    </div>
  );
}
