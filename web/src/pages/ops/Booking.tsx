import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import { api, ApiError, explain } from "../../api/client";
import { asList, useList, useRefresh } from "../../api/hooks";
import { STAGE_LABEL, STAGE_TONE, useInspectionTypes, useLabels, useTypeLabels } from "../../api/labels";
import type { Booking, Inspection, MasterListItem, User } from "../../api/types";
import { useAuth } from "../../auth";
import { saveDirty } from "../../lib/saveDirty";
import { usePinnedTrees, useTrees } from "../../lib/useTrees";
import { addFile } from "../../lib/uploadManager";
import { FormRenderer } from "../../ui/FormRenderer";
import { Confirm, Field, Modal, Pill, Tabs, useToast, when } from "../../ui/kit";
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
    <div style={{ maxWidth: 720 }}>
      <h1>New booking</h1>
      <FormRenderer kind="booking" tree={tree} values={values} errors={errors} readOnlyKeys={["assigned_expert"]} onChange={(k, v) => { setValues({ ...values, [k]: v }); setErrors({ ...errors, [k]: "" }); }} />
      <button className="primary" disabled={create.isPending} onClick={() => create.mutate()}>Create booking</button>
    </div>
  );
}

type Tab = "booking" | "inspection" | "media" | "ratings" | "report" | "history";

function Detail({ id }: { id: string }) {
  const { can } = useAuth();
  const { say, fail } = useToast();
  const refresh = useRefresh();
  const b = useQuery({ queryKey: ["booking", id], queryFn: () => api<Booking>(`bookings/${id}`) });
  useCrumb(b.data?.booking_id);
  const insps = useQuery({ queryKey: ["inspections", id], queryFn: async () => asList<Inspection>(await api(`bookings/${id}/inspections`)) });
  const [tab, setTab] = useState<Tab>("booking");
  const [action, setAction] = useState<null | "assign" | "reschedule" | "cancel" | "release" | "type">(null);
  const booking = b.data;
  const experts = useList<User>("experts", "users", { role: "expert" });
  const trees = useTrees(booking?.inspection_type);
  const reload = () => Promise.all([refresh("booking"), refresh("inspections"), refresh("board"), refresh("report")]);
  const insp = (insps.data ?? []).filter((i) => i.status === "submitted").sort((a, c) => (c.submitted_at ?? "").localeCompare(a.submitted_at ?? ""))[0] ?? (insps.data ?? [])[0];
  const pinned = usePinnedTrees(insp);                   // the exact versions this inspection was started on
  if (!booking) return <p className="muted pad">Loading…</p>;
  const expert = experts.data?.find((u) => u.id === booking.assigned_expert);
  const open = booking.stage === "draft" || booking.stage === "assigned";
  return (
    <>
      <div className="bar">
        <h1 className="grow">{booking.booking_id} <span className="muted small">{String(booking.answers.customer_name ?? "")}</span></h1>
        <Pill tone={STAGE_TONE[booking.stage]}>{STAGE_LABEL[booking.stage] ?? booking.stage}</Pill>
        {booking.conflict && <Pill tone="bad">Conflict: two experts</Pill>}
        {expert && <span className="muted">Expert: {expert.name || expert.username}</span>}
      </div>
      <div className="bar">
        {can("bookings.assign") && booking.stage !== "cancelled" && <button onClick={() => setAction("assign")}>{booking.assigned_expert ? "Reassign" : "Assign"}</button>}
        {can("bookings.reschedule") && booking.stage !== "cancelled" && booking.stage !== "completed" && <button onClick={() => setAction("reschedule")}>Reschedule</button>}
        {can("bookings.edit") && open && <button onClick={() => setAction("type")}>Change type</button>}
        {can("bookings.force_release") && booking.stage === "in_progress" && <button onClick={() => setAction("release")}>Force release</button>}
        {can("bookings.cancel") && booking.stage !== "cancelled" && booking.stage !== "completed" && <button className="danger" onClick={() => setAction("cancel")}>Cancel booking</button>}
      </div>
      {booking.alerts?.map((a, i) => <p key={i} className="error" role="alert">⚠ {a.detail} <span className="muted small">{when(a.at)}</span></p>)}
      <Tabs value={tab} onChange={setTab} tabs={[{ id: "booking", label: "Booking" }, { id: "inspection", label: "Inspection" }, { id: "media", label: "Media" }, { id: "ratings", label: "Ratings" }, { id: "report", label: "Report" }, { id: "history", label: "History" }]} />
      {tab === "booking" && trees.booking && <BookingTab booking={booking} tree={trees.booking} onSaved={reload} />}
      {tab === "inspection" && <InspectionTab booking={booking} insp={insp} trees={pinned} onSaved={reload} />}
      {tab === "media" && <MediaTab booking={booking} insp={insp} trees={pinned} onChanged={reload} />}
      {tab === "ratings" && <RatingsTab insp={insp} trees={pinned} onSaved={reload} />}
      {tab === "report" && <ReportTab booking={booking} />}
      {tab === "history" && <HistoryTab booking={booking} insps={insps.data ?? []} experts={experts.data ?? []} onResolved={reload} />}
      {action && <Actions kind={action} booking={booking} experts={experts.data ?? []} onClose={() => setAction(null)} onDone={() => { setAction(null); say("Done."); void reload(); }} fail={fail} />}
    </>
  );
}

