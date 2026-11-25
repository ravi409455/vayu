import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import { fetchAll, useList, useRefresh } from "../../api/hooks";
import type { MasterList, MasterListItem } from "../../api/types";
import { useAuth } from "../../auth";
import { Empty, LoadError, PageHeader, Pill, useToast } from "../../ui/kit";
import { slugKey } from "../../lib/fieldTypes";
import { keys } from "../../api/keys";

export function MasterLists() {
  const { can } = useAuth();
  const { say, fail } = useToast();
  const refresh = useRefresh();
  const lists = useList<MasterList>(keys.masterLists(), "master-lists");
  const [open, setOpen] = useState<MasterList | null>(null);
  const [item, setItem] = useState({ key: "", label: "", keyTouched: false });
  const manage = can("master_lists.manage");
  const items = useQuery({
    queryKey: keys.listItems((open ?? lists.data?.[0])?.key, true),
    enabled: !!(open ?? lists.data?.[0]),
    queryFn: ({ signal }) => fetchAll<MasterListItem>(`master-lists/${(open ?? lists.data![0])!.key}/items`, { include_archived: 1 }, signal),
  });
  const add = useMutation({
    mutationFn: () => api(`master-lists/${(open ?? lists.data![0])!.key}/items`, { body: { key: item.key, label: item.label } }),
    onSuccess: () => { setItem({ key: "", label: "", keyTouched: false }); say("Added."); void refresh(keys.listItems()); },
    onError: fail,
  });
  const patch = useMutation({
    mutationFn: (v: { id: number; body: Record<string, unknown> }) => api(`master-list-items/${v.id}`, { method: "PATCH", body: v.body }),
    onSuccess: () => { say("Saved."); void refresh(keys.listItems()); },
    onError: fail,
  });
  const current = open ?? (lists.data ?? [])[0] ?? null;
  return (
    <>
      <PageHeader title="Master lists" subtitle="The choices dropdowns offer: cities, car models, reasons…" />
      {lists.isError && <LoadError error={lists.error} what="master lists" onRetry={lists.refetch} />}
      <div className="split-view">
        <nav className="card list-nav" aria-label="Lists">
          {(lists.data ?? []).map((l) => (
            <button key={l.id} className={`tree-item${current?.id === l.id ? " on" : ""}`} aria-current={current?.id === l.id} onClick={() => setOpen(l)}>
              <span className="grow">{l.name}</span></button>))}
        </nav>
        {current && (
          <section className="table-card" aria-label={current.name}>
            <h2 className="table-title">{current.name} <span className="muted small mono">{current.key}</span></h2>
            <table className="rows"><thead><tr><th>Label</th><th>Key</th><th>Status</th><th><span className="sr-only">Actions</span></th></tr></thead>
              <tbody>{(items.data ?? []).map((i) => (
                <tr key={i.id} className={i.archived ? "muted" : ""}>
                  <td>{manage ? <input aria-label={`Label of ${i.key}`} defaultValue={i.label} onBlur={(e) => e.target.value !== i.label && patch.mutate({ id: i.id, body: { label: e.target.value } })} /> : i.label}</td>
                  <td className="mono small">{i.key}</td>
                  <td>{i.archived ? <Pill tone="warn">Archived</Pill> : <Pill tone="ok">In use</Pill>}</td>
                  <td style={{ textAlign: "right" }}>{manage && <button className="sm" onClick={() => patch.mutate({ id: i.id, body: { archived: !i.archived } })}>{i.archived ? "Restore" : "Archive"}</button>}</td>
                </tr>))}</tbody></table>
            {items.data && items.data.length === 0 && <Empty>This list is empty.</Empty>}
            {manage && <div className="table-foot add-item">
              <input aria-label="Label" placeholder="New item label" value={item.label} onChange={(e) => setItem({ ...item, label: e.target.value, key: item.keyTouched ? item.key : slugKey(e.target.value) })} />
              <input aria-label="New key" placeholder="key" className="mono" value={item.key} onChange={(e) => setItem({ ...item, key: e.target.value, keyTouched: true })} />
              <button className="primary sm" disabled={!item.key || !item.label} onClick={() => add.mutate()}>Add item</button></div>}
          </section>)}
      </div>
    </>
  );
}
