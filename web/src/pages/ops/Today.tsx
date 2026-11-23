import { Plus } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { api, type Page } from "../../api/client";
import { useList, useRefresh } from "../../api/hooks";
import { useLabels } from "../../api/labels";
import type { Booking, User } from "../../api/types";
import { useAuth } from "../../auth";
import { fmtTime, today } from "../../lib/format";
import { useNeeds } from "../../lib/problems";
import { Avatar } from "../../ui/Avatar";
import { Empty, PageHeader, useToast } from "../../ui/kit";
import { Actions } from "./Booking";
import { useCount, viewQuery } from "./Bookings";

const SLOT_HOURS = 1.5;            // ponytail: bookings have a start time only; a job is drawn 1.5 h long
const SLOT_PX = 76;                // width of 30 minutes; the day scrolls sideways
const LANE_W = 200;                // the expert column, kept in view while scrolling

const toHours = (t: unknown) => { const m = typeof t === "string" ? t.match(/^(\d{1,2}):(\d{2})/) : null; return m ? Number(m[1]) + Number(m[2]) / 60 : null; };

/** The hours the schedule spans: 8 am to 8 pm, widened to fit the day's jobs. */
export function dayWindow(starts: number[]): [number, number] {
  const lo = Math.min(8, ...starts.map(Math.floor));
  const hi = Math.max(20, ...starts.map((s) => Math.ceil(s + SLOT_HOURS)));
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
  const { needs } = useNeeds();
  const scroller = useRef<HTMLDivElement>(null);
  const car = useLabels("car_make_model");
  const city = useLabels("city");
  const [assigning, setAssigning] = useState<Booking | null>(null);
  const all = (q.data?.results ?? []).filter((b) => b.stage !== "cancelled");
  const by = (stage: string) => all.filter((b) => b.stage === stage).length;
  // Every number is the count of the very list its card opens (same question, same answer).
  const todayN = useCount(viewQuery("today", new Date()));
  const doneToday = useCount({ ...viewQuery("today", new Date()), stage: "completed" });
  const unassigned = useCount(viewQuery("unassigned"));
  const inProgress = useCount(viewQuery("in_progress"));
  const uploading = useCount(viewQuery("uploading"));
  const cancelled = (q.data?.results ?? []).length - all.length;
  const kpis = [
    { label: "Today's jobs", value: todayN ?? "—", sub: `${by("completed")} done · ${by("in_progress")} in progress${cancelled ? ` · ${cancelled} cancelled` : ""}`, to: "/bookings?all=1" },
    { label: "Unassigned", value: unassigned ?? "—", sub: unassigned ? "on any day, need an expert" : "all assigned", to: "/bookings?view=unassigned&all=1", tone: unassigned ? "warn" : "" },
    { label: "In progress", value: inProgress ?? "—", sub: "experts on site", to: "/bookings?view=in_progress&all=1", tone: "info" },
    { label: "Uploading", value: uploading ?? "—", sub: "files still coming", to: "/bookings?view=uploading&all=1" },
    { label: "Completed", value: doneToday ?? "—", sub: "today", to: "/bookings?view=today&stage=completed&all=1", tone: "ok" },
    { label: "Needs you", value: needs.length, sub: needs.length ? "open the list" : "all clear", to: "/problems", tone: needs.length ? "bad" : "" },
  ];
  const starts = all.map((b) => toHours(b.answers.inspection_time)).filter((x): x is number => x !== null);
  const [lo, hi] = dayWindow(starts);
  const slots = (hi - lo) * 2;                          // one column per 30 minutes
  const lanes = [
    { id: 0, name: "Unassigned", user: null as User | null, jobs: all.filter((b) => !b.assigned_expert) },
    ...[...new Set(all.map((b) => b.assigned_expert).filter((x): x is number => !!x))].map((id) => ({
      id, user: experts.data?.find((u) => u.id === id) ?? null, name: experts.data?.find((u) => u.id === id)?.name ?? `#${id}`, jobs: all.filter((b) => b.assigned_expert === id) })),
  ].filter((l) => l.jobs.length > 0);
  const now = new Date();
  const nowAt = now.getHours() + now.getMinutes() / 60;
  const scrollToNow = () => { const el = scroller.current; if (el) el.scrollTo({ left: Math.max(0, (nowAt - lo - 1) * 2 * SLOT_PX), behavior: "smooth" }); };
  useEffect(() => { scrollToNow(); }, [all.length > 0]); // eslint-disable-line react-hooks/exhaustive-deps
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
      <section className="card schedule-card" aria-label="Schedule by expert">
        <div className="sheet-head" style={{ padding: "0 0 10px", border: 0 }}>
          <h3>Schedule by expert</h3>
          <span className="legend done">Done</span><span className="legend prog">In progress</span><span className="legend next">To start</span><span className="legend open">Unassigned</span>
          <button className="sm" onClick={() => scrollToNow()}>Now</button>
        </div>
        {all.length === 0 && q.data && <Empty title="Nothing booked for today">New bookings for today show here.</Empty>}
        {all.length > 0 && (
          <div className="sched-scroll" ref={scroller}>
            <div className="sched" style={{ width: LANE_W + slots * SLOT_PX }}>
              <div className="sched-row sched-hours">
                <div className="sched-who" />
                {Array.from({ length: slots }, (_, i) => {
                  const m = lo * 60 + i * 30;
                  return <div key={i} className={`sched-slot-label${m % 60 === 0 ? " hour" : ""}`} style={{ width: SLOT_PX }}>{fmtTime(`${Math.floor(m / 60)}:${String(m % 60).padStart(2, "0")}`)}</div>;
                })}
              </div>
              {lanes.map((l) => (
                <div key={l.id} className="sched-row">
                  <div className="sched-who">
                    {l.user ? <Avatar who={l.user} size={28} /> : <span className="avatar lane-open" style={{ width: 28, height: 28 }}>?</span>}
                    <div style={{ minWidth: 0 }}><div className="small ellipsis" style={{ fontWeight: 600 }}>{l.name}</div><div className="muted" style={{ fontSize: 11 }}>{l.jobs.length} job{l.jobs.length === 1 ? "" : "s"}</div></div>
                  </div>
                  <div className="sched-track" style={{ width: slots * SLOT_PX, backgroundSize: `${SLOT_PX}px 100%, ${SLOT_PX * 2}px 100%` }}>
                    {nowAt > lo && nowAt < hi && <span className="now-line" style={{ left: (nowAt - lo) * 2 * SLOT_PX }} />}
                    {l.jobs.map((b) => {
                      const st = toHours(b.answers.inspection_time) ?? lo;
                      return (
                        <Link key={b.id} to={`/booking/${b.id}`} className={`job-block ${KIND[b.stage]}`} title={`${b.booking_id} · ${fmtTime(b.answers.inspection_time)} · ${String(b.answers.customer_name ?? "")}`}
                          style={{ left: (st - lo) * 2 * SLOT_PX + 2, width: SLOT_HOURS * 2 * SLOT_PX - 4 }}>
                          <span className="jb-top"><b>{b.booking_id}</b><span>{fmtTime(b.answers.inspection_time)}</span></span>
                          <span className="jb-sub">{String(b.answers.customer_name ?? "")}</span>
                          <span className="jb-sub">{car(b.answers.car_make_model)} · {city(b.answers.city)}</span>
                        </Link>);
                    })}
                  </div>
                </div>))}
            </div>
          </div>)}
      </section>
      {assigning && <Actions kind="assign" booking={assigning} experts={experts.data ?? []} onClose={() => setAssigning(null)} fail={fail} onDone={() => { setAssigning(null); say("Assigned."); void refresh("bookings-page"); }} />}
    </>
  );
}
