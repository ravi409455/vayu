import { describe, expect, it } from "vitest";
import type { FormField, FormPage } from "../api/types";
import { applyMedia, lockedFrom, reconcileMedia, unvisited, wizardSteps, type Step, type Tree } from "./wizard";

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

describe("moving around freely", () => {
  const st = (id: string, gate = false): Step => ({ id, title: id, kind: "inspection", page: { ...page(id, []), gate } });
  const steps = [st("checkin", true), st("exterior"), st("interior"), { id: "review", title: "Review", kind: "review" } as Step];
  it("every page is open unless a must-finish page before it still has gaps", () => {
    expect(lockedFrom(steps, () => 0)).toBe(4);                                  // nothing locked
    expect(lockedFrom(steps, (s) => (s.id === "checkin" ? 2 : 0))).toBe(1);      // all after check-in wait
    expect(lockedFrom(steps, (s) => (s.id === "exterior" ? 3 : 0))).toBe(4);     // an ordinary page never locks others
  });
  it("lists the pages not opened yet, never the review", () => {
    expect(unvisited(steps, ["checkin", "interior", "review"]).map((s) => s.id)).toEqual(["exterior"]);
    expect(unvisited(steps, ["checkin", "exterior", "interior"])).toEqual([]);
  });
});


describe("a phone that lost its draft picks the server's files up again", () => {
  const start = tree(page("Check-in", [field("selfie", { type: "photo", config: { max_count: 1 } })]));
  const custom = tree(page("Photos", [field("front", { type: "photo", config: { max_count: 2 } }), field("sign", { type: "signature" })]));
  const trees = { start, inspection: custom, end: null };
  const answers = (over: Record<string, Record<string, unknown>> = {}) => ({ start: {}, inspection: {}, end: {}, ...over });
  const m = (id: string, field_key: string, status = "verified") => ({ id, field_key, kind: "photo", status });
  const never = () => false;

  it("finished files go back into the answers, in the part their field belongs to", () => {
    const { add } = reconcileMedia(trees, answers(), [m("a", "selfie"), m("b", "front"), m("c", "front"), m("d", "sign", "uploaded")], never);
    expect(add.map((x) => [x.part, x.key, x.id])).toEqual([["start", "selfie", "a"], ["inspection", "front", "b"], ["inspection", "front", "c"], ["inspection", "sign", "d"]]);
    expect(applyMedia(answers(), add)).toEqual({ start: { selfie: ["a"] }, inspection: { front: ["b", "c"], sign: "d" }, end: {} });
  });
  it("files that have not finished are left alone: another device or tab may still be sending them (H-16)", () => {
    expect(reconcileMedia(trees, answers(), [m("p", "selfie", "pending"), m("f", "front", "failed")], never)).toEqual({ add: [] });
  });
  it("leaves alone files already in the answers, files this phone is still sending, unknown fields, and anything over the limit", () => {
    const r = reconcileMedia(trees, answers({ start: { selfie: ["a"] }, inspection: { front: ["x"] } }),
      [m("a", "selfie"), m("n", "selfie"), m("sending", "front", "pending"), m("y", "front"), m("z", "front"), m("q", "nothing")], (id) => id === "sending");
    expect(r.add.map((x) => x.id)).toEqual(["y"]);                 // selfie is full; front had room for one more
  });
});
