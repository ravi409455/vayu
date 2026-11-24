import { Download, FileText, PanelLeftClose, PanelLeftOpen, Phone, Plus, RefreshCw } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import { api, ApiError, explain } from "../../api/client";
import { asList, useList, useRefresh } from "../../api/hooks";
import { STAGE_LABEL, STAGE_TONE, useInspectionTypes, useLabels, useTypeLabels } from "../../api/labels";
import type { Booking, FormPage, FormSection, FormVersion, Inspection, MasterListItem, User } from "../../api/types";
import { useAuth } from "../../auth";
import { saveDirty } from "../../lib/saveDirty";
import { usePinnedTrees, useTrees } from "../../lib/useTrees";
import { addFile, discardFile, uploaded } from "../../lib/uploadManager";
import { FormRenderer } from "../../ui/FormRenderer";
import { Confirm, Empty, Field, Modal, Pill, Tabs, useToast } from "../../ui/kit";
import { AnswerSheet, AnswerValue, defectOf, readableFields, type SheetFilter } from "../../ui/AnswerSheet";
import { Avatar } from "../../ui/Avatar";
import { isPdf, mediaUrl, useMediaUrl, Thumb } from "../../ui/MediaThumb";
import { MoreMenu } from "../../ui/Menu";
import { fmtPhone, fmtSlot, fmtStamp, mapsUrl } from "../../lib/format";
import { FLAG_NAME, timingFlags } from "../../lib/timing";
import { missingFields } from "../../lib/formSpec";
import { StaleDialog, type Stale } from "../../ui/StaleDialog";
import type { Answers } from "../../lib/formSpec";
import { useCrumb } from "../../ui/crumb";

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

type Tab = "booking" | "inspection" | "media" | "ratings" | "report";
type Activity = { at: string; kind: string; by: { id: number; name: string; role: string } | null; changes: Record<string, [unknown, unknown]>; keys: string[] };
type ActionKind = "assign" | "reschedule" | "cancel" | "release" | "type";

function Detail({ id }: { id: string }) {
  const { can } = useAuth();
  const { say, fail } = useToast();
  const refresh = useRefresh();
  const b = useQuery({ queryKey: ["booking", id], queryFn: () => api<Booking>(`bookings/${id}`) });
  useCrumb(b.data?.booking_id);
  const insps = useQuery({ queryKey: ["inspections", id], queryFn: async () => asList<Inspection>(await api(`bookings/${id}/inspections`)) });
  const activity = useQuery({ queryKey: ["activity", id], queryFn: () => api<Activity[]>(`bookings/${id}/activity`) });
  const [tab, setTab] = useState<Tab | null>(null);
  const [action, setAction] = useState<null | ActionKind>(null);
  const [rail, setRail] = useState(() => { try { return localStorage.getItem("vayu:booking-rail") !== "hidden"; } catch { return true; } });
  const toggleRail = () => { setRail(!rail); try { localStorage.setItem("vayu:booking-rail", rail ? "hidden" : "shown"); } catch { /* private window: it just will not be remembered */ } };
  const booking = b.data;
  const experts = useList<User>("experts", "users", { role: "expert" });
  const trees = useTrees(booking?.inspection_type);
  const car = useLabels("car_make_model");
  const city = useLabels("city");
  const typeLabel = useTypeLabels();
  const reload = () => Promise.all([refresh("booking"), refresh("inspections"), refresh("board"), refresh("report"), refresh("activity"), refresh("bookings-page")]);
  const insp = (insps.data ?? []).filter((i) => i.status === "submitted").sort((a, c) => (c.submitted_at ?? "").localeCompare(a.submitted_at ?? ""))[0] ?? (insps.data ?? [])[0];
  const pinned = usePinnedTrees(insp);                   // the exact versions this inspection was started on
  if (!booking) return <p className="muted pad">Loading…</p>;
  const current: Tab = tab ?? (insp?.status === "submitted" ? "inspection" : "booking");
  const expert = experts.data?.find((u) => u.id === booking.assigned_expert);
  const open = booking.stage === "draft" || booking.stage === "assigned";
  const live = booking.stage !== "cancelled" && booking.stage !== "completed";
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
            {timingFlags(booking.timing).map((f) => <Pill key={f.flag} tone="bad">{f.words}</Pill>)}
            {fmtSlot(a.inspection_date, a.inspection_time) && <span className="chip">{fmtSlot(a.inspection_date, a.inspection_time)}</span>}
            {a.city ? <span className="chip">{city(a.city)}</span> : null}
            {expert ? <span className="chip who-avatar"><Avatar who={expert} size={18} />Expert: {expert.name || expert.username}</span> : null}
          </div>
        </div>
        <div className="page-actions">
          {can("bookings.reschedule") && live && <button onClick={() => setAction("reschedule")}>Reschedule</button>}
          {can("bookings.assign") && booking.stage !== "cancelled" && <button className={booking.assigned_expert ? "" : "primary"} onClick={() => setAction("assign")}>{booking.assigned_expert ? "Reassign" : "Assign"}</button>}
          <MoreMenu label="More actions" items={[
            { label: "Change type", onClick: () => setAction("type"), hidden: !(can("bookings.edit") && open) },
            { label: "Force release", onClick: () => setAction("release"), hidden: !(can("bookings.force_release") && booking.stage === "in_progress") },
            { label: "Cancel booking", danger: true, onClick: () => setAction("cancel"), hidden: !(can("bookings.cancel") && live) },
          ]} />
        </div>
      </header>
      {booking.alerts?.map((x, i) => <div key={i} className="banner warn" role="alert">{x.detail} <span className="muted small">{fmtStamp(x.at)}</span></div>)}
      {timingFlags(booking.timing).map((f) => (
        <div key={f.flag} className="banner warn" role="status" aria-label={FLAG_NAME[f.flag]} style={{ display: "flex", gap: 12, alignItems: "center" }}>
          <span className="grow">{f.words}.{" "}
            {f.reviewedAt ? <span className="muted small">Reviewed by {f.reviewedBy} · {fmtStamp(f.reviewedAt)}</span>
              : <span className="muted small">{f.flag === "late" ? `Limit: start within ${booking.timing?.grace_minutes} min of the booked time.` : `Limit: take at least ${booking.timing?.min_minutes} min.`}</span>}</span>
          {!f.reviewedAt && can("bookings.review_timing") && <button className="sm" onClick={async () => { try { await api(`bookings/${booking.id}/timing-review`, { body: { flag: f.flag } }); say("Marked reviewed."); void reload(); void refresh("problems"); } catch (e) { fail(e); } }}>Mark reviewed</button>}
        </div>))}
      {booking.conflict && <ConflictBanner booking={booking} insps={insps.data ?? []} experts={experts.data ?? []} onResolved={reload} />}
      <Tabs value={current} onChange={setTab} tabs={[{ id: "booking", label: "Booking" }, { id: "inspection", label: "Inspection" }, { id: "media", label: mediaCount ? `Media ${mediaCount}` : "Media" }, { id: "ratings", label: "Ratings" }, { id: "report", label: "Report" }]} />
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
          <ActivityCard rows={activity.data ?? []} experts={experts.data ?? []} labels={(k) => { const [p, f] = k.split("."); return f ? labelOf(pinned[p as Part], f) : labelOf(trees.booking, k); }} typeLabel={typeLabel} />
        </aside>}
        <div className="record-main">
          {current === "booking" && trees.booking && <BookingTab booking={booking} tree={trees.booking} onSaved={reload} />}
          {current === "inspection" && <InspectionTab booking={booking} insp={insp} trees={pinned} activity={activity.data ?? []} onSaved={reload} />}
          {current === "media" && <MediaTab booking={booking} insp={insp} trees={pinned} onChanged={reload} />}
          {current === "ratings" && <RatingsTab insp={insp} trees={pinned} onSaved={reload} />}
          {current === "report" && <ReportTab booking={booking} />}
        </div>
      </div>
      {action && <Actions kind={action} booking={booking} experts={experts.data ?? []} onClose={() => setAction(null)} onDone={() => { setAction(null); say("Done."); void reload(); }} fail={fail} />}
    </div>
  );
}

