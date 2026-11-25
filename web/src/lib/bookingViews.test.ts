import { describe, expect, it } from "vitest";
import { viewQuery } from "./bookingViews";
import { dayWindow } from "./schedule";

const NOW = new Date(2026, 10, 23, 14, 20); // Mon 23 Nov 2026, 2:20 pm

describe("booking views", () => {
  it("each saved view asks the server for the right slice", () => {
    expect(viewQuery("today", NOW)).toEqual({ date_from: "2026-11-23", date_to: "2026-11-23", order: "schedule" });
    expect(viewQuery("unassigned", NOW)).toMatchObject({ stage: "draft" });
    expect(viewQuery("uploading", NOW)).toEqual({ stage: "submitted" });
    expect(viewQuery("upcoming", NOW)).toMatchObject({ date_from: "2026-11-24" });
    expect(viewQuery("all", NOW)).toEqual({});
  });
  it("the schedule spans at least 9 am to 9 pm and grows to fit early or late jobs", () => {
    expect(dayWindow([])).toEqual([9, 21]);
    expect(
      dayWindow([
        { start: 7.5, end: 8.5 },
        { start: 20.25, end: 21.25 },
      ]),
    ).toEqual([7, 22]);
  });
});
