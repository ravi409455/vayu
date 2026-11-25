import { describe, expect, it } from "vitest";

describe("row menus", () => {
  it("open below the button, or above it near the bottom, and stay inside the window", async () => {
    const { placeMenu } = await import("./Menu");
    const view = { width: 1440, height: 900 }, menu = { width: 200, height: 180 };
    expect(placeMenu({ top: 100, bottom: 130, right: 1400 }, menu, view)).toEqual({ top: 136, left: 1200 });
    expect(placeMenu({ top: 800, bottom: 830, right: 1400 }, menu, view)).toEqual({ top: 614, left: 1200 });   // flipped up
    expect(placeMenu({ top: 100, bottom: 130, right: 50 }, menu, view).left).toBe(8);                         // not off the left edge
  });
});
