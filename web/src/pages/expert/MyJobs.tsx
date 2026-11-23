import { Link } from "react-router-dom";
import { useList } from "../../api/hooks";
import { STAGE_LABEL, STAGE_TONE, useLabels, useTypeLabels } from "../../api/labels";
import type { Booking } from "../../api/types";
import { Empty, Pill, PageHeader } from "../../ui/kit";

const OPEN = ["assigned", "in_progress", "submitted"];

export function MyJobs() {
  const jobs = useList<Booking>("my-jobs", "bookings");
  const car = useLabels("car_make_model");
  const type = useTypeLabels();
  const all = jobs.data ?? [];
  const open = all.filter((b) => OPEN.includes(b.stage)).sort((a, b) => `${a.answers.inspection_date}${a.answers.inspection_time}`.localeCompare(`${b.answers.inspection_date}${b.answers.inspection_time}`));
  const done = all.filter((b) => !OPEN.includes(b.stage));
  const card = (b: Booking) => (
    <Link key={b.id} to={`/jobs/${b.id}`} className="card job" aria-label={`Job ${b.booking_id}`}>
      <div className="bar" style={{ marginBottom: 4 }}>
        <strong className="grow">{String(b.answers.customer_name ?? "")}</strong>
        <Pill tone={STAGE_TONE[b.stage]}>{STAGE_LABEL[b.stage] ?? b.stage}</Pill>
      </div>
      <div>{car(b.answers.car_make_model)} · {type(b.inspection_type)}</div>
      <div className="muted small">{String(b.answers.inspection_date ?? "")} {String(b.answers.inspection_time ?? "")} · {b.booking_id}</div>
      <div className="muted small">{String(b.answers.address ?? "")}</div>
    </Link>
  );
  return (
    <div style={{ maxWidth: 640 }}>
      <PageHeader title="My jobs" />
      {jobs.isLoading && <p className="muted">Loading…</p>}
      {!jobs.isLoading && open.length === 0 && <Empty>No jobs right now.</Empty>}
      {open.map(card)}
      {done.length > 0 && <><h2>Earlier</h2>{done.map(card)}</>}
    </div>
  );
}
