import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Booking } from "./api/types";
import { activityText } from "./pages/ops/booking/ActivityCard";
import { WaitingFiles } from "./pages/ops/booking/WaitingFiles";
import { ToastProvider } from "./ui/kit";

const added: { replaces?: string }[] = [];
vi.mock("./lib/uploadManager", () => ({
  addFile: async (a: { replaces?: string }) => (added.push(a), `new${added.length}`),
  uploaded: async () => {},
  discardFile: async () => {},
}));
vi.mock("./auth", () => ({ useAuth: () => ({ can: () => true }) }));

afterEach(() => vi.restoreAllMocks());

const booking = { id: "b1", booking_id: "DEMO-4", stage: "submitted", row_version: 3 } as unknown as Booking;

function serve(missing: unknown[], phone: unknown = null) {
  const calls: { call: string; body?: unknown }[] = [];
  vi.spyOn(globalThis, "fetch").mockImplementation(async (url, init) => {
    calls.push({ call: `${init?.method ?? "GET"} ${String(url)}`, body: init?.body ? JSON.parse(String(init.body)) : undefined });
    const body = String(url).includes("missing-files") ? { missing, can_finish: missing.length > 0, phone } : { stage: "completed" };
    return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
  });
  return calls;
}

const row = (o: Record<string, unknown>) => ({
  part: "inspection",
  page: "Inspection",
  section: "Exterior",
  ids: ["m1"],
  of: 1,
  count: 1,
  required: false,
  ...o,
});

function show(onFinished = () => {}) {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <ToastProvider>
          <WaitingFiles booking={booking} fields={[]} expert="Imran" onFinished={onFinished} />
        </ToastProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("waiting for the expert's files (lost phone)", () => {
  it("one row per field, required first, with where it is and how many are missing", async () => {
    serve(
      [
        row({ key: "front", label: "Front photos", count: 2, of: 5, ids: ["a", "b"] }),
        row({ key: "odo", label: "Odometer photo", required: true, page: "Check-in", section: "Arrival", part: "start" }),
      ],
      { last_seen_at: new Date(Date.now() - 9 * 3600_000).toISOString(), files: 3 },
    );
    show();
    const box = await screen.findByRole("status", { name: "Waiting for files" });
    expect(box).toHaveTextContent("Waiting for 3 files from the expert, 1 required");
    expect(box).toHaveTextContent("Imran's phone: not seen for 9 h, still holds 3 files. It may be lost.");
    const items = screen.getAllByRole("listitem");
    expect(items[0]).toHaveTextContent("Check-in › Arrival › Odometer photo");
    expect(items[0]).toHaveTextContent("Required");
    expect(items[1]).toHaveTextContent("2 of 5 photos not arrived");
  });
  it("required files missing: Ops can still finish, with a reason and a note", async () => {
    const calls = serve([row({ key: "odo", label: "Odometer photo", required: true })]);
    const onFinished = vi.fn();
    const u = userEvent.setup();
    show(onFinished);
    await u.click(await screen.findByRole("button", { name: "Finish without the missing files" }));
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveTextContent("1 is required");
    await u.selectOptions(screen.getByLabelText("Reason"), "phone_lost");
    await u.type(screen.getByLabelText("Note (optional)"), "Phone fell in water");
    await u.click(screen.getByRole("button", { name: "Finish" }));
    await waitFor(() => expect(onFinished).toHaveBeenCalled());
    expect(calls.find((c) => c.call === "POST /api/v1/bookings/b1/finish")?.body).toEqual({
      reason: "phone_lost",
      note: "Phone fell in water",
    });
  });
  it("a phone seen recently: wait", async () => {
    serve([row({ key: "front", label: "Front photos" })], { last_seen_at: new Date().toISOString(), files: 1 });
    show();
    expect(await screen.findByRole("status", { name: "Waiting for files" })).toHaveTextContent(
      "seen 0 mins ago, still holds 1 file. Usually wait.",
    );
  });
  it("one pick fills the missing places in order; extra files are not used", async () => {
    const calls = serve([row({ key: "front", label: "Front photos", count: 2, of: 5, ids: ["a", "b"] })]);
    const u = userEvent.setup();
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <ToastProvider>
            <WaitingFiles
              booking={booking}
              fields={[
                {
                  key: "front",
                  label: "Front photos",
                  type: "photo",
                  part: "inspection",
                  section: "Exterior",
                  max: 5,
                  opsOk: true,
                  accept: "image/*",
                },
              ]}
              expert="Imran"
              onFinished={() => {}}
            />
          </ToastProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    await screen.findByRole("status", { name: "Waiting for files" });
    const files = [1, 2, 3].map((i) => new File(["x"], `p${i}.jpg`, { type: "image/jpeg" }));
    await u.upload(document.querySelector<HTMLInputElement>('input[type="file"]')!, files);
    await waitFor(() => expect(added.map((a) => a.replaces)).toEqual(["a", "b"]));
    await waitFor(() =>
      expect(calls.filter((c) => c.call.includes("/attach")).map((c) => c.body)).toEqual([{ replaces: "a" }, { replaces: "b" }]),
    );
    expect(await screen.findByText(/Only 2 were missing; 1 photo not used/)).toBeInTheDocument();
  });
  it("nothing missing: no box", async () => {
    serve([]);
    show();
    await waitFor(() => expect(screen.queryByRole("status", { name: "Waiting for files" })).toBeNull());
  });
  it("the history says who finished it and without what", () => {
    const line = activityText(
      {
        at: "",
        kind: "finished_without_files",
        by: { id: 1, name: "Priya", role: "ops" },
        changes: { stage: ["submitted", "completed"], missing: 2 as never, required: 1 as never, reason: "customer_waiting" as never },
        keys: ["inspection.front", "stage"],
      },
      () => "",
      (k) => (k === "inspection.front" ? "Front photos" : k),
      (k) => String(k),
    );
    expect(line).toBe("Finished by Priya without 2 files (1 required): Front photos · customer is waiting");
  });
});
