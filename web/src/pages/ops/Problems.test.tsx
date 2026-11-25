import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AuthProvider } from "../../auth";
import { Problems } from "./Problems";

afterEach(() => vi.restoreAllMocks());

describe("problem queue", () => {
  it("groups what needs a person, with a count per group and in total", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (url) => {
      const u = String(url);
      const body = u.includes("auth/me")
        ? { id: 1, username: "o", name: "O", role: "ops", permissions: { "bookings.view": "all" } }
        : u.includes("stuck-uploads")
          ? [
              {
                id: "a",
                booking: "b1",
                booking_id: "B1",
                field_key: "p",
                status: "pending",
                expert: "ravi",
                created_at: "2026-11-23T01:00:00Z",
              },
              {
                id: "b",
                booking: "b2",
                booking_id: "B2",
                field_key: "p",
                status: "uploaded",
                expert: "ravi",
                created_at: "2026-11-23T01:00:00Z",
              },
            ]
          : u.includes("problems/reports")
            ? [{ booking: "b3", booking_id: "B3", status: "failed", error: "render_failed" }]
            : u.includes("problem=conflict")
              ? {
                  count: 1,
                  next: null,
                  previous: null,
                  results: [{ id: "b4", booking_id: "B4", conflict: "TWO_EXPERTS", stage: "submitted", alerts: [], answers: {} }],
                }
              : { count: 0, next: null, previous: null, results: [] };
      return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
    });
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <AuthProvider>
            <Problems />
          </AuthProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    const list = await screen.findByRole("list", { name: "Needs you" });
    await waitFor(() => expect(list).toHaveTextContent("B4: two experts submitted"));
    expect(list).toHaveTextContent("Upload stuck: B1");
    expect(list).toHaveTextContent("Report failed: B3");
    expect(screen.getByRole("heading", { name: /Needs you/ })).toHaveTextContent("4");
    expect(screen.getByRole("button", { name: "Stuck uploads 2" })).toBeInTheDocument(); // one filter per kind present
    expect(screen.queryByRole("button", { name: /Type changes/ })).toBeNull();
  });
  it("says so when there is nothing wrong", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(
      async (url) =>
        new Response(
          JSON.stringify(
            String(url).includes("auth/me")
              ? { id: 1, username: "o", name: "O", role: "ops", permissions: { "bookings.view": "all" } }
              : String(url).includes("problem=")
                ? { count: 0, next: null, previous: null, results: [] }
                : [],
          ),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
    );
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <AuthProvider>
            <Problems />
          </AuthProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(await screen.findByText("All clear")).toBeInTheDocument();
  });
  it("a server error is never shown as all clear (H-17)", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (url) =>
      String(url).includes("auth/me")
        ? new Response(JSON.stringify({ id: 1, username: "o", name: "O", role: "ops", permissions: { "bookings.view": "all" } }), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          })
        : new Response("{}", { status: 500, headers: { "Content-Type": "application/json" } }),
    );
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter>
          <AuthProvider>
            <Problems />
          </AuthProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(await screen.findByText("Could not load what needs you.")).toBeInTheDocument();
    expect(screen.queryByText("All clear")).toBeNull();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });
  it("the count is the server's, not the first page's (F-153)", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (url) => {
      const u = String(url);
      const body = u.includes("auth/me")
        ? { id: 1, username: "o", name: "O", role: "ops", permissions: { "bookings.view": "all" } }
        : u.includes("problem=conflict")
          ? {
              count: 60,
              next: "x",
              previous: null,
              results: [{ id: "b4", booking_id: "B4", conflict: "TWO_EXPERTS", stage: "submitted", alerts: [], answers: {} }],
            }
          : u.includes("problem=") || u.includes("stage=draft")
            ? { count: 0, next: null, previous: null, results: [] }
            : [];
      return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
    });
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <AuthProvider>
            <Problems />
          </AuthProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.getByRole("heading", { name: /Needs you/ })).toHaveTextContent("60"));
  });
  it("lists this week's bookings stamped on an unchecked phone clock as Unverified times (F-222)", async () => {
    const asked: string[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (url) => {
      const u = String(url);
      asked.push(u);
      const body = u.includes("auth/me")
        ? { id: 1, username: "o", name: "O", role: "ops", permissions: { "bookings.view": "all" } }
        : u.includes("problem=unverified_time")
          ? {
              count: 1,
              next: null,
              previous: null,
              results: [
                {
                  id: "b9",
                  booking_id: "B9",
                  stage: "completed",
                  unverified_time: true,
                  alerts: [],
                  answers: { inspection_date: "2026-11-24", inspection_time: "10:00" },
                },
              ],
            }
          : u.includes("problem=") || u.includes("bookings?")
            ? { count: 0, next: null, previous: null, results: [] }
            : [];
      return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
    });
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <AuthProvider>
            <Problems />
          </AuthProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    const list = await screen.findByRole("list", { name: "Needs you" });
    await waitFor(() => expect(list).toHaveTextContent("B9: time not verified"));
    expect(screen.getByRole("button", { name: "Unverified times 1" })).toBeInTheDocument();
    expect(asked.find((u) => u.includes("problem=unverified_time"))).toMatch(/date_from=.*date_to=/); // this week only: the mark never clears
  });
});
