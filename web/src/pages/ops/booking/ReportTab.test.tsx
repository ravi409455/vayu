import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AuthProvider } from "../../../auth";
import { reportProblems } from "../../../lib/problems";
import { ReportTab } from "./ReportTab";
import { ToastProvider } from "../../../ui/kit";

afterEach(() => vi.restoreAllMocks());
const json = (x: unknown, status = 200) => new Response(JSON.stringify(x), { status, headers: { "Content-Type": "application/json" } });
const report = (over: Record<string, unknown>) => ({ revision: 1, status: "ready", updating: false, generated_at: "2026-11-25T10:00:00Z", filename: "r.pdf", error: "",
  url: null, out_of_date: true, regenerate: { allowed: true, reason: null }, ...over });

function mount(rep: Record<string, unknown>, perms: Record<string, string> = { "reports.view": "all", "submissions.edit": "all" }) {
  const posts: string[] = [];
  let release!: () => void;
  vi.spyOn(globalThis, "fetch").mockImplementation(async (url, init) => {
    const u = String(url);
    if (u.includes("auth/me")) return json({ id: 1, username: "o", role: "ops", permissions: perms });
    if (u.endsWith("/report/regenerate")) { posts.push(String(init?.method)); await new Promise<void>((r) => { release = r; }); return new Response(null, { status: 202 }); }
    if (u.endsWith("/report")) return json(rep);
    return json([]);
  });
  render(<QueryClientProvider client={new QueryClient()}><MemoryRouter><AuthProvider><ToastProvider>
    <ReportTab booking={{ id: "b1", stage: "completed" } as never} activity={[]} /></ToastProvider></AuthProvider></MemoryRouter></QueryClientProvider>);
  return { posts, release: () => release() };
}

describe("reports are made again only by Regenerate (F-219)", () => {
  it("an out-of-date PDF says so, and a double click sends one regenerate", async () => {
    const m = mount(report({}));
    expect(await screen.findByText(/Out of date: changes since this PDF/)).toBeInTheDocument();
    const button = await screen.findByRole("button", { name: "Regenerate" });
    await userEvent.setup().dblClick(button);
    await waitFor(() => expect(m.posts).toEqual(["POST"]));
    expect(screen.getByRole("button", { name: "Making…" })).toBeDisabled();
    m.release();
  });
  it("when it cannot be made, the button is off and says why", async () => {
    mount(report({ out_of_date: false, regenerate: { allowed: false, reason: "Its photos were removed by the retention setting, so the last PDF is kept." } }));
    const button = await screen.findByRole("button", { name: "Regenerate" });
    expect(button).toBeDisabled();
    expect(screen.getByText(/Regenerate is off: Its photos were removed/)).toBeInTheDocument();
    expect(screen.queryByText(/Out of date/)).toBeNull();
  });
  it("no Regenerate for someone who may not change submissions", async () => {
    mount(report({}), { "reports.view": "all" });
    expect(await screen.findByText(/Out of date: changes since this PDF/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Regenerate" })).toBeNull();
  });
  it("Needs you lists out-of-date reports apart from failed and stuck ones", () => {
    const row = (problem: "failed" | "stuck" | "out_of_date", since: string | null = null) => ({ booking: problem, booking_id: problem.toUpperCase(), status: "ready", error: "", problem, out_of_date_since: since });
    const r = reportProblems([row("failed"), row("stuck"), row("out_of_date", "2026-11-25T10:00:00Z")]);
    expect(r.failed.map((x) => x.booking)).toEqual(["failed", "stuck"]);
    expect(r.outOfDate).toEqual([{ booking: "out_of_date", booking_id: "OUT_OF_DATE", since: "2026-11-25T10:00:00Z" }]);
  });
});
