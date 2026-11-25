import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MyJobs } from "./pages/expert/MyJobs";

const json = (x: unknown) => new Response(JSON.stringify(x), { status: 200, headers: { "Content-Type": "application/json" } });
const lead = (id: string, stage: string, date: string) => ({
  id,
  booking_id: id,
  stage,
  inspection_type: "pdi",
  answers: { customer_name: `Customer ${id}`, inspection_date: date, inspection_time: "10:00" },
});

afterEach(() => vi.restoreAllMocks());

describe("My leads (H-14 / F-103)", () => {
  it("lists an open lead however many newer bookings the expert has", async () => {
    const seen: string[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (u) => {
      const url = String(u);
      seen.push(url);
      if (url.includes("stage=assigned"))
        return json({ count: 1, next: null, previous: null, results: [lead("OLD-1", "assigned", "2026-12-20")] });
      if (url.includes("/bookings")) return json({ count: 0, next: null, previous: null, results: [] });
      return json([]);
    });
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <MyJobs />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(await screen.findByRole("link", { name: "Lead OLD-1" })).toBeInTheDocument();
    expect(seen.some((u) => u.includes("bookings?date_from="))).toBe(true); // finished ones: by date, with "Show older leads"
  });
});