function BookingTab({ booking, tree, onSaved }: { booking: Booking; tree: NonNullable<ReturnType<typeof useTrees>["booking"]>; onSaved: () => void }) {
  const { can } = useAuth();
  const { say, fail } = useToast();
  const [values, setValues] = useState<Answers>(booking.answers);
  const [dirty, setDirty] = useState<Answers>({});
  const [stale, setStale] = useState<Stale | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  useEffect(() => { setValues({ ...booking.answers, ...dirty }); }, [booking.row_version]); // eslint-disable-line react-hooks/exhaustive-deps
  const change = (k: string, v: unknown) => { setValues({ ...values, [k]: v }); setDirty({ ...dirty, [k]: v }); setErrors({ ...errors, [k]: "" }); };
  async function save(rowVersion = booking.row_version) {
    try {
      const r = await saveDirty((rv, ch) => api(`bookings/${booking.id}`, { method: "PATCH", body: { row_version: rv, answers: ch } }), rowVersion, dirty);
      if (!r.ok) return setStale(r.stale);
      setDirty({}); setStale(null); say("Saved."); onSaved();
    } catch (e) {
      if (e instanceof ApiError && e.body.errors) setErrors(e.body.errors as Record<string, string>);
      else if (e instanceof ApiError && e.code === "FIELD_ACCESS") setErrors(Object.fromEntries(((e.body.keys as string[]) ?? []).map((k) => [k, "You cannot change this now."])));
      else if (e instanceof ApiError && e.code === "DUPLICATE_BOOKING_ID") setErrors({ booking_id: explain(e) });
      else fail(e);
    }
  }
  return (
    <div style={{ maxWidth: 720 }}>
      <FormRenderer kind="booking" tree={tree} values={values} errors={errors} readOnly={!can("bookings.edit")} readOnlyKeys={["assigned_expert", "inspection_type"]} onChange={change} />
      {can("bookings.edit") && <button className="primary" disabled={Object.keys(dirty).length === 0} onClick={() => save()}>Save changes</button>}
      {stale && <StaleDialog info={stale} mine={Object.keys(dirty)} onRetry={() => save(stale.rowVersion)} onReload={() => { setDirty({}); setStale(null); onSaved(); }} />}
    </div>
  );
}

type Trees = ReturnType<typeof usePinnedTrees>;
type Part = "inspection" | "start" | "end";
type Parts = Record<Part, Answers>;
const NO_ANSWERS: Parts = { inspection: {}, start: {}, end: {} };

