import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import { useList, useRefresh } from "../../api/hooks";
import { useAuth } from "../../auth";
import { Modal, Pill, useToast } from "../../ui/kit";

type Item = { id: number; kind: "field" | "section"; key: string; name: string; revision: number; archived: boolean; definition: unknown };
type Usage = { form: string; version: number; status: string; kind?: string; key?: string; label?: string };

export function Library() {
  const { can } = useAuth();
  const { say, fail } = useToast();
  const refresh = useRefresh();
  const items = useList<Item>("library", "library");
  const [open, setOpen] = useState<Item | null>(null);
  const detail = useQuery({ queryKey: ["library-item", open?.id], enabled: !!open, queryFn: () => api<Item & { usages: Usage[] }>(`library/${open!.id}`) });
  const archive = useMutation({
    mutationFn: (i: Item) => api(`library/${i.id}`, { method: "PATCH", body: { archived: !i.archived } }),
    onSuccess: () => { say("Done."); void refresh("library"); },
    onError: fail,
  });
  return (
    <>
      <h1>Library</h1>
      <p className="muted">Reusable fields and sections. A form can link to an item (changes arrive as an “update available” you accept) or copy it. Add items from the form builder with “Save to library”.</p>
      <table><thead><tr><th>Name</th><th>Kind</th><th>Key</th><th>Revision</th><th /></tr></thead>
        <tbody>{(items.data ?? []).map((i) => (
          <tr key={i.id} className="click" onClick={() => setOpen(i)}>
            <td>{i.name}</td><td>{i.kind}</td><td className="mono">{i.key}</td><td>r{i.revision}</td>
            <td>{i.archived && <Pill tone="warn">Archived</Pill>}</td></tr>))}</tbody></table>
      {open && (
        <Modal title={open.name} onClose={() => setOpen(null)}
          actions={<>{can("library.edit") && <button onClick={() => { archive.mutate(open); setOpen(null); }}>{open.archived ? "Restore" : "Archive"}</button>}<button onClick={() => setOpen(null)}>Close</button></>}>
          <h3>Used in</h3>
          {(detail.data?.usages ?? []).length === 0 && <p className="muted">Not used anywhere yet.</p>}
          <ul>{(detail.data?.usages ?? []).map((u, n) => <li key={n}>{u.form} v{u.version} <Pill>{u.status}</Pill></li>)}</ul>
          <h3>Definition</h3>
          <pre className="mono" style={{ overflow: "auto", maxHeight: 260 }}>{JSON.stringify(detail.data?.definition ?? open.definition, null, 1)}</pre>
        </Modal>
      )}
    </>
  );
}
