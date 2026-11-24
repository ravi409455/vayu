// How a booking is drawn on Today's "Schedule by expert": where its box starts and ends, whether
// it was late, and what the hover says. All times are hours into the day (10.5 = 10:30).
import type { Booking } from "../api/types";
import { fmtTime, isoDay } from "./format";

export const PLANNED_HOURS = 1;            // a job that has not started: booked time, one hour
export const LATE_AFTER_HOURS = 15 / 60;   // started more than 15 minutes after the booked time
const MIN_HOURS = 0.25;                    // a job that just started is still a box you can see

export type Span = {
  start: number; end: number;
  kind: "planned" | "running" | "finished";
  late: number;                            // minutes after the booked time it really started; 0 = not late
};

export const hoursOf = (t: unknown): number | null => {
  const m = typeof t === "string" ? t.match(/^(\d{1,2}):(\d{2})/) : null;
  return m ? Number(m[1]) + Number(m[2]) / 60 : null;
};

/** The hours into `day` of an ISO date-time; before that day is 0, after it 24. */
function clock(iso: string | null | undefined, day: string): number | null {
  const d = iso ? new Date(iso) : null;
  if (!d || Number.isNaN(d.getTime())) return null;
  const k = isoDay(d);
  return k < day ? 0 : k > day ? 24 : d.getHours() + d.getMinutes() / 60;
}

type Job = Pick<Booking, "stage" | "answers" | "started_at"> & { finished_at?: string | null };

export function jobSpan(b: Job, now: Date): Span {
  const day = isoDay(now);
  const booked = hoursOf(b.answers.inspection_time);
  const started = clock(b.started_at, day);
  const running = b.stage === "in_progress", done = b.stage === "submitted" || b.stage === "completed";
  if (started === null || !(running || done)) {                      // not started: where it was booked
    const s = booked ?? 8;
    return { start: s, end: s + PLANNED_HOURS, kind: "planned", late: 0 };
  }
  const late = booked !== null && started - booked > LATE_AFTER_HOURS ? Math.round((started - booked) * 60) : 0;
  if (running) return { start: started, end: Math.max(now.getHours() + now.getMinutes() / 60, started + MIN_HOURS), kind: "running", late };
  const finished = clock(b.finished_at, day) ?? started + PLANNED_HOURS;
  return { start: started, end: Math.max(finished, started + MIN_HOURS), kind: "finished", late };
}

export const DAY_START = 9, DAY_END = 21;      // the working day: 9 am to 9 pm

/** The hours the schedule spans: 9 am to 9 pm, widened to fit the day's boxes. */
export function dayWindow(spans: { start: number; end: number }[]): [number, number] {
  return [Math.min(DAY_START, ...spans.map((s) => Math.floor(s.start))), Math.max(DAY_END, ...spans.map((s) => Math.ceil(s.end)))];
}

/** Which sub-row each box goes in so none covers another (first row that is free by its start). */
export function stackRows(spans: { start: number; end: number }[]): { row: number[]; rows: number } {
  const ends: number[] = [];
  const row = new Array<number>(spans.length).fill(0);
  [...spans.keys()].sort((a, b) => spans[a]!.start - spans[b]!.start).forEach((i) => {
    let r = ends.findIndex((e) => e <= spans[i]!.start);
    if (r < 0) r = ends.length;
    ends[r] = spans[i]!.end;
    row[i] = r;
  });
  return { row, rows: Math.max(1, ends.length) };
}

export const hm = (h: number) => { const m = Math.round(h * 60); return fmtTime(`${Math.floor(m / 60) % 24}:${String(m % 60).padStart(2, "0")}`); };
const length = (h: number) => { const m = Math.round(h * 60), x = Math.floor(m / 60); return x ? `${x} h${m % 60 ? ` ${m % 60} min` : ""}` : `${m} min`; };

/** The hover: the real start and end where they are known, the booked hour otherwise, said so. */
export function spanTitle(s: Span): string {
  const text = s.kind === "planned" ? `Booked ${hm(s.start)} – ${hm(s.end)} (planned)`
    : s.kind === "running" ? `Started ${hm(s.start)}, still going`
      : `Started ${hm(s.start)}, finished ${hm(s.end)} (${length(s.end - s.start)})`;
  return s.late ? `${text}\nStarted ${s.late} min late` : text;
}

export const WINDOW_HOURS = 3;

/** Where the quick 3-hour windows start: 9, 12, 3, 6 for a 9 am to 9 pm day. */
export function windowStarts(lo: number, hi: number): number[] {
  const out: number[] = [];
  for (let s = lo; s + WINDOW_HOURS <= hi; s += WINDOW_HOURS) out.push(s);
  if (out.length && out[out.length - 1]! + WINDOW_HOURS < hi) out.push(hi - WINDOW_HOURS);
  return out.length ? out : [lo];
}

/** Keep a window's start inside the day. */
export const clampStart = (s: number, lo: number, hi: number) => Math.min(Math.max(s, lo), Math.max(lo, hi - WINDOW_HOURS));

const h12 = (h: number) => ((Math.floor(h) + 11) % 12) + 1;
const ampm = (h: number) => (h >= 12 && h < 24 ? "pm" : "am");
/** "8–11 am", "11 am–2 pm". */
export function rangeLabel(start: number): string {
  const end = start + WINDOW_HOURS;
  return ampm(start) === ampm(end) ? `${h12(start)}–${h12(end)} ${ampm(end)}` : `${h12(start)} ${ampm(start)}–${h12(end)} ${ampm(end)}`;
}

export type Fact = { label: string; value: string; bad?: boolean };

/** The lines of the hover card: what was booked, when it really began and ended, how long it took. */
export function spanFacts(s: Span, booked: number | null, nowAt: number): Fact[] {
  if (s.kind === "planned") {
    return [{ label: "Booked", value: `${hm(s.start)} – ${hm(s.end)} (planned)` },
      nowAt > s.start ? { label: "Status", value: `Not started, ${length(nowAt - s.start)} past the booked time`, bad: true }
        : { label: "Status", value: `Not started, begins in ${length(s.start - nowAt)}` }];
  }
  const out: Fact[] = [];
  if (booked !== null) out.push({ label: "Booked", value: hm(booked) });
  out.push({ label: "Started", value: s.late ? `${hm(s.start)}, ${s.late} min late` : hm(s.start), bad: s.late > 0 });
  if (s.kind === "running") out.push({ label: "Now", value: `Still going, ${length(Math.max(0, nowAt - s.start))} so far` });
  else out.push({ label: "Finished", value: hm(s.end) }, { label: "Took", value: length(s.end - s.start) });
  return out;
}
