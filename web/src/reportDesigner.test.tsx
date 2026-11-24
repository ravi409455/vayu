import { describe, expect, it, vi } from "vitest";
import type { FormPage } from "./api/types";
import {
  addPart, blankPage, fillGrid, findPart, locate, movePage, movePart, newPart, pageFromForm, pageOf, partName,
  removePart, shiftPart, updatePage, updatePart, withIds, type Definition, type Part,
} from "./pages/admin/report/model";

const T = (id: string, title = id): Part => ({ id, type: "table", title, source: { kind: "fields", rows: [] } });
const def = (): Definition => ({ schema: 2, pages: [
  { id: "p1", title: "Cover", parts: [T("a"), { id: "cols", type: "columns", columns: [{ parts: [T("in1"), T("in2")] }, { parts: [] }] }, T("b")] },
  { id: "p2", title: "Detail", parts: [T("c")] }] });

describe("report template model", () => {
  it("gives every page and part an id, inside columns too", () => {
    const d = withIds({ schema: 2, pages: [{ title: "P", parts: [{ type: "columns", columns: [{ parts: [{ type: "spacer" }] }, { parts: [] }] }] }] });
    const cols = d.pages[0]!.parts[0] as Extract<Part, { type: "columns" }>;
    expect(d.pages[0]!.id).toBeTruthy();
    expect(cols.id).toBeTruthy();
    expect(cols.columns[0]!.parts[0]!.id).toBeTruthy();
    expect(withIds({ schema: 2, pages: undefined as never }).pages).toEqual([]);
  });
  it("finds, changes and removes parts wherever they sit", () => {
    const d = def();
    expect(findPart(d, "in2")?.id).toBe("in2");
    expect(findPart(d, "nope")).toBeNull();
    expect(locate(d, "c")?.index).toBe(0);
    expect(pageOf(d, "in1")?.id).toBe("p1");
    const renamed = updatePart(d, "in1", { title: "Inner" } as Partial<Part>);
    expect((findPart(renamed, "in1") as { title: string }).title).toBe("Inner");
    expect(updatePart(d, "nope", {})).toBe(d);
    expect(findPart(removePart(d, "in2"), "in2")).toBeNull();
    expect(removePart(d, "nope")).toBe(d);
  });
  it("moves parts among their neighbours only", () => {
    const d = def();
    expect(shiftPart(d, "b", -1).pages[0]!.parts.map((p) => p.id)).toEqual(["a", "b", "cols"]);
    expect(shiftPart(d, "a", -1)).toBe(d);                       // already first
    expect(shiftPart(d, "nope", 1)).toBe(d);
    const inner = shiftPart(d, "in1", 1);
    expect((findPart(inner, "cols") as Extract<Part, { type: "columns" }>).columns[0]!.parts.map((p) => p.id)).toEqual(["in2", "in1"]);
    expect(movePart(d, "b", "a").pages[0]!.parts.map((p) => p.id)).toEqual(["b", "a", "cols"]);
    expect(movePart(d, "a", "in1")).toBe(d);                     // another list: not by dragging
    expect(movePart(d, "a", "nope")).toBe(d);
  });
  it("adds parts after the selected one or at the end, and moves and edits pages", () => {
    const d = def();
    expect(addPart(d, "p1", T("new"), "a").pages[0]!.parts.map((p) => p.id)).toEqual(["a", "new", "cols", "b"]);
    expect(addPart(d, "p2", T("new")).pages[1]!.parts.map((p) => p.id)).toEqual(["c", "new"]);
    expect(addPart(d, "p2", T("new"), "gone").pages[1]!.parts.map((p) => p.id)).toEqual(["c", "new"]);
    expect(movePage(d, "p2", "p1").pages.map((p) => p.id)).toEqual(["p2", "p1"]);
    expect(movePage(d, "p2", "nope")).toBe(d);
    expect(updatePage(d, "p2", { style: "full" }).pages[1]!.style).toBe("full");
  });
  it("names parts the way a person would", () => {
    const sections = { "inspection.front": "Front" };
    expect(partName(T("x", "Key checks"))).toBe("Key checks");
    expect(partName({ type: "text", html: "<h2>Exterior</h2><p>{{ sys.booking_id }}</p>" })).toBe("Exterior sys.booking_id");
    expect(partName({ type: "text", html: "" })).toBe("Text");
    expect(partName({ type: "table", source: { kind: "section", section: "inspection.front" } }, sections)).toBe("Front");
    expect(partName({ type: "photos", source: { kind: "section", section: "inspection.rear" } })).toBe("rear photos");
    expect(partName({ type: "table", source: { kind: "defects" } })).toBe("All problems found");
    expect(partName({ type: "photos", source: { kind: "issues" } })).toBe("All issue photos");
    expect(partName({ type: "verify" })).toBe("Verify code");
  });
  it("starts each kind of part sensibly", () => {
    expect(newPart("table", "inspection.front")).toMatchObject({ type: "table", source: { kind: "section", section: "inspection.front" } });
    expect(newPart("table")).toMatchObject({ source: { kind: "fields", rows: [] } });
    expect(newPart("photos")).toMatchObject({ source: { kind: "issues" } });
    expect(newPart("photos", "inspection.front")).toMatchObject({ source: { kind: "section" } });
    for (const t of ["text", "columns", "verify", "contents", "spacer", "page_break", "html"] as const) expect(newPart(t).type).toBe(t);
    expect(newPart("html")).toMatchObject({ css: expect.stringContaining(".note") });
    expect(partName(newPart("html"))).toBe("Custom HTML");
  });
  it("makes a ready page from a form page: heading, a table each, then issue photos", () => {
    const fp = { id: 1, title: "Exterior <Body>", sections: [
      { id: 1, key: "front", title: "Front", fields: [{ key: "bonnet", type: "single_choice" }, { key: "bonnet_photo", type: "photo" }] },
      { id: 2, key: "pics", title: "Pictures", fields: [{ key: "front_view", type: "photo" }] }] } as unknown as FormPage;
    const page = pageFromForm(fp);
    expect(page.title).toBe("Exterior <Body>");
    expect(page.parts.map((p) => p.type)).toEqual(["text", "table", "photos", "photos"]);
    expect((page.parts[0] as { html: string }).html).toBe("<h2>Exterior &lt;Body&gt;</h2>");
    expect(page.parts[2]).toMatchObject({ which: "issues" });
    expect(page.parts[3]).toMatchObject({ which: "all", source: { section: "inspection.pics" } });
    expect(blankPage("divider").style).toBe("full");
    expect(blankPage("verify").parts.some((p) => p.type === "verify")).toBe(true);
    expect(blankPage("blank", "Notes").title).toBe("Notes");
  });
  it("fills a grid from field names that follow a pattern", () => {
    const grid = { kind: "grid" as const, columns: [{ label: "Tread" }, { label: "Made (week, year)" }],
      rows: [{ label: "Driver front", cells: [{ text: "" }, { field: "inspection.keep_me" }] }, { label: "Stepney", cells: [] }] };
    const out = fillGrid(grid, "tyre", new Set(["tyre_driver_front_tread", "tyre_stepney_tread"]));
    expect(out.rows[0]!.cells).toEqual([{ field: "inspection.tyre_driver_front_tread" }, { field: "inspection.keep_me" }]);
    expect(out.rows[1]!.cells).toEqual([{ field: "inspection.tyre_stepney_tread" }, { text: "" }]);
  });
});

