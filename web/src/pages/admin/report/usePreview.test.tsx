import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { previewPlan, type Definition } from "./model";
import { pdfIds, placeOf, sheetsOf, type LayoutPage } from "./Preview";
import { usePreview } from "./usePreview";

const api = vi.hoisted(() => vi.fn());
vi.mock("../../../api/client", () => ({ api }));

const page = (title: string, extra: object = {}) => ({ title, parts: [{ type: "text", html: `<p>${title}</p>`, id: title }], ...extra });
const def = (...titles: string[]): Definition => ({ schema: 2, pages: titles.map((t) => page(t)) }) as unknown as Definition;
const sheet = (section: number | null): LayoutPage => ({ width: 794, height: 1123, parts: [], section });

describe("what an edit redraws", () => {
  const a = def("One", "Two", "Three");
  it("nothing yet on screen, or nothing changed", () => {
    expect(previewPlan(null, a)).toBe("all");
    expect(previewPlan(a, def("One", "Two", "Three"))).toBeNull();
  });
  it("one page when that page alone changed", () => {
    expect(previewPlan(a, def("One", "Two!", "Three"))).toBe(1);
  });
  it("everything when two pages, the page list or the report's settings changed", () => {
    expect(previewPlan(a, def("One!", "Two!", "Three"))).toBe("all");
    expect(previewPlan(a, def("One", "Two"))).toBe("all");
    expect(previewPlan(a, def("Two", "One", "Three"))).toBe("all");
    expect(previewPlan(a, { ...a, paper: { size: "Letter" } })).toBe("all");
  });
  it("everything when the page has a contents list (it names the other pages)", () => {
    const toc = {
      ...a,
      pages: [a.pages[0]!, { ...a.pages[1]!, parts: [{ type: "contents", id: "c" }] }, a.pages[2]!],
    } as unknown as Definition;
    expect(previewPlan(toc, { ...toc, pages: [toc.pages[0]!, { ...toc.pages[1]!, title: "New" }, toc.pages[2]!] })).toBe("all");
  });
});

describe("the sheets on screen", () => {
  const pages = [sheet(0), sheet(1), sheet(1), sheet(null), sheet(2)];
  const id = (p: string) => (p === "whole" ? 1 : 2);
  it("are the whole report's when nothing was swapped in", () => {
    expect(sheetsOf("whole", pages, {}, id).map((s) => s.key)).toEqual(["1:1", "1:2", "1:3", "1:4", "1:5"]);
  });
  it("show a redrawn page's sheets in place of its old ones, more or fewer", () => {
    const more = sheetsOf("whole", pages, { 1: { pdf: "new", pages: [sheet(1), sheet(1), sheet(1)] } }, id);
    expect(more.map((s) => s.key)).toEqual(["1:1", "2:1", "2:2", "2:3", "1:4", "1:5"]);
    expect(sheetsOf("whole", pages, { 1: { pdf: "new", pages: [] } }, id).map((s) => s.key)).toEqual(["1:1", "1:4", "1:5"]);
  });
  it("give a page its first page number and the page count", () => {
    expect(placeOf(pages, {}, 1)).toEqual({ first: 2, total: 5 });
    expect(placeOf(pages, { 1: { pdf: "new", pages: [sheet(1)] } }, 2)).toEqual({ first: 4, total: 4 });
    expect(placeOf(pages, {}, 7)).toBeNull();
  });
});

describe("the ids of the PDFs on screen", () => {
  it("are never given twice, so each new drawing of a page is shown (the third edit too)", () => {
    const ids = pdfIds();
    const seen = new Set<number>();
    for (const patch of ["A", "B", "C", "D", "E"]) {
      const id = ids.idOf(patch);
      expect(seen.has(id)).toBe(false);
      seen.add(id);
      ids.idOf("whole");
      ids.keep(new Set(["whole", patch])); // the older drawing of the page is gone
    }
    expect(ids.idOf("whole")).toBe(ids.idOf("whole"));
  });
});