function InspectionTab({ booking, insp, trees, onSaved }: { booking: Booking; insp?: Inspection; trees: Trees; onSaved: () => void }) {
  const { can } = useAuth();
  const { say, fail } = useToast();
  const [vals, setVals] = useState<Parts>(NO_ANSWERS);
  const [dirty, setDirty] = useState<Parts>(NO_ANSWERS);
  const [stale, setStale] = useState<Stale | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const rv = insp?.row_version;
  useEffect(() => { if (insp) setVals({ inspection: { ...(insp.answers.inspection ?? {}), ...dirty.inspection }, start: { ...(insp.answers.start ?? {}), ...dirty.start }, end: { ...(insp.answers.end ?? {}), ...dirty.end } }); }, [insp?.id, rv]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!insp) return <p className="muted">No inspection has been submitted yet.</p>;
  const mineKeys = [...Object.keys(dirty.inspection), ...Object.keys(dirty.start), ...Object.keys(dirty.end)];
  const change = (part: Part) => (k: string, v: unknown) => { setVals({ ...vals, [part]: { ...vals[part], [k]: v } }); setDirty({ ...dirty, [part]: { ...dirty[part], [k]: v } }); };
  async function save(rowVersion = insp!.row_version) {
    try {
      const r = await saveDirty((v, ch) => api(`inspections/${insp!.id}`, { method: "PATCH", body: { row_version: v, answers: ch } }), rowVersion, dirty);
      if (!r.ok) return setStale(r.stale);
      setDirty(NO_ANSWERS); setStale(null); say("Saved. Ratings and Key Checks were recalculated."); onSaved();
    } catch (e) {
      if (e instanceof ApiError && e.body.errors) setErrors(e.body.errors as Record<string, string>);
      else if (e instanceof ApiError && e.code === "FIELD_ACCESS") setErrors(Object.fromEntries(((e.body.keys as string[]) ?? []).map((k) => [k, "You cannot change this now."])));
      else fail(e);
    }
  }
  const canEdit = can("submissions.edit");
  return (
    <div style={{ maxWidth: 760 }}>
      {insp.last_edited_by && <p className="muted small">Last edited by {insp.last_edited_by} {when(insp.last_edited_at)}</p>}
      {trees.start && <><h2>Check-in</h2><FormRenderer kind="start" tree={trees.start} values={vals.start} ctx={{ booking: booking.answers, inspection: vals.inspection, end: vals.end }} errors={errors} readOnly={!canEdit} bookingId={booking.id} onChange={change("start")} /></>}
      {trees.inspection && <FormRenderer kind="inspection" tree={trees.inspection} values={vals.inspection} ctx={{ booking: booking.answers, start: vals.start, end: vals.end }} errors={errors} readOnly={!canEdit} bookingId={booking.id} onChange={change("inspection")} />}
      {trees.end && <><h2>Wrap-up</h2><FormRenderer kind="end" tree={trees.end} values={vals.end} ctx={{ booking: booking.answers, inspection: vals.inspection, start: vals.start }} errors={errors} readOnly={!canEdit} bookingId={booking.id} onChange={change("end")} /></>}
      {canEdit && <button className="primary" disabled={mineKeys.length === 0} onClick={() => save()}>Save changes</button>}
      {stale && <StaleDialog info={stale} mine={mineKeys} onRetry={() => save(stale.rowVersion)} onReload={() => { setDirty(NO_ANSWERS); setStale(null); onSaved(); }} />}
    </div>
  );
}

function mediaFields(trees: Trees): { key: string; label: string; type: string; part: Part }[] {
  const out: { key: string; label: string; type: string; part: Part }[] = [];
  for (const [part, tree] of [["start", trees.start], ["inspection", trees.inspection], ["end", trees.end]] as const)
    tree?.pages.forEach((p) => p.sections.forEach((s) => s.fields.forEach((f) => { if (["photo", "video", "file", "signature"].includes(f.type)) out.push({ key: f.key, label: f.label || f.key, type: f.type, part }); })));
  return out;
}

