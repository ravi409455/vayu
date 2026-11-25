import { describe, expect, it, vi } from "vitest";
import type { FormPage } from "./api/types";
import {
  addPart,
  blankPage,
  fillGrid,
  findPart,
  locate,
  movePage,
  movePart,
  newPart,
  pageFromForm,
  pageOf,
  partName,
  removePart,
  replaceRef,
  sharedPart,
  shiftPart,
  themeOf,
  unlinkShared,
  updatePage,
  updatePart,
  withIds,
  withoutTheme,
  type Definition,
  type Part,
} from "./pages/admin/report/model";
import { keyOf, snippetContent } from "./pages/admin/report/sharing";

const T = (id: string, title = id): Part => ({ id, type: "table", title, source: { kind: "fields", rows: [] } });
const def = (): Definition => ({
  schema: 2,
  pages: [
    {
      id: "p1",
      title: "Cover",
      parts: [T("a"), { id: "cols", type: "columns", columns: [{ parts: [T("in1"), T("in2")] }, { parts: [] }] }, T("b")],
    },
    { id: "p2", title: "Detail", parts: [T("c")] },
  ],
});

describe("report template model", () => {
  it("gives every page and part an id, inside columns too", () => {
    const d = withIds({
      schema: 2,
      pages: [{ title: "P", parts: [{ type: "columns", columns: [{ parts: [{ type: "spacer" }] }, { parts: [] }] }] }],
    });
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
    expect(shiftPart(d, "a", -1)).toBe(d); // already first
    expect(shiftPart(d, "nope", 1)).toBe(d);
    const inner = shiftPart(d, "in1", 1);
    expect((findPart(inner, "cols") as Extract<Part, { type: "columns" }>).columns[0]!.parts.map((p) => p.id)).toEqual(["in2", "in1"]);
    expect(movePart(d, "b", "a").pages[0]!.parts.map((p) => p.id)).toEqual(["b", "a", "cols"]);
    expect(movePart(d, "a", "in1")).toBe(d); // another list: not by dragging
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
    const fp = {
      id: 1,
      title: "Exterior <Body>",
      sections: [
        {
          id: 1,
          key: "front",
          title: "Front",
          fields: [
            { key: "bonnet", type: "single_choice" },
            { key: "bonnet_photo", type: "photo" },
          ],
        },
        { id: 2, key: "pics", title: "Pictures", fields: [{ key: "front_view", type: "photo" }] },
      ],
    } as unknown as FormPage;
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
    const grid = {
      kind: "grid" as const,
      columns: [{ label: "Tread" }, { label: "Made (week, year)" }],
      rows: [
        { label: "Driver front", cells: [{ text: "" }, { field: "inspection.keep_me" }] },
        { label: "Stepney", cells: [] },
      ],
    };
    const out = fillGrid(grid, "tyre", new Set(["tyre_driver_front_tread", "tyre_stepney_tread"]));
    expect(out.rows[0]!.cells).toEqual([{ field: "inspection.tyre_driver_front_tread" }, { field: "inspection.keep_me" }]);
    expect(out.rows[1]!.cells).toEqual([{ field: "inspection.tyre_stepney_tread" }, { text: "" }]);
  });
});

describe("the rich text editor's cleaner", () => {
  it("keeps the allowed tags and classes and drops everything that could run", async () => {
    const { cleanHtml } = await import("./pages/admin/report/RichText");
    const out = cleanHtml(
      '<p class="tone-bad" onclick="x()">Hi <img src=x onerror="alert(1)"><script>bad()</script><a href="javascript:alert(1)">l</a><a href="https://ok.test">k</a><font>f</font></p>',
    );
    expect(out).toBe('<p class="tone-bad">Hi <a>l</a><a href="https://ok.test">k</a>f</p>');
  });
});

