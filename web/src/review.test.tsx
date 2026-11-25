import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AuthProvider } from "./auth";
import { ReviewTab } from "./pages/ops/booking/ReviewTab";

afterEach(() => vi.restoreAllMocks());

describe("quick rating clicks (F-114)", () => {
  it("each save sends the row version the one before got back", async () => {
    let version = 5;
    const sent: number[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (url, init) => {
      const u = String(url);
      if (u.includes("auth/me")) return new Response(JSON.stringify({ id: 1, username: "o", role: "ops", permissions: { "ratings.override": "all", "bookings.view": "all" } }), { status: 200, headers: { "Content-Type": "application/json" } });
      const rv = JSON.parse(String(init?.body)).row_version as number;
      sent.push(rv);
      if (rv !== version) return new Response(JSON.stringify({ code: "STALE_INSPECTION", detail: "changed" }), { status: 409, headers: { "Content-Type": "application/json" } });
      version++;
      return new Response(JSON.stringify({ id: "i1", row_version: version }), { status: 200, headers: { "Content-Type": "application/json" } });
    });
    const insp = { id: "i1", row_version: 5, status: "submitted", scores: { ratings: {}, overall: {} } };
    const trees = { inspection: { key_checks: [], rating_config: { categories: [{ key: "body", label: "Body" }] } } };
    render(<QueryClientProvider client={new QueryClient()}><MemoryRouter><AuthProvider>
      <ReviewTab booking={{ stage: "completed" } as never} insp={insp as never} trees={trees as never} onSaved={() => {}} /></AuthProvider></MemoryRouter></QueryClientProvider>);
    const group = await screen.findByRole("radiogroup", { name: "Body rating" });
    await waitFor(() => expect(group.querySelector("button")).toBeEnabled());
    const u = userEvent.setup();
    const [, , , three, four] = group.querySelectorAll("button");
    await u.click(three!); await u.click(four!);
    await waitFor(() => expect(sent).toEqual([5, 6]));
  });
});
