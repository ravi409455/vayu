import { LayoutGrid, List, Plus } from "lucide-react";
import { useEffect, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api, type Page } from "../../api/client";
import { asList, useList, useRefresh } from "../../api/hooks";
import { STAGE_LABEL, STAGE_TONE, useInspectionTypes, useLabels, useTypeLabels } from "../../api/labels";
import type { Booking, MasterListItem, User } from "../../api/types";
import { useAuth } from "../../auth";
import { addDays, fmtSlot, today } from "../../lib/format";
import { loadJSON, saveJSON } from "../../lib/store";
import { ExpertCell } from "../../ui/ExpertCell";
import { Confirm, Empty, PageHeader, Pill, useToast } from "../../ui/kit";
import { MoreMenu } from "../../ui/Menu";
import { Actions } from "./Booking";

/** Admin may delete any booking; Ops only one that is still an untouched draft. */
export function canDelete(role: string, stage: string): boolean {
  return role === "admin" || stage === "draft";
}

export type View = "today" | "unassigned" | "in_progress" | "uploading" | "upcoming" | "completed" | "all";
export type Filters = { search: string; city: string; expert: string; type: string; stage: string; date_from: string; date_to: string };
export const EMPTY: Filters = { search: "", city: "", expert: "", type: "", stage: "", date_from: "", date_to: "" };

/** What each saved view asks the server for (on top of the person's own filters). */
export function viewQuery(view: View, now = new Date()): Record<string, string> {
  const t = today(now);
  switch (view) {
    case "today": return { date_from: t, date_to: t, order: "schedule" };
    case "unassigned": return { stage: "draft", order: "schedule" };
    case "in_progress": return { stage: "in_progress", order: "schedule" };
    case "uploading": return { stage: "submitted" };
    case "upcoming": return { date_from: addDays(t, 1), order: "schedule" };
    case "completed": return { stage: "completed" };
    default: return {};
  }
}

const VIEWS: { id: View; label: string; counted?: boolean }[] = [
  { id: "today", label: "Today", counted: true }, { id: "unassigned", label: "Unassigned", counted: true },
  { id: "in_progress", label: "In progress", counted: true }, { id: "uploading", label: "Uploading", counted: true },
  { id: "upcoming", label: "Upcoming" }, { id: "completed", label: "Completed" }, { id: "all", label: "All" },
];
const BOARD: string[] = ["draft", "assigned", "in_progress", "submitted", "completed"];

/** How many bookings a query matches: the same question the list asks, so a number and its list agree. */
export function useCount(query: Record<string, string>) {
  return useQuery({ queryKey: ["bookings-page", "count", query], staleTime: 30_000, queryFn: () => api<Page<Booking>>("bookings", { query }) }).data?.count;
}

function ViewTab({ v, on, onPick, own }: { v: (typeof VIEWS)[number]; on: boolean; onPick: () => void; own: Record<string, string> }) {
  const n = useCount({ ...own, ...viewQuery(v.id) });          // the person's filters apply to the numbers too
  return (
    <button role="tab" aria-selected={on} className={on ? "on" : ""} onClick={onPick}>
      {v.label}{v.counted && n !== undefined && <span className={`count-pill${v.id === "unassigned" && n > 0 ? " warn" : ""}`}>{n}</span>}
    </button>
  );
}

