import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../../../api/client";
import type { Definition } from "./model";
import { previewPlan } from "./model";
import { placeOf, type LayoutPage, type Patch } from "./Preview";

export type Whole = { pdf: string; pages: LayoutPage[]; checks?: { page: number; code: string; message: string }[] };
type Answer = Whole;
/** full: the whole report, the reader waits for it; page: one page, about a second;
 *  quiet: the whole report again behind the scenes, after the editing stopped. */
export type Drawing = "full" | "page" | "quiet" | null;

const IDLE_MS = 5000;

/** The designer's live preview. An edit to one page draws that page alone (about 1 s instead of
 *  the whole report's 4 or more) and swaps its sheets in; the whole report is drawn when there is
 *  nothing on screen yet, when the booking or version changes, when the edit touches more than
 *  one page, and quietly once the editing has stopped for 5 s. One draw at a time: while one
 *  runs, later edits wait and only the newest is drawn. */
export function usePreview(versionId: number | undefined, booking: string, def: Definition | null, onError: (e: unknown) => void) {
  const [whole, setWhole] = useState<Whole | null>(null);
  const [patches, setPatches] = useState<Record<number, Patch>>({});
  const [drawing, setDrawing] = useState<Drawing>(null);
  const s = useRef({
    busy: false,
    alive: true,
    key: "", // version + booking the sheets on screen belong to
    base: null as Definition | null, // the definition of the last draw
    wanted: null as Definition | null,
    wantedKey: "",
    whole: null as Whole | null,
    patches: {} as Record<number, Patch>,
    again: false, // a whole draw is due (idle, or someone asked for the whole PDF)
    waiters: [] as ((pdf: string | null) => void)[],
  });
  const fail = useRef(onError);
  fail.current = onError;

  const pump = useCallback(() => {
    const st = s.current;
    if (st.busy || !st.alive || !st.wanted || !versionId || !booking) return;
    const def_ = st.wanted;
    const key = st.wantedKey;
    let plan: number | "all" | null = key !== st.key || !st.whole ? "all" : previewPlan(st.base, def_);
    let place: { first: number; total: number } | null = null;
    if (typeof plan === "number") {
      place = placeOf(st.whole!.pages, st.patches, plan);
      if (!place) plan = "all"; // the page has no sheet on screen: nowhere to swap it in
    }
    let mode: Drawing = plan === "all" ? "full" : "page";
    if (st.again && plan !== "all") {
      plan = "all"; // nothing new to show, or one page: the whole report, behind the scenes
      mode = "quiet";
    }
    if (plan === null) return;
    st.again = false;
    st.busy = true;
    st.base = def_;
    setDrawing(mode);
    const body =
      plan === "all"
        ? { booking, definition: def_ }
        : { booking, definition: def_, only_page: plan, first_page: place!.first, total_pages: place!.total };
    api<Answer>(`pdf-template-versions/${versionId}/preview`, { body })
      .then((r) => {
        if (!st.alive || key !== st.wantedKey) return; // another booking or version was picked meanwhile
        if (plan === "all") {
          st.key = key;
          st.whole = r;
          st.patches = {};
          setWhole(r);
          setPatches({});
          st.waiters.splice(0).forEach((w) => w(st.wanted === def_ ? r.pdf : null));
        } else {
          st.patches = { ...st.patches, [plan as number]: { pdf: r.pdf, pages: r.pages } };
          setPatches(st.patches);
        }
      })
      .catch((e) => {
        st.base = null; // the next draw is a whole one
        st.again = false;
        st.waiters.splice(0).forEach((w) => w(null));
        if (st.alive) fail.current(e);
      })
      .finally(() => {
        st.busy = false;
        if (!st.alive) return;
        setDrawing(null);
        // a newer edit, booking or version arrived meanwhile, or a whole draw is due (never the
        // same failed draw again: that would loop)
        if (st.wanted !== def_ || st.wantedKey !== key || st.again) pump();
      });
  }, [versionId, booking]);

  useEffect(() => {
    const st = s.current;
    st.alive = true;
    return () => {
      st.alive = false;
    };
  }, []);

  // a new definition, booking or version: draw (or wait for the draw that is running)
  useEffect(() => {
    const st = s.current;
    st.wanted = def;
    st.wantedKey = `${versionId ?? ""}|${booking}`;
    pump();
  }, [def, versionId, booking, pump]);

  // the editing stopped: the whole report again, quietly (page numbers, contents, layout checks)
  const stale = Object.keys(patches).length > 0;
  useEffect(() => {
    if (!stale) return;
    const h = setTimeout(() => {
      s.current.again = true;
      pump();
    }, IDLE_MS);
    return () => clearTimeout(h);
  }, [stale, def, patches, pump]);

  /** The whole report's PDF with every edit in it (drawn now if single pages were swapped in). */
  const wholePdf = useCallback((): Promise<string | null> => {
    const st = s.current;
    if (!st.busy && st.whole && !Object.keys(st.patches).length && st.wanted === st.base) return Promise.resolve(st.whole.pdf);
    return new Promise((resolve) => {
      st.waiters.push(resolve);
      st.again = true;
      pump();
    });
  }, [pump]);

  return { whole, patches, drawing, stale, wholePdf };
}
