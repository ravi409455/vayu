import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import { asList, useList, useRefresh } from "../../api/hooks";
import type { MasterList, MasterListItem } from "../../api/types";
import { useAuth } from "../../auth";
import { Field, Modal, Pill, useToast, PageHeader } from "../../ui/kit";

export function MasterLists() {
  const { can } = useAuth();
  const { say, fail } = useToast();
  const refresh = useRefresh();
  const lists = useList<MasterList>("master-lists", "master-lists");
  const [open, setOpen] = useState<MasterList | null>(null);
  const [item, setItem] = useState({ key: "", label: "" });
  const manage = can("master_lists.manage");
  const items = useQuery({
    queryKey: ["master-list-items", open?.key],
    enabled: !!open,
    queryFn: async () => asList<MasterListItem>(await api(`master-lists/${open!.key}/items`, { query: { include_archived: 1 } })),
  });
  const add = useMutation({
    mutationFn: () => api(`master-lists/${open!.key}/items`, { body: { key: item.key, label: item.label } }),
    onSuccess: () => { setItem({ key: "", label: "" }); void refresh("master-list-items"); },
    onError: fail,
  });
  const patch = useMutation({
    mutationFn: (v: { id: number; body: Record<string, unknown> }) => api(`master-list-items/${v.id}`, { method: "PATCH", body: v.body }),
    onSuccess: () => { say("Saved."); void refresh("master-list-items"); },
    onError: fail,
  });
  return (
    <>
      <PageHeader title="Master lists" subtitle="The choices that dropdowns offer: cities, inspection types, cancel reasons, car models."
        tip="Each item has a permanent key (used by reports and the API) and a label people see. Keys never change; to stop offering something, archive it: old bookings keep showing it." />
      <table><thead><tr><th>List</th><th>Key</th><th /></tr></thead>
        <tbody>{(lists.data ?? []).map((l) => (
          <tr key={l.id} className="click" onClick={() => setOpen(l)}><td>{l.name}</td><td className="mono">{l.key}</td><td><button className="link">Open</button></td></tr>
        ))}</tbody></table>
      {open && (
        <Modal title={open.name} onClose={() => setOpen(null)}>
          <table><tbody>{(items.data ?? []).map((i) => (
            <tr key={i.id}>
              <td className="mono">{i.key}</td>
              <td>{manage ? <input defaultValue={i.label} onBlur={(e) => e.target.value !== i.label && patch.mutate({ id: i.id, body: { label: e.target.value } })} /> : i.label}</td>
              <td>{i.archived ? <Pill tone="warn">Archived</Pill> : null}</td>
              <td>{manage && <button className="link" onClick={() => patch.mutate({ id: i.id, body: { archived: !i.archived } })}>{i.archived ? "Restore" : "Archive"}</button>}</td>
            </tr>))}</tbody></table>
          {manage && <div className="bar" style={{ marginTop: 12 }}>
            <Field label="New key"><input aria-label="New key" value={item.key} onChange={(e) => setItem({ ...item, key: e.target.value })} /></Field>
            <Field label="Label"><input aria-label="Label" value={item.label} onChange={(e) => setItem({ ...item, label: e.target.value })} /></Field>
            <button className="primary" disabled={!item.key || !item.label} onClick={() => add.mutate()}>Add</button></div>}
        </Modal>
      )}
    </>
  );
}
