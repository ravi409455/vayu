import { describe, expect, it } from "vitest";

const NOW = new Date(2026, 10, 23, 14, 20); // Mon 23 Nov 2026, 2:20 pm

describe("my jobs", () => {
  it("groups leads under Overdue, Today, Tomorrow, Later and Earlier (finished)", async () => {
    const { groupOf } = await import("./MyJobs");
    const j = (stage: string, d: string) => ({ stage, answers: { inspection_date: d } });
    expect(groupOf(j("assigned", "2026-11-23"), NOW)).toBe("Today");
    expect(groupOf(j("in_progress", "2026-11-20"), NOW)).toBe("Overdue");
    expect(groupOf(j("assigned", "2026-11-24"), NOW)).toBe("Tomorrow");
    expect(groupOf(j("assigned", "2026-12-02"), NOW)).toBe("Later");
    expect(groupOf(j("completed", "2026-11-23"), NOW)).toBe("Earlier");
  });
});

describe("my jobs quick filters", () => {
  it("sorts each job into To do / Today / Upcoming / Started / Done", async () => {
    const { matchesJob } = await import("./MyJobs");
    const j = (stage: string, d: string) => ({ stage, answers: { inspection_date: d } });
    const today = j("assigned", "2026-11-23"),
      later = j("assigned", "2026-12-01"),
      started = j("in_progress", "2026-11-23"),
      done = j("completed", "2026-11-20");
    const pick = (f: Parameters<typeof matchesJob>[1]) => [today, later, started, done].filter((b) => matchesJob(b, f, NOW));
    expect(pick("open")).toEqual([today, later, started]);
    expect(pick("today")).toEqual([today, started]);
    expect(pick("upcoming")).toEqual([later]);
    expect(pick("started")).toEqual([started]);
    expect(pick("done")).toEqual([done]);
    expect(pick("all")).toHaveLength(4);
  });
});
