import { describe, expect, it } from "vitest";
import { addFieldTo, asField, isSection, moveField, newFieldDef, previewTree, removeFieldFrom, replaceField, ruleChoices, sameDef, SYSTEM_RULE_FIELDS, withDraft, type SectionDef } from "./libraryDef";

const tyres: SectionDef = { title: "Tyres", fields: [newFieldDef("fl", "Front left", "number"), newFieldDef("fr", "Front right", "number")] };

describe("library definitions in the editor", () => {
  it("tells a section from a field", () => {
    expect(isSection(tyres)).toBe(true);
    expect(isSection(newFieldDef("a", "A", "short_text"))).toBe(false);
  });
  it("shows a field definition as the field the editor expects, with sensible blanks", () => {
    const f = asField({ key: "k", label: "K", type: "yes_no" });
    expect(f).toMatchObject({ key: "k", required: false, visible: true, helper_text: "", config: {}, access: {}, show_if: null, locked: false, library: null });
  });
  it("writes only what the editor changed, and never the key or type", () => {
    const d = newFieldDef("k", "Old", "short_text");
    const out = withDraft(d, { label: "New", required: true, key: "other", type: "number" } as never);
    expect(out).toMatchObject({ key: "k", type: "short_text", label: "New", required: true });
    expect(withDraft(d, {})).toEqual(d);
  });
  it("adds, removes, replaces and reorders a section's fields", () => {
    const more = addFieldTo(tyres, newFieldDef("rl", "Rear left", "number"));
    expect(more.fields.map((f) => f.key)).toEqual(["fl", "fr", "rl"]);
    expect(moveField(more, "rl", -1).fields.map((f) => f.key)).toEqual(["fl", "rl", "fr"]);
    expect(moveField(more, "fl", -1)).toBe(more);                         // already first
    expect(moveField(more, "rl", 1)).toBe(more);                          // already last
    expect(moveField(more, "ghost", 1)).toBe(more);
    expect(removeFieldFrom(more, "fr").fields.map((f) => f.key)).toEqual(["fl", "rl"]);
    expect(replaceField(more, { ...more.fields[0]!, label: "FL" }).fields[0]!.label).toBe("FL");
  });
  it("builds a one-section preview tree for a field and for a section", () => {
    const field = previewTree("field", newFieldDef("k", "K", "yes_no"));
    expect(field.pages[0]!.sections[0]!.fields.map((f) => f.key)).toEqual(["k"]);
    const sec = previewTree("section", { ...tyres, visible: false, show_if: { "!!": [1] } });
    expect(sec.pages[0]!.sections[0]).toMatchObject({ title: "Tyres", visible: false, show_if: { "!!": [1] } });
    expect(sec.pages[0]!.sections[0]!.fields).toHaveLength(2);
  });
  it("offers rules only the item's own fields and the system fields", () => {
    const own = ruleChoices("section", tyres, SYSTEM_RULE_FIELDS).map((c) => c.value);
    expect(own.slice(0, 2)).toEqual(["inspection.fl", "inspection.fr"]);
    expect(own).toContain("inspection.chassis_no");
    expect(own).toContain("booking.city");
    expect(own).not.toContain("inspection.door");
    expect(ruleChoices("field", newFieldDef("solo", "Solo", "short_text"), []).map((c) => c.value)).toEqual(["inspection.solo"]);
  });
  it("compares definitions by content", () => {
    expect(sameDef(tyres, JSON.parse(JSON.stringify(tyres)))).toBe(true);
    expect(sameDef(tyres, addFieldTo(tyres, newFieldDef("x", "X", "yes_no")))).toBe(false);
  });
});
