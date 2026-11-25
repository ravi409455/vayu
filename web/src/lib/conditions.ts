// The condition builder's model <-> JsonLogic. Only shapes the builder can draw round-trip;
// anything else is kept as raw JSON ("advanced") so nothing an Admin wrote is ever lost.
export const OPS = [
  { id: "==", label: "is" },
  { id: "!=", label: "is not" },
  { id: ">", label: "is greater than" },
  { id: ">=", label: "is at least" },
  { id: "<", label: "is less than" },
  { id: "<=", label: "is at most" },
  { id: "in", label: "is one of" },
  { id: "filled", label: "is filled in" },
  { id: "empty", label: "is empty" },
] as const;
export type OpId = (typeof OPS)[number]["id"];
export type Row = { field: string; op: OpId; value: string };
export type Cond = { join: "and" | "or"; rows: Row[] };

const COMPARE = new Set(["==", "!=", ">", ">=", "<", "<="]);

/** "12" -> 12, "true" -> true, anything else stays text. Choice keys are text, numbers are numbers. */
export function parseValue(s: string): string | number | boolean {
  const t = s.trim();
  if (t === "true") return true;
  if (t === "false") return false;
  if (t !== "" && !isNaN(Number(t)) && /^-?\d+(\.\d+)?$/.test(t)) return Number(t);
  return s;
}

function rowRule(r: Row): unknown {
  const v = { var: r.field };
  if (r.op === "filled") return { "!!": [v] };
  if (r.op === "empty") return { "!": [v] };
  if (r.op === "in")
    return {
      in: [
        v,
        r.value
          .split(",")
          .map((x) => parseValue(x.trim()))
          .filter((x) => x !== ""),
      ],
    };
  return { [r.op]: [v, parseValue(r.value)] };
}

/** No rows -> null (meaning "always"). One row needs no and/or wrapper. */
export function toRule(c: Cond): unknown {
  const rows = c.rows.filter((r) => r.field && (r.op === "filled" || r.op === "empty" || r.value !== ""));
  if (rows.length === 0) return null;
  const rules = rows.map(rowRule);
  return rules.length === 1 ? rules[0] : { [c.join]: rules };
}

function show(v: unknown): string {
  return Array.isArray(v) ? v.join(", ") : String(v);
}

function rowFrom(rule: unknown): Row | null {
  if (!rule || typeof rule !== "object" || Array.isArray(rule)) return null;
  const entries = Object.entries(rule as Record<string, unknown>);
  if (entries.length !== 1) return null;
  const [op, args] = entries[0] as [string, unknown];
  if (op === "!!" || op === "!") {
    const a = Array.isArray(args) ? args : [args];
    const v = a[0] as { var?: unknown } | undefined;
    if (a.length === 1 && v && typeof v.var === "string") return { field: v.var, op: op === "!!" ? "filled" : "empty", value: "" };
    return null;
  }
  if (!Array.isArray(args) || args.length !== 2) return null;
  const [left, right] = args as [{ var?: unknown } | undefined, unknown];
  if (!left || typeof left !== "object" || typeof left.var !== "string") return null;
  if (op === "in" && Array.isArray(right) && right.every((x) => typeof x !== "object" || x === null))
    return { field: left.var, op: "in", value: show(right) };
  if (COMPARE.has(op) && (typeof right !== "object" || right === null))
    return { field: left.var, op: op as OpId, value: right === null ? "" : show(right) };
  return null;
}

/** null when the rule is too fancy for the builder (use raw JSON), a Cond otherwise. */
export function fromRule(rule: unknown): Cond | null {
  if (rule === null || rule === undefined) return { join: "and", rows: [] };
  const one = rowFrom(rule);
  if (one) return { join: "and", rows: [one] };
  if (typeof rule !== "object" || Array.isArray(rule)) return null;
  const entries = Object.entries(rule as Record<string, unknown>);
  const [join, list] = entries[0] ?? [];
  if (entries.length !== 1 || (join !== "and" && join !== "or") || !Array.isArray(list) || list.length === 0) return null;
  const rows = list.map(rowFrom);
  if (rows.some((r) => r === null)) return null;
  return { join, rows: rows as Row[] };
}
