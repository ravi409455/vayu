import { describe, expect, it } from "vitest";
import type { FormField, FormPage } from "../api/types";
import { wizardSteps, type Tree } from "./wizard";

let n = 0;
const field = (key: string, over: Partial<FormField> = {}): FormField => ({
  id: ++n, section: 1, key, label: key, helper_text: "", type: "short_text", config: {}, required: false, required_if: null, show_if: null,
  visible: true, order: 0, is_system: false, access: {}, locked: false, library: null, ...over,
});
const page = (title: string, fields: FormField[]): FormPage => ({
  id: ++n, title, order: 0, visible: true, gate: false, show_if: null, access: {},
  sections: [{ id: ++n, page: 1, title: "S", order: 0, visible: true, show_if: null, access: {}, fields, locked: false, library: null }],
});
const tree = (...pages: FormPage[]): Tree => ({ id: ++n, pages, checks: [] });
const none = { start: {}, inspection: {}, end: {} };

describe("the expert's steps", () => {
  const start = tree(page("Check-in", [field("selfie")]));
  const end = tree(page("Wrap-up", [field("taking_payment")]));
  const custom = tree(page("Exterior", [field("door")]), page("Interior", [field("seat")]));

  it("go start, then the custom form's pages, then end, then the review", () => {
    const steps = wizardSteps({ start, inspection: custom, end }, none, {});
    expect(steps.map((s) => [s.kind, s.title])).toEqual([["start", "Check-in"], ["inspection", "Exterior"], ["inspection", "Interior"], ["end", "Wrap-up"], ["review", "Review"]]);
  });
  it("leave out a form the inspection is not pinned to", () => {
    expect(wizardSteps({ start: null, inspection: custom, end: null }, none, {}).map((s) => s.title)).toEqual(["Exterior", "Interior", "Review"]);
    expect(wizardSteps({ start, inspection: custom, end: null }, none, {}).map((s) => s.title)).toEqual(["Check-in", "Exterior", "Interior", "Review"]);
  });
  it("skip a pinned form with nothing to show, and a page hidden by a rule", () => {
    const empty = tree();
    const hidden = tree({ ...page("Pay", [field("amount")]), show_if: { "==": [{ var: "booking.vip" }, true] } });
    expect(wizardSteps({ start: empty, inspection: custom, end: hidden }, none, {}).map((s) => s.title)).toEqual(["Exterior", "Interior", "Review"]);
    expect(wizardSteps({ start: empty, inspection: custom, end: hidden }, none, { booking: { vip: true } }).map((s) => s.title))
      .toEqual(["Exterior", "Interior", "Pay", "Review"]);
  });
  it("always ends with the review, even when nothing else shows", () => {
    expect(wizardSteps({ start: null, inspection: tree(), end: null }, none, {}).map((s) => s.kind)).toEqual(["review"]);
  });
});
