import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { api, type Page } from "../../api/client";
import { asList, useList } from "../../api/hooks";
import { STAGE_LABEL, STAGE_TONE, useInspectionTypes, useLabels, useTypeLabels } from "../../api/labels";
import type { Booking, MasterListItem, User } from "../../api/types";
import { useAuth } from "../../auth";
import { loadJSON, saveJSON } from "../../lib/store";
import { Pill, PageHeader } from "../../ui/kit";

export type Filters = { search: string; city: string; expert: string; type: string; stage: string; date_from: string; date_to: string };
export const EMPTY: Filters = { search: "", city: "", expert: "", type: "", stage: "", date_from: "", date_to: "" };
export const todayIso = () => new Date().toISOString().slice(0, 10);

export function JobBoard() {
  const { me } = useAuth();
  const nav = useNavigate();
  const key = `vayu:board:${me?.id}`;
  const [f, setF] = useState<Filters>(() => loadJSON<Filters>(key, EMPTY));   // filters are remembered per person
  const [page, setPage] = useState(1);
  useEffect(() => saveJSON(key, f), [key, f]);
  const set = (p: Partial<Filters>) => { setF({ ...f, ...p }); setPage(1); };
  const q = useQuery({ queryKey: ["board", f, page], queryFn: () => api<Page<Booking>>("bookings", { query: { ...f, page } }) });
  const experts = useList<User>("experts", "users", { role: "expert" });
  const cities = useQuery({ queryKey: ["list-items", "city"], queryFn: async () => asList<MasterListItem>(await api("master-lists/city/items")) });
  const types = useInspectionTypes();
  const car = useLabels("car_make_model");
  const type = useTypeLabels();
  const nameOf = new Map((experts.data ?? []).map((u) => [u.id, u.name || u.username]));
  return (
    <>
      <PageHeader title="Job board" subtitle="Every booking, with filters that are remembered for you." tip="A read-only view of the bookings. Click a row to open the full booking. Your filters stay as you left them. To create or manage bookings use the Bookings page.">
        <button onClick={() => set({ date_from: todayIso(), date_to: todayIso() })}>Today</button>
        <button onClick={() => setF(EMPTY)}>Clear filters</button>
</PageHeader>
      <div className="card"><div className="grid2">
        <input aria-label="Search" placeholder="Search booking ID, customer, phone, chassis, car" value={f.search} onChange={(e) => set({ search: e.target.value })} />
        <select aria-label="City" value={f.city} onChange={(e) => set({ city: e.target.value })}><option value="">All cities</option>{(cities.data ?? []).map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}</select>
        <select aria-label="Expert" value={f.expert} onChange={(e) => set({ expert: e.target.value })}><option value="">All experts</option>{(experts.data ?? []).map((u) => <option key={u.id} value={u.id}>{u.name || u.username}</option>)}</select>
        <select aria-label="Type" value={f.type} onChange={(e) => set({ type: e.target.value })}><option value="">All types</option>{types.map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}</select>
        <select aria-label="Stage" value={f.stage} onChange={(e) => set({ stage: e.target.value })}><option value="">All stages</option>{Object.entries(STAGE_LABEL).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>
        <div className="bar" style={{ margin: 0 }}><input aria-label="From" type="date" value={f.date_from} onChange={(e) => set({ date_from: e.target.value })} /><input aria-label="To" type="date" value={f.date_to} onChange={(e) => set({ date_to: e.target.value })} /></div>
      </div></div>
      <table>
        <thead><tr><th>Booking</th><th>Customer</th><th>Car</th><th>Type</th><th>When</th><th>Expert</th><th>Stage</th></tr></thead>
        <tbody>{(q.data?.results ?? []).map((b) => (
          <tr key={b.id} className="click" onClick={() => nav(`/booking/${b.id}`)}>
            <td><Link to={`/booking/${b.id}`} onClick={(e) => e.stopPropagation()}>{b.booking_id}</Link></td>
            <td>{String(b.answers.customer_name ?? "")}</td><td>{car(b.answers.car_make_model)}</td><td>{type(b.inspection_type)}</td>
            <td>{String(b.answers.inspection_date ?? "")} {String(b.answers.inspection_time ?? "")}</td>
            <td>{b.assigned_expert ? nameOf.get(b.assigned_expert) ?? `#${b.assigned_expert}` : <span className="muted">—</span>}</td>
            <td><Pill tone={STAGE_TONE[b.stage]}>{STAGE_LABEL[b.stage] ?? b.stage}</Pill>{b.conflict && <> <Pill tone="bad">Conflict</Pill></>}</td></tr>))}</tbody>
      </table>
      {q.data && q.data.results.length === 0 && <p className="muted pad">No bookings match.</p>}
      <div className="bar" style={{ marginTop: 10 }}>
        <button disabled={!q.data?.previous} onClick={() => setPage(page - 1)}>Previous</button>
        <button disabled={!q.data?.next} onClick={() => setPage(page + 1)}>Next</button>
        <span className="muted">{q.data?.count ?? 0} bookings</span></div>
    </>
  );
}
