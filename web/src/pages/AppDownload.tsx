import { useQuery } from "@tanstack/react-query";
import { Download } from "lucide-react";
import { api } from "../api/client";
import { LoadError, PageHeader } from "../ui/kit";

type Latest = { version_code: number | null; version_name?: string; size?: number; sha256?: string; notes?: string[]; min_version: number };

const mb = (n: number) => `${(n / 1024 / 1024).toFixed(1)} MB`;

/** The Android app for experts and Ops: the newest build, straight from our server (signed in only,
 *  REQUIREMENTS §10), with its checksum so it can be checked before installing. */
export function AppDownload() {
  const q = useQuery({ queryKey: ["app-latest"], queryFn: ({ signal }) => api<Latest>("app/latest", { signal }) });
  const r = q.data;
  return (
    <div style={{ maxWidth: 680 }}>
      <PageHeader title="Android app" subtitle="Install Vayu on an Android phone. The app updates itself after that." />
      {q.isError && <LoadError error={q.error} what="the app download" onRetry={q.refetch} />}
      {q.isLoading && <p className="muted">Loading…</p>}
      {r && !r.version_code && <div className="card" role="status"><strong>No app build has been published yet.</strong><p className="muted">An Admin publishes one on the server; it shows here at once.</p></div>}
      {r?.version_code && (
        <div className="card">
          <h2 style={{ marginTop: 0 }}>Version {r.version_name}</h2>
          {r.notes && r.notes.length > 0 && <ul>{r.notes.map((n) => <li key={n}>{n}</li>)}</ul>}
          <a className="btn primary" href="/api/v1/app/download" download><Download size={16} aria-hidden /> Download the app{r.size ? ` (${mb(r.size)})` : ""}</a>
          <ol className="small" style={{ marginTop: 14 }}>
            <li>Open the downloaded file on the phone. Android may ask to allow installs from your browser: allow it for this install.</li>
            <li>Open Vayu and sign in with your own username.</li>
          </ol>
          {r.sha256 && <p className="muted small">SHA-256 checksum, to check the file is ours: <code className="mono" style={{ wordBreak: "break-all" }}>{r.sha256}</code></p>}
        </div>)}
    </div>
  );
}
