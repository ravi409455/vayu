import { useEffect, useState } from "react";
import type { Access, FormField, Option } from "../../api/types";
import { AccessMatrix } from "../../ui/AccessMatrix";
import { ConditionBuilder, type FieldChoice } from "../../ui/ConditionBuilder";
import { Field } from "../../ui/kit";
import { CHOICE_TYPES, FIELD_TYPES, MEDIA_TYPES } from "../../lib/fieldTypes";

export type FieldDraft = Pick<FormField, "label" | "helper_text" | "type" | "config" | "required" | "required_if" | "show_if" | "visible" | "access">;

/** The settings of one field. The key and type are fixed once a field exists (answers, PDFs and
 *  integrations rely on them); everything else can change while the version is a draft. */
export function FieldEditor({ field, choices, lists, categories, onSave, onDelete, readOnly }: {
  field: FormField; choices: FieldChoice[]; lists: { key: string; name: string }[]; categories: string[];
  onSave: (d: FieldDraft) => void; onDelete: () => void; readOnly: boolean;
}) {
  const [d, setD] = useState<FieldDraft>(field);
  useEffect(() => setD(field), [field]);
  const set = (p: Partial<FieldDraft>) => setD({ ...d, ...p });
  const cfg = d.config as Record<string, unknown>;
  const setCfg = (p: Record<string, unknown>) => set({ config: { ...cfg, ...p } });
  const dirty = JSON.stringify(d) !== JSON.stringify({ ...field, level: undefined });
  const type = FIELD_TYPES.find((t) => t.id === field.type)?.label ?? field.type;
  const locked = field.locked || field.is_system;

  return (
    <div>
      <h2>{field.label || field.key}</h2>
      <p className="muted small">Key <code>{field.key}</code> · {type}{field.is_system && " · system field"}{field.locked && " · linked to the library"}</p>
      <fieldset disabled={readOnly} style={{ border: 0, padding: 0 }}>
        <Field label="Label"><input value={d.label} onChange={(e) => set({ label: e.target.value })} /></Field>
        <Field label="Help text (shown under the field)"><input value={d.helper_text} onChange={(e) => set({ helper_text: e.target.value })} /></Field>
        {!field.is_system && (
          <>
            <label className="check"><input type="checkbox" checked={d.required} onChange={(e) => set({ required: e.target.checked })} /> Always required</label>
            <ConditionBuilder label="Required only if" value={d.required_if} onChange={(r) => set({ required_if: r })} fields={choices} />
            <ConditionBuilder label="Show only if" value={d.show_if} onChange={(r) => set({ show_if: r })} fields={choices} />
            <label className="check"><input type="checkbox" checked={d.visible} onChange={(e) => set({ visible: e.target.checked })} /> Visible</label>
          </>
        )}
        {!locked && CHOICE_TYPES.includes(field.type) && <OptionsEditor options={(cfg.options as Option[]) ?? []} onChange={(options) => setCfg({ options })} />}
        {!locked && field.type === "master_list" && (
          <Field label="List"><select value={String(cfg.list ?? "")} onChange={(e) => setCfg({ list: e.target.value })}>
            <option value="">Choose…</option>{lists.map((l) => <option key={l.key} value={l.key}>{l.name}</option>)}</select></Field>
        )}
        {!locked && field.type === "user_picker" && (
          <Field label="People from role"><select value={String(cfg.role ?? "expert")} onChange={(e) => setCfg({ role: e.target.value })}>
            <option value="expert">Experts</option><option value="ops">Ops</option><option value="admin">Admins</option></select></Field>
        )}
        {!locked && field.type === "number" && (
          <div className="grid2">
            <Field label="Unit"><input value={String(cfg.unit ?? "")} onChange={(e) => setCfg({ unit: e.target.value || undefined })} /></Field>
            <Field label="Smallest"><input type="number" value={String(cfg.min ?? "")} onChange={(e) => setCfg({ min: e.target.value === "" ? undefined : Number(e.target.value) })} /></Field>
            <Field label="Largest"><input type="number" value={String(cfg.max ?? "")} onChange={(e) => setCfg({ max: e.target.value === "" ? undefined : Number(e.target.value) })} /></Field>
          </div>
        )}
        {!locked && ["photo", "video", "file"].includes(field.type) && (
          <div className="grid2">
            {field.type !== "file" && <Field label="At least"><input type="number" min={0} value={String(cfg.min_count ?? 0)} onChange={(e) => setCfg({ min_count: Number(e.target.value) })} /></Field>}
            <Field label="At most"><input type="number" min={1} value={String(cfg.max_count ?? 1)} onChange={(e) => setCfg({ max_count: Number(e.target.value) })} /></Field>
          </div>
        )}
        {!locked && field.type === "rating" && (
          <Field label="Rating category" help="Which category's rating this field shows."><select value={String(cfg.category ?? "")} onChange={(e) => setCfg({ category: e.target.value })}>
            <option value="">Choose…</option>{categories.map((c) => <option key={c} value={c}>{c}</option>)}</select></Field>
        )}
        {!locked && field.type === "derived" && (
          <>
            <ConditionBuilder label="Key Check is “Yes” when" value={cfg.rule} onChange={(r) => setCfg({ rule: r ?? { "!!": [1] } })} fields={choices} />
            <div className="grid2">
              <Field label="Label when yes"><input value={String(cfg.true_label ?? "")} onChange={(e) => setCfg({ true_label: e.target.value })} /></Field>
              <Field label="Label when no"><input value={String(cfg.false_label ?? "")} onChange={(e) => setCfg({ false_label: e.target.value })} /></Field>
            </div>
          </>
        )}
        {MEDIA_TYPES.includes(field.type) && <p className="muted small">Photos and files are uploaded straight to storage, checked, and then shown in reports.</p>}
        <h3>Who can see or change it</h3>
        <AccessMatrix value={d.access} onChange={(a: Access) => set({ access: a })} />
      </fieldset>
      {!readOnly && (
        <div className="bar" style={{ marginTop: 14 }}>
          <button className="primary" disabled={!dirty} onClick={() => onSave(d)}>Save field</button>
          {!field.is_system && <button className="danger" onClick={onDelete}>Delete field</button>}
        </div>
      )}
    </div>
  );
}

function OptionsEditor({ options, onChange }: { options: Option[]; onChange: (o: Option[]) => void }) {
  const set = (i: number, p: Partial<Option>) => onChange(options.map((o, j) => (j === i ? { ...o, ...p } : o)));
  return (
    <div className="card">
      <strong>Choices</strong>
      {options.map((o, i) => (
        <div className="cond-row" key={i}>
          <input aria-label="Choice key" value={o.key} placeholder="key" onChange={(e) => set(i, { key: e.target.value })} />
          <input aria-label="Choice label" value={o.label} placeholder="label" onChange={(e) => set(i, { label: e.target.value })} />
          <label className="check"><input type="checkbox" checked={!!o.is_defect} onChange={(e) => set(i, { is_defect: e.target.checked, severity: e.target.checked ? (o.severity ?? "minor") : null })} /> Defect</label>
          {o.is_defect && (
            <select aria-label="Severity" value={o.severity ?? "minor"} onChange={(e) => set(i, { severity: e.target.value })} style={{ maxWidth: 110 }}>
              <option value="minor">Minor</option><option value="major">Major</option><option value="critical">Critical</option></select>
          )}
          <button className="link" aria-label="Remove choice" onClick={() => onChange(options.filter((_, j) => j !== i))}>✕</button>
        </div>
      ))}
      <button className="link" onClick={() => onChange([...options, { key: "", label: "" }])}>+ Add choice</button>
    </div>
  );
}
