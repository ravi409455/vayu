// The expert's steps: the start form's pages (when the inspection is pinned to one), then the
// custom form's pages, then the end form's pages, then the review. A form with nothing visible is
// skipped. Pure, so the order and the skipping can be tested without a browser.
import type { FormPage, FormVersion } from "../api/types";
import { maxFiles, MEDIA_TYPES } from "./fieldTypes";
import { visiblePages, type Answers, type Ctx } from "./formSpec";

export type Part = "start" | "inspection" | "end";
export type Tree = Pick<FormVersion, "pages" | "checks"> & { id: number };
export type Trees = { start: Tree | null; inspection: Tree; end: Tree | null };
export type Step = { id: string; title: string; kind: Part | "review"; page?: FormPage };

export function wizardSteps(trees: Trees, answers: Record<Part, Answers>, ctx: Ctx): Step[] {
  const out: Step[] = [];
  for (const part of ["start", "inspection", "end"] as const) {
    const tree = trees[part];
    if (!tree) continue;
    for (const p of visiblePages(part, tree, answers[part], ctx))
      out.push({ id: `${part[0]}${p.id}`, title: p.title, kind: part, page: p });
  }
  out.push({ id: "review", title: "Review", kind: "review" });
  return out;
}

/** Steps the expert may open now. Any order is fine, except that a page the Admin marked "must be
 *  finished before moving on" holds everything after it until its required fields are filled.
 *  Returns the index of the first step that is locked (steps.length when nothing is). */
export function lockedFrom(steps: Step[], missingOn: (s: Step) => number): number {
  const gate = steps.findIndex((s) => s.kind !== "review" && s.page?.gate && missingOn(s) > 0);
  return gate === -1 ? steps.length : gate + 1;
}

/** Pages the expert has not opened yet (the review is not a page). */
export function unvisited(steps: Step[], visited: string[]): Step[] {
  const seen = new Set(visited);
  return steps.filter((s) => s.kind !== "review" && !seen.has(s.id));
}

/** A file the server holds for this job (from `bookings/{id}/media`). */
export type ServerMedia = { id: string; field_key: string; kind: string; status: string };
export type MediaAdd = { part: Part; key: string; id: string; single: boolean };

/** A phone that lost its draft (another device, cleared storage) must not lose the files already
 *  on the server: finished files go back into the answers. Files that have not finished are left
 *  alone: another device or tab may still be sending them (the server's stuck-upload check reports
 *  the ones that never arrive). */
export function reconcileMedia(
  trees: Trees,
  answers: Record<Part, Answers>,
  server: ServerMedia[],
  tracked: (id: string) => boolean,
): { add: MediaAdd[] } {
  const fields = new Map<string, { part: Part; type: string; max: number }>();
  for (const part of ["start", "inspection", "end"] as const)
    for (const p of trees[part]?.pages ?? [])
      for (const s of p.sections)
        for (const f of s.fields) if (MEDIA_TYPES.includes(f.type)) fields.set(f.key, { part, type: f.type, max: maxFiles(f) });
  const used = new Set<string>();
  for (const part of ["start", "inspection", "end"] as const)
    for (const v of Object.values(answers[part] ?? {}))
      for (const id of Array.isArray(v) ? v : [v]) if (typeof id === "string") used.add(id);
  const room = new Map<string, number>();
  const add: MediaAdd[] = [];
  for (const m of server) {
    const f = fields.get(m.field_key);
    if (!f || used.has(m.id) || tracked(m.id) || (m.status !== "uploaded" && m.status !== "verified")) continue;
    const have =
      room.get(m.field_key) ??
      (() => {
        const v = answers[f.part]?.[m.field_key];
        return Array.isArray(v) ? v.length : v ? 1 : 0;
      })();
    if (have >= f.max) continue;
    room.set(m.field_key, have + 1);
    add.push({ part: f.part, key: m.field_key, id: m.id, single: f.type === "signature" });
  }
  return { add };
}

export function applyMedia<T extends Record<Part, Answers>>(draft: T, add: MediaAdd[]): T {
  const out: Record<string, Answers> = { ...draft };
  for (const a of add) {
    const cur = out[a.part]![a.key];
    if (a.single) out[a.part] = { ...out[a.part], [a.key]: a.id };
    else out[a.part] = { ...out[a.part], [a.key]: [...(Array.isArray(cur) ? (cur as string[]) : []), a.id] };
  }
  return out as T;
}
