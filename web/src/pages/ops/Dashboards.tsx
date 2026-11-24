import { useEffect, useRef, useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { BarChart3, CalendarDays, Download, Table2 } from "lucide-react";
import { api } from "../../api/client";
import { useList } from "../../api/hooks";
import { STAGE_LABEL, useLabels, useTypeLabels } from "../../api/labels";
import type { User } from "../../api/types";
import { useAuth } from "../../auth";
import { addDays, fmtDay, today } from "../../lib/format";
import { Avatar } from "../../ui/Avatar";
import { Empty, PageHeader } from "../../ui/kit";
import { StackedBars } from "../../ui/StackedBars";

type Row = { period: string; key: string; count: number };
type Stats = { bookings: number; completed: number; cancelled: number; completion_rate: number | null; avg_minutes: number | null; on_time: number | null;
  late: number; late_pct: number | null; quick: number; quick_pct: number | null };
type Summary = { date_from: string; date_to: string; period: Stats; previous: Stats; by_expert: (Stats & { expert: number })[] };
const BY = { type: "Type", city: "City", expert: "Expert", stage: "Stage", lead_owner: "Lead owner" } as const;
type Preset = "today" | "7" | "30" | "month" | "custom";
type Delta = { text: string; good: boolean | null };
const EXPERTS_SHOWN = 8;

/** Rows -> one line per period with a count per key, for a simple table and bars. */
export function pivot(rows: Row[]): { periods: string[]; keys: string[]; cell: (p: string, k: string) => number } {
  const periods = [...new Set(rows.map((r) => r.period))].sort();
  const keys = [...new Set(rows.map((r) => r.key))].sort();
  const m = new Map(rows.map((r) => [`${r.period}|${r.key}`, r.count]));
  return { periods, keys, cell: (p, k) => m.get(`${p}|${k}`) ?? 0 };
}

/** The dates a preset covers. */
export function presetRange(p: Preset, now = new Date()): [string, string] {
  const t = today(now);
  if (p === "today") return [t, t];
  if (p === "7") return [addDays(t, -6), t];
  if (p === "month") return [`${t.slice(0, 8)}01`, t];
  return [addDays(t, -29), t];
}

export function daysBetween(from: string, to: string): string[] {
  const out: string[] = [];
  for (let d = from; d <= to && out.length < 400; d = addDays(d, 1)) out.push(d);
  return out;
}

/** The period the numbers are compared with: as many days, straight before (as the server counts it). */
export function previousRange(from: string, to: string): [string, string] {
  const n = daysBetween(from, to).length;
  return [addDays(from, -n), addDays(from, -1)];
}

/** "26 Oct", with the year only when it is not this year. */
export function shortDay(iso: string, now = new Date()): string {
  const [y, m, d] = iso.split("-").map(Number);
  const s = new Date(y!, m! - 1, d!).toLocaleDateString("en-IN", { day: "numeric", month: "short" });
  return y === now.getFullYear() ? s : `${s} ${y}`;
}

/** "26 Oct – 24 Nov", or one day ("Today", "Mon 23 Nov") when the range is a single day. */
export const rangeText = (from: string, to: string, now = new Date()) =>
  from === to ? fmtDay(from, now) : `${shortDay(from, now)} – ${shortDay(to, now)}`;

/** Why a custom range can't be used, or null when it can. */
export function rangeProblem(from: string, to: string, now = new Date()): string | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(from) || !/^\d{4}-\d{2}-\d{2}$/.test(to)) return "Pick both dates.";
  if (from > to) return "The start date is after the end date.";
  if (to > today(now)) return "The end date is in the future.";
  if (daysBetween(from, to).length >= 400) return "Pick at most a year.";
  return null;
}

/** The Custom button: shows the range it holds, and opens a small box to change it. */
function CustomRange({ on, value, onApply }: { on: boolean; value: [string, string]; onApply: (r: [string, string]) => void }) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState(value);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false); };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("mousedown", away); document.removeEventListener("keydown", esc); };
  }, [open]);
  const problem = rangeProblem(draft[0], draft[1]);
  return (
    <div className="dash-custom" ref={box}>
      <button aria-pressed={on} aria-expanded={open} aria-haspopup="dialog" onClick={() => { setDraft(value); setOpen(!open); }}>
        {on ? <><CalendarDays size={14} aria-hidden />{rangeText(value[0], value[1])}</> : "Custom"}
      </button>
      {open && (
        <div className="dash-custom-box" role="dialog" aria-label="Custom dates">
          <div className="dash-custom-fields">
            <label>From<input type="date" aria-label="From" max={today()} value={draft[0]} onChange={(e) => setDraft([e.target.value, draft[1]])} /></label>
            <label>To<input type="date" aria-label="To" max={today()} value={draft[1]} onChange={(e) => setDraft([draft[0], e.target.value])} /></label>
          </div>
          {problem && draft[0] && draft[1] ? <p className="error" role="alert">{problem}</p> : null}
          <div className="dash-custom-foot">
            <button className="sm" onClick={() => setOpen(false)}>Cancel</button>
            <button className="sm primary" disabled={!!problem} onClick={() => { onApply(draft); setOpen(false); }}>Apply</button>
          </div>
        </div>)}
    </div>
  );
}

