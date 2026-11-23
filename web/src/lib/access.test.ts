import { describe, expect, it } from "vitest";
import { getCell, isEmpty, setCell, setRole, STAGES } from "./access";

describe("access matrix editor state", () => {
  it("sets and reads one cell without touching the input", () => {
    const a = {};
    const b = setCell(a, "expert", "submitted", "view");
    expect(getCell(b, "expert", "submitted")).toBe("view");
    expect(getCell(a, "expert", "submitted")).toBe("");
    expect(a).toEqual({});
  });
  it("inherit removes the cell and empty roles disappear", () => {
    let a = setCell({}, "ops", "draft", "edit");
    a = setCell(a, "ops", "draft", "");
    expect(isEmpty(a)).toBe(true);
    expect(setCell({}, "ops", "draft", "")).toEqual({});
  });
  it("a whole role at once", () => {
    const a = setRole({}, "expert", "hidden");
    expect(STAGES.every((s) => getCell(a, "expert", s) === "hidden")).toBe(true);
    expect(isEmpty(setRole(a, "expert", ""))).toBe(true);
  });
});

import { defaultLevel, effectiveLevel, PRESETS } from "./access";

describe("what a person gets at a stage", () => {
  it("follows the standard policy when nothing is set", () => {
    expect(defaultLevel("expert", "in_progress", "inspection", "short_text")).toBe("edit");
    expect(defaultLevel("expert", "submitted", "inspection", "short_text")).toBe("view");
    expect(defaultLevel("expert", "draft", "inspection", "short_text")).toBe("hidden");
    expect(defaultLevel("expert", "in_progress", "inspection", "rating")).toBe("hidden");
    expect(defaultLevel("ops", "completed", "inspection", "derived")).toBe("view");
    expect(defaultLevel("ops", "completed", "inspection", "photo")).toBe("edit");
    expect(defaultLevel("admin", "draft", "booking", "short_text")).toBe("edit");
    expect(defaultLevel("expert", "assigned", "booking", "phone")).toBe("view");
    expect(defaultLevel("expert", "draft", "booking", "phone")).toBe("hidden");
  });
  it("the most specific layer wins and says where it came from", () => {
    const page = { expert: { in_progress: "hidden" as const } };
    const section = { expert: { in_progress: "view" as const } };
    const field = { expert: { in_progress: "edit" as const } };
    expect(effectiveLevel("expert", "in_progress", "inspection", "short_text", { field, section, page })).toEqual({ level: "edit", source: "field" });
    expect(effectiveLevel("expert", "in_progress", "inspection", "short_text", { section, page })).toEqual({ level: "view", source: "section" });
    expect(effectiveLevel("expert", "in_progress", "inspection", "short_text", { page })).toEqual({ level: "hidden", source: "page" });
    expect(effectiveLevel("expert", "in_progress", "inspection", "short_text", {})).toEqual({ level: "edit", source: "default" });
  });
  it("an expert never gets write access to ratings, even if a layer says so", () => {
    const field = { expert: { in_progress: "edit" as const } };
    expect(effectiveLevel("expert", "in_progress", "inspection", "rating", { field })).toEqual({ level: "hidden", source: "default" });
  });
  it("presets produce sensible matrices", () => {
    const by = Object.fromEntries(PRESETS.map((p) => [p.id, p.apply()]));
    expect(by.default).toEqual({});
    expect(effectiveLevel("expert", "in_progress", "inspection", "short_text", { field: by.ops_only! }).level).toBe("hidden");
    expect(effectiveLevel("expert", "in_progress", "inspection", "short_text", { field: by.expert_readonly! }).level).toBe("view");
    expect(effectiveLevel("expert", "submitted", "inspection", "short_text", { field: by.locked_after_submit! }).level).toBe("view");
    expect(effectiveLevel("expert", "in_progress", "inspection", "short_text", { field: by.locked_after_submit! }).level).toBe("edit");
    expect(effectiveLevel("ops", "completed", "inspection", "short_text", { field: by.ops_only! }).level).toBe("edit");
  });
});
