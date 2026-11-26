import { describe, expect, it, vi } from "vitest";
import { report, scrub, scrubCrumb, sentryEnvironment, startMonitoring, stripQuery } from "./monitor";

describe("web errors to Sentry (R-36, F-235)", () => {
  it("is off without a DSN: nothing loads, nothing is sent", async () => {
    await startMonitoring(undefined);
    expect(() => report(new Error("x"))).not.toThrow();
  });
  it("sends no request body, cookies, headers, query strings or extra data", () => {
    const e = scrub({
      type: undefined,
      request: {
        url: "https://app.carcid.in/bookings?search=98765",
        data: { name: "Kavya" },
        cookies: { sessionid: "s" },
        headers: { a: "b" },
        query_string: "search=98765",
      },
      user: { id: 7, username: "ravi", email: "r@x" },
      extra: { answers: { phone: "98765" } },
    } as never);
    expect(e.request).toEqual({ url: "https://app.carcid.in/bookings" });
    expect(e.user).toEqual({ id: 7 });
    expect(e.extra).toBeUndefined();
  });
  it("drops console and typing breadcrumbs, and the query part of URLs", () => {
    expect(scrubCrumb({ category: "console", message: "Kavya 98765" })).toBeNull();
    expect(scrubCrumb({ category: "ui.input" })).toBeNull();
    expect(scrubCrumb({ category: "ui.click", message: 'a[aria-label="Call 9876500011"]', data: { x: 1 } })).toEqual({
      category: "ui.click",
      message: undefined,
      data: undefined,
    });
    expect(scrubCrumb({ category: "fetch", data: { url: "/api/v1/bookings?search=Sharma", method: "GET" } })?.data).toEqual({
      url: "/api/v1/bookings",
      method: "GET",
    });
    expect(scrubCrumb({ category: "navigation", data: { from: "/bookings?search=Sharma", to: "/booking/1" } })?.data).toEqual({
      from: "/bookings",
      to: "/booking/1",
    });
  });
  it("with a DSN, the SDK starts with nothing collected about people or requests", async () => {
    const init = vi.fn();
    vi.doMock("@sentry/react", () => ({ init, captureException: vi.fn(), setUser: vi.fn() }));
    vi.resetModules();
    const m = await import("./monitor");
    await m.startMonitoring("https://key@o1.ingest.sentry.io/1");
    expect(init).toHaveBeenCalledWith(
      expect.objectContaining({
        dataCollection: { userInfo: false, cookies: false, httpHeaders: false, httpBodies: [], urlQueryParams: false },
      }),
    );
    vi.doUnmock("@sentry/react");
  });
  it("masks the report and ZIP tokens in customer page paths (N11)", () => {
    expect(stripQuery("https://vayu.carcid.in/report/verify/abcDEF_123")).toBe("https://vayu.carcid.in/report/verify/[token]");
    expect(stripQuery("/verify/abc/photos?x=1")).toBe("/verify/[token]");
    expect(stripQuery("/api/v1/verify/abc")).toBe("/api/v1/verify/[token]");
    expect(stripQuery("/zip/tok")).toBe("/zip/[token]");
    expect(stripQuery("/booking/1")).toBe("/booking/1");
    const e = scrub({
      type: undefined,
      transaction: "/verify/secret",
      exception: { values: [{ type: "ApiError", value: "Kavya's booking SA1 was changed" }] },
    } as never);
    expect(e.transaction).toBe("/verify/[token]");
    expect(e.exception?.values?.[0]?.value).toBe("ApiError");
  });

  it("one web build: the Sentry label comes from the address in a production build", () => {
    vi.stubEnv("PROD", true);
    vi.stubEnv("VITE_SENTRY_ENV", "");
    expect(sentryEnvironment("vayu-staging.carcid.in")).toBe("staging");
    expect(sentryEnvironment("vayu.carcid.in")).toBe("production");
    vi.stubEnv("VITE_SENTRY_ENV", "e2e");
    expect(sentryEnvironment("vayu.carcid.in")).toBe("e2e");
    vi.unstubAllEnvs();
  });
});
