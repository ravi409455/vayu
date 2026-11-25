import { describe, expect, it } from "vitest";
import type { Booking } from "../api/types";
import { visibleNav } from "../Layout";
import { timingPills } from "../pages/ops/Bookings";
import { viewQuery } from "./bookingViews";
import { jobSpan } from "./schedule";
import { fmtMinutes, timingFlags } from "./timing";

const t = (over: Partial<NonNullable<Booking["timing"]>>) => ({ late_minutes: 40, duration_minutes: 25, late: false, quick: false,
  min_minutes: 45, grace_minutes: 15, late_reviewed_by: null, late_reviewed_at: null, quick_reviewed_by: null, quick_reviewed_at: null, ...over });

describe("started late / too quick", () => {
  it("says each problem on its own, reviewed apart, and nothing when all is fine", () => {
    const both = timingFlags(t({ late: true, quick: true, late_reviewed_by: "ops", late_reviewed_at: "2026-11-24T10:00:00Z" }));
    expect(both.map((f) => [f.flag, f.words, f.reviewedBy])).toEqual([["late", "Started 40 min late", "ops"], ["quick", "Took 25 min (min 45)", null]]);
    expect(timingFlags(t({}))).toEqual([]);
    expect(timingFlags(undefined)).toEqual([]);           // Experts never get the timing at all
    expect(timingPills({ timing: t({ quick: true }) } as Booking)).toEqual(["Too quick 25 min"]);
  });
  it("long gaps read in hours and days", () => {
    expect([fmtMinutes(40), fmtMinutes(125), fmtMinutes(120), fmtMinutes(7125), fmtMinutes(null)]).toEqual(["40 min", "2 h 5 min", "2 h", "4 days 22 h", "—"]);
  });
  it("the Bookings tabs ask the server for the flag", () => {
    expect(viewQuery("late")).toEqual({ timing: "late" });
    expect(viewQuery("quick")).toEqual({ timing: "quick" });
  });
  it("the schedule's red mark follows the grace Admin set", () => {
    const job = { stage: "in_progress", answers: { inspection_time: "10:00" }, started_at: new Date(2026, 10, 24, 10, 20).toISOString() };
    const now = new Date(2026, 10, 24, 11);
    expect(jobSpan(job, now).late).toBe(20);              // default 15 min
    expect(jobSpan(job, now, 30).late).toBe(0);
  });
  it("Admin and Ops see Settings, Experts do not", () => {
    const labels = (role: string, perms: string[]) => visibleNav(role, (p) => perms.includes(p)).flatMap((g) => g.items.map((i) => i.label));
    expect(labels("ops", ["settings.view"])).toContain("Settings");
    expect(labels("admin", ["settings.view"])).toContain("Settings");
    expect(labels("expert", ["settings.view"])).not.toContain("Settings");
  });
});
