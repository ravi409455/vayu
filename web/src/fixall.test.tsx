// Second review round: failed loads are shown as failures (H-17, Roles High), API-key actions (H-1),
// the report tab with no report and after Regenerate (H-5, N2), session wipe across people (R-06).
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AuthProvider } from "./auth";
import type { Booking } from "./api/types";
import { ApiKeys } from "./pages/admin/ApiKeys";
import { Roles } from "./pages/admin/Roles";
import { Settings } from "./pages/admin/Settings";
import { ReportTab } from "./pages/ops/booking/ReportTab";
import { ToastProvider } from "./ui/kit";

afterEach(() => vi.restoreAllMocks());
const wiped = vi.fn(async () => {});
vi.mock("./lib/store", async (orig) => ({ ...(await orig<typeof import("./lib/store")>()), wipeWork: () => wiped() }));

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
const ALL = ["api_keys.manage", "settings.view", "settings.edit", "reports.view", "submissions.edit", "roles.manage", "forms.view"];
const ME = { id: 1, username: "a", name: "A", role: "admin", permissions: Object.fromEntries(ALL.map((p) => [p, "all"])) };
type Handler = (init?: RequestInit) => unknown;
function serve(routes: Record<string, Handler>) {
  const calls: { url: string; init?: RequestInit }[] = [];
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    calls.push({ url, init });
    if (url.includes("auth/me")) return json(ME);
    const hit = Object.entries(routes)
      .filter(([p]) => url.split("?")[0]!.endsWith(p))
      .sort((a, b) => b[0].length - a[0].length)[0];
    if (!hit) return json({ code: "NOT_FOUND", detail: "Not found." }, 404);
    const out = hit[1](init);
    return out instanceof Response ? out : json(out);
  });
  return calls;
}
const down = () => json({ code: "error", detail: "The server had a problem." }, 500);
const shell = (ui: React.ReactNode) =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter>
        <AuthProvider>
          <ToastProvider>{ui}</ToastProvider>
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );

describe("a failed load is never shown as empty (H-17)", () => {
  it("Roles: shows the error and offers no matrix to save over the real permissions", async () => {
    serve({
      "/permissions": () => [{ key: "bookings.view", group: "Bookings", label: "See bookings", scoped: true, grantable: true }],
      "/roles": down,
    });
    shell(<Roles />);
    expect(await screen.findByText(/Could not load permissions/)).toBeTruthy();
    expect(screen.queryByRole("radiogroup")).toBeNull();
    expect(screen.queryByText("Save changes")).toBeNull();
  });
  it("Settings: shows the error, never the defaults as saved numbers, and Save stays off", async () => {
    serve({ "/settings/timing": down, "/settings/media": () => ({ photo_days: 0, video_days: 0 }), "/forms": () => [] });
    shell(<Settings />);
    expect(await screen.findByText(/Could not load settings/)).toBeTruthy();
    expect(screen.queryByLabelText("Late-start grace (minutes)")).toBeNull();
    expect((screen.getAllByRole("button", { name: "Save" })[0] as HTMLButtonElement).disabled).toBe(true);
  });
});

describe("API keys can be given booking actions (H-1)", () => {
  it("sends the ticked actions and shows them in the list", async () => {
    const calls = serve({
      "/api-keys": (init) =>
        init?.method === "POST"
          ? { id: "k2", key: "vk_x_secret" }
          : [
              {
                id: "k1",
                name: "ERP",
                prefix: "ab",
                scope: { forms: { booking: ["*"] } },
                allow_delete: false,
                allowed_actions: ["cancel"],
                revoked_at: null,
                last_used_at: null,
              },
            ],
      "/forms": () => [{ id: 1, key: "booking", type: "booking", name: "Booking", is_active: true }],
    });
    shell(<ApiKeys />);
    expect(await screen.findByText("Cancel bookings")).toBeTruthy();
    await userEvent.click(screen.getAllByRole("button", { name: "New key" })[0]!);
    await userEvent.type(screen.getByLabelText("Name"), "CRM");
    await userEvent.type(screen.getByLabelText("Fields of booking"), "*");
    await userEvent.click(screen.getByLabelText("Assign and reassign experts"));
    await userEvent.click(screen.getByLabelText("Reschedule bookings"));
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(calls.some((c) => c.init?.method === "POST")).toBe(true));
    const body = JSON.parse(String(calls.find((c) => c.init?.method === "POST")!.init!.body));
    expect(body.allowed_actions).toEqual(["assign", "reschedule"]);
  });
});

const BOOKING = { id: "b1", booking_id: "SA1", stage: "completed", conflict: "" } as unknown as Booking;

describe("the report tab (H-5, N2)", () => {
  it("a completed booking with no report offers to make it", async () => {
    const calls = serve({ "/report": () => json({ code: "NO_REPORT", detail: "x" }, 404), "/report/regenerate": () => json({}, 202) });
    shell(<ReportTab booking={BOOKING} activity={[]} />);
    await userEvent.click(await screen.findByRole("button", { name: /Make the PDF/ }));
    await waitFor(() => expect(calls.some((c) => c.url.endsWith("report/regenerate"))).toBe(true));
  });
  it("a failed load is an error, not 'No report yet'", async () => {
    serve({ "/report": down });
    shell(<ReportTab booking={BOOKING} activity={[]} />);
    expect(await screen.findByText(/Could not load report/)).toBeTruthy();
    expect(screen.queryByText("No report yet")).toBeNull();
  });
  it("after Regenerate it keeps watching until the new revision shows, even before the worker starts", async () => {
    let revision = 1;
    const report = () => ({
      revision,
      status: "ready",
      updating: false,
      out_of_date: true,
      regenerate: { allowed: true, reason: null },
      generated_at: null,
      filename: "a.pdf",
      error: "render_failed",
      url: null,
    });
    serve({ "/report": report, "/report/regenerate": () => json({}, 202) });
    shell(<ReportTab booking={BOOKING} activity={[]} />);
    expect(await screen.findByText(/the PDF could not be made/)).toBeTruthy(); // words, not the raw code
    await userEvent.click(screen.getByRole("button", { name: /Regenerate/ }));
    expect(await screen.findByRole("button", { name: /Making/ })).toBeTruthy(); // not offered again
    revision = 2;
    await waitFor(() => expect(screen.getByRole("button", { name: /Regenerate/ })).toBeTruthy(), { timeout: 5000 });
  });
});

describe("unsent work belongs to one person (R-06)", () => {
  it("is wiped when someone else signs in after a time-out, and kept for the same person", async () => {
    const m = new Map<string, string>([["vayu:last-person", "1"]]);
    vi.stubGlobal("localStorage", {
      getItem: (k: string) => m.get(k) ?? null,
      setItem: (k: string, v: string) => void m.set(k, v),
      removeItem: (k: string) => void m.delete(k),
    });
    const { forgetOthersWork } = await import("./auth");
    wiped.mockClear();
    await forgetOthersWork(1);
    expect(wiped).not.toHaveBeenCalled(); // the same person keeps their unsent work
    await forgetOthersWork(2);
    expect(wiped).toHaveBeenCalledTimes(1);
    expect(m.get("vayu:last-person")).toBe("2");
    vi.unstubAllGlobals();
  });
});
