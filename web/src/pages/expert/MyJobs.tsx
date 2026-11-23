import { MapPin, Phone } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { useList } from "../../api/hooks";
import { STAGE_LABEL, STAGE_TONE, useLabels, useTypeLabels } from "../../api/labels";
import type { Booking } from "../../api/types";
import { addDays, fmtDay, fmtPhone, fmtTime, mapsUrl, today } from "../../lib/format";
import { Empty, Pill, PageHeader } from "../../ui/kit";

const OPEN = ["assigned", "in_progress", "submitted"];

/** Which heading a job sits under: Today, Tomorrow, Later (still to do) or Earlier (done). */
export function groupOf(b: Pick<Booking, "stage" | "answers">, now = new Date()): "Today" | "Tomorrow" | "Later" | "Earlier" {
  if (!OPEN.includes(b.stage)) return "Earlier";
  const d = String(b.answers.inspection_date ?? "");
  const t = today(now);
  if (d <= t) return "Today";                 // overdue jobs stay on top, with today's
  return d === addDays(t, 1) ? "Tomorrow" : "Later";
}

export function MyJobs() {
  const jobs = useList<Booking>("my-jobs", "bookings");
  const car = useLabels("car_make_model");
  const city = useLabels("city");
  const type = useTypeLabels();
  const [sel, setSel] = useState<string | null>(null);
  const slot = (b: Booking) => `${b.answers.inspection_date ?? ""}${b.answers.inspection_time ?? ""}`;
  const all = [...(jobs.data ?? [])].sort((a, b) => slot(a).localeCompare(slot(b)));
  const groups = (["Today", "Tomorrow", "Later", "Earlier"] as const).map((g) => ({ g, rows: g === "Earlier" ? all.filter((b) => groupOf(b) === g).reverse() : all.filter((b) => groupOf(b) === g) })).filter((x) => x.rows.length);
  const current = all.find((b) => b.id === sel) ?? groups[0]?.rows[0];
  return (
    <>
      <PageHeader title="My jobs" count={all.filter((b) => OPEN.includes(b.stage)).length} />
      {jobs.isLoading && <p className="muted">Loading…</p>}
      {!jobs.isLoading && all.length === 0 && <Empty title="No jobs right now">New jobs show here as soon as Ops assign them to you.</Empty>}
      <div className="split-view">
        <div className="job-list">
          {groups.map(({ g, rows }) => (
            <section key={g} aria-label={g}>
              <h2 className="gallery-h">{g} <span className="muted small">{rows.length}</span></h2>
              <div className="table-card">
                {rows.map((b) => (
                  <Link key={b.id} to={`/jobs/${b.id}`} aria-label={`Job ${b.booking_id}`} className={`job-row${current?.id === b.id ? " on" : ""}`}
                    onMouseEnter={() => setSel(b.id)} onFocus={() => setSel(b.id)}>
                    <span className="job-time">{g === "Earlier" || g === "Later" ? fmtDay(b.answers.inspection_date) : fmtTime(b.answers.inspection_time)}</span>
                    <span className="grow" style={{ minWidth: 0 }}><span className="cell-main">{String(b.answers.customer_name ?? "")}</span>
                      <span className="cell-sub ellipsis" style={{ display: "block" }}>{car(b.answers.car_make_model)} · {type(b.inspection_type)} · {city(b.answers.city)}</span></span>
                    <Pill tone={STAGE_TONE[b.stage]}>{STAGE_LABEL[b.stage] ?? b.stage}</Pill>
                  </Link>))}
              </div>
            </section>))}
        </div>
        {current && (
          <aside className="card job-preview" aria-label="Job details">
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
