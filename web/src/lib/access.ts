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
