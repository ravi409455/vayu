import { Link2, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import type { Access, Check as Validation, FormField, Option } from "../../api/types";
import { uploadFile } from "../../api/client";
import { iconFor } from "../../lib/typeIcons";
import { AccessEditor } from "../../ui/AccessEditor";
import { ConditionBuilder, type FieldChoice } from "../../ui/ConditionBuilder";
import { Check, Field, Pill, Tabs, useToast } from "../../ui/kit";
import { InfoTip } from "../../ui/InfoTip";
import { MoreMenu } from "../../ui/Menu";
import { CHOICE_TYPES, FIELD_TYPES, NO_TEXT_TYPES, slugKey, SYSTEM_TYPE_LABELS, UPLOAD_TYPES } from "../../lib/fieldTypes";

export type FieldDraft = Pick<FormField, "label" | "helper_text" | "type" | "config" | "required" | "required_if" | "show_if" | "visible" | "access">;
/** A validation being edited: one saved (has an id) or new. */
export type ValidationDraft = Pick<Validation, "rule" | "message" | "fields"> & { id?: number };
type Pane = "settings" | "logic" | "access";

/** The settings of one field, in three tabs. The key and type are fixed once a field exists
 *  (answers, PDFs and integrations rely on them); everything else can change while the version is a draft. */
export function FieldEditor({ field, choices, lists, categories, onSave, onDelete, readOnly, kind = "inspection", parents, extra, outside, siblings, checks }: {
  field: FormField; choices: FieldChoice[]; lists: { key: string; name: string }[]; categories: string[];
  /** the other fields of this field's section (a photo can show one of them) */
  siblings?: { key: string; label: string; type: string }[];
  onSave: (d: FieldDraft, validations?: ValidationDraft[]) => void; onDelete: () => void; readOnly: boolean; kind?: string;
  /** this field's validations (answer rules that point at it); given: the Logic tab edits them */
  checks?: Validation[];
  parents?: { section?: Access; page?: Access }; extra?: React.ReactNode; outside?: React.ReactNode;
}) {
  const [d, setD] = useState<FieldDraft>(field);
  const [pane, setPane] = useState<Pane>("settings");
  const { fail } = useToast();
  const savedVals = (checks ?? []).map(({ id, rule, message, fields }) => ({ id, rule, message, fields }));
  const [vals, setVals] = useState<ValidationDraft[]>(savedVals);
  useEffect(() => setD(field), [field]);
  useEffect(() => setVals(savedVals), [JSON.stringify(savedVals)]); // eslint-disable-line react-hooks/exhaustive-deps
  const set = (p: Partial<FieldDraft>) => setD({ ...d, ...p });
  const cfg = d.config as Record<string, unknown>;
  const setCfg = (p: Record<string, unknown>) => set({ config: { ...cfg, ...p } });
  const valsDirty = JSON.stringify(vals) !== JSON.stringify(savedVals);
  const dirty = JSON.stringify(d) !== JSON.stringify({ ...field, level: undefined }) || valsDirty;
  const ref = `${kind === "custom" ? "inspection" : kind}.${field.key}`;
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
            <Field label="Label">
              <input value={d.label} placeholder="The question people see" onChange={(e) => set({ label: e.target.value })} />
            </Field>
            <Field label="Help text">
              <input value={d.helper_text} placeholder="Optional: an example or a reminder" onChange={(e) => set({ helper_text: e.target.value })} />
            </Field>
            {!field.is_system && (
              <div className="switch-list">
                <label className="switch-row"><span className="grow">Required <InfoTip label="About Required">It must be answered before the form can be submitted.</InfoTip></span>
                  <input type="checkbox" role="switch" className="switch" checked={d.required} onChange={(e) => set({ required: e.target.checked })} aria-label="Required" /></label>
                <label className="switch-row"><span className="grow">Visible <InfoTip label="About Visible">Turned off, the field is hidden everywhere, for everyone.</InfoTip></span>
                  <input type="checkbox" role="switch" className="switch" checked={d.visible} onChange={(e) => set({ visible: e.target.checked })} aria-label="Visible" /></label>
              </div>
            )}
            {["gps", "date", "time", "datetime"].includes(field.type) && (
              <Check label="Fill in automatically" disabled={locked} checked={cfg.auto === undefined ? field.type === "gps" : cfg.auto === true} onChange={(e) => setCfg({ auto: e.target.checked })}
                tip={<>{field.type === "gps" ? "The location is taken as soon as the page opens." : "The date and time are stamped when the page opens (server-corrected)."} The person cannot edit it. Leave off if they should enter it themselves.</>} />
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
              savedKeys={new Set((((field.config as Record<string, unknown>).options as Option[] | undefined) ?? []).map((o) => o.key))}
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
            {!locked && media && cfg.capture !== "upload" && (
              <Field label="Camera" tip="Which camera the Android app opens first. The expert can still switch with the flip button.">
                <select aria-label="Camera" value={String(cfg.camera ?? "back")} onChange={(e) => setCfg({ camera: e.target.value === "back" ? undefined : e.target.value })}>
                  <option value="back">Back</option><option value="front">Front (selfie)</option></select>
              </Field>
            )}
            {!locked && (media || field.type === "file") && (
              <Check label="Upload by Ops allowed" checked={cfg.ops_upload !== false} onChange={(e) => setCfg({ ops_upload: e.target.checked ? undefined : false })}
                tip={`After the expert submits, Ops and Admin can add or replace these ${field.type}s from their computer or phone. Turn off when only the expert's own upload counts.`} />
            )}
            {!locked && UPLOAD_TYPES.includes(field.type) && (
              <div className="grid2">
                {field.type !== "file" && <Field label="At least"><input type="number" min={0} value={String(cfg.min_count ?? 0)} onChange={(e) => setCfg({ min_count: Number(e.target.value) })} /></Field>}
                <Field label="At most"><input type="number" min={1} value={String(cfg.max_count ?? 1)} onChange={(e) => setCfg({ max_count: Number(e.target.value) })} /></Field>
              </div>
            )}
            {!field.locked && field.type === "short_text" && (
              <Check label="Scan with the camera" checked={cfg.scan === true} onChange={(e) => setCfg({ scan: e.target.checked || undefined })}
                tip="In the Android app, a scan button reads the text (a chassis number, a registration). The expert can still type over it." />
            )}
            {!locked && field.type === "photo" && (
              <>
                <Check label="Issue photo" checked={cfg.issue_photo === true} onChange={(e) => setCfg({ issue_photo: e.target.checked || undefined })}
                  tip="Counts as a photo of a problem whenever it is taken. The report can show only these." />
                {siblings && (
                  <Field label="Photo of" tip="The check this photo shows. The report can caption it with that check and its answer, and counts it as an issue photo when the answer is a problem.">
                    <select aria-label="Photo of" value={String(cfg.photo_of ?? "")} onChange={(e) => setCfg({ photo_of: e.target.value || undefined })}>
                      <option value="">No particular check</option>
                      {siblings.filter((x) => !NO_TEXT_TYPES.includes(x.type)).map((x) => <option key={x.key} value={x.key}>{x.label || x.key}</option>)}
                    </select>
                  </Field>)}
              </>
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
        {pane === "logic" && <>
          {field.is_system ? <p className="muted small">System fields are always shown and always required: the platform relies on them. They can still have validations.</p> : (
            <>
              <ConditionBuilder label="Required only if" value={d.required_if} onChange={(r) => set({ required_if: r })} fields={choices}
                tip="The field becomes required only when these conditions match. A field hidden by a rule is never required, even if it says “required”." />
              <ConditionBuilder label="Show only if" value={d.show_if} onChange={(r) => set({ show_if: r })} fields={choices}
                tip="The field appears only when these conditions match." />
            </>
          )}
          {checks && <section aria-label="Validation">
            <div className="label-row" style={{ margin: "14px 0 6px" }}><strong>Validation</strong>
              <InfoTip label="About validation">The answer must match the condition, or the expert sees your message under the field and cannot submit. Checked only once the fields it uses are answered.</InfoTip></div>
            {vals.map((v, i) => (
              <div key={v.id ?? `new-${i}`} className="val-item">
                <ConditionBuilder label="Valid when" value={v.rule} fields={choices}
                  onClear={() => setVals(vals.filter((_, j) => j !== i))}
                  onChange={(r) => setVals(vals.map((x, j) => (j === i ? { ...x, rule: r } : x)))} />
                <Field label="Message when not valid">
                  <input value={v.message} placeholder="e.g. Cannot be after the registration date" maxLength={300}
                    onChange={(e) => setVals(vals.map((x, j) => (j === i ? { ...x, message: e.target.value } : x)))} />
                </Field>
                {v.fields.length > 1 && <p className="muted small">Also shown on: {v.fields.filter((k) => k !== field.key).join(", ")}</p>}
                <button type="button" className="link danger-link" onClick={() => setVals(vals.filter((_, j) => j !== i))}>Remove validation</button>
              </div>))}
            <button type="button" className="link" onClick={() => setVals([...vals, { rule: { "!!": [{ var: ref }] }, message: "", fields: [field.key] }])}>+ Add validation</button>
          </section>}
        </>}
        {pane === "access" && <AccessEditor value={d.access} onChange={(a) => set({ access: a })} kind={kind} ftype={field.type} parents={parents} />}
      </fieldset>
      {outside}
      {!readOnly && (
        <div className="insp-foot">
          {!field.is_system && <button className="link danger-link" onClick={onDelete}><Trash2 size={14} aria-hidden /> Delete field</button>}
          <span className="grow muted small" style={{ textAlign: "right" }}>{dirty ? "Unsaved changes" : ""}</span>
          <button className="primary" disabled={!dirty || vals.some((v) => !v.message.trim() || !v.rule)}
            title={vals.some((v) => !v.rule) ? "Finish the validation's condition" : vals.some((v) => !v.message.trim()) ? "Every validation needs a message" : undefined}
            onClick={() => (checks ? onSave(d, vals) : onSave(d))}>Save field</button>
        </div>
      )}
    </div>
  );
}

const OUTCOMES = [
  { id: "fine", label: "Fine" }, { id: "minor", label: "Defect: minor" }, { id: "major", label: "Defect: major" }, { id: "critical", label: "Defect: critical" },
] as const;
/** Only a choice that is not saved yet takes its key from the label; a saved choice keeps its key
 *  (answers, rules and reports point at it) however its label changes. */
export const followsLabel = (o: Option, saved: Set<string>) => !saved.has(o.key) && (!o.key || o.key === slugKey(o.label));
const outcomeOf = (o: Option) => (o.is_defect ? (o.severity ?? "minor") : "fine");
const TONES = [{ id: "", label: "Report colour: automatic" }, { id: "ok", label: "Green" }, { id: "warn", label: "Amber" }, { id: "bad", label: "Red" }, { id: "muted", label: "Grey" }] as const;
/** The colour an answer prints in: the one chosen, else from its meaning (fine green, minor amber, worse red). */
export const toneOf = (o: Option) => o.tone ?? (!o.is_defect ? "ok" : (o.severity ?? "minor") === "minor" ? "warn" : "bad");

/** The answers people can pick: label, what it means for the rating, the order. The key (used by the
 *  API, rules and reports) follows the label until someone types their own. */
function OptionsEditor({ options, onChange, display, onDisplay, savedKeys }: { options: Option[]; onChange: (o: Option[]) => void; display: string | null; onDisplay: (d: string) => void; savedKeys: Set<string> }) {
  const [keys, setKeys] = useState(false);
  const set = (i: number, p: Partial<Option>) => onChange(options.map((o, j) => (j === i ? { ...o, ...p } : o)));
  const move = (i: number, by: number) => { const j = i + by; if (j < 0 || j >= options.length) return; const out = [...options]; [out[i], out[j]] = [out[j]!, out[i]!]; onChange(out); };
  const dupes = new Set(options.map((o) => o.key).filter((k, i, a) => k && a.indexOf(k) !== i));
  return (
    <section className="options-editor" aria-label="Choices">
      <div className="opt-head">
        <span className="opt-title grow">Choices</span>
        {display !== null && (
          <div className="seg sm" role="group" aria-label="Show as">
            <button type="button" aria-pressed={display !== "dropdown"} onClick={() => onDisplay("buttons")}>Buttons</button>
            <button type="button" aria-pressed={display === "dropdown"} onClick={() => onDisplay("dropdown")}>Dropdown</button>
          </div>)}
      </div>
      <ol className="opt-list">
        {options.map((o, i) => {
          const out = outcomeOf(o);
          const showKey = keys || !savedKeys.has(o.key) || dupes.has(o.key);
          return (
            <li key={i} className={`opt-row ${out}`}>
              <div className="opt-main">
                <select aria-label={`Colour of ${o.label || "this choice"} in the report`} title="Colour in the report" className={`opt-tone tone-${toneOf(o)}`}
                  value={o.tone ?? ""} onChange={(e) => set(i, { tone: (e.target.value || undefined) as Option["tone"] })}>
                  {TONES.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}</select>
                <input aria-label="Choice label" value={o.label} placeholder="Answer"
                  onChange={(e) => set(i, { label: e.target.value, ...(followsLabel(o, savedKeys) ? { key: slugKey(e.target.value) } : {}) })} />
                <select aria-label="What this choice means" value={out} onChange={(e) => {
                  const v = e.target.value;
                  set(i, v === "fine" ? { is_defect: false, severity: null } : { is_defect: true, severity: v });
                }}>{OUTCOMES.map((x) => <option key={x.id} value={x.id}>{x.label}</option>)}</select>
                <MoreMenu label={`More for ${o.label || "this choice"}`} items={[
                  { label: "Move up", onClick: () => move(i, -1), hidden: i === 0 },
                  { label: "Move down", onClick: () => move(i, 1), hidden: i === options.length - 1 },
                  { label: "Remove", danger: true, onClick: () => onChange(options.filter((_, j) => j !== i)) },
                ]} />
              </div>
              {showKey && (
                <div className="opt-sub">
                  <label className="opt-key"><span>key</span><input aria-label="Choice key" className="mono" value={o.key} placeholder="key" onChange={(e) => set(i, { key: e.target.value })}
                    title={savedKeys.has(o.key) ? "Answers already saved use this key: changing it disconnects them" : undefined} /></label>
                  {dupes.has(o.key) && <span className="error" style={{ margin: 0 }}>used twice</span>}
                  {!savedKeys.has(o.key) && <span className="muted small">new</span>}
                </div>)}
            </li>);
        })}
      </ol>
      <div className="opt-foot">
        <button type="button" className="link" onClick={() => onChange([...options, { key: "", label: "" }])}>+ Add choice</button>
        <span className="grow" />
        <button type="button" className="link muted-link" aria-pressed={keys} onClick={() => setKeys(!keys)}>{keys ? "Hide keys" : "Show keys"}</button>
      </div>
      {display !== null && options.length > 5 && display !== "dropdown" && <p className="muted small" style={{ margin: "6px 0 0" }}>More than 5 choices show as a dropdown unless you pick Buttons.</p>}
    </section>
  );
}
