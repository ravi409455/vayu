import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { fmtStamp, ist, today } from "./format";

// The office computer may not be on India time; the server always is (F-012 / F-124 / F-132).
let before: string | undefined;
beforeEach(() => {
  before = process.env.TZ;
  process.env.TZ = "UTC";
});
afterEach(() => {
  process.env.TZ = before;
});

describe("India time whatever the computer's time zone", () => {
  it("'today' is India's day: 02:00 IST is still 20:30 UTC the day before", () => {
    const at = new Date("2026-11-24T20:30:00Z"); // 25 Nov, 02:00 in India
    expect(new Date(at).getUTCDate()).toBe(24);
    expect(today(at)).toBe("2026-11-25");
    expect(ist(at)).toMatchObject({ day: "2026-11-25", hhmm: "02:00", hours: 2 });
  });
  it("a timestamp reads in India time", () => {
    expect(fmtStamp("2026-11-25T04:00:00Z", new Date("2026-11-25T06:00:00Z"))).toBe("Today, 9:30 am");
  });
});
