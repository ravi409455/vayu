import { Plus, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api } from "../../../api/client";
import type { FormVersion, KeyCheck, KeyCheckType } from "../../../api/types";
import { slugKey } from "../../../lib/fieldTypes";
import { ConditionBuilder, type FieldChoice } from "../../../ui/ConditionBuilder";
import { Check, Empty, Field } from "../../../ui/kit";
import { MoreMenu } from "../../../ui/Menu";

const TYPES: { id: KeyCheckType; label: string; tip: string }[] = [
  { id: "linked", label: "From fields", tip: "Takes the answers of one or more fields." },
  { id: "rule", label: "Yes / No from a rule", tip: "Yes or No, worked out from the answers." },
  { id: "text", label: "Text", tip: "Ops type it in; starts with the default." },
  { id: "number", label: "Number", tip: "Ops type it in; sent to integrations as a number when it reads as one." },
  { id: "date", label: "Date", tip: "Ops type it in, e.g. 24-11-2026." },
];
const MEDIA = new Set(["photo", "video", "file", "signature", "image", "derived", "rating"]);
const typeLabel = (t: KeyCheckType) => TYPES.find((x) => x.id === t)?.label ?? t;
/** The short name a template uses: an inspection field by its key, others with their form. */
const short = (ref: string) => (ref.startsWith("inspection.") ? ref.slice(11) : ref);
const blank = (label: string, keys: Set<string>): KeyCheck => {
  let key = slugKey(label) || "key_check", n = 2;
  while (keys.has(key)) key = `${slugKey(label) || "key_check"}_${n++}`;
  return { key, label, type: "linked", fields: [], combine: "join", separator: ", ", default: "" };
};

/** The Key Checks tab: short facts Ops review on every booking (experts never see them). Laid
 *  out like Questions: the list on the left, the selected one's settings on the right. Saved as a
 *  whole list. A key stays fixed once saved: reports and integrations point at it. */
export function KeyChecks({ version, choices, edit, run }: { version: FormVersion; choices: FieldChoice[]; edit: boolean; run: (fn: () => Promise<unknown>) => void }) {
  const saved = version.key_checks ?? [];
  const [items, setItems] = useState<KeyCheck[]>(saved);
  const [sel, setSel] = useState(0);
  useEffect(() => { setItems(version.key_checks ?? []); }, [version.key_checks]);
  const savedKeys = useMemo(() => new Set(saved.map((k) => k.key)), [saved]);
  const dirty = JSON.stringify(items) !== JSON.stringify(saved);
  const pickable = choices.filter((c) => !MEDIA.has(c.type ?? ""));      // answers only, no photos
  const current = items[Math.min(sel, items.length - 1)];
  const replace = (kc: KeyCheck) => setItems(items.map((k) => (k === current ? kc : k)));
  const set = (p: Partial<KeyCheck>) => replace({ ...current!, ...p });
  const move = (i: number, by: number) => { const j = i + by; const out = [...items]; [out[i], out[j]] = [out[j]!, out[i]!]; setItems(out); setSel(j); };
  const add = () => { setItems([...items, blank("New Key Check", new Set(items.map((k) => k.key)))]); setSel(items.length); };
  const save = () => run(() => api(`form-versions/${version.id}/key-checks`, { method: "PATCH", body: { key_checks: items } }));

  return (
    <div className="builder">
      <section className="card" aria-label="Key Checks">
        <div className="bar" style={{ marginTop: 0 }}>
          <span className="grow muted small">Facts Ops review on each booking. Experts never see them.</span>
          {edit && <button className="sm" onClick={add}><Plus size={14} aria-hidden /> Add Key Check</button>}
        </div>
        {items.length === 0 ? <Empty title="No Key Checks yet">{edit ? "Add one, e.g. “Accident history” or “Odometer”." : "This version is live and cannot change. Start a new draft (top right) to add Key Checks."}</Empty> : (
          <div className="kc-list">
            {items.map((k, i) => (
              <div key={i} role="button" tabIndex={0} className={`field-row${k === current ? " on" : ""}`} onClick={() => setSel(i)}
                onKeyDown={(e) => { if (e.key === "Enter" && e.target === e.currentTarget) setSel(i); }}>
                <span className="grow ellipsis"><strong>{k.label || k.key}</strong></span>
                <span className="type-tag">{typeLabel(k.type)}</span>
                {k.in_report === false && <span className="type-tag">not in report</span>}
                {edit && <MoreMenu label={`More for ${k.label}`} items={[
                  { label: "Move up", onClick: () => move(i, -1), hidden: i === 0 },
                  { label: "Move down", onClick: () => move(i, 1), hidden: i === items.length - 1 },
                  { label: "Delete", danger: true, onClick: () => { setItems(items.filter((_, j) => j !== i)); setSel(Math.max(0, i - 1)); } },
                ]} />}
              </div>))}
          </div>)}
        {edit && (dirty || items.length > 0) && (
          <div className="insp-foot">
            <span className="grow muted small">{dirty ? "Unsaved changes" : "All saved"}</span>
            {dirty && <button onClick={() => setItems(saved)}>Undo</button>}
            <button className="primary" disabled={!dirty} onClick={save}>Save Key Checks</button>
          </div>)}
      </section>
      <aside className="card inspector" aria-label="Key Check settings">
        {!current ? <p className="muted small">{edit ? "Add a Key Check to set it up." : "Start a new draft to add or change Key Checks."}</p> : (
          <fieldset disabled={!edit} style={{ border: 0, padding: 0, margin: 0, minWidth: 0 }}>
            <div className="insp-head"><div className="grow"><h2>{current.label || "Key Check"}</h2>
              <p className="muted small">key <code>{current.key}</code></p></div></div>
            <Field label="Label">
              <input value={current.label} onChange={(e) => set({ label: e.target.value, ...(savedKeys.has(current.key) ? {} : { key: slugKey(e.target.value) || current.key }) })} />
            </Field>
            <Field label="Type" tip={<>{TYPES.map((t) => <span key={t.id}><strong>{t.label}:</strong> {t.tip}<br /></span>)}Whatever the type, Ops can replace the value with their own text.</>}>
              <select value={current.type} onChange={(e) => {
                const type = e.target.value as KeyCheckType;
                const base: KeyCheck = { key: current.key, label: current.label, type, default: current.default ?? "", ...(current.in_report === false ? { in_report: false } : {}) };
                // a new type starts clean: settings of the old one would be refused
                replace({ ...base, ...(type === "linked" ? { fields: [], combine: "join", separator: ", " } : type === "rule" ? { rule: { "!!": [{ var: "inspection.chassis_no" }] }, true_label: "Yes", false_label: "No" } : {}) });
              }}>{TYPES.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}</select>
            </Field>
            {current.type === "linked" && <Linked kc={current} set={set} choices={pickable} />}
            {current.type === "rule" && <>
              <ConditionBuilder label="Yes when" value={current.rule} onChange={(r) => set({ rule: (r ?? { "!!": [1] }) as Record<string, unknown> })} fields={choices} />
              <div className="grid2">
                <Field label="Text when yes"><input value={current.true_label ?? ""} placeholder="Yes" onChange={(e) => set({ true_label: e.target.value })} /></Field>
                <Field label="Text when no"><input value={current.false_label ?? ""} placeholder="No" onChange={(e) => set({ false_label: e.target.value })} /></Field>
              </div></>}
            {current.type !== "rule" && (
              <Field label="Default value" tip={current.type === "linked" ? "Shown when all the picked fields are empty." : "What Ops see until they type something else."}>
                <input value={current.default ?? ""} placeholder={current.type === "date" ? "e.g. 24-11-2026" : current.type === "number" ? "e.g. 0" : "Optional"} onChange={(e) => set({ default: e.target.value })} />
              </Field>)}
            <Check label="Show in the report" checked={current.in_report !== false} onChange={(e) => set({ in_report: e.target.checked ? undefined : false })}
              tip="Off keeps it for Ops and integrations only; the PDF report leaves it out." />
          </fieldset>)}
      </aside>
    </div>
  );
}

