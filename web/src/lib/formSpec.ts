// Turns a form tree from the API into what the shared rule engine needs, and answers the
// questions screens ask: what is visible, what is still missing, which page holds it.
import type { FormPage, FormVersion } from "../api/types";
import { evaluateForm, isEmpty, type FieldSpec, type FormSpec, type Result } from "../rules/rules";

/** The name a form's answers go by in rules: the custom form is "inspection". */
export type Kind = "booking" | "start" | "end" | "inspection";
export type Answers = Record<string, unknown>;
export type Ctx = { booking?: Answers; start?: Answers; end?: Answers; inspection?: Answers };

const today = () => new Date().toISOString().slice(0, 10);

export function specFromTree(kind: Kind, tree: Pick<FormVersion, "pages" | "checks">): FormSpec {
  const containers: FormSpec["containers"] = [];
  const fields: FieldSpec[] = [];
  for (const p of tree.pages) {
    containers.push({ id: `p${p.id}`, kind: "page", parent: null, visible: p.visible, show_if: p.show_if });
    for (const s of p.sections) {
      containers.push({ id: `s${s.id}`, kind: "section", parent: `p${p.id}`, visible: s.visible, show_if: s.show_if });
      for (const f of s.fields) {
        fields.push({
          key: f.key, type: f.type, section: `s${s.id}`, visible: f.visible, show_if: f.show_if, required: f.required,
          required_if: f.required_if, options: (f.config.options as FieldSpec["options"]) ?? undefined,
          rule: f.type === "derived" ? f.config.rule : undefined,
        });
      }
    }
  }
  return { form: kind, containers, fields, checks: (tree.checks ?? []).map((c) => ({ rule: c.rule, message: c.message, fields: c.fields })) };
}

/** Evaluate one form given its own answers and the other forms' answers. */
export function evaluateTree(kind: Kind, tree: Pick<FormVersion, "pages" | "checks">, values: Answers, ctx: Ctx = {}): Result {
  return evaluateForm(specFromTree(kind, tree), { booking: ctx.booking, start: ctx.start, end: ctx.end, inspection: ctx.inspection, [kind]: values }, today());
}

export type Gap = { key: string; label: string; page: number; pageTitle: string };

/** Every visible required field that is still empty (system-computed types never count). */
export function missingFields(kind: Kind, tree: Pick<FormVersion, "pages" | "checks">, values: Answers, ctx: Ctx = {}): Gap[] {
  const r = evaluateTree(kind, tree, values, ctx);
  const out: Gap[] = [];
  tree.pages.forEach((p, i) =>
    p.sections.forEach((s) =>
      s.fields.forEach((f) => {
        if (f.type === "derived" || f.type === "rating" || f.type === "image") return;
        if (r.visible[f.key] && r.required[f.key] && isEmpty(values[f.key]))
          out.push({ key: f.key, label: f.label || f.key, page: i, pageTitle: p.title });
      })));
  return out;
}

/** Pages that actually have something to show (not hidden by a rule and not empty of fields). */
export function visiblePages(kind: Kind, tree: Pick<FormVersion, "pages" | "checks">, values: Answers, ctx: Ctx = {}): FormPage[] {
  const r = evaluateTree(kind, tree, values, ctx);
  return tree.pages.filter((p) => p.sections.some((s) => s.fields.some((f) => r.visible[f.key])));
}

/** Only the answers of fields that exist, are visible, and are not system-computed. */
export function submittable(kind: Kind, tree: Pick<FormVersion, "pages" | "checks">, values: Answers, ctx: Ctx = {}): Answers {
  const r = evaluateTree(kind, tree, values, ctx);
  const out: Answers = {};
  for (const p of tree.pages) for (const s of p.sections) for (const f of s.fields) {
    if (f.type === "derived" || f.type === "rating" || f.type === "image") continue;
    const v = values[f.key];
    if (r.visible[f.key] && !isEmpty(v)) out[f.key] = v;
  }
  return out;
}

/** What is still missing on ONE page (the page gate: "finish this before you move on"). */
export function pageGaps(kind: Kind, tree: Pick<FormVersion, "pages" | "checks">, page: FormPage, values: Answers, ctx: Ctx = {}): Gap[] {
  const index = tree.pages.findIndex((p) => p.id === page.id);
  return missingFields(kind, tree, values, ctx).filter((g) => g.page === index);
}
