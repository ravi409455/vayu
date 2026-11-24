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

/** The hours the schedule spans: 8 am to 8 pm, widened to fit the day's boxes. */
export function dayWindow(spans: { start: number; end: number }[]): [number, number] {
  return [Math.min(8, ...spans.map((s) => Math.floor(s.start))), Math.max(20, ...spans.map((s) => Math.ceil(s.end)))];
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