/** Fields a "From fields" Key Check takes, and how their answers are combined. */
function Linked({ kc, set, choices }: { kc: KeyCheck; set: (p: Partial<KeyCheck>) => void; choices: FieldChoice[] }) {
  const fields = kc.fields ?? [];
  const label = (ref: string) => choices.find((c) => c.value === ref)?.label ?? ref;
  return (
    <>
      <Field label="Fields" tip="Their answers, as people read them (labels, not codes). Empty ones are skipped." bare>
        <div className="chips" style={{ marginBottom: 6 }}>
          {fields.map((ref) => <span key={ref} className="chip">{label(ref)}<button type="button" className="link" aria-label={`Remove ${label(ref)}`} onClick={() => set({ fields: fields.filter((x) => x !== ref) })}><X size={12} aria-hidden /></button></span>)}
          {fields.length === 0 && <span className="muted small">None picked yet.</span>}
        </div>
        <select aria-label="Add a field" value="" onChange={(e) => { if (e.target.value) set({ fields: [...fields, e.target.value] }); }}>
          <option value="">Add a field…</option>
          {choices.filter((c) => !fields.includes(c.value)).map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
        </select>
      </Field>
      <Field label="Combine as" bare tip="Join: the answers one after another with a separator. Template: your own sentence with the answers put in.">
        <div className="seg" role="group" aria-label="Combine as">
          <button type="button" aria-pressed={kc.combine !== "template"} onClick={() => set({ combine: "join", template: undefined, separator: kc.separator ?? ", " })}>Join</button>
          <button type="button" aria-pressed={kc.combine === "template"} onClick={() => set({ combine: "template", template: kc.template ?? fields.map((f) => `{${short(f)}}`).join(" · ") })}>Template</button>
        </div>
      </Field>
      {kc.combine === "template"
        ? <Field label="Template" tip="Put a field in with its name in braces, e.g. {odometer} km. Click a name below to insert it.">
            <textarea rows={2} value={kc.template ?? ""} onChange={(e) => set({ template: e.target.value })} />
          </Field>
        : <Field label="Separator"><input value={kc.separator ?? ", "} onChange={(e) => set({ separator: e.target.value })} style={{ maxWidth: 120 }} /></Field>}
      {kc.combine === "template" && fields.length > 0 && (
        <div className="chips" style={{ marginTop: -4 }}>
          {fields.map((f) => <button key={f} type="button" className="sm" onClick={() => set({ template: `${kc.template ?? ""}{${short(f)}}` })}>{`{${short(f)}}`}</button>)}
        </div>)}
    </>
  );
}
