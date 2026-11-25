import { afterEach, describe, expect, it, vi } from "vitest";
import { pivot } from "./Dashboards";

afterEach(() => vi.restoreAllMocks());

const NOW = new Date(2026, 10, 23, 14, 20); // Mon 23 Nov 2026, 2:20 pm

describe("dashboard", () => {
  it("presets cover the right dates and pick a sensible bar size", async () => {
    const { presetRange, groupFor, delta } = await import("./Dashboards");
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
    const { daysBetween } = await import("./Dashboards");
    expect(daysBetween("2026-11-29", "2026-12-02")).toEqual(["2026-11-29", "2026-11-30", "2026-12-01", "2026-12-02"]);
    expect(delta(null, 5, "count").text).toBe("");
  });
  it("compares with as many days straight before, and keeps minutes short", async () => {
    const { previousRange, minsParts } = await import("./Dashboards");
    expect(previousRange("2026-10-26", "2026-11-24")).toEqual(["2026-09-26", "2026-10-25"]); // 30 days before 30 days
    expect(previousRange("2026-11-24", "2026-11-24")).toEqual(["2026-11-23", "2026-11-23"]);
    expect(minsParts(40)).toEqual(["40", "min"]);
    expect(minsParts(100)).toEqual(["1 h 40 m", ""]);
    expect(minsParts(null)).toEqual(["—", ""]);
  });
  it("names a range briefly and refuses a custom range it can't use", async () => {
    const { rangeText, rangeProblem, shortDay } = await import("./Dashboards");
    expect(rangeText("2026-10-26", "2026-11-23", NOW)).toBe("26 Oct – 23 Nov");
    expect(rangeText("2026-11-23", "2026-11-23", NOW)).toBe("Today");
    expect(shortDay("2025-12-30", NOW)).toBe("30 Dec 2025");
    expect(rangeProblem("2026-11-01", "2026-11-20", NOW)).toBeNull();
    expect(rangeProblem("", "2026-11-20", NOW)).toBe("Pick both dates.");
    expect(rangeProblem("2026-11-21", "2026-11-20", NOW)).toMatch(/after the end/);
    expect(rangeProblem("2026-11-21", "2026-11-24", NOW)).toMatch(/future/);
    expect(rangeProblem("2025-01-01", "2026-11-20", NOW)).toMatch(/at most a year/);
  });
});

describe("dashboard table", () => {
  it("lines rows up by period and key, zero when missing", () => {
    const { periods, keys, cell } = pivot([
      { period: "2026-10-14", key: "pdi", count: 2 },
      { period: "2026-10-14", key: "ev", count: 1 },
      { period: "2026-10-21", key: "pdi", count: 3 },
    ]);
    expect(periods).toEqual(["2026-10-14", "2026-10-21"]);
    expect(keys).toEqual(["ev", "pdi"]);
    expect([cell("2026-10-14", "pdi"), cell("2026-10-21", "ev")]).toEqual([2, 0]);
    expect(pivot([]).periods).toEqual([]);
  });
});
