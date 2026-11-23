import { Plus } from "lucide-react";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { api, type Page } from "../../api/client";
import { useList, useRefresh } from "../../api/hooks";
import { useLabels } from "../../api/labels";
import type { Booking, User } from "../../api/types";
import { useAuth } from "../../auth";
import { fmtTime, today } from "../../lib/format";
import { useProblems } from "../../lib/problems";
import { Avatar } from "../../ui/Avatar";
import { Empty, PageHeader, useToast } from "../../ui/kit";
import { Actions } from "./Booking";

const SLOT_HOURS = 1.5;            // ponytail: bookings have a start time only; a job is drawn 1.5 h long

const toHours = (t: unknown) => { const m = typeof t === "string" ? t.match(/^(\d{1,2}):(\d{2})/) : null; return m ? Number(m[1]) + Number(m[2]) / 60 : null; };

/** The hours the schedule spans: 9 to 19, widened to fit the day's jobs. */
export function dayWindow(starts: number[]): [number, number] {
  const lo = Math.min(9, ...starts.map(Math.floor));
  const hi = Math.max(19, ...starts.map((s) => Math.ceil(s + SLOT_HOURS)));
  return [lo, hi];
}

const KIND: Record<string, string> = { draft: "open", assigned: "next", in_progress: "prog", submitted: "prog", completed: "done", cancelled: "off" };