/** Day bars for up to a month, weeks up to four months, months beyond. */
export const groupFor = (from: string, to: string) => {
  const days = (Date.parse(to) - Date.parse(from)) / 86_400_000 + 1;
  return days <= 31 ? "day" : days <= 120 ? "week" : "month";
};

/** "+8%" / "−1.2 pts" against the previous period, and whether that is good news. */
export function delta(now: number | null, before: number | null, kind: "count" | "pct" | "minutes", higherIsBetter = true): Delta {
  if (now === null || before === null) return { text: "", good: null };
  if (kind === "pct") { const d = Math.round((now - before) * 10) / 10; return { text: `${d >= 0 ? "+" : "−"}${Math.abs(d)} pts`, good: d === 0 ? null : (d > 0) === higherIsBetter }; }
  if (kind === "minutes") { const d = now - before; return { text: `${d >= 0 ? "+" : "−"}${Math.abs(d)} min`, good: d === 0 ? null : (d > 0) === higherIsBetter }; }
  if (before === 0) return { text: "", good: null };          // nothing to compare with
  const d = Math.round(((now - before) / before) * 100);
  return { text: `${d >= 0 ? "+" : "−"}${Math.abs(d)}%`, good: d === 0 ? null : (d > 0) === higherIsBetter };
}

/** The small chip under a number: ▲ 12% in green when that is good news, red when bad, grey when flat. */
function DeltaChip({ d }: { d: Delta }) {
  if (!d.text) return <span className="muted">No earlier data</span>;
  if (d.good === null) return <span className="dash-chip flat">No change</span>;
  const up = d.text.startsWith("+");
  return <span className={`dash-chip ${d.good ? "good" : "bad"}`} title="Compared with the period before">{up ? "▲" : "▼"} {d.text.slice(1)}</span>;
}

/** One number in a group: label, value (with a small grey unit), and what sits under it. */
function Stat({ label, value, unit, flag, children }: { label: string; value: string; unit?: string; flag?: boolean; children: ReactNode }) {
  return (
    <div className={`dash-stat${flag ? " flag" : ""}`}>
      <span className="dash-stat-label">{label}</span>
      <span className="dash-stat-value">{value}{unit && <small>{unit}</small>}</span>
      <span className="dash-stat-sub">{children}</span>
    </div>
  );
}

/** 40 → ["40", "min"]; 100 → ["1 h 40 m", ""]. */
export const minsParts = (m: number | null): [string, string] =>
  m === null ? ["—", ""] : m >= 60 ? [`${Math.floor(m / 60)} h ${m % 60} m`, ""] : [String(m), "min"];
const mins = (m: number | null) => minsParts(m).filter(Boolean).join(" ");
const pctParts = (p: number | null): [string, string] => (p === null ? ["—", ""] : [String(p), "%"]);
const Dash = () => <span className="dash-zero"><span aria-hidden>–</span><span className="sr-only">none</span></span>;