/** Admin only (the server sends the old file's id to nobody else): open a replaced file. */
function openOld(id: string) {
  const w = window.open("", "_blank");            // opened now, so the pop-up blocker allows it
  void mediaUrl(id).then((l) => { if (l && w) w.location.href = l.url; else w?.close(); });
}

const labelOf = (tree: FormVersion | null | undefined, key: string) =>
  tree?.pages.flatMap((p) => p.sections.flatMap((s) => s.fields)).find((f) => f.key === key)?.label || key;

/** One line per thing that happened, newest first. */
export function activityText(r: Activity, expertName: (id: unknown) => string, label: (k: string) => string, typeLabel: (k: unknown) => string): string {
  const by = r.by?.name ?? "The system";
  const c = r.changes;
  if (r.kind === "created") return `Created by ${by}`;
  if (r.kind === "inspection_edited") return `${by} changed ${r.keys.length} answer${r.keys.length === 1 ? "" : "s"}`;
  if (r.kind === "ratings_changed") return `${by} changed the ratings`;
  if (r.kind === "media_replaced") return `${by} replaced a file in ${r.keys.map(label).join(", ") || "the inspection"}`;
  if (r.kind === "media_added") return `${by} added a file to ${r.keys.map(label).join(", ") || "the inspection"}`;
  if (r.kind === "late_reviewed") return `Late start reviewed by ${by}`;
  if (r.kind === "quick_reviewed") return `Quick finish reviewed by ${by}`;
  const stage = c.stage?.[1];
  if (stage === "completed") return "Completed: every file uploaded";
  if (stage === "submitted") return `Submitted by ${by}`;
  if (stage === "in_progress") return `Started by ${by}`;
  if (stage === "cancelled") return `Cancelled by ${by}`;
  if (stage === "assigned" && c.stage?.[0] === "in_progress") return `Force-released by ${by}`;
  if (c.assigned_expert) return `${c.assigned_expert[0] ? "Reassigned" : "Assigned"} to ${expertName(c.assigned_expert[1])} by ${by}`;
  if (c.inspection_date || c.inspection_time) return `Rescheduled to ${fmtSlot(c.inspection_date?.[1], c.inspection_time?.[1])} by ${by}`;
  if (c.inspection_type) return `Type changed to ${typeLabel(c.inspection_type[1])} by ${by}`;
  if (c.conflict) return `Conflict resolved by ${by}`;
  return `${by} changed ${r.keys.map(label).join(", ") || "the booking"}`;
}

function ActivityCard({ rows, experts, labels, typeLabel }: { rows: Activity[]; experts: User[]; labels: (k: string) => string; typeLabel: (k: unknown) => string }) {
  const [all, setAll] = useState(false);
  const name = (id: unknown) => { const u = experts.find((x) => x.id === id); return u ? u.name || u.username : "an expert"; };
  const shown = all ? rows : rows.slice(0, 6);
  return (
    <section className="card" aria-label="Activity">
      <h2 className="rail-h">Activity</h2>
      {rows.length === 0 && <p className="muted small">Nothing yet.</p>}
      <ol className="timeline">
        {shown.map((r, i) => (
          <li key={i} className={r.kind === "inspection_edited" || r.kind === "edited" ? "edit" : r.changes.stage ? "stage" : ""}>
            <div>{activityText(r, name, labels, typeLabel)}</div>
            {typeof r.changes.media?.[0] === "string" && <button className="link small" onClick={() => openOld(String(r.changes.media![0]))}>Open the old file</button>}
            <div className="muted small">{fmtStamp(r.at)}</div>
          </li>))}
      </ol>
      {rows.length > 6 && <button className="link" onClick={() => setAll(!all)}>{all ? "Show less" : `Show all ${rows.length}`}</button>}
    </section>
  );
}

function ConflictBanner({ booking, insps, experts, onResolved }: { booking: Booking; insps: Inspection[]; experts: User[]; onResolved: () => void }) {
  const { can } = useAuth();
  const { fail, say } = useToast();
  const [keep, setKeep] = useState("");
  const who = (id: number) => experts.find((u) => u.id === id)?.name ?? `#${id}`;
  const submitted = insps.filter((i) => i.status === "submitted");
  return (
    <div className="banner bad" role="alert">
      <strong>Two experts submitted this booking.</strong> Choose which inspection counts; the other is kept but set aside.
      {can("bookings.edit") && submitted.length > 1 && (
        <div className="bar" style={{ marginTop: 8, marginBottom: 0 }}>
          <select aria-label="Inspection to keep" value={keep} onChange={(e) => setKeep(e.target.value)} style={{ maxWidth: 320 }}><option value="">Choose…</option>{submitted.map((i) => <option key={i.id} value={i.id}>{who(i.expert)} · {fmtStamp(i.submitted_at)}</option>)}</select>
          <button className="primary" disabled={!keep} onClick={async () => { try { await api(`bookings/${booking.id}/resolve-conflict`, { body: { inspection: keep } }); say("Resolved."); onResolved(); } catch (e) { fail(e); } }}>Keep this one</button>
        </div>)}
    </div>
  );
}

