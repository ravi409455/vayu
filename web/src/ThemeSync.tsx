import { useEffect } from "react";
import { useAuth } from "./auth";
import { applySignedOut, applyTheme } from "./lib/theme";

/** Keeps the page's look in step with who is signed in: their saved theme, Light when nobody is,
 *  and, for "match my device", the device's own light / dark switch. */
export function ThemeSync() {
  const { me, loading } = useAuth();
  const choice = me?.theme ?? "light";
  const signedIn = !!me;
  useEffect(() => {
    if (loading) return;
    if (!signedIn) { applySignedOut(); return; }
    applyTheme(choice);
    if (choice !== "system" || !window.matchMedia) return;
    const q = window.matchMedia("(prefers-color-scheme: dark)");
    const again = () => applyTheme("system");
    q.addEventListener("change", again);
    return () => q.removeEventListener("change", again);
  }, [loading, signedIn, choice]);
  return null;
}
