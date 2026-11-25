import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchAll } from "./hooks";

const page = (results: unknown[], next: string | null) =>
  new Response(JSON.stringify({ count: 3, next, previous: null, results }), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });

afterEach(() => vi.restoreAllMocks());

describe("lists read every page (H-14)", () => {
  it("follows the server's pages to the end", async () => {
    const seen: string[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (u) => {
      seen.push(String(u));
      return String(u).includes("page=2")
        ? page([{ id: 3 }], null)
        : page([{ id: 1 }, { id: 2 }], "http://x/api/v1/users?role=expert&page=2");
    });
    expect(await fetchAll<{ id: number }>("users", { role: "expert" })).toEqual([{ id: 1 }, { id: 2 }, { id: 3 }]);
    expect(seen).toEqual(["/api/v1/users?role=expert", "/api/v1/users?role=expert&page=2"]);
  });
  it("a plain array is the whole list", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response("[1,2]", { status: 200, headers: { "Content-Type": "application/json" } }),
    );
    expect(await fetchAll("forms")).toEqual([1, 2]);
  });
});
