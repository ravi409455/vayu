import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, ApiError } from "../api/client";
import { fmtDay, fmtStamp } from "../lib/format";

/** Customers see the Car C.I.D. brand on these pages, never the staff app's name. */
function BrandLogo() {
  useEffect(() => {
    document.title = "Car C.I.D.";
  }, []);
  return (
    <p className="brand-logo">
      <img src="/carcid-logo.png" alt="" width={44} height={44} />
      <strong>Car C.I.D.</strong>
    </p>
  );
}

/** A report or ZIP token as the server makes them. Anything else never reaches the API (F-063). */
const TOKEN = /^[A-Za-z0-9_:-]{1,200}$/; // report: url-safe base64; ZIP: signed "id:time:signature"
export const validToken = (t: string | undefined): t is string => !!t && TOKEN.test(t);
/** Only a download on https (or plain http while the page itself is, on a test server) is followed. */
export function safeDownload(url: string | undefined, here = window.location): string | null {
  if (!url) return null;
  try {
    const u = new URL(url, here.href);
    return u.protocol === "https:" || (u.protocol === "http:" && here.protocol === "http:") ? u.href : null;
  } catch {
    return null;
  }
}
const notFound = (e: unknown) => e instanceof ApiError && (e.status === 404 || e.status === 410);

type Verify = {
  valid: boolean;
  booking_id: string;
  car: string;
  type: string;
  date: string | null;
  overall_rating: string | null;
  revision: number;
  generated_at: string | null;
  current: boolean;
};

/** The page behind the QR code on a report: proves it is genuine, shows a summary only. */
export function VerifyPage() {
  const { token } = useParams();
  const [v, setV] = useState<Verify | null>(null);
  const [problem, setProblem] = useState<"missing" | "down" | null>(validToken(token) ? null : "missing");
  const [tries, setTries] = useState(0);
  useEffect(() => {
    if (!validToken(token)) return;
    setProblem(null);
    api<Verify>(`verify/${encodeURIComponent(token)}`)
      .then(setV)
      .catch((e) => setProblem(notFound(e) ? "missing" : "down"));
  }, [token, tries]);
  return (
    <main className="public-page">
      <BrandLogo />
      <h1 style={{ fontSize: 22 }}>Report check</h1>
      {!v && !problem && (
        <p className="muted" role="status">
          Checking…
        </p>
      )}
      {problem === "missing" && (
        <div className="card" role="alert">
          <strong>We could not find this report.</strong>
          <p className="muted">Check that the link or QR code is the one printed on the report.</p>
        </div>
      )}
      {problem === "down" && (
        <div className="card" role="alert">
          <strong>We could not check this report right now.</strong>
          <p className="muted">This is a problem on our side, not with the report. Please try again in a moment.</p>
          <button onClick={() => setTries((n) => n + 1)}>Try again</button>
        </div>
      )}
      {v && (
        <div className="card">
          <div className="banner" style={{ background: "var(--ok-tint)", color: "var(--ok)", borderColor: "transparent" }}>
            <strong>✓ This is a genuine Car C.I.D. report.</strong>
          </div>
          <dl className="details">
            <dt>Booking ID</dt>
            <dd>{v.booking_id}</dd>
            <dt>Car</dt>
            <dd>{v.car}</dd>
            <dt>Inspection</dt>
            <dd>{v.type}</dd>
            <dt>Inspected on</dt>
            <dd>{v.date ? fmtDay(v.date) : "—"}</dd>
            <dt>Overall rating</dt>
            <dd>{v.overall_rating ? v.overall_rating[0]!.toUpperCase() + v.overall_rating.slice(1) : "—"}</dd>
            <dt>Version</dt>
            <dd>
              {v.revision}
              {v.generated_at ? `, made ${fmtStamp(v.generated_at)}` : ""}
            </dd>
          </dl>
          {!v.current && <p className="muted small">A newer version of this report is being prepared.</p>}
        </div>
      )}
    </main>
  );
}

type ZipState = { status: string; progress: number; url?: string };

/** Polls a ZIP link until it is ready, then starts the download. `path` null: not known yet.
 *  It slows down as it waits (1.5 s up to 5 s, so two tabs stay under the server's limit), keeps
 *  going through a busy or failing server, and stops only when the link does not exist (F-176). */
export function useZip(path: string | null): { state: ZipState | null; gone: boolean; slow: boolean } {
  const [state, setState] = useState<ZipState | null>(null);
  const [gone, setGone] = useState(false);
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    if (!path) return;
    let stop = false,
      wait = 1500,
      timer: ReturnType<typeof setTimeout>;
    const again = (ms: number) => {
      timer = setTimeout(tick, ms);
    };
    const tick = async () => {
      try {
        const r = await api<ZipState>(path, { query: { format: "json" } });
        if (stop) return;
        setState(r);
        setSlow(false);
        const url = r.status === "ready" ? safeDownload(r.url) : null;
        if (url) {
          window.location.assign(url);
          return;
        }
        wait = Math.min(5000, wait * 1.5);
        again(wait);
      } catch (e) {
        if (stop) return;
        if (notFound(e)) {
          setGone(true);
          return;
        }
        setSlow(true); // too many tries, or the server is busy: keep waiting
        wait = Math.min(10_000, wait * 2);
        again(wait);
      }
    };
    void tick();
    return () => {
      stop = true;
      clearTimeout(timer);
    };
  }, [path]);
  return { state, gone, slow };
}

