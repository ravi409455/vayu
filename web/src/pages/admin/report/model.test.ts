import { describe, expect, it } from "vitest";
import { slugKey } from "../../../lib/fieldTypes";
import { freshCopies, pageOf, partNames, withIds, withoutIds, type Definition } from "./model";
import { keyOf } from "./sharing";

const def = (): Definition =>
  withIds({
    schema: 2,
    pages: [
      {
        title: "One",
        parts: [
          { type: "text", html: "Hello" },
          { type: "columns", columns: [{ parts: [{ type: "text", html: "Inner" }] }] },
        ] as never,
      },
      { title: "Two", parts: [] },
    ],
  });

describe("report designer helpers, one copy each (F-016)", () => {
  it("copies get fresh ids and keep everything else", () => {
    const d = def();
    const [copy] = freshCopies([d.pages[0]!.parts[0]!]);
    expect(copy!.id).toBeTruthy();
    expect(copy!.id).not.toBe(d.pages[0]!.parts[0]!.id);
    expect(withoutIds(copy)).toEqual(withoutIds(d.pages[0]!.parts[0]));
  });
  it("finds a part's page, also inside columns, and names every part", () => {
    const d = def();
    const inner = (d.pages[0]!.parts[1] as Extract<(typeof d.pages)[0]["parts"][number], { type: "columns" }>).columns[0]!.parts[0]!;
    expect(pageOf(d, inner.id!)?.title).toBe("One");
    expect(partNames(d)[inner.id!]).toBe("Inner");
  });
  it("shared-item keys are slug keys with their own prefix and length", () => {
    expect(keyOf("Car C.I.D. theme")).toBe("car_c_i_d_theme");
    expect(keyOf("1st look")).toBe("x_1st_look");
    expect(keyOf("a".repeat(80))).toHaveLength(60);
    expect(slugKey("1st look")).toBe("f_1st_look");
  });
});
