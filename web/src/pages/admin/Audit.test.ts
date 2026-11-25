import { describe, expect, it } from "vitest";

describe("audit log links", () => {
  it("opens what an entry is about, and nothing for deleted things", async () => {
    const { targetLink } = await import("./Audit");
    expect(targetLink({ target_type: "booking", target_id: "b1", action: "booking.force_release" })).toBe("/booking/b1");
    expect(targetLink({ target_type: "booking", target_id: "b1", action: "booking.delete" })).toBeNull();
    expect(targetLink({ target_type: "library_item", target_id: "7", action: "library.update" })).toBe("/library/7");
    expect(targetLink({ target_type: "form_version", target_id: "3", action: "form.publish" })).toBe("/forms");
    expect(targetLink({ target_type: "something_new", target_id: "1", action: "x.y" })).toBeNull();
  });
});
