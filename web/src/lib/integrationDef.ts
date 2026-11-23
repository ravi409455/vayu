import type { BodyRow } from "../api/types";

/** A value as the server sends it for the picker. */
export type CatalogueEntry = { group: string; ref: string; label: string; type: string };
/** A string with {{ref}} tokens, taken apart: text and values alternate, always starting and ending with text. */
export type Part = { t: string } | { r: string };

const TOKEN = /\{\{\s*([A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_-]+)+)\s*\}\}/g;

export function parseParts(s: string): Part[] {
  const out: Part[] = [];
  let last = 0;
  for (const m of s.matchAll(TOKEN)) {
    out.push({ t: s.slice(last, m.index) }, { r: m[1]! });
    last = m.index! + m[0].length;
  }
  out.push({ t: s.slice(last) });
  return out;
}

export const joinParts = (parts: Part[]): string => parts.map((p) => ("t" in p ? p.t : `{{${p.r}}}`)).join("");

/** Put a value at `caret` inside the text part `at`. */
export function insertValue(value: string, at: number, caret: number, ref: string): { value: string; focus: number } {
  const parts = parseParts(value);
  const p = parts[at];
  if (!p || !("t" in p)) return { value, focus: 0 };
  parts.splice(at, 1, { t: p.t.slice(0, caret) }, { r: ref }, { t: p.t.slice(caret) });
  return { value: joinParts(parts), focus: at + 2 };
}

/** Take the value at part index `i` out. */
export function removeValue(value: string, i: number): string {
  const parts = parseParts(value);
  if (!parts[i] || "t" in parts[i]!) return value;
  parts.splice(i, 1);
  return joinParts(parts);
}

export const GROUP_LABEL: Record<string, string> = {
  booking: "Booking form", start: "Check-in (start)", inspection: "Inspection", end: "Wrap-up (end)",
  job: "Job", result: "Results", link: "Links", event: "Event",
};

export const EVENT_LABEL: Record<string, string> = {
  "booking.created": "Booking created", "booking.updated": "Booking updated (incl. assignment and stage)", "booking.deleted": "Booking deleted",
  "inspection.started": "Inspection started", "inspection.submitted": "Inspection submitted", "media.completed": "All media verified (Completed)",
  "pdf.ready": "PDF ready (also on regenerate)", "alert.conflict": "Conflict alert", "alert.stuck_upload": "Stuck upload alert",
};
/** The event in a few words, for lists (the editor uses the longer labels). */
export const eventWord = (e: string) => (EVENT_LABEL[e] ?? e).replace(/ \(.*\)$/, "");
/** A booking form can use the booking events only; an inspection form all of them. */
export const eventsFor = (formType: string): string[] =>
  Object.keys(EVENT_LABEL).filter((e) => formType !== "booking" || e.startsWith("booking."));
export const METHODS = ["POST", "PUT", "PATCH", "GET", "DELETE"];
export const hasBody = (method: string) => ["POST", "PUT", "PATCH"].includes(method);
export const MAX_DEPTH = 6;

// ---------------------------------------------------------------- body rows

export type RowKind = "value" | "fixed" | "group";
export const kindOf = (r: BodyRow): RowKind => (r.rows ? "group" : r.fixed !== undefined ? "fixed" : "value");

export function blankRow(kind: RowKind = "value"): BodyRow {
  return kind === "group" ? { key: "", rows: [] } : kind === "fixed" ? { key: "", fixed: "" } : { key: "", value: "" };
}

/** The same row as another kind (the key stays). */
export const asKind = (r: BodyRow, kind: RowKind): BodyRow => ({ ...blankRow(kind), key: r.key });

/** Does any value in these rows (or in text) use this ref? */
export function refsIn(text: string): string[] {
  return [...text.matchAll(TOKEN)].map((m) => m[1]!);
}

/** The text a value input shows for a ref: its picker label, or the ref itself when it is gone. */
export const labelFor = (catalogue: CatalogueEntry[], ref: string): { label: string; known: boolean } => {
  const e = catalogue.find((c) => c.ref === ref);
  return { label: e?.label ?? ref, known: !!e };
};

/** A fixed value in the type the person chose. */
export const typedFixed = (kind: "text" | "number" | "yesno", raw: string): string | number | boolean =>
  kind === "number" ? (raw.trim() === "" || Number.isNaN(Number(raw)) ? 0 : Number(raw)) : kind === "yesno" ? raw === "true" : raw;
export const fixedKind = (v: string | number | boolean | undefined): "text" | "number" | "yesno" =>
  typeof v === "number" ? "number" : typeof v === "boolean" ? "yesno" : "text";

/** What goes to the server: rows without empty keys left half-built. */
export function cleanRows(rows: BodyRow[]): BodyRow[] {
  return rows.filter((r) => r.key.trim() !== "").map((r) => (r.rows ? { key: r.key, rows: cleanRows(r.rows) } : r.fixed !== undefined ? { key: r.key, fixed: r.fixed } : { key: r.key, value: r.value ?? "", ...(r.as_text ? { as_text: true } : {}) }));
}

export const cleanPairs = (rows: { key: string; value: string }[]) => rows.filter((r) => r.key.trim() !== "");
