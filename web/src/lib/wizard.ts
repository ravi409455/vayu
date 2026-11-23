// The expert's steps: the start form's pages (when the inspection is pinned to one), then the
// custom form's pages, then the end form's pages, then the review. A form with nothing visible is
// skipped. Pure, so the order and the skipping can be tested without a browser.
import type { FormPage, FormVersion } from "../api/types";
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
    for (const p of visiblePages(part, tree, answers[part], ctx)) out.push({ id: `${part[0]}${p.id}`, title: p.title, kind: part, page: p });
  }
  out.push({ id: "review", title: "Review", kind: "review" });
  return out;
}
