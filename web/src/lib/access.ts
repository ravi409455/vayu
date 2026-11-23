// The access matrix editor: per role (expert, ops) and booking stage, hidden / view / edit, or
// "inherit" (not set at this level, so the section/page/default decides).
import type { Access } from "../api/types";

export const ROLES = ["expert", "ops"] as const;
export const STAGES = ["draft", "assigned", "in_progress", "submitted", "completed", "cancelled"] as const;
export type Level = "hidden" | "view" | "edit";
export const LEVELS: Level[] = ["hidden", "view", "edit"];

export function getCell(a: Access, role: string, stage: string): Level | "" {
  return a?.[role]?.[stage] ?? "";
}

/** A new matrix with one cell changed; "" removes it, and empty roles disappear. */
export function setCell(a: Access, role: string, stage: string, level: Level | ""): Access {
  const out: Access = {};
  for (const [r, stages] of Object.entries(a ?? {})) out[r] = { ...stages };
  if (level === "") {
    if (out[role]) {
      delete out[role][stage];
      if (Object.keys(out[role]).length === 0) delete out[role];
    }
    return out;
  }
  out[role] = { ...(out[role] ?? {}), [stage]: level };
  return out;
}

/** Set a whole row (one role, every stage) at once. */
export function setRole(a: Access, role: string, level: Level | ""): Access {
  return STAGES.reduce((acc, s) => setCell(acc, role, s, level), a);
}

export function isEmpty(a: Access): boolean {
  return Object.keys(a ?? {}).length === 0;
}

export type LevelSource = "field" | "section" | "page" | "default";
const SYSTEM_FILLED = ["derived", "rating"];

/** What applies when no field, section or page says anything (mirrors the server's policy). */
export function defaultLevel(role: string, stage: string, kind: string, ftype: string): Level {
  const system = SYSTEM_FILLED.includes(ftype);
  if (role === "admin") return "edit";
  if (role === "ops") return system ? "view" : "edit";
  if (system) return "hidden";
  if (kind === "booking") return ["assigned", "in_progress", "submitted", "completed"].includes(stage) ? "view" : "hidden";
  if (stage === "in_progress") return "edit";
  return stage === "submitted" || stage === "completed" ? "view" : "hidden";
}

/** The level a person gets at a stage, and which layer decided it (the most specific one wins). */
export function effectiveLevel(
  role: string, stage: string, kind: string, ftype: string, layers: { field?: Access; section?: Access; page?: Access },
): { level: Level; source: LevelSource } {
  const order: [LevelSource, Access | undefined][] = [["field", layers.field], ["section", layers.section], ["page", layers.page]];
  for (const [source, a] of order) {
    const l = a?.[role]?.[stage];
    if (l && !(role === "expert" && SYSTEM_FILLED.includes(ftype))) return { level: l, source };
  }
  return { level: defaultLevel(role, stage, kind, ftype), source: "default" };
}

/** Ready-made access patterns, so nobody has to fill twelve cells by hand. */
export const PRESETS: { id: string; label: string; tip: string; apply: () => Access | null }[] = [
  { id: "default", label: "Standard", tip: "Experts fill it while working and can read it afterwards. Ops can always edit.", apply: () => ({}) },
  { id: "ops_only", label: "Ops only", tip: "Experts never see it. Ops and Admin can edit it.", apply: () => setRole({}, "expert", "hidden") },
  { id: "expert_readonly", label: "Read-only for experts", tip: "Experts can see it but not change it.", apply: () => setRole({}, "expert", "view") },
  { id: "locked_after_submit", label: "Lock after submit", tip: "Experts edit while working; after they submit nobody but Ops can change it.",
    apply: () => setCell(setCell(setCell({}, "expert", "submitted", "view"), "expert", "completed", "view"), "expert", "in_progress", "edit") },
];