/** Edit one section in place: its inputs, Save and Cancel. */
function SectionEditor({ children, onSave, onCancel, saving, changed }: { children: React.ReactNode; onSave: () => void; onCancel: () => void; saving: boolean; changed: boolean }) {
  return (
    <>
      <div className="two-col">{children}</div>
      <div className="bar" style={{ marginTop: 8, marginBottom: 0 }}>
        <button className="primary" disabled={!changed || saving} onClick={onSave}>Save changes</button>
        <button onClick={onCancel}>Cancel</button>
      </div>
    </>
  );
}

const onlySection = (page: FormPage, s: FormSection): FormPage[] => [{ ...page, sections: [s] }];

function BookingTab({ booking, tree, onSaved }: { booking: Booking; tree: FormVersion; onSaved: () => void }) {
  const { can } = useAuth();
  const { say, fail } = useToast();
  const [values, setValues] = useState<Answers>(booking.answers);
  const [dirty, setDirty] = useState<Answers>({});
  const [stale, setStale] = useState<Stale | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [editing, setEditing] = useState<{ page: FormPage; section: FormSection } | null>(null);
  const [saving, setSaving] = useState(false);
  useEffect(() => { setValues({ ...booking.answers, ...dirty }); }, [booking.row_version]); // eslint-disable-line react-hooks/exhaustive-deps
  const change = (k: string, v: unknown) => { setValues({ ...values, [k]: v }); setDirty({ ...dirty, [k]: v }); setErrors({ ...errors, [k]: "" }); };
  const cancel = () => { setDirty({}); setErrors({}); setValues(booking.answers); setEditing(null); };
  async function save(rowVersion = booking.row_version) {
    setSaving(true);
    try {
      const r = await saveDirty((rv, ch) => api(`bookings/${booking.id}`, { method: "PATCH", body: { row_version: rv, answers: ch } }), rowVersion, dirty);
      if (!r.ok) return setStale(r.stale);
      setDirty({}); setStale(null); setEditing(null); say("Saved."); onSaved();
    } catch (e) {
      if (e instanceof ApiError && e.body.errors) setErrors(e.body.errors as Record<string, string>);
      else if (e instanceof ApiError && e.code === "FIELD_ACCESS") setErrors(Object.fromEntries(((e.body.keys as string[]) ?? []).map((k) => [k, "You cannot change this now."])));
      else if (e instanceof ApiError && e.code === "DUPLICATE_BOOKING_ID") setErrors({ booking_id: explain(e) });
      else fail(e);
    } finally { setSaving(false); }
  }
  const editor = editing && (
    <SectionEditor changed={Object.keys(dirty).length > 0} saving={saving} onSave={() => save()} onCancel={cancel}>
      <FormRenderer kind="booking" tree={tree} pages={onlySection(editing.page, editing.section)} values={values} errors={errors} readOnlyKeys={["assigned_expert", "inspection_type"]} onChange={change} />
    </SectionEditor>);
  return (
    <>
      <AnswerSheet part={{ kind: "booking", tree, values }} onEdit={can("bookings.edit") ? (page, section) => { cancel(); setEditing({ page, section }); } : undefined}
        editing={editing ? { sectionId: editing.section.id, node: editor } : null} />
      {stale && <StaleDialog info={stale} mine={Object.keys(dirty)} onRetry={() => save(stale.rowVersion)} onReload={() => { setDirty({}); setStale(null); onSaved(); }} />}
    </>
  );
}

type Trees = ReturnType<typeof usePinnedTrees>;
type Part = "inspection" | "start" | "end";
type Parts = Record<Part, Answers>;
const NO_ANSWERS: Parts = { inspection: {}, start: {}, end: {} };
const PART_ORDER: Part[] = ["start", "inspection", "end"];

