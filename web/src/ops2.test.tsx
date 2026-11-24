import { describe, expect, it, vi } from "vitest";
import type { FormField } from "./api/types";
import { addDays, fmtDay, fmtPhone, fmtSlot, fmtStamp, fmtTime } from "./lib/format";
import { activityText } from "./pages/ops/Booking";
import { viewQuery } from "./pages/ops/Bookings";
import { dayWindow } from "./pages/ops/Today";
import { defectOf } from "./ui/AnswerSheet";

const NOW = new Date(2026, 10, 23, 14, 20);   // Mon 23 Nov 2026, 2:20 pm

describe("human dates, times and phones", () => {
  it("says today / tomorrow / yesterday, else a short date (with the year only when it differs)", () => {
    expect(fmtDay("2026-11-23", NOW)).toBe("Today");
    expect(fmtDay("2026-11-24", NOW)).toBe("Tomorrow");
    expect(fmtDay("2026-11-22", NOW)).toBe("Yesterday");
    expect(fmtDay("2026-11-27", NOW)).toMatch(/^Fri 27 Nov$/);
    expect(fmtDay("2027-01-05", NOW)).toMatch(/2027$/);
    expect(fmtDay("nope", NOW)).toBe("");
    expect(addDays("2026-12-31", 1)).toBe("2027-01-01");
  });
  it("uses a 12-hour clock", () => {
    expect([fmtTime("00:05"), fmtTime("09:30"), fmtTime("12:00"), fmtTime("15:30")]).toEqual(["12:05 am", "9:30 am", "12:00 pm", "3:30 pm"]);
    expect(fmtSlot("2026-11-24", "10:30", NOW)).toBe("Tomorrow, 10:30 am");
    expect(fmtStamp(new Date(2026, 10, 23, 9, 5).toISOString(), NOW)).toBe("Today, 9:05 am");
  });
  it("groups an Indian mobile number and leaves anything else alone", () => {
    expect(fmtPhone("+919876500000")).toBe("+91 98765 00000");
    expect(fmtPhone("12345")).toBe("12345");
  });
});

describe("booking views", () => {
  it("each saved view asks the server for the right slice", () => {
    expect(viewQuery("today", NOW)).toEqual({ date_from: "2026-11-23", date_to: "2026-11-23", order: "schedule" });
    expect(viewQuery("unassigned", NOW)).toMatchObject({ stage: "draft" });
    expect(viewQuery("uploading", NOW)).toEqual({ stage: "submitted" });
    expect(viewQuery("upcoming", NOW)).toMatchObject({ date_from: "2026-11-24" });
    expect(viewQuery("all", NOW)).toEqual({});
  });
  it("the schedule spans at least 9 am to 9 pm and grows to fit early or late jobs", () => {
    expect(dayWindow([])).toEqual([9, 21]);
    expect(dayWindow([{ start: 7.5, end: 8.5 }, { start: 20.25, end: 21.25 }])).toEqual([7, 22]);
  });
});

describe("activity lines", () => {
  const by = { id: 1, name: "Priya", role: "ops" };
  const line = (r: Partial<Parameters<typeof activityText>[0]>) => activityText({ at: "", kind: "changed", by, changes: {}, keys: [], ...r }, () => "Ravi", (k) => k === "customer_name" ? "Customer name" : k, (k) => String(k).toUpperCase());
  it("says what happened in words", () => {
    expect(line({ kind: "created" })).toBe("Created by Priya");
    expect(line({ changes: { assigned_expert: [null, 5] } })).toBe("Assigned to Ravi by Priya");
    expect(line({ changes: { assigned_expert: [4, 5] } })).toBe("Reassigned to Ravi by Priya");
    expect(line({ changes: { stage: ["submitted", "completed"] }, by: null })).toBe("Completed: every file uploaded");
    expect(line({ changes: { stage: ["in_progress", "assigned"] } })).toBe("Force-released by Priya");
    expect(line({ kind: "edited", keys: ["customer_name"] })).toBe("Priya changed Customer name");
    expect(line({ kind: "inspection_edited", keys: ["inspection.a", "inspection.b"] })).toBe("Priya changed 2 answers");
    expect(line({ changes: { inspection_type: ["pdi", "ev"] } })).toBe("Type changed to EV by Priya");
  });
});

