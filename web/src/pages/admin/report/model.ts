/** The report template (schema 2) as the designer edits it: pages holding parts. Pure functions,
 *  so every change is easy to test. The backend's apps/reports/schema.json is the full contract. */
import type { FormPage } from "../../../api/types";
import { NO_TEXT_TYPES } from "../../../lib/fieldTypes";

export type Row = { field: string; label?: string; show_if?: unknown; fallback?: string };
export type Cell = { field: string; fallback?: string } | { text: string };
export type Source =
  | { kind: "fields"; rows: Row[] }
  | { kind: "section"; section: string; exclude?: string[]; fallback?: string }
  | { kind: "defects" }
  | { kind: "grid"; columns: { label: string; width?: number }[]; rows: { label: string; show_if?: unknown; cells: Cell[] }[] };
export type PhotoSource = { kind: "fields"; fields: string[] } | { kind: "section"; section: string } | { kind: "issues" };
export type Box = { space_above?: number; space_below?: number; padding?: number; border?: "none" | "all" | "bottom" | "left"; border_width?: number; border_color?: string; background?: string; round?: boolean };
export type StyleRule = { when: "problem" | "ok" | "warn" | "bad" | "muted" | "minor" | "major" | "critical" | "not_checked" | "empty"; label?: string; value?: string; bold?: boolean; background?: string };
export type Look = { lines?: "all" | "rows" | "none"; height?: "compact" | "normal" | "roomy"; stripes?: boolean; label_width?: number; header?: boolean; headers?: string[]; emphasis?: boolean; kv?: boolean };
type Common = { id?: string; show_if?: unknown; hide_when_empty?: boolean; new_page?: boolean; keep_together?: boolean; keep_title?: boolean; box?: Box };
export type SharedRef = { key: string; revision: number };
export type Part = Common &
  (
    | { type: "table"; title?: string; source: Source; per_row?: 1 | 2 | 3 | 4; look?: Look; style_rules?: StyleRule[] }
    | {
        type: "photos";
        title?: string;
        source: PhotoSource;
        which?: "all" | "issues" | "first";
        per_row?: 1 | 2 | 3 | 4;
        shape?: "4:3" | "16:9" | "1:1" | "original";
        fit?: "fill" | "whole" | "top";
        caption?: "label" | "check" | "custom" | "none";
        caption_text?: string;
        frame?: { border?: "none" | "grey" | "brand"; round?: boolean; gap?: number };
      }
    | {
        type: "text";
        html: string;
        columns?: 1 | 2;
        size?: "fine" | "small" | "normal" | "large" | "title";
        align?: "left" | "center" | "right" | "justify";
      }
    | { type: "columns"; columns: { width?: number; parts: Part[] }[]; gap?: number; align?: "top" | "middle" }
    | { type: "verify"; size?: number }
    | { type: "button"; link: LinkName; label: string; align?: "left" | "center" | "right" }
    | { type: "contents"; title?: string; columns?: 1 | 2 }
    | { type: "page_break" }
    | { type: "spacer"; height?: number }
    | { type: "html"; title?: string; html: string; css?: string }
    | { type: "snippet"; ref: SharedRef }
  );
export type PartType = Part["type"];
/** The report's own links: the verify page, and one ZIP of every photo or every video. */
export type LinkName = "photos" | "videos" | "verify";
export const LINKS: [LinkName, string, string][] = [
  ["photos", "Download all photos", "Download photos"],
  ["videos", "Download all videos", "Download videos"],
  ["verify", "Verify this report", "Verify this report"]];
export type ReportPage = { id?: string; title: string; style?: "normal" | "cover" | "full"; show_if?: unknown; parts: Part[] };
export type SlotItem = { text: string } | { image: string; height?: number; tile?: boolean };
export type Band = { left?: SlotItem[]; center?: SlotItem[]; right?: SlotItem[]; background?: "none" | "brand"; height?: number };
export type Definition = {
  schema: 2; filename?: string; pages: ReportPage[]; theme_ref?: SharedRef;
  paper?: { size?: "A4" | "Letter"; orientation?: "portrait" | "landscape"; margins?: { top?: number; right?: number; bottom?: number; left?: number } };
  theme?: { colors?: Partial<Record<"brand" | "text" | "ok" | "warn" | "bad" | "muted", string>>; size?: number; fonts?: { body?: string; headings?: string } };
  bands?: Partial<Record<"normal" | "cover", { header?: Band; footer?: Band }>>;
  watermark?: { image: string; opacity?: number; width?: number };
};

