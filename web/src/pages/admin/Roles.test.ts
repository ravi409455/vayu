import { afterEach, describe, expect, it, vi } from "vitest";
import { visibleNav } from "../../Layout";
import { OPS_NOT_ON_WEB } from "./Roles";

afterEach(() => vi.restoreAllMocks());

describe("the Roles screen offers Ops only what the web shows them (F-224)", () => {
  it("no page in the Ops menu depends on a permission the screen hides from Ops", () => {
    const opsPerms = visibleNav("ops", () => true).flatMap((g) => g.items.map((i) => i.perm)).filter(Boolean) as string[];
    expect(opsPerms.filter((p) => OPS_NOT_ON_WEB.has(p))).toEqual([]);
    expect(OPS_NOT_ON_WEB.has("api_keys.manage") && OPS_NOT_ON_WEB.has("integrations.manage")).toBe(true);
  });
});
