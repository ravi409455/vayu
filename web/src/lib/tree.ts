// Dragging in the form builder: pure functions that move a page, section or field and work out
// exactly what the server has to be told (only the containers whose order changed).
import { arrayMove } from "@dnd-kit/sortable";
import type { FormPage } from "../api/types";

export type Ref = { kind: "page" | "section" | "field"; id: number };
export type ReorderBody = { pages?: number[]; sections?: Record<string, number[]>; fields?: Record<string, number[]> };

const clone = (pages: FormPage[]): FormPage[] => pages.map((p) => ({ ...p, sections: p.sections.map((s) => ({ ...s, fields: [...s.fields] })) }));

function findSection(pages: FormPage[], id: number) {
  for (const p of pages) { const i = p.sections.findIndex((s) => s.id === id); if (i >= 0) return { page: p, index: i }; }
  return null;
}
function findField(pages: FormPage[], id: number) {
  for (const p of pages) for (const s of p.sections) { const i = s.fields.findIndex((f) => f.id === id); if (i >= 0) return { section: s, index: i }; }
  return null;
}

/** The pages as they should look after `active` is dropped on `over`. Unknown or meaningless
 *  drops return the pages unchanged. */
export function applyDrag(pages: FormPage[], active: Ref, over: Ref): FormPage[] {
  if (active.kind === over.kind && active.id === over.id) return pages;
  const out = clone(pages);
  if (active.kind === "page") {
    const from = out.findIndex((p) => p.id === active.id);
    const to = over.kind === "page" ? out.findIndex((p) => p.id === over.id) : -1;
    return from < 0 || to < 0 ? pages : arrayMove(out, from, to);
  }
  if (active.kind === "section") {
    const src = findSection(out, active.id);
    if (!src) return pages;
    const [moved] = src.page.sections.splice(src.index, 1);
    let target = over.kind === "page" ? { page: out.find((p) => p.id === over.id)!, index: -1 } : over.kind === "section" ? findSection(out, over.id) : null;
    if (!target || !target.page) { src.page.sections.splice(src.index, 0, moved!); return pages; }
    const at = target.index < 0 ? target.page.sections.length : target.index;
    target.page.sections.splice(at, 0, moved!);
    return out;
  }
  const src = findField(out, active.id);
  if (!src) return pages;
  const [moved] = src.section.fields.splice(src.index, 1);
  const target = over.kind === "section"
    ? { section: out.flatMap((p) => p.sections).find((s) => s.id === over.id)!, index: -1 }
    : over.kind === "field" ? findField(out, over.id) : null;
  if (!target || !target.section) { src.section.fields.splice(src.index, 0, moved!); return pages; }
  target.section.fields.splice(target.index < 0 ? target.section.fields.length : target.index, 0, moved!);
  return out;
}

const ids = <T extends { id: number }>(xs: T[]) => xs.map((x) => x.id);
const same = (a: number[], b: number[]) => a.length === b.length && a.every((v, i) => v === b[i]);

/** What changed between two arrangements, in the shape of POST form-versions/<id>/reorder. */
export function reorderBody(before: FormPage[], after: FormPage[]): ReorderBody {
  const body: ReorderBody = {};
  if (!same(ids(before), ids(after))) body.pages = ids(after);
  const beforeSections = new Map(before.map((p) => [p.id, ids(p.sections)]));
  const beforeFields = new Map(before.flatMap((p) => p.sections).map((s) => [s.id, ids(s.fields)]));
  for (const p of after) {
    if (!same(beforeSections.get(p.id) ?? [], ids(p.sections))) (body.sections ??= {})[String(p.id)] = ids(p.sections);
    for (const s of p.sections) if (!same(beforeFields.get(s.id) ?? [], ids(s.fields))) (body.fields ??= {})[String(s.id)] = ids(s.fields);
  }
  return body;
}
export const isEmptyBody = (b: ReorderBody) => !b.pages && !b.sections && !b.fields;
