import { useMutation, useQuery } from "@tanstack/react-query";
import { PanelLeftClose, PanelLeftOpen, Phone } from "lucide-react";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api, ApiError, explain } from "../../api/client";
import { fetchAll, useList, useRefresh } from "../../api/hooks";
import { keys } from "../../api/keys";
import { STAGE_LABEL, STAGE_TONE, useLabels, useTypeLabels } from "../../api/labels";
import type { Booking, Inspection, User } from "../../api/types";
import { useAuth } from "../../auth";
import { allowedActions } from "../../lib/actions";
import type { Answers } from "../../lib/formSpec";
import { fmtPhone, fmtSlot, fmtStamp, mapsUrl } from "../../lib/format";
import { FLAG_NAME, timingFlags } from "../../lib/timing";
import { usePinnedTrees, useTrees } from "../../lib/useTrees";
import { Avatar } from "../../ui/Avatar";
import { FormRenderer } from "../../ui/FormRenderer";
import { MoreMenu } from "../../ui/Menu";
import { useCrumb } from "../../ui/crumb";
import { LoadError, Pill, Tabs, useToast } from "../../ui/kit";
import { Actions } from "./booking/Actions";
import { ActivityCard } from "./booking/ActivityCard";
import { BookingTab } from "./booking/BookingTab";
import { ConflictBanner } from "./booking/ConflictBanner";
import { InspectionTab } from "./booking/InspectionTab";
import { MediaTab } from "./booking/MediaTab";
import { ReportTab, useReport } from "./booking/ReportTab";
import { ReviewTab } from "./booking/ReviewTab";
import { WaitingFiles } from "./booking/WaitingFiles";
import { type Activity, idsOf, labelOf, mediaFields, type Part } from "./booking/parts";

export function BookingPage() {
  const id = useParams().id!;
  return id === "new" ? <NewBooking /> : <Detail id={id} />;
}

function NewBooking() {
  const { fail } = useToast();
  useCrumb("New booking");
  const nav = useNavigate();
  const { booking: tree, loading } = useTrees();
  const [values, setValues] = useState<Answers>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const create = useMutation({
    mutationFn: () => api<Booking>("bookings", { body: { answers: values } }),
    onSuccess: (b) => nav(`/booking/${b.id}`),
    onError: (e) => {
      if (e instanceof ApiError && e.body.errors) setErrors(e.body.errors as Record<string, string>);
      else if (e instanceof ApiError && e.code === "DUPLICATE_BOOKING_ID") setErrors({ booking_id: explain(e) });
      else fail(e);
    },
  });
  if (loading || !tree) return <p className="muted pad">Loading…</p>;
  return (
    <div style={{ maxWidth: 1040 }}>
      <header className="page-head"><div className="grow"><h1>New booking</h1></div>
        <div className="page-actions"><button onClick={() => nav(-1)}>Cancel</button><button className="primary" disabled={create.isPending} onClick={() => create.mutate()}>Create booking</button></div></header>
      <div className="two-col">
        <FormRenderer kind="booking" tree={tree} values={values} errors={errors} readOnlyKeys={["assigned_expert"]} onChange={(k, v) => { setValues({ ...values, [k]: v }); setErrors({ ...errors, [k]: "" }); }} />
      </div>
    </div>
  );
}

type Tab = "booking" | "inspection" | "media" | "review" | "report";
type ActionKind = "assign" | "reschedule" | "cancel" | "release" | "type";

