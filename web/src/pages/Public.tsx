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

type ZipState = { status: string; progress: number; url?: string };

/** Polls a ZIP link until it is ready, then starts the download. `path` null: not known yet. */
function useZip(path: string | null): { state: ZipState | null; gone: boolean } {
  const [state, setState] = useState<ZipState | null>(null);
  const [gone, setGone] = useState(false);
  useEffect(() => {
    if (!path) return;
    let stop = false;
    const tick = async () => {
      try {
        const r = await api<ZipState>(path, { query: { format: "json" } });
        if (stop) return;
        setState(r);
        if (r.status === "ready" && r.url) { window.location.assign(r.url); return; }
        setTimeout(tick, 1500);
      } catch (e) { if (!stop) setGone(true); void (e instanceof ApiError); }
    };
    void tick();
    return () => { stop = true; };
  }, [path]);
  return { state, gone };
}

function Progress({ state, note }: { state: ZipState | null; note: string }) {
  return state?.status === "ready"
    ? <p className="ok"><strong>Ready.</strong> Your download is starting… <a href={state.url}>Tap here if it does not.</a></p>
    : <><p><strong>Preparing… {state?.progress ?? 0}%</strong></p><div className="progress"><div style={{ width: `${state?.progress ?? 0}%` }} /></div><p className="muted small">{note}</p></>;
}

/** "Preparing… x%" and then the download starts by itself. */
export function ZipPage() {
  const token = useParams().token!;
  const { state, gone } = useZip(`zips/${token}`);
  return (
    <div className="public-page">
      <p><Logo /></p>
      <h1 style={{ fontSize: 22 }}>Download</h1>
      {gone ? <div className="card" role="alert"><strong>This download link is invalid, expired or has nothing in it.</strong></div> : (
        <div className="card" role="status"><Progress state={state} note="This takes a moment the first time. The file is kept for 7 days." /></div>)}
    </div>
  );
}

type ReportMedia = { booking_id: string; link: "photos" | "videos"; count: number; zip: string };

/** Behind "Download all photos / videos" in a report: one ZIP, in folders by section. The link
 *  works for as long as the report does. */
export function ReportMediaPage() {
  const { token, link } = useParams() as { token: string; link: string };
  const [info, setInfo] = useState<ReportMedia | null>(null);
  const [bad, setBad] = useState<string | null>(null);
  useEffect(() => {
    api<ReportMedia>(`verify/${token}/${link}`).then(setInfo)
      .catch((e) => setBad(e instanceof ApiError && e.code === "NO_MEDIA" ? `This report has no ${link}.`
        : e instanceof ApiError && e.code === "MEDIA_REMOVED" ? `These ${link} are no longer available. Files are kept on our server for a limited time after the inspection.`
          : "We could not find this report. The link may be wrong."));
  }, [token, link]);
  const { state, gone } = useZip(info?.zip ?? null);
  const what = link === "videos" ? "videos" : "photos";
  return (
    <div className="public-page">
      <p><Logo /></p>
      <h1 style={{ fontSize: 22 }}>{info ? `${info.count} ${info.count === 1 ? what.slice(0, -1) : what}` : `Inspection ${what}`}</h1>
      {info && <p className="muted">From the Car C.I.D. inspection, booking {info.booking_id}. They download as one ZIP file, in a folder for each part of the car.</p>}
      {bad || gone ? <div className="card" role="alert"><strong>{bad ?? "This download is not available right now. Please try again later."}</strong></div> : (
        <div className="card" role="status">
          <Progress state={state} note={what === "videos" ? "Videos are large: use Wi-Fi if you can. This takes a moment the first time." : "This takes a moment the first time."} />
          <p className="muted small">On a phone, open the file from your Downloads or Files app to see them.</p>
        </div>)}
    </div>
  );
}
