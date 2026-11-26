import { Component, lazy, type ComponentType, type ReactNode } from "react";
import { report } from "../lib/monitor";

/** A page that crashed shows a way out instead of a blank screen. */
export class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  componentDidCatch(error: unknown) {
    report(error, { where: "page" });
  }
  render() {
    if (!this.state.failed) return this.props.children;
    const offline = typeof navigator !== "undefined" && navigator.onLine === false;
    return (
      <div className="empty-state load-error" role="alert" style={{ margin: 24 }}>
        <strong>{offline ? "No connection: this page could not be opened." : "Something went wrong on this page."}</strong>
        <span>{offline ? "Reload once you are back online. What you saved is kept." : "Reload to try again. What you saved is kept."}</span>
        <button className="primary" onClick={() => location.reload()}>
          Reload
        </button>
      </div>
    );
  }
}

const RELOADED = "vayu:chunk-reload";
// Safari and Firefox cancel a page file still loading when the browser leaves the page: that is
// not a missing file, and a reload then would undo where the person was going (F-6)
let leaving = false;
if (typeof window !== "undefined") {
  window.addEventListener("beforeunload", () => {
    leaving = true;
    setTimeout(() => (leaving = false), 1000); // still here: the person chose to stay
  });
  window.addEventListener("pagehide", () => (leaving = true));
  window.addEventListener("pageshow", () => (leaving = false)); // back from the back/forward cache
}
/** A lazy page whose file is gone (a new version went live while the tab was open) reloads the
 *  app once to fetch the new files; a second failure goes to the error boundary. */
export function lazyPage(load: () => Promise<{ default: ComponentType }>) {
  return lazy(() =>
    load().then(
      (m) => {
        try {
          sessionStorage.removeItem(RELOADED);
        } catch {
          /* blocked */
        }
        return m;
      },
      (e: unknown) => {
        if (leaving) return new Promise<{ default: ComponentType }>(() => {});
        let first = false;
        try {
          first = !sessionStorage.getItem(RELOADED) && navigator.onLine !== false;
          if (first) sessionStorage.setItem(RELOADED, "1");
        } catch {
          /* blocked: do not loop */
        }
        // offline, a reload would only land on the browser's "no internet" page and lose the app
        if (!first || navigator.onLine === false) throw e;
        location.reload();
        return new Promise<{ default: ComponentType }>(() => {});
      },
    ),
  );
}