describe("the rich text editor's cleaner", () => {
  it("keeps the allowed tags and classes and drops everything that could run", async () => {
    const { cleanHtml } = await import("./pages/admin/report/RichText");
    const out = cleanHtml('<p class="tone-bad" onclick="x()">Hi <img src=x onerror="alert(1)"><script>bad()</script><a href="javascript:alert(1)">l</a><a href="https://ok.test">k</a><font>f</font></p>');
    expect(out).toBe('<p class="tone-bad">Hi <a>l</a><a href="https://ok.test">k</a>f</p>');
  });
});

describe("the part settings panel", () => {
  const ctx = { readOnly: false, sections: [{ value: "inspection.front", label: "Exterior → Front (2)", fields: [{ key: "bonnet", label: "Bonnet", type: "single_choice" }, { key: "bonnet_photo", label: "Bonnet photo", type: "photo" }] }],
    fields: [{ value: "inspection.bonnet", label: "inspection: Bonnet", type: "single_choice" }, { value: "inspection.bonnet_photo", label: "inspection: Bonnet photo", type: "photo" }] };
  it("switches a table to a form section and leaves a check out", async () => {
    const { render, screen } = await import("@testing-library/react");
    const userEvent = (await import("@testing-library/user-event")).default;
    const { PartSettings } = await import("./pages/admin/report/PartSettings");
    const onChange = vi.fn();
    const u = userEvent.setup();
    const part: Part = { id: "t", type: "table", title: "", source: { kind: "fields", rows: [] } };
    const { rerender } = render(<PartSettings part={part} ctx={ctx} onChange={onChange} onDelete={() => {}} onDuplicate={() => {}} onMove={() => {}} />);
    await u.click(screen.getByRole("radio", { name: /All checks in a form section/ }));
    expect(onChange).toHaveBeenLastCalledWith({ source: { kind: "section", section: "inspection.front" } });
    rerender(<PartSettings part={{ ...part, source: { kind: "section", section: "inspection.front" } }} ctx={ctx} onChange={onChange} onDelete={() => {}} onDuplicate={() => {}} onMove={() => {}} />);
    expect(screen.queryByRole("option", { name: "Bonnet photo" })).toBeNull();          // photos never go in a table
    await u.selectOptions(screen.getByLabelText("Leave out a check"), "bonnet");
    expect(onChange).toHaveBeenLastCalledWith({ source: { kind: "section", section: "inspection.front", exclude: ["bonnet"] } });
    await u.click(screen.getByRole("button", { name: "2" }));
    expect(onChange).toHaveBeenLastCalledWith({ per_row: 2 });
  });
  it("picks photo grid settings and page break settings", async () => {
    const { render, screen } = await import("@testing-library/react");
    const userEvent = (await import("@testing-library/user-event")).default;
    const { PartSettings } = await import("./pages/admin/report/PartSettings");
    const onChange = vi.fn();
    const u = userEvent.setup();
    const part: Part = { id: "p", type: "photos", source: { kind: "issues" } };
    render(<PartSettings part={part} ctx={ctx} onChange={onChange} onDelete={() => {}} onDuplicate={() => {}} onMove={() => {}} />);
    await u.click(screen.getByRole("button", { name: "Fields I pick" }));
    expect(onChange).toHaveBeenLastCalledWith({ source: { kind: "fields", fields: [] } });
    await u.click(screen.getByRole("button", { name: "Check + answer" }));
    expect(onChange).toHaveBeenLastCalledWith({ caption: "check" });
    await u.click(screen.getByRole("checkbox", { name: "Start on a new page" }));
    expect(onChange).toHaveBeenLastCalledWith({ new_page: true });
  });
  it("adds style rules: when a problem, red answer; when critical, bold on a red tint", async () => {
    const { render, screen } = await import("@testing-library/react");
    const userEvent = (await import("@testing-library/user-event")).default;
    const { PartSettings } = await import("./pages/admin/report/PartSettings");
    const onChange = vi.fn();
    const u = userEvent.setup();
    const part: Part = { id: "t", type: "table", source: { kind: "defects" }, style_rules: [{ when: "problem", value: "bad" }] };
    render(<PartSettings part={part} ctx={ctx} onChange={onChange} onDelete={() => {}} onDuplicate={() => {}} onMove={() => {}} />);
    await u.click(screen.getByText("Style rules"));
    await u.selectOptions(screen.getByLabelText("Rule 1 when"), "critical");
    expect(onChange).toHaveBeenLastCalledWith({ style_rules: [{ when: "critical", value: "bad" }] });
    await u.selectOptions(screen.getByLabelText("Answer colour"), "");               // back to unchanged
    expect(onChange).toHaveBeenLastCalledWith({ style_rules: [{ when: "problem" }] });
    await u.selectOptions(screen.getByLabelText("Row tint"), "bad");
    expect(onChange).toHaveBeenLastCalledWith({ style_rules: [{ when: "problem", value: "bad", background: "bad" }] });
    await u.click(screen.getByRole("checkbox", { name: "Bold" }));
    expect(onChange).toHaveBeenLastCalledWith({ style_rules: [{ when: "problem", value: "bad", bold: true }] });
    await u.click(screen.getByRole("button", { name: "+ Add rule" }));
    expect(onChange).toHaveBeenLastCalledWith({ style_rules: [{ when: "problem", value: "bad" }, { when: "problem", value: "bad" }] });
    await u.click(screen.getByRole("button", { name: "Remove rule 1" }));
    expect(onChange).toHaveBeenLastCalledWith({ style_rules: undefined });
  });
  it("edits custom HTML and CSS and puts a value where the cursor is", async () => {
    const { render, screen } = await import("@testing-library/react");
    const userEvent = (await import("@testing-library/user-event")).default;
    const { PartSettings } = await import("./pages/admin/report/PartSettings");
    const onChange = vi.fn();
    const u = userEvent.setup();
    const part: Part = { id: "h", type: "html", html: "<p>AB</p>" };
    render(<PartSettings part={part} ctx={ctx} onChange={onChange} onDelete={() => {}} onDuplicate={() => {}} onMove={() => {}} />);
    const area = screen.getByRole("textbox", { name: "HTML" }) as HTMLTextAreaElement;
    area.setSelectionRange(4, 4);
    await u.selectOptions(screen.getByLabelText("Insert a value"), "inspection.bonnet");
    expect(onChange).toHaveBeenLastCalledWith({ html: "<p>A{{ inspection.bonnet }}B</p>" });
    await u.type(screen.getByRole("textbox", { name: "CSS" }), "p");
    expect(onChange).toHaveBeenLastCalledWith({ css: "p" });
    expect(screen.queryByRole("option", { name: "Bonnet photo" })).toBeNull();
  });
});
