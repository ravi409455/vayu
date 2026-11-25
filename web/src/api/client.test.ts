import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError, explain, staleInfo } from "./client";
import { fetchAll } from "./hooks";

afterEach(() => vi.restoreAllMocks());

describe("requests can be cancelled (F-167)", () => {
  it("api() and fetchAll() hand the query's signal to fetch", async () => {
    const f = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation(async () => new Response("[]", { status: 200, headers: { "Content-Type": "application/json" } }));
    const c = new AbortController();
    await api("bookings", { signal: c.signal });
    await fetchAll("users", undefined, c.signal);
    expect(f.mock.calls.map(([, init]) => init?.signal)).toEqual([c.signal, c.signal]);
  });
});

describe("error handling", () => {
  it("explains each kind of failure in plain words", () => {
    expect(explain(new ApiError(403, {}))).toMatch(/not allowed/);
    expect(explain(new ApiError(426, {}))).toMatch(/out of date/);
    expect(explain(new ApiError(429, {}))).toMatch(/Too many/);
    expect(explain(new ApiError(500, {}))).toMatch(/server had a problem/);
    expect(explain(new ApiError(400, { code: "X", detail: "Booking ID 'A' is already used." }))).toBe("Booking ID 'A' is already used.");
    expect(explain(new ApiError(400, { city: ["Not a valid choice."] }))).toBe("city: Not a valid choice.");
    // the server's shape (one_shape): detail is the first field's message, fields name it
    const field = { inspection_date: ["Enter a valid date."] };
    expect(explain(new ApiError(400, { ...field, code: "INVALID", detail: "Enter a valid date.", fields: field }))).toBe(
      "inspection date: Enter a valid date.",
    );
    const general = { non_field_errors: ["Pick one."] };
    expect(explain(new ApiError(400, { code: "INVALID", detail: "Pick one.", fields: general }))).toBe("Pick one.");
    expect(explain(new TypeError("network"))).toMatch(/connection/);
  });
  it("reads who changed a booking from a 409", () => {
    const e = new ApiError(409, {
      code: "STALE_BOOKING",
      detail: "x",
      changed_by: "priya",
      changed_at: "2026-11-23T10:00:00Z",
      changed_keys: ["city"],
      row_version: 4,
    });
    expect(staleInfo(e)).toEqual({ by: "priya", at: "2026-11-23T10:00:00Z", keys: ["city"], rowVersion: 4 });
    expect(staleInfo(new ApiError(409, { code: "DRAFT_EXISTS" }))).toBeNull();
    expect(staleInfo(new Error("x"))).toBeNull();
  });
  it("a 401 signs the person out and a 426 asks for a reload", async () => {
    const { setApiHandlers } = await import("./client");
    const onUnauthorized = vi.fn();
    const onUpgrade = vi.fn();
    setApiHandlers({ onUnauthorized, onUpgrade });
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("{}", { status: 401, headers: { "Content-Type": "application/json" } }));
    await expect(api("x")).rejects.toMatchObject({ status: 401 });
    expect(onUnauthorized).toHaveBeenCalledOnce();
    vi.restoreAllMocks();
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("{}", { status: 426, headers: { "Content-Type": "application/json" } }));
    await expect(api("x")).rejects.toMatchObject({ status: 426 });
    expect(onUpgrade).toHaveBeenCalledOnce();
    vi.restoreAllMocks();
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("{}", { status: 401, headers: { "Content-Type": "application/json" } }));
    onUnauthorized.mockClear();
    await expect(api("auth/login", { body: {} })).rejects.toMatchObject({ status: 401 });
    expect(onUnauthorized).toHaveBeenCalledOnce(); // sign-in failures are 401 too: wrong password shows its own message
  });
  it("sends the CSRF token on writes only", async () => {
    document.cookie = "csrftoken=abc123";
    const spy = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation(async () => new Response("{}", { status: 200, headers: { "Content-Type": "application/json" } }));
    await api("x");
    await api("x", { body: { a: 1 } });
    const [get, post] = spy.mock.calls.map((c) => (c[1]?.headers ?? {}) as Record<string, string>);
    expect(get?.["X-CSRFToken"]).toBeUndefined();
    expect(post?.["X-CSRFToken"]).toBe("abc123");
  });
});
