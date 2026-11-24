import { ChevronDown, ChevronLeft, ChevronRight, Plus, Users } from "lucide-react";
import { Fragment, useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { api, type Page } from "../../api/client";
import { useList, useRefresh } from "../../api/hooks";
import { useLabels } from "../../api/labels";
import type { Booking, User } from "../../api/types";
import { useAuth } from "../../auth";
import { fmtTime, today } from "../../lib/format";
import { loadJSON, saveJSON } from "../../lib/store";
import { clampStart, DAY_END, DAY_START, dayWindow, hm, hoursOf, jobSpan, rangeLabel, spanFacts, spanTitle, stackRows, WINDOW_HOURS, windowStarts, type Span } from "../../lib/schedule";
import { useNeeds } from "../../lib/problems";
import { Avatar } from "../../ui/Avatar";
import { Empty, PageHeader, useToast } from "../../ui/kit";
import { Actions } from "./Booking";
import { useCount, viewQuery } from "./Bookings";

const SLOT_PX = 76;                // width of 30 minutes; the day scrolls sideways
const LANE_W = 200;                // the expert column, kept in view while scrolling
const GUTTER = 36;                 // room at each end of the grid so a time label is never hidden by the expert column or the edge
const CHOSEN = "vayu:today-experts";  // the experts picked in the Experts menu, kept per browser

const LANE_H = 76;                 // height of one row of boxes; a lane with overlapping jobs gets more rows
export { dayWindow };

const STAGE_NAME: Record<string, string> = { draft: "Not assigned", assigned: "Assigned", in_progress: "In progress", submitted: "Uploading files", completed: "Completed" };
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

  // Who is on the schedule: every expert, or just the ones chosen in the Experts menu.
  const everyone = [
    { id: 0, name: "Unassigned", user: null as User | null, jobs: all.filter((b) => !b.assigned_expert) },
    ...[...new Map([...(experts.data ?? []).map((u) => [u.id, u] as const),
      ...all.filter((b) => b.assigned_expert && !experts.data?.some((u) => u.id === b.assigned_expert)).map((b) => [b.assigned_expert!, null] as const)]).entries()]
      .map(([id, user]) => ({ id, user, name: user?.name ?? `#${id}`, jobs: all.filter((b) => b.assigned_expert === id) }))
      .sort((x, y) => x.name.localeCompare(y.name)),
  ];
  const [sel, setSel] = useState<number[]>(() => loadJSON<number[]>(CHOSEN, []));
  const [menu, setMenu] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  useEffect(() => {                                   // the expert menu closes on a click outside or Escape
    if (!menu) return;
    const away = (e: MouseEvent) => { if (!menuRef.current?.contains(e.target as Node)) setMenu(false); };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setMenu(false); };
    document.addEventListener("mousedown", away); document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("mousedown", away); document.removeEventListener("keydown", esc); };
  }, [menu]);
  const [find, setFind] = useState("");
  const choose = (next: number[]) => { setSel(next); saveJSON(CHOSEN, next); };
  const lanes = sel.length ? everyone.filter((l) => sel.includes(l.id)) : everyone.filter((l) => l.id !== 0 || l.jobs.length > 0);   // every expert, free or not; Unassigned only when it has jobs
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
  }, [hasJobs]);
  const slotPx = mode === "3h" && viewW > LANE_W + 240 ? Math.floor((viewW - LANE_W - 2 * GUTTER) / (WINDOW_HOURS * 2)) : SLOT_PX;
  const nowX = GUTTER + (nowAt - lo) * 2 * slotPx;
  const goTo = (start: number, smooth = true) => {
    const el = scroller.current;
    if (el) el.scrollTo({ left: Math.max(0, (clampStart(start, lo, hi) - lo) * 2 * slotPx), behavior: smooth ? "smooth" : "auto" });
  };
  useEffect(() => { goTo(want.current ?? left.current ?? nowAt - 1, false); want.current = null; }, [slotPx, hasJobs]); // eslint-disable-line react-hooks/exhaustive-deps
  const onScroll = (el: HTMLDivElement) => { const h = lo + el.scrollLeft / (2 * slotPx); left.current = h; setLeftH(h); };
  const pick = (start: number) => { if (mode === "day") { want.current = start; setMode("3h"); } else goTo(start); };
  const step = (dir: number) => goTo(Math.round(leftH) + dir);
  const [tip, setTip] = useState<{ b: Booking; sp: Span; who: string; x: number; y: number; up: boolean } | null>(null);
  const showTip = (el: HTMLElement, b: Booking, sp: Span, who: string) => {      // the card sits under the box, or over it near the bottom
    const r = el.getBoundingClientRect(), below = r.bottom + 230 < window.innerHeight;
    setTip({ b, sp, who, x: Math.min(Math.max(8, r.left), window.innerWidth - 328), y: below ? r.bottom + 8 : r.top - 8, up: !below });
  };
  const drag = useRef<{ x: number; y: number; left: number; top: number; moved: boolean } | null>(null);
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
          <div className="sched-menu" ref={menuRef}>
            <button className="sm" aria-haspopup="listbox" aria-expanded={menu} onClick={() => setMenu(!menu)}><Users size={14} aria-hidden /> {sel.length ? `${sel.length} expert${sel.length === 1 ? "" : "s"}` : "All experts"} <ChevronDown size={14} aria-hidden /></button>
            {menu && (
              <div className="sched-pop" role="listbox" aria-label="Choose experts" aria-multiselectable>
                <input type="search" placeholder="Find an expert" aria-label="Find an expert" autoFocus value={find} onChange={(e) => setFind(e.target.value)} />
                <div className="sched-pop-head"><span className="muted small">{sel.length ? `${sel.length} chosen` : "Every expert is shown"}</span>{sel.length > 0 && <button className="sm" onClick={() => choose([])}>Show all</button>}</div>
                <ul>
                  {pickRows.map((l) => (
                    <li key={l.id}>
                      <label className={`sched-pick${l.jobs.length ? "" : " idle"}`}>
                        <input type="checkbox" checked={sel.includes(l.id)} onChange={() => choose(sel.includes(l.id) ? sel.filter((x) => x !== l.id) : [...sel, l.id])} />
                        <span className="ellipsis">{l.name}</span><span className="muted small">{l.jobs.length}</span>
                      </label>
                    </li>))}
                  {pickRows.length === 0 && <li className="muted small" style={{ padding: 6 }}>No one by that name.</li>}
                </ul>
              </div>)}
          </div>
        </div>
        {hasJobs && (
          <div className="sched-bar" role="group" aria-label="Time window">
            {mode === "3h" && <button className="sm icon" aria-label="One hour earlier" onClick={() => step(-1)}><ChevronLeft size={15} aria-hidden /></button>}
            <button className="sm" onClick={() => pick(nowAt - 1)}>Now</button>
            {windowStarts(DAY_START, DAY_END).map((s) => (
              <button key={s} className={`sm${mode === "3h" && Math.abs(leftH - s) < 0.26 ? " on" : ""}`} aria-pressed={mode === "3h" && Math.abs(leftH - s) < 0.26} onClick={() => pick(s)}>{rangeLabel(s)}</button>))}
            {mode === "3h" && <button className="sm icon" aria-label="One hour later" onClick={() => step(1)}><ChevronRight size={15} aria-hidden /></button>}
            <button className={`sm${mode === "day" ? " on" : ""}`} aria-pressed={mode === "day"} onClick={() => setMode(mode === "day" ? "3h" : "day")}>Full day</button>
          </div>)}
        {all.length === 0 && q.data && <Empty title="Nothing booked for today">New bookings for today show here.</Empty>}
        {hasJobs && (
          <div className="sched-body">
            <div className="sched-scroll" ref={scroller}
              onScroll={(e) => onScroll(e.currentTarget)}
              onPointerDown={(e) => { if (e.pointerType === "mouse" && e.button === 0) drag.current = { x: e.clientX, y: e.clientY, left: e.currentTarget.scrollLeft, top: e.currentTarget.scrollTop, moved: false }; }}
              onPointerMove={(e) => {
                const d = drag.current; if (!d) return;
                const dx = e.clientX - d.x, dy = e.clientY - d.y;
                if (!d.moved && Math.hypot(dx, dy) > 4) { d.moved = true; e.currentTarget.setPointerCapture(e.pointerId); }
                if (d.moved) { e.currentTarget.scrollLeft = d.left - dx; e.currentTarget.scrollTop = d.top - dy; }   // any direction
              }}
              onPointerUp={() => setTimeout(() => { drag.current = null; }, 0)}
              onPointerCancel={() => setTimeout(() => { drag.current = null; }, 0)}
              onClickCapture={(e) => { if (drag.current?.moved) { e.preventDefault(); e.stopPropagation(); } }}>
              <div className="sched" style={{ width: LANE_W + 2 * GUTTER + slots * slotPx }}>
                {nowAt > lo && nowAt < hi && <span className="now-line" style={{ left: LANE_W + nowX }} />}
                <div className="sched-row sched-hours">
                  <div className="sched-who" />
                  <div className="sched-axis" style={{ width: slots * slotPx + 2 * GUTTER }}>
                    {nowAt > lo && nowAt < hi && <>
                      <span className="now-line" style={{ left: nowX, top: 0 }} />
                      <span className="now-chip" style={{ left: nowX }}>{hm(nowAt)}</span>
                    </>}
                    {Array.from({ length: slots }, (_, i) => {
                      const m = lo * 60 + i * 30;
                      return <span key={i} className={`sched-tick${m % 60 === 0 ? " hour" : ""}`} style={{ left: GUTTER + i * slotPx }}>{fmtTime(`${Math.floor(m / 60)}:${String(m % 60).padStart(2, "0")}`)}</span>;
                    })}
                  </div>
                </div>
                {lanes.length === 0 && <div className="sched-row"><div className="sched-who" /><div className="muted" style={{ padding: 18 }}>Nobody to show. Choose experts in the Experts menu, or Show all.</div></div>}
                {lanes.map((l) => {
                  const laid = stackRows(l.jobs.map((b) => spans.get(b.id)!));
                  return (
                    <div key={l.id} className="sched-row">
                      <div className="sched-who">
                        {l.user ? <Avatar who={l.user} size={28} /> : <span className="avatar lane-open" style={{ width: 28, height: 28 }}>?</span>}
                        <div style={{ minWidth: 0 }}><div className="small ellipsis" style={{ fontWeight: 600 }}>{l.name}</div><div className="muted" style={{ fontSize: 11 }}>{l.jobs.length ? `${l.jobs.length} job${l.jobs.length === 1 ? "" : "s"}` : "Free today"}</div></div>
                      </div>
                      <div className="sched-track" style={{ width: slots * slotPx + 2 * GUTTER, height: laid.rows * LANE_H, backgroundSize: `${slotPx}px 100%, ${slotPx * 2}px 100%`, backgroundPosition: `${GUTTER}px 0, ${GUTTER}px 0` }}>
                        {l.jobs.map((b, i) => {
                          const sp = spans.get(b.id)!;
                          return (
                            <Link key={b.id} to={`/booking/${b.id}`} className={`job-block ${KIND[b.stage]}${sp.late ? " late" : ""}`}
                              aria-label={`${b.booking_id}, ${String(b.answers.customer_name ?? "")}. ${spanTitle(sp).replace("\n", ". ")}`}
                              onMouseEnter={(e) => showTip(e.currentTarget, b, sp, l.name)} onMouseLeave={() => setTip(null)}
                              onFocus={(e) => showTip(e.currentTarget, b, sp, l.name)} onBlur={() => setTip(null)}
                              style={{ left: GUTTER + (sp.start - lo) * 2 * slotPx + 2, width: (sp.end - sp.start) * 2 * slotPx - 4, top: laid.row[i]! * LANE_H + 8, height: LANE_H - 16, bottom: "auto" }}>
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
      {tip && (
        <div className="job-tip" role="tooltip" style={{ left: tip.x, top: tip.y, transform: tip.up ? "translateY(-100%)" : undefined }}>
          <div className="job-tip-head"><b>{tip.b.booking_id}</b><span className={`job-tip-pill ${KIND[tip.b.stage]}`}>{STAGE_NAME[tip.b.stage] ?? tip.b.stage}</span></div>
          <div className="job-tip-name">{String(tip.b.answers.customer_name ?? "")}</div>
          <div className="job-tip-sub">{car(tip.b.answers.car_make_model)} · {city(tip.b.answers.city)}</div>
          <dl>
            <dt>Expert</dt><dd>{tip.who === "Unassigned" ? "Not assigned yet" : tip.who}</dd>
            {spanFacts(tip.sp, hoursOf(tip.b.answers.inspection_time), nowAt).map((f) => <Fragment key={f.label}><dt>{f.label}</dt><dd className={f.bad ? "bad" : ""}>{f.value}</dd></Fragment>)}
          </dl>
        </div>)}
      {assigning && <Actions kind="assign" booking={assigning} experts={experts.data ?? []} onClose={() => setAssigning(null)} fail={fail} onDone={() => { setAssigning(null); say("Assigned."); void refresh("bookings-page"); }} />}
    </>
  );
}