/** Every booking: saved views as tabs, one row of filters (remembered per person), a list or a board. */
export function Bookings() {
  const { me, can } = useAuth();
  const nav = useNavigate();
  const { say, fail } = useToast();
  const refresh = useRefresh();
  const [sp, setSp] = useSearchParams();
  const view = (sp.get("view") as View | null) ?? (sp.get("search") ? "all" : "today");
  const key = `vayu:bookings:${me?.id}`;
  // Arriving from a number on Today (?all=1) shows exactly what that number counted: saved filters are set aside.
  const [f, setF] = useState<Filters>(() => ({ ...(sp.get("all") ? EMPTY : loadJSON<Filters>(key, EMPTY)), search: sp.get("search") ?? "", ...(sp.get("stage") ? { stage: sp.get("stage")! } : {}) }));
  const [layout, setLayout] = useState<"list" | "board">(() => loadJSON(`${key}:layout`, "list"));
  const [page, setPage] = useState(1);
  const [acting, setActing] = useState<{ kind: "assign" | "reschedule" | "cancel"; b: Booking } | null>(null);
  const [deleting, setDeleting] = useState<Booking | null>(null);
  useEffect(() => saveJSON(key, { ...f, search: "" }), [key, f]);
  useEffect(() => saveJSON(`${key}:layout`, layout), [key, layout]);
  const urlSearch = sp.get("search");
  useEffect(() => { if (urlSearch !== null) { setF((x) => ({ ...x, search: urlSearch })); setPage(1); } }, [urlSearch]);
  const set = (p: Partial<Filters>) => { setF({ ...f, ...p }); setPage(1); };
  const pick = (v: View) => { setSp(v === "today" ? {} : { view: v }); setPage(1); };
  const own = Object.fromEntries(Object.entries(f).filter(([, v]) => v !== ""));
  const query = { ...own, ...viewQuery(view), page };
  const q = useQuery({ queryKey: ["bookings-page", query], queryFn: () => api<Page<Booking>>("bookings", { query }) });
  const experts = useList<User>("experts", "users", { role: "expert" });
  const cities = useQuery({ queryKey: ["list-items", "city"], queryFn: async () => asList<MasterListItem>(await api("master-lists/city/items")) });
  const types = useInspectionTypes();
  const car = useLabels("car_make_model");
  const city = useLabels("city");
  const type = useTypeLabels();
  const remove = useMutation({
    mutationFn: (b: Booking) => api(`bookings/${b.id}`, { method: "DELETE" }),
    onSuccess: () => { setDeleting(null); say("Booking deleted."); void refresh("bookings-page"); },
    onError: (e) => { setDeleting(null); fail(e); },
  });
  const rows = q.data?.results ?? [];
  const filtered = Object.keys(own).some((k) => k !== "search");
  const menu = (b: Booking) => {
    const live = b.stage !== "cancelled" && b.stage !== "completed";
    return [
      { label: "Open booking", onClick: () => nav(`/booking/${b.id}`) },
      { label: b.assigned_expert ? "Reassign expert" : "Assign expert", onClick: () => setActing({ kind: "assign", b }), hidden: !can("bookings.assign") || !live || b.stage === "in_progress" || b.stage === "submitted" },
      { label: "Reschedule", onClick: () => setActing({ kind: "reschedule", b }), hidden: !can("bookings.reschedule") || !(b.stage === "draft" || b.stage === "assigned") },
      { label: "Cancel booking…", danger: true, onClick: () => setActing({ kind: "cancel", b }), hidden: !can("bookings.cancel") || !live },
      { label: "Delete…", danger: true, onClick: () => setDeleting(b), hidden: !(can("bookings.delete") && canDelete(me?.role ?? "", b.stage)) },
    ];
  };
  const assignBtn = (b: Booking) => can("bookings.assign") && b.stage === "draft"
    ? <button className="sm assign-btn" onClick={(e) => { e.stopPropagation(); setActing({ kind: "assign", b }); }}>Assign expert</button>
    : <ExpertCell id={b.assigned_expert} experts={experts.data ?? []} />;
  return (
    <>
      <PageHeader title="Bookings" count={q.data?.count}>
        <div className="seg" role="group" aria-label="Layout">
          <button aria-pressed={layout === "list"} onClick={() => setLayout("list")}><List size={14} aria-hidden /> List</button>
          <button aria-pressed={layout === "board"} onClick={() => setLayout("board")}><LayoutGrid size={14} aria-hidden /> Board</button>
        </div>
        {can("bookings.create") && <button className="primary" onClick={() => nav("/booking/new")}><Plus size={15} aria-hidden /> New booking</button>}
      </PageHeader>
      <div className="tabs" role="tablist" aria-label="Views">
        {VIEWS.map((v) => <ViewTab key={v.id} v={v} on={view === v.id} onPick={() => pick(v.id)} own={own} />)}
      </div>
      <div className="filters">
        <input aria-label="Filter bookings" className="filter-search" placeholder="Filter: booking ID, customer, phone, chassis" value={f.search} onChange={(e) => { set({ search: e.target.value }); if (e.target.value && view !== "all") setSp({ view: "all" }); }} />
        <select aria-label="City" className={f.city ? "set" : ""} value={f.city} onChange={(e) => set({ city: e.target.value })}><option value="">City</option>{(cities.data ?? []).map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}</select>
        <select aria-label="Type" className={f.type ? "set" : ""} value={f.type} onChange={(e) => set({ type: e.target.value })}><option value="">Type</option>{types.map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}</select>
        <select aria-label="Expert" className={f.expert ? "set" : ""} value={f.expert} onChange={(e) => set({ expert: e.target.value })}><option value="">Expert</option>{(experts.data ?? []).map((u) => <option key={u.id} value={u.id}>{u.name || u.username}</option>)}</select>
        {view === "all" && <select aria-label="Stage" className={f.stage ? "set" : ""} value={f.stage} onChange={(e) => set({ stage: e.target.value })}><option value="">Stage</option>{Object.entries(STAGE_LABEL).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>}
        {(view === "all" || view === "completed") && <label className="date-range"><span>From</span><input aria-label="From" type="date" value={f.date_from} onChange={(e) => set({ date_from: e.target.value })} /><span>to</span><input aria-label="To" type="date" value={f.date_to} onChange={(e) => set({ date_to: e.target.value })} /></label>}
        {filtered && <button className="link" onClick={() => setF({ ...EMPTY, search: f.search })}>Clear filters</button>}
      </div>
      {layout === "list" ? (
        <div className="table-card">
          <table className="rows">
            <thead><tr><th>Booking</th><th>Car</th><th>When</th><th className="opt">Where</th><th>Expert</th><th>Status</th><th aria-label="Actions" /></tr></thead>
            <tbody>{rows.map((b) => (
              <tr key={b.id} className="click" onClick={() => nav(`/booking/${b.id}`)}>
                <td><Link to={`/booking/${b.id}`} className="cell-main" onClick={(e) => e.stopPropagation()}>{b.booking_id}</Link><div className="cell-sub">{String(b.answers.customer_name ?? "")}</div></td>
                <td><div>{car(b.answers.car_make_model)}</div><div className="cell-sub">{type(b.inspection_type)}</div></td>
                <td className="nowrap">{fmtSlot(b.answers.inspection_date, b.answers.inspection_time) || "—"}</td>
                <td className="opt">{city(b.answers.city)}</td>
                <td>{assignBtn(b)}</td>
                <td><Pill tone={STAGE_TONE[b.stage]}>{STAGE_LABEL[b.stage] ?? b.stage}</Pill>{b.conflict && <> <Pill tone="bad">Conflict</Pill></>}</td>
                <td style={{ textAlign: "right" }}><MoreMenu label={`Actions for ${b.booking_id}`} items={menu(b)} /></td>
              </tr>))}</tbody>
          </table>
          {q.data && rows.length === 0 && <Empty title="No bookings here">{filtered || f.search ? "Nothing matches these filters." : view === "today" ? "Nothing is booked for today." : "Nothing in this view right now."}</Empty>}
          {q.data && (q.data.next || q.data.previous) && <div className="table-foot">
            <span className="muted grow">{(page - 1) * 50 + 1}–{(page - 1) * 50 + rows.length} of {q.data.count}</span>
            <button className="sm" disabled={!q.data.previous} onClick={() => setPage(page - 1)}>Previous</button>
            <button className="sm" disabled={!q.data.next} onClick={() => setPage(page + 1)}>Next</button></div>}
        </div>
      ) : (
        <div className="board">
          {BOARD.filter((s) => (view === "all" || view === "today" || view === "upcoming") || rows.some((b) => b.stage === s)).map((s) => {
            const col = rows.filter((b) => b.stage === s);
            return (
              <section key={s} className="board-col" aria-label={STAGE_LABEL[s]}>
                <h3><Pill tone={STAGE_TONE[s]}>{STAGE_LABEL[s]}</Pill> <span className="muted small">{col.length}</span></h3>
                {col.map((b) => (
                  <div key={b.id} className="board-card" onClick={() => nav(`/booking/${b.id}`)}>
                    <div className="bar" style={{ margin: 0 }}><Link to={`/booking/${b.id}`} className="cell-main grow" onClick={(e) => e.stopPropagation()}>{b.booking_id}</Link><MoreMenu label={`Actions for ${b.booking_id}`} items={menu(b)} /></div>
                    <div className="small">{String(b.answers.customer_name ?? "")}</div>
                    <div className="cell-sub">{car(b.answers.car_make_model)} · {fmtSlot(b.answers.inspection_date, b.answers.inspection_time)}</div>
                    <div style={{ marginTop: 6 }}>{assignBtn(b)}</div>
                  </div>))}
                {col.length === 0 && <p className="muted small">None</p>}
              </section>);
          })}
        </div>
      )}
      {acting && <Actions kind={acting.kind} booking={acting.b} experts={experts.data ?? []} onClose={() => setActing(null)} fail={fail} onDone={() => { setActing(null); say("Done."); void refresh("bookings-page"); }} />}
      {deleting && (
        <Confirm title={`Delete ${deleting.booking_id}?`} danger confirmLabel="Delete booking" onCancel={() => setDeleting(null)} onConfirm={() => remove.mutate(deleting)}>
          <p>The booking{deleting.stage === "draft" ? "" : " and everything recorded on it"} is removed for good. This cannot be undone and is written to the audit log.</p>
          {me?.role !== "admin" && <p className="muted small">Ops can only delete a draft that nobody has worked on. To stop a booking that is under way, cancel it instead.</p>}
        </Confirm>)}
    </>
  );
}
