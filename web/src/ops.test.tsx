import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "./api/client";
import type { FormField, FormPage } from "./api/types";
import { saveDirty } from "./lib/saveDirty";
import { Problems } from "./pages/ops/Problems";
import { pivot } from "./pages/ops/Dashboards";
import { FormRenderer } from "./ui/FormRenderer";
import { StaleDialog } from "./ui/StaleDialog";

afterEach(() => vi.restoreAllMocks());

describe("409 'changed by someone': retry only my own fields", () => {
  const stale = new ApiError(409, { code: "STALE_INSPECTION", detail: "x", changed_by: "priya", changed_at: "2026-11-23T10:00:00Z", changed_keys: ["remarks"], row_version: 7 });

  it("turns the 409 into data, sends only the changed fields, and retries with the new version", async () => {
    const send = vi.fn().mockRejectedValueOnce(stale).mockResolvedValueOnce({ ok: 1 });
    const mine = { odometer: 150 };
    const first = await saveDirty(send, 3, mine);
    expect(first).toEqual({ ok: false, stale: { by: "priya", at: "2026-11-23T10:00:00Z", keys: ["remarks"], rowVersion: 7 } });
    const second = await saveDirty(send, first.ok ? 0 : first.stale.rowVersion, mine);
    expect(second.ok).toBe(true);
    expect(send).toHaveBeenNthCalledWith(1, 3, { odometer: 150 });
    expect(send).toHaveBeenNthCalledWith(2, 7, { odometer: 150 });      // only my field, on the newest version
  });
  it("other failures are not swallowed", async () => {
    await expect(saveDirty(vi.fn().mockRejectedValue(new ApiError(400, { detail: "bad" })), 1, {})).rejects.toBeInstanceOf(ApiError);
    await expect(saveDirty(vi.fn().mockRejectedValue(new ApiError(409, { code: "DRAFT_EXISTS" })), 1, {})).rejects.toBeInstanceOf(ApiError);
  });
  it("the dialog names who changed it and warns when both changed the same field", async () => {
    const onRetry = vi.fn();
    const u = userEvent.setup();
    render(<StaleDialog info={{ by: "priya", at: "", keys: ["remarks", "odometer"], rowVersion: 7 }} mine={["odometer"]} onRetry={onRetry} onReload={() => {}} />);
    expect(screen.getByRole("dialog", { name: /priya changed this/ })).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("odometer");
    await u.click(screen.getByRole("button", { name: /Save only my 1 change/ }));
    expect(onRetry).toHaveBeenCalled();
  });
  it("no warning when the changes do not overlap", () => {
    render(<StaleDialog info={{ by: "priya", at: "", keys: ["remarks"], rowVersion: 7 }} mine={["odometer", "city"]} onRetry={() => {}} onReload={() => {}} />);
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByRole("button", { name: /Save only my 2 changes/ })).toBeInTheDocument();
  });
});

describe("problem queue", () => {
  it("shows a count on each tab that has something", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (url) => {
      const u = String(url);
      const body = u.includes("stuck-uploads") ? [{ id: "a", booking: "b1", booking_id: "B1", field_key: "p", status: "pending", expert: "ravi", created_at: "2026-11-23T01:00:00Z" }, { id: "b", booking: "b2", booking_id: "B2", field_key: "p", status: "uploaded", expert: "ravi", created_at: "2026-11-23T01:00:00Z" }]
        : u.includes("problems/reports") ? [{ booking: "b3", booking_id: "B3", status: "failed", stale: false, error: "render_failed" }]
        : u.includes("problem=conflict") ? { count: 1, next: null, previous: null, results: [{ id: "b4", booking_id: "B4", conflict: "TWO_EXPERTS", stage: "submitted", alerts: [] }] }
        : { count: 0, next: null, previous: null, results: [] };
      return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
    });
    render(<QueryClientProvider client={new QueryClient()}><MemoryRouter><Problems /></MemoryRouter></QueryClientProvider>);
    expect(await screen.findByRole("tab", { name: "Stuck uploads (2)" })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("tab", { name: "Conflicts (1)" })).toBeInTheDocument());
    expect(screen.getByRole("tab", { name: "PDF problems (1)" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Rejected type changes" })).toBeInTheDocument();     // empty: no count
    expect(screen.getByText("B1")).toBeInTheDocument();
  });
  it("says so when there is nothing wrong", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (url) => new Response(JSON.stringify(String(url).includes("problem=") ? { count: 0, next: null, previous: null, results: [] } : []), { status: 200, headers: { "Content-Type": "application/json" } }));
    render(<QueryClientProvider client={new QueryClient()}><MemoryRouter><Problems /></MemoryRouter></QueryClientProvider>);
    expect(await screen.findByText("No uploads are stuck.")).toBeInTheDocument();
  });
});

