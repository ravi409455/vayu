// Vayu's form logic on top of JsonLogic. Semantics: /shared/rule-vectors/SCHEMA.md (normative;
// mirrors backend/apps/forms/rules.py and the Kotlin adapter, all proven by the same cases).
import jsonLogic from "json-logic-js";

export const FORMS = ["booking", "ops", "inspection"] as const;
type Values = Record<string, unknown>;

export type Container = {
  id: string;
  kind: "page" | "section";
  parent?: string | null;
  visible?: boolean;
  show_if?: unknown;
};
export type Option = { key: string; label: string; is_defect?: boolean; severity?: string | null };
export type FieldSpec = {
  key: string;
  type: string;
  section: string;
  visible?: boolean;
  show_if?: unknown;
  required?: boolean;
  required_if?: unknown;
  options?: Option[];
  rule?: unknown;
};
export type CheckSpec = { rule: unknown; message: string; fields: string[] };
export type FormSpec = { form: string; containers: Container[]; fields: FieldSpec[]; checks?: CheckSpec[] };
export type Result = {
  visible: Record<string, boolean>;
  required: Record<string, boolean>;
  errors: Record<string, string>;
  derived: Record<string, unknown>;
  defects: string[];
};

const CHOICE = new Set(["single_choice", "multi_choice"]);

/**
 * Never throws: a rule that cannot apply to the data yields null (same as the Python adapter).
 * NaN and Infinity (e.g. "+" on non-numbers) also become null.
 */
export function evaluate(rule: unknown, data: unknown): unknown {
  try {
    const v = jsonLogic.apply(rule as jsonLogic.RulesLogic, data);
    if (v === undefined || (typeof v === "number" && !Number.isFinite(v))) return null;
    return v;
  } catch {
    return null;
  }
}

export function truthy(rule: unknown, data: unknown): boolean {
  if (rule === null || rule === undefined) return true;
  return Boolean(evaluate({ "!!": [rule] }, data));
}

export function isEmpty(v: unknown): boolean {
  if (v === null || v === undefined) return true;
  if (typeof v === "string") return v.trim() === "";
  if (Array.isArray(v)) return v.length === 0;
  if (typeof v === "object") return Object.keys(v as object).length === 0;
  return false;
}

const normalise = (answers: Values = {}): Values =>
  Object.fromEntries(Object.entries(answers).map(([k, v]) => [k, isEmpty(v) ? null : v]));

function isDefect(f: FieldSpec, value: unknown): boolean {
  if (!CHOICE.has(f.type) || value === null) return false;
  const defects = new Set((f.options ?? []).filter((o) => o.is_defect).map((o) => o.key));
  const chosen = Array.isArray(value) ? value : [value];
  return chosen.some((v) => defects.has(v as string));
}

export function evaluateForm(
  spec: FormSpec,
  answers: Record<string, Values | undefined>,
  today: string,
  overrides: Values = {},
): Result {
  const own = spec.form;
  const base: Record<string, Values> = Object.fromEntries(FORMS.map((f) => [f, normalise(answers[f])]));
  const values: Values = Object.fromEntries(spec.fields.map((f) => [f.key, base[own]?.[f.key] ?? null]));
  const containers = new Map(spec.containers.map((c) => [c.id, c]));

  const buildData = (vis: Record<string, boolean>) => {
    const shown = Object.fromEntries(spec.fields.map((f) => [f.key, vis[f.key] ? values[f.key] : null]));
    const defects = spec.fields
      .filter((f) => vis[f.key] && isDefect(f, values[f.key]))
      .map((f) => `${own}.${f.key}`)
      .sort();
    return { ...base, [own]: shown, _today: today, _defects: defects };
  };

  const containerVisible = (cid: string | null | undefined, data: object, memo: Map<string, boolean>): boolean => {
    if (cid === null || cid === undefined) return true;
    const cached = memo.get(cid);
    if (cached !== undefined) return cached;
    const c = containers.get(cid);
    if (!c) throw new Error(`Unknown container ${cid}`);
    const v = (c.visible ?? true) && containerVisible(c.parent, data, memo) && truthy(c.show_if, data);
    memo.set(cid, v);
    return v;
  };

  let visible: Record<string, boolean> = Object.fromEntries(spec.fields.map((f) => [f.key, true]));
  let settled = false;
  for (let i = 0; i < spec.fields.length + spec.containers.length + 2; i++) {
    const data = buildData(visible);
    const memo = new Map<string, boolean>();
    const next = Object.fromEntries(
      spec.fields.map((f) => [
        f.key,
        (f.visible ?? true) && containerVisible(f.section, data, memo) && truthy(f.show_if, data),
      ]),
    );
    if (spec.fields.every((f) => next[f.key] === visible[f.key])) {
      settled = true;
      break;
    }
    visible = next;
  }
  if (!settled) throw new Error("Visibility did not settle: the form has a rule cycle.");

  const data = buildData(visible);
  const derived: Values = {};
  for (const f of spec.fields) {
    if (f.type !== "derived") continue;
    const ov = overrides[f.key];
    derived[f.key] = !visible[f.key] ? null : ov !== null && ov !== undefined ? ov : truthy(f.rule, data);
  }

  const required: Record<string, boolean> = Object.fromEntries(
    spec.fields.map((f) => [
      f.key,
      Boolean(visible[f.key]) &&
        ((f.required ?? false) || (f.required_if !== null && f.required_if !== undefined && truthy(f.required_if, data))),
    ]),
  );
  const errors: Record<string, string> = {};
  for (const f of spec.fields) if (required[f.key] && values[f.key] === null) errors[f.key] = "required";
  for (const check of spec.checks ?? []) {
    const runnable = check.fields.every((k) => visible[k] && values[k] !== null && values[k] !== undefined);
    if (runnable && !truthy(check.rule, data)) for (const k of check.fields) errors[k] ??= "check_failed";
  }
  return { visible, required, errors, derived, defects: data._defects };
}
