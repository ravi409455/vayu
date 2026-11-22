// Rules must never throw: odd data gives a falsy result (mirrors test_rule_robustness.py).
import { describe, expect, it } from "vitest";
import { evaluate, truthy } from "./rules";

const VALUES = [null, true, false, 0, 1, 2.5, "", "abc", "2026-10-14", ["a", "b"], [], { a: 1 }];
const BINARY = ["==", "!=", "===", "!==", "<", "<=", ">", ">=", "in", "+"];
const ITERATING = ["some", "all", "none", "filter", "reduce"];

describe("rules never throw", () => {
  it.each(BINARY)("binary %s", (op) => {
    for (const a of VALUES) for (const b of VALUES) {
      expect(() => evaluate({ [op]: [{ var: "x" }, { var: "y" }] }, { x: a, y: b })).not.toThrow();
    }
  });
  it.each(["!", "!!"])("unary %s", (op) => {
    for (const a of VALUES) expect(() => evaluate({ [op]: [{ var: "x" }] }, { x: a })).not.toThrow();
  });
  it.each(ITERATING)("iterating %s", (op) => {
    for (const a of VALUES) {
      const rule =
        op === "reduce"
          ? { reduce: [{ var: "x" }, { "+": [{ var: "current" }, { var: "accumulator" }] }, 0] }
          : { [op]: [{ var: "x" }, { in: [{ var: "" }, ["a", "b"]] }] };
      expect(() => evaluate(rule, { x: a })).not.toThrow();
    }
  });
  it("a rule that cannot apply is falsy, not an error", () => {
    const rule = { in: ["x", { var: "n" }] };
    expect(truthy(rule, { n: 5 })).toBe(false);
  });
});