let counter = 0;
/** A short id, unique enough inside one template. */
export function uid(): string {
  counter = (counter + 1) % 1296;
  return Date.now().toString(36).slice(-5) + counter.toString(36).padStart(2, "0") + Math.random().toString(36).slice(2, 4);
}

/** Every page and part gets an id (the designer selects and the preview highlights by id). */
export function withIds(d: Definition): Definition {
  const fix = (parts: Part[]): Part[] => parts.map((p) => {
    const q = { ...p, id: p.id ?? uid() } as Part;
    return q.type === "columns" ? { ...q, columns: q.columns.map((c) => ({ ...c, parts: fix(c.parts) })) } : q;
  });
  return { ...d, pages: (d.pages ?? []).map((pg) => ({ ...pg, id: pg.id ?? uid(), parts: fix(pg.parts ?? []) })) };
}

type Where = { list: Part[]; index: number; set: (parts: Part[]) => Definition };

/** Where a part lives (its list and position), and how to write that list back. */
export function locate(d: Definition, id: string): Where | null {
  const inParts = (parts: Part[], write: (p: Part[]) => Definition): Where | null => {
    const index = parts.findIndex((p) => p.id === id);
    if (index >= 0) return { list: parts, index, set: write };
    for (const [k, p] of parts.entries()) {
      if (p.type !== "columns") continue;
      for (const [c, col] of p.columns.entries()) {
        const found = inParts(col.parts, (np) => write(parts.map((x, j) => (j === k ? { ...p, columns: p.columns.map((cc, ci) => (ci === c ? { ...cc, parts: np } : cc)) } as Part : x))));
        if (found) return found;
      }
    }
    return null;
  };
  for (const [i, page] of d.pages.entries()) {
    const found = inParts(page.parts, (np) => ({ ...d, pages: d.pages.map((pg, j) => (j === i ? { ...pg, parts: np } : pg)) }));
    if (found) return found;
  }
  return null;
}

export function findPart(d: Definition, id: string): Part | null {
  const w = locate(d, id);
  return w ? w.list[w.index]! : null;
}

/** A PDF template as the list sends it, and one of its versions. */
export type Template = { id: number; form: number; form_key: string; versions: { id: number; number: number; status: string }[] };
export type TVersion = { id: number; template: number; number: number; status: string; definition: Definition; row_version: number };

/** A deep copy with every "id" dropped (withIds gives the copy fresh ones). */
export const withoutIds = <T,>(x: T): T => JSON.parse(JSON.stringify(x, (k, v: unknown) => (k === "id" ? undefined : v))) as T;
/** Copies of these parts with fresh ids, to put beside or instead of the originals. */
export const freshCopies = (parts: Part[]): Part[] => withIds({ schema: 2, pages: [{ title: "", parts: withoutIds(parts) }] }).pages[0]!.parts;

/** Every part of the definition with its name (for the preview's outlines). */
export function partNames(d: Definition, sections: Record<string, string> = {}, shared: Record<string, string> = {}): Record<string, string> {
  const out: Record<string, string> = {};
  const walk = (parts: Part[]) => parts.forEach((p) => { out[p.id!] = partName(p, sections, shared); if (p.type === "columns") p.columns.forEach((c) => walk(c.parts)); });
  d.pages.forEach((pg) => walk(pg.parts));
  return out;
}

/** The page that holds this part (also inside columns). */
export function pageOf(d: Definition, partId: string): ReportPage | null {
  return d.pages.find((pg) => JSON.stringify(pg.parts).includes(`"id":"${partId}"`)) ?? null;
}

export function updatePart(d: Definition, id: string, patch: Partial<Part>): Definition {
  const w = locate(d, id);
  return w ? w.set(w.list.map((p, i) => (i === w.index ? ({ ...p, ...patch } as Part) : p))) : d;
}

export function removePart(d: Definition, id: string): Definition {
  const w = locate(d, id);
  return w ? w.set(w.list.filter((_, i) => i !== w.index)) : d;
}