const mediaUrl = (id: string) => api<{ url: string; preview_url: string | null }>(`media/${id}/url`).catch(() => null);

function MediaTab({ booking, insp, trees, onChanged }: { booking: Booking; insp?: Inspection; trees: Trees; onChanged: () => void }) {
  const { can } = useAuth();
  const { fail, say } = useToast();
  const [zip, setZip] = useState<string>("");
  const [confirm, setConfirm] = useState<null | { id: string }>(null);
  const fields = useMemo(() => mediaFields(trees), [trees]);
  if (!insp) return <p className="muted">No inspection yet.</p>;
  const ids = (part: Part, key: string): string[] => { const v = (insp.answers[part] ?? {})[key]; return Array.isArray(v) ? (v as string[]) : v ? [String(v)] : []; };
  async function add(f: (typeof fields)[number], files: FileList | null) {
    if (!files || !insp) return;
    try {
      let list = ids(f.part, f.key);
      for (const file of Array.from(files)) { const id = await addFile({ bookingId: booking.id, fieldKey: f.key, kind: f.type as "photo", file, name: file.name, source: "gallery" }); list = f.type === "signature" ? [id] : [...list, id]; }
      await api(`inspections/${insp.id}`, { method: "PATCH", body: { row_version: insp.row_version, answers: { [f.part]: { [f.key]: f.type === "signature" ? list[0] : list } } } });
      say("Added. It is checked in the background."); onChanged();
    } catch (e) { fail(e); }
  }
  async function remove(id: string) {
    try { await api(`media/${id}`, { method: "DELETE" }); setConfirm(null); say("Deleted."); onChanged(); } catch (e) { setConfirm(null); fail(e); }
  }
  async function makeZip(kind: "image" | "video") {
    try { const r = await api<{ url: string }>(`bookings/${booking.id}/media-zip`, { body: { kind } }); setZip(`/zip/${r.url.split("/zips/")[1]}`); } catch (e) { fail(e); }
  }
  return (
    <>
      {can("media.download") && <div className="bar"><button onClick={() => makeZip("image")}>Download all images (ZIP)</button><button onClick={() => makeZip("video")}>Download all videos (ZIP)</button>
        {zip && <a href={zip} target="_blank" rel="noreferrer">Open the ZIP page</a>}</div>}
      {fields.map((f) => (
        <div className="card" key={`${f.part}.${f.key}`}>
          <h3 style={{ marginTop: 0 }}>{f.label}</h3>
          <div className="photo-grid">
            {ids(f.part, f.key).map((id) => (
              <div key={id} data-testid="gallery-item"><Thumb id={id} video={f.type === "video"} />
                {can("media.manage") && <button className="link" onClick={() => setConfirm({ id })}>Delete</button>}</div>))}
          </div>
          {ids(f.part, f.key).length === 0 && <p className="muted small">Nothing here.</p>}
          {can("media.manage") && <label className="btn" style={{ display: "inline-block", marginTop: 8 }}>Add {f.type}<input type="file" hidden accept={f.type === "video" ? "video/*" : "image/*,application/pdf"} multiple={f.type !== "signature"} aria-label={`Add to ${f.label}`} onChange={(e) => { void add(f, e.target.files); e.target.value = ""; }} /></label>}
        </div>))}
      {fields.length === 0 && <p className="muted">This form has no photo or video fields.</p>}
      {confirm && <Confirm title="Delete this file?" danger confirmLabel="Delete" onCancel={() => setConfirm(null)} onConfirm={() => remove(confirm.id)}><p>It is removed from the booking and from every ZIP. This cannot be undone.</p></Confirm>}
    </>
  );
}