function InspectionTab({ booking, insp, trees, activity, onSaved }: { booking: Booking; insp?: Inspection; trees: Trees; activity: Activity[]; onSaved: () => void }) {
  const { can } = useAuth();
  const { say, fail } = useToast();
  const [vals, setVals] = useState<Parts>(NO_ANSWERS);
  const [dirty, setDirty] = useState<Parts>(NO_ANSWERS);
  const [stale, setStale] = useState<Stale | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [filter, setFilter] = useState<SheetFilter>("all");
  const [editing, setEditing] = useState<{ part: Part; page: FormPage; section: FormSection } | null>(null);
  const [saving, setSaving] = useState(false);
  const rv = insp?.row_version;
  const fromServer = (i: Inspection, d: Parts): Parts => ({ inspection: { ...(i.answers.inspection ?? {}), ...d.inspection }, start: { ...(i.answers.start ?? {}), ...d.start }, end: { ...(i.answers.end ?? {}), ...d.end } });
  useEffect(() => { if (insp) setVals(fromServer(insp, dirty)); }, [insp?.id, rv]); // eslint-disable-line react-hooks/exhaustive-deps
  const edited = useMemo(() => {
    const out: Record<Part, Set<string>> = { inspection: new Set(), start: new Set(), end: new Set() };
    activity.filter((r) => r.kind === "inspection_edited" && r.by && r.by.role !== "expert").forEach((r) => r.keys.forEach((k) => { const [part, key] = k.split("."); if (part && key && part in out) out[part as Part].add(key); }));
    return out;
  }, [activity]);
  if (!insp) return <Empty title="No inspection yet">It shows here once the expert submits it.</Empty>;
  const ctxFor = (part: Part) => ({ booking: booking.answers, ...Object.fromEntries(PART_ORDER.filter((p) => p !== part).map((p) => [p, vals[p]])) });
  const parts = PART_ORDER.filter((p) => trees[p]).map((p) => ({ part: p, tree: trees[p]! }));
  const rows = parts.flatMap(({ part, tree }) => readableFields(part, tree, vals[part], ctxFor(part)).map((r) => ({ ...r, part, v: vals[part][r.f.key] })));
  const isEmpty = (v: unknown) => v === undefined || v === null || v === "" || (Array.isArray(v) && v.length === 0);
  const answered = rows.filter((r) => !isEmpty(r.v)).length;
  const defects = rows.map((r) => defectOf(r.f, r.v)).filter(Boolean) as string[];
  const editedCount = rows.filter((r) => edited[r.part].has(r.f.key)).length;
  const missing = parts.reduce((n, { part, tree }) => n + missingFields(part, tree, vals[part], ctxFor(part)).length, 0);
  const checks = (trees.inspection?.pages ?? []).flatMap((p) => p.sections.flatMap((s) => s.fields.filter((f) => f.type === "derived")));
  const mineKeys = PART_ORDER.flatMap((p) => Object.keys(dirty[p]));
  const change = (part: Part) => (k: string, v: unknown) => { setVals({ ...vals, [part]: { ...vals[part], [k]: v } }); setDirty({ ...dirty, [part]: { ...dirty[part], [k]: v } }); setErrors({ ...errors, [k]: "" }); };
  const cancel = () => { setDirty(NO_ANSWERS); setErrors({}); setVals(fromServer(insp, NO_ANSWERS)); setEditing(null); };
  async function save(rowVersion = insp!.row_version) {
    setSaving(true);
    try {
      const r = await saveDirty((v, ch) => api(`inspections/${insp!.id}`, { method: "PATCH", body: { row_version: v, answers: ch } }), rowVersion, dirty);
      if (!r.ok) return setStale(r.stale);
      setDirty(NO_ANSWERS); setStale(null); setEditing(null); say("Saved. Ratings and Key Checks were recalculated."); onSaved();
    } catch (e) {
      if (e instanceof ApiError && e.body.errors) setErrors(e.body.errors as Record<string, string>);
      else if (e instanceof ApiError && e.code === "FIELD_ACCESS") setErrors(Object.fromEntries(((e.body.keys as string[]) ?? []).map((k) => [k, "You cannot change this now."])));
      else fail(e);
    } finally { setSaving(false); }
  }
  const canEdit = can("submissions.edit");
  const pageCounts = parts.flatMap(({ part, tree }) => tree.pages.map((p) => {
    const mine = rows.filter((r) => r.part === part && r.page.id === p.id);
    return { id: `${part}-p${p.id}`, title: p.title, n: mine.length, done: mine.filter((r) => !isEmpty(r.v)).length, defects: mine.filter((r) => defectOf(r.f, r.v)).length };
  })).filter((p) => p.n > 0);
  const major = defects.filter((d) => d === "Major").length;
  return (
    <>
      <section className="card summary-strip" aria-label="Inspection summary">
        <div><div className="muted small">Answered</div><div className="big">{answered} <span className="muted small">of {rows.length}</span></div>
          <div className="progress thin"><div style={{ width: `${rows.length ? (answered / rows.length) * 100 : 0}%` }} /></div></div>
        <div><div className="muted small">Defects</div><div className={`big${defects.length ? " bad-text" : ""}`}>{defects.length}</div><div className="muted small">{major} major · {defects.length - major} other</div></div>
        {insp.scores?.derived && checks.length > 0 && <div><div className="muted small">Key Checks</div><div className="chips">{checks.map((f) => <span key={f.key} className="chip">{f.label}: {insp.scores?.derived?.[f.key] === true ? String(f.config.true_label ?? "Yes") : String(f.config.false_label ?? "No")}</span>)}</div></div>}
        <div><div className="muted small">Required, not answered</div><div className={`big${missing ? " warn-text" : ""}`}>{missing}</div></div>
      </section>
      <div className="bar">
        <div className="seg" role="group" aria-label="Show">
          {([["all", `All ${rows.length}`], ["defects", `Defects ${defects.length}`], ["edited", `Edited by Ops ${editedCount}`], ["empty", `Not answered ${rows.length - answered}`]] as const).map(([k, l]) =>
            <button key={k} aria-pressed={filter === k} onClick={() => setFilter(k)}>{l}</button>)}
        </div>
        <span className="grow" />
        {insp.last_edited_by && <span className="muted small">Last edited by {insp.last_edited_by}, {fmtStamp(insp.last_edited_at)}</span>}
      </div>
      <div className="review">
        <nav className="card review-index" aria-label="Inspection pages">
          {pageCounts.map((p) => <a key={p.id} href={`#${p.id}`} onClick={(e) => { e.preventDefault(); document.getElementById(p.id)?.scrollIntoView({ behavior: "smooth", block: "start" }); }}>
            <span className="grow ellipsis">{p.title}</span>{p.defects > 0 && <span className="pill bad" title="Defects">{p.defects}</span>}<span className={`small ${p.done === p.n ? "ok" : "muted"}`} title="Answered">{p.done === p.n ? "✓" : `${p.done}/${p.n}`}</span></a>)}
        </nav>
        <div className="review-main">
          {parts.map(({ part, tree }) => (
            <AnswerSheet key={part} part={{ kind: part, tree, values: vals[part], ctx: ctxFor(part) }} filter={filter} edited={edited[part]} anchor={(p) => `${part}-p${p.id}`}
              onEdit={canEdit ? (page, section) => { cancel(); setEditing({ part, page, section }); } : undefined}
              editing={editing?.part === part ? { sectionId: editing.section.id, node: (
                <SectionEditor changed={mineKeys.length > 0} saving={saving} onSave={() => save()} onCancel={cancel}>
                  <FormRenderer kind={part} tree={tree} pages={onlySection(editing.page, editing.section)} values={vals[part]} ctx={ctxFor(part)} errors={errors} bookingId={booking.id} onChange={change(part)}
                    mediaEditor={(f, ids) => <OpsMediaEditor booking={booking} f={toMediaField(f, part, "")} ids={ids} onDone={onSaved} />} />
                </SectionEditor>) } : null} />
          ))}
          {filter !== "all" && rows.filter((r) => filter === "defects" ? defectOf(r.f, r.v) : filter === "edited" ? edited[r.part].has(r.f.key) : isEmpty(r.v)).length === 0 && <Empty>Nothing to show with this filter.</Empty>}
        </div>
      </div>
      {stale && <StaleDialog info={stale} mine={mineKeys} onRetry={() => save(stale.rowVersion)} onReload={() => { setDirty(NO_ANSWERS); setStale(null); setEditing(null); onSaved(); }} />}
    </>
  );
}

