import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(() => vi.restoreAllMocks());

describe("shell v3", () => {
  it("names the server from its host, and shows nothing on production", async () => {
    const { envName } = await import("./Logo");
    expect(envName("localhost")).toBe("Local");
    expect(envName("127.0.0.1")).toBe("Local");
    expect(envName("vayu.test")).toBe("Local");
    expect(envName("staging.vayu.carcid.in")).toBe("Staging");
    expect(envName("vayu-dev.example.com")).toBe("Staging");
    expect(envName("vayu.carcid.in")).toBeNull();
    expect(envName("devices.carcid.in")).toBeNull();
  });
  it("builds the breadcrumb from the path and what the page is showing", async () => {
    const { crumbsFor } = await import("./TopBar");
    expect(crumbsFor("/bookings", "")).toEqual([{ label: "Bookings" }]);
    expect(crumbsFor("/booking/abc", "BK-1044")).toEqual([{ label: "Bookings", to: "/bookings" }, { label: "BK-1044" }]);
    expect(crumbsFor("/forms/7", "Used car")).toEqual([{ label: "Forms", to: "/forms" }, { label: "Used car" }]);
    expect(crumbsFor("/forms/7", "")).toEqual([{ label: "Forms", to: "/forms" }]);
    expect(crumbsFor("/nowhere", "x")).toEqual([]);
  });
});
