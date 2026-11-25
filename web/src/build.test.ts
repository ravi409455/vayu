// @vitest-environment node
import { describe, expect, it } from "vitest";
import config from "../vite.config";

describe("the production build (R-21)", () => {
  it("publishes no source maps", () => {
    expect((config as { build?: { sourcemap?: unknown } }).build?.sourcemap).toBe(false);
  });
});
