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
