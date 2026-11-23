import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, type Page } from "../../api/client";
import { when, PageHeader } from "../../ui/kit";

type Row = { id: number; actor_username: string | null; action: string; target_type: string; summary: string; created_at: string };

export function Audit() {
  const [action, setAction] = useState("");
  const [page, setPage] = useState(1);
  const q = useQuery({ queryKey: ["audit", action, page], queryFn: () => api<Page<Row>>("audit-logs", { query: { action, page } }) });
  return (
    <>
      <PageHeader title="Audit log" subtitle="Who changed what: forms, templates, users, roles, integrations and API keys."
        tip="Entries cannot be edited or deleted. Type the start of an action to filter, for example “form.” for everything about forms.">
        <input style={{ maxWidth: 260 }} placeholder="Filter by action, e.g. form.publish" value={action} onChange={(e) => { setAction(e.target.value); setPage(1); }} /></PageHeader>
      <table><thead><tr><th>When</th><th>Who</th><th>Action</th><th>What</th></tr></thead>
        <tbody>{(q.data?.results ?? []).map((r) => (
          <tr key={r.id}><td>{when(r.created_at)}</td><td>{r.actor_username ?? "system"}</td><td className="mono">{r.action}</td><td>{r.summary}</td></tr>))}</tbody></table>
      <div className="bar" style={{ marginTop: 10 }}>
        <button disabled={!q.data?.previous} onClick={() => setPage(page - 1)}>Newer</button>
        <button disabled={!q.data?.next} onClick={() => setPage(page + 1)}>Older</button>
        <span className="muted">{q.data?.count ?? 0} entries</span></div>
    </>
  );
}
