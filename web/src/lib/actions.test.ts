import { describe, expect, it } from "vitest";
import { allowedActions } from "./actions";

const all = () => true;
const of = (stage: string) => [...allowedActions({ stage } as never, all)].sort();

describe("booking actions follow the server's stage rules (F-011 / F-126)", () => {
  it("offers only what the server accepts in each stage", () => {
    expect(of("draft")).toEqual(["assign", "cancel", "reschedule", "type"]);
    expect(of("assigned")).toEqual(["assign", "cancel", "reschedule", "type"]);
    expect(of("in_progress")).toEqual(["cancel", "release"]); // no reschedule, no reassign: release first
    expect(of("submitted")).toEqual([]); // not cancelled, not reassigned
    expect(of("completed")).toEqual([]);
    expect(of("cancelled")).toEqual([]);
  });
  it("and only with the permission", () => {
    expect([...allowedActions({ stage: "draft" } as never, (p) => p === "bookings.cancel")]).toEqual(["cancel"]);
  });
});