/** Ops' home: what today looks like, who is where, and what needs a person now. */
export function Today() {
  const { can } = useAuth();
  const nav = useNavigate();
  const { say, fail } = useToast();
  const refresh = useRefresh();
  const t = today();
  const q = useQuery({ queryKey: ["bookings-page", "today-home", t], refetchInterval: 60_000,
    queryFn: () => api<Page<Booking>>("bookings", { query: { date_from: t, date_to: t, order: "schedule" } }) });
  const experts = useList<User>("experts", "users", { role: "expert" });
  const problems = useProblems();
  const car = useLabels("car_make_model");
  const city = useLabels("city");
  const [assigning, setAssigning] = useState<Booking | null>(null);
  const all = (q.data?.results ?? []).filter((b) => b.stage !== "cancelled");
  const by = (stage: string) => all.filter((b) => b.stage === stage).length;
  const kpis = [
    { label: "Today's jobs", value: q.data ? all.length : "—", sub: `${by("completed")} done · ${by("in_progress")} in progress`, to: "/bookings" },
    { label: "Unassigned", value: by("draft"), sub: all.find((b) => b.stage === "draft") ? `next at ${fmtTime(all.find((b) => b.stage === "draft")!.answers.inspection_time)}` : "all assigned", to: "/bookings?view=unassigned", tone: by("draft") ? "warn" : "" },
    { label: "In progress", value: by("in_progress"), sub: "experts on site", to: "/bookings?view=in_progress", tone: "info" },
    { label: "Uploading", value: by("submitted"), sub: "files still coming", to: "/bookings?view=uploading" },
    { label: "Completed", value: by("completed"), sub: "today", to: "/bookings?view=completed", tone: "ok" },
    { label: "Problems", value: problems.total, sub: problems.total ? "see Needs you" : "all clear", to: "/problems", tone: problems.total ? "bad" : "" },
  ];
  const starts = all.map((b) => toHours(b.answers.inspection_time)).filter((x): x is number => x !== null);
  const [lo, hi] = dayWindow(starts);
  const span = hi - lo;
  const lanes = [
    { id: 0, name: "Unassigned", user: null as User | null, jobs: all.filter((b) => !b.assigned_expert) },
    ...[...new Set(all.map((b) => b.assigned_expert).filter((x): x is number => !!x))].map((id) => ({
      id, user: experts.data?.find((u) => u.id === id) ?? null, name: experts.data?.find((u) => u.id === id)?.name ?? `#${id}`, jobs: all.filter((b) => b.assigned_expert === id) })),
  ].filter((l) => l.jobs.length > 0);
  const now = new Date();
  const nowAt = now.getHours() + now.getMinutes() / 60;
  const needs = [
    ...all.filter((b) => b.stage === "draft").map((b) => ({ key: `a${b.id}`, tone: "warn", title: `${b.booking_id} has no expert`, meta: `${fmtTime(b.answers.inspection_time)} · ${city(b.answers.city)}`, action: can("bookings.assign") ? <button className="sm" onClick={() => setAssigning(b)}>Assign</button> : null })),
    ...problems.stuck.map((s) => ({ key: `s${s.id}`, tone: "bad", title: `Upload stuck for ${s.booking_id}`, meta: `${s.expert} · ${s.field_key}`, action: <Link className="btn sm" to={`/booking/${s.booking}`}>Open</Link> })),
    ...problems.conflicts.map((b) => ({ key: `c${b.id}`, tone: "bad", title: `${b.booking_id}: two experts submitted`, meta: "Choose which inspection counts", action: <Link className="btn sm" to={`/booking/${b.id}`}>Resolve</Link> })),
    ...problems.pdf.map((r) => ({ key: `p${r.booking}`, tone: "warn", title: r.stale ? `Report out of date: ${r.booking_id}` : `Report failed: ${r.booking_id}`, meta: r.error || "Answers changed after the PDF was made", action: <Link className="btn sm" to={`/booking/${r.booking}`}>Open</Link> })),
    ...problems.types.map((b) => ({ key: `t${b.id}`, tone: "warn", title: `${b.booking_id}: type change rejected`, meta: "The expert started another type", action: <Link className="btn sm" to={`/booking/${b.id}`}>Open</Link> })),
  ];
  return (
    <>
      <PageHeader title="Today" subtitle={now.toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long" })}>
        <button onClick={() => nav("/bookings")}>All bookings</button>
        {can("bookings.create") && <button className="primary" onClick={() => nav("/booking/new")}><Plus size={15} aria-hidden /> New booking</button>}
      </PageHeader>
      <section className="kpis" aria-label="Today in numbers">
        {kpis.map((k) => (
          <Link key={k.label} to={k.to} className="card kpi">
            <span className="kpi-label">{k.label}</span>
            <span className={`kpi-value ${k.tone ?? ""}`}>{k.value}</span>
            <span className="kpi-sub">{k.sub}</span>
          </Link>))}
      </section>
      <div className="today-cols">
        <section className="card schedule" aria-label="Schedule by expert">
          <div className="sheet-head" style={{ padding: "0 0 10px", border: 0 }}>
            <h3>Schedule by expert</h3>
            <span className="legend done">Done</span><span className="legend prog">In progress</span><span className="legend next">To start</span><span className="legend open">Unassigned</span>
          </div>
          {all.length === 0 && q.data && <Empty title="Nothing booked for today">New bookings for today show here.</Empty>}
          {all.length > 0 && <>
            <div className="hours" aria-hidden="true">{Array.from({ length: span + 1 }, (_, i) => <span key={i} style={{ left: `${(i / span) * 100}%` }}>{fmtTime(`${lo + i}:00`).replace(":00", "")}</span>)}</div>
            {lanes.map((l) => (
              <div key={l.id} className="lane">
                <div className="lane-who">
                  {l.user ? <Avatar who={l.user} size={26} /> : <span className="avatar lane-open" style={{ width: 26, height: 26 }}>?</span>}
                  <div><div className="small" style={{ fontWeight: 500 }}>{l.name}</div><div className="muted" style={{ fontSize: 11 }}>{l.jobs.length} job{l.jobs.length === 1 ? "" : "s"}</div></div>
                </div>
                <div className="lane-track">
                  {nowAt > lo && nowAt < hi && <span className="now-line" style={{ left: `${((nowAt - lo) / span) * 100}%` }} />}
                  {l.jobs.map((b) => {
                    const s = toHours(b.answers.inspection_time) ?? lo;
                    return (
                      <Link key={b.id} to={`/booking/${b.id}`} className={`job-block ${KIND[b.stage]}`} title={`${b.booking_id} · ${fmtTime(b.answers.inspection_time)} · ${String(b.answers.customer_name ?? "")}`}
                        style={{ left: `${((s - lo) / span) * 100}%`, width: `calc(${(SLOT_HOURS / span) * 100}% - 4px)` }}>
                        <b>{b.booking_id}</b><br />{car(b.answers.car_make_model)}
                      </Link>);
                  })}
                </div>
              </div>))}
          </>}
        </section>
        <section className="card needs" aria-label="Needs you">
          <div className="sheet-head" style={{ padding: "0 0 6px", border: 0 }}><h3>Needs you</h3><Link to="/problems" className="small">All problems</Link></div>
          {needs.length === 0 && <p className="muted small">Nothing needs you right now.</p>}
          {needs.slice(0, 8).map((n) => (
            <div key={n.key} className="need">
              <span className={`dot ${n.tone}`} aria-hidden="true" />
              <div className="grow" style={{ minWidth: 0 }}><div className="small" style={{ fontWeight: 500 }}>{n.title}</div><div className="muted" style={{ fontSize: 12 }}>{n.meta}</div></div>
              {n.action}
            </div>))}
          {needs.length > 8 && <Link to="/problems" className="small">{needs.length - 8} more</Link>}
        </section>
      </div>
      {assigning && <Actions kind="assign" booking={assigning} experts={experts.data ?? []} onClose={() => setAssigning(null)} fail={fail} onDone={() => { setAssigning(null); say("Assigned."); void refresh("bookings-page"); }} />}
    </>
  );
}
