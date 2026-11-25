import { ArrowDown, ArrowUp, Plus, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { api, ApiError } from "../../api/client";
import { useList, useRefresh } from "../../api/hooks";
import type { MasterList } from "../../api/types";
import { useAuth } from "../../auth";
import { FIELD_TYPES, slugKey } from "../../lib/fieldTypes";
import { addFieldTo, asField, isSection, moveField, newFieldDef, previewTree, removeFieldFrom, replaceField, ruleChoices, sameDef, SYSTEM_RULE_FIELDS, withDraft, type Definition, type FieldDef } from "../../lib/libraryDef";
import { AccessEditor } from "../../ui/AccessEditor";
import { ConditionBuilder } from "../../ui/ConditionBuilder";
import { FormRenderer } from "../../ui/FormRenderer";
import { Empty, Field, LoadError, Modal, PageHeader, Pill, Tabs, useToast, when } from "../../ui/kit";
import { FieldEditor, type FieldDraft } from "./builder/FieldEditor";
import { PushReview } from "./library/PushReview";
import { useCrumb } from "../../ui/crumb";
import { keys } from "../../api/keys";

type Item = { id: number; kind: "field" | "section"; key: string; name: string; revision: number; archived: boolean; definition: Definition; usages: { form: string; version: number; status: string }[] };
type Revision = { revision: number; name: string; definition: Definition; changed_keys: string[]; by: string; by_login?: string; at: string };
type Tab = "settings" | "used" | "history";

/** The library item editor: settings on the left, a live preview on the right. Saving makes a new
 *  revision; "Save and update everywhere" then shows exactly what every form would get. */
export function LibraryEditor() {
  const id = Number(useParams().id);
  const { can } = useAuth();
  const { say, fail } = useToast();
  const refresh = useRefresh();
  const item = useQuery({ queryKey: keys.libraryItem(id), queryFn: ({ signal }) => api<Item>(`library/${id}`, { signal }) });
  useCrumb(item.data?.name);
  const history = useQuery({ queryKey: keys.libraryHistory(id), queryFn: ({ signal }) => api<Revision[]>(`library/${id}/history`, { signal }) });
  const lists = useList<MasterList>(keys.masterLists(), "master-lists");
  const [def, setDef] = useState<Definition | null>(null);
  const [name, setName] = useState("");
  const [pick, setPick] = useState<string | null>(null);              // which field of a section is open
  const [tab, setTab] = useState<Tab>("settings");
  const [adding, setAdding] = useState(false);
  const [review, setReview] = useState<number | null>(null);        // the revision being pushed
  const [stale, setStale] = useState(false);
  const [error, setError] = useState("");
  const [values, setValues] = useState<Record<string, unknown>>({});
  const it = item.data;
  useEffect(() => { if (it) { setDef(it.definition); setName(it.name); setPick(null); } }, [it?.id, it?.revision]); // eslint-disable-line react-hooks/exhaustive-deps -- reloads the editor only for another item or revision, so a refetch keeps what is being typed

  const edit = can("library.edit");
  const dirty = !!it && !!def && (!sameDef(def, it.definition) || name !== it.name);
  const save = useMutation({
    mutationFn: () => api<Item>(`library/${id}`, { method: "PATCH", body: { definition: def, revision: it!.revision, name } }),
    onSuccess: (r) => { setError(""); say(`Saved as revision ${r.revision}.`); void refresh(keys.library(), keys.libraryItem(), keys.libraryHistory()); },
    onError: (e) => { if (e instanceof ApiError && e.code === "STALE_LIBRARY_ITEM") setStale(true); else setError(e instanceof ApiError ? e.message : "Could not save."); },
  });
  const archive = useMutation({
    mutationFn: () => api(`library/${id}`, { method: "PATCH", body: { archived: !it!.archived } }),
    onSuccess: () => { say("Done."); void refresh(keys.library(), keys.libraryItem()); }, onError: fail,
  });
  const tree = useMemo(() => (it && def ? previewTree(it.kind, def) : null), [it, def]);
  if (item.isError) return <LoadError error={item.error} what="library item" onRetry={item.refetch} />;
  if (!it || !def || !tree) return <p className="muted pad">Loading…</p>;
  const section = isSection(def) ? def : null;
  const choices = ruleChoices(it.kind, def, SYSTEM_RULE_FIELDS);
  const openField = section ? section.fields.find((f) => f.key === pick) : (def as FieldDef);
  const catalogue = (lists.data ?? []).map((l) => ({ key: l.key, name: l.name }));
  const setField = (f: FieldDef, d: FieldDraft) => {
    const next = withDraft(f, d);
    setDef(section ? replaceField(section, next) : next);
  };
  const saveThen = async () => { try { const r = await save.mutateAsync(); setReview(r.revision); } catch { /* the error shows below */ } };

  return (
    <>
      <PageHeader title={<>{it.name} <span className="pill">{it.kind === "section" ? "Section" : "Field"}</span>{it.archived && <> <Pill tone="warn">Archived</Pill></>}</>}
        subtitle={<>Revision {it.revision} · key <span className="mono">{it.key}</span>. Everything inside the item is decided here; each form only decides where it sits.</>}>
        {edit && <button onClick={() => archive.mutate()}>{it.archived ? "Restore" : "Archive"}</button>}
      </PageHeader>
      {stale && (
        <Modal title="Someone else saved this item" onClose={() => setStale(false)}
          actions={<><button onClick={() => setStale(false)}>Keep editing</button><button className="primary" onClick={() => { setStale(false); void refresh(keys.libraryItem(), keys.libraryHistory()); }}>Reload their version</button></>}>
          <p>Another Admin saved a newer revision after you opened it. Reload to see theirs; your unsaved changes here will be replaced.</p>
        </Modal>)}
      <Tabs value={tab} onChange={setTab} tabs={[{ id: "settings", label: "Settings" }, { id: "used", label: `Used in (${it.usages.length})` }, { id: "history", label: "History" }]} />
      {tab === "settings" && (
        <div className="library-editor">
          <div className="card">
            <Field label="Name in the library" help="What people see when they pick it."><input aria-label="Name in the library" value={name} disabled={!edit} onChange={(e) => setName(e.target.value)} /></Field>
            {section && (
              <>
                <Field label="Section title"><input aria-label="Section title" value={section.title} disabled={!edit} onChange={(e) => setDef({ ...section, title: e.target.value })} /></Field>
                <label className="check"><input type="checkbox" checked={section.visible ?? true} disabled={!edit} onChange={(e) => setDef({ ...section, visible: e.target.checked })} /> Visible</label>
                <ConditionBuilder label="Show the section only if" value={section.show_if ?? null} onChange={(r) => setDef({ ...section, show_if: r })} fields={choices} />
                <AccessEditor value={section.access ?? {}} onChange={(a) => setDef({ ...section, access: a })} kind="inspection" disabled={!edit} />
                <h3>Fields in this section</h3>
                <ul className="lib-fields">{section.fields.map((f) => (
                  <li key={f.key} className={pick === f.key ? "on" : ""}>
                    <button className="link grow" title={f.key} onClick={() => setPick(f.key)}>{f.label || f.key}</button>
                    {edit && <>
                      <button className="icon-btn" aria-label={`Move ${f.label || f.key} up`} onClick={() => setDef(moveField(section, f.key, -1))}><ArrowUp size={14} aria-hidden /></button>
                      <button className="icon-btn" aria-label={`Move ${f.label || f.key} down`} onClick={() => setDef(moveField(section, f.key, 1))}><ArrowDown size={14} aria-hidden /></button>
                      <button className="icon-btn" aria-label={`Remove ${f.label || f.key}`} onClick={() => { setDef(removeFieldFrom(section, f.key)); if (pick === f.key) setPick(null); }}><Trash2 size={14} aria-hidden /></button></>}
                  </li>))}</ul>
                {edit && <button onClick={() => setAdding(true)}><Plus size={14} aria-hidden /> Add a field</button>}
              </>
            )}
            {openField && (
              <div style={{ marginTop: 14 }}>
                <FieldEditor field={asField(openField, 1)} choices={choices} lists={catalogue} categories={[]} readOnly={!edit} kind="inspection" onSave={(d) => setField(openField, d)} />
              </div>)}
          </div>
          <div className="card" aria-label="Preview">
            <h3>Preview</h3>
            <FormRenderer kind="inspection" tree={tree} values={values} onChange={(k, v) => setValues({ ...values, [k]: v })} preview role="expert" />
          </div>
        </div>
      )}
      {tab === "used" && (
        <div className="table-card">
          {it.usages.length === 0 ? <Empty title="Not used yet">Add it to a form from the builder: Add question › From the library.</Empty> : (
            <table className="rows"><thead><tr><th>Form</th><th>Version</th><th>State</th></tr></thead>
              <tbody>{it.usages.map((u, i) => <tr key={i}><td>{u.form}</td><td>v{u.version}</td><td><Pill tone={u.status === "draft" ? "warn" : "ok"}>{u.status === "draft" ? "Draft" : "Live"}</Pill></td></tr>)}</tbody></table>)}
        </div>
      )}
      {tab === "history" && (
        <div className="table-card">
          <table className="rows"><thead><tr><th>Revision</th><th>Who</th><th>When</th><th>What changed</th><th><span className="sr-only">Actions</span></th></tr></thead>
            <tbody>{(history.data ?? []).map((h) => (
              <tr key={h.revision}><td>r{h.revision}{h.revision === it.revision && <> <Pill tone="ok">current</Pill></>}</td><td title={h.by_login}>{h.by || "—"}</td><td>{when(h.at)}</td>
                <td>{h.changed_keys.length ? h.changed_keys.join(", ") : "created"}</td>
                <td>{edit && h.revision !== it.revision && <button aria-label={`Restore revision ${h.revision}`} onClick={() => { setDef(h.definition); setName(h.name); setTab("settings"); say(`Revision ${h.revision} is loaded. Save to make it the newest.`); }}>Restore</button>}</td></tr>))}</tbody></table>
        </div>
      )}
      {error && <p className="error" role="alert">{error}</p>}
      {edit && (
        <div className={dirty ? "save-bar" : "bar"} style={{ marginTop: 14 }}>
          <span className="grow muted small">{dirty ? "Unsaved changes. Forms using this item show “update available” after you save." : `Used in ${it.usages.length} form${it.usages.length === 1 ? "" : "s"}.`}</span>
          <button disabled={save.isPending || (it.usages.length === 0 && !dirty)} onClick={() => (dirty ? void saveThen() : setReview(it.revision))}>Save and update everywhere…</button>
          <button className="primary" disabled={!dirty || save.isPending} onClick={() => save.mutate()}>Save</button>
        </div>
      )}
      {adding && section && <AddFieldHere onClose={() => setAdding(false)} existing={section.fields.map((f) => f.key)} onAdd={(f) => { setDef(addFieldTo(section, f)); setPick(f.key); setAdding(false); }} />}
      {review !== null && <PushReview itemId={id} itemName={name} revision={review} onClose={() => setReview(null)} onDone={() => void refresh(keys.library(), keys.libraryItem(), keys.forms())} />}
    </>
  );
}

function AddFieldHere({ onAdd, onClose, existing }: { onAdd: (f: FieldDef) => void; onClose: () => void; existing: string[] }) {
  const [label, setLabel] = useState("");
  const [key, setKey] = useState("");
  const [type, setType] = useState("short_text");
  const taken = existing.includes(key);
  const ok = label.trim() && /^[a-z][a-z0-9_]{1,62}$/.test(key) && !taken;
  return (
    <Modal title="Add a field to this section" onClose={onClose} actions={<><button onClick={onClose}>Cancel</button><button className="primary" disabled={!ok} onClick={() => onAdd(newFieldDef(key, label.trim(), type))}>Add</button></>}>
      <Field label="Label"><input aria-label="Label" value={label} onChange={(e) => { setLabel(e.target.value); if (!key || key === slugKey(label)) setKey(slugKey(e.target.value)); }} /></Field>
      <Field label="Key" help={taken ? "This section already has a field with that key." : "Used by the API and reports. It can never change."}><input aria-label="Key" value={key} onChange={(e) => setKey(e.target.value)} /></Field>
      <Field label="Type"><select aria-label="Type" value={type} onChange={(e) => setType(e.target.value)}>
        {FIELD_TYPES.filter((t) => !["derived", "rating", "image"].includes(t.id)).map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}</select></Field>
    </Modal>
  );
}
