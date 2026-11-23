import { describe, expect, it } from "vitest";
import { evaluate } from "../rules/rules";
import { fromRule, parseValue, toRule, type Cond } from "./conditions";

const data = { inspection: { door: "dent", odometer: 120, tags: "a" }, booking: {}, _today: "2026-01-01", _defects: [] };

describe("condition builder emits JsonLogic", () => {
  it("one row needs no wrapper", () => {
    const rule = toRule({ join: "and", rows: [{ field: "inspection.door", op: "==", value: "dent" }] });
    expect(rule).toEqual({ "==": [{ var: "inspection.door" }, "dent"] });
    expect(evaluate(rule, data)).toBe(true);
  });
  it("several rows join with and / or", () => {
    const rows: Cond["rows"] = [
      { field: "inspection.door", op: "==", value: "ok" },
      { field: "inspection.odometer", op: ">", value: "100" },
    ];
    expect(evaluate(toRule({ join: "and", rows }), data)).toBe(false);
    expect(evaluate(toRule({ join: "or", rows }), data)).toBe(true);
  });
  it("numbers stay numbers and booleans stay booleans", () => {
    expect(parseValue("100")).toBe(100);
    expect(parseValue("-2.5")).toBe(-2.5);
    expect(parseValue("true")).toBe(true);
    expect(parseValue("MA3Y")).toBe("MA3Y");
    expect(parseValue("007x")).toBe("007x");
  });
  it("is one of, filled and empty", () => {
    expect(evaluate(toRule({ join: "and", rows: [{ field: "inspection.door", op: "in", value: "dent, scratch" }] }), data)).toBe(true);
    expect(evaluate(toRule({ join: "and", rows: [{ field: "inspection.door", op: "filled", value: "" }] }), data)).toBe(true);
    expect(evaluate(toRule({ join: "and", rows: [{ field: "inspection.missing", op: "empty", value: "" }] }), data)).toBe(true);
  });
  it("an unfinished row is ignored and no rows means always", () => {
    expect(toRule({ join: "and", rows: [{ field: "", op: "==", value: "x" }, { field: "a.b", op: "==", value: "" }] })).toBeNull();
  });
});

describe("round trip", () => {
  const cases: Cond[] = [
    { join: "and", rows: [] },
    { join: "and", rows: [{ field: "inspection.door", op: "==", value: "dent" }] },
    { join: "or", rows: [{ field: "inspection.door", op: "!=", value: "ok" }, { field: "inspection.odometer", op: "<=", value: "50" }] },
    { join: "and", rows: [{ field: "booking.city", op: "in", value: "delhi, pune" }, { field: "inspection.door", op: "filled", value: "" }, { field: "ops.x", op: "empty", value: "" }] },
  ];
  for (const c of cases) it(JSON.stringify(c), () => expect(fromRule(toRule(c))).toEqual(c));
  it("keeps what it cannot draw as raw JSON (null)", () => {
    expect(fromRule({ some: [{ var: "_defects" }, { in: [{ var: "" }, ["a"]] }] })).toBeNull();
    expect(fromRule({ and: [{ "==": [{ var: "a.b" }, 1] }, { some: [1] }] })).toBeNull();
    expect(fromRule({ "==": [1, 2] })).toBeNull();
    expect(fromRule({ "==": [{ var: "a.b" }, { var: "c.d" }] })).toBeNull();
    expect(fromRule([1])).toBeNull();
    expect(fromRule({ and: [] })).toBeNull();
    expect(fromRule({ a: 1, b: 2 })).toBeNull();
    expect(fromRule({ "!!": [1] })).toBeNull();
  });
});
