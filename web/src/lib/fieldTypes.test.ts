import { describe, expect, it } from "vitest";
import { READERS } from "../ui/AnswerSheet";
import { INPUTS } from "../ui/FormRenderer";
import { defaultConfig, FIELD_TYPES, iconFor, TYPES, typeSummary } from "./fieldTypes";

describe("one field-type registry (F-049)", () => {
  const ids = Object.keys(TYPES);
  it("every type has an input (or is the shown picture) and a reader", () => {
    expect(ids.filter((t) => t !== "image" && !INPUTS[t])).toEqual([]);
    expect(ids.filter((t) => !READERS[t])).toEqual([]);
    expect(Object.keys(INPUTS).filter((t) => !TYPES[t])).toEqual([]);
    expect(Object.keys(READERS).filter((t) => !TYPES[t])).toEqual([]);
  });
  it("the builder offers every type but the system's, each with an icon", () => {
    expect(FIELD_TYPES.map((t) => t.id)).not.toContain("form_choice");
    expect(FIELD_TYPES).toHaveLength(ids.length - 1);
    expect(new Set(ids.map((t) => iconFor(t))).size).toBeGreaterThan(15);
  });
  it("summaries and starting configs read as before", () => {
    expect(typeSummary({ type: "single_choice", config: { options: [1, 2, 3, 4] } })).toBe("Choose one · 4 choices");
    expect(typeSummary({ type: "form_choice", config: { options: [1] } })).toBe("Pick of a custom form · 1 choice");
    expect(typeSummary({ type: "number", config: { unit: "km" } })).toBe("Number · km");
    expect(typeSummary({ type: "photo", config: { capture: "camera" } })).toBe("Photos · camera only");
    expect(typeSummary({ type: "gps", config: {} })).toBe("GPS location · automatic");
    expect(typeSummary({ type: "date", config: {} })).toBe("Date");
    expect(defaultConfig("file")).toEqual({ max_count: 1 });
    expect(defaultConfig("signature")).toEqual({});
    expect(defaultConfig("nope")).toEqual({});
  });
});