describe("dashboard table", () => {
  it("lines rows up by period and key, zero when missing", () => {
    const { periods, keys, cell } = pivot([{ period: "2026-10-14", key: "pdi", count: 2 }, { period: "2026-10-14", key: "ev", count: 1 }, { period: "2026-10-21", key: "pdi", count: 3 }]);
    expect(periods).toEqual(["2026-10-14", "2026-10-21"]);
    expect(keys).toEqual(["ev", "pdi"]);
    expect([cell("2026-10-14", "pdi"), cell("2026-10-21", "ev")]).toEqual([2, 0]);
    expect(pivot([]).periods).toEqual([]);
  });
});

let n = 100;
const fld = (key: string, type: string, over: Partial<FormField> = {}): FormField => ({
  id: ++n, section: 1, key, label: key, helper_text: "", type, config: {}, required: false, required_if: null, show_if: null, visible: true, order: 0,
  is_system: false, access: {}, locked: false, library: null, ...over,
});
const pageOf = (fields: FormField[]): FormPage => ({ id: 1, title: "P", order: 0, visible: true, gate: false, show_if: null, access: {}, sections: [{ id: 1, page: 1, title: "S", order: 0, visible: true, show_if: null, access: {}, fields, locked: false, library: null }] });

describe("form renderer", () => {
  const tree = { pages: [pageOf([fld("door", "short_text"), fld("kc", "derived", { config: { rule: { "!!": [1] }, true_label: "Found" } }), fld("engine", "rating"), fld("view_only", "short_text", { level: "view" })])], checks: [] };
  function show(role: string) {
    render(<QueryClientProvider client={new QueryClient()}><FormRenderer kind="inspection" tree={tree} values={{ view_only: "x" }} role={role} onChange={() => {}} /></QueryClientProvider>);
  }
  it("never shows ratings or Key Checks to an expert", () => {
    show("expert");
    expect(screen.getByLabelText("door")).toBeInTheDocument();
    expect(screen.queryByText("Found")).toBeNull();
    expect(screen.queryByText(/Calculated from the defects/)).toBeNull();
  });
  it("shows them to Ops, read-only", () => {
    show("ops");
    expect(screen.getByText("Found")).toBeInTheDocument();
    expect(screen.getByText(/Calculated from the defects/)).toBeInTheDocument();
  });
  it("a field the server marks view-only cannot be typed in", () => {
    show("ops");
    expect(screen.getByLabelText("view_only")).toBeDisabled();
    expect(screen.getByLabelText("door")).toBeEnabled();
  });
  it("a rule that hides a field removes it, and a required field is starred", async () => {
    const t2 = { pages: [pageOf([fld("a", "short_text", { required: true }), fld("b", "short_text", { show_if: { "==": [{ var: "inspection.a" }, "x"] } })])], checks: [] };
    const { rerender } = render(<QueryClientProvider client={new QueryClient()}><FormRenderer kind="inspection" tree={t2} values={{}} onChange={() => {}} /></QueryClientProvider>);
    expect(screen.getByText("a *")).toBeInTheDocument();
    expect(screen.queryByLabelText("b")).toBeNull();
    rerender(<QueryClientProvider client={new QueryClient()}><FormRenderer kind="inspection" tree={t2} values={{ a: "x" }} onChange={() => {}} /></QueryClientProvider>);
    expect(screen.getByLabelText("b")).toBeInTheDocument();
  });
  it("typing reports the change, choice buttons toggle, and GPS refusal says 'GPS unavailable'", async () => {
    const onChange = vi.fn();
    const u = userEvent.setup();
    const t3 = { pages: [pageOf([fld("note", "short_text"), fld("fuel", "single_choice", { config: { options: [{ key: "p", label: "Petrol" }, { key: "d", label: "Diesel" }] } }), fld("loc", "gps")])], checks: [] };
    Object.defineProperty(globalThis.navigator, "geolocation", { configurable: true, value: { getCurrentPosition: (_ok: unknown, bad: () => void) => bad() } });
    render(<QueryClientProvider client={new QueryClient()}><FormRenderer kind="inspection" tree={t3} values={{}} onChange={onChange} /></QueryClientProvider>);
    await u.type(screen.getByLabelText("note"), "a");
    expect(onChange).toHaveBeenCalledWith("note", "a");
    await u.click(screen.getByRole("radio", { name: "Diesel" }));
    expect(onChange).toHaveBeenCalledWith("fuel", "d");
    expect(await screen.findByText("GPS unavailable")).toBeInTheDocument();        // asked by itself, no button needed
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });
  it("takes the location by itself and reports it once", async () => {
    const onChange = vi.fn();
    Object.defineProperty(globalThis.navigator, "geolocation", { configurable: true, value: { getCurrentPosition: (ok: (p: unknown) => void) => ok({ coords: { latitude: 28.61394, longitude: 77.20902, accuracy: 12.4 } }) } });
    render(<QueryClientProvider client={new QueryClient()}><FormRenderer kind="inspection" tree={{ pages: [pageOf([fld("loc", "gps")])], checks: [] }} values={{}} onChange={onChange} /></QueryClientProvider>);
    await waitFor(() => expect(onChange).toHaveBeenCalledWith("loc", { lat: 28.61394, lng: 77.20902, accuracy: 12 }));
    expect(onChange).toHaveBeenCalledTimes(1);
  });
  it("does not ask for the location when a value exists, in read-only mode, or in the builder's preview", () => {
    const ask = vi.fn();
    Object.defineProperty(globalThis.navigator, "geolocation", { configurable: true, value: { getCurrentPosition: ask } });
    const t = { pages: [pageOf([fld("loc", "gps")])], checks: [] };
    const wrap = (props: { values: Record<string, unknown>; readOnly?: boolean; preview?: boolean }) => <QueryClientProvider client={new QueryClient()}><FormRenderer kind="inspection" tree={t} onChange={() => {}} {...props} /></QueryClientProvider>;
    render(wrap({ values: { loc: { lat: 1, lng: 2 } } }));
    render(wrap({ values: {}, readOnly: true }));
    render(wrap({ values: {}, preview: true }));
    expect(ask).not.toHaveBeenCalled();
    expect(screen.getByText(/Taken automatically/)).toBeInTheDocument();
  });
  it.each([["both", true, true], ["camera", true, false], ["upload", false, true]])("capture mode %s shows camera=%s attach=%s", (mode, camera, attach) => {
    const t = { pages: [pageOf([fld("shot", "photo", { config: { max_count: 2, capture: mode } })])], checks: [] };
    render(<QueryClientProvider client={new QueryClient()}><FormRenderer kind="inspection" tree={t} values={{}} bookingId="b1" onChange={() => {}} /></QueryClientProvider>);
    expect(!!screen.queryByRole("button", { name: /Open camera/ })).toBe(camera);
    expect(!!screen.queryByRole("button", { name: /Attach a photo/ })).toBe(attach);
  });
  it("videos offer Record instead of Camera, and files only ever offer Attach", () => {
    const t = { pages: [pageOf([fld("clip", "video", { config: { max_count: 1 } }), fld("doc", "file", { config: { max_count: 1 } })])], checks: [] };
    render(<QueryClientProvider client={new QueryClient()}><FormRenderer kind="inspection" tree={t} values={{}} bookingId="b1" onChange={() => {}} /></QueryClientProvider>);
    expect(screen.getByRole("button", { name: "Open camera: video" })).toHaveTextContent("Record");
    expect(screen.getByRole("button", { name: "Attach a video" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Open camera: file" })).toBeNull();
    expect(screen.getByRole("button", { name: "Attach a file" })).toBeInTheDocument();
  });
  it("a preview adds stand-in media without uploading anything", async () => {
    const onChange = vi.fn();
    const u = userEvent.setup();
    const t = { pages: [pageOf([fld("shot", "photo", { config: { max_count: 2, capture: "upload" } })])], checks: [] };
    render(<QueryClientProvider client={new QueryClient()}><FormRenderer kind="inspection" tree={t} values={{}} preview onChange={onChange} /></QueryClientProvider>);
    await u.upload(screen.getByTestId("file-shot"), new File(["x"], "a.jpg", { type: "image/jpeg" }));
    expect(onChange).toHaveBeenCalledWith("shot", [expect.stringMatching(/^preview-/)]);
  });
});
