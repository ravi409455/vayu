// Light / Dark / Match my device. The choice is saved on the server per person; the last signed-in
// choice is also kept in this browser so the page can be painted right the first time (no flash).
export type ThemeChoice = "light" | "dark" | "system";
export const THEME_KEY = "vayu:theme";

export const isChoice = (v: unknown): v is ThemeChoice => v === "light" || v === "dark" || v === "system";

/** What the page should actually look like. "system" follows the device. */
export function resolveTheme(choice: ThemeChoice, deviceIsDark: boolean): "light" | "dark" {
  return choice === "system" ? (deviceIsDark ? "dark" : "light") : choice;
}

const deviceIsDark = () => typeof window !== "undefined" && !!window.matchMedia?.("(prefers-color-scheme: dark)").matches;

/** Show this choice now. Pass `remember: false` for the signed-out look (it must not be saved). */
export function applyTheme(choice: ThemeChoice, remember = true): "light" | "dark" {
  const resolved = resolveTheme(choice, deviceIsDark());
  const root = document.documentElement;
  root.dataset.theme = resolved;
  root.style.colorScheme = resolved;
  if (remember) {
    try {
      localStorage.setItem(THEME_KEY, choice);
    } catch {
      /* private mode: fine */
    }
  }
  return resolved;
}

/** Signed out (and the sign-in page) is always Light, and the cached choice is forgotten. */
export function applySignedOut(): void {
  applyTheme("light", false);
  try {
    localStorage.removeItem(THEME_KEY);
  } catch {
    /* fine */
  }
}