type MediaField = { key: string; label: string; type: string; part: Part; section: string; max: number; opsOk: boolean; accept: string };
const MAX_DEFAULT: Record<string, number> = { photo: 10, video: 3, file: 5, signature: 1 };
// what the file picker offers (the server checks the same: a file field's "allowed" setting)
const FILE_ACCEPT: Record<string, string> = { image: "image/jpeg,image/png", pdf: "application/pdf" };
const acceptFor = (f: { type: string; config: Record<string, unknown> }) => f.type === "video" ? "video/*" : f.type === "file"
  ? ((f.config.allowed as string[] | undefined) ?? ["image", "pdf"]).map((a) => FILE_ACCEPT[a]).join(",") : "image/*";

const toMediaField = (f: FormPage["sections"][number]["fields"][number], part: Part, section: string): MediaField => ({ key: f.key, label: f.label || f.key, type: f.type, part, section,
  max: f.type === "signature" ? 1 : Number(f.config.max_count ?? MAX_DEFAULT[f.type]), accept: acceptFor(f),
  opsOk: ["photo", "video", "file"].includes(f.type) && f.config.ops_upload !== false });

function mediaFields(trees: Trees): MediaField[] {
  const out: MediaField[] = [];
  for (const part of PART_ORDER) trees[part]?.pages.forEach((p) => p.sections.forEach((s) => s.fields.forEach((f) => {
    if (["photo", "video", "file", "signature"].includes(f.type)) out.push(toMediaField(f, part, s.title || p.title));
  })));
  return out;
}

/** A media field in the Inspection edit view: the files as plain thumbnails, then the same
 *  Replace / Add bar as the Media tab. With several files, click one to pick what Replace swaps. */
function OpsMediaEditor({ booking, f, ids, onDone }: { booking: Booking; f: MediaField; ids: string[]; onDone: () => void }) {
  const [sel, setSel] = useState<string | null>(null);
  const video = f.type === "video";
  const current = sel && ids.includes(sel) ? sel : ids[0];
  const pick = ids.length > 1;
  return (
    <div>
      {ids.length === 0 && <p className="muted small">No {video ? "videos" : "files"} yet.</p>}
      {ids.length > 0 && (
        <div className="photo-grid">
          {ids.map((id, i) => pick
            ? <button key={id} type="button" className={`tile-btn${id === current ? " on" : ""}`} data-testid="media-item" aria-pressed={id === current}
                aria-label={`${f.label} ${i + 1}`} onClick={() => setSel(id)}><Thumb id={id} video={video} /></button>
            : <Thumb key={id} id={id} video={video} />)}
        </div>)}
      <OpsFileActions booking={booking} f={f} count={ids.length} replaceId={current} onDone={onDone} onReplaced={setSel}
        hint={pick ? `Replace swaps the selected ${f.type}; click another to pick it.` : undefined} />
    </div>);
}

const opsMayEdit = (booking: Booking) => booking.stage === "submitted" || booking.stage === "completed";

/** Ops' add and replace for one field: saved straight away (upload, then attach), never a delete.
 *  The server checks the same rules: after submit, photos and videos, not blocked. */
function useOpsFiles(booking: Booking, f: MediaField, onDone: () => void, onReplaced?: (id: string) => void) {
  const { can } = useAuth();
  const { say, fail } = useToast();
  const [busy, setBusy] = useState(false);
  async function put(files: File[], replaces?: string) {
    if (!files.length) return;
    setBusy(true);
    try {
      for (const file of files) {
        const id = await addFile({ bookingId: booking.id, fieldKey: f.key, kind: f.type as "photo", file, name: file.name, source: "gallery", replaces });
        // only a fully sent file goes into the inspection (a half-sent one must not push out a good one)
        try { await uploaded(id); } catch (e) { void discardFile(id); throw e; }
        await api(`media/${id}/attach`, { body: replaces ? { replaces } : {} });
        if (replaces) onReplaced?.(id);
      }
      say(replaces ? "Replaced. The old file is kept in the history." : "Added. It is checked in the background.");
    } catch (e) { fail(e); } finally { setBusy(false); onDone(); }
  }
  return { allowed: can("media.manage") && opsMayEdit(booking) && f.opsOk, busy, put,
    accept: f.accept, noun: f.type === "photo" ? "photo" : f.type };
}

/** A button that opens the file picker (a label around a hidden file input). */
function FilePick({ className, busy, disabled, accept, multiple, label, title, onPick, children }: { className: string; busy: boolean; disabled?: boolean; accept: string; multiple?: boolean; label: string; title?: string; onPick: (files: File[]) => void; children: React.ReactNode }) {
  const off = busy || disabled;
  return (
    <label className={`${className}${off ? " disabled" : ""}`} title={title} aria-disabled={off || undefined}>
      {children}
      <input type="file" hidden disabled={off} accept={accept} multiple={multiple} aria-label={label}
        onChange={(e) => { const files = Array.from(e.target.files ?? []); e.target.value = ""; onPick(files); }} />
    </label>);
}

/** Replace and Add under the Media preview (or Add alone on an empty field). Add stays visible
 *  but greyed out when the field is full, so people see why they can only replace. */
function OpsFileActions({ booking, f, count, replaceId, onDone, onReplaced, hint }: { booking: Booking; f: MediaField; count: number; replaceId?: string; onDone: () => void; onReplaced?: (id: string) => void; hint?: string }) {
  const ops = useOpsFiles(booking, f, onDone, onReplaced);
  if (!ops.allowed) return null;
  const room = f.max - count;
  const add = (
    <FilePick className="btn sm" busy={ops.busy} disabled={room <= 0} accept={ops.accept} multiple={room > 1} label={`Add to ${f.label}`}
      title={room <= 0 ? `Full (${count} of ${f.max}). Replace a ${ops.noun} instead.` : undefined} onPick={(fs) => void ops.put(fs.slice(0, room))}>
      <Plus size={14} aria-hidden /> Add {ops.noun}</FilePick>);
  if (!replaceId) return add;
  return (
    <div className="ops-file-actions">
      <div className="ops-file-btns">
        <FilePick className="btn sm primary" busy={ops.busy} accept={ops.accept} label={`Replace this ${ops.noun}`} onPick={(fs) => void ops.put(fs.slice(0, 1), replaceId)}>
          <RefreshCw size={14} aria-hidden /> Replace</FilePick>
        {add}
      </div>
      <p className="muted small">{ops.busy ? "Uploading…" : `${count} of ${f.max} in this field${room <= 0 ? " (full)" : ""}. Saves straight away.${hint ? ` ${hint}` : ""}`}</p>
    </div>);
}

