import { ArrowDown, ArrowUp, Link2, Trash2, X } from "lucide-react";
import { useEffect, useState } from "react";
import type { Access, FormField, Option } from "../../api/types";
import { uploadFile } from "../../api/client";
import { iconFor } from "../../lib/typeIcons";
import { AccessEditor } from "../../ui/AccessEditor";
import { ConditionBuilder, type FieldChoice } from "../../ui/ConditionBuilder";
import { Field, Pill, Tabs, useToast } from "../../ui/kit";
import { CHOICE_TYPES, FIELD_TYPES, slugKey, SYSTEM_TYPE_LABELS } from "../../lib/fieldTypes";

export type FieldDraft = Pick<FormField, "label" | "helper_text" | "type" | "config" | "required" | "required_if" | "show_if" | "visible" | "access">;
type Pane = "settings" | "logic" | "access";

/** The settings of one field, in three tabs. The key and type are fixed once a field exists
 *  (answers, PDFs and integrations rely on them); everything else can change while the version is a draft. */
export function FieldEditor({ field, choices, lists, categories, onSave, onDelete, readOnly, kind = "inspection", parents, extra, outside }: {
  field: FormField; choices: FieldChoice[]; lists: { key: string; name: string }[]; categories: string[];
  onSave: (d: FieldDraft) => void; onDelete: () => void; readOnly: boolean; kind?: string;
  parents?: { section?: Access; page?: Access }; extra?: React.ReactNode; outside?: React.ReactNode;
}) {
  const [d, setD] = useState<FieldDraft>(field);
  const [pane, setPane] = useState<Pane>("settings");
  const { fail } = useToast();
  useEffect(() => setD(field), [field]);
  const set = (p: Partial<FieldDraft>) => setD({ ...d, ...p });
  const cfg = d.config as Record<string, unknown>;
  const setCfg = (p: Record<string, unknown>) => set({ config: { ...cfg, ...p } });
  const dirty = JSON.stringify(d) !== JSON.stringify({ ...field, level: undefined });
  const type = FIELD_TYPES.find((t) => t.id === field.type)?.label ?? SYSTEM_TYPE_LABELS[field.type] ?? field.type;
  const locked = field.locked || field.is_system;
  const Icon = iconFor(field.type);
  const media = field.type === "photo" || field.type === "video";

  return (
    <div>
      <div className="insp-head">
        <span className="type-badge"><Icon size={16} aria-hidden /></span>
        <div className="grow">
          <h2>{field.label || field.key}</h2>
          <div className="chips" style={{ marginTop: 4 }}>
            <span className="pill type-pill"><Icon size={12} aria-hidden /> {type}</span>
            {field.is_system && <span className="pill">System field</span>}
            {field.locked && <span className="pill">From the library</span>}
            <span className="muted small">key <code>{field.key}</code></span>
          </div>
        </div>
        {field.library && <Pill tone={field.library.update_available ? "warn" : "info"}><Link2 size={12} aria-hidden /> Library{field.library.update_available ? ": update available" : ""}</Pill>}
      </div>
      <Tabs value={pane} onChange={setPane} tabs={[{ id: "settings", label: "Settings" }, { id: "logic", label: "Logic" }, { id: "access", label: "Access" }]} />
      <fieldset disabled={readOnly} style={{ border: 0, padding: 0, margin: 0, minWidth: 0 }}>
        {pane === "settings" && (
          <>
            <Field label="Label" tip="What the person sees above the field.">
              <input value={d.label} onChange={(e) => set({ label: e.target.value })} />
            </Field>
            <Field label="Help text" tip="Small grey text under the field: an example or a reminder.">
              <input value={d.helper_text} onChange={(e) => set({ helper_text: e.target.value })} />
            </Field>
            {!field.is_system && (
              <div className="bar" style={{ gap: 18, marginBottom: 10 }}>
                <label className="check"><input type="checkbox" checked={d.required} onChange={(e) => set({ required: e.target.checked })} /> Required</label>
                <label className="check"><input type="checkbox" checked={d.visible} onChange={(e) => set({ visible: e.target.checked })} /> Visible</label>
              </div>
            )}
            {["gps", "date", "time", "datetime"].includes(field.type) && (
              <label className="check" style={{ alignItems: "flex-start" }}>
                <input type="checkbox" disabled={locked} checked={cfg.auto === undefined ? field.type === "gps" : cfg.auto === true} onChange={(e) => setCfg({ auto: e.target.checked })} />
                <span><strong>Fill in automatically</strong><br /><span className="muted small">{field.type === "gps" ? "The location is taken as soon as the page opens." : "The date and time are stamped when the page opens (server-corrected)."} The person cannot edit it. Leave off if they should enter it themselves.</span></span>
              </label>
            )}
            {field.type === "image" && (
              <Field label="Picture" tip="A picture shown to the expert in the form, for example a QR code to scan. PNG or JPEG, up to 2 MB. It is not an answer and not part of the report.">
                {typeof cfg.asset === "string" && <img src={`/api/v1/form-assets/${cfg.asset}`} alt="The uploaded picture" style={{ maxWidth: 220, maxHeight: 220, display: "block", marginBottom: 8, border: "1px solid var(--line)", borderRadius: 8 }} />}
                <input type="file" accept="image/png,image/jpeg" aria-label="Upload the picture" onChange={async (e) => {
                  const file = e.target.files?.[0];
                  if (!file) return;
                  try { const r = await uploadFile<{ id: string }>("form-assets", file); setCfg({ asset: r.id }); } catch (err) { fail(err); }
                }} />
              </Field>
            )}
            {!field.locked && CHOICE_TYPES.includes(field.type) && <OptionsEditor options={(cfg.options as Option[]) ?? []} onChange={(options) => setCfg({ options })}
              display={field.type === "single_choice" ? String(cfg.display ?? "") : null} onDisplay={(display) => setCfg({ display })} />}
            {!locked && field.type === "master_list" && (
              <Field label="List" tip="The master list whose items this field offers (cities, car models...).">
                <select value={String(cfg.list ?? "")} onChange={(e) => setCfg({ list: e.target.value })}>
                  <option value="">Choose…</option>{lists.map((l) => <option key={l.key} value={l.key}>{l.name}</option>)}</select>
              </Field>
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
            {!locked && media && (
              <Field label={field.type === "photo" ? "How photos are added" : "How videos are added"}
                tip="Camera: only a live capture. Upload: only a file from the device. Both: the expert chooses. Use Camera-only when a gallery photo would not be trustworthy.">
                <select aria-label="How files are added" value={String(cfg.capture ?? "both")} onChange={(e) => setCfg({ capture: e.target.value })}>
                  <option value="both">Camera and upload</option><option value="camera">Camera only</option><option value="upload">Upload only</option></select>
              </Field>
            )}
            {!locked && ["photo", "video", "file"].includes(field.type) && (
              <div className="grid2">
                {field.type !== "file" && <Field label="At least"><input type="number" min={0} value={String(cfg.min_count ?? 0)} onChange={(e) => setCfg({ min_count: Number(e.target.value) })} /></Field>}
                <Field label="At most"><input type="number" min={1} value={String(cfg.max_count ?? 1)} onChange={(e) => setCfg({ max_count: Number(e.target.value) })} /></Field>
              </div>
            )}
            {!locked && field.type === "rating" && (
              <Field label="Rating category" tip="Which category's rating this field shows. Categories are set on the Ratings tab.">
                <select value={String(cfg.category ?? "")} onChange={(e) => setCfg({ category: e.target.value })}>
                  <option value="">Choose…</option>{categories.map((c) => <option key={c} value={c}>{c}</option>)}</select>
              </Field>
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
            {extra}
          </>
        )}
        {pane === "logic" && (
          field.is_system ? <p className="muted">System fields are always shown and always required: the platform relies on them.</p> : (
            <>
              <p className="muted small">Rules make a field appear or become required only in some situations.</p>
              <ConditionBuilder label="Required only if" value={d.required_if} onChange={(r) => set({ required_if: r })} fields={choices} />
              <ConditionBuilder label="Show only if" value={d.show_if} onChange={(r) => set({ show_if: r })} fields={choices} />
              <p className="muted small">A field that is hidden by a rule is never required, even if it says “required”.</p>
            </>
          )
        )}
        {pane === "access" && <AccessEditor value={d.access} onChange={(a) => set({ access: a })} kind={kind} ftype={field.type} parents={parents} />}
      </fieldset>
      {outside}
      {!readOnly && (
        <div className="insp-foot">
          <button className="primary" disabled={!dirty} onClick={() => onSave(d)}>Save field</button>
          {!field.is_system && <button className="danger" onClick={onDelete}><Trash2 size={14} aria-hidden /> Delete field</button>}
        </div>
      )}
    </div>
  );
}

const OUTCOMES = [
  { id: "fine", label: "Fine" }, { id: "minor", label: "Defect: minor" }, { id: "major", label: "Defect: major" }, { id: "critical", label: "Defect: critical" },
] as const;
const outcomeOf = (o: Option) => (o.is_defect ? (o.severity ?? "minor") : "fine");

/** The answers people can pick: label, what it means for the rating, the order. The key (used by the
 *  API, rules and reports) follows the label until someone types their own. */
function OptionsEditor({ options, onChange, display, onDisplay }: { options: Option[]; onChange: (o: Option[]) => void; display: string | null; onDisplay: (d: string) => void }) {
  const set = (i: number, p: Partial<Option>) => onChange(options.map((o, j) => (j === i ? { ...o, ...p } : o)));
  const move = (i: number, by: number) => { const j = i + by; if (j < 0 || j >= options.length) return; const out = [...options]; [out[i], out[j]] = [out[j]!, out[i]!]; onChange(out); };
  const dupes = new Set(options.map((o) => o.key).filter((k, i, a) => k && a.indexOf(k) !== i));
  return (
    <section className="options-editor" aria-label="Choices">
      <div className="opt-head">
        <strong className="grow">Choices</strong>
        {display !== null && (
          <div className="seg" role="group" aria-label="Show as">
            <button type="button" aria-pressed={display !== "dropdown"} onClick={() => onDisplay("buttons")}>Buttons</button>
            <button type="button" aria-pressed={display === "dropdown"} onClick={() => onDisplay("dropdown")}>Dropdown</button>
          </div>)}
      </div>
      <p className="muted small" style={{ margin: "0 0 8px" }}>A defect counts against the rating; its severity decides how much.</p>
      <ol className="opt-list">
        {options.map((o, i) => {
          const out = outcomeOf(o);
          return (
            <li key={i} className={`opt-row ${out}`}>
              <div className="opt-main">
                <span className="opt-dot" aria-hidden="true" />
                <input aria-label="Choice label" value={o.label} placeholder="What people see"
                  onChange={(e) => set(i, { label: e.target.value, ...(!o.key || o.key === slugKey(o.label) ? { key: slugKey(e.target.value) } : {}) })} />
                <select aria-label="What this choice means" value={out} onChange={(e) => {
                  const v = e.target.value;
                  set(i, v === "fine" ? { is_defect: false, severity: null } : { is_defect: true, severity: v });
                }}>{OUTCOMES.map((x) => <option key={x.id} value={x.id}>{x.label}</option>)}</select>
              </div>
              <div className="opt-sub">
                <label className="opt-key"><span>key</span><input aria-label="Choice key" className="mono" value={o.key} placeholder="key" onChange={(e) => set(i, { key: e.target.value })} /></label>
                {dupes.has(o.key) && <span className="error" style={{ margin: 0 }}>used twice</span>}
                <span className="grow" />
                <button type="button" className="icon-btn" aria-label={`Move ${o.label || "choice"} up`} disabled={i === 0} onClick={() => move(i, -1)}><ArrowUp size={14} aria-hidden /></button>
                <button type="button" className="icon-btn" aria-label={`Move ${o.label || "choice"} down`} disabled={i === options.length - 1} onClick={() => move(i, 1)}><ArrowDown size={14} aria-hidden /></button>
                <button type="button" className="icon-btn" aria-label="Remove choice" onClick={() => onChange(options.filter((_, j) => j !== i))}><X size={14} aria-hidden /></button>
              </div>
            </li>);
        })}
      </ol>
      <button type="button" className="link" onClick={() => onChange([...options, { key: "", label: "" }])}>+ Add choice</button>
      {display !== null && options.length > 5 && display !== "dropdown" && <p className="muted small">More than 5 choices show as a dropdown unless you pick Buttons here.</p>}
    </section>
  );
}