function Thumb({ id, video }: { id: string; video: boolean }) {
  const q = useQuery({ queryKey: ["media-url", id], staleTime: 600_000, queryFn: () => mediaUrl(id) });
  if (!q.data) return <div style={{ aspectRatio: "4/3", background: "#eee", borderRadius: 8 }} aria-label="Not ready yet" />;
  return video ? <video src={q.data.url} controls preload="metadata" /> : <a href={q.data.url} target="_blank" rel="noreferrer"><img src={q.data.preview_url ?? q.data.url} alt="" /></a>;
}

const WORDS = ["excellent", "good", "average", "bad"];

function RatingsTab({ insp, trees, onSaved }: { insp?: Inspection; trees: Trees; onSaved: () => void }) {
  const { can } = useAuth();
  const { say, fail } = useToast();
  if (!insp) return <p className="muted">No inspection yet.</p>;
  const s = insp.scores;
  const cats = trees.inspection?.rating_config?.categories ?? [];
  const checks = (trees.inspection?.pages ?? []).flatMap((p) => p.sections.flatMap((sec) => sec.fields.filter((f) => f.type === "derived")));
  async function send(body: Record<string, unknown>) {
    try { await api(`inspections/${insp!.id}/overrides`, { method: "PATCH", body: { row_version: insp!.row_version, ...body } }); say("Saved."); onSaved(); } catch (e) { fail(e); }
  }
  const edit = can("ratings.override");
  return (
    <div style={{ maxWidth: 720 }}>
      <h2 style={{ marginTop: 0 }}>Ratings</h2>
      <table><thead><tr><th>Category</th><th>Suggested</th><th>Rating</th></tr></thead>
        <tbody>{cats.map((c) => {
          const r = s?.ratings?.[c.key];
          return <tr key={c.key}><td>{c.label}</td><td>{r?.suggested ?? "—"}</td>
            <td>{edit ? <select aria-label={`${c.label} rating`} value={r?.overridden ? r.value : ""} onChange={(e) => send({ ratings: { [c.key]: e.target.value ? Number(e.target.value) : null } })}>
              <option value="">Use suggestion ({r?.suggested ?? "—"})</option>{[1, 2, 3, 4, 5].map((n) => <option key={n} value={n}>{n}</option>)}</select> : r?.value}
              {r?.overridden && <> <Pill tone="warn">Overridden</Pill></>}</td></tr>;
        })}</tbody></table>
      <h3>Overall</h3>
      <p><strong>{s?.overall?.word ?? "—"}</strong> <span className="muted small">(suggested {s?.overall?.suggested_word ?? "—"}, average {s?.overall?.average ?? "—"})</span> {s?.overall?.overridden && <Pill tone="warn">Overridden</Pill>}</p>
      {edit && <Field label="Overall word"><select aria-label="Overall word" value={s?.overall?.overridden ? s.overall.word : ""} onChange={(e) => send({ overall: e.target.value || null })}>
        <option value="">Use suggestion</option>{WORDS.map((w) => <option key={w} value={w}>{w}</option>)}</select></Field>}
      <h3>Key Checks</h3>
      <table><tbody>{checks.map((f) => (
        <tr key={f.key}><td>{f.label}</td><td>{s?.derived?.[f.key] === true ? String(f.config.true_label ?? "Yes") : String(f.config.false_label ?? "No")}</td>
          <td>{edit && <select aria-label={`${f.label} override`} value={(insp.overrides?.derived as Record<string, boolean> | undefined)?.[f.key] === undefined ? "" : String((insp.overrides?.derived as Record<string, boolean>)[f.key])}
            onChange={(e) => send({ derived: { [f.key]: e.target.value === "" ? null : e.target.value === "true" } })}>
            <option value="">Automatic</option><option value="true">{String(f.config.true_label ?? "Yes")}</option><option value="false">{String(f.config.false_label ?? "No")}</option></select>}</td></tr>))}</tbody></table>
    </div>
  );
}

type ReportInfo = { verify_url?: string; revision: number; status: string; stale: boolean; generated_at: string | null; filename: string; error: string; url: string | null };