describe("defects in the review sheet", () => {
  const f = (type: string): FormField => ({ id: 1, section: 1, key: "door", label: "Door", helper_text: "", type, required: false, required_if: null, show_if: null, visible: true, order: 0, is_system: false, access: {}, locked: false, library: null,
    config: { options: [{ key: "ok", label: "OK" }, { key: "scr", label: "Scratched", is_defect: true, severity: "minor" }, { key: "dent", label: "Dented", is_defect: true, severity: "major" }] } });
  it("marks a defect answer with its severity, and nothing else", () => {
    expect(defectOf(f("single_choice"), "ok")).toBeNull();
    expect(defectOf(f("single_choice"), "scr")).toBe("Minor");
    expect(defectOf(f("multi_choice"), ["scr", "dent"])).toBe("Major");
    expect(defectOf(f("short_text"), "dent")).toBeNull();
  });
});

describe("dashboard", () => {
  it("presets cover the right dates and pick a sensible bar size", async () => {
    const { presetRange, groupFor, delta } = await import("./pages/ops/Dashboards");
    expect(presetRange("today", NOW)).toEqual(["2026-11-23", "2026-11-23"]);
    expect(presetRange("7", NOW)).toEqual(["2026-11-17", "2026-11-23"]);
    expect(presetRange("month", NOW)).toEqual(["2026-11-01", "2026-11-23"]);
    expect(groupFor("2026-11-01", "2026-11-30")).toBe("day");
    expect(groupFor("2026-09-01", "2026-11-30")).toBe("week");
    expect(groupFor("2026-01-01", "2026-11-30")).toBe("month");
    expect(delta(110, 100, "count")).toEqual({ text: "+10%", good: true });
    expect(delta(95.5, 96.7, "pct")).toEqual({ text: "−1.2 pts", good: false });
    expect(delta(100, 110, "minutes", false)).toEqual({ text: "−10 min", good: true });
    expect(delta(3, 0, "count").text).toBe("");
    const { daysBetween } = await import("./pages/ops/Dashboards");
    expect(daysBetween("2026-11-29", "2026-12-02")).toEqual(["2026-11-29", "2026-11-30", "2026-12-01", "2026-12-02"]);
    expect(delta(null, 5, "count").text).toBe("");
  });
});

describe("my jobs", () => {
  it("groups jobs under Today (overdue too), Tomorrow, Later and Earlier (finished)", async () => {
    const { groupOf } = await import("./pages/expert/MyJobs");
    const j = (stage: string, d: string) => ({ stage, answers: { inspection_date: d } });
    expect(groupOf(j("assigned", "2026-11-23"), NOW)).toBe("Today");
    expect(groupOf(j("in_progress", "2026-11-20"), NOW)).toBe("Today");
    expect(groupOf(j("assigned", "2026-11-24"), NOW)).toBe("Tomorrow");
    expect(groupOf(j("assigned", "2026-12-02"), NOW)).toBe("Later");
    expect(groupOf(j("completed", "2026-11-23"), NOW)).toBe("Earlier");
  });
});

describe("audit log links", () => {
  it("opens what an entry is about, and nothing for deleted things", async () => {
    const { targetLink } = await import("./pages/admin/Audit");
    expect(targetLink({ target_type: "booking", target_id: "b1", action: "booking.force_release" })).toBe("/booking/b1");
    expect(targetLink({ target_type: "booking", target_id: "b1", action: "booking.delete" })).toBeNull();
    expect(targetLink({ target_type: "library_item", target_id: "7", action: "library.update" })).toBe("/library/7");
    expect(targetLink({ target_type: "form_version", target_id: "3", action: "form.publish" })).toBe("/forms");
    expect(targetLink({ target_type: "something_new", target_id: "1", action: "x.y" })).toBeNull();
  });
});

describe("integration words", () => {
  it("names events and delivery errors in words", async () => {
    const { eventWord, errorWord } = await import("./pages/admin/Integrations");
    expect(eventWord("booking.updated")).toBe("Booking updated");
    expect(eventWord("pdf.ready")).toBe("PDF ready");
    expect(errorWord("blocked_address")).toMatch(/not allowed/);
    expect(errorWord("http_503")).toBe("Server answered 503");
    expect(errorWord("something_new")).toBe("something_new");
  });
});

