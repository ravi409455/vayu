import { ExternalLink, Plus, Trash2, XCircle } from "lucide-react";
import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { api, type Page } from "../../api/client";
import { asList, useList, useRefresh } from "../../api/hooks";
import { STAGE_LABEL, STAGE_TONE, useLabels } from "../../api/labels";
import type { Booking, MasterListItem, User } from "../../api/types";
import { useAuth } from "../../auth";
import { Confirm, PageHeader, Pill, useToast } from "../../ui/kit";
import { Actions } from "./Booking";

/** Admin may delete any booking; Ops only one that is still an untouched draft. */
export function canDelete(role: string, stage: string): boolean {
  return role === "admin" || stage === "draft";
}

/** Create, find, open, cancel and delete bookings. Opening one shows the full booking page. */
export function Bookings() {
  const { me, can } = useAuth();
  const nav = useNavigate();
  const { say, fail } = useToast();
  const refresh = useRefresh();
  const [f, setF] = useState({ search: "", stage: "", city: "", type: "" });
  const [page, setPage] = useState(1);
  const [cancelling, setCancelling] = useState<Booking | null>(null);
  const [deleting, setDeleting] = useState<Booking | null>(null);
  const set = (p: Partial<typeof f>) => { setF({ ...f, ...p }); setPage(1); };
  const q = useQuery({ queryKey: ["bookings-page", f, page], queryFn: () => api<Page<Booking>>("bookings", { query: { ...f, page } }) });
  const experts = useList<User>("experts", "users", { role: "expert" });
  const cities = useQuery({ queryKey: ["list-items", "city"], queryFn: async () => asList<MasterListItem>(await api("master-lists/city/items")) });
  const types = useQuery({ queryKey: ["list-items", "inspection_type"], queryFn: async () => asList<MasterListItem>(await api("master-lists/inspection_type/items")) });
  const car = useLabels("car_make_model");
  const type = useLabels("inspection_type");
  const nameOf = new Map((experts.data ?? []).map((u) => [u.id, u.name || u.username]));
  const remove = useMutation({
    mutationFn: (b: Booking) => api(`bookings/${b.id}`, { method: "DELETE" }),
    onSuccess: () => { setDeleting(null); say("Booking deleted."); void refresh("bookings-page"); },
    onError: (e) => { setDeleting(null); fail(e); },
  });
  return (
    <>
      <PageHeader title="Bookings" subtitle="Create, find and manage every booking. Open one for the full details."
        tip="This is where bookings are created and managed. The Job board is a read-only view of the same bookings. Admin can delete any booking; Ops can only delete a draft nobody has worked on (use Cancel for the rest).">
        {can("bookings.create") && <button className="primary" onClick={() => nav("/booking/new")}><Plus size={15} aria-hidden /> New booking</button>}
      </PageHeader>
      <div className="card"><div className="grid2">
        <input aria-label="Search" placeholder="Search booking ID, customer, phone, chassis, car" value={f.search} onChange={(e) => set({ search: e.target.value })} />
        <select aria-label="Stage" value={f.stage} onChange={(e) => set({ stage: e.target.value })}><option value="">All stages</option>{Object.entries(STAGE_LABEL).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>
        <select aria-label="City" value={f.city} onChange={(e) => set({ city: e.target.value })}><option value="">All cities</option>{(cities.data ?? []).map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}</select>
        <select aria-label="Type" value={f.type} onChange={(e) => set({ type: e.target.value })}><option value="">All types</option>{(types.data ?? []).map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}</select>
      </div></div>
      <table>
        <thead><tr><th>Booking</th><th>Customer</th><th>Car</th><th>Type</th><th>When</th><th>Expert</th><th>Status</th><th /></tr></thead>
        <tbody>{(q.data?.results ?? []).map((b) => (
          <tr key={b.id}>
            <td><Link to={`/booking/${b.id}`}>{b.booking_id}</Link></td>
            <td>{String(b.answers.customer_name ?? "")}</td><td>{car(b.answers.car_make_model)}</td><td>{type(b.inspection_type)}</td>
            <td>{String(b.answers.inspection_date ?? "")} {String(b.answers.inspection_time ?? "")}</td>
            <td>{b.assigned_expert ? nameOf.get(b.assigned_expert) ?? `#${b.assigned_expert}` : <span className="muted">—</span>}</td>
            <td><Pill tone={STAGE_TONE[b.stage]}>{STAGE_LABEL[b.stage] ?? b.stage}</Pill>{b.conflict && <> <Pill tone="bad">Conflict</Pill></>}</td>
            <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
              <button className="icon-btn" aria-label={`Open ${b.booking_id}`} title="Open" onClick={() => nav(`/booking/${b.id}`)}><ExternalLink size={16} aria-hidden /></button>
              {can("bookings.cancel") && b.stage !== "cancelled" && b.stage !== "completed" && <button className="icon-btn" aria-label={`Cancel ${b.booking_id}`} title="Cancel booking" onClick={() => setCancelling(b)}><XCircle size={16} aria-hidden /></button>}
              {can("bookings.delete") && canDelete(me?.role ?? "", b.stage) && <button className="icon-btn" aria-label={`Delete ${b.booking_id}`} title="Delete" onClick={() => setDeleting(b)}><Trash2 size={16} aria-hidden /></button>}
            </td></tr>))}</tbody>
      </table>
      {q.data && q.data.results.length === 0 && <p className="muted pad">No bookings match.</p>}
      <div className="bar" style={{ marginTop: 10 }}>
        <button disabled={!q.data?.previous} onClick={() => setPage(page - 1)}>Previous</button>
        <button disabled={!q.data?.next} onClick={() => setPage(page + 1)}>Next</button>
        <span className="muted">{q.data?.count ?? 0} bookings</span></div>
      {cancelling && <Actions kind="cancel" booking={cancelling} experts={[]} onClose={() => setCancelling(null)} fail={fail} onDone={() => { setCancelling(null); say("Cancelled."); void refresh("bookings-page"); }} />}
      {deleting && (
        <Confirm title={`Delete ${deleting.booking_id}?`} danger confirmLabel="Delete booking" onCancel={() => setDeleting(null)} onConfirm={() => remove.mutate(deleting)}>
          <p>The booking{deleting.stage === "draft" ? "" : " and everything recorded on it"} is removed for good. This cannot be undone and is written to the audit log.</p>
          {me?.role !== "admin" && <p className="muted small">Ops can only delete a draft that nobody has worked on. To stop a booking that is under way, cancel it instead.</p>}
        </Confirm>)}
    </>
  );
}
