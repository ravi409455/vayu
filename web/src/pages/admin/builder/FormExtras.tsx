import { useState } from "react";
import { api } from "../../../api/client";
import type { Check, FormVersion, RatingConfig } from "../../../api/types";
import { ConditionBuilder, type FieldChoice } from "../../../ui/ConditionBuilder";
import { Field, Modal } from "../../../ui/kit";
import { slugKey } from "../../../lib/fieldTypes";

export function Checks({ version, choices, edit, run }: { version: FormVersion; choices: FieldChoice[]; edit: boolean; run: (fn: () => Promise<unknown>) => void }) {
  const [adding, setAdding] = useState<{ rule: unknown; message: string; fields: string } | null>(null);
  return (
    <>
      <p className="muted">Key Checks warn when answers contradict each other. Ops see the message on the submission; they never block the expert.</p>
      <table><thead><tr><th>Message</th><th>Fields</th><th /></tr></thead>
        <tbody>{version.checks.map((c: Check) => (
          <tr key={c.id}><td>{c.message}</td><td className="mono">{c.fields.join(", ")}</td>
            <td>{edit && <button className="link" onClick={() => run(() => api(`checks/${c.id}`, { method: "DELETE" }))}>Delete</button>}</td></tr>))}</tbody></table>
      {edit && <button className="primary" style={{ marginTop: 10 }} onClick={() => setAdding({ rule: null, message: "", fields: "" })}>Add a check</button>}
      {adding && (
        <Modal title="New Key Check" onClose={() => setAdding(null)}
          actions={<><button onClick={() => setAdding(null)}>Cancel</button><button className="primary" disabled={!adding.message || !adding.fields || adding.rule === null}
            onClick={() => { const a = adding; setAdding(null); run(() => api(`form-versions/${version.id}/checks`, { body: { rule: a.rule, message: a.message, fields: a.fields.split(",").map((x) => x.trim()).filter(Boolean) } })); }}>Add</button></>}>
          <ConditionBuilder label="Problem when" value={adding.rule} onChange={(r) => setAdding({ ...adding, rule: r })} fields={choices} />
          <Field label="Message"><input value={adding.message} onChange={(e) => setAdding({ ...adding, message: e.target.value })} /></Field>
          <Field label="Field keys it points at" help="Comma separated, e.g. odometer, door"><input value={adding.fields} onChange={(e) => setAdding({ ...adding, fields: e.target.value })} /></Field>
        </Modal>
      )}
    </>
  );
}

const DEFAULT_RATING: RatingConfig = { categories: [], deductions: { minor: 0.25, major: 1, critical: 3 }, thresholds: { excellent: 4.5, good: 3.5, average: 2.5 } };

export function Ratings({ version, sections, edit, run }: { version: FormVersion; sections: string[]; edit: boolean; run: (fn: () => Promise<unknown>) => void }) {
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
          <Field label="Sections counted in this category" help="Hold Ctrl/Cmd to pick several.">
            <select multiple disabled={!edit} value={c.sections} onChange={(e) => setCat(i, { sections: [...e.target.selectedOptions].map((o) => o.value) })} style={{ minHeight: 110 }}>
              {sections.map((s) => <option key={s}>{s}</option>)}</select></Field>
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