describe("the designer's live preview", () => {
  const whole = { pdf: "WHOLE", pages: [sheet(0), sheet(1), sheet(1), sheet(2)], checks: [] };
  const one = { pdf: "ONE", pages: [sheet(1)], checks: [] };
  beforeEach(() => {
    vi.useFakeTimers();
    api.mockReset();
  });
  afterEach(() => vi.useRealTimers());
  const settle = () => act(async () => void (await vi.advanceTimersByTimeAsync(0)));
  const bodies = () => api.mock.calls.map((c) => c[1].body);

  it("draws the whole report first, then only the edited page, then the whole again once the editing stops", async () => {
    api.mockResolvedValueOnce(whole).mockResolvedValueOnce(one).mockResolvedValueOnce(whole);
    const a = def("One", "Two", "Three");
    const fail = vi.fn();
    const { result, rerender } = renderHook(({ d }) => usePreview(7, "B1", d, fail), { initialProps: { d: a } });
    expect(result.current.drawing).toBe("full");
    await settle();
    expect(api.mock.calls[0]![0]).toBe("pdf-template-versions/7/preview");
    expect(bodies()[0]).toEqual({ booking: "B1", definition: a });
    expect(result.current.whole?.pdf).toBe("WHOLE");

    const b = def("One", "Two!", "Three");
    rerender({ d: b });
    expect(result.current.drawing).toBe("page");
    await settle();
    // page 2 of the template: its sheets are the report's pages 2-3 of 4
    expect(bodies()[1]).toEqual({ booking: "B1", definition: b, only_page: 1, first_page: 2, total_pages: 4 });
    expect(result.current.patches).toEqual({ 1: { pdf: "ONE", pages: one.pages } });
    expect(result.current.stale).toBe(true);

    await act(async () => void (await vi.advanceTimersByTimeAsync(4900)));
    expect(api).toHaveBeenCalledTimes(2); // still editing, perhaps
    await act(async () => void (await vi.advanceTimersByTimeAsync(200)));
    expect(bodies()[2]).toEqual({ booking: "B1", definition: b }); // the whole report, quietly
    await settle();
    expect(result.current.patches).toEqual({});
    expect(result.current.stale).toBe(false);
    expect(fail).not.toHaveBeenCalled();
  });

  it("draws one at a time: edits made meanwhile wait, and only the newest is drawn", async () => {
    let finish: (v: unknown) => void = () => {};
    api.mockResolvedValueOnce(whole).mockImplementationOnce(() => new Promise((r) => (finish = r)));
    const { result, rerender } = renderHook(({ d }) => usePreview(7, "B1", d, vi.fn()), {
      initialProps: { d: def("One", "Two", "Three") },
    });
    await settle();
    rerender({ d: def("One", "Two!", "Three") });
    rerender({ d: def("One", "Two!!", "Three") }); // while page 2 is being drawn
    const last = def("One", "Two!!!", "Three");
    rerender({ d: last });
    expect(api).toHaveBeenCalledTimes(2);
    api.mockResolvedValueOnce(one);
    await act(async () => {
      finish(one);
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(api).toHaveBeenCalledTimes(3); // not 4: "Two!!" was never drawn
    expect(bodies()[2].definition).toBe(last);
    expect(bodies()[2].only_page).toBe(1);
    expect(result.current.drawing).toBeNull();
  });

  it("draws everything for another booking, and when edits touched two pages while a draw ran", async () => {
    api.mockResolvedValue(whole);
    const { rerender } = renderHook(({ d, b }) => usePreview(7, b, d, vi.fn()), { initialProps: { d: def("One", "Two"), b: "B1" } });
    await settle();
    rerender({ d: def("One", "Two"), b: "B2" });
    await settle();
    expect(bodies()[1]).toEqual({ booking: "B2", definition: expect.anything() });
    rerender({ d: def("One!", "Two!"), b: "B2" });
    await settle();
    expect(bodies()[2].only_page).toBeUndefined();
  });

  it("gives the whole PDF with every edit in it: at once when it is on screen, drawn now when pages were swapped in", async () => {
    api
      .mockResolvedValueOnce(whole)
      .mockResolvedValueOnce(one)
      .mockResolvedValueOnce({ ...whole, pdf: "FRESH" });
    const { result, rerender } = renderHook(({ d }) => usePreview(7, "B1", d, vi.fn()), { initialProps: { d: def("One", "Two") } });
    await settle();
    await expect(result.current.wholePdf()).resolves.toBe("WHOLE");
    rerender({ d: def("One", "Two!") });
    await settle();
    let got: string | null = "";
    await act(async () => {
      const p = result.current.wholePdf();
      await vi.advanceTimersByTimeAsync(0);
      got = await p;
    });
    expect(got).toBe("FRESH");
    expect(api).toHaveBeenCalledTimes(3);
  });

  it("says so when a draw fails, does not try the same draw again, and draws everything next time", async () => {
    const fail = vi.fn();
    api.mockResolvedValueOnce(whole).mockRejectedValueOnce(new Error("no")).mockResolvedValueOnce(whole);
    const { result, rerender } = renderHook(({ d }) => usePreview(7, "B1", d, fail), { initialProps: { d: def("One", "Two") } });
    await settle();
    rerender({ d: def("One", "Two!") });
    let got: string | null = "x";
    await act(async () => {
      const p = result.current.wholePdf(); // asked while the failing draw runs
      await vi.advanceTimersByTimeAsync(0);
      got = await p;
    });
    expect(fail).toHaveBeenCalledTimes(1);
    expect(got).toBeNull();
    expect(api).toHaveBeenCalledTimes(2);
    rerender({ d: def("One", "Two!!") });
    await settle();
    expect(bodies()[2].only_page).toBeUndefined(); // after a failure: the whole report
  });

  it("waits for a version and a booking, and stops when the screen is left", async () => {
    api.mockResolvedValue(whole);
    const { rerender, unmount } = renderHook(({ v, b }) => usePreview(v, b, def("One"), vi.fn()), {
      initialProps: { v: undefined as number | undefined, b: "" },
    });
    await settle();
    expect(api).not.toHaveBeenCalled();
    rerender({ v: 7, b: "B1" });
    unmount();
    await settle();
    expect(api).toHaveBeenCalledTimes(1);
  });
});
