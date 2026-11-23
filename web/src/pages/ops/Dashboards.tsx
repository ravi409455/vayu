import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import { useList } from "../../api/hooks";
import { STAGE_LABEL, useLabels, useTypeLabels } from "../../api/labels";
import type { User } from "../../api/types";
import { useAuth } from "../../auth";
import { addDays, fmtDay, today } from "../../lib/format";
import { Avatar } from "../../ui/Avatar";
import { Empty, PageHeader } from "../../ui/kit";

type Row = { period: string; key: string; count: number };
type Stats = { bookings: number; completed: number; cancelled: number; completion_rate: number | null; avg_minutes: number | null; on_time: number | null };
type Summary = { date_from: string; date_to: string; period: Stats; previous: Stats; by_expert: (Stats & { expert: number })[] };
const BY = { type: "Type", city: "City", expert: "Expert", stage: "Stage", lead_owner: "Lead owner" } as const;
type Preset = "today" | "7" | "30" | "month" | "custom";
// blue steps of different lightness (told apart without colour vision), then neutrals
const PALETTE = ["#1f3a6e", "#4f7fd9", "#a9c2f2", "#0f766e", "#7dd3c0", "#98a2b3", "#667085", "#d0d5dd"];

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

/** Day bars for up to a month, weeks up to four months, months beyond. */
export const groupFor = (from: string, to: string) => {
  const days = (Date.parse(to) - Date.parse(from)) / 86_400_000 + 1;
  return days <= 31 ? "day" : days <= 120 ? "week" : "month";
};

/** "+8%" / "−1.2 pts" against the previous period, and whether that is good news. */
export function delta(now: number | null, before: number | null, kind: "count" | "pct" | "minutes", higherIsBetter = true): { text: string; good: boolean | null } {
  if (now === null || before === null) return { text: "", good: null };
  if (kind === "pct") { const d = Math.round((now - before) * 10) / 10; return { text: `${d >= 0 ? "+" : "−"}${Math.abs(d)} pts`, good: d === 0 ? null : (d > 0) === higherIsBetter }; }
  if (kind === "minutes") { const d = now - before; return { text: `${d >= 0 ? "+" : "−"}${Math.abs(d)} min`, good: d === 0 ? null : (d > 0) === higherIsBetter }; }
  if (before === 0) return { text: "", good: null };          // nothing to compare with
  const d = Math.round(((now - before) / before) * 100);
  return { text: `${d >= 0 ? "+" : "−"}${Math.abs(d)}%`, good: d === 0 ? null : (d > 0) === higherIsBetter };
}

const mins = (m: number | null) => (m === null ? "—" : m >= 60 ? `${Math.floor(m / 60)} h ${m % 60} m` : `${m} m`);