function ReportTab({ booking }: { booking: Booking }) {
  const { can } = useAuth();
  const { say, fail } = useToast();
  const refresh = useRefresh();
  const q = useQuery({ queryKey: ["report", booking.id], retry: false, queryFn: async () => { try { return await api<ReportInfo>(`bookings/${booking.id}/report`); } catch (e) { if (e instanceof ApiError && e.status === 404) return null; throw e; } } });
  const regen = useMutation({ mutationFn: () => api(`bookings/${booking.id}/report/regenerate`, { body: {} }), onSuccess: () => { say("Regenerating. This takes a few seconds."); setTimeout(() => void refresh("report"), 4000); }, onError: fail });
  const r = q.data;
  return (
    <div style={{ maxWidth: 640 }}>
      {!r && <p className="muted">No report yet. It is made automatically when the booking is Completed.</p>}
      {r && <div className="card">
        <p><Pill tone={r.status === "ready" ? "ok" : r.status === "failed" ? "bad" : "warn"}>{r.status}</Pill> {r.stale && <Pill tone="warn">Out of date: regenerate after your edits</Pill>} <span className="muted small">revision {r.revision} · {when(r.generated_at)}</span></p>
        {r.error && <p className="error">Problem: {r.error}</p>}
        {r.url && <a className="btn" href={r.url} download={r.filename}>Download {r.filename}</a>}
        {r.verify_url && <p className="small muted">Public check page: <a href={r.verify_url} target="_blank" rel="noreferrer">{r.verify_url}</a></p>}
      </div>}
      {can("reports.regenerate") && booking.stage === "completed" && <button onClick={() => regen.mutate()}>Regenerate PDF</button>}
    </div>
  );
}

function HistoryTab({ booking, insps, experts, onResolved }: { booking: Booking; insps: Inspection[]; experts: User[]; onResolved: () => void }) {
  const { can } = useAuth();
  const { fail, say } = useToast();
  const [keep, setKeep] = useState("");
  const who = (id: number) => experts.find((u) => u.id === id)?.name ?? `#${id}`;
  const submitted = insps.filter((i) => i.status === "submitted");
  return (
    <div style={{ maxWidth: 720 }}>
      <div className="card"><h3 style={{ marginTop: 0 }}>Inspections</h3>
        <table><tbody>{insps.map((i) => <tr key={i.id}><td>{who(i.expert)}</td><td><Pill tone={i.status === "submitted" ? "ok" : undefined}>{i.status}</Pill></td><td>{when(i.submitted_at)}</td></tr>)}</tbody></table>
        {booking.conflict && can("bookings.edit") && submitted.length > 1 && (
          <div style={{ marginTop: 10 }}>
            <p className="error">Two experts submitted this booking. Choose which inspection counts; the other is kept but set aside.</p>
            <select aria-label="Inspection to keep" value={keep} onChange={(e) => setKeep(e.target.value)}><option value="">Choose…</option>{submitted.map((i) => <option key={i.id} value={i.id}>{who(i.expert)} · {when(i.submitted_at)}</option>)}</select>{" "}
            <button className="primary" disabled={!keep} onClick={async () => { try { await api(`bookings/${booking.id}/resolve-conflict`, { body: { inspection: keep } }); say("Resolved."); onResolved(); } catch (e) { fail(e); } }}>Keep this one</button>
          </div>)}
      </div>
      <div className="card"><h3 style={{ marginTop: 0 }}>Reschedules</h3>
        {((booking as unknown as { reschedules?: { old_date: string; old_time: string; new_date: string; new_time: string; reason: string; by: string; at: string }[] }).reschedules ?? []).map((r, i) => <p key={i} className="small">{r.old_date} {r.old_time} → {r.new_date} {r.new_time} · {r.reason} · {r.by}, {when(r.at)}</p>)}
        {!((booking as unknown as { reschedules?: unknown[] }).reschedules?.length) && <p className="muted small">None.</p>}</div>
    </div>
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