describe("the part settings panel", () => {
  const ctx = {
    readOnly: false,
    sections: [
      {
        value: "inspection.front",
        label: "Exterior → Front (2)",
        fields: [
          { key: "bonnet", label: "Bonnet", type: "single_choice" },
          { key: "bonnet_photo", label: "Bonnet photo", type: "photo" },
        ],
      },
    ],
    fields: [
      { value: "inspection.bonnet", label: "inspection: Bonnet", type: "single_choice" },
      { value: "inspection.bonnet_photo", label: "inspection: Bonnet photo", type: "photo" },
    ],
  };
  it("switches a table to a form section and leaves a check out", async () => {
    const { render, screen } = await import("@testing-library/react");
    const userEvent = (await import("@testing-library/user-event")).default;
    const { PartSettings } = await import("./pages/admin/report/PartSettings");
    const onChange = vi.fn();
    const u = userEvent.setup();
    const part: Part = { id: "t", type: "table", title: "", source: { kind: "fields", rows: [] } };
    const { rerender } = render(
      <PartSettings part={part} ctx={ctx} onChange={onChange} onDelete={() => {}} onDuplicate={() => {}} onMove={() => {}} />,
    );
    await u.click(screen.getByRole("radio", { name: /All checks in a form section/ }));
    expect(onChange).toHaveBeenLastCalledWith({ source: { kind: "section", section: "inspection.front" } });
    rerender(
      <PartSettings
        part={{ ...part, source: { kind: "section", section: "inspection.front" } }}
        ctx={ctx}
        onChange={onChange}
        onDelete={() => {}}
        onDuplicate={() => {}}
        onMove={() => {}}
      />,
    );
    expect(screen.queryByRole("option", { name: "Bonnet photo" })).toBeNull(); // photos never go in a table
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
    await u.selectOptions(screen.getByLabelText("Answer colour"), ""); // back to unchanged
    expect(onChange).toHaveBeenLastCalledWith({ style_rules: [{ when: "problem" }] });
    await u.selectOptions(screen.getByLabelText("Row tint"), "bad");
    expect(onChange).toHaveBeenLastCalledWith({ style_rules: [{ when: "problem", value: "bad", background: "bad" }] });
    await u.click(screen.getByRole("checkbox", { name: "Bold" }));
    expect(onChange).toHaveBeenLastCalledWith({ style_rules: [{ when: "problem", value: "bad", bold: true }] });
    await u.click(screen.getByRole("button", { name: "+ Add rule" }));
    expect(onChange).toHaveBeenLastCalledWith({
      style_rules: [
        { when: "problem", value: "bad" },
        { when: "problem", value: "bad" },
      ],
    });
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
  it("shows a shared part's version and offers the newest and a copy to edit here", async () => {
    const { render, screen } = await import("@testing-library/react");
    const userEvent = (await import("@testing-library/user-event")).default;
    const { PartSettings } = await import("./pages/admin/report/PartSettings");
    const onChange = vi.fn(),
      onUnlink = vi.fn();
    const u = userEvent.setup();
    const snippets = [
      {
        id: 1,
        kind: "snippet" as const,
        key: "terms",
        name: "Disclaimer",
        revision: 3,
        used_by: [
          { template: 1, form: "PDI" },
          { template: 2, form: "EV" },
        ],
      },
    ];
    const part: Part = { id: "s", type: "snippet", ref: { key: "terms", revision: 2 } };
    const { rerender } = render(
      <PartSettings
        part={part}
        ctx={{ ...ctx, snippets }}
        onChange={onChange}
        onDelete={() => {}}
        onDuplicate={() => {}}
        onMove={() => {}}
        onUnlink={onUnlink}
      />,
    );
    expect(screen.getByText(/Used by: PDI, EV/)).toBeTruthy();
    await u.click(screen.getByRole("button", { name: "Use the newest version" }));
    expect(onChange).toHaveBeenLastCalledWith({ ref: { key: "terms", revision: 3 } });
    await u.click(screen.getByRole("button", { name: /Stop sharing/ }));
    expect(onUnlink).toHaveBeenCalled();
    expect(screen.queryByText("Share with other reports")).toBeNull(); // already shared
    rerender(
      <PartSettings
        part={{ ...part, ref: { key: "gone", revision: 1 } }}
        ctx={{ ...ctx, snippets }}
        onChange={onChange}
        onDelete={() => {}}
        onDuplicate={() => {}}
        onMove={() => {}}
      />,
    );
    expect(screen.getByText(/not on this server/)).toBeTruthy();
  });
});

describe("room to work", () => {
  it("edits a grid in a wide window", async () => {
    const { render, screen } = await import("@testing-library/react");
    const userEvent = (await import("@testing-library/user-event")).default;
    const { PartSettings } = await import("./pages/admin/report/PartSettings");
    const u = userEvent.setup();
    const ctx = { readOnly: false, sections: [], fields: [] };
    const part: Part = {
      id: "g",
      type: "table",
      source: {
        kind: "grid",
        columns: [{ label: "Engine" }, { label: "A.C." }],
        rows: [{ label: "", cells: [{ field: "inspection.e" }, { text: "" }] }],
      },
    };
    render(<PartSettings part={part} ctx={ctx} onChange={() => {}} onDelete={() => {}} onDuplicate={() => {}} onMove={() => {}} />);
    expect(screen.getByText(/1 cell with a field/)).toBeTruthy();
    expect(screen.queryByLabelText("Column 1 name")).toBeNull();
    await u.click(screen.getByRole("button", { name: "Edit grid" }));
    expect((screen.getByLabelText("Column 1 name") as HTMLInputElement).value).toBe("Engine");
  });
  it("folds pages and opens the page of the part being changed", async () => {
    const { render, screen } = await import("@testing-library/react");
    const userEvent = (await import("@testing-library/user-event")).default;
    const { PagesPanel } = await import("./pages/admin/report/PagesPanel");
    const u = userEvent.setup();
    const d = def();
    const props = { def: d, onSelect: () => {}, onChange: () => {}, formPages: [], sections: {}, readOnly: true };
    const { rerender } = render(<PagesPanel {...props} sel={null} />);
    expect(screen.queryByText("c")).toBeNull(); // page 2 folded
    expect(screen.getByText("1 part")).toBeTruthy();
    rerender(<PagesPanel {...props} sel={{ kind: "part", id: "c" }} />);
    expect(screen.getByText("c")).toBeTruthy(); // opened by itself
    await u.click(screen.getByRole("button", { name: "Fold all" }));
    expect(screen.queryByText("a")).toBeNull();
    await u.click(screen.getByRole("button", { name: "Open page 1" }));
    expect(screen.getByText("a")).toBeTruthy();
    await u.click(screen.getByRole("button", { name: "Open all" }));
    expect(screen.getByText("c")).toBeTruthy();
  });
});

describe("sharing helpers", () => {
  it("swaps a field the form lacks for the suggested one everywhere in a part", () => {
    const p: Part = {
      id: "t",
      type: "table",
      title: "{{ inspection.odo }} km",
      source: { kind: "fields", rows: [{ field: "inspection.odo" }, { field: "inspection.odometer_x" }] },
    };
    expect(replaceRef(p, "inspection.odo", "inspection.odometer")).toEqual({
      id: "t",
      type: "table",
      title: "{{ inspection.odometer }} km",
      source: { kind: "fields", rows: [{ field: "inspection.odometer" }, { field: "inspection.odometer_x" }] },
    });
    const sec: Part = { id: "s", type: "table", source: { kind: "section", section: "inspection.frnt", exclude: ["frnt", "x"] } };
    expect(replaceRef(sec, "inspection.frnt", "inspection.front")).toMatchObject({
      source: { section: "inspection.front", exclude: ["front", "x"] },
    });
    expect(
      replaceRef(
        { id: "b", type: "table", source: { kind: "section", section: "inspection.a", exclude: ["k"] } },
        "booking.k",
        "booking.j",
      ),
    ).toMatchObject({ source: { exclude: ["k"] } }); // exclusions are inspection fields
  });
  it("puts a shared part's own parts in its place, and splits a theme off a template", () => {
    const d: Definition = {
      schema: 2,
      theme: { size: 10 },
      bands: {},
      filename: "x.pdf",
      pages: [{ id: "p", title: "P", parts: [T("a"), sharedPart({ key: "k", revision: 1 }), T("b")] }],
    };
    const sid = d.pages[0]!.parts[1]!.id!;
    const out = unlinkShared(d, sid, [{ id: "old", type: "text", html: "<p>Terms</p>" }, { type: "spacer" }]);
    expect(out.pages[0]!.parts.map((p) => p.type)).toEqual(["table", "text", "spacer", "table"]);
    expect(out.pages[0]!.parts[1]!.id).not.toBe("old");
    expect(unlinkShared(d, "nope", [])).toBe(d);
    expect(themeOf(d)).toEqual({ theme: { size: 10 }, bands: {} });
    expect(withoutTheme(d)).toEqual({ schema: 2, filename: "x.pdf", pages: d.pages });
    expect(partName(d.pages[0]!.parts[1]!, {}, { k: "Disclaimer" })).toBe("Disclaimer");
    expect(partName(d.pages[0]!.parts[1]!)).toBe("k");
    expect(snippetContent({ id: "z", type: "spacer", height: 4 })).toEqual({ parts: [{ type: "spacer", height: 4 }] });
    expect([keyOf("Car C.I.D. theme"), keyOf("2024 look"), keyOf("  ")]).toEqual(["car_c_i_d_theme", "x_2024_look", "x_"]);
  });
});

describe("download links", () => {
  it("starts a button on the photos ZIP and lets rich text link only to the report's own links", async () => {
    expect(newPart("button")).toMatchObject({ type: "button", link: "photos", label: "Download photos" });
    expect(partName(newPart("button"))).toBe("Button link");
    const { cleanHtml } = await import("./pages/admin/report/RichText");
    expect(cleanHtml('<a href="{{ sys.photos_url }}">p</a><a href="{{ inspection.note }}">n</a>')).toBe(
      '<a href="{{ sys.photos_url }}">p</a><a>n</a>',
    );
  });
  it("picks what a button opens and resets its text to match", async () => {
    const { render, screen } = await import("@testing-library/react");
    const userEvent = (await import("@testing-library/user-event")).default;
    const { PartSettings } = await import("./pages/admin/report/PartSettings");
    const onChange = vi.fn();
    const u = userEvent.setup();
    render(
      <PartSettings
        part={newPart("button")}
        ctx={{ readOnly: false, sections: [], fields: [] }}
        onChange={onChange}
        onDelete={() => {}}
        onDuplicate={() => {}}
        onMove={() => {}}
      />,
    );
    expect(screen.getByText(/One tap downloads a ZIP of every photo/)).toBeTruthy();
    await u.selectOptions(screen.getByLabelText("Opens"), "videos");
    expect(onChange).toHaveBeenLastCalledWith({ link: "videos", label: "Download videos" });
    await u.click(screen.getByRole("button", { name: "Left" }));
    expect(onChange).toHaveBeenLastCalledWith({ align: "left" });
  });
  it("shows the customer how many photos, then starts the ZIP download", async () => {
    const { render, screen } = await import("@testing-library/react");
    const { MemoryRouter, Route, Routes } = await import("react-router-dom");
    const { ReportMediaPage } = await import("./pages/Public");
    const assign = vi.fn();
    vi.stubGlobal("location", { ...window.location, assign });
    const json = (b: unknown, status = 200) => new Response(JSON.stringify(b), { status, headers: { "Content-Type": "application/json" } });
    vi.spyOn(globalThis, "fetch").mockImplementation(async (u) =>
      String(u).includes("/zips/")
        ? json({ status: "ready", progress: 100, url: "https://files.test/DEMO-3%20photos.zip" })
        : json({ booking_id: "DEMO-3", link: "photos", count: 48, zip: "zips/abc" }),
    );
    render(
      <MemoryRouter initialEntries={["/verify/tok/photos"]}>
        <Routes>
          <Route path="/verify/:token/:link" element={<ReportMediaPage />} />
        </Routes>
      </MemoryRouter>,
    );
    expect(await screen.findByRole("heading", { name: "48 photos" })).toBeTruthy();
    expect(screen.getByText(/booking DEMO-3/)).toBeTruthy();
    expect(screen.getByText("Car C.I.D.")).toBeTruthy(); // the customer's brand, not "Vayu"
    expect(screen.queryByText("Vayu")).toBeNull();
    expect(document.title).toBe("Car C.I.D.");
    await vi.waitFor(() => expect(assign).toHaveBeenCalledWith("https://files.test/DEMO-3%20photos.zip"));
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });
  it("says plainly when a report has no videos", async () => {
    const { render, screen } = await import("@testing-library/react");
    const { MemoryRouter, Route, Routes } = await import("react-router-dom");
    const { ReportMediaPage } = await import("./pages/Public");
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ code: "NO_MEDIA", message: "x" }), { status: 404, headers: { "Content-Type": "application/json" } }),
    );
    render(
      <MemoryRouter initialEntries={["/verify/tok/videos"]}>
        <Routes>
          <Route path="/verify/:token/:link" element={<ReportMediaPage />} />
        </Routes>
      </MemoryRouter>,
    );
    expect(await screen.findByText("This report has no videos.")).toBeTruthy();
    vi.restoreAllMocks();
  });
  it("an expired photo link says so and offers no retry (R-09: 30 days after the first PDF)", async () => {
    const { render, screen } = await import("@testing-library/react");
    const { MemoryRouter, Route, Routes } = await import("react-router-dom");
    const { ReportMediaPage } = await import("./pages/Public");
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ code: "LINK_EXPIRED", detail: "x" }), { status: 410, headers: { "Content-Type": "application/json" } }),
    );
    render(
      <MemoryRouter initialEntries={["/verify/tok/photos"]}>
        <Routes>
          <Route path="/verify/:token/:link" element={<ReportMediaPage />} />
        </Routes>
      </MemoryRouter>,
    );
    expect(
      await screen.findByText(
        /This link has expired. Photo and video links work for 30 days after the report is made. Ask Car C.I.D. for a new report./,
      ),
    ).toBeTruthy();
    expect(screen.queryByText(/try again/i)).toBeNull();
    expect(screen.queryByRole("button", { name: /try again|retry/i })).toBeNull();
    vi.restoreAllMocks();
  });
});

