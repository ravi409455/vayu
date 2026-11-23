import { useEffect, useRef, useState } from "react";

export type LayoutPart = { id: string; x: number; y: number; w: number; h: number };
export type LayoutPage = { width: number; height: number; parts: LayoutPart[] };

/** The real PDF, drawn page by page, with an outline over every part: click one to change it.
 *  Smaller parts sit on top, so a click inside columns picks the inner part. */
export function Preview({ pdf, pages, selected, names, onSelect }: {
  pdf: string; pages: LayoutPage[]; selected: string | null; names: Record<string, string>; onSelect: (id: string) => void;
}) {
  const box = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(560);
  const [failed, setFailed] = useState(false);
  const canvases = useRef<(HTMLCanvasElement | null)[]>([]);

  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setWidth(Math.max(280, Math.min(900, e!.contentRect.width - 8))));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const pdfjs = await import("pdfjs-dist");
        const worker = await import("pdfjs-dist/build/pdf.worker.min.mjs?url");
        pdfjs.GlobalWorkerOptions.workerSrc = worker.default;
        const bytes = Uint8Array.from(atob(pdf), (c) => c.charCodeAt(0));
        const doc = await pdfjs.getDocument({ data: bytes }).promise;
        for (let n = 1; n <= doc.numPages && !cancelled; n++) {
          const page = await doc.getPage(n);
          const base = page.getViewport({ scale: 1 });
          const ratio = window.devicePixelRatio || 1;
          const viewport = page.getViewport({ scale: (width / base.width) * ratio });
          const canvas = canvases.current[n - 1];
          if (!canvas) continue;
          canvas.width = viewport.width;
          canvas.height = viewport.height;
          await page.render({ canvasContext: canvas.getContext("2d")!, viewport }).promise;
        }
        setFailed(false);
      } catch {
        if (!cancelled) setFailed(true);
      }
    })();
    return () => { cancelled = true; };
  }, [pdf, width]);

  useEffect(() => {
    if (!selected) return;
    box.current?.querySelector(`[data-part="${CSS.escape(selected)}"]`)?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [selected]);

  if (failed) return <p className="muted small">The preview could not be drawn here. Use “Open the PDF” to see it.</p>;
  return (
    <div ref={box} className="rd-pages">
      {pages.map((pg, i) => {
        const scale = width / pg.width;
        const parts = [...pg.parts].sort((a, b) => b.w * b.h - a.w * a.h);
        return (
          <div key={i} className="rd-page" style={{ width, height: pg.height * scale }}>
            <canvas ref={(c) => { canvases.current[i] = c; }} style={{ width, height: pg.height * scale }} aria-label={`Page ${i + 1}`} />
            {parts.map((p) => (
              <button key={p.id} type="button" data-part={p.id} className={`rd-hit${selected === p.id ? " on" : ""}`}
                aria-label={`Select ${names[p.id] ?? "part"}`} title={names[p.id]}
                style={{ left: p.x * scale, top: p.y * scale, width: p.w * scale, height: p.h * scale }}
                onClick={(e) => { e.stopPropagation(); onSelect(p.id); }} />
            ))}
            <span className="rd-pageno">{i + 1}</span>
          </div>
        );
      })}
    </div>
  );
}
