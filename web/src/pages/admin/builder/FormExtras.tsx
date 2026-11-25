import { useState } from "react";
import { api } from "../../../api/client";
import type { FormVersion, RatingConfig } from "../../../api/types";
import { Field } from "../../../ui/kit";
import { slugKey } from "../../../lib/fieldTypes";

const DEFAULT_RATING: RatingConfig = { categories: [], deductions: { minor: 0.25, major: 1, critical: 3 }, thresholds: { excellent: 4.5, good: 3.5, average: 2.5 } };

/** A section a category can count: stored by its key (F-045), shown by its title. */
export type RatedSection = { key: string; title: string };

export function Ratings({ version, sections, edit, run }: { version: FormVersion; sections: RatedSection[]; edit: boolean; run: (fn: () => Promise<unknown>) => void }) {
  const [cfg, setCfg] = useState<RatingConfig>({ ...DEFAULT_RATING, ...(version.rating_config ?? {}) });
  const cats = cfg.categories ?? [];
  const setCat = (i: number, p: Partial<NonNullable<RatingConfig["categories"]>[number]>) => setCfg({ ...cfg, categories: cats.map((c, j) => (j === i ? { ...c, ...p } : c)) });
  return (
    <>
      <p className="muted">Each category starts at 5. Every defect deducts points by severity (minimum 1). The overall rating is the average; a Critical defect caps it at “Average”. Experts never see any of this.</p>
      {cats.map((c, i) => (
        <div className="card" key={i}>
          <div className="grid2">
            <Field label="Category label"><input value={c.label} disabled={!edit} onChange={(e) => setCat(i, { label: e.target.value, key: c.key || slugKey(e.target.value) })} /></Field>
            <Field label="Key"><input value={c.key} disabled={!edit} onChange={(e) => setCat(i, { key: e.target.value })} /></Field>
          </div>
          <div className="field"><span className="label-row">Sections counted in this category</span>
            <div className="chip-row" role="group" aria-label={`Sections counted in ${c.label || "this category"}`}>
              {sections.map((s) => {
                // the server stores keys; a config saved before F-045 may still name the title
                const on = c.sections.includes(s.key) || c.sections.includes(s.title);
                return (
                  <button key={s.key} type="button" className="chip-toggle" aria-pressed={on} disabled={!edit}
                    onClick={() => setCat(i, { sections: on ? c.sections.filter((x) => x !== s.key && x !== s.title) : [...c.sections, s.key] })}>
                    {on ? "✓ " : ""}{s.title}</button>); })}
            </div>
            <span className="help">{c.sections.length ? `${c.sections.length} section${c.sections.length === 1 ? "" : "s"}` : "Pick the sections whose defects count here."}</span></div>
          {edit && <button className="link" onClick={() => setCfg({ ...cfg, categories: cats.filter((_, j) => j !== i) })}>Remove category</button>}
        </div>
      ))}
      {edit && <button onClick={() => setCfg({ ...cfg, categories: [...cats, { key: "", label: "", sections: [] }] })}>+ Add category</button>}
      <h3>Points taken off per defect</h3>
      <div className="grid2">
        {(["minor", "major", "critical"] as const).map((k) => (
          <Field key={k} label={k[0]!.toUpperCase() + k.slice(1)}><input type="number" step="0.25" disabled={!edit} value={cfg.deductions?.[k] ?? 0} onChange={(e) => setCfg({ ...cfg, deductions: { ...DEFAULT_RATING.deductions!, ...cfg.deductions, [k]: Number(e.target.value) } })} /></Field>))}
      </div>
      <h3>Overall word cut-offs (average at least…)</h3>
      <div className="grid2">
        {Object.entries(cfg.thresholds ?? {}).map(([w, n]) => (
          <Field key={w} label={w[0]!.toUpperCase() + w.slice(1)}><input type="number" step="0.1" disabled={!edit} value={n} onChange={(e) => setCfg({ ...cfg, thresholds: { ...cfg.thresholds, [w]: Number(e.target.value) } })} /></Field>))}
      </div>
      {edit && <button className="primary" style={{ marginTop: 10 }} onClick={() => run(() => api(`form-versions/${version.id}/rating-config`, { method: "PATCH", body: { config: cfg } }))}>Save ratings</button>}
    </>
  );
}