describe("photo and video storage setting", () => {
  it("shows a deleted file as deleted, not as still loading", async () => {
    const { render, screen } = await import("@testing-library/react");
    const { QueryClient, QueryClientProvider } = await import("@tanstack/react-query");
    const { Thumb } = await import("./ui/MediaThumb");
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ code: "MEDIA_REMOVED", detail: "x" }), {
        status: 410,
        headers: { "Content-Type": "application/json" },
      }),
    );
    render(
      <QueryClientProvider client={new QueryClient()}>
        <Thumb id="a" />
      </QueryClientProvider>,
    );
    expect(await screen.findByLabelText("Deleted after the storage time set in Settings")).toHaveTextContent("Deleted");
    vi.restoreAllMocks();
  });
  it("lets Admin keep photos 90 days and refuses fewer than 30", async () => {
    const { render, screen, waitFor } = await import("@testing-library/react");
    const userEvent = (await import("@testing-library/user-event")).default;
    const { QueryClient, QueryClientProvider } = await import("@tanstack/react-query");
    const { MemoryRouter } = await import("react-router-dom");
    const { AuthProvider } = await import("./auth");
    const { Settings } = await import("./pages/admin/Settings");
    const puts: unknown[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (url, init) => {
      const u = String(url);
      if (init?.method === "PUT") puts.push(JSON.parse(String(init.body)));
      const body = u.includes("auth/me")
        ? { id: 1, username: "a", name: "A", role: "admin", permissions: { "settings.view": "all", "settings.edit": "all" } }
        : u.includes("settings/media")
          ? { photo_days: 0, video_days: 0 }
          : u.includes("settings/timing")
            ? { late_grace_minutes: 15, min_minutes_default: 30, min_minutes_by_type: {} }
            : [];
      return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
    });
    const u = userEvent.setup();
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <AuthProvider>
            <Settings />
          </AuthProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    const box = await screen.findByLabelText("Keep photos for (days)");
    expect(screen.getAllByText("kept for ever")).toHaveLength(2);
    const section = screen.getByRole("region", { name: "Photo and video storage" });
    const save = section.querySelector("button")!;
    await u.clear(box);
    await u.type(box, "5");
    expect(save).toBeDisabled(); // 1 to 29 days is refused
    await u.clear(box);
    await u.type(box, "90");
    expect(save).toBeEnabled();
    await u.click(save);
    await waitFor(() => expect(puts).toContainEqual({ photo_days: 90, video_days: 0 }));
    vi.restoreAllMocks();
  });
});

