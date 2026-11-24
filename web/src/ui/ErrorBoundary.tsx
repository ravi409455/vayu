import { Component, lazy, type ComponentType, type ReactNode } from "react";
import { report } from "../lib/monitor";

/** A page that crashed shows a way out instead of a blank screen. */
export class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch(error: unknown) { report(error, { where: "page" }); }
  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <div className="empty-state load-error" role="alert" style={{ margin: 24 }}>
        <strong>Something went wrong on this page.</strong>
        <span>Reload to try again. What you saved is kept.</span>
        <button className="primary" onClick={() => location.reload()}>Reload</button>
      </div>
    );
  }
}

const RELOADED = "vayu:chunk-reload";
/** A lazy page whose file is gone (a new version went live while the tab was open) reloads the
 *  app once to fetch the new files; a second failure goes to the error boundary. */
export function lazyPage(load: () => Promise<{ default: ComponentType }>) {
  return lazy(() => load().then((m) => { try { sessionStorage.removeItem(RELOADED); } catch { /* blocked */ } return m; }, (e: unknown) => {
    let first = false;
    try { first = !sessionStorage.getItem(RELOADED); if (first) sessionStorage.setItem(RELOADED, "1"); } catch { /* blocked: do not loop */ }
    if (!first) throw e;
    location.reload();
    return new Promise<{ default: ComponentType }>(() => {});
  }));
}
