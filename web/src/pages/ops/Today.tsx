import { ChevronLeft, ChevronRight, Plus, Users } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { api, type Page } from "../../api/client";
import { useList, useRefresh } from "../../api/hooks";
import { useLabels } from "../../api/labels";
import type { Booking, User } from "../../api/types";
import { useAuth } from "../../auth";
import { fmtTime, today } from "../../lib/format";
import { loadJSON, saveJSON } from "../../lib/store";
import { clampStart, dayWindow, hm, jobSpan, rangeLabel, spanTitle, stackRows, WINDOW_HOURS, windowStarts } from "../../lib/schedule";
import { useNeeds } from "../../lib/problems";
import { Avatar } from "../../ui/Avatar";
import { Empty, PageHeader, useToast } from "../../ui/kit";
import { Actions } from "./Booking";
import { useCount, viewQuery } from "./Bookings";

const SLOT_PX = 76;                // width of 30 minutes; the day scrolls sideways
const LANE_W = 200;                // the expert column, kept in view while scrolling
const CHOSEN = "vayu:today-experts";  // the experts picked in the side panel, kept per browser

const LANE_H = 76;                 // height of one row of boxes; a lane with overlapping jobs gets more rows
export { dayWindow };

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
  const [, tick] = useState(0);
  useEffect(() => { const id = setInterval(() => tick((n) => n + 1), 60_000); return () => clearInterval(id); }, []);
  const now = new Date();
  const spans = new Map(all.map((b) => [b.id, jobSpan(b, now)]));
  const [lo, hi] = dayWindow([...spans.values()]);
  const slots = (hi - lo) * 2;                          // one column per 30 minutes
  const nowAt = now.getHours() + now.getMinutes() / 60;

  // Who is on the schedule: everyone with a job today, or just the experts chosen in the side panel.
  const everyone = [
    { id: 0, name: "Unassigned", user: null as User | null, jobs: all.filter((b) => !b.assigned_expert) },
    ...[...new Map([...(experts.data ?? []).map((u) => [u.id, u] as const),
      ...all.filter((b) => b.assigned_expert && !experts.data?.some((u) => u.id === b.assigned_expert)).map((b) => [b.assigned_expert!, null] as const)]).entries()]
      .map(([id, user]) => ({ id, user, name: user?.name ?? `#${id}`, jobs: all.filter((b) => b.assigned_expert === id) }))
      .sort((x, y) => x.name.localeCompare(y.name)),
  ];
  const [sel, setSel] = useState<number[]>(() => loadJSON<number[]>(CHOSEN, []));
  const [side, setSide] = useState(true);
  const [find, setFind] = useState("");
  const choose = (next: number[]) => { setSel(next); saveJSON(CHOSEN, next); };
  const lanes = sel.length ? everyone.filter((l) => sel.includes(l.id)) : everyone.filter((l) => l.jobs.length > 0);
  const pickRows = everyone.filter((l) => l.name.toLowerCase().includes(find.trim().toLowerCase()));

  // The view: a 3-hour window that fills the width (no sideways scrolling needed), or the full day.
  const [mode, setMode] = useState<"3h" | "day">("3h");
  const [viewW, setViewW] = useState(0);
  const [leftH, setLeftH] = useState(0);                // the hour at the left edge of the grid
  const left = useRef<number | null>(null);
  const want = useRef<number | null>(null);
  const hasJobs = all.length > 0;
  useEffect(() => {
    const el = scroller.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setViewW(el.clientWidth));
    ro.observe(el); setViewW(el.clientWidth);
    return () => ro.disconnect();
  }, [hasJobs, side]);
  const slotPx = mode === "3h" && viewW > LANE_W + 240 ? Math.floor((viewW - LANE_W) / (WINDOW_HOURS * 2)) : SLOT_PX;
  const nowX = (nowAt - lo) * 2 * slotPx;
  const goTo = (start: number, smooth = true) => {
    const el = scroller.current;
    if (el) el.scrollTo({ left: Math.max(0, (clampStart(start, lo, hi) - lo) * 2 * slotPx), behavior: smooth ? "smooth" : "auto" });
  };
  useEffect(() => { goTo(want.current ?? left.current ?? nowAt - 1, false); want.current = null; }, [slotPx, hasJobs]); // eslint-disable-line react-hooks/exhaustive-deps
  const onScroll = (el: HTMLDivElement) => { const h = lo + el.scrollLeft / (2 * slotPx); left.current = h; setLeftH(h); };
  const pick = (start: number) => { if (mode === "day") { want.current = start; setMode("3h"); } else goTo(start); };
  const step = (dir: number) => goTo(Math.round(leftH) + dir);
  const drag = useRef<{ x: number; left: number; moved: boolean } | null>(null);
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
          <span className="legend done">Done</span><span className="legend prog">In progress</span><span className="legend next">To start</span><span className="legend open">Unassigned</span><span className="legend late">Started late</span>
          <button className="sm" aria-pressed={side} onClick={() => setSide(!side)}><Users size={14} aria-hidden /> Experts{sel.length ? ` (${sel.length})` : ""}</button>
        </div>
        {hasJobs && (
          <div className="sched-bar" role="group" aria-label="Time window">
            {mode === "3h" && <button className="sm icon" aria-label="One hour earlier" onClick={() => step(-1)}><ChevronLeft size={15} aria-hidden /></button>}
            <button className="sm" onClick={() => pick(nowAt - 1)}>Now</button>
            {windowStarts(lo, hi).map((s) => (
              <button key={s} className={`sm${mode === "3h" && Math.abs(leftH - s) < 0.26 ? " on" : ""}`} aria-pressed={mode === "3h" && Math.abs(leftH - s) < 0.26} onClick={() => pick(s)}>{rangeLabel(s)}</button>))}
            {mode === "3h" && <button className="sm icon" aria-label="One hour later" onClick={() => step(1)}><ChevronRight size={15} aria-hidden /></button>}
            <button className={`sm${mode === "day" ? " on" : ""}`} aria-pressed={mode === "day"} onClick={() => setMode(mode === "day" ? "3h" : "day")}>Full day</button>
          </div>)}
        {all.length === 0 && q.data && <Empty title="Nothing booked for today">New bookings for today show here.</Empty>}
        {hasJobs && (
          <div className="sched-body">
            {side && (
              <aside className="sched-side" aria-label="Filter by expert">
                <div className="sched-side-head"><b>Experts</b>{sel.length > 0 && <button className="sm" onClick={() => choose([])}>Show all</button>}</div>
                <input type="search" placeholder="Find an expert" aria-label="Find an expert" value={find} onChange={(e) => setFind(e.target.value)} />
                <p className="muted small" style={{ margin: "6px 0" }}>{sel.length ? `${sel.length} chosen` : "Everyone with a job today"}</p>
                <ul>
                  {pickRows.map((l) => (
                    <li key={l.id}>
                      <label className={`sched-pick${l.jobs.length ? "" : " idle"}`}>
                        <input type="checkbox" checked={sel.includes(l.id)} onChange={() => choose(sel.includes(l.id) ? sel.filter((x) => x !== l.id) : [...sel, l.id])} />
                        <span className="ellipsis">{l.name}</span><span className="muted small">{l.jobs.length}</span>
                      </label>
                    </li>))}
                </ul>
              </aside>)}
            <div className="sched-scroll" ref={scroller}
              onScroll={(e) => onScroll(e.currentTarget)}
              onPointerDown={(e) => { if (e.pointerType === "mouse" && e.button === 0) drag.current = { x: e.clientX, left: e.currentTarget.scrollLeft, moved: false }; }}
              onPointerMove={(e) => {
                const d = drag.current; if (!d) return;
                const dx = e.clientX - d.x;
                if (!d.moved && Math.abs(dx) > 4) { d.moved = true; e.currentTarget.setPointerCapture(e.pointerId); }
                if (d.moved) e.currentTarget.scrollLeft = d.left - dx;
              }}
              onPointerUp={() => setTimeout(() => { drag.current = null; }, 0)}
              onPointerCancel={() => setTimeout(() => { drag.current = null; }, 0)}
              onClickCapture={(e) => { if (drag.current?.moved) { e.preventDefault(); e.stopPropagation(); } }}>
              <div className="sched" style={{ width: LANE_W + slots * slotPx }}>
                {nowAt > lo && nowAt < hi && <span className="now-line" style={{ left: LANE_W + nowX }} />}
                <div className="sched-row sched-hours">
                  <div className="sched-who" />
                  <div className="sched-axis" style={{ width: slots * slotPx }}>
                    {nowAt > lo && nowAt < hi && <>
                      <span className="now-line" style={{ left: nowX, top: 0 }} />
                      <span className="now-chip" style={{ left: nowX }}>{hm(nowAt)}</span>
                    </>}
                    {Array.from({ length: slots }, (_, i) => {
                      const m = lo * 60 + i * 30;
                      return <span key={i} className={`sched-tick${m % 60 === 0 ? " hour" : ""}${i === 0 ? " first" : ""}`} style={{ left: i * slotPx }}>{fmtTime(`${Math.floor(m / 60)}:${String(m % 60).padStart(2, "0")}`)}</span>;
                    })}
                  </div>
                </div>
                {lanes.length === 0 && <div className="sched-row"><div className="sched-who" /><div className="muted" style={{ padding: 18 }}>Nobody to show. Choose experts in the side panel, or Show all.</div></div>}
                {lanes.map((l) => {
                  const laid = stackRows(l.jobs.map((b) => spans.get(b.id)!));
                  return (
                    <div key={l.id} className="sched-row">
                      <div className="sched-who">
                        {l.user ? <Avatar who={l.user} size={28} /> : <span className="avatar lane-open" style={{ width: 28, height: 28 }}>?</span>}
                        <div style={{ minWidth: 0 }}><div className="small ellipsis" style={{ fontWeight: 600 }}>{l.name}</div><div className="muted" style={{ fontSize: 11 }}>{l.jobs.length ? `${l.jobs.length} job${l.jobs.length === 1 ? "" : "s"}` : "Free today"}</div></div>
                      </div>
                      <div className="sched-track" style={{ width: slots * slotPx, height: laid.rows * LANE_H, backgroundSize: `${slotPx}px 100%, ${slotPx * 2}px 100%` }}>
                        {l.jobs.map((b, i) => {
                          const sp = spans.get(b.id)!;
                          return (
                            <Link key={b.id} to={`/booking/${b.id}`} className={`job-block ${KIND[b.stage]}${sp.late ? " late" : ""}`}
                              title={`${b.booking_id} · ${String(b.answers.customer_name ?? "")}\n${spanTitle(sp)}`}
                              style={{ left: (sp.start - lo) * 2 * slotPx + 2, width: (sp.end - sp.start) * 2 * slotPx - 4, top: laid.row[i]! * LANE_H + 8, height: LANE_H - 16, bottom: "auto" }}>
                              <span className="jb-top"><b>{b.booking_id}</b><span>{hm(sp.start)}</span></span>
                              <span className="jb-sub">{String(b.answers.customer_name ?? "")}</span>
                              <span className="jb-sub">{car(b.answers.car_make_model)} · {city(b.answers.city)}</span>
                            </Link>);
                        })}
                      </div>
                    </div>);
                })}
              </div>
            </div>
          </div>)}
      </section>
      {assigning && <Actions kind="assign" booking={assigning} experts={experts.data ?? []} onClose={() => setAssigning(null)} fail={fail} onDone={() => { setAssigning(null); say("Assigned."); void refresh("bookings-page"); }} />}
    </>
  );
}
