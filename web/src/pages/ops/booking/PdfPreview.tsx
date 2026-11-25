import { Maximize2, Minimize2, ZoomIn, ZoomOut } from "lucide-react";
import { useEffect, useState } from "react";

const ZOOMS = [50, 75, 100, 125, 150, 200];

/** The report shown in the page: a whole page at a glance by default, fit to width, or zoomed;
 *  full screen keeps these controls. The viewer's own toolbar is hidden: its download button would
 *  skip the log (Download PDF is the logged one). */
export function PdfPreview({ url }: { url: string }) {
  const [view, setView] = useState<"fit" | "width" | number>("fit");
  const [big, setBig] = useState(false); // fills the whole window (works in every browser)
  useEffect(() => {
    if (!big) return;
    const esc = (e: KeyboardEvent) => {
      if (e.key === "Escape") setBig(false);
    };
    document.addEventListener("keydown", esc);
    return () => document.removeEventListener("keydown", esc);
  }, [big]);
  const zoom = typeof view === "number" ? view : 100;
  const step = (by: number) => setView(ZOOMS[Math.max(0, Math.min(ZOOMS.length - 1, ZOOMS.indexOf(zoom) + by))]!);
  const hash = `toolbar=0&navpanes=0&${view === "fit" ? "view=Fit" : view === "width" ? "view=FitH" : `zoom=${view}`}`;
  return (
    <div className={`pdf-wrap${big ? " big" : ""}`}>
      <div className="bar pdf-tools">
        <div className="seg" role="group" aria-label="Page view">
          <button aria-pressed={view === "fit"} onClick={() => setView("fit")}>
            Whole page
          </button>
          <button aria-pressed={view === "width"} onClick={() => setView("width")}>
            Fit width
          </button>
        </div>
        <button className="sm" aria-label="Zoom out" disabled={typeof view === "number" && zoom <= ZOOMS[0]!} onClick={() => step(-1)}>
          <ZoomOut size={15} aria-hidden />
        </button>
        <span className="muted small" style={{ minWidth: 40, textAlign: "center" }}>
          {typeof view === "number" ? `${view}%` : "Auto"}
        </span>
        <button className="sm" aria-label="Zoom in" disabled={zoom >= ZOOMS[ZOOMS.length - 1]!} onClick={() => step(1)}>
          <ZoomIn size={15} aria-hidden />
        </button>
        <span className="grow" />
        <button className="sm" onClick={() => setBig(!big)}>
          {big ? (
            <>
              <Minimize2 size={15} aria-hidden /> Close full screen
            </>
          ) : (
            <>
              <Maximize2 size={15} aria-hidden /> Full screen
            </>
          )}
        </button>
      </div>
      {/* the key reloads the viewer: it reads its view settings only when it opens */}
      <iframe key={hash} className="pdf-frame" title="Report preview" src={`${url}#${hash}`} />
    </div>
  );
}
