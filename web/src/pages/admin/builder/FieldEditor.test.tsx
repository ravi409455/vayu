import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { FormField } from "../../../api/types";
import { FieldEditor } from "./FieldEditor";

afterEach(() => vi.restoreAllMocks());

const FIELD: FormField = {
  id: 1,
  section: 1,
  key: "door",
  label: "Door",
  helper_text: "",
  type: "single_choice",
  config: { options: [{ key: "ok", label: "OK" }] },
  required: false,
  required_if: null,
  show_if: null,
  visible: true,
  order: 0,
  is_system: false,
  access: {},
  locked: false,
  library: null,
};

const noop = () => {};

describe("choice keys stay put once saved", () => {
  it("renaming a saved choice keeps its key; a new one follows its label", async () => {
    const { followsLabel } = await import("./FieldEditor");
    const saved = new Set(["ok"]);
    expect(followsLabel({ key: "ok", label: "OK" }, saved)).toBe(false); // saved: never rewritten
    expect(followsLabel({ key: "", label: "" }, saved)).toBe(true); // new and empty
    expect(followsLabel({ key: "badly", label: "Badly" }, saved)).toBe(true); // new, still following
    expect(followsLabel({ key: "custom", label: "Badly" }, saved)).toBe(false); // new, key typed by hand
  });
  it("editing the label of a saved choice in the editor does not touch its key", async () => {
    const { render, screen } = await import("@testing-library/react");
    const userEvent = (await import("@testing-library/user-event")).default;
    const { FieldEditor } = await import("./FieldEditor");
    const onSave = vi.fn();
    const f = {
      id: 1,
      section: 1,
      key: "door",
      label: "Door",
      helper_text: "",
      type: "single_choice",
      required: false,
      required_if: null,
      show_if: null,
      config: { options: [{ key: "ok", label: "OK" }] },
      visible: true,
      order: 0,
      is_system: false,
      access: {},
      locked: false,
      library: null,
    };
    const u = userEvent.setup();
    render(<FieldEditor field={f as never} choices={[]} lists={[]} categories={[]} onSave={onSave} onDelete={() => {}} readOnly={false} />);
    await u.clear(screen.getByLabelText("Choice label"));
    await u.type(screen.getByLabelText("Choice label"), "Fine");
    await u.click(screen.getByRole("button", { name: "Save field" }));
    expect(onSave.mock.calls[0]![0].config.options).toEqual([{ key: "ok", label: "Fine" }]);
  });
});

describe("report support in the field editor", () => {
  const base = {
    id: 1,
    section: 1,
    helper_text: "",
    required: false,
    required_if: null,
    show_if: null,
    visible: true,
    order: 0,
    is_system: false,
    access: {},
    locked: false,
    library: null,
  };
  it("an answer prints in the colour chosen, else one that follows its meaning", async () => {
    const { toneOf } = await import("./FieldEditor");
    expect(toneOf({ key: "ok", label: "Ok" })).toBe("ok");
    expect(toneOf({ key: "s", label: "Scratch", is_defect: true, severity: "minor" })).toBe("warn");
    expect(toneOf({ key: "d", label: "Damaged", is_defect: true, severity: "major" })).toBe("bad");
    expect(toneOf({ key: "na", label: "Not available", tone: "muted" })).toBe("muted");
  });
  it("picks a report colour for an answer", async () => {
    const { render, screen } = await import("@testing-library/react");
    const userEvent = (await import("@testing-library/user-event")).default;
    const { FieldEditor } = await import("./FieldEditor");
    const onSave = vi.fn();
    const f = {
      ...base,
      key: "plate",
      label: "Number plate",
      type: "single_choice",
      config: { options: [{ key: "na", label: "Not available" }] },
    };
    const u = userEvent.setup();
    render(<FieldEditor field={f as never} choices={[]} lists={[]} categories={[]} onSave={onSave} onDelete={() => {}} readOnly={false} />);
    await u.selectOptions(screen.getByLabelText("Colour of Not available in the report"), "muted");
    await u.click(screen.getByRole("button", { name: "Save field" }));
    expect(onSave.mock.calls[0]![0].config.options).toEqual([{ key: "na", label: "Not available", tone: "muted" }]);
  });
  it("a photo can be an issue photo and show one of the checks of its section", async () => {
    const { render, screen } = await import("@testing-library/react");
    const userEvent = (await import("@testing-library/user-event")).default;
    const { FieldEditor } = await import("./FieldEditor");
    const onSave = vi.fn();
    const f = { ...base, key: "door_photo", label: "Door photo", type: "photo", config: { max_count: 3 } };
    const siblings = [
      { key: "door", label: "Door", type: "single_choice" },
      { key: "other_photo", label: "Other photo", type: "photo" },
    ];
    const u = userEvent.setup();
    render(
      <FieldEditor
        field={f as never}
        choices={[]}
        lists={[]}
        categories={[]}
        onSave={onSave}
        onDelete={() => {}}
        readOnly={false}
        siblings={siblings}
      />,
    );
    expect(screen.queryByRole("option", { name: "Other photo" })).toBeNull(); // a photo cannot show a photo
    await u.click(screen.getByRole("checkbox", { name: /Issue photo/ }));
    await u.selectOptions(screen.getByLabelText("Photo of"), "door");
    await u.click(screen.getByRole("button", { name: "Save field" }));
    expect(onSave.mock.calls[0]![0].config).toEqual({ max_count: 3, issue_photo: true, photo_of: "door" });
  });
  it("a new photo shows the nearest check above it", async () => {
    const { photoOfDefault } = await import("../../../lib/fieldTypes");
    expect(
      photoOfDefault([
        { key: "door", type: "single_choice" },
        { key: "door_remark", type: "short_text" },
        { key: "x", type: "photo" },
      ]),
    ).toBe("door");
    expect(photoOfDefault([{ key: "x", type: "photo" }])).toBeUndefined();
  });
});

