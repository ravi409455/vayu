import { evaluateTree, type Answers, type Ctx, type Kind } from "../lib/formSpec";
import type { FormField, FormPage, FormVersion } from "../api/types";
import { FieldInput } from "./FieldInputs";

export { INPUTS, nowAs } from "./FieldInputs";

export type RenderProps = {
  kind: Kind;
  tree: Pick<FormVersion, "pages" | "checks">;
  values: Answers;
  ctx?: Ctx;
  onChange: (key: string, value: unknown) => void;
  errors?: Record<string, string>;
  readOnly?: boolean;
  readOnlyKeys?: string[];            // fields changed only through their own action (expert, type)
  role?: string;
  bookingId?: string;                 // needed for photo / video / file fields
  preview?: boolean;                  // the builder's preview: nothing is uploaded or located
  pages?: FormPage[];                 // render only these pages (the wizard shows one at a time)
  mediaUrl?: (id: string) => Promise<{ url: string; preview_url: string | null; removed?: boolean } | null>;
  onMediaRemove?: (field: FormField, id: string) => void;
  mediaEditor?: (field: FormField, ids: string[]) => React.ReactNode;   // Ops: their own Replace / Add
};

/** Draws a form tree: only what is visible, with the right input for each type, and the
 *  access level the server assigned (view = read-only). Ratings and Key Checks never show to experts. */
export function FormRenderer(p: RenderProps) {
  const result = evaluateTree(p.kind, p.tree, p.values, p.ctx);
  const pages = p.pages ?? p.tree.pages;
  // one page / one section: their names ("Page 1", "Section 1") say nothing, so they are not shown
  const onePage = p.tree.pages.length === 1, oneSection = onePage && p.tree.pages[0]!.sections.length === 1;
  return (
    <div>
      {pages.map((page) => (
        <div key={page.id}>
          {p.pages === undefined && !onePage && <h2>{page.title}</h2>}
          {page.sections.map((s) => {
            const fields = s.fields.filter((f) => result.visible[f.key] && !(p.role === "expert" && (f.type === "derived" || f.type === "rating")));
            if (fields.length === 0) return null;
            return (
              <section className="card" key={s.id} aria-label={s.title}>
                {!oneSection && <h3 style={{ marginTop: 0 }}>{s.title}</h3>}
                {fields.map((f) => (
                  <FieldInput key={f.id} f={f} value={p.values[f.key]} derived={result.derived[f.key]} required={!!result.required[f.key]}
                    error={p.errors?.[f.key]} readOnly={p.readOnly || p.readOnlyKeys?.includes(f.key) || f.level === "view" || f.type === "derived" || f.type === "rating"}
                    onChange={(v) => p.onChange(f.key, v)} p={p} />
                ))}
              </section>
            );
          })}
        </div>
      ))}
    </div>
  );
}

