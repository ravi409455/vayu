import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Booking } from "./api/types";
import { WaitingFiles, activityText } from "./pages/ops/Booking";
import { ToastProvider } from "./ui/kit";

afterEach(() => vi.restoreAllMocks());

const booking = { id: "b1", booking_id: "DEMO-4", stage: "submitted", row_version: 3 } as unknown as Booking;

function serve(missing: unknown[], canFinish: boolean) {
  const calls: string[] = [];
  vi.spyOn(globalThis, "fetch").mockImplementation(async (url, init) => {
    calls.push(`${init?.method ?? "GET"} ${String(url)}`);
    const body = String(url).includes("missing-files") ? { missing, can_finish: canFinish } : { stage: "completed" };
    return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
  });
  return calls;
}

function show(onFinished = () => {}, onMedia = () => {}) {
  render(<QueryClientProvider client={new QueryClient()}><MemoryRouter><ToastProvider>
    <WaitingFiles booking={booking} onFinished={onFinished} onMedia={onMedia} />
  </ToastProvider></MemoryRouter></QueryClientProvider>);
}

describe("waiting for the expert's files (lost phone)", () => {
  it("a required file must be uploaded by Ops before finishing", async () => {
    serve([{ part: "inspection", key: "odo", label: "Odometer photo", count: 1, required: true },
      { part: "inspection", key: "front", label: "Front photos", count: 2, required: false }], false);
    const onMedia = vi.fn();
    show(() => {}, onMedia);
    const box = await screen.findByRole("status", { name: "Waiting for files" });
    expect(box).toHaveTextContent("Waiting for 3 files from the expert: Odometer photo · required, Front photos (2).");
    expect(screen.getByRole("button", { name: "Finish without the missing files" })).toBeDisabled();
    await userEvent.setup().click(screen.getByRole("button", { name: "Open Media" }));
    expect(onMedia).toHaveBeenCalled();
  });
  it("only optional files missing: Ops confirm and the job finishes", async () => {
    const calls = serve([{ part: "inspection", key: "front", label: "Front photos", count: 2, required: false }], true);
    const onFinished = vi.fn();
    const u = userEvent.setup();
    show(onFinished);
    await u.click(await screen.findByRole("button", { name: "Finish without the missing files" }));
    expect(screen.getByRole("dialog")).toHaveTextContent("without 2 files");
    await u.click(screen.getByRole("button", { name: "Finish" }));
    await waitFor(() => expect(onFinished).toHaveBeenCalled());
    expect(calls).toContain("POST /api/v1/bookings/b1/finish");
  });
  it("nothing missing: no box", async () => {
    serve([], false);
    show();
    await waitFor(() => expect(screen.queryByRole("status", { name: "Waiting for files" })).toBeNull());
  });
  it("the history says who finished it and without what", () => {
    const line = activityText({ at: "", kind: "finished_without_files", by: { id: 1, name: "Priya", role: "ops" },
      changes: { stage: ["submitted", "completed"], missing: 2 as never }, keys: ["inspection.front", "stage"] },
    () => "", (k) => k === "inspection.front" ? "Front photos" : k, (k) => String(k));
    expect(line).toBe("Finished by Priya without 2 files: Front photos");
  });
});