function Detail({ id }: { id: string }) {
  const { can } = useAuth();
  const { say, fail } = useToast();
  const refresh = useRefresh();
  const b = useQuery({ queryKey: keys.booking(id), queryFn: ({ signal }) => api<Booking>(`bookings/${id}`, { signal }) });
  useCrumb(b.data?.booking_id);
  const insps = useQuery({ queryKey: keys.bookingPart(id, "inspections"), queryFn: ({ signal }) => fetchAll<Inspection>(`bookings/${id}/inspections`, undefined, signal) });
  const activity = useQuery({ queryKey: keys.bookingPart(id, "activity"), queryFn: ({ signal }) => api<Activity[]>(`bookings/${id}/activity`, { signal }) });
  const [tab, setTab] = useState<Tab | null>(null);
  const [action, setAction] = useState<null | ActionKind>(null);
  const [reviewing, setReviewing] = useState("");
  const [rail, setRail] = useState(() => { try { return localStorage.getItem("vayu:booking-rail") !== "hidden"; } catch { return true; } });
  const toggleRail = () => { setRail(!rail); try { localStorage.setItem("vayu:booking-rail", rail ? "hidden" : "shown"); } catch { /* private window: it just will not be remembered */ } };
  const booking = b.data;
  const experts = useList<User>(keys.users(), "users", { role: "expert" });
  const trees = useTrees(booking?.inspection_type);
  const car = useLabels("car_make_model");
  const city = useLabels("city");
  const typeLabel = useTypeLabels();
  // this booking and its parts, every booking list, and the "Needs you" problems (not the old "board")
  const reload = () => refresh(keys.booking(id), keys.bookings(), keys.problems());
  const insp = (insps.data ?? []).filter((i) => i.status === "submitted").sort((a, c) => (c.submitted_at ?? "").localeCompare(a.submitted_at ?? ""))[0] ?? (insps.data ?? [])[0];
  const pinned = usePinnedTrees(insp);                   // the exact versions this inspection was started on
  const report = useReport(id, booking?.stage === "completed" && can("reports.view"));     // for the "PDF out of date" label
  if (b.isError) return <LoadError error={b.error} what="booking" onRetry={b.refetch} />;
  if (!booking) return <p className="muted pad">Loading…</p>;
  const current: Tab = tab ?? (insp?.status === "submitted" ? "inspection" : "booking");
  const expert = experts.data?.find((u) => u.id === booking.assigned_expert);
  const allowed = allowedActions(booking, can);
  const a = booking.answers;
  const mediaCount = insp ? mediaFields(pinned).reduce((n, f) => n + idsOf(insp, f.part, f.key).length, 0) : 0;
  return (
    <div className="record">
      <header className="record-head">
        <div className="grow">
          <div className="muted small">{booking.booking_id} · {typeLabel(booking.inspection_type)}</div>
          <h1>{String(a.customer_name ?? "")}{a.car_make_model ? <span className="muted"> · {car(a.car_make_model)}</span> : null}</h1>
          <div className="chips">
            <Pill tone={STAGE_TONE[booking.stage]}>{STAGE_LABEL[booking.stage] ?? booking.stage}</Pill>
            {booking.conflict && <Pill tone="bad">Conflict: two experts</Pill>}
            {report.data?.out_of_date && <Pill tone="warn">PDF out of date</Pill>}
            {timingFlags(booking.timing).map((f) => <Pill key={f.flag} tone="warn">{f.words}</Pill>)}
            {fmtSlot(a.inspection_date, a.inspection_time) && <span className="chip">{fmtSlot(a.inspection_date, a.inspection_time)}</span>}
            {a.city ? <span className="chip">{city(a.city)}</span> : null}
            {expert ? <span className="chip who-avatar"><Avatar who={expert} size={18} />Expert: {expert.name || expert.username}</span> : null}
          </div>
        </div>
        <div className="page-actions">
          {allowed.has("reschedule") && <button onClick={() => setAction("reschedule")}>Reschedule</button>}
          {allowed.has("assign") && <button className={booking.assigned_expert ? "" : "primary"} onClick={() => setAction("assign")}>{booking.assigned_expert ? "Reassign" : "Assign"}</button>}
          {(allowed.has("type") || allowed.has("release") || allowed.has("cancel")) && <MoreMenu label="More actions" items={[
            { label: "Change type", onClick: () => setAction("type"), hidden: !allowed.has("type") },
            { label: "Force release", onClick: () => setAction("release"), hidden: !allowed.has("release") },
            { label: "Cancel booking", danger: true, onClick: () => setAction("cancel"), hidden: !allowed.has("cancel") },
          ]} />}
        </div>
      </header>
      {booking.alerts?.map((x, i) => <div key={i} className="banner warn" role="alert">{x.detail} <span className="muted small">{fmtStamp(x.at)}</span></div>)}
      {timingFlags(booking.timing).map((f) => (
        <div key={f.flag} className="banner warn" role="status" aria-label={FLAG_NAME[f.flag]} style={{ display: "flex", gap: 12, alignItems: "center" }}>
          <span className="grow">{f.words}.{" "}
            {f.reviewedAt ? <span className="muted small">Reviewed by {f.reviewedBy} · {fmtStamp(f.reviewedAt)}</span>
              : <span className="muted small">{f.flag === "late" ? `Limit: start within ${booking.timing?.grace_minutes} min of the booked time.` : `Limit: take at least ${booking.timing?.min_minutes} min.`}</span>}</span>
          {!f.reviewedAt && can("bookings.review_timing") && <button className="sm" disabled={reviewing === f.flag} onClick={async () => {
            setReviewing(f.flag);
            try { await api(`bookings/${booking.id}/timing-review`, { body: { flag: f.flag } }); say("Marked reviewed."); void reload();
            } catch (e) { fail(e); } finally { setReviewing(""); } }}>Mark reviewed</button>}
        </div>))}
      {booking.conflict && <ConflictBanner booking={booking} insps={insps.data ?? []} experts={experts.data ?? []} onResolved={reload} />}
      {booking.stage === "submitted" && can("media.manage") && <WaitingFiles booking={booking} onFinished={reload} onMedia={() => setTab("media")} />}
      <Tabs value={current} onChange={setTab} tabs={[{ id: "booking", label: "Booking" }, { id: "inspection", label: "Inspection" }, { id: "media", label: mediaCount ? `Media ${mediaCount}` : "Media" }, { id: "review", label: "Review" }, { id: "report", label: "Report" }]} />
      <button className="sm rail-toggle" aria-expanded={rail} onClick={toggleRail}>
        {rail ? <PanelLeftClose size={14} aria-hidden /> : <PanelLeftOpen size={14} aria-hidden />}{rail ? "Hide customer, car and activity" : "Show customer, car and activity"}</button>
      <div className="record-body">
        {rail && <aside className="record-rail" aria-label="Summary">
          <section className="card">
            <h2 className="rail-h">Customer</h2>
            <div style={{ fontWeight: 600 }}>{String(a.customer_name ?? "")}</div>
            {a.customer_phone ? <div className="rail-line"><span className="grow">{fmtPhone(a.customer_phone)}</span><a className="btn sm" href={`tel:${String(a.customer_phone)}`} aria-label="Call the customer"><Phone size={14} aria-hidden /></a></div> : null}
            {a.address ? <><div className="muted small">{String(a.address)}</div><a className="small" href={mapsUrl(`${String(a.address)} ${city(a.city)}`)} target="_blank" rel="noreferrer">Open in Maps</a></> : null}
          </section>
          <section className="card">
            <h2 className="rail-h">Car</h2>
            <dl className="details">
              {a.car_make_model ? <><dt>Model</dt><dd>{car(a.car_make_model)}</dd></> : null}
              <dt>Inspection</dt><dd>{typeLabel(booking.inspection_type)}</dd>
              {insp?.answers.inspection?.registration_no ? <><dt>Registration</dt><dd>{String(insp.answers.inspection.registration_no)}</dd></> : null}
              {insp?.answers.inspection?.chassis_no ? <><dt>Chassis</dt><dd className="mono small">{String(insp.answers.inspection.chassis_no)}</dd></> : null}
              {insp?.answers.inspection?.odometer !== undefined && insp?.answers.inspection?.odometer !== null ? <><dt>Odometer</dt><dd>{Number(insp.answers.inspection.odometer).toLocaleString("en-IN")} km</dd></> : null}
            </dl>
          </section>
          <ActivityCard rows={activity.data ?? []} experts={experts.data ?? []} labels={(k) => {
            const [p, f] = k.split(".");
            if (p === "check") return pinned.inspection?.key_checks?.find((x) => x.key === f)?.label ?? f!;
            return f ? labelOf(pinned[p as Part], f) : labelOf(trees.booking, k); }} typeLabel={typeLabel} />
        </aside>}
        <div className="record-main">
          {current === "booking" && trees.booking && <BookingTab booking={booking} tree={trees.booking} onSaved={reload} />}
          {current === "inspection" && <InspectionTab booking={booking} insp={insp} trees={pinned} activity={activity.data ?? []} onSaved={reload} />}
          {current === "media" && <MediaTab booking={booking} insp={insp} trees={pinned} onChanged={reload} />}
          {current === "review" && <ReviewTab booking={booking} insp={insp} trees={pinned} onSaved={reload} />}
          {current === "report" && <ReportTab booking={booking} activity={activity.data ?? []} />}
        </div>
      </div>
      {action && <Actions kind={action} booking={booking} experts={experts.data ?? []} onClose={() => setAction(null)} onDone={() => { setAction(null); say("Done."); void reload(); }} fail={fail} />}
    </div>
  );
}