function Progress({ state, note, slow }: { state: ZipState | null; note: string; slow: boolean }) {
  const pct = state?.progress ?? 0;
  const url = state?.status === "ready" ? safeDownload(state.url) : null;
  return url ? (
    <p className="ok">
      <strong>Ready.</strong> Your download is starting…{" "}
      <a className="text-link" href={url}>
        Click or tap here if it does not start.
      </a>
    </p>
  ) : (
    <>
      <p>
        <strong>Preparing… {pct}%</strong>
      </p>
      <div
        className="progress"
        role="progressbar"
        aria-label="Preparing the download"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={pct}
      >
        <div style={{ width: `${pct}%` }} />
      </div>
      <p className="muted small">{slow ? "Still working on it. Keep this page open." : note}</p>
    </>
  );
}

/** "Preparing… x%" and then the download starts by itself. */
export function ZipPage() {
  const { token } = useParams();
  const { state, gone, slow } = useZip(validToken(token) ? `zips/${encodeURIComponent(token)}` : null);
  return (
    <main className="public-page">
      <BrandLogo />
      <h1 style={{ fontSize: 22 }}>Download</h1>
      {gone || !validToken(token) ? (
        <div className="card" role="alert">
          <strong>This download link is invalid, expired or has nothing in it.</strong>
        </div>
      ) : (
        <div className="card" role="status">
          <Progress state={state} slow={slow} note="This takes a moment the first time. The file is kept for 7 days." />
        </div>
      )}
    </main>
  );
}

type ReportMedia = { booking_id: string; link: "photos" | "videos"; count: number; zip: string };

/** Behind "Download all photos / videos" in a report: one ZIP, in folders by section. The link
 *  works for 30 days after the report is first made (then 410 LINK_EXPIRED, R-09). */
export function ReportMediaPage() {
  const { token, link } = useParams();
  const ok = validToken(token) && (link === "photos" || link === "videos");
  const [info, setInfo] = useState<ReportMedia | null>(null);
  const [bad, setBad] = useState<string | null>(ok ? null : "We could not find this report. The link may be wrong.");
  useEffect(() => {
    if (!ok) return;
    api<ReportMedia>(`verify/${encodeURIComponent(token)}/${link}`)
      .then(setInfo)
      .catch((e) =>
        setBad(
          e instanceof ApiError && e.code === "NO_MEDIA"
            ? `This report has no ${link}.`
            : e instanceof ApiError && e.code === "LINK_EXPIRED"
              ? "This link has expired. Photo and video links work for 30 days after the report is made. Ask Car C.I.D. for a new report."
              : e instanceof ApiError && e.code === "MEDIA_REMOVED"
                ? `These ${link} are no longer available. Files are kept on our server for a limited time after the inspection.`
                : notFound(e)
                  ? "We could not find this report. The link may be wrong."
                  : "We could not get the download ready right now. Please try again in a moment.",
        ),
      );
  }, [token, link, ok]);
  // the server's own ZIP path only: a "zips/<token>" link it gave, nothing else
  const zip = info && /^zips\/[A-Za-z0-9_:-]{1,200}$/.test(info.zip) ? info.zip : null;
  const { state, gone, slow } = useZip(zip);
  const what = link === "videos" ? "videos" : "photos";
  return (
    <main className="public-page">
      <BrandLogo />
      <h1 style={{ fontSize: 22 }}>{info ? `${info.count} ${info.count === 1 ? what.slice(0, -1) : what}` : `Inspection ${what}`}</h1>
      {info && (
        <p className="muted">
          From the Car C.I.D. inspection, booking {info.booking_id}. They download as one ZIP file, in a folder for each part of the car.
        </p>
      )}
      {bad || gone ? (
        <div className="card" role="alert">
          <strong>{bad ?? "This download is not available any more."}</strong>
        </div>
      ) : (
        <div className="card" role="status">
          <Progress
            state={state}
            slow={slow}
            note={
              what === "videos"
                ? "Videos are large: use Wi-Fi if you can. This takes a moment the first time."
                : "This takes a moment the first time."
            }
          />
          <p className="muted small">On a phone, open the file from your Downloads or Files app to see them.</p>
        </div>
      )}
      {validToken(token) && (
        <p className="small">
          <Link className="text-link" to={`/verify/${encodeURIComponent(token)}`}>
            Check this report is genuine
          </Link>
        </p>
      )}
    </main>
  );
}
