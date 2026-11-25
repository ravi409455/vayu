import { describe, expect, it } from "vitest";
import type { FormField, FormPage } from "../api/types";
import { evaluateTree, missingFields, pageGaps, submittable, visiblePages } from "./formSpec";

let n = 0;
const field = (key: string, over: Partial<FormField> = {}): FormField => ({
  id: ++n,
  section: 1,
  key,
  label: key,
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
  ...over,
});
const page = (title: string, fields: FormField[], over: Partial<FormPage> = {}): FormPage => ({
  id: ++n,
  title,
  order: 0,
  visible: true,
  gate: false,
  show_if: null,
  access: {},
  sections: [{ id: ++n, page: 1, title: "S", order: 0, visible: true, show_if: null, access: {}, fields, locked: false, library: null }],
  ...over,
});

// the payment rule: the amount is needed unless "pay later" was chosen
const wrap = page("Wrap-up", [
  field("payment_status", {
    type: "single_choice",
    required: true,
    config: {
      options: [
        { key: "paid", label: "Paid" },
        { key: "pay_later", label: "Pay later" },
      ],
    },
  }),
  field("amount", {
    type: "currency",
    required_if: { "==": [{ var: "end.payment_status" }, "paid"] },
    show_if: { "==": [{ var: "end.payment_status" }, "paid"] },
  }),
]);
const tree = { pages: [wrap], checks: [] };

describe("wizard gap review", () => {
  it("lists every missing required field, with its page", () => {
    const gaps = missingFields("end", tree, {});
    expect(gaps).toEqual([{ key: "payment_status", label: "payment_status", page: 0, pageTitle: "Wrap-up" }]);
  });
  it("payment rule: paid needs an amount, pay later does not", () => {
    expect(missingFields("end", tree, { payment_status: "paid" }).map((g) => g.key)).toEqual(["amount"]);
    expect(missingFields("end", tree, { payment_status: "paid", amount: 500 })).toEqual([]);
    expect(missingFields("end", tree, { payment_status: "pay_later" })).toEqual([]);
  });
  it("a field hidden by a rule is never a gap, and every gap across pages is listed", () => {
    const p1 = page("Body", [
      field("door", { required: true }),
      field("photo", {
        type: "photo",
        required_if: { "==": [{ var: "inspection.door" }, "dent"] },
        show_if: { "==": [{ var: "inspection.door" }, "dent"] },
      }),
    ]);
    const p2 = page("Final", [field("remarks", { required: true })]);
    const t = { pages: [p1, p2], checks: [] };
    expect(missingFields("inspection", t, {}).map((g) => g.key)).toEqual(["door", "remarks"]);
    expect(missingFields("inspection", t, { door: "dent" }).map((g) => [g.key, g.page])).toEqual([
      ["photo", 0],
      ["remarks", 1],
    ]);
    expect(missingFields("inspection", t, { door: "ok", remarks: "fine" })).toEqual([]);
  });
  it("computed fields (Key Checks, ratings) never count as gaps", () => {
    const t = {
      pages: [
        page("P", [
          field("kc", { type: "derived", required: true, config: { rule: { "!!": [1] } } }),
          field("r", { type: "rating", required: true }),
        ]),
      ],
      checks: [],
    };
    expect(missingFields("inspection", t, {})).toEqual([]);
  });
  it("uses the other forms' answers in rules", () => {
    const t = { pages: [page("P", [field("extra", { required_if: { "==": [{ var: "booking.city" }, "delhi"] } })])], checks: [] };
    expect(missingFields("inspection", t, {}, { booking: { city: "delhi" } }).map((g) => g.key)).toEqual(["extra"]);
    expect(missingFields("inspection", t, {}, { booking: { city: "pune" } })).toEqual([]);
  });
});

describe("what gets sent", () => {
  it("drops hidden, empty and computed answers", () => {
    const p = page("P", [
      field("a"),
      field("b", { show_if: { "==": [{ var: "inspection.a" }, "x"] } }),
      field("k", { type: "derived", config: { rule: { "!!": [1] } } }),
    ]);
    const t = { pages: [p], checks: [] };
    expect(submittable("inspection", t, { a: "y", b: "stale", k: true })).toEqual({ a: "y" });
    expect(submittable("inspection", t, { a: "x", b: "kept" })).toEqual({ a: "x", b: "kept" });
    expect(submittable("inspection", t, { a: "  " })).toEqual({});
  });
  it("shows only pages with something visible", () => {
    const hidden = page("Hidden", [field("h", { show_if: { "==": [{ var: "inspection.a" }, "x"] } })]);
    const t = { pages: [page("P", [field("a")]), hidden], checks: [] };
    expect(visiblePages("inspection", t, {}).map((p) => p.title)).toEqual(["P"]);
    expect(visiblePages("inspection", t, { a: "x" }).map((p) => p.title)).toEqual(["P", "Hidden"]);
  });
  it("evaluates Key Checks", () => {
    const t = {
      pages: [page("P", [field("kc", { type: "derived", config: { rule: { "==": [{ var: "inspection.a" }, "x"] } } }), field("a")])],
      checks: [],
    };
    expect(evaluateTree("inspection", t, { a: "x" }).derived.kc).toBe(true);
    expect(evaluateTree("inspection", t, { a: "y" }).derived.kc).toBe(false);
  });
});

describe("start and end pages", () => {
  it("picture fields never count as missing and are never sent", () => {
    const t = { pages: [page("P", [field("qr", { type: "image", required: true, config: { asset: "x" } }), field("a")])], checks: [] };
    expect(missingFields("end", t, {})).toEqual([]);
    expect(submittable("end", t, { qr: "something", a: "y" })).toEqual({ a: "y" });
  });
});

describe("page gate", () => {
  it("lists only what is missing on that page", () => {
    const p1 = page("Check-in", [field("gps", { required: true })]);
    const p2 = page("Body", [field("door", { required: true })]);
    const t = { pages: [p1, p2], checks: [] };
    expect(pageGaps("start", t, p1, {}).map((g) => g.key)).toEqual(["gps"]);
    expect(pageGaps("start", t, p2, {}).map((g) => g.key)).toEqual(["door"]);
    expect(pageGaps("start", t, p1, { gps: { lat: 1, lng: 2 } })).toEqual([]);
  });
});
