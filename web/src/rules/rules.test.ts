// @vitest-environment node
// Runs the shared cases in /shared/rule-vectors (the Python and Kotlin suites run the same files).
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { evaluate, evaluateForm, type FormSpec } from "./rules";

const load = (name: string) =>
  JSON.parse(readFileSync(new URL(`../../../shared/rule-vectors/${name}`, import.meta.url), "utf8"));

type EvalCase = { name: string; rule: unknown; data: unknown; expected: unknown };
type FormCase = {
  name: string;
  spec: FormSpec;
  answers: Record<string, Record<string, unknown>>;
  today: string;
  overrides: Record<string, unknown>;
  expected: {
    visible?: Record<string, boolean>;
    required?: Record<string, boolean>;
    errors: Record<string, string>;
    derived: Record<string, unknown>;
    defects: string[];
  };
};

const EVAL: EvalCase[] = load("eval_vectors.json");
const FORM: FormCase[] = load("form_vectors.json");
const ROBUST: EvalCase[] = load("robust_vectors.json");

describe("eval vectors", () => {
  it.each(EVAL.map((c) => [c.name, c] as const))("%s", (_, c) => {
    expect(evaluate(c.rule, c.data)).toEqual(c.expected);
  });
});

describe("robust vectors", () => {
  it.each(ROBUST.map((c) => [c.name, c] as const))("%s", (_, c) => {
    expect(evaluate(c.rule, c.data)).toEqual(c.expected);
  });
});

describe("form vectors", () => {
  it.each(FORM.map((c) => [c.name, c] as const))("%s", (_, c) => {
    const r = evaluateForm(c.spec, c.answers, c.today, c.overrides);
    for (const [k, v] of Object.entries(c.expected.visible ?? {})) expect(r.visible[k], `visible[${k}]`).toBe(v);
    for (const [k, v] of Object.entries(c.expected.required ?? {})) expect(r.required[k], `required[${k}]`).toBe(v);
    expect(r.errors).toEqual(c.expected.errors);
    expect(r.derived).toEqual(c.expected.derived);
    expect(r.defects).toEqual(c.expected.defects);
  });
});

it("vector files are substantial", () => {
  expect(EVAL.length).toBeGreaterThanOrEqual(50);
  expect(ROBUST.length).toBeGreaterThanOrEqual(1000);
  expect(FORM.length).toBeGreaterThanOrEqual(60);
});
