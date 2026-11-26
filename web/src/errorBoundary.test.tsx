import { render, screen } from "@testing-library/react";
import { Suspense } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ErrorBoundary, lazyPage } from "./ui/ErrorBoundary";

afterEach(() => {
  vi.restoreAllMocks();
  sessionStorage.clear();
});

describe("a page that breaks (R-13)", () => {
  it("shows Reload instead of a blank screen", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    function Boom(): never {
      throw new Error("boom");
    }
    render(
      <ErrorBoundary>
        <Boom />
      </ErrorBoundary>,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Something went wrong on this page.");
    expect(screen.getByRole("button", { name: "Reload" })).toBeInTheDocument();
  });
  it("a lazy page that fails to load reloads the app once, then shows the error", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const reload = vi.fn();
    vi.spyOn(window, "location", "get").mockReturnValue({ ...window.location, reload } as Location);
    const Page = lazyPage(() => Promise.reject(new Error("chunk gone")));
    render(
      <ErrorBoundary>
        <Suspense fallback="…">
          <Page />
        </Suspense>
      </ErrorBoundary>,
    );
    await vi.waitFor(() => expect(reload).toHaveBeenCalledTimes(1));
    const Again = lazyPage(() => Promise.reject(new Error("chunk gone"))); // after the reload: still failing
    render(
      <ErrorBoundary>
        <Suspense fallback="…">
          <Again />
        </Suspense>
      </ErrorBoundary>,
    );
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(reload).toHaveBeenCalledTimes(1);
  });
  it("a page file cancelled because the browser is leaving does not reload (F-6, Safari/Firefox)", async () => {
    sessionStorage.clear();
    const reload = vi.fn();
    vi.spyOn(window, "location", "get").mockReturnValue({ ...window.location, reload } as Location);
    window.dispatchEvent(new Event("pagehide"));
    const Page = lazyPage(() => Promise.reject(new Error("cancelled")));
    render(
      <ErrorBoundary>
        <Suspense fallback="…">
          <Page />
        </Suspense>
      </ErrorBoundary>,
    );
    await new Promise((r) => setTimeout(r, 50));
    expect(reload).not.toHaveBeenCalled();
    window.dispatchEvent(new Event("pageshow"));
  });
});
