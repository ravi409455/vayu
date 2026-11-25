import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AuthProvider } from "./auth";
import { Bookings } from "./pages/ops/Bookings";
import { ToastProvider } from "./ui/kit";

afterEach(() => vi.restoreAllMocks());

function serve(perms: Record<string, string>) {
  const calls: string[] = [];
  vi.spyOn(globalThis, "fetch").mockImplementation(async (url) => {
    const u = String(url);
    calls.push(u);
    const body = u.includes("auth/me")
      ? { id: 1, username: "ops", name: "Priya", role: "ops", permissions: perms }
      : u.includes("answer-fields")
        ? [
            {
              field: "end.payment_verified",
              label: "Payment verified?",
              type: "single_choice",
              form: "Wrap-up",
              options: [
                { value: "verified", label: "Verified" },
                { value: "mismatch", label: "Mismatch" },
              ],
            },
          ]
        : u.includes("inspection-types")
          ? [{ key: "pdi", label: "PDI", available: true }]
          : u.includes("/bookings?") || u.endsWith("/bookings")
            ? { count: 0, next: null, previous: null, results: [] }
            : [];
    return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
  });
  return calls;
}

function show() {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter initialEntries={["/bookings?view=all"]}>
        <AuthProvider>
          <ToastProvider>
            <Bookings />
          </ToastProvider>
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("filter bookings by an answer (generic: payments are ordinary fields)", () => {
  it("picks a field, then a value or 'Not filled', and asks the server for exactly that", async () => {
    const calls = serve({ "bookings.view": "all", "submissions.view": "all" });
    const u = userEvent.setup();
    show();
    await screen.findByLabelText("Filter bookings");
    expect(screen.queryByLabelText("Answer")).toBeNull(); // a type comes first
    await u.selectOptions(await screen.findByLabelText("Type"), "pdi");
    await u.selectOptions(await screen.findByLabelText("Answer"), "end.payment_verified");
    expect(calls.some((c) => c.includes("answer-fields?type=pdi"))).toBe(true);
    expect(screen.getByLabelText("Answer value")).toHaveTextContent("Not filled");
    expect(calls.some((c) => c.includes("answer="))).toBe(false); // waits for a value
    await u.selectOptions(screen.getByLabelText("Answer value"), "__none__");
    await waitFor(() => expect(calls.some((c) => c.includes("answer=end.payment_verified") && c.includes("value=__none__"))).toBe(true));
    await u.selectOptions(screen.getByLabelText("Type"), ""); // a new type clears it
    expect(screen.queryByLabelText("Answer value")).toBeNull();
  });
  it("is not offered to someone who may not see inspection answers", async () => {
    const calls = serve({ "bookings.view": "all" });
    show();
    await screen.findByLabelText("Filter bookings");
    expect(screen.queryByLabelText("Answer")).toBeNull();
    expect(calls.some((c) => c.includes("answer-fields"))).toBe(false);
  });
});

describe("typing in the Bookings filter (F-085)", () => {
  it("asks the server once typing pauses, not once per letter", async () => {
    const calls = serve({ "bookings.view": "all" });
    const u = userEvent.setup();
    show();
    const box = await screen.findByLabelText("Filter bookings");
    await waitFor(() => expect(calls.some((c) => c.includes("/bookings?"))).toBe(true));
    await u.type(box, "Sharma");
    await waitFor(() => expect(calls.some((c) => c.includes("search=Sharma"))).toBe(true));
    const partial = calls.filter((c) => /search=S(h|ha|har|harm)?(&|$)/.test(c));
    expect(partial).toEqual([]); // no request for "S", "Sh", … "Sharm"
  });
});
