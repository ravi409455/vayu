import { describe, expect, it } from "vitest";
import { activityDetails, activityText } from "./ActivityCard";

describe("activity lines", () => {
  const by = { id: 1, name: "Priya", role: "ops" };
  const line = (r: Partial<Parameters<typeof activityText>[0]>) =>
    activityText(
      { at: "", kind: "changed", by, changes: {}, keys: [], ...r },
      () => "Ravi",
      (k) => (k === "customer_name" ? "Customer name" : k),
      (k) => String(k).toUpperCase(),
    );
  it("says what happened in words", () => {
    expect(line({ kind: "created" })).toBe("Created by Priya");
    expect(line({ changes: { assigned_expert: [null, 5] } })).toBe("Assigned to Ravi by Priya");
    expect(line({ changes: { assigned_expert: [4, 5] } })).toBe("Reassigned to Ravi by Priya");
    expect(line({ changes: { stage: ["submitted", "completed"] }, by: null })).toBe("Completed: every file uploaded");
    expect(line({ changes: { stage: ["in_progress", "assigned"] } })).toBe("Force-released by Priya");
    expect(line({ kind: "edited", keys: ["customer_name"] })).toBe("Priya changed Customer name");
    expect(line({ kind: "inspection_edited", keys: ["inspection.a", "inspection.b"] })).toBe("Priya changed 2 answers");
    expect(line({ changes: { inspection_type: ["pdi", "ev"] } })).toBe("Type changed to EV by Priya");
    expect(line({ kind: "media_replaced", keys: ["inspection.odometer_photo"] })).toBe(
      "Priya replaced a file in inspection.odometer_photo",
    );
    expect(line({ kind: "media_added", keys: ["inspection.clip"] })).toBe("Priya added a file to inspection.clip");
    expect(
      line({ kind: "key_checks_changed", keys: ["check.accident"], changes: { "check.accident": ["None seen", "Minor, rear"] } }),
    ).toBe("Priya changed check.accident: None seen → Minor, rear");
    expect(line({ kind: "key_checks_changed", keys: ["check.odo"], changes: { "check.odo": ["", null] } })).toBe(
      "Priya changed check.odo: empty → empty",
    );
    expect(line({ kind: "report_downloaded", changes: { revision: 3 } as never })).toBe("Priya downloaded the report");
    expect(line({ kind: "report_shared", changes: { revision: 3, how: "check_link" } as never })).toBe(
      "Priya copied the report's check link",
    );
  });
});

describe("what changed, on hover", () => {
  const by = { id: 1, name: "Priya", role: "ops" };
  const details = (r: Partial<Parameters<typeof activityDetails>[0]>) =>
    activityDetails(
      { at: "", kind: "edited", by, changes: {}, keys: [], ...r },
      () => "Ravi",
      (k) => ({ customer_phone: "Customer phone", "inspection.odometer": "Odometer" })[k] ?? k,
      (k) => String(k).toUpperCase(),
    );
  it("lists each changed value as old → new", () => {
    expect(details({ changes: { customer_phone: ["9800000000", "9700000000"] } })).toEqual(["Customer phone: 9800000000 → 9700000000"]);
    expect(details({ kind: "inspection_edited", changes: { "inspection.odometer": [42000, 42100] } })).toEqual(["Odometer: 42000 → 42100"]);
  });
  it("says empty, Yes/No, joins lists and names people and types", () => {
    expect(details({ changes: { note: [null, "Scratch"], ok: [false, true], colours: [["red"], ["red", "blue"]] } })).toEqual([
      "note: empty → Scratch",
      "ok: No → Yes",
      "colours: red → red, blue",
    ]);
    expect(details({ kind: "changed", changes: { assigned_expert: [null, 5], inspection_type: ["pdi", "ev"] } })).toEqual([
      "assigned_expert: empty → Ravi",
      "inspection_type: PDI → EV",
    ]);
  });
  it("leaves out what the line already says and rows with no values", () => {
    expect(details({ kind: "changed", changes: { stage: ["assigned", "in_progress"] } })).toEqual([]);
    expect(details({ kind: "key_checks_changed", changes: { "check.a": ["x", "y"] } })).toEqual([]);
    expect(details({ keys: ["customer_name"] })).toEqual([]); // an old row: only the field name was kept
  });
});