const idsOf = (insp: Inspection, part: Part, key: string): string[] => { const v = (insp.answers[part] ?? {})[key]; return Array.isArray(v) ? (v as string[]) : v ? [String(v)] : []; };

const TYPE_GROUPS = [["photo", "Photos"], ["video", "Videos"], ["file", "Documents"], ["signature", "Signatures"]] as const;

function MediaTab({ booking, insp, trees, onChanged }: { booking: Booking; insp?: Inspection; trees: Trees; onChanged: () => void }) {
  const { can } = useAuth();
  const { fail, say } = useToast();
  const [zip, setZip] = useState<string>("");
  const [view, setView] = useState<"section" | "type">(() => { try { return localStorage.getItem("vayu:media-view") === "type" ? "type" : "section"; } catch { return "section"; } });
  const pickView = (v: "section" | "type") => { setView(v); try { localStorage.setItem("vayu:media-view", v); } catch { /* private window: not remembered */ } };
  const [showEmpty, setShowEmpty] = useState(false);
  const [sel, setSel] = useState<string | null>(null);
  const fields = useMemo(() => mediaFields(trees), [trees]);
  const onServer = useQuery({ queryKey: ["booking-media", booking.id], enabled: can("media.manage"),
    queryFn: () => api<{ id: string; by_ops: boolean }[]>(`bookings/${booking.id}/media`) });
  const byOps = new Set((onServer.data ?? []).filter((m) => m.by_ops).map((m) => m.id));
  // Ops add or replace photos and videos once the expert has submitted; nobody deletes
  if (!insp) return <Empty title="No inspection yet">Photos and videos show here once the expert starts uploading.</Empty>;
  const all = fields.flatMap((f) => idsOf(insp, f.part, f.key).map((id) => ({ id, f })));
  const empty = fields.filter((f) => idsOf(insp, f.part, f.key).length === 0);
  // by section (form order) or by type (photos, videos, documents, signatures)
  const groups = (view === "type"
    ? TYPE_GROUPS.map(([type, title]) => ({ title, items: all.filter((x) => x.f.type === type) }))
    : [...new Set(fields.map((f) => f.section))].map((title) => ({ title, items: all.filter((x) => x.f.section === title) })))
    .filter((g) => g.items.length > 0);
  const items = groups.flatMap((g) => g.items);          // ‹ › follow what is on screen
  const current = items.find((x) => x.id === sel) ?? items[0];
  const at = current ? items.indexOf(current) : -1;
  const refreshed = () => { void onServer.refetch(); onChanged(); };
  async function makeZip(k: "image" | "video") {
    try { const r = await api<{ url: string }>(`bookings/${booking.id}/media-zip`, { body: { kind: k } }); setZip(`/zip/${r.url.split("/zips/")[1]}`); } catch (e) { fail(e); }
  }
  return (
    <>
      <div className="bar">
        <div className="seg" role="group" aria-label="Group files">
          {([["section", "By section"], ["type", "By type"]] as const).map(([k, l]) => <button key={k} aria-pressed={view === k} onClick={() => pickView(k)}>{l}</button>)}
        </div>
        <span className="muted small">{all.length} {all.length === 1 ? "file" : "files"}</span>
        <label className="check small"><input type="checkbox" checked={showEmpty} onChange={(e) => setShowEmpty(e.target.checked)} /> Show empty fields ({empty.length})</label>
        <span className="grow" />
        {can("media.download") && <MoreMenu label="Download" items={[{ label: "All images (ZIP)", onClick: () => void makeZip("image") }, { label: "All videos (ZIP)", onClick: () => void makeZip("video") }]}><Download size={16} aria-hidden /> ZIP</MoreMenu>}
        {zip && <a href={zip} target="_blank" rel="noreferrer">Open the ZIP page</a>}
      </div>
      {items.length === 0 && !showEmpty && <Empty title="No photos or videos yet">{fields.length ? "Files show here as the expert uploads them." : "This form has no photo or video fields."}</Empty>}
      <div className="gallery-wrap">
        <div className="gallery">
          {groups.map((g) => (
            <section key={g.title} aria-label={g.title}>
              <h3 className="gallery-h">{g.title} <span className="muted small">{g.items.length}</span></h3>
              <div className="tile-grid">
                {g.items.map((x) => {
                  const sev = defectFor(insp, trees, x.f);
                  return (
                    <button key={x.id} className={`tile-btn${current?.id === x.id ? " on" : ""}`} data-testid="gallery-item" onClick={() => setSel(x.id)} aria-label={`${x.f.label}${sev ? `, ${sev}` : ""}`}>
                      <Thumb id={x.id} video={x.f.type === "video"} />
                      {sev && <span className="pill bad tile-tag">{sev}</span>}
                      {byOps.has(x.id) && <span className="pill tile-tag ops-tag">Added by Ops</span>}
                      <span className="tile-label ellipsis" title={`${x.f.section} › ${x.f.label}`}>{view === "type" ? `${x.f.section} › ${x.f.label}` : x.f.label}</span>
                    </button>);
                })}
              </div>
            </section>))}
          {showEmpty && empty.length > 0 && (
            <section aria-label="Empty fields">
              <h3 className="gallery-h">Empty fields <span className="muted small">{empty.length}</span></h3>
              <div className="empty-list">{empty.map((f) => <div key={`${f.part}.${f.key}`} className="empty-row"><span className="grow">{f.section} › {f.label}</span>
                <OpsFileActions booking={booking} f={f} count={0} onDone={refreshed} /></div>)}</div>
            </section>)}
        </div>
        {current && (
          <aside className="card preview-pane" aria-label="Selected file">
            <PreviewMedia id={current.id} video={current.f.type === "video"} />
            <div className="bar" style={{ margin: "8px 0" }}>
              <button className="sm" aria-label="Previous file" disabled={at <= 0} onClick={() => setSel(items[at - 1]!.id)}>‹</button>
              <span className="muted small grow" style={{ textAlign: "center" }}>{at + 1} of {items.length}</span>
              <button className="sm" aria-label="Next file" disabled={at >= items.length - 1} onClick={() => setSel(items[at + 1]!.id)}>›</button>
            </div>
            <div style={{ fontWeight: 600 }}>{current.f.label}</div>
            <div className="muted small">{current.f.section}</div>
            <AnswerNear insp={insp} trees={trees} f={current.f} />
            {byOps.has(current.id) && <p className="muted small" style={{ margin: "6px 0 0" }}>Added by Ops</p>}
            <OpsFileActions booking={booking} f={current.f} count={idsOf(insp, current.f.part, current.f.key).length} replaceId={current.id} onDone={refreshed} onReplaced={setSel} />
          </aside>)}
      </div>
    </>
  );
}

