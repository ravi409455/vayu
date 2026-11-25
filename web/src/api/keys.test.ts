import { QueryClient } from "@tanstack/react-query";
import { describe, expect, it } from "vitest";
import { keys } from "./keys";

const stale = (qc: QueryClient) =>
  qc
    .getQueryCache()
    .getAll()
    .filter((q) => q.state.isInvalidated)
    .map((q) => JSON.stringify(q.queryKey))
    .sort();

describe("one key factory (F-014)", () => {
  it("an Admin's master-list edit refreshes the dropdowns' copy too", async () => {
    const qc = new QueryClient();
    qc.setQueryData(keys.listItems("city", true), []);
    qc.setQueryData(keys.listItems("city"), []);
    qc.setQueryData(keys.booking("b1"), {});
    await qc.invalidateQueries({ queryKey: keys.listItems() });
    expect(stale(qc)).toEqual(['["list-items","city"]', '["list-items","city","archived"]'].sort());
  });
  it("one form version is one family, however it was loaded", async () => {
    const qc = new QueryClient();
    for (const k of [
      keys.formVersion(5),
      keys.formVersions("live", 1, 2),
      keys.formVersions("pinned", 5),
      keys.formVersions("set", "inspection:5"),
    ])
      qc.setQueryData(k, {});
    await qc.invalidateQueries({ queryKey: keys.formVersion() });
    expect(stale(qc)).toHaveLength(4);
  });
  it("refreshing a booking reaches its parts, not other bookings", async () => {
    const qc = new QueryClient();
    qc.setQueryData(keys.booking("b1"), {});
    qc.setQueryData(keys.bookingPart("b1", "activity"), []);
    qc.setQueryData(keys.booking("b2"), {});
    await qc.invalidateQueries({ queryKey: keys.booking("b1") });
    expect(stale(qc)).toEqual(['["booking","b1","activity"]', '["booking","b1"]'].sort());
  });
  it("every users list is one family (all, experts, by role)", () => {
    expect(keys.users({ role: "expert" }).slice(0, 1)).toEqual(keys.users());
  });
});
