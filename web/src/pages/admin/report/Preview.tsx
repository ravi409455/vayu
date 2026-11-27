import { useEffect, useMemo, useRef, useState } from "react";

export type LayoutPart = { id: string; x: number; y: number; w: number; h: number };
/** section: which page of the template the sheet belongs to (its place in the definition). */
export type LayoutPage = { width: number; height: number; parts: LayoutPart[]; section?: number | null };
/** One template page drawn on its own, newer than the whole report on screen. */
export type Patch = { pdf: string; pages: LayoutPage[] };

type Sheet = { pdf: string; n: number; layout: LayoutPage; key: string };

/** The sheets to show: the whole report's, with each patched template page's sheets in place of
 *  its old ones (a patch may have more or fewer sheets, or none). */
export function sheetsOf(pdf: string, pages: LayoutPage[], patches: Record<number, Patch>, idOf: (pdf: string) => number): Sheet[] {
  const out: Sheet[] = [];
  const done = new Set<number>();
  pages.forEach((layout, i) => {
    const s = layout.section;
    const patch = s == null ? undefined : patches[s];
    if (s == null || !patch) {
      out.push({ pdf, n: i + 1, layout, key: `${idOf(pdf)}:${i + 1}` });
    } else if (!done.has(s)) {
      done.add(s);
      patch.pages.forEach((l, k) => out.push({ pdf: patch.pdf, n: k + 1, layout: l, key: `${idOf(patch.pdf)}:${k + 1}` }));
    }
  });
  return out;
}

/** Short ids for the PDFs on screen. An id is never given twice: a sheet's canvas is drawn again
 *  only when its key changes, so a new PDF reusing an old id would leave the old drawing up. */
export function pdfIds() {
  const ids = new Map<string, number>();
  let last = 0;
  return {
    idOf(p: string) {
      if (!ids.has(p)) ids.set(p, ++last);
      return ids.get(p)!;
    },
    keep(used: Set<string>) {
      for (const p of [...ids.keys()]) if (!used.has(p)) ids.delete(p);
    },
  };
}

/** The real PDF, drawn page by page, with an outline over every part: click one to change it.
 *  Smaller parts sit on top, so a click inside columns picks the inner part.
 *  patches: template pages drawn again on their own since the whole report was (the designer's
 *  quick preview); only their sheets are drawn again, the rest stay as they are. */
export function Preview({
  pdf,
  pages,
  patches,
  selected,
  names,
  onSelect,
}: {
  pdf: string;
  pages: LayoutPage[];
  patches?: Record<number, Patch>;
  selected: string | null;
  names: Record<string, string>;
  onSelect: (id: string) => void;
}) {
  const box = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(560);
  const [failed, setFailed] = useState(false);
  const canvases = useRef(new Map<string, HTMLCanvasElement>());
  const ids = useRef(pdfIds()); // each PDF on screen gets a short id (the key of its sheets)
  const sheets = useMemo(() => {
    const list = sheetsOf(pdf, pages, patches ?? {}, ids.current.idOf);
    ids.current.keep(new Set([pdf, ...list.map((s) => s.pdf)]));
    return list;
  }, [pdf, pages, patches]);

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
        const docs = new Map<string, Awaited<ReturnType<typeof pdfjs.getDocument>["promise"]>>();
        for (const s of sheets) {
          if (cancelled) return;
          const canvas = canvases.current.get(s.key);
          const drawn = `${s.key}@${width}`;
          if (!canvas || canvas.dataset.drawn === drawn) continue; // already shows this sheet at this size
          if (!docs.has(s.pdf)) {
            const bytes = Uint8Array.from(atob(s.pdf), (c) => c.charCodeAt(0));
            docs.set(s.pdf, await pdfjs.getDocument({ data: bytes }).promise);
          }
          const page = await docs.get(s.pdf)!.getPage(s.n);
          const base = page.getViewport({ scale: 1 });
          const ratio = window.devicePixelRatio || 1;
          const viewport = page.getViewport({ scale: (width / base.width) * ratio });
          canvas.width = viewport.width;
          canvas.height = viewport.height;
          await page.render({ canvasContext: canvas.getContext("2d")!, viewport }).promise;
          if (!cancelled) canvas.dataset.drawn = drawn;
        }
        setFailed(false);
      } catch {
        if (!cancelled) setFailed(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [sheets, width]);

  useEffect(() => {
    if (!selected) return;
    box.current?.querySelector(`[data-part="${CSS.escape(selected)}"]`)?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [selected]);

  if (failed) return <p className="muted small">The preview could not be drawn here. Use “Open the PDF” to see it.</p>;
  return (
    <div ref={box} className="rd-pages">
      {sheets.map((sheet, i) => {
        const pg = sheet.layout;
        const scale = width / pg.width;
        const parts = [...pg.parts].sort((a, b) => b.w * b.h - a.w * a.h);
        return (
          <div key={sheet.key} className="rd-page" style={{ width, height: pg.height * scale }}>
            <canvas
              ref={(c) => {
                if (c) canvases.current.set(sheet.key, c);
                else canvases.current.delete(sheet.key);
              }}
              style={{ width, height: pg.height * scale }}
              aria-label={`Page ${i + 1}`}
            />
            {parts.map((p) => (
              <button
                key={p.id}
                type="button"
                data-part={p.id}
                className={`rd-hit${selected === p.id ? " on" : ""}`}
                aria-label={`Select ${names[p.id] ?? "part"}`}
                title={names[p.id]}
                style={{ left: p.x * scale, top: p.y * scale, width: p.w * scale, height: p.h * scale }}
                onClick={(e) => {
                  e.stopPropagation();
                  onSelect(p.id);
                }}
              />
            ))}
            <span className="rd-pageno">{i + 1}</span>
          </div>
        );
      })}
    </div>
  );
}

/** Where a template page's sheets sit among those on screen: its first page number, and how many
 *  pages the report has (null: it has no sheet on screen). */
export function placeOf(pages: LayoutPage[], patches: Record<number, Patch>, section: number): { first: number; total: number } | null {
  const sections = sheetsOf("", pages, patches, () => 0).map((s) => s.layout.section);
  const at = sections.indexOf(section);
  return at < 0 ? null : { first: at + 1, total: sections.length };
}