/** The choice question in the same section a photo belongs to (what it shows: OK, dented...). */
function nearestChoice(trees: Trees, f: MediaField) {
  const tree = trees[f.part];
  const sec = tree?.pages.flatMap((p) => p.sections).find((s) => s.fields.some((x) => x.key === f.key));
  const fields = sec?.fields ?? [];
  const i = fields.findIndex((x) => x.key === f.key);
  return [...fields.slice(0, i)].reverse().find((x) => x.type === "single_choice" || x.type === "multi_choice");
}
function defectFor(insp: Inspection, trees: Trees, f: MediaField): string | null {
  const q = nearestChoice(trees, f);
  return q ? defectOf(q, (insp.answers[f.part] ?? {})[q.key]) : null;
}
function AnswerNear({ insp, trees, f }: { insp: Inspection; trees: Trees; f: MediaField }) {
  const q = nearestChoice(trees, f);
  if (!q) return null;
  const v = (insp.answers[f.part] ?? {})[q.key];
  const sev = defectOf(q, v);
  return <p className="small" style={{ margin: "6px 0 0" }}>{q.label}: <strong className={sev ? "bad-text" : ""}><AnswerValue f={q} v={v} /></strong>{sev && <> <span className="pill bad">{sev}</span></>}</p>;
}

function PreviewMedia({ id, video }: { id: string; video: boolean }) {
  const links = useMediaUrl(id);
  if (!links) return <div className="preview-media empty" aria-label="Not ready yet" />;
  if (isPdf(links)) return <a className="preview-media doc" href={links.url} target="_blank" rel="noreferrer"><FileText size={40} aria-hidden /><span>Open the PDF</span></a>;
  return video ? <video className="preview-media" src={links.url} controls preload="metadata" />
    : <a href={links.url} target="_blank" rel="noreferrer"><img className="preview-media" src={links.preview_url ?? links.url} alt="" /></a>;
}

const WORDS = ["excellent", "good", "average", "bad"];

/** 1 to 5 (or words) as one row of buttons; the suggestion is marked; Auto clears an override. */
function Seg<T extends string | number>({ label, value, suggested, options, onPick, disabled }: { label: string; value: T | null; suggested?: T; options: { v: T; label: string }[]; onPick: (v: T | null) => void; disabled: boolean }) {
  return (
    <div className="seg" role="radiogroup" aria-label={label}>
      <button role="radio" aria-checked={value === null} disabled={disabled} onClick={() => onPick(null)}>Auto</button>
      {options.map((o) => <button key={String(o.v)} role="radio" aria-checked={value === o.v} disabled={disabled} onClick={() => onPick(o.v)} title={o.v === suggested ? "Suggested" : undefined}>{o.label}{o.v === suggested ? <span className="sugg" aria-label="suggested">•</span> : null}</button>)}
    </div>
  );
}

function RatingsTab({ insp, trees, onSaved }: { insp?: Inspection; trees: Trees; onSaved: () => void }) {
  const { can } = useAuth();
  const { say, fail } = useToast();
  if (!insp) return <Empty title="No inspection yet">Ratings are calculated from the defects once the expert submits.</Empty>;
  const s = insp.scores;
  const cats = trees.inspection?.rating_config?.categories ?? [];
  const checks = (trees.inspection?.pages ?? []).flatMap((p) => p.sections.flatMap((sec) => sec.fields.filter((f) => f.type === "derived")));
  async function send(body: Record<string, unknown>) {
    try { await api(`inspections/${insp!.id}/overrides`, { method: "PATCH", body: { row_version: insp!.row_version, ...body } }); say("Saved."); onSaved(); } catch (e) { fail(e); }
  }
  const edit = can("ratings.override");
  const nums = [1, 2, 3, 4, 5].map((n) => ({ v: n, label: String(n) }));
  const derivedOverride = (k: string) => (insp.overrides?.derived as Record<string, boolean> | undefined)?.[k];
  return (
    <div className="stack">
      <section className="card">
        <div className="sheet-head"><h3>Overall</h3><span className="pill">{s?.overall?.word ?? "—"}</span><span className="muted small">average {s?.overall?.average ?? "—"} · suggested {s?.overall?.suggested_word ?? "—"}</span>{s?.overall?.overridden && <Pill tone="warn">Overridden</Pill>}</div>
        <Seg label="Overall word" value={s?.overall?.overridden ? s.overall.word : null} suggested={s?.overall?.suggested_word} options={WORDS.map((w) => ({ v: w, label: w[0]!.toUpperCase() + w.slice(1) }))} disabled={!edit} onPick={(v) => send({ overall: v })} />
      </section>
      <section className="card">
        <h3 style={{ marginTop: 0 }}>Ratings</h3>
        <div className="rating-rows">
          {cats.map((c) => {
            const r = s?.ratings?.[c.key];
            return (
              <div key={c.key} className="rating-row">
                <div className="grow"><strong>{c.label}</strong> <span className="muted small">Suggested {r?.suggested ?? "—"}</span> {r?.overridden && <Pill tone="warn">Overridden</Pill>}</div>
                <Seg label={`${c.label} rating`} value={r?.overridden ? r.value : null} suggested={r?.suggested} options={nums} disabled={!edit} onPick={(v) => send({ ratings: { [c.key]: v } })} />
              </div>);
          })}
          {cats.length === 0 && <p className="muted">This form has no rating categories.</p>}
        </div>
      </section>
      {checks.length > 0 && <section className="card">
        <h3 style={{ marginTop: 0 }}>Key Checks</h3>
        <div className="rating-rows">
          {checks.map((f) => {
            const yes = String(f.config.true_label ?? "Yes"), no = String(f.config.false_label ?? "No");
            const o = derivedOverride(f.key);
            return (
              <div key={f.key} className="rating-row">
                <div className="grow"><strong>{f.label}</strong> <span className="muted small">Now: {s?.derived?.[f.key] === true ? yes : no}</span></div>
                <Seg label={`${f.label} override`} value={o === undefined ? null : o ? "true" : "false"} options={[{ v: "true", label: yes }, { v: "false", label: no }]} disabled={!edit}
                  onPick={(v) => send({ derived: { [f.key]: v === null ? null : v === "true" } })} />
              </div>);
          })}
        </div>
      </section>}
    </div>
  );
}