describe("the shared library", () => {
  it("renames an item and offers delete only when no report uses it", async () => {
    const { render, screen, waitFor } = await import("@testing-library/react");
    const userEvent = (await import("@testing-library/user-event")).default;
    const { QueryClient, QueryClientProvider } = await import("@tanstack/react-query");
    const { SharedLibrary } = await import("./pages/admin/report/SharedLibrary");
    const calls: { method: string; url: string; body?: unknown }[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (url, init) => {
      calls.push({ method: init?.method ?? "GET", url: String(url), body: init?.body ? JSON.parse(String(init.body)) : undefined });
      const items = [
        { id: 1, kind: "theme", key: "carcid", name: "Car C.I.D.", revision: 4, used_by: [{ template: 7, form: "PDI", published: 4 }] },
        { id: 2, kind: "snippet", key: "old", name: "Old terms", revision: 1, used_by: [] },
      ];
      return init?.method === "DELETE"
        ? new Response(null, { status: 204 })
        : new Response(JSON.stringify(init?.method && init.method !== "GET" ? items[0] : items), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
    });
    const u = userEvent.setup();
    render(
      <QueryClientProvider client={new QueryClient()}>
        <SharedLibrary editable forms={[]} templates={[]} />
      </QueryClientProvider>,
    );
    await u.click(await screen.findByRole("button", { name: "More for Car C.I.D." }));
    expect(screen.queryByRole("menuitem", { name: "Delete" })).toBeNull(); // in use: no delete
    await u.click(screen.getByRole("menuitem", { name: "Rename" }));
    const box = screen.getByLabelText("Name");
    await u.clear(box);
    await u.type(box, "Car C.I.D. look");
    await u.click(screen.getByRole("button", { name: "Rename" }));
    await waitFor(() =>
      expect(calls).toContainEqual({ method: "PATCH", url: expect.stringContaining("pdf-shared/1"), body: { name: "Car C.I.D. look" } }),
    );
    await u.click(screen.getByRole("button", { name: "More for Old terms" }));
    await u.click(screen.getByRole("menuitem", { name: "Delete" }));
    await u.click(screen.getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(calls.some((c) => c.method === "DELETE" && c.url.includes("pdf-shared/2"))).toBe(true));
    vi.restoreAllMocks();
  });
  it("says who uses an item at which version", async () => {
    const { usedBy } = await import("./pages/admin/report/SharedLibrary");
    expect(
      usedBy([
        { template: 1, form: "PDI", published: 4, draft: 4 },
        { template: 2, form: "EV", published: 3, draft: 4 },
        { template: 3, form: "Used car", draft: 2 },
      ]),
    ).toBe("PDI (uses v4) · EV (live uses v3, draft uses v4) · Used car (draft uses v2)");
  });
  it("lists themes and shared parts, edits a part and saves it as the next version after a warning", async () => {
    const { render, screen, waitFor, within } = await import("@testing-library/react");
    const userEvent = (await import("@testing-library/user-event")).default;
    const { QueryClient, QueryClientProvider } = await import("@tanstack/react-query");
    const { SharedLibrary } = await import("./pages/admin/report/SharedLibrary");
    const posts: { url: string; body: unknown }[] = [];
    const items = [
      {
        id: 1,
        kind: "theme",
        key: "carcid",
        name: "Car C.I.D.",
        revision: 4,
        used_by: [{ template: 7, form: "PDI", published: 4, draft: 4 }],
      },
      { id: 2, kind: "snippet", key: "disc", name: "PDI disclaimer", revision: 2, used_by: [{ template: 7, form: "PDI", published: 2 }] },
    ];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (url, init) => {
      const u = String(url);
      if (init?.method === "POST") posts.push({ url: u, body: JSON.parse(String(init.body)) });
      const body = u.includes("/preview")
        ? { pdf: "", pages: [] }
        : u.includes("pdf-shared/2")
          ? { ...items[1], content: { parts: [{ type: "text", html: "<p>Terms</p>" }] } }
          : u.endsWith("pdf-shared") && init?.method === "POST"
            ? { ...items[1], revision: 3, updated: ["PDI v13 (published)"] }
            : u.includes("pdf-shared")
              ? items
              : u.includes("pdf-template-versions/70")
                ? { id: 70, definition: { schema: 2, theme_ref: { key: "carcid", revision: 4 }, pages: [] } }
                : u.includes("bookings")
                  ? { count: 0, next: null, previous: null, results: [] }
                  : [];
      return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
    });
    const u = userEvent.setup();
    render(
      <QueryClientProvider client={new QueryClient()}>
        <SharedLibrary
          editable
          forms={[]}
          templates={[{ id: 7, form: 3, form_key: "pdi", versions: [{ id: 70, number: 12, status: "published" }] }]}
        />
      </QueryClientProvider>,
    );
    const parts = await screen.findByRole("region", { name: "Shared parts" });
    expect(within(parts).getByRole("row", { name: /PDI disclaimer v2 PDI \(uses v2\)/ })).toBeTruthy();
    expect(within(screen.getByRole("region", { name: "Themes" })).getByText("Car C.I.D.")).toBeTruthy();
    await u.click(within(parts).getByRole("button", { name: "Edit" }));
    const save = await screen.findByRole("button", { name: "Save as version 3" });
    expect(save).toBeDisabled(); // nothing changed yet
    await u.click(await screen.findByText("Terms")); // the part in the list
    await u.click(screen.getByRole("button", { name: "Centre" }));
    await u.click(save);
    expect(screen.getByText(/Every report using it changes: PDI \(uses v2\)/)).toBeTruthy();
    await u.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() =>
      expect(posts.find((p) => p.url.endsWith("pdf-shared"))?.body).toEqual({
        kind: "snippet",
        key: "disc",
        name: "PDI disclaimer",
        content: { parts: [{ type: "text", html: "<p>Terms</p>", align: "center" }] },
      }),
    );
    vi.restoreAllMocks();
  });
});
