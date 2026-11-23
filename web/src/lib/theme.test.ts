import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { applySignedOut, applyTheme, cachedTheme, isChoice, resolveTheme, THEME_KEY } from "./theme";

const media = (dark: boolean) => vi.stubGlobal("matchMedia", (q: string) => ({ matches: dark && q.includes("dark"), addEventListener() {}, removeEventListener() {} }));

function memoryStorage() {
  const m = new Map<string, string>();
  return { getItem: (k: string) => m.get(k) ?? null, setItem: (k: string, v: string) => void m.set(k, v), removeItem: (k: string) => void m.delete(k), clear: () => m.clear() };
}
beforeEach(() => { vi.stubGlobal("localStorage", memoryStorage()); document.documentElement.removeAttribute("data-theme"); });
afterEach(() => vi.unstubAllGlobals());

describe("theme", () => {
  it("follows the device only for 'system'", () => {
    expect(resolveTheme("system", true)).toBe("dark");
    expect(resolveTheme("system", false)).toBe("light");
    expect(resolveTheme("light", true)).toBe("light");
    expect(resolveTheme("dark", false)).toBe("dark");
  });
  it("sets the page and remembers the choice (not the resolved look)", () => {
    media(true);
    expect(applyTheme("system")).toBe("dark");
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(document.documentElement.style.colorScheme).toBe("dark");
    expect(localStorage.getItem(THEME_KEY)).toBe("system");
    expect(cachedTheme()).toBe("system");
  });
  it("is always Light when signed out and forgets the remembered choice", () => {
    media(true);
    applyTheme("dark");
    applySignedOut();
    expect(document.documentElement.dataset.theme).toBe("light");
    expect(cachedTheme()).toBeNull();
  });
  it("does not save the signed-out look", () => {
    applyTheme("dark", false);
    expect(cachedTheme()).toBeNull();
  });
  it("ignores a damaged remembered value and survives storage being unavailable", () => {
    localStorage.setItem(THEME_KEY, "purple");
    expect(cachedTheme()).toBeNull();
    expect(isChoice("dark") && !isChoice("purple") && !isChoice(null)).toBe(true);
    const blocked = () => { throw new Error("blocked"); };
    vi.stubGlobal("localStorage", { getItem: blocked, setItem: blocked, removeItem: blocked });
    expect(cachedTheme()).toBeNull();
    expect(() => applyTheme("dark")).not.toThrow();
    expect(() => applySignedOut()).not.toThrow();
  });
  it("works when the browser cannot tell the device preference", () => {
    vi.stubGlobal("matchMedia", undefined);
    expect(applyTheme("system")).toBe("light");
  });
});
