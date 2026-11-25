import { Link2, Search } from "lucide-react";
import { useMemo, useState } from "react";
import { useList } from "../../../api/hooks";
import { defaultConfig, FIELD_TYPES, iconFor, slugKey, typeLabel } from "../../../lib/fieldTypes";
import { Field, Modal, Tabs } from "../../../ui/kit";
import { keys } from "../../../api/keys";

type LibItem = { id: number; kind: "field" | "section"; key: string; name: string; revision: number; archived: boolean; definition: { type?: string; fields?: unknown[] } };

/** Step 1: pick what kind of question. Step 2: name it. Or take a ready-made one from the library. */
export function AddFieldDialog({ sectionTitle, onClose, onAdd, onLibrary }: {
  sectionTitle: string; onClose: () => void; onAdd: (body: Record<string, unknown>) => void; onLibrary: (itemId: number, link: boolean) => void;
}) {
  const [tab, setTab] = useState<"new" | "library">("new");
  const [q, setQ] = useState("");
  const [type, setType] = useState<string | null>(null);
  const [label, setLabel] = useState("");
  const [key, setKey] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const lib = useList<LibItem>(keys.library(), "library", { kind: "field" });
  // Key Checks now live on their own tab: the old Yes/No field is no longer offered
  const groups = useMemo(() => [...new Set(FIELD_TYPES.map((t) => t.group))].filter((g) => g !== "Old"), []);
  const match = (s: string) => s.toLowerCase().includes(q.trim().toLowerCase());
  return (
    <Modal title={`Add a field to “${sectionTitle}”`} onClose={onClose}
      actions={type ? <><button onClick={() => setType(null)}>Back</button>
        <button className="primary" disabled={!label || !key || (type === "image" && !file)} onClick={() => onAdd({ key, label, type, config: defaultConfig(type), ...(file ? { __file: file } : {}) })}>Add field</button>
        </> : <button onClick={onClose}>Cancel</button>}>
      {!type && (
        <>
          <Tabs value={tab} onChange={setTab} tabs={[{ id: "new", label: "New question" }, { id: "library", label: "From the library" }]} />
          <div className="searchbox"><Search size={15} aria-hidden /><input aria-label="Search field types" placeholder="Search: photo, number, choice…" value={q} onChange={(e) => setQ(e.target.value)} /></div>
        </>
      )}
      {!type && tab === "new" && groups.map((g) => {
        const types = FIELD_TYPES.filter((t) => t.group === g && match(t.label + t.id));
        return types.length === 0 ? null : (
          <div key={g}><h3>{g}</h3>
            <div className="tiles">{types.map((t) => { const I = iconFor(t.id); return (
              <button key={t.id} type="button" className="tile" onClick={() => setType(t.id)}><span className="type-badge"><I size={16} aria-hidden /></span><strong>{t.label}</strong></button>); })}</div></div>);
      })}
      {!type && tab === "library" && (
        <>
          {(lib.data ?? []).filter((i) => !i.archived && match(i.name + i.key)).map((i) => (
            <div className="bar card" key={i.id} style={{ padding: 10, marginBottom: 8 }}>
              <div className="grow"><strong>{i.name}</strong><div className="muted small">{typeLabel(i.definition.type ?? "")} · r{i.revision}</div></div>
              <button title="Stays in sync: changes to the library item reach this form as an update you accept" onClick={() => onLibrary(i.id, true)}><Link2 size={14} aria-hidden /> Link</button>
              <button title="A plain copy you can edit freely" onClick={() => onLibrary(i.id, false)}>Copy</button>
            </div>
          ))}
          {(lib.data ?? []).filter((i) => !i.archived).length === 0 && <p className="empty-state">The library has no fields yet. Use “Save to library” on any field to add one.</p>}
        </>
      )}
      {type && (
        <>
          <Field label="Label" tip="What the person sees above the field."><input autoFocus value={label} onChange={(e) => { setLabel(e.target.value); if (!key || key === slugKey(label)) setKey(slugKey(e.target.value)); }} /></Field>
          <Field label="Key" tip="A short name used by reports, the API and integrations. It can never change, so pick it carefully." help="Lowercase letters, numbers and underscores."><input value={key} onChange={(e) => setKey(e.target.value)} /></Field>
          {type === "image" && <Field label="Picture" tip="PNG or JPEG, up to 2 MB, shown to the expert in the form." help="Choose the picture to show."><input type="file" accept="image/png,image/jpeg" aria-label="Choose the picture" onChange={(e) => setFile(e.target.files?.[0] ?? null)} /></Field>}
        </>
      )}
    </Modal>
  );
}

export function AddSectionDialog({ onClose, onBlank, onLibrary }: { onClose: () => void; onBlank: (title: string) => void; onLibrary: (itemId: number, link: boolean) => void }) {
  const [title, setTitle] = useState("");
  const lib = useList<LibItem>(keys.library(), "library", { kind: "section" });
  const items = (lib.data ?? []).filter((i) => !i.archived);
  return (
    <Modal title="Add a section" onClose={onClose} actions={<><button onClick={onClose}>Cancel</button><button className="primary" disabled={!title.trim()} onClick={() => onBlank(title.trim())}>Add blank section</button></>}>
      <Field label="Section name" tip="A group of related questions, shown as one card."><input autoFocus value={title} onChange={(e) => setTitle(e.target.value)} onKeyDown={(e) => e.key === "Enter" && title.trim() && onBlank(title.trim())} /></Field>
      <h3>Or start from the library</h3>
      {items.map((i) => (
        <div className="bar card" key={i.id} style={{ padding: 10, marginBottom: 8 }}>
          <div className="grow"><strong>{i.name}</strong><div className="muted small">{(i.definition.fields ?? []).length} fields · r{i.revision}</div></div>
          <button onClick={() => onLibrary(i.id, true)}><Link2 size={14} aria-hidden /> Link</button>
          <button onClick={() => onLibrary(i.id, false)}>Copy</button>
        </div>
      ))}
      {items.length === 0 && <p className="muted small">No library sections yet.</p>}
    </Modal>
  );
}
