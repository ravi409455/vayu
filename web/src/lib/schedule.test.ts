import { describe, expect, it } from "vitest";
import { clampStart, jobSpan, rangeLabel, spanTitle, stackRows, windowStarts } from "./schedule";

const at = (h: number, m = 0) => new Date(2026, 10, 24, h, m);               // today, 24 Nov 2026
const job = (stage: string, booked: string, started?: Date, finished?: Date) => ({
  stage: stage as never, answers: { inspection_time: booked },
  started_at: started?.toISOString() ?? null, finished_at: finished?.toISOString() ?? null });

describe("where a box starts and ends", () => {
  it("a job not started stays at its booked time, one hour wide, even when it is overdue", () => {
    expect(jobSpan(job("assigned", "10:00"), at(11, 30))).toEqual({ start: 10, end: 11, kind: "planned", late: 0 });
    expect(jobSpan(job("draft", "14:30"), at(9))).toMatchObject({ start: 14.5, end: 15.5, kind: "planned" });
  });
  it("a job in progress runs from its real start to now", () => {
    expect(jobSpan(job("in_progress", "10:00", at(10, 5)), at(11, 30))).toEqual({ start: 10 + 5 / 60, end: 11.5, kind: "running", late: 0 });
    expect(jobSpan(job("in_progress", "10:00", at(11, 30)), at(11, 31)).end).toBeCloseTo(11.5 + 0.25);   // never thinner than a visible box
  });
  it("a finished job runs from its real start to the moment the expert submitted", () => {
    expect(jobSpan(job("completed", "10:00", at(10), at(11, 15)), at(18))).toEqual({ start: 10, end: 11.25, kind: "finished", late: 0 });
    expect(jobSpan(job("submitted", "10:00", at(10), at(10, 40)), at(18)).end).toBeCloseTo(10 + 40 / 60);
    expect(jobSpan(job("completed", "10:00", at(10)), at(18)).end).toBe(11);   // no finish time known: an hour
  });
  it("is late only when it really started more than 15 minutes after the booked time", () => {
    expect(jobSpan(job("in_progress", "10:00", at(10, 15)), at(12)).late).toBe(0);
    expect(jobSpan(job("in_progress", "10:00", at(10, 16)), at(12)).late).toBe(16);
    expect(jobSpan(job("completed", "10:00", at(9, 30), at(10, 30)), at(18)).late).toBe(0);   // early is not late
  });
  it("a job started on an earlier day begins at the left edge", () => {
    const y = new Date(2026, 10, 23, 22);
    expect(jobSpan({ ...job("in_progress", "10:00"), started_at: y.toISOString() }, at(9)).start).toBe(0);
  });
});

describe("overlapping boxes", () => {
  it("go to the next free sub-row, and touching boxes share one", () => {
    const r = stackRows([{ start: 10, end: 11 }, { start: 10.5, end: 11.5 }, { start: 11, end: 12 }, { start: 11.6, end: 12.6 }]);
    expect(r).toEqual({ row: [0, 1, 0, 1], rows: 2 });
    expect(stackRows([])).toEqual({ row: [], rows: 1 });
  });
});

describe("the hover", () => {
  it("says planned, running or finished with the real times, and how late", () => {
    expect(spanTitle({ start: 10, end: 11, kind: "planned", late: 0 })).toBe("Booked 10:00 am – 11:00 am (planned)");
    expect(spanTitle({ start: 10.5, end: 12, kind: "running", late: 30 })).toBe("Started 10:30 am, still going\nStarted 30 min late");
    expect(spanTitle({ start: 10, end: 11.25, kind: "finished", late: 0 })).toBe("Started 10:00 am, finished 11:15 am (1 h 15 min)");
    expect(spanTitle({ start: 10, end: 11, kind: "finished", late: 0 })).toContain("(1 h)");
    expect(spanTitle({ start: 10, end: 10.5, kind: "finished", late: 0 })).toContain("(30 min)");
  });
});

describe("the 3-hour windows", () => {
  it("start every three hours and the last one ends with the day", () => {
    expect(windowStarts(8, 20)).toEqual([8, 11, 14, 17]);
    expect(windowStarts(7, 21)).toEqual([7, 10, 13, 16, 18]);          // the last is pulled back to end at 9 pm
    expect(windowStarts(8, 9)).toEqual([8]);
  });
  it("are kept inside the day", () => {
    expect(clampStart(5, 8, 20)).toBe(8);
    expect(clampStart(19, 8, 20)).toBe(17);
    expect(clampStart(12.5, 8, 20)).toBe(12.5);
  });
  it("are named the way people say them", () => {
    expect(rangeLabel(8)).toBe("8–11 am");
    expect(rangeLabel(11)).toBe("11 am–2 pm");
    expect(rangeLabel(17)).toBe("5–8 pm");
    expect(rangeLabel(21)).toBe("9 pm–12 am");
  });
});
