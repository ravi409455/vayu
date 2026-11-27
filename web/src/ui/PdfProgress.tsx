import { useEffect, useState } from "react";

/** The PDF is being made (about 7 s, and the server can't say how far along it is): a bar that
 *  fills to 90% over the usual time, then creeps on until the PDF arrives and this goes away. */
// ponytail: a fixed 7 s guess; measure real render times if they drift far from it
export function PdfProgress({ seconds = 7, label = "Making the PDF…" }: { seconds?: number; label?: string }) {
  const [start] = useState(() => Date.now());
  const [now, setNow] = useState(start);
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(id);
  }, []);
  const s = (now - start) / 1000;
  const pct = s <= seconds ? (90 * s) / seconds : 90 + 9 * (1 - Math.exp(-(s - seconds) / seconds));
  const hint = s > seconds ? "Taking longer than usual" : `Usually about ${seconds} seconds`;
  return (
    <div className="pdf-progress">
      <div className="pdf-progress-top">
        <span>{label}</span>
        <span className="muted small">{hint}</span>
      </div>
      <div
        className="pdf-progress-track"
        role="progressbar"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(pct)}
        aria-valuetext={hint}
      >
        <div className="pdf-progress-fill" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}
