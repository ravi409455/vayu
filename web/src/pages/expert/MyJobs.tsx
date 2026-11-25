import { MapPin, Phone } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { fetchAll } from "../../api/hooks";
import { STAGE_LABEL, STAGE_TONE, useLabels, useTypeLabels } from "../../api/labels";
import type { Booking } from "../../api/types";
import { addDays, fmtDay, fmtPhone, fmtTime, mapsUrl, today } from "../../lib/format";
import { Empty, LoadError, Pill, PageHeader } from "../../ui/kit";
import { loadJSON, saveJSON } from "../../lib/store";

const OPEN = ["assigned", "in_progress", "submitted"];

/** Which heading a lead sits under: Overdue, Today, Tomorrow, Later (still to do) or Earlier (done). */
export function groupOf(b: Pick<Booking, "stage" | "answers">, now = new Date()): "Overdue" | "Today" | "Tomorrow" | "Later" | "Earlier" {
  if (!OPEN.includes(b.stage)) return "Earlier";
  const d = String(b.answers.inspection_date ?? "");
  const t = today(now);
  if (d < t) return "Overdue";                // on top, and not counted as today's (F-190)
  if (d === t) return "Today";
  return d === addDays(t, 1) ? "Tomorrow" : "Later";
}

export type JobFilter = "open" | "today" | "upcoming" | "started" | "done" | "all";
export const JOB_FILTERS: { id: JobFilter; label: string }[] = [
  { id: "open", label: "To do" }, { id: "today", label: "Today" }, { id: "upcoming", label: "Upcoming" },
  { id: "started", label: "In progress" }, { id: "done", label: "Completed" }, { id: "all", label: "All" },
];

/** Does this job belong in the quick filter? "To do" is everything not finished yet. */
export function matchesJob(b: Pick<Booking, "stage" | "answers">, f: JobFilter, now = new Date()): boolean {
  const g = groupOf(b, now);
  switch (f) {
    case "open": return OPEN.includes(b.stage);
    case "today": return g === "Today";
    case "upcoming": return g === "Tomorrow" || g === "Later";
    case "started": return b.stage === "in_progress" || b.stage === "submitted";
    case "done": return !OPEN.includes(b.stage);
    default: return true;
  }
}

/** Every open lead (however old), plus everything booked from `since` on (finished ones too). */
async function myLeads(since: string): Promise<Booking[]> {
  const lists = await Promise.all([...OPEN.map((stage) => fetchAll<Booking>("bookings", { stage })), fetchAll<Booking>("bookings", { date_from: since })]);
  return [...new Map(lists.flat().map((b) => [b.id, b])).values()];
}

