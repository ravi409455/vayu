import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import { useList } from "../../api/hooks";
import type { User } from "../../api/types";
import { useAuth } from "../../auth";
import { PageHeader } from "../../ui/kit";

type Row = { period: string; key: string; count: number };
const BY = { type: "Inspection type", city: "City", expert: "Expert", stage: "Stage", lead_owner: "Lead owner" } as const;

/** Rows -> one line per period with a count per key, for a simple table and bars. */
export function pivot(rows: Row[]): { periods: string[]; keys: string[]; cell: (p: string, k: string) => number } {
  const periods = [...new Set(rows.map((r) => r.period))].sort();
  const keys = [...new Set(rows.map((r) => r.key))].sort();
  const m = new Map(rows.map((r) => [`${r.period}|${r.key}`, r.count]));
  return { periods, keys, cell: (p, k) => m.get(`${p}|${k}`) ?? 0 };
}

export function Dashboards() {
  const { can } = useAuth();
  const [group, setGroup] = useState("day");
  const [by, setBy] = useState<keyof typeof BY>("type");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const users = useList<User>("users-all", "users");
  const q = useQuery({ queryKey: ["volume", group, by, from, to], queryFn: () => api<{ rows: Row[] }>("dashboards/volume", { query: { group, by, date_from: from, date_to: to } }) });
  const rows = q.data?.rows ?? [];
  const { periods, keys, cell } = pivot(rows);
  const name = (k: string) => (by === "expert" || by === "lead_owner") && k ? (users.data ?? []).find((u) => String(u.id) === k)?.name ?? k : k || "—";
  const max = Math.max(1, ...rows.map((r) => r.count));
  const csv = `/api/v1/dashboards/volume?${new URLSearchParams({ group, by, date_from: from, date_to: to, export: "csv" })}`;
  return (
    <>
      <PageHeader title="Dashboards" subtitle="How many bookings, by day, week or month." tip="Split the numbers by inspection type, city, expert, stage or lead owner. The CSV has exactly what the table shows.">
        {can("dashboards.export") && <a className="btn" href={csv} download>Export CSV</a>}</PageHeader>
      <div className="card"><div className="grid2">
        <select aria-label="Group by time" value={group} onChange={(e) => setGroup(e.target.value)}><option value="day">By day</option><option value="week">By week</option><option value="month">By month</option></select>
        <select aria-label="Split by" value={by} onChange={(e) => setBy(e.target.value as keyof typeof BY)}>{Object.entries(BY).map(([k, l]) => <option key={k} value={k}>Split by {l.toLowerCase()}</option>)}</select>
        <input aria-label="From" type="date" value={from} onChange={(e) => setFrom(e.target.value)} /><input aria-label="To" type="date" value={to} onChange={(e) => setTo(e.target.value)} /></div></div>
      {rows.length === 0 ? <p className="muted pad">No bookings in this range.</p> : (
        <table aria-label="Bookings volume"><thead><tr><th>Period</th>{keys.map((k) => <th key={k}>{name(k)}</th>)}</tr></thead>
          <tbody>{periods.map((p) => <tr key={p}><td>{p}</td>{keys.map((k) => { const n = cell(p, k); return <td key={k}>{n > 0 && <div style={{ display: "flex", alignItems: "center", gap: 6 }}><div style={{ background: "var(--brand)", height: 10, width: `${(n / max) * 80}px`, borderRadius: 3 }} /> {n}</div>}</td>; })}</tr>)}</tbody></table>)}
    </>
  );
}