describe("field types in words", () => {
  it("names the type with the detail that matters", async () => {
    const { typeSummary } = await import("./lib/fieldTypes");
    expect(typeSummary({ type: "single_choice", config: { options: [{}, {}, {}] } })).toBe("Choose one · 3 choices");
    expect(typeSummary({ type: "number", config: { unit: "km" } })).toBe("Number · km");
    expect(typeSummary({ type: "photo", config: { capture: "camera" } })).toBe("Photos · camera only");
    expect(typeSummary({ type: "gps", config: {} })).toBe("GPS location · automatic");
    expect(typeSummary({ type: "short_text", config: {} })).toBe("Short text");
  });
  it("a new choice's key follows its label until someone types a key", async () => {
    const { render, screen } = await import("@testing-library/react");
    const userEvent = (await import("@testing-library/user-event")).default;
    const { FieldEditor } = await import("./pages/admin/FieldEditor");
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

describe("choice keys stay put once saved", () => {
  it("renaming a saved choice keeps its key; a new one follows its label", async () => {
    const { followsLabel } = await import("./pages/admin/FieldEditor");
    const saved = new Set(["ok"]);
    expect(followsLabel({ key: "ok", label: "OK" }, saved)).toBe(false);          // saved: never rewritten
    expect(followsLabel({ key: "", label: "" }, saved)).toBe(true);               // new and empty
    expect(followsLabel({ key: "badly", label: "Badly" }, saved)).toBe(true);     // new, still following
    expect(followsLabel({ key: "custom", label: "Badly" }, saved)).toBe(false);   // new, key typed by hand
  });
  it("editing the label of a saved choice in the editor does not touch its key", async () => {
    const { render, screen } = await import("@testing-library/react");
    const userEvent = (await import("@testing-library/user-event")).default;
    const { FieldEditor } = await import("./pages/admin/FieldEditor");
    const onSave = vi.fn();
    const f = { id: 1, section: 1, key: "door", label: "Door", helper_text: "", type: "single_choice", required: false, required_if: null, show_if: null,
      config: { options: [{ key: "ok", label: "OK" }] }, visible: true, order: 0, is_system: false, access: {}, locked: false, library: null };
    const u = userEvent.setup();
    render(<FieldEditor field={f as never} choices={[]} lists={[]} categories={[]} onSave={onSave} onDelete={() => {}} readOnly={false} />);
    await u.clear(screen.getByLabelText("Choice label"));
    await u.type(screen.getByLabelText("Choice label"), "Fine");
    await u.click(screen.getByRole("button", { name: "Save field" }));
    expect(onSave.mock.calls[0]![0].config.options).toEqual([{ key: "ok", label: "Fine" }]);
  });
});

describe("report support in the field editor", () => {
  const base = { id: 1, section: 1, helper_text: "", required: false, required_if: null, show_if: null, visible: true, order: 0, is_system: false, access: {}, locked: false, library: null };
  it("an answer prints in the colour chosen, else one that follows its meaning", async () => {
    const { toneOf } = await import("./pages/admin/FieldEditor");
    expect(toneOf({ key: "ok", label: "Ok" })).toBe("ok");
    expect(toneOf({ key: "s", label: "Scratch", is_defect: true, severity: "minor" })).toBe("warn");
    expect(toneOf({ key: "d", label: "Damaged", is_defect: true, severity: "major" })).toBe("bad");
    expect(toneOf({ key: "na", label: "Not available", tone: "muted" })).toBe("muted");
  });
  it("picks a report colour for an answer", async () => {
    const { render, screen } = await import("@testing-library/react");
    const userEvent = (await import("@testing-library/user-event")).default;
    const { FieldEditor } = await import("./pages/admin/FieldEditor");
    const onSave = vi.fn();
    const f = { ...base, key: "plate", label: "Number plate", type: "single_choice", config: { options: [{ key: "na", label: "Not available" }] } };
    const u = userEvent.setup();
    render(<FieldEditor field={f as never} choices={[]} lists={[]} categories={[]} onSave={onSave} onDelete={() => {}} readOnly={false} />);
    await u.selectOptions(screen.getByLabelText("Colour of Not available in the report"), "muted");
    await u.click(screen.getByRole("button", { name: "Save field" }));
    expect(onSave.mock.calls[0]![0].config.options).toEqual([{ key: "na", label: "Not available", tone: "muted" }]);
  });
  it("a photo can be an issue photo and show one of the checks of its section", async () => {
    const { render, screen } = await import("@testing-library/react");
    const userEvent = (await import("@testing-library/user-event")).default;
    const { FieldEditor } = await import("./pages/admin/FieldEditor");
    const onSave = vi.fn();
    const f = { ...base, key: "door_photo", label: "Door photo", type: "photo", config: { max_count: 3 } };
    const siblings = [{ key: "door", label: "Door", type: "single_choice" }, { key: "other_photo", label: "Other photo", type: "photo" }];
    const u = userEvent.setup();
    render(<FieldEditor field={f as never} choices={[]} lists={[]} categories={[]} onSave={onSave} onDelete={() => {}} readOnly={false} siblings={siblings} />);
    expect(screen.queryByRole("option", { name: "Other photo" })).toBeNull();          // a photo cannot show a photo
    await u.click(screen.getByRole("checkbox", { name: /Issue photo/ }));
    await u.selectOptions(screen.getByLabelText("Photo of"), "door");
    await u.click(screen.getByRole("button", { name: "Save field" }));
    expect(onSave.mock.calls[0]![0].config).toEqual({ max_count: 3, issue_photo: true, photo_of: "door" });
  });
  it("a new photo shows the nearest check above it", async () => {
    const { photoOfDefault } = await import("./lib/fieldTypes");
    expect(photoOfDefault([{ key: "door", type: "single_choice" }, { key: "door_remark", type: "short_text" }, { key: "x", type: "photo" }])).toBe("door");
    expect(photoOfDefault([{ key: "x", type: "photo" }])).toBeUndefined();
  });
});

describe("row menus", () => {
  it("open below the button, or above it near the bottom, and stay inside the window", async () => {
    const { placeMenu } = await import("./ui/Menu");
    const view = { width: 1440, height: 900 }, menu = { width: 200, height: 180 };
    expect(placeMenu({ top: 100, bottom: 130, right: 1400 }, menu, view)).toEqual({ top: 136, left: 1200 });
    expect(placeMenu({ top: 800, bottom: 830, right: 1400 }, menu, view)).toEqual({ top: 614, left: 1200 });   // flipped up
    expect(placeMenu({ top: 100, bottom: 130, right: 50 }, menu, view).left).toBe(8);                         // not off the left edge
  });
});

describe("stacked bars", () => {
  it("uses clean ticks and folds a ninth series into Other", async () => {
    const { niceTicks, foldSeries } = await import("./ui/StackedBars");
    expect(niceTicks(4)).toEqual([0, 1, 2, 3, 4]);
    expect(niceTicks(23)).toEqual([0, 10, 20, 30]);
    expect(niceTicks(0)).toEqual([0, 1]);
    const series = Array.from({ length: 10 }, (_, i) => ({ key: `s${i}`, name: `S${i}` }));
    const cols = [{ key: "d", label: "d", long: "d", values: Object.fromEntries(series.map((s, i) => [s.key, i + 1])) }];
    const f = foldSeries(series, cols);
    expect(f.series).toHaveLength(8);
    expect(f.series[7]!.name).toBe("Other");
    expect(f.cols[0]!.values.__other).toBe(1 + 2 + 3);         // the three smallest
  });
});

describe("my jobs quick filters", () => {
  it("sorts each job into To do / Today / Upcoming / Started / Done", async () => {
    const { matchesJob } = await import("./pages/expert/MyJobs");
    const j = (stage: string, d: string) => ({ stage, answers: { inspection_date: d } });
    const today = j("assigned", "2026-11-23"), later = j("assigned", "2026-12-01"), started = j("in_progress", "2026-11-23"), done = j("completed", "2026-11-20");
    const pick = (f: Parameters<typeof matchesJob>[1]) => [today, later, started, done].filter((b) => matchesJob(b, f, NOW));
    expect(pick("open")).toEqual([today, later, started]);
    expect(pick("today")).toEqual([today, started]);
    expect(pick("upcoming")).toEqual([later]);
    expect(pick("started")).toEqual([started]);
    expect(pick("done")).toEqual([done]);
    expect(pick("all")).toHaveLength(4);
  });
});