/** Move a part up or down among its neighbours. */
export function shiftPart(d: Definition, id: string, by: -1 | 1): Definition {
  const w = locate(d, id);
  if (!w) return d;
  const j = w.index + by;
  if (j < 0 || j >= w.list.length) return d;
  const out = [...w.list];
  [out[w.index], out[j]] = [out[j]!, out[w.index]!];
  return w.set(out);
}

/** Move a part to another position, in the same list (what dragging does). */
export function movePart(d: Definition, id: string, overId: string): Definition {
  const a = locate(d, id), b = locate(d, overId);
  if (!a || !b || a.list !== b.list) return d;
  const out = [...a.list];
  const [p] = out.splice(a.index, 1);
  out.splice(b.index, 0, p!);
  return a.set(out);
}

export function addPart(d: Definition, pageId: string, part: Part, afterId?: string | null): Definition {
  if (afterId) {
    const w = locate(d, afterId);
    if (w) return w.set([...w.list.slice(0, w.index + 1), part, ...w.list.slice(w.index + 1)]);
  }
  return { ...d, pages: d.pages.map((pg) => (pg.id === pageId ? { ...pg, parts: [...pg.parts, part] } : pg)) };
}

export function updatePage(d: Definition, id: string, patch: Partial<ReportPage>): Definition {
  return { ...d, pages: d.pages.map((pg) => (pg.id === id ? { ...pg, ...patch } : pg)) };
}

export function movePage(d: Definition, id: string, overId: string): Definition {
  const from = d.pages.findIndex((p) => p.id === id), to = d.pages.findIndex((p) => p.id === overId);
  if (from < 0 || to < 0) return d;
  const pages = [...d.pages];
  const [p] = pages.splice(from, 1);
  pages.splice(to, 0, p!);
  return { ...d, pages };
}

export const PART_LABEL: Record<PartType, string> = {
  table: "Table of checks", photos: "Photos", text: "Text", columns: "Side by side", verify: "Verify code", button: "Button link",
  contents: "Contents list", page_break: "Page break", spacer: "Space", html: "Custom HTML", snippet: "Shared part",
};

/** What the pages list calls a part: its title, its text, or what it is. */
export function partName(p: Part, sections: Record<string, string> = {}, shared: Record<string, string> = {}): string {
  if ("title" in p && p.title) return p.title;
  if (p.type === "snippet") return shared[p.ref.key] ?? p.ref.key;
  if (p.type === "text") return p.html.replace(/<[^>]+>/g, " ").replace(/\{\{\s*([\w.]+)\s*\}\}/g, "$1").replace(/\s+/g, " ").trim().slice(0, 40) || "Text";
  if ((p.type === "table" || p.type === "photos") && p.source.kind === "section") {
    const name = sections[p.source.section] ?? p.source.section.split(".")[1]!;
    return p.type === "photos" ? `${name} photos` : name;
  }
  if (p.type === "table" && p.source.kind === "defects") return "All problems found";
  if (p.type === "photos" && p.source.kind === "issues") return "All issue photos";
  return PART_LABEL[p.type];
}

/** A starting part of each kind, as "+ Add to this page" makes it. */
export function newPart(type: PartType, firstSection?: string): Part {
  const id = uid();
  switch (type) {
    case "table": return firstSection ? { id, type, title: "", look: { header: true }, source: { kind: "section", section: firstSection } } : { id, type, title: "", source: { kind: "fields", rows: [] } };
    case "photos": return { id, type, title: "", per_row: 3, caption: "check", source: firstSection ? { kind: "section", section: firstSection } : { kind: "issues" } };
    case "text": return { id, type, html: "<p>Text</p>" };
    case "columns": return { id, type, gap: 6, columns: [{ parts: [] }, { parts: [] }] };
    case "verify": return { id, type, size: 50 };
    case "button": return { id, type, link: "photos", label: LINKS[0]![2] };
    case "contents": return { id, type, columns: 2 };
    case "spacer": return { id, type, height: 10 };
    case "html": return { id, type, html: '<div class="note">\n  <p>Booking {{ sys.booking_id }}</p>\n</div>', css: ".note { border-left: 1mm solid var(--brand); padding-left: 3mm }" };
    default: return { id, type: "page_break" };
  }
}

/** "+ Add page": a ready page made from one page of the form: its heading, a table for each
 *  section, then the photos of anything found wrong. */
