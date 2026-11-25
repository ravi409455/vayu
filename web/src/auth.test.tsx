import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError } from "./api/client";
import { AuthProvider, useAuth } from "./auth";
import * as uploads from "./lib/uploadManager";

afterEach(() => vi.restoreAllMocks());

describe("identity changes clear what was cached", () => {
  function probe() {
    const qc = new QueryClient();
    qc.setQueryData(["bookings"], [{ customer: "private" }]);
    let auth!: ReturnType<typeof useAuth>;
    function Grab() {
      auth = useAuth();
      return null;
    }
    render(<QueryClientProvider client={qc}><AuthProvider><Grab /></AuthProvider></QueryClientProvider>);
    return { qc, get auth() { return auth; } };
  }
  it("logout clears everything even when the call fails", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (u) =>
      String(u).includes("auth/logout") ? new Response("{}", { status: 500, headers: { "Content-Type": "application/json" } })
        : new Response(JSON.stringify({ id: 1, username: "a", permissions: {}, role: "ops" }), { status: 200, headers: { "Content-Type": "application/json" } }));
    const p = probe();
    await screen.findByText((_, el) => el === null || true).catch(() => {});
    await vi.waitFor(() => expect(p.auth.me).not.toBeNull());
    const stop = vi.spyOn(uploads, "reset");
    await expect(p.auth.logout()).rejects.toBeInstanceOf(ApiError);
    expect(stop).toHaveBeenCalled();                    // the upload queue stops too (F-072)
    expect(p.qc.getQueryData(["bookings"])).toBeUndefined();
    expect(p.qc.getQueryData(["me"])).toBeNull();
  });
  it("login starts from an empty cache and a 401 anywhere clears it", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () =>
      new Response(JSON.stringify({ id: 2, username: "b", permissions: {}, role: "ops" }), { status: 200, headers: { "Content-Type": "application/json" } }));
    const p = probe();
    await vi.waitFor(() => expect(p.auth.me).not.toBeNull());
    p.qc.setQueryData(["bookings"], ["old person's data"]);
    await p.auth.login("b", "pw");
    expect(p.qc.getQueryData(["bookings"])).toBeUndefined();
    p.qc.setQueryData(["bookings"], ["more"]);
    vi.restoreAllMocks();
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => new Response("{}", { status: 401, headers: { "Content-Type": "application/json" } }));
    await expect(api("anything")).rejects.toMatchObject({ status: 401 });
    expect(p.qc.getQueryData(["bookings"])).toBeUndefined();
    expect(p.qc.getQueryData(["me"])).toBeNull();
  });
});