export function Dashboards() {
  const { can } = useAuth();
  const [preset, setPreset] = useState<Preset>("30");
  const [custom, setCustom] = useState<[string, string]>(presetRange("30"));
  const [by, setBy] = useState<keyof typeof BY>("type");
  const [from, to] = preset === "custom" ? custom : presetRange(preset);
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
  const who = (id: unknown) => (users.data ?? []).find((u) => String(u.id) === String(id));
  const name = (k: string) => !k ? "—" : by === "type" ? typeLabel(k) : by === "city" ? cityLabel(k) : by === "stage" ? STAGE_LABEL[k] ?? k : who(k)?.name || k;
  const totals = periods.map((p) => keys.reduce((n, k) => n + cell(p, k), 0));
  const max = Math.max(1, ...totals);
  const csv = `/api/v1/dashboards/volume?${new URLSearchParams({ group, by, date_from: from, date_to: to, export: "csv" })}`;
  const s = sum.data;
  const kpis = s ? [
    { label: "Bookings", value: String(s.period.bookings), d: delta(s.period.bookings, s.previous.bookings, "count") },
    { label: "Completed", value: String(s.period.completed), d: delta(s.period.completed, s.previous.completed, "count") },
    { label: "Completion rate", value: s.period.completion_rate === null ? "—" : `${s.period.completion_rate}%`, d: delta(s.period.completion_rate, s.previous.completion_rate, "pct") },
    { label: "Average time on site", value: mins(s.period.avg_minutes), d: delta(s.period.avg_minutes, s.previous.avg_minutes, "minutes", false) },
    { label: "Started on time", value: s.period.on_time === null ? "—" : `${s.period.on_time}%`, d: delta(s.period.on_time, s.previous.on_time, "pct") },
    { label: "Cancelled", value: String(s.period.cancelled), d: delta(s.period.cancelled, s.previous.cancelled, "count", false) },
  ] : [];
  const periodLabel = (p: string) => group === "day" ? fmtDay(p) : group === "week" ? `Week ${p.split("-W")[1]}` : new Date(`${p}-01`).toLocaleDateString("en-IN", { month: "short", year: "numeric" });
  return (
    <>
      <PageHeader title="Dashboard" subtitle={`${fmtDay(from)} – ${fmtDay(to)}, compared with the ${preset === "today" ? "day" : "days"} before`}>
        <div className="seg" role="group" aria-label="Period">
          {([["today", "Today"], ["7", "7 days"], ["30", "30 days"], ["month", "This month"], ["custom", "Custom"]] as const).map(([k, l]) =>
            <button key={k} aria-pressed={preset === k} onClick={() => setPreset(k)}>{l}</button>)}
        </div>
        {can("dashboards.export") && <a className="btn" href={csv} download>Export CSV</a>}
      </PageHeader>
      {preset === "custom" && <div className="filters"><label className="date-range"><span>From</span><input aria-label="From" type="date" value={custom[0]} onChange={(e) => setCustom([e.target.value, custom[1]])} /><span>to</span><input aria-label="To" type="date" value={custom[1]} onChange={(e) => setCustom([custom[0], e.target.value])} /></label></div>}
      <section className="kpis" aria-label="Key numbers">
        {kpis.map((k) => (
          <div key={k.label} className="card kpi" style={{ display: "flex", flexDirection: "column", gap: 2, margin: 0 }}>
            <span className="kpi-label">{k.label}</span>
            <span className="kpi-value">{k.value}</span>
            <span className={`kpi-sub ${k.d.good === true ? "ok" : k.d.good === false ? "warn-text" : ""}`}>{k.d.text}{k.d.text && <span className="muted"> vs before</span>}</span>
          </div>))}
      </section>
      <div className="today-cols">
        <section className="card schedule" aria-label="Bookings over time">
          <div className="sheet-head" style={{ padding: "0 0 12px", border: 0 }}>
            <h3>Bookings per {group}</h3>
            <select aria-label="Split by" value={by} onChange={(e) => setBy(e.target.value as keyof typeof BY)} style={{ width: "auto" }}>{Object.entries(BY).map(([k, l]) => <option key={k} value={k}>Split by {l.toLowerCase()}</option>)}</select>
          </div>
          {rows.length === 0 ? <Empty title="No bookings in this range" /> : <>
            <div className="legend-row">{keys.map((k, i) => <span key={k} className="legend-key"><span style={{ background: PALETTE[i % PALETTE.length] }} />{name(k)}</span>)}</div>
            <div className="chart" role="img" aria-label={`Bookings per ${group}, split by ${BY[by].toLowerCase()}. The table below has the exact numbers.`}>
              {periods.map((p, pi) => (
                <div key={p} className="bar-col" title={`${periodLabel(p)}: ${totals[pi]}`}>
                  <div className="bar-stack" style={{ height: `${(totals[pi]! / max) * 100}%` }}>
                    {keys.map((k, i) => cell(p, k) > 0 && <div key={k} style={{ flexGrow: cell(p, k), background: PALETTE[i % PALETTE.length] }} />)}
                  </div>
                </div>))}
            </div>
            <div className="chart-axis"><span>{periodLabel(periods[0]!)}</span>{periods.length > 2 && <span>{periodLabel(periods[Math.floor(periods.length / 2)]!)}</span>}<span>{periodLabel(periods[periods.length - 1]!)}</span></div>
          </>}
        </section>
        <section className="card needs" aria-label="By expert" style={{ padding: "16px 0 6px" }}>
          <h3 style={{ margin: "0 18px 8px" }}>By expert</h3>
          {(s?.by_expert.length ?? 0) === 0 ? <p className="muted small" style={{ margin: "0 18px" }}>No assigned jobs in this range.</p> : (
            <table className="rows"><thead><tr><th>Expert</th><th className="num">Jobs</th><th className="num">Avg time</th><th className="num">On time</th></tr></thead>
              <tbody>{s!.by_expert.map((r) => { const u = who(r.expert); return (
                <tr key={r.expert}><td><span className="who-avatar"><Avatar who={u ?? { id: r.expert }} size={22} />{u?.name || u?.username || `#${r.expert}`}</span></td>
                  <td className="num">{r.bookings}</td><td className="num">{mins(r.avg_minutes)}</td>
                  <td className={`num ${r.on_time !== null && r.on_time < 90 ? "warn-text" : ""}`}>{r.on_time === null ? "—" : `${r.on_time}%`}</td></tr>); })}</tbody></table>)}
        </section>
      </div>
      {rows.length > 0 && (
        <section className="table-card" style={{ marginTop: 16 }} aria-label="Exact numbers">
          <table className="rows" aria-label="Bookings volume"><thead><tr><th>{group === "day" ? "Day" : group === "week" ? "Week" : "Month"}</th>{keys.map((k) => <th key={k} className="num">{name(k)}</th>)}<th className="num">Total</th></tr></thead>
            <tbody>{[...periods].reverse().filter((p) => keys.some((k) => cell(p, k) > 0)).map((p) => <tr key={p}><td>{periodLabel(p)}</td>{keys.map((k) => <td key={k} className="num">{cell(p, k) || ""}</td>)}<td className="num"><strong>{keys.reduce((n, k) => n + cell(p, k), 0)}</strong></td></tr>)}</tbody></table>
        </section>)}
    </>
  );
}