export function MyJobs() {
  const [days, setDays] = useState(30);
  const since = addDays(today(), -days);
  const jobs = useQuery({ queryKey: ["my-jobs", since], queryFn: () => myLeads(since), refetchInterval: 60_000, placeholderData: keepPreviousData });
  const car = useLabels("car_make_model");
  const city = useLabels("city");
  const type = useTypeLabels();
  const [sel, setSel] = useState<string | null>(null);
  const slot = (b: Booking) => `${b.answers.inspection_date ?? ""}${b.answers.inspection_time ?? ""}`;
  const [filter, setFilter] = useState<JobFilter>(() => loadJSON<JobFilter>("vayu:myjobs:filter", "open"));
  const [q, setQ] = useState("");
  useEffect(() => saveJSON("vayu:myjobs:filter", filter), [filter]);
  const everything = [...(jobs.data ?? [])].sort((a, b) => slot(a).localeCompare(slot(b)));
  const needle = q.trim().toLowerCase();
  const all = everything.filter((b) => matchesJob(b, filter) && (!needle || [b.booking_id, b.answers.customer_name, car(b.answers.car_make_model), city(b.answers.city), b.answers.address]
    .some((x) => String(x ?? "").toLowerCase().includes(needle))));
  const countOf = (f: JobFilter) => everything.filter((b) => matchesJob(b, f)).length;
  const groups = (["Overdue", "Today", "Tomorrow", "Later", "Earlier"] as const).map((g) => ({ g, rows: g === "Earlier" ? all.filter((b) => groupOf(b) === g).reverse() : all.filter((b) => groupOf(b) === g) })).filter((x) => x.rows.length);
  const current = all.find((b) => b.id === sel) ?? groups[0]?.rows[0];
  return (
    <>
      <PageHeader title="My leads" count={countOf("open")} />
      {everything.length > 0 && (
        <div className="filters">
          <div className="seg" role="group" aria-label="Show">
            {JOB_FILTERS.map((x) => <button key={x.id} aria-pressed={filter === x.id} onClick={() => setFilter(x.id)}>{x.label} <span className="muted">{countOf(x.id)}</span></button>)}
          </div>
          <input aria-label="Find a lead" className="filter-search" placeholder="Find: customer, booking ID, car, area" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>)}
      {jobs.isLoading && <p className="muted">Loading…</p>}
      {jobs.isError && <LoadError error={jobs.error} what="your leads" onRetry={jobs.refetch} />}
      {!jobs.isLoading && !jobs.isError && everything.length === 0 && <Empty title="No leads right now">New leads show here as soon as Ops assign them to you.</Empty>}
      {!jobs.isLoading && everything.length > 0 && all.length === 0 && <Empty title="Nothing here">{needle ? "No lead matches what you typed." : "No leads in this view."}</Empty>}
      {!jobs.isLoading && !groups.some((x) => x.g === "Earlier") && (filter === "done" || filter === "all") && <p><button className="link" disabled={jobs.isFetching} onClick={() => setDays((d) => d + 30)}>Show leads booked before {fmtDay(since)}</button></p>}
      <div className="split-view">
        <div className="job-list">
          {groups.map(({ g, rows }) => (
            <section key={g} aria-label={g}>
              <h2 className="gallery-h">{g} <span className="muted small">{rows.length}</span></h2>
              {g === "Earlier" && <p className="muted small">Finished leads booked since {fmtDay(since)}.</p>}
              <div className="table-card">
                {rows.map((b) => (
                  <Link key={b.id} to={`/jobs/${b.id}`} aria-label={`Lead ${b.booking_id}`} className={`job-row${current?.id === b.id ? " on" : ""}`}
                    onMouseEnter={() => setSel(b.id)} onFocus={() => setSel(b.id)}>
                    <span className="job-time">{g === "Earlier" || g === "Later" ? fmtDay(b.answers.inspection_date)
                      : b.answers.inspection_date !== today() ? <span className="warn-text" title="Overdue">{fmtDay(b.answers.inspection_date)}</span> : fmtTime(b.answers.inspection_time)}</span>
                    <span className="grow" style={{ minWidth: 0 }}><span className="cell-main">{String(b.answers.customer_name ?? "")}</span>
                      <span className="cell-sub ellipsis" style={{ display: "block" }}>{car(b.answers.car_make_model)} · {type(b.inspection_type)} · {city(b.answers.city)}</span></span>
                    <Pill tone={STAGE_TONE[b.stage]}>{STAGE_LABEL[b.stage] ?? b.stage}</Pill>
                  </Link>))}
              </div>
              {g === "Earlier" && <button className="link" disabled={jobs.isFetching} onClick={() => setDays((d) => d + 30)}>Show older leads</button>}
            </section>))}
        </div>
        {current && (
          <aside className="card job-preview" aria-label="Lead details">
            <div className="muted small">{current.booking_id} · {type(current.inspection_type)}</div>
            <h2 style={{ margin: "2px 0 4px" }}>{String(current.answers.customer_name ?? "")}</h2>
            <div className="chips" style={{ marginBottom: 10 }}><Pill tone={STAGE_TONE[current.stage]}>{STAGE_LABEL[current.stage] ?? current.stage}</Pill><span className="chip">{fmtDay(current.answers.inspection_date)}, {fmtTime(current.answers.inspection_time)}</span></div>
            <dl className="details">
              <dt>Car</dt><dd>{car(current.answers.car_make_model)}</dd>
              <dt>Address</dt><dd>{String(current.answers.address ?? "")}</dd>
              <dt>Phone</dt><dd>{fmtPhone(current.answers.customer_phone)}</dd>
            </dl>
            <div className="bar">
              {current.answers.customer_phone ? <a className="btn" href={`tel:${String(current.answers.customer_phone)}`}><Phone size={15} aria-hidden /> Call</a> : null}
              {current.answers.address ? <a className="btn" href={mapsUrl(`${String(current.answers.address)} ${city(current.answers.city)}`)} target="_blank" rel="noreferrer"><MapPin size={15} aria-hidden /> Directions</a> : null}
              <span className="grow" />
              <Link className="btn primary" to={`/jobs/${current.id}`}>{current.stage === "assigned" ? "Open to start" : "Open"}</Link>
            </div>
          </aside>)}
      </div>
    </>
  );
}
