import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "./client";
import { fetchAll } from "./hooks";

afterEach(() => vi.restoreAllMocks());

describe("requests can be cancelled (F-167)", () => {
  it("api() and fetchAll() hand the query's signal to fetch", async () => {
    const f = vi.spyOn(globalThis, "fetch").mockImplementation(async () => new Response("[]", { status: 200, headers: { "Content-Type": "application/json" } }));
    const c = new AbortController();
    await api("bookings", { signal: c.signal });
    await fetchAll("users", undefined, c.signal);
    expect(f.mock.calls.map(([, init]) => init?.signal)).toEqual([c.signal, c.signal]);
  });
});
