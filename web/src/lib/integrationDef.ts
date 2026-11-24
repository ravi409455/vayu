/** A value as the server sends it for the picker. */
export type CatalogueEntry = { group: string; ref: string; label: string; type: string };
/** A string with {{ref}} tokens, taken apart: text and values alternate, always starting and ending with text. */
export type Part = { t: string } | { r: string };

const TOKEN = /\{\{\s*([A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_-]+)+)(?:\s*\|\s*text)?\s*\}\}/g;

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
  "pdf.ready": "PDF ready (each time it is made again)", "alert.conflict": "Conflict alert", "alert.stuck_upload": "Stuck upload alert",
};
/** The event in a few words, for lists (the editor uses the longer labels). */
export const eventWord = (e: string) => (EVENT_LABEL[e] ?? e).replace(/ \(.*\)$/, "");
/** A booking form can use the booking events only; an inspection form all of them. */
export const eventsFor = (formType: string): string[] =>
  Object.keys(EVENT_LABEL).filter((e) => formType !== "booking" || e.startsWith("booking."));
/** Why the value list holds what it holds: the form and the event decide which values exist. */
export function pickerHint(formType: string, event: string): string {
  if (formType === "booking") return "The booking form can use booking values, job facts and event details. For inspection answers, results and PDF links, choose an inspection form.";
  const later = "Inspection answers, results and links come with the later events (from “Inspection submitted”; PDF and ZIP links from “PDF ready”).";
  if (event === "booking.deleted") return "Nothing of a deleted booking is sent except its Booking ID and the event details.";
  if (["booking.created", "alert.conflict", "alert.stuck_upload"].includes(event)) return `For “${eventWord(event)}” only booking values, job facts and event details exist yet. ${later} Pick one of those events to use them.`;
  if (event === "inspection.started") return `Check-in answers exist now. ${later}`;
  if (["inspection.submitted", "media.completed"].includes(event)) return "Inspection answers, results and photo links exist now. The PDF link comes with “PDF ready”.";
  return "";
}
export const METHODS = ["POST", "PUT", "PATCH", "GET", "DELETE"];
export const hasBody = (method: string) => ["POST", "PUT", "PATCH"].includes(method);
export const MAX_DEPTH = 6;

// ---------------------------------------------------------------- the JSON body

/** The `{{` the caret is inside of (no `}}` or line break since it), and what was typed after it. */
export function jsonOpenToken(text: string, caret: number): { start: number; fragment: string } | null {
  const before = text.slice(0, caret);
  const start = before.lastIndexOf("{{");
  if (start < 0) return null;
  const typed = before.slice(start + 2);
  if (/[}\n"]/.test(typed)) return null;
  return { start, fragment: typed.replace(/\|.*$/, "").trim() };
}

/** The values whose label, key or group contains every word typed so far. */
export function matchValues(catalogue: CatalogueEntry[], fragment: string): CatalogueEntry[] {
  const words = fragment.toLowerCase().split(/\s+/).filter(Boolean);
  return catalogue.filter((e) => words.every((w) => `${e.label} ${e.ref} ${GROUP_LABEL[e.group] ?? ""}`.toLowerCase().includes(w)));
}

/** What a new custom body starts as. */
export const STARTER_BODY = '{\n  "ref": "{{job.booking_id}}",\n  "event": "{{event.name}}"\n}';

export const cleanPairs = (rows: { key: string; value: string }[]) => rows.filter((r) => r.key.trim() !== "");

/** The saved body as text for the editor. */
export const bodyText = (body: unknown): string =>
  body && typeof body === "object" && Object.keys(body).length > 0 ? JSON.stringify(body, null, 2) : "";

/** Parse the editor's text: the JSON, or why not. */
export function parseBody(text: string): { ok: true; body: unknown } | { ok: false; error: string } {
  try {
    const body = JSON.parse(text);
    if (body === null || typeof body !== "object") return { ok: false, error: "The body must be a JSON object { … } or list [ … ]." };
    return { ok: true, body };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : "This is not valid JSON." };
  }
}

/** The text a value input shows for a ref: its picker label, or the ref itself when it is gone. */
export const labelFor = (catalogue: CatalogueEntry[], ref: string): { label: string; known: boolean } => {
  const e = catalogue.find((c) => c.ref === ref);
  return { label: e?.label ?? ref, known: !!e };
};
