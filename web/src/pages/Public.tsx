import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api, ApiError } from "../api/client";
import { Logo } from "../ui/Logo";
import { fmtDay, fmtStamp } from "../lib/format";

type Verify = { valid: boolean; booking_id: string; car: string; type: string; date: string | null; overall_rating: string | null; revision: number; generated_at: string | null; current: boolean };

/** The page behind the QR code on a report: proves it is genuine, shows a summary only. */
export function VerifyPage() {
  const token = useParams().token!;
  const [v, setV] = useState<Verify | null>(null);
  const [bad, setBad] = useState(false);
  useEffect(() => { api<Verify>(`verify/${token}`).then(setV).catch(() => setBad(true)); }, [token]);
  return (
    <div className="public-page">
      <p><Logo /></p>
      <h1 style={{ fontSize: 22 }}>Report check</h1>
      {bad && <div className="card" role="alert"><strong>We could not find this report.</strong><p className="muted">The link may be wrong or the report was replaced.</p></div>}
      {v && (
        <div className="card">
          <div className="banner" style={{ background: "var(--ok-tint)", color: "var(--ok)", borderColor: "transparent" }}><strong>✓ This is a genuine Car C.I.D. report.</strong></div>
          <dl className="details">
            <dt>Booking ID</dt><dd>{v.booking_id}</dd>
            <dt>Car</dt><dd>{v.car}</dd>
            <dt>Inspection</dt><dd>{v.type}</dd>
            <dt>Inspected on</dt><dd>{v.date ? fmtDay(v.date) : "—"}</dd>
            <dt>Overall rating</dt><dd>{v.overall_rating ? v.overall_rating[0]!.toUpperCase() + v.overall_rating.slice(1) : "—"}</dd>
            <dt>Version</dt><dd>{v.revision}{v.generated_at ? `, made ${fmtStamp(v.generated_at)}` : ""}</dd>
          </dl>
          {!v.current && <p className="muted small">A newer version of this report is being prepared.</p>}
        </div>)}
    </div>
  );
}

/** "Preparing… x%" and then the download starts by itself. */
export function ZipPage() {
  const token = useParams().token!;
  const [state, setState] = useState<{ status: string; progress: number; url?: string } | null>(null);
  const [gone, setGone] = useState(false);
  useEffect(() => {
    let stop = false;
    const tick = async () => {
      try {
        const r = await api<{ status: string; progress: number; url?: string }>(`zips/${token}`, { query: { format: "json" } });
        if (stop) return;
        setState(r);
        if (r.status === "ready" && r.url) { window.location.assign(r.url); return; }
        setTimeout(tick, 1500);
      } catch (e) { if (!stop) setGone(true); void (e instanceof ApiError); }
    };
    void tick();
    return () => { stop = true; };
  }, [token]);
  return (
    <div className="public-page">
      <p><Logo /></p>
      <h1 style={{ fontSize: 22 }}>Download</h1>
      {gone ? <div className="card" role="alert"><strong>This download link is invalid, expired or has nothing in it.</strong></div> : (
        <div className="card" role="status">
          {state?.status === "ready" ? <p className="ok"><strong>Ready.</strong> Your download is starting… <a href={state.url}>Click here if it does not.</a></p>
            : <><p><strong>Preparing… {state?.progress ?? 0}%</strong></p><div className="progress"><div style={{ width: `${state?.progress ?? 0}%` }} /></div><p className="muted small">This takes a moment the first time. The file is kept for 7 days.</p></>}
        </div>)}
    </div>
  );
}
