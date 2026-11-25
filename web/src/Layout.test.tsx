import { afterEach, describe, expect, it, vi } from "vitest";
import { OPS_PAGES, visibleNav } from "./Layout";
import { canDelete } from "./pages/ops/Bookings";

afterEach(() => vi.restoreAllMocks());

describe("who sees what", () => {
  it("Ops see exactly Today, Bookings, Problems and Dashboard", () => {
    const everything = () => true;
    const titles = visibleNav("ops", everything).flatMap((g) => g.items.map((i) => i.to));
    expect(titles.sort()).toEqual([...OPS_PAGES].sort());
  });
  it("Admin sees the management pages too, and nobody has a Search page any more", () => {
    const admin = visibleNav("admin", () => true).flatMap((g) => g.items.map((i) => i.to));
    expect(admin).toEqual(expect.arrayContaining(["/bookings", "/forms", "/library", "/users", "/integrations"]));
    expect(admin).not.toContain("/search");
    expect(admin).not.toContain("/jobs");
  });
  it("Admin may delete any booking, Ops only a draft", () => {
    expect(canDelete("admin", "completed")).toBe(true);
    expect(canDelete("ops", "draft")).toBe(true);
    expect(canDelete("ops", "assigned")).toBe(false);
    expect(canDelete("ops", "cancelled")).toBe(false);
  });
});
