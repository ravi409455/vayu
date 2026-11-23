import { describe, expect, it } from "vitest";
import type { FormField } from "./api/types";
import { addDays, fmtDay, fmtPhone, fmtSlot, fmtStamp, fmtTime } from "./lib/format";
import { activityText } from "./pages/ops/Booking";
import { viewQuery } from "./pages/ops/Bookings";
import { dayWindow } from "./pages/ops/Today";
import { defectOf } from "./ui/AnswerSheet";

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

describe("booking views", () => {
  it("each saved view asks the server for the right slice", () => {
    expect(viewQuery("today", NOW)).toEqual({ date_from: "2026-11-23", date_to: "2026-11-23", order: "schedule" });
    expect(viewQuery("unassigned", NOW)).toMatchObject({ stage: "draft" });
    expect(viewQuery("uploading", NOW)).toEqual({ stage: "submitted" });
    expect(viewQuery("upcoming", NOW)).toMatchObject({ date_from: "2026-11-24" });
    expect(viewQuery("all", NOW)).toEqual({});
  });
  it("the schedule spans at least 9 to 7 and grows to fit early or late jobs", () => {
    expect(dayWindow([])).toEqual([9, 19]);
    expect(dayWindow([7.5, 18.75])).toEqual([7, 21]);
  });
});

describe("activity lines", () => {
  const by = { id: 1, name: "Priya", role: "ops" };
  const line = (r: Partial<Parameters<typeof activityText>[0]>) => activityText({ at: "", kind: "changed", by, changes: {}, keys: [], ...r }, () => "Ravi", (k) => k === "customer_name" ? "Customer name" : k, (k) => String(k).toUpperCase());
  it("says what happened in words", () => {
    expect(line({ kind: "created" })).toBe("Created by Priya");
    expect(line({ changes: { assigned_expert: [null, 5] } })).toBe("Assigned to Ravi by Priya");
    expect(line({ changes: { assigned_expert: [4, 5] } })).toBe("Reassigned to Ravi by Priya");
    expect(line({ changes: { stage: ["submitted", "completed"] }, by: null })).toBe("Completed: every file uploaded");
    expect(line({ changes: { stage: ["in_progress", "assigned"] } })).toBe("Force-released by Priya");
    expect(line({ kind: "edited", keys: ["customer_name"] })).toBe("Priya changed Customer name");
    expect(line({ kind: "inspection_edited", keys: ["inspection.a", "inspection.b"] })).toBe("Priya changed 2 answers");
    expect(line({ changes: { inspection_type: ["pdi", "ev"] } })).toBe("Type changed to EV by Priya");
  });
});

describe("defects in the review sheet", () => {
  const f = (type: string): FormField => ({ id: 1, section: 1, key: "door", label: "Door", helper_text: "", type, required: false, required_if: null, show_if: null, visible: true, order: 0, is_system: false, access: {}, locked: false, library: null,
    config: { options: [{ key: "ok", label: "OK" }, { key: "scr", label: "Scratched", is_defect: true, severity: "minor" }, { key: "dent", label: "Dented", is_defect: true, severity: "major" }] } });
  it("marks a defect answer with its severity, and nothing else", () => {
    expect(defectOf(f("single_choice"), "ok")).toBeNull();
    expect(defectOf(f("single_choice"), "scr")).toBe("Minor");
    expect(defectOf(f("multi_choice"), ["scr", "dent"])).toBe("Major");
    expect(defectOf(f("short_text"), "dent")).toBeNull();
  });
});

describe("dashboard", () => {
  it("presets cover the right dates and pick a sensible bar size", async () => {
    const { presetRange, groupFor, delta } = await import("./pages/ops/Dashboards");
    expect(presetRange("today", NOW)).toEqual(["2026-11-23", "2026-11-23"]);
    expect(presetRange("7", NOW)).toEqual(["2026-11-17", "2026-11-23"]);
    expect(presetRange("month", NOW)).toEqual(["2026-11-01", "2026-11-23"]);
    expect(groupFor("2026-11-01", "2026-11-30")).toBe("day");
    expect(groupFor("2026-09-01", "2026-11-30")).toBe("week");
    expect(groupFor("2026-01-01", "2026-11-30")).toBe("month");
    expect(delta(110, 100, "count")).toEqual({ text: "+10%", good: true });
    expect(delta(95.5, 96.7, "pct")).toEqual({ text: "−1.2 pts", good: false });
    expect(delta(100, 110, "minutes", false)).toEqual({ text: "−10 min", good: true });
    expect(delta(3, 0, "count").text).toBe("");
    const { daysBetween } = await import("./pages/ops/Dashboards");
    expect(daysBetween("2026-11-29", "2026-12-02")).toEqual(["2026-11-29", "2026-11-30", "2026-12-01", "2026-12-02"]);
    expect(delta(null, 5, "count").text).toBe("");
  });
});