type ReportInfo = { verify_url?: string; revision: number; status: string; stale: boolean; generated_at: string | null; filename: string; error: string; url: string | null; preview_url?: string | null };

function ReportTab({ booking }: { booking: Booking }) {
  const { can } = useAuth();
  const { say, fail } = useToast();
  const refresh = useRefresh();
  const q = useQuery({ queryKey: ["report", booking.id], retry: false, queryFn: async () => { try { return await api<ReportInfo>(`bookings/${booking.id}/report`); } catch (e) { if (e instanceof ApiError && e.status === 404) return null; throw e; } } });
  const regen = useMutation({ mutationFn: () => api(`bookings/${booking.id}/report/regenerate`, { body: {} }), onSuccess: () => { say("Regenerating. This takes a few seconds."); setTimeout(() => void refresh("report"), 4000); }, onError: fail });
  const r = q.data;
  return (
    <>
      <div className="bar">
        {r && <><Pill tone={r.status === "ready" ? "ok" : r.status === "failed" ? "bad" : "warn"}>{r.status === "ready" ? "Ready" : r.status}</Pill><span className="muted small">Revision {r.revision} · {fmtStamp(r.generated_at)}</span></>}
        <span className="grow" />
        {r?.verify_url && <button onClick={() => { void navigator.clipboard?.writeText(r.verify_url!); say("Check link copied."); }}>Copy check link</button>}
        {can("reports.regenerate") && booking.stage === "completed" && <button onClick={() => regen.mutate()}>Regenerate PDF</button>}
        {r?.url && <a className="btn primary" href={r.url} download={r.filename}><Download size={15} aria-hidden /> Download PDF</a>}
      </div>
      {r?.stale && <div className="banner warn">Out of date: answers changed after this PDF was made. Regenerate it to include them.</div>}
      {r?.error && <div className="banner bad">Problem: {r.error}</div>}
      {!r && <Empty title="No report yet">It is made automatically when the booking is Completed.</Empty>}
      {r?.preview_url && <iframe className="pdf-frame" title="Report preview" src={r.preview_url} />}
    </>
  );
}

export function Actions({ kind, booking, experts, onClose, onDone, fail }: { kind: "assign" | "reschedule" | "cancel" | "release" | "type"; booking: Booking; experts: User[]; onClose: () => void; onDone: () => void; fail: (e: unknown) => void }) {
  const [expert, setExpert] = useState(String(booking.assigned_expert ?? ""));
  const [date, setDate] = useState(String(booking.answers.inspection_date ?? ""));
  const [time, setTime] = useState(String(booking.answers.inspection_time ?? ""));
  const [reason, setReason] = useState("");
  const [type, setType] = useState(booking.inspection_type);
  const reasons = useQuery({ queryKey: ["list-items", kind === "cancel" ? "cancel_reason" : "reschedule_reason"], enabled: kind === "cancel" || kind === "reschedule", queryFn: async () => asList<MasterListItem>(await api(`master-lists/${kind === "cancel" ? "cancel_reason" : "reschedule_reason"}/items`)) });
  const types = useInspectionTypes();
  const typeLabel = useTypeLabels();
  const go = async (path: string, body: unknown) => { try { await api(`bookings/${booking.id}/${path}`, { body }); onDone(); } catch (e) { fail(e); } };
  if (kind === "release") return <Confirm title="Force release this job?" danger confirmLabel="Force release" onCancel={onClose} onConfirm={() => go("force-release", {})}><p>The expert is taken off the job. If they still have a draft on their phone and submit it later, Ops will see a conflict to resolve.</p></Confirm>;
  const title = { assign: "Assign an expert", reschedule: "Reschedule", cancel: "Cancel this booking", type: "Change inspection type" }[kind];
  const ok = kind === "assign" ? !!expert : kind === "reschedule" ? !!date && !!time && !!reason : kind === "cancel" ? !!reason : !!type && type !== booking.inspection_type;
  const submit = () => kind === "assign" ? go("assign", { expert: Number(expert) }) : kind === "reschedule" ? go("reschedule", { date, time, reason }) : kind === "cancel" ? go("cancel", { reason }) : go("change-type", { inspection_type: type });
  return (
    <Modal title={title} onClose={onClose} actions={<><button onClick={onClose}>Back</button><button className={kind === "cancel" ? "danger" : "primary"} disabled={!ok} onClick={submit}>{title}</button></>}>
      {kind === "assign" && <Field label="Expert"><select aria-label="Expert" value={expert} onChange={(e) => setExpert(e.target.value)}><option value="">Choose…</option>{experts.filter((u) => u.is_active).map((u) => <option key={u.id} value={u.id}>{u.name || u.username}</option>)}</select></Field>}
      {kind === "reschedule" && <><Field label="New date"><input aria-label="New date" type="date" value={date} onChange={(e) => setDate(e.target.value)} /></Field><Field label="New time"><input aria-label="New time" type="time" value={time} onChange={(e) => setTime(e.target.value)} /></Field></>}
      {(kind === "reschedule" || kind === "cancel") && <Field label="Reason"><select aria-label="Reason" value={reason} onChange={(e) => setReason(e.target.value)}><option value="">Choose…</option>{(reasons.data ?? []).filter((r) => !r.archived).map((r) => <option key={r.key} value={r.key}>{r.label}</option>)}</select></Field>}
      {kind === "type" && <Field label="Inspection type"><select aria-label="Inspection type" value={type} onChange={(e) => setType(e.target.value)}>{types.filter((t) => t.available).map((t) => <option key={t.key} value={t.key}>{typeLabel(t.key)}</option>)}</select></Field>}
    </Modal>
  );
}
