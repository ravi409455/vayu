import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { api } from "../../api/client";
import { useList, useRefresh } from "../../api/hooks";
import { useAuth } from "../../auth";
import { slugKey } from "../../lib/fieldTypes";
import { newFieldDef } from "../../lib/libraryDef";
import { Field, Modal, PageHeader, Pill, useToast } from "../../ui/kit";

type Item = { id: number; kind: "field" | "section"; key: string; name: string; revision: number; archived: boolean; used_in: number };

export function Library() {
  const { can } = useAuth();
  const { fail } = useToast();
  const nav = useNavigate();
  const refresh = useRefresh();
  const [q, setQ] = useState("");
  const [kind, setKind] = useState("");
  const [archived, setArchived] = useState(false);
  const items = useList<Item>("library", "library", { q: q || undefined, kind: kind || undefined, include_archived: archived ? 1 : undefined });
  const [creating, setCreating] = useState(false);
  const [n, setN] = useState({ kind: "section", name: "", key: "" });
  const create = useMutation({
    mutationFn: () => api<Item>("library", { body: { kind: n.kind, key: n.key, name: n.name, definition: n.kind === "field" ? newFieldDef(n.key, n.name, "short_text") : { title: n.name, visible: true, fields: [newFieldDef("first_field", "First field", "short_text")] } } }),
    onSuccess: (r) => { void refresh("library"); nav(`/library/${r.id}`); },
    onError: fail,
  });
  const rows = items.data ?? [];
  return (
    <>
      <PageHeader title="Library" subtitle="Reusable fields and sections: built once, used in many forms, and updated everywhere from one place.">
        {can("library.edit") && <button className="primary" onClick={() => setCreating(true)}>New item</button>}</PageHeader>
      <div className="card"><div className="grid2">
        <input aria-label="Search the library" placeholder="Search by name or key" value={q} onChange={(e) => setQ(e.target.value)} />
        <select aria-label="Kind" value={kind} onChange={(e) => setKind(e.target.value)}><option value="">Fields and sections</option><option value="field">Fields</option><option value="section">Sections</option></select>
        <label className="check"><input type="checkbox" checked={archived} onChange={(e) => setArchived(e.target.checked)} /> Show archived</label>
      </div></div>
      {rows.length === 0 && <div className="card empty-state"><strong>{q || kind ? "Nothing matches" : "The library is empty"}</strong><p>{q || kind ? "Try another search." : "Create an item here, or open a form in the builder and choose “Save to library” on a field or a section."}</p></div>}
      {rows.length > 0 && (
        <table><thead><tr><th>Name</th><th>Kind</th><th>Key</th><th>Revision</th><th>Used in</th><th /></tr></thead>
          <tbody>{rows.map((i) => (
            <tr key={i.id}>
              <td><Link to={`/library/${i.id}`}>{i.name}</Link></td><td>{i.kind}</td><td className="mono">{i.key}</td><td>r{i.revision}</td>
              <td>{i.used_in === 0 ? <span className="muted">no form</span> : `${i.used_in} form${i.used_in === 1 ? "" : "s"}`}</td>
              <td>{i.archived && <Pill tone="warn">Archived</Pill>}</td></tr>))}</tbody></table>)}
      {creating && (
        <Modal title="New library item" onClose={() => setCreating(false)}
          actions={<><button onClick={() => setCreating(false)}>Cancel</button><button className="primary" disabled={!n.name.trim() || !/^[a-z][a-z0-9_]{1,62}$/.test(n.key)} onClick={() => create.mutate()}>Create and open</button></>}>
          <Field label="What is it"><select aria-label="Item kind" value={n.kind} onChange={(e) => setN({ ...n, kind: e.target.value })}><option value="section">A section (several fields together)</option><option value="field">A single field</option></select></Field>
          <Field label="Name"><input aria-label="Name" value={n.name} onChange={(e) => setN({ ...n, name: e.target.value, key: slugKey(e.target.value) })} /></Field>
          <Field label="Key" help="Used by the API and reports. It can never change."><input aria-label="Key" value={n.key} onChange={(e) => setN({ ...n, key: e.target.value })} /></Field>
        </Modal>)}
    </>
  );
}
