import { describe, expect, it, vi } from "vitest";
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

describe("field types in words", () => {
  it("names the type with the detail that matters", async () => {
    const { typeSummary } = await import("./fieldTypes");
    expect(typeSummary({ type: "single_choice", config: { options: [{}, {}, {}] } })).toBe("Choose one · 3 choices");
    expect(typeSummary({ type: "number", config: { unit: "km" } })).toBe("Number · km");
    expect(typeSummary({ type: "photo", config: { capture: "camera" } })).toBe("Photos · camera only");
    expect(typeSummary({ type: "gps", config: {} })).toBe("GPS location · automatic");
    expect(typeSummary({ type: "short_text", config: {} })).toBe("Short text");
  });
  it("a new choice's key follows its label until someone types a key", async () => {
    const { render, screen } = await import("@testing-library/react");
    const userEvent = (await import("@testing-library/user-event")).default;
    const { FieldEditor } = await import("../pages/admin/builder/FieldEditor");
    const onSave = vi.fn();
    const f = { id: 1, section: 1, key: "door", label: "Door", helper_text: "", type: "single_choice", required: false, required_if: null, show_if: null,
      config: { options: [{ key: "ok", label: "OK" }] }, visible: true, order: 0, is_system: false, access: {}, locked: false, library: null };
    const u = userEvent.setup();
    render(<FieldEditor field={f as never} choices={[]} lists={[]} categories={[]} onSave={onSave} onDelete={() => {}} readOnly={false} />);
    await u.click(screen.getByRole("button", { name: "+ Add choice" }));
    await u.type(screen.getAllByLabelText("Choice label")[1]!, "Badly dented");
    await u.selectOptions(screen.getAllByLabelText("What this choice means")[1]!, "major");
    await u.click(screen.getByRole("button", { name: "Dropdown" }));
    await u.click(screen.getByRole("button", { name: "Save field" }));
    expect(onSave.mock.calls[0]![0].config).toEqual({ options: [{ key: "ok", label: "OK" }, { key: "badly_dented", label: "Badly dented", is_defect: true, severity: "major" }], display: "dropdown" });
  });
});
