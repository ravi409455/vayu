import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { api } from "../api/client";
import { fetchAll } from "../api/hooks";
import { useLabels, useTypeLabels } from "../api/labels";
import type { FormField, FormPage, FormSection, FormVersion, Option, User } from "../api/types";
import { evaluateTree, type Answers, type Ctx, type Kind } from "../lib/formSpec";
import { fmtDay, fmtPhone, fmtStamp, fmtTime, mapsUrl } from "../lib/format";
import { Thumb } from "./MediaThumb";
import { MEDIA_TYPES, NOT_ASKED_TYPES } from "../lib/fieldTypes";
import { isEmpty } from "../rules/rules";

export type SheetFilter = "all" | "defects" | "edited" | "empty";
const SKIP = NOT_ASKED_TYPES;          // shown on the Ratings tab, or nothing to read

/** Is this answer a defect, and how bad? (choices marked as a defect by the Admin) */
export function defectOf(f: FormField, v: unknown): string | null {
  const opts = (f.config.options as Option[] | undefined) ?? [];
  const picked = f.type === "single_choice" ? [v] : f.type === "multi_choice" && Array.isArray(v) ? v : [];
  const bad = opts.filter((o) => o.is_defect && picked.includes(o.key));
  if (bad.length === 0) return null;
  return bad.some((o) => o.severity === "major") ? "Major" : bad[0]!.severity === "minor" ? "Minor" : "Defect";
}

/** The fields of a tree a reader sees (visible by the rules, not automatic, not a picture). */
export function readableFields(kind: Kind, tree: Pick<FormVersion, "pages" | "checks">, values: Answers, ctx?: Ctx) {
  const visible = evaluateTree(kind, tree, values, ctx).visible;
  return tree.pages.flatMap((p) => p.sections.flatMap((s) => s.fields.filter((f) => visible[f.key] && !SKIP.includes(f.type)).map((f) => ({ page: p, section: s, f }))));
}

function ListLabel({ list, value }: { list: string; value: unknown }) {
  const label = useLabels(list);
  return <>{(Array.isArray(value) ? value : [value]).map(label).join(", ")}</>;
}

function UserName({ role, id }: { role: string; id: unknown }) {
  const q = useQuery({ queryKey: ["users-by-role", role], retry: false, staleTime: 300_000, queryFn: ({ signal }) => fetchAll<User>("users", { role }, signal) });
  const u = q.data?.find((x) => x.id === id);
  return <>{u ? u.name || u.username : `#${String(id)}`}</>;
}

/** One answer, as a person reads it. */
function TypeName({ v }: { v: unknown }) {
  return <>{useTypeLabels()(v)}</>;
}

/** Names the Admin never changed ("Page 1", "Section 1") say nothing to a reader. */
export const generic = (title: string) => /^(page|section)\s*\d+$/i.test(title.trim());

export function AnswerValue({ f, v }: { f: FormField; v: unknown }) {
  if (isEmpty(v)) return <span className="muted">Not answered</span>;
  if (f.key === "inspection_type") return <TypeName v={v} />;
  const opts = (f.config.options as Option[] | undefined) ?? [];
  const opt = (k: unknown) => opts.find((o) => o.key === k)?.label ?? String(k);
  switch (f.type) {
    case "single_choice": return <>{opt(v)}</>;
    case "multi_choice": return <>{(v as unknown[]).map(opt).join(", ")}</>;
    case "yes_no": return <>{v ? "Yes" : "No"}</>;
    case "number": return <>{String(v)}{f.config.unit ? ` ${String(f.config.unit)}` : ""}</>;
    case "currency": return <>₹{Number(v).toLocaleString("en-IN")}</>;
    case "date": return <>{fmtDay(v)}</>;
    case "time": return <>{fmtTime(v)}</>;
    case "datetime": return <>{fmtStamp(v)}</>;
    case "phone": return <>{fmtPhone(v)}</>;
    case "master_list": return <ListLabel list={String(f.config.list ?? "")} value={v} />;
    case "user_picker": return <UserName role={String(f.config.role ?? "expert")} id={v} />;
    case "gps": {
      const g = v as { lat: number; lng: number };
      return <a href={mapsUrl(`${g.lat},${g.lng}`)} target="_blank" rel="noreferrer">Open in Maps</a>;
    }
    default:
      if (MEDIA_TYPES.includes(f.type)) {
        const ids = Array.isArray(v) ? (v as string[]) : [String(v)];
        return (
          <span className="sheet-thumbs">
            {ids.slice(0, 4).map((id) => <Thumb key={id} id={id} video={f.type === "video"} size={48} />)}
            {ids.length > 4 && <span className="muted small">+{ids.length - 4}</span>}
            {f.type !== "photo" && f.type !== "video" && <span className="muted small">{ids.length} {f.type === "signature" ? "signature" : "file"}{ids.length > 1 ? "s" : ""}</span>}
          </span>
        );
      }
      return <>{String(v)}</>;
  }
}