describe("field validations on the Logic tab", () => {
  it("are edited there and saved with the field; a message is required", async () => {
    const { render, screen } = await import("@testing-library/react");
    const userEvent = (await import("@testing-library/user-event")).default;
    const { FieldEditor } = await import("./FieldEditor");
    const onSave = vi.fn();
    const f = {
      id: 1,
      section: 1,
      key: "odo",
      label: "Odometer",
      helper_text: "",
      type: "number",
      required: false,
      required_if: null,
      show_if: null,
      config: {},
      visible: true,
      order: 0,
      is_system: true,
      access: {},
      locked: false,
      library: null,
    };
    const checks = [{ id: 7, rule: { ">": [{ var: "inspection.odo" }, 0] }, message: "Too low", fields: ["odo"], order: 0 }];
    const u = userEvent.setup();
    render(
      <FieldEditor
        field={f as never}
        choices={[]}
        lists={[]}
        categories={[]}
        onSave={onSave}
        onDelete={() => {}}
        readOnly={false}
        kind="custom"
        checks={checks}
      />,
    );
    await u.click(screen.getByRole("tab", { name: "Logic" }));
    const msg = screen.getByLabelText("Message when not valid");
    await u.clear(msg);
    expect(screen.getByRole("button", { name: "Save field" })).toBeDisabled(); // no message: no save
    await u.type(msg, "Must be more than 0");
    await u.click(screen.getByRole("button", { name: "+ Add validation" }));
    await u.type(screen.getAllByLabelText("Message when not valid")[1]!, "Needed");
    await u.click(screen.getByRole("button", { name: "Save field" }));
    expect(onSave.mock.calls[0]![1]).toEqual([
      { id: 7, rule: checks[0]!.rule, message: "Must be more than 0", fields: ["odo"] },
      { rule: { "!!": [{ var: "inspection.odo" }] }, message: "Needed", fields: ["odo"] },
    ]);
  });

  it("go away when their last condition is deleted", async () => {
    const { render, screen } = await import("@testing-library/react");
    const userEvent = (await import("@testing-library/user-event")).default;
    const { FieldEditor } = await import("./FieldEditor");
    const onSave = vi.fn();
    const f = {
      id: 1,
      section: 1,
      key: "odo",
      label: "Odometer",
      helper_text: "",
      type: "number",
      required: false,
      required_if: null,
      show_if: null,
      config: {},
      visible: true,
      order: 0,
      is_system: false,
      access: {},
      locked: false,
      library: null,
    };
    const checks = [{ id: 7, rule: { ">": [{ var: "inspection.odo" }, 0] }, message: "Too low", fields: ["odo"], order: 0 }];
    const u = userEvent.setup();
    render(
      <FieldEditor
        field={f as never}
        choices={[{ value: "inspection.odo", label: "Odometer" }]}
        lists={[]}
        categories={[]}
        onSave={onSave}
        onDelete={() => {}}
        readOnly={false}
        kind="custom"
        checks={checks}
      />,
    );
    await u.click(screen.getByRole("tab", { name: "Logic" }));
    const validation = screen.getByRole("region", { name: "Validation" });
    const { within } = await import("@testing-library/react");
    await u.click(within(validation).getByRole("button", { name: "Remove condition" }));
    expect(screen.queryByLabelText("Message when not valid")).toBeNull();
    await u.click(screen.getByRole("button", { name: "Save field" }));
    expect(onSave.mock.calls[0]![1]).toEqual([]);
  });
});