export function Dashboards() {
  const { can } = useAuth();
  const seesTiming = can("bookings.review_timing");
  const [preset, setPreset] = useState<Preset>("30");
  const [custom, setCustom] = useState<[string, string]>(presetRange("30"));
  const [by, setBy] = useState<keyof typeof BY>("type");
  const [asTable, setAsTable] = useState(false);
  const [allExperts, setAllExperts] = useState(false);
  const [from, to] = preset === "custom" ? custom : presetRange(preset);
  const [prevFrom, prevTo] = previousRange(from, to);
  const group = groupFor(from, to);
  const users = useList<User>("users-all", "users");
  const typeLabel = useTypeLabels();
  const cityLabel = useLabels("city");
  const sum = useQuery({ queryKey: ["dash-summary", from, to], queryFn: () => api<Summary>("dashboards/summary", { query: { date_from: from, date_to: to } }) });
  const vol = useQuery({ queryKey: ["volume", group, by, from, to], queryFn: () => api<{ rows: Row[] }>("dashboards/volume", { query: { group, by, date_from: from, date_to: to } }) });
  const rows = vol.data?.rows ?? [];
  const piv = pivot(rows);
  const { keys, cell } = piv;
  // every day of the range gets a bar (an empty day is a gap, not missing); weeks and months as given
  const periods = group === "day" && rows.length ? daysBetween(from, to) : piv.periods;
  const total = rows.reduce((n, r) => n + r.count, 0);
  const who = (id: unknown) => (users.data ?? []).find((u) => String(u.id) === String(id));
  const name = (k: string) => !k ? "—" : by === "type" ? typeLabel(k) : by === "city" ? cityLabel(k) : by === "stage" ? STAGE_LABEL[k] ?? k : who(k)?.name || k;
  const csv = `/api/v1/dashboards/volume?${new URLSearchParams({ group, by, date_from: from, date_to: to, export: "csv" })}`;
  const s = sum.data;
  const periodLabel = (p: string, short = false) => group === "day"
    ? (short ? new Date(`${p}T00:00`).toLocaleDateString("en-IN", { day: "numeric", month: "short" }) : fmtDay(p))
    : group === "week" ? `${short ? "W" : "Week "}${p.split("-W")[1]}` : new Date(`${p}-01`).toLocaleDateString("en-IN", { month: "short", ...(short ? {} : { year: "numeric" }) });
  const experts = [...(s?.by_expert ?? [])].sort((a, b) => b.bookings - a.bookings);
  const shownExperts = allExperts ? experts : experts.slice(0, EXPERTS_SHOWN);
  const flagLink = (view: string) => `/bookings?view=${view}&date_from=${from}&date_to=${to}&all=1`;
  return (
    <>
      <PageHeader title="Dashboard" subtitle={<>{rangeText(from, to)} <span className="dash-vs">vs {rangeText(prevFrom, prevTo)}</span></>}>
        <div className="seg" role="group" aria-label="Period">
          {([["today", "Today"], ["7", "7 days"], ["30", "30 days"], ["month", "This month"]] as const).map(([k, l]) =>
            <button key={k} aria-pressed={preset === k} onClick={() => setPreset(k)}>{l}</button>)}
          <CustomRange on={preset === "custom"} value={custom} onApply={(r) => { setCustom(r); setPreset("custom"); }} />
        </div>
        {can("dashboards.export") && <a className="btn sm dash-export" href={csv} download title={`Download bookings per ${group}, split by ${BY[by].toLowerCase()}, as a CSV file`}><Download size={14} aria-hidden />Export CSV</a>}
      </PageHeader>
      {sum.isError && <p className="error" role="alert">Could not load the numbers. Refresh the page to try again.</p>}

      {s && (
        <div className="dash-groups">
          <section className="dash-group" aria-label="Bookings">
            <h2 className="dash-group-title">Bookings</h2>
            <div className="dash-stats">
              <Stat label="Booked" value={String(s.period.bookings)}><DeltaChip d={delta(s.period.bookings, s.previous.bookings, "count")} /></Stat>
              <Stat label="Completed" value={String(s.period.completed)}><DeltaChip d={delta(s.period.completed, s.previous.completed, "count")} /></Stat>
              <Stat label="Completion rate" value={pctParts(s.period.completion_rate)[0]} unit={pctParts(s.period.completion_rate)[1]}><DeltaChip d={delta(s.period.completion_rate, s.previous.completion_rate, "pct")} /></Stat>
              <Stat label="Cancelled" value={String(s.period.cancelled)}><DeltaChip d={delta(s.period.cancelled, s.previous.cancelled, "count", false)} /></Stat>
            </div>
          </section>
          <section className="dash-group" aria-label="On site">
            <h2 className="dash-group-title">On site</h2>
            <div className="dash-stats">
              <Stat label="Avg time on site" value={minsParts(s.period.avg_minutes)[0]} unit={minsParts(s.period.avg_minutes)[1]}><DeltaChip d={delta(s.period.avg_minutes, s.previous.avg_minutes, "minutes", false)} /></Stat>
              <Stat label="Started on time" value={pctParts(s.period.on_time)[0]} unit={pctParts(s.period.on_time)[1]}><DeltaChip d={delta(s.period.on_time, s.previous.on_time, "pct")} /></Stat>
              {seesTiming && <>
                <Stat label="Started late" value={String(s.period.late)} unit={s.period.late_pct === null ? "" : `${s.period.late_pct}%`} flag={s.period.late > 0}>
                  {s.period.late > 0 ? <Link to={flagLink("late")}>View bookings →</Link> : <DeltaChip d={delta(s.period.late, s.previous.late, "count", false)} />}</Stat>
                <Stat label="Too quick" value={String(s.period.quick)} unit={s.period.quick_pct === null ? "" : `${s.period.quick_pct}%`} flag={s.period.quick > 0}>
                  {s.period.quick > 0 ? <Link to={flagLink("quick")}>View bookings →</Link> : <DeltaChip d={delta(s.period.quick, s.previous.quick, "count", false)} />}</Stat>
              </>}
            </div>
          </section>
        </div>)}

      <section className="card dash-card" aria-label="Bookings over time">
        <div className="dash-card-head">
          <h3>Bookings per {group}</h3>
          {total > 0 && <span className="muted small">{total.toLocaleString("en-IN")} booking{total === 1 ? "" : "s"}</span>}
          <div className="dash-card-tools">
            <div className="seg sm" role="group" aria-label="Split by">
              {Object.entries(BY).map(([k, l]) => <button key={k} aria-pressed={by === k} onClick={() => setBy(k as keyof typeof BY)}>{l}</button>)}
            </div>
            <div className="seg sm" role="group" aria-label="Show as">
              <button aria-pressed={!asTable} aria-label="Chart" title="Chart" onClick={() => setAsTable(false)}><BarChart3 size={14} aria-hidden /></button>
              <button aria-pressed={asTable} aria-label="Table" title="Table" onClick={() => setAsTable(true)}><Table2 size={14} aria-hidden /></button>
            </div>
          </div>
        </div>
        {rows.length === 0 ? <Empty title="No bookings in this range" /> : asTable ? (
          <div className="dash-table-wrap">
            <table className="rows dash-table" aria-label="Bookings volume"><thead><tr><th>{group === "day" ? "Day" : group === "week" ? "Week" : "Month"}</th>{keys.map((k) => <th key={k} className="num">{name(k)}</th>)}<th className="num">Total</th></tr></thead>
              <tbody>{[...periods].reverse().filter((p) => keys.some((k) => cell(p, k) > 0)).map((p) => <tr key={p}><td>{periodLabel(p)}</td>{keys.map((k) => <td key={k} className="num">{cell(p, k) || <Dash />}</td>)}<td className="num"><strong>{keys.reduce((n, k) => n + cell(p, k), 0)}</strong></td></tr>)}</tbody></table>
          </div>
        ) : (
          <StackedBars series={keys.map((k) => ({ key: k, name: name(k) }))}
            cols={periods.map((p) => ({ key: p, label: periodLabel(p, true), long: periodLabel(p), values: Object.fromEntries(keys.map((k) => [k, cell(p, k)])) }))} />)}
      </section>

      <section className="card dash-card flush" aria-label="By expert">
        <div className="dash-card-head">
          <h3>By expert</h3>
          {experts.length > 0 && <span className="muted small">{experts.length} expert{experts.length === 1 ? "" : "s"} · most bookings first</span>}
        </div>
        {experts.length === 0 ? <p className="muted small dash-empty">No assigned bookings in this range.</p> : (
          <div className="dash-table-wrap">
            <table className="rows dash-table">
              <thead><tr><th>Expert</th><th className="num">Bookings</th><th className="num">Avg time on site</th><th className="num">On time</th>{seesTiming && <><th className="num">Started late</th><th className="num">Too quick</th></>}</tr></thead>
              <tbody>{shownExperts.map((r) => { const u = who(r.expert); const low = r.on_time !== null && r.on_time < 90; return (
                <tr key={r.expert}><td><span className="who-avatar"><Avatar who={u ?? { id: r.expert }} size={24} />{u?.name || u?.username || `#${r.expert}`}</span></td>
                  <td className="num">{r.bookings}</td>
                  <td className="num">{r.avg_minutes === null ? <Dash /> : mins(r.avg_minutes)}</td>
                  <td className="num">{r.on_time === null ? <Dash /> : <span className={`dash-ontime${low ? " low" : ""}`}><span className="dash-meter" aria-hidden><i style={{ width: `${r.on_time}%` }} /></span>{r.on_time}%</span>}</td>
                  {seesTiming && <>
                    <td className="num">{r.late ? <span className="dash-flag">{r.late}</span> : <Dash />}</td>
                    <td className="num">{r.quick ? <span className="dash-flag">{r.quick}</span> : <Dash />}</td></>}</tr>); })}</tbody>
            </table>
          </div>)}
        {experts.length > EXPERTS_SHOWN && (
          <button className="link dash-more" onClick={() => setAllExperts(!allExperts)}>{allExperts ? "Show fewer" : `Show all ${experts.length} experts`}</button>)}
      </section>
    </>
  );
}