export type SheetPart = { kind: Kind; tree: Pick<FormVersion, "pages" | "checks">; values: Answers; ctx?: Ctx };

/** A form's answers to read, not to fill in: per section, two columns of label and answer, defects
 *  marked, filters, and an Edit button that swaps one section for its inputs. */
export function AnswerSheet({ part, filter = "all", edited, onEdit, editing, anchor }: {
  part: SheetPart; filter?: SheetFilter; edited?: Set<string>;
  onEdit?: (page: FormPage, section: FormSection) => void;
  editing?: { sectionId: number; node: ReactNode } | null;
  anchor?: (page: FormPage) => string;
}) {
  const rows = readableFields(part.kind, part.tree, part.values, part.ctx);
  const keep = (f: FormField) => {
    const v = part.values[f.key];
    if (filter === "defects") return !!defectOf(f, v);
    if (filter === "edited") return !!edited?.has(f.key);
    if (filter === "empty") return isEmpty(v);
    return true;
  };
  const pages = part.tree.pages.map((p) => ({
    page: p,
    sections: p.sections.map((s) => ({ s, fields: rows.filter((r) => r.section.id === s.id && keep(r.f)).map((r) => r.f) }))
      .filter((x) => x.fields.length > 0 || editing?.sectionId === x.s.id),
  })).filter((x) => x.sections.length > 0);
  if (pages.length === 0) return null;
  return (
    <>
      {pages.map(({ page, sections }) => (
        <div key={page.id} id={anchor?.(page)} className="sheet-page">
          {sections.map(({ s, fields }) => {
            const all = rows.filter((r) => r.section.id === s.id).map((r) => r.f);
            const answered = all.filter((f) => !isEmpty(part.values[f.key])).length;
            const defects = all.filter((f) => defectOf(f, part.values[f.key])).length;
            const isEditing = editing?.sectionId === s.id;
            return (
              <section className="card sheet" key={s.id} aria-label={s.title}>
                <div className="sheet-head">
                  <h3>{generic(s.title) ? (generic(page.title) ? "Details" : page.title) : s.title}{!generic(page.title) && !generic(s.title) && s.title !== page.title && <span className="muted"> · {page.title}</span>}</h3>
                  <span className="muted small">{answered} of {all.length} answered{defects ? ` · ${defects} defect${defects > 1 ? "s" : ""}` : ""}</span>
                  {onEdit && !isEditing && <button className="sm" onClick={() => onEdit(page, s)}>Edit</button>}
                </div>
                {isEditing ? <div className="sheet-edit">{editing!.node}</div> : (
                  <div className="sheet-grid">
                    {fields.map((f) => {
                      const v = part.values[f.key];
                      const sev = defectOf(f, v);
                      const changed = edited?.has(f.key);
                      return (
                        <div key={f.key} className={`sheet-row${sev ? " defect" : ""}${changed ? " edited" : ""}`}>
                          <div className="sheet-label">{f.label || f.key}</div>
                          <div className="sheet-value">
                            <AnswerValue f={f} v={v} />
                            {sev && <span className="pill bad">{sev}</span>}
                            {changed && <span className="pill">Edited by Ops</span>}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </section>
            );
          })}
        </div>
      ))}
    </>
  );
}
