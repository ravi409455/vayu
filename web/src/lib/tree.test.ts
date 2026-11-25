import { describe, expect, it } from "vitest";
import type { FormField, FormPage } from "../api/types";
import { applyDrag, isEmptyBody, reorderBody } from "./tree";

const f = (id: number): FormField => ({
  id,
  section: 0,
  key: `f${id}`,
  label: `F${id}`,
  helper_text: "",
  type: "short_text",
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
});
const sec = (id: number, fields: number[]) => ({
  id,
  page: 0,
  title: `S${id}`,
  order: 0,
  visible: true,
  show_if: null,
  access: {},
  fields: fields.map(f),
  locked: false,
  library: null,
});
const page = (id: number, sections: ReturnType<typeof sec>[]): FormPage => ({
  id,
  title: `P${id}`,
  order: 0,
  visible: true,
  gate: false,
  show_if: null,
  access: {},
  sections,
});
const base = (): FormPage[] => [page(1, [sec(10, [100, 101, 102]), sec(11, [110])]), page(2, [sec(20, [200])])];
const order = (pages: FormPage[]) => pages.map((p) => [p.id, p.sections.map((s) => [s.id, s.fields.map((x) => x.id)])]);

describe("dragging in the form builder", () => {
  it("reorders pages", () => {
    const after = applyDrag(base(), { kind: "page", id: 1 }, { kind: "page", id: 2 });
    expect(after.map((p) => p.id)).toEqual([2, 1]);
    expect(reorderBody(base(), after)).toEqual({ pages: [2, 1] });
  });
  it("reorders fields inside a section, and tells the server only about that section", () => {
    const after = applyDrag(base(), { kind: "field", id: 102 }, { kind: "field", id: 100 });
    expect(after[0]!.sections[0]!.fields.map((x) => x.id)).toEqual([102, 100, 101]);
    expect(reorderBody(base(), after)).toEqual({ fields: { "10": [102, 100, 101] } });
  });
  it("moves a field into another section, before another field or at the end of an empty drop on the section", () => {
    const before = applyDrag(base(), { kind: "field", id: 100 }, { kind: "field", id: 200 });
    expect(order(before)).toEqual([
      [
        1,
        [
          [10, [101, 102]],
          [11, [110]],
        ],
      ],
      [2, [[20, [100, 200]]]],
    ]);
    const end = applyDrag(base(), { kind: "field", id: 100 }, { kind: "section", id: 11 });
    expect(end[0]!.sections[1]!.fields.map((x) => x.id)).toEqual([110, 100]);
    expect(reorderBody(base(), end)).toEqual({ fields: { "10": [101, 102], "11": [110, 100] } });
  });
  it("moves a section to another page, or to the end of a page dropped on directly", () => {
    const a = applyDrag(base(), { kind: "section", id: 11 }, { kind: "section", id: 20 });
    expect(a[1]!.sections.map((s) => s.id)).toEqual([11, 20]);
    expect(reorderBody(base(), a)).toEqual({ sections: { "1": [10], "2": [11, 20] } });
    const b = applyDrag(base(), { kind: "section", id: 10 }, { kind: "page", id: 2 });
    expect(b[1]!.sections.map((s) => s.id)).toEqual([20, 10]);
  });
  it("ignores drops that mean nothing", () => {
    const pages = base();
    expect(applyDrag(pages, { kind: "field", id: 100 }, { kind: "field", id: 100 })).toBe(pages);
    expect(applyDrag(pages, { kind: "page", id: 1 }, { kind: "section", id: 10 })).toBe(pages);
    expect(applyDrag(pages, { kind: "page", id: 99 }, { kind: "page", id: 1 })).toBe(pages);
    expect(applyDrag(pages, { kind: "section", id: 99 }, { kind: "page", id: 1 })).toBe(pages);
    expect(applyDrag(pages, { kind: "section", id: 10 }, { kind: "field", id: 100 })).toBe(pages);
    expect(applyDrag(pages, { kind: "field", id: 99 }, { kind: "section", id: 10 })).toBe(pages);
    expect(applyDrag(pages, { kind: "field", id: 100 }, { kind: "page", id: 2 })).toBe(pages);
    expect(order(pages)).toEqual(order(base())); // never mutates its input
  });
  it("no change means an empty request", () => {
    expect(isEmptyBody(reorderBody(base(), base()))).toBe(true);
  });
});
