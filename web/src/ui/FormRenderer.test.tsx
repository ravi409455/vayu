import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { FormField, FormPage } from "../api/types";
import { FormRenderer, nowAs } from "./FormRenderer";

afterEach(() => vi.restoreAllMocks());

let n = 100;

const fld = (key: string, type: string, over: Partial<FormField> = {}): FormField => ({
  id: ++n,
  section: 1,
  key,
  label: key,
  helper_text: "",
  type,
  config: {},
  required: false,
  required_if: null,
  show_if: null,
  visible: true,
  order: 0,
  is_system: false,
  access: {},
  locked: false,
  library: null,
  ...over,
});

const pageOf = (fields: FormField[]): FormPage => ({
  id: 1,
  title: "P",
  order: 0,
  visible: true,
  gate: false,
  show_if: null,
  access: {},
  sections: [{ id: 1, page: 1, title: "S", order: 0, visible: true, show_if: null, access: {}, fields, locked: false, library: null }],
});

describe("form renderer", () => {
  const tree = {
    pages: [
      pageOf([
        fld("door", "short_text"),
        fld("kc", "derived", { config: { rule: { "!!": [1] }, true_label: "Found" } }),
        fld("engine", "rating"),
        fld("view_only", "short_text", { level: "view" }),
      ]),
    ],
    checks: [],
  };
  function show(role: string) {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <FormRenderer kind="inspection" tree={tree} values={{ view_only: "x" }} role={role} onChange={() => {}} />
      </QueryClientProvider>,
    );
  }
  it("colours a picked answer by meaning: green when fine, red for a defect, neutral for yes / no", () => {
    const opts = [
      { key: "ok", label: "OK" },
      { key: "dent", label: "Dented", is_defect: true },
    ];
    const t = {
      pages: [
        pageOf([
          fld("door", "single_choice", { config: { options: opts } }),
          fld("glass", "single_choice", { config: { options: opts } }),
          fld("keys", "yes_no"),
        ]),
      ],
      checks: [],
    };
    render(
      <QueryClientProvider client={new QueryClient()}>
        <FormRenderer kind="inspection" tree={t} values={{ door: "ok", glass: "dent", keys: true }} onChange={() => {}} />
      </QueryClientProvider>,
    );
    const picked = screen.getAllByRole("radio", { checked: true });
    expect(picked.map((b) => [b.textContent, b.className])).toEqual([
      ["OK", "choice"],
      ["Dented", "choice defect"],
      ["Yes", "choice plain"],
    ]);
    expect(picked.some((b) => b.className.includes("primary"))).toBe(false);
  });
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
    const t2 = {
      pages: [
        pageOf([fld("a", "short_text", { required: true }), fld("b", "short_text", { show_if: { "==": [{ var: "inspection.a" }, "x"] } })]),
      ],
      checks: [],
    };
    const { rerender } = render(
      <QueryClientProvider client={new QueryClient()}>
        <FormRenderer kind="inspection" tree={t2} values={{}} onChange={() => {}} />
      </QueryClientProvider>,
    );
    expect(screen.getByText("a *")).toBeInTheDocument();
    expect(screen.queryByLabelText("b")).toBeNull();
    rerender(
      <QueryClientProvider client={new QueryClient()}>
        <FormRenderer kind="inspection" tree={t2} values={{ a: "x" }} onChange={() => {}} />
      </QueryClientProvider>,
    );
    expect(screen.getByLabelText("b")).toBeInTheDocument();
  });
  it("typing reports the change, choice buttons toggle, and GPS refusal says 'GPS unavailable'", async () => {
    const onChange = vi.fn();
    const u = userEvent.setup();
    const t3 = {
      pages: [
        pageOf([
          fld("note", "short_text"),
          fld("fuel", "single_choice", {
            config: {
              options: [
                { key: "p", label: "Petrol" },
                { key: "d", label: "Diesel" },
              ],
            },
          }),
          fld("loc", "gps"),
        ]),
      ],
      checks: [],
    };
    Object.defineProperty(globalThis.navigator, "geolocation", {
      configurable: true,
      value: { getCurrentPosition: (_ok: unknown, bad: () => void) => bad() },
    });
    render(
      <QueryClientProvider client={new QueryClient()}>
        <FormRenderer kind="inspection" tree={t3} values={{}} onChange={onChange} />
      </QueryClientProvider>,
    );
    await u.type(screen.getByLabelText("note"), "a");
    expect(onChange).toHaveBeenCalledWith("note", "a");
    await u.click(screen.getByRole("radio", { name: "Diesel" }));
    expect(onChange).toHaveBeenCalledWith("fuel", "d");
    expect(await screen.findByText("GPS unavailable")).toBeInTheDocument(); // asked by itself, no button needed
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });
  it("takes the location by itself and reports it once", async () => {
    const onChange = vi.fn();
    Object.defineProperty(globalThis.navigator, "geolocation", {
      configurable: true,
      value: {
        getCurrentPosition: (ok: (p: unknown) => void) => ok({ coords: { latitude: 28.61394, longitude: 77.20902, accuracy: 12.4 } }),
      },
    });
    render(
      <QueryClientProvider client={new QueryClient()}>
        <FormRenderer kind="inspection" tree={{ pages: [pageOf([fld("loc", "gps")])], checks: [] }} values={{}} onChange={onChange} />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(onChange).toHaveBeenCalledWith("loc", { lat: 28.61394, lng: 77.20902, accuracy: 12 }));
    expect(onChange).toHaveBeenCalledTimes(1);
  });
  it("does not ask for the location when a value exists, in read-only mode, or in the builder's preview", () => {
    const ask = vi.fn();
    Object.defineProperty(globalThis.navigator, "geolocation", { configurable: true, value: { getCurrentPosition: ask } });
    const t = { pages: [pageOf([fld("loc", "gps")])], checks: [] };
    const wrap = (props: { values: Record<string, unknown>; readOnly?: boolean; preview?: boolean }) => (
      <QueryClientProvider client={new QueryClient()}>
        <FormRenderer kind="inspection" tree={t} onChange={() => {}} {...props} />
      </QueryClientProvider>
    );
    render(wrap({ values: { loc: { lat: 1, lng: 2 } } }));
    render(wrap({ values: {}, readOnly: true }));
    render(wrap({ values: {}, preview: true }));
    expect(ask).not.toHaveBeenCalled();
    expect(screen.getByText(/Taken automatically/)).toBeInTheDocument();
  });
  it.each([
    ["both", true, true],
    ["camera", true, false],
    ["upload", false, true],
  ])("capture mode %s shows camera=%s attach=%s", (mode, camera, attach) => {
    const t = { pages: [pageOf([fld("shot", "photo", { config: { max_count: 2, capture: mode } })])], checks: [] };
    render(
      <QueryClientProvider client={new QueryClient()}>
        <FormRenderer kind="inspection" tree={t} values={{}} bookingId="b1" onChange={() => {}} />
      </QueryClientProvider>,
    );
    expect(!!screen.queryByRole("button", { name: /Open camera/ })).toBe(camera);
    expect(!!screen.queryByRole("button", { name: /Attach a photo/ })).toBe(attach);
  });
  it("videos offer Record instead of Camera, and files only ever offer Attach", () => {
    const t = {
      pages: [pageOf([fld("clip", "video", { config: { max_count: 1 } }), fld("doc", "file", { config: { max_count: 1 } })])],
      checks: [],
    };
    render(
      <QueryClientProvider client={new QueryClient()}>
        <FormRenderer kind="inspection" tree={t} values={{}} bookingId="b1" onChange={() => {}} />
      </QueryClientProvider>,
    );
    expect(screen.getByRole("button", { name: "Open camera: video" })).toHaveTextContent("Record");
    expect(screen.getByRole("button", { name: "Attach a video" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Open camera: file" })).toBeNull();
    expect(screen.getByRole("button", { name: "Attach a file" })).toBeInTheDocument();
  });
  it("a preview adds stand-in media without uploading anything", async () => {
    const onChange = vi.fn();
    const u = userEvent.setup();
    const t = { pages: [pageOf([fld("shot", "photo", { config: { max_count: 2, capture: "upload" } })])], checks: [] };
    render(
      <QueryClientProvider client={new QueryClient()}>
        <FormRenderer kind="inspection" tree={t} values={{}} preview onChange={onChange} />
      </QueryClientProvider>,
    );
    await u.upload(screen.getByTestId("file-shot"), new File(["x"], "a.jpg", { type: "image/jpeg" }));
    expect(onChange).toHaveBeenCalledWith("shot", [expect.stringMatching(/^preview-/)]);
  });
});

describe("picture, automatic and manual fields", () => {
  const render1 = (fields: FormField[], props: Record<string, unknown> = {}) =>
    render(
      <QueryClientProvider client={new QueryClient()}>
        <FormRenderer
          kind="end"
          tree={{ pages: [pageOf(fields)], checks: [] }}
          values={{}}
          onChange={(props.onChange as () => void) ?? (() => {})}
          {...props}
        />
      </QueryClientProvider>,
    );

  it("a picture field shows its image to the expert, read-only, and nowhere else", () => {
    const qr = fld("qr", "image", { label: "Scan to pay", config: { asset: "abc-123" } });
    const { unmount } = render1([qr], { role: "expert" });
    expect(screen.getByAltText("Scan to pay")).toHaveAttribute("src", "/api/v1/form-assets/abc-123");
    expect(screen.queryByRole("textbox")).toBeNull(); // nothing to fill in
    unmount();
    render1([qr], { role: "ops" });
    expect(screen.queryByAltText("Scan to pay")).toBeNull();
  });
  it("the builder's preview shows the picture too", () => {
    render1([fld("qr", "image", { label: "QR", config: { asset: "z" } })], { preview: true, role: "ops" });
    expect(screen.getByAltText("QR")).toBeInTheDocument();
  });
  it("an automatic date and time is stamped once and cannot be typed", async () => {
    const onChange = vi.fn();
    render1([fld("arrived", "datetime", { label: "Arrived", config: { auto: true } })], { onChange });
    await waitFor(() =>
      expect(onChange).toHaveBeenCalledWith("arrived", expect.stringMatching(/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d[+-]\d\d:\d\d$/)),
    );
    expect(onChange).toHaveBeenCalledTimes(1);
    expect(screen.queryByLabelText("Arrived")).toBeNull(); // no input to edit
    expect(screen.getByText("(automatic)")).toBeInTheDocument();
  });
  it("automatic date and time do not stamp in preview, read-only mode or when a value exists", () => {
    const onChange = vi.fn();
    const t = [fld("d", "date", { config: { auto: true } })];
    render1(t, { onChange, preview: true });
    render1(t, { onChange, readOnly: true });
    render(
      <QueryClientProvider client={new QueryClient()}>
        <FormRenderer kind="end" tree={{ pages: [pageOf(t)], checks: [] }} values={{ d: "2026-01-02" }} onChange={onChange} />
      </QueryClientProvider>,
    );
    expect(onChange).not.toHaveBeenCalled();
    expect(screen.getByText("2026-01-02")).toBeInTheDocument();
  });
  it("without the automatic setting a date is an ordinary input", () => {
    render1([fld("d", "date", { label: "Day" })]);
    expect(screen.getByLabelText("Day")).toHaveAttribute("type", "date");
  });
  it("a location set to manual waits for the button instead of asking by itself", async () => {
    const ask = vi.fn((ok: (p: unknown) => void) => ok({ coords: { latitude: 1, longitude: 2, accuracy: 3 } }));
    Object.defineProperty(globalThis.navigator, "geolocation", { configurable: true, value: { getCurrentPosition: ask } });
    const onChange = vi.fn();
    const u = userEvent.setup();
    render1([fld("loc", "gps", { config: { auto: false } })], { onChange });
    expect(ask).not.toHaveBeenCalled();
    await u.click(screen.getByRole("button", { name: "Capture my location" }));
    expect(onChange).toHaveBeenCalledWith("loc", { lat: 1, lng: 2, accuracy: 3 });
  });
  it("nowAs gives the shapes the server stores", () => {
    const d = new Date(2026, 10, 23, 9, 5, 7);
    expect(nowAs("date", d)).toBe("2026-11-23");
    expect(nowAs("time", d)).toBe("09:05");
    expect(nowAs("datetime", d)).toMatch(/^2026-11-23T09:05:07[+-]\d\d:\d\d$/);
  });
});