export function pageFromForm(page: FormPage): ReportPage {
  const parts: Part[] = [{ id: uid(), type: "text", html: `<h2>${escape(page.title)}</h2>` }];
  for (const s of page.sections) {
    const ref = `inspection.${s.key}`;
    const multi = page.sections.length > 1;
    const hasChecks = s.fields.some((f) => !NO_TEXT_TYPES.includes(f.type));
    const hasPhotos = s.fields.some((f) => f.type === "photo");
    if (hasChecks) parts.push({ id: uid(), type: "table", title: multi ? s.title : "", look: { header: true }, source: { kind: "section", section: ref } });
    if (hasPhotos) parts.push({ id: uid(), type: "photos", title: "", per_row: 3, caption: "check", which: hasChecks ? "issues" : "all", source: { kind: "section", section: ref } });
  }
  return { id: uid(), title: page.title, style: "normal", parts };
}

export function blankPage(kind: "blank" | "divider" | "verify", title?: string): ReportPage {
  if (kind === "divider") return { id: uid(), title: title ?? "Detailed report", style: "full", parts: [
    { id: uid(), type: "spacer", height: 80 },
    { id: uid(), type: "text", size: "title", align: "center", html: "<p>Detailed Report</p>" },
    { id: uid(), type: "spacer", height: 10 },
    { id: uid(), type: "contents", columns: 2 }] };
  if (kind === "verify") return { id: uid(), title: "Verify this report", style: "normal", parts: [
    { id: uid(), type: "spacer", height: 18 },
    { id: uid(), type: "text", align: "center", html: "<h2>Verify this report</h2><p>Scan the code or open the link to see this report as it was issued.</p>" },
    { id: uid(), type: "verify", size: 60 }] };
  return { id: uid(), title: title ?? "New page", style: "normal", parts: [] };
}

/** Fill a grid's cells from field keys that follow `<prefix>_<row>_<column>`: rows and columns
 *  are named by their labels, made into keys ("Driver front" -> driver_front). */
export function fillGrid(source: Extract<Source, { kind: "grid" }>, prefix: string, known: Set<string>): Extract<Source, { kind: "grid" }> {
  const slug = (t: string) => t.toLowerCase().replace(/\([^)]*\)/g, "").replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "");
  return { ...source, rows: source.rows.map((r) => ({ ...r, cells: source.columns.map((c, i) => {
    const key = [prefix, slug(r.label), slug(c.label)].filter(Boolean).join("_");
    return known.has(key) ? { field: `inspection.${key}` } : (r.cells[i] ?? { text: "" });
  }) })) };
}

/** A shared part (e.g. the disclaimer) placed in a page. */
export function sharedPart(ref: SharedRef): Part {
  return { id: uid(), type: "snippet", ref };
}

/** Swap one field or section for another in a part, e.g. a suggestion for a field the form
 *  lacks: "inspection.odo" -> "inspection.odometer", in rows, cells, placeholders and exclusions. */
export function replaceRef(p: Part, from: string, to: string): Part {
  const [, fromKey] = from.split("."), [, toKey] = to.split(".");
  const placeholder = new RegExp(`\\{\\{\\s*${from.replace(/\./g, "\\.")}\\s*\\}\\}`, "g");
  return JSON.parse(JSON.stringify(p, (k, v: unknown) => {
    if (k === "exclude" && Array.isArray(v) && from.startsWith("inspection.")) return v.map((x) => (x === fromKey ? toKey : x));
    if (typeof v !== "string") return v;
    return v === from ? to : v.replace(placeholder, `{{ ${to} }}`);
  })) as Part;
}

/** Put a shared part's own parts in its place (fresh ids), to change them in this template only. */
export function unlinkShared(d: Definition, id: string, parts: Part[]): Definition {
  const w = locate(d, id);
  if (!w) return d;
  const fresh = freshCopies(parts);
  return w.set([...w.list.slice(0, w.index), ...fresh, ...w.list.slice(w.index + 1)]);
}

/** The theme settings a shared theme holds. */
export const THEME_KEYS = ["theme", "bands", "watermark"] as const;
export function themeOf(d: Definition): Pick<Definition, (typeof THEME_KEYS)[number]> {
  return Object.fromEntries(THEME_KEYS.filter((k) => d[k] !== undefined).map((k) => [k, d[k]]));
}
export function withoutTheme(d: Definition): Definition {
  const out = { ...d };
  for (const k of THEME_KEYS) delete out[k];
  return out;
}

function escape(t: string): string {
  return t.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
