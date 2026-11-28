import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AppDownload } from "./pages/AppDownload";
import { ToastProvider } from "./ui/kit";

afterEach(() => vi.restoreAllMocks());
const show = (body: unknown) => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } }),
  );
  render(
    <QueryClientProvider client={new QueryClient()}>
      <ToastProvider>
        <AppDownload />
      </ToastProvider>
    </QueryClientProvider>,
  );
};

describe("APK download page (F-226)", () => {
  it("offers the newest build with its size and checksum", async () => {
    show({
      version_code: 42,
      version_name: "1.4.0",
      size: 31_457_280,
      sha256: "ab".repeat(32),
      notes: ["Faster uploads"],
      min_version: 40,
    });
    const link = await screen.findByRole("link", { name: "Download the app" });
    expect(link).toHaveAttribute("href", "/api/v1/app/download");
    expect(screen.getByText(/30\.0 MB/)).toBeInTheDocument();
    expect(screen.getByText("Faster uploads")).toBeInTheDocument();
    expect(screen.getByText("ab".repeat(32))).toBeInTheDocument();
  });
  it("says so when nothing is published yet", async () => {
    show({ version_code: null, min_version: 1 });
    expect(await screen.findByText("No app build has been published yet.")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Download/ })).toBeNull();
  });
});
