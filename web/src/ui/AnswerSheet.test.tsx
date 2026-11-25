import { describe, expect, it } from "vitest";
import type { FormField } from "../api/types";
import { defectOf } from "./AnswerSheet";

describe("defects in the review sheet", () => {
  const f = (type: string): FormField => ({
    id: 1,
    section: 1,
    key: "door",
    label: "Door",
    helper_text: "",
    type,
    required: false,
    required_if: null,
    show_if: null,
    visible: true,
    order: 0,
    is_system: false,
    access: {},
    locked: false,
    library: null,
    config: {
      options: [
        { key: "ok", label: "OK" },
        { key: "scr", label: "Scratched", is_defect: true, severity: "minor" },
        { key: "dent", label: "Dented", is_defect: true, severity: "major" },
      ],
    },
  });
  it("marks a defect answer with its severity, and nothing else", () => {
    expect(defectOf(f("single_choice"), "ok")).toBeNull();
    expect(defectOf(f("single_choice"), "scr")).toBe("Minor");
    expect(defectOf(f("multi_choice"), ["scr", "dent"])).toBe("Major");
    expect(defectOf(f("short_text"), "dent")).toBeNull();
  });
});
