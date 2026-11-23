import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, type Page } from "../../api/client";
import { useList } from "../../api/hooks";
import type { User } from "../../api/types";
import { fmtStamp } from "../../lib/format";
import { Empty, PageHeader } from "../../ui/kit";

type Row = { id: number; actor_username: string | null; action: string; target_type: string; summary: string; created_at: string };
const AREAS: [string, string][] = [["", "Everything"], ["form", "Forms"], ["library", "Library"], ["pdf_template", "PDF templates"], ["user", "Users"],
  ["role", "Roles"], ["integration", "Integrations"], ["api_key", "API keys"], ["booking", "Bookings"], ["master_list", "Master lists"]];

export function Audit() {
  const [f, setF] = useState({ action: "", actor: "", from: "", to: "" });
  const [page, setPage] = useState(1);
  const set = (p: Partial<typeof f>) => { setF({ ...f, ...p }); setPage(1); };
  const users = useList<User>("users-all", "users");
  const q = useQuery({ queryKey: ["audit", f, page], queryFn: () => api<Page<Row>>("audit-logs", { query: { ...f, page } }) });
  const rows = q.data?.results ?? [];
  return (
    <>
      <PageHeader title="Audit log" count={q.data?.count} />
      <div className="filters">
        <select aria-label="Area" className={f.action ? "set" : ""} value={f.action} onChange={(e) => set({ action: e.target.value })}>{AREAS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>
        <select aria-label="Who" className={f.actor ? "set" : ""} value={f.actor} onChange={(e) => set({ actor: e.target.value })}><option value="">Anyone</option>{(users.data ?? []).map((u) => <option key={u.id} value={u.id}>{u.name || u.username}</option>)}</select>
        <label className="date-range"><span>From</span><input aria-label="From" type="date" value={f.from} onChange={(e) => set({ from: e.target.value })} /><span>to</span><input aria-label="To" type="date" value={f.to} onChange={(e) => set({ to: e.target.value })} /></label>
      </div>
      <div className="table-card">
        <table className="rows"><thead><tr><th>When</th><th>Who</th><th>What happened</th><th>Action</th></tr></thead>
          <tbody>{rows.map((r) => (
            <tr key={r.id}><td className="nowrap">{fmtStamp(r.created_at)}</td><td>{r.actor_username ?? "system"}</td><td>{r.summary}</td><td className="mono small muted">{r.action}</td></tr>))}</tbody></table>
        {q.data && rows.length === 0 && <Empty>Nothing matches these filters.</Empty>}
        {q.data && (q.data.next || q.data.previous) && <div className="table-foot"><span className="grow muted">{q.data.count} entries</span>
          <button className="sm" disabled={!q.data.previous} onClick={() => setPage(page - 1)}>Newer</button>
          <button className="sm" disabled={!q.data.next} onClick={() => setPage(page + 1)}>Older</button></div>}
      </div>
    </>
  );
}