describe("field editor", () => {
  it("shows the key and type as fixed text after the first save", () => {
    render(<FieldEditor field={FIELD} choices={[]} lists={[]} categories={[]} onSave={noop} onDelete={noop} readOnly={false} />);
    expect(screen.getByText("door")).toBeInTheDocument();
    expect(screen.queryByLabelText("Key")).toBeNull();
    expect(screen.queryByLabelText("Type")).toBeNull();
  });
  it("only lets you save once something changed, and sends the new label", async () => {
    const onSave = vi.fn();
    const u = userEvent.setup();
    render(<FieldEditor field={FIELD} choices={[]} lists={[]} categories={[]} onSave={onSave} onDelete={noop} readOnly={false} />);
    expect(screen.getByRole("button", { name: "Save field" })).toBeDisabled();
    await u.type(screen.getByLabelText("Label"), "!");
    await u.click(screen.getByRole("button", { name: "Save field" }));
    expect(onSave).toHaveBeenCalledWith(expect.objectContaining({ label: "Door!" }));
  });
  it("a published (read-only) version cannot be edited", () => {
    render(<FieldEditor field={FIELD} choices={[]} lists={[]} categories={[]} onSave={noop} onDelete={noop} readOnly />);
    expect(screen.queryByRole("button", { name: "Save field" })).toBeNull();
    expect(screen.getByLabelText("Label")).toBeDisabled();
  });
  it("a photo field chooses which camera the Android app opens (Back by default)", async () => {
    const onSave = vi.fn();
    const u = userEvent.setup();
    const photo: FormField = { ...FIELD, key: "selfie2", type: "photo", config: { max_count: 1 } };
    render(<FieldEditor field={photo} choices={[]} lists={[]} categories={[]} onSave={onSave} onDelete={noop} readOnly={false} />);
    expect(screen.getByLabelText("Camera")).toHaveValue("back");
    await u.selectOptions(screen.getByLabelText("Camera"), "front");
    await u.click(screen.getByRole("button", { name: "Save field" }));
    expect(onSave).toHaveBeenCalledWith(expect.objectContaining({ config: expect.objectContaining({ camera: "front" }) }));
  });
  it("a photo, video or document can be hidden from the customer; other fields can't", async () => {
    const onSave = vi.fn();
    const u = userEvent.setup();
    const photo: FormField = { ...FIELD, key: "pay", type: "photo", config: { max_count: 1 } };
    const { unmount } = render(
      <FieldEditor field={photo} choices={[]} lists={[]} categories={[]} onSave={onSave} onDelete={noop} readOnly={false} />,
    );
    expect(screen.getByLabelText("Hide from customer")).not.toBeChecked();
    await u.click(screen.getByLabelText("Hide from customer"));
    await u.click(screen.getByRole("button", { name: "Save field" }));
    expect(onSave).toHaveBeenCalledWith(expect.objectContaining({ config: expect.objectContaining({ hide_from_customer: true }) }));
    unmount();
    render(<FieldEditor field={FIELD} choices={[]} lists={[]} categories={[]} onSave={noop} onDelete={noop} readOnly={false} />);
    expect(screen.queryByLabelText("Hide from customer")).toBeNull();
  });
  it("an upload-only photo field has no camera choice", () => {
    const photo: FormField = { ...FIELD, key: "doc2", type: "photo", config: { capture: "upload" } };
    render(<FieldEditor field={photo} choices={[]} lists={[]} categories={[]} onSave={noop} onDelete={noop} readOnly={false} />);
    expect(screen.queryByLabelText("Camera")).toBeNull();
  });
  it("system fields cannot be deleted or made optional", () => {
    render(
      <FieldEditor
        field={{ ...FIELD, is_system: true }}
        choices={[]}
        lists={[]}
        categories={[]}
        onSave={noop}
        onDelete={noop}
        readOnly={false}
      />,
    );
    expect(screen.queryByRole("button", { name: "Delete field" })).toBeNull();
    expect(screen.queryByText("Always required")).toBeNull();
  });
});
