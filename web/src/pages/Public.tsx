import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api, ApiError } from "../api/client";
import { Logo } from "../ui/Logo";

type Verify = { valid: boolean; booking_id: string; car: string; type: string; date: string | null; overall_rating: string | null; revision: number; generated_at: string | null; current: boolean };

/** The page behind the QR code on a report: proves it is genuine, shows a summary only. */
export function VerifyPage() {
  const token = useParams().token!;
  const [v, setV] = useState<Verify | null>(null);
  const [bad, setBad] = useState(false);
  useEffect(() => { api<Verify>(`verify/${token}`).then(setV).catch(() => setBad(true)); }, [token]);
  return (
    <div style={{ maxWidth: 480, margin: "10vh auto", padding: 16 }}>
      <p><Logo /></p>
      <h1>Report check</h1>
      {bad && <div className="card" role="alert"><strong>We could not find this report.</strong><p className="muted">The link may be wrong or the report was replaced.</p></div>}
      {v && (
        <div className="card">
          <p className="ok"><strong>✓ This is a genuine Car C.I.D. report.</strong></p>
          <table><tbody>
            <tr><th>Booking ID</th><td>{v.booking_id}</td></tr><tr><th>Car</th><td>{v.car}</td></tr><tr><th>Inspection</th><td>{v.type}</td></tr>
            <tr><th>Date</th><td>{v.date ?? "—"}</td></tr><tr><th>Overall rating</th><td>{v.overall_rating ?? "—"}</td></tr><tr><th>Revision</th><td>{v.revision}</td></tr></tbody></table>
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
    <div style={{ maxWidth: 480, margin: "10vh auto", padding: 16 }}>
      <p><Logo /></p>
      <h1>Download</h1>
      {gone ? <div className="card" role="alert"><strong>This download link is invalid, expired or has nothing in it.</strong></div> : (
        <div className="card" role="status">
          {state?.status === "ready" ? <p className="ok"><strong>Ready.</strong> Your download is starting… <a href={state.url}>Click here if it does not.</a></p>
            : <><p><strong>Preparing… {state?.progress ?? 0}%</strong></p><div className="progress"><div style={{ width: `${state?.progress ?? 0}%` }} /></div><p className="muted small">This takes a moment the first time. The file is kept for 7 days.</p></>}
        </div>)}
    </div>
  );
}
