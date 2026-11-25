import { describe, expect, it } from "vitest";
import { addDays, fmtDay, fmtPhone, fmtSlot, fmtStamp, fmtTime } from "./format";

const NOW = new Date(2026, 10, 23, 14, 20);   // Mon 23 Nov 2026, 2:20 pm

describe("human dates, times and phones", () => {
  it("says today / tomorrow / yesterday, else a short date (with the year only when it differs)", () => {
    expect(fmtDay("2026-11-23", NOW)).toBe("Today");
    expect(fmtDay("2026-11-24", NOW)).toBe("Tomorrow");
    expect(fmtDay("2026-11-22", NOW)).toBe("Yesterday");
    expect(fmtDay("2026-11-27", NOW)).toMatch(/^Fri 27 Nov$/);
    expect(fmtDay("2027-01-05", NOW)).toMatch(/2027$/);
    expect(fmtDay("nope", NOW)).toBe("");
    expect(addDays("2026-12-31", 1)).toBe("2027-01-01");
  });
  it("uses a 12-hour clock", () => {
    expect([fmtTime("00:05"), fmtTime("09:30"), fmtTime("12:00"), fmtTime("15:30")]).toEqual(["12:05 am", "9:30 am", "12:00 pm", "3:30 pm"]);
    expect(fmtSlot("2026-11-24", "10:30", NOW)).toBe("Tomorrow, 10:30 am");
    expect(fmtStamp(new Date(2026, 10, 23, 9, 5).toISOString(), NOW)).toBe("Today, 9:05 am");
  });
  it("groups an Indian mobile number and leaves anything else alone", () => {
    expect(fmtPhone("+919876500000")).toBe("+91 98765 00000");
    expect(fmtPhone("12345")).toBe("12345");
  });
});
