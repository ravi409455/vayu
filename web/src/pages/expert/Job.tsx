import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { api, ApiError, explain } from "../../api/client";
import { STAGE_LABEL, STAGE_TONE, useLabels, useTypeLabels } from "../../api/labels";
import type { Booking } from "../../api/types";
import { useRefresh } from "../../api/hooks";
import { missingFields, pageGaps, submittable, type Answers } from "../../lib/formSpec";
import { applyMedia, lockedFrom, reconcileMedia, unvisited, wizardSteps, type Part, type ServerMedia, type Tree } from "../../lib/wizard";
import { loadJSON, removeKey, saveJSON } from "../../lib/store";
import { discardFile, resumeUploads, summary, uploadFor, useUploads, retryFailed } from "../../lib/uploadManager";
import { FormRenderer } from "../../ui/FormRenderer";
import { Confirm, Pill } from "../../ui/kit";
import { useCrumb } from "../../ui/crumb";
import { MapPin, Phone } from "lucide-react";
import { fmtPhone, fmtSlot, mapsUrl } from "../../lib/format";

type Session = { startUuid: string; submitUuid: string; inspectionId: string; form: Tree; startForm: Tree | null; endForm: Tree | null; versionId: number; started?: boolean };   // started: false until the check-in is done (the job is not "in progress" before)
type Forms = { form: Tree; start_form: Tree | null; end_form: Tree | null };
type Draft = { inspection: Answers; start: Answers; end: Answers; step: number; visited?: string[] };
const EMPTY_DRAFT: Draft = { inspection: {}, start: {}, end: {}, step: 0, visited: [] };
const sKey = (id: string) => `vayu:job:${id}`;
const dKey = (id: string) => `vayu:draft:${id}`;

export function Job() {
  const id = useParams().id!;
  const refresh = useRefresh();
  const booking = useQuery({ queryKey: ["job", id], queryFn: () => api<Booking>(`bookings/${id}`), refetchInterval: (q) => (q.state.data?.stage === "submitted" ? 4000 : false) });
  useCrumb(booking.data?.booking_id);
  const [session, setSession] = useState<Session | null>(() => loadJSON<Session | null>(sKey(id), null));
  const b = booking.data;
  const [error, setError] = useState("");
  const car = useLabels("car_make_model");
  const city = useLabels("city");
  const type = useTypeLabels();

  /** Tells the server the job has started. With a check-in form the server wants its answers: a job is
   *  only "in progress" once the check-in is done. */
  const start = useMutation({
    mutationFn: async (startAnswers?: Answers) => {
      const startUuid = session?.startUuid ?? crypto.randomUUID();
      const r = await api<{ inspection: { id: string; form_version: number } } & Forms>(`bookings/${id}/start`, {
        body: { client_uuid: startUuid, client_started_at: new Date().toISOString(), inspection_type: b?.inspection_type, start_answers: startAnswers } });
      const s: Session = { startUuid, submitUuid: session?.submitUuid ?? crypto.randomUUID(), inspectionId: r.inspection.id, form: r.form, startForm: r.start_form, endForm: r.end_form, versionId: r.inspection.form_version, started: true };
      saveJSON(sKey(id), s);
      return s;
    },
    onSuccess: (s) => { setSession(s); setError(""); void refresh("job"); },
    onError: (e) => setError(explain(e)),
  });
  /** Opens the forms on this phone without starting the job; a form with no check-in starts at once. */
  const open = useMutation({
    mutationFn: async () => {
      const f = await api<Forms>(`bookings/${id}/forms`);
      const s: Session = { startUuid: crypto.randomUUID(), submitUuid: crypto.randomUUID(), inspectionId: "", form: f.form, startForm: f.start_form, endForm: f.end_form, versionId: f.form.id, started: false };
      if (!f.start_form) return start.mutateAsync(undefined);
      saveJSON(sKey(id), s);
      return s;
    },
    onSuccess: (s) => setSession(s),
    onError: (e) => setError(explain(e)),
  });

  if (booking.isLoading) return <p className="muted pad">Loading…</p>;
  if (!b) return <p className="error pad">This lead could not be opened.</p>;
  const canWork = b.stage === "assigned" || b.stage === "in_progress";
  return (
    <div style={{ maxWidth: session && canWork ? 1100 : 680 }}>
      {(!session || !canWork) && (
        <>
          <div className="bar"><h1 className="grow">{String(b.answers.customer_name ?? "")}</h1><Pill tone={STAGE_TONE[b.stage]}>{STAGE_LABEL[b.stage] ?? b.stage}</Pill></div>
          <div className="card">
            <dl className="details">
              <dt>When</dt><dd><strong>{fmtSlot(b.answers.inspection_date, b.answers.inspection_time)}</strong></dd>
              <dt>Car</dt><dd>{car(b.answers.car_make_model)} · {type(b.inspection_type)}</dd>
              <dt>Address</dt><dd>{String(b.answers.address ?? "")}, {city(b.answers.city)}</dd>
              <dt>Phone</dt><dd>{fmtPhone(b.answers.customer_phone)}</dd>
              <dt>Booking</dt><dd className="muted">{b.booking_id}</dd>
            </dl>
            <div className="bar" style={{ marginBottom: 0 }}>
              {b.answers.customer_phone ? <a className="btn" href={`tel:${String(b.answers.customer_phone)}`} aria-label={`Call ${String(b.answers.customer_phone)}`}><Phone size={15} aria-hidden /> Call</a> : null}
              {b.answers.address ? <a className="btn" href={mapsUrl(`${String(b.answers.address)} ${city(b.answers.city)}`)} target="_blank" rel="noreferrer"><MapPin size={15} aria-hidden /> Directions</a> : null}
            </div>
          </div>
          {b.stage === "assigned" && <><p className="muted">Check the details above, then start when you reach the car.</p>
            <button className="primary bigbtn" onClick={() => open.mutate()} disabled={open.isPending}>Start inspection</button></>}
          {b.stage === "in_progress" && !session && <button className="primary bigbtn" onClick={() => start.mutate(undefined)} disabled={start.isPending}>Continue inspection</button>}
          {!canWork && <Finished booking={b} />}
          {error && <p className="error" role="alert">{error}</p>}
        </>
      )}
      {session && canWork && <Wizard booking={b} session={session} onStart={(a) => start.mutate(a)} starting={start.isPending} startError={error} onSubmitted={() => { removeKey(dKey(id)); removeKey(sKey(id)); setSession(null); void refresh("job"); }} />}
    </div>
  );
}

function Finished({ booking }: { booking: Booking }) {
  const ups = useUploads(booking.id);
  const { done, total } = summary(ups);
  return (
    <div className="card" role="status">
      {booking.stage === "submitted" && <p><strong>Submitted.</strong> Uploading photos{total ? ` (${done}/${total})` : ""}… keep this page open until it says Completed.</p>}
      {booking.stage === "completed" && <p className="ok"><strong>Completed.</strong> Everything arrived and the report is being made.</p>}
      {booking.stage === "cancelled" && <p>This lead was cancelled.</p>}
      {ups.some((u) => u.status === "failed") && <button onClick={retryFailed}>Retry uploads</button>}
    </div>
  );
}

function Wizard({ booking, session, onStart, starting, startError, onSubmitted }: { booking: Booking; session: Session; onStart: (startAnswers: Answers) => void; starting: boolean; startError: string; onSubmitted: () => void }) {
  const id = booking.id;
  const [draft, setDraft] = useState<Draft>(() => ({ ...EMPTY_DRAFT, ...loadJSON<Partial<Draft>>(dKey(id), {}) }));
  const [errors, setErrors] = useState<Record<string, Record<string, string>>>({});
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const ups = useUploads(id);
  const draftRef = useRef(draft);
  draftRef.current = draft;
  useEffect(() => { saveJSON(dKey(id), draft); }, [id, draft]);

  const insp = session.form;
  const trees = useMemo(() => ({ start: session.startForm ?? null, inspection: insp, end: session.endForm ?? null }), [session, insp]);
  const ctx = { booking: booking.answers, inspection: draft.inspection, start: draft.start, end: draft.end };
  const steps = useMemo(
    () => wizardSteps(trees, { inspection: draft.inspection, start: draft.start, end: draft.end }, ctx),
    [trees, draft.inspection, draft.start, draft.end, booking.answers]); // eslint-disable-line react-hooks/exhaustive-deps
  // A phone that lost its draft (another device, cleared storage): pick up the files the server already holds.
  useEffect(() => {
    let off = false;
    void (async () => {
      await resumeUploads(id);
      const server = await api<ServerMedia[]>(`bookings/${id}/media`).catch(() => null);
      if (!server || off) return;
      const { add, discard: stale } = reconcileMedia(trees, draftRef.current, server, (mid) => !!uploadFor(mid));
      if (add.length > 0) setDraft((d) => applyMedia(d, add));
      stale.forEach((mid) => void discardFile(mid));
    })();
    return () => { off = true; };
  }, [id]); // eslint-disable-line react-hooks/exhaustive-deps

  // The job only becomes "in progress" once the check-in is complete.
  const unstarted = session.started === false;
  const checkinDone = !trees.start || missingFields("start", trees.start, draft.start, ctx).length === 0;
  const tried = useRef("");
  const checkinKey = JSON.stringify(draft.start);
  useEffect(() => {
    if (unstarted && checkinDone && !starting && tried.current !== checkinKey) { tried.current = checkinKey; onStart(draftRef.current.start); }
  }, [unstarted, checkinDone, starting, checkinKey]); // eslint-disable-line react-hooks/exhaustive-deps
  const step = Math.min(draft.step, steps.length - 1);
  const cur = steps[step]!;
  const set = (kind: Part) => (key: string, v: unknown) => setDraft((d) => ({ ...d, [kind]: { ...d[kind], [key]: v } }));
  const [blocked, setBlocked] = useState<string[]>([]);
  const [confirm, setConfirm] = useState<null | "discard" | "submit">(null);
  const stepId = steps[Math.min(draft.step, steps.length - 1)]?.id;
  useEffect(() => {                                   // remember which pages the expert has opened
    if (stepId && !(draft.visited ?? []).includes(stepId)) setDraft((d) => ({ ...d, visited: [...(d.visited ?? []), stepId] }));
  }, [stepId]); // eslint-disable-line react-hooks/exhaustive-deps
  const go = (n: number) => { setMsg(""); setBlocked([]); setDraft((d) => ({ ...d, step: Math.max(0, Math.min(steps.length - 1, n)) })); window.scrollTo?.(0, 0); };
  /** Next: a page the Admin marked "must be finished" holds the person until its required fields are filled. */
  function next() {
    if (cur.kind !== "review" && cur.page?.gate) {
      const gaps = pageGaps(cur.kind, trees[cur.kind]!, cur.page, draft[cur.kind], ctx);
      if (gaps.length > 0) { setBlocked(gaps.map((g) => g.label)); return; }
    }
    go(step + 1);
  }

  const gaps = (["start", "inspection", "end"] as const).flatMap((part) =>
    trees[part] ? missingFields(part, trees[part]!, draft[part], ctx).map((g) => ({ ...g, kind: part })) : []);
  const stepOf = (g: (typeof gaps)[number]) => steps.findIndex((s) => s.kind === g.kind && s.page && trees[g.kind]!.pages[g.page]?.id === s.page.id);

  async function submit() {
    setBusy(true);
    setMsg("");
    try {
      await api(`bookings/${id}/submit`, { body: {
        client_submission_uuid: session.submitUuid, form_version: session.versionId,
        answers: {
          inspection: submittable("inspection", insp, draft.inspection, ctx),
          start: trees.start ? submittable("start", trees.start, draft.start, ctx) : {},
          end: trees.end ? submittable("end", trees.end, draft.end, ctx) : {} } } });
      onSubmitted();
    } catch (e) {
      if (e instanceof ApiError && e.code === "INVALID_ANSWERS") {
        const errs = (e.body.errors ?? {}) as Record<string, string>;
        setErrors({ inspection: errs, start: errs, end: errs });
        const label = (k: string) => Object.values(trees).flatMap((t) => t?.pages.flatMap((pg) => pg.sections.flatMap((sec) => sec.fields)) ?? []).find((f) => f.key === k)?.label || k;
        setMsg("Some answers need another look: " + Object.keys(errs).map(label).join(", "));
      } else setMsg(explain(e));
    } finally { setBusy(false); }
  }

  const { done, total } = summary(ups);
  const progress = Math.round((step / (steps.length - 1)) * 100);
  const missingOn = (s: (typeof steps)[number]) => (s.kind !== "review" && s.page ? pageGaps(s.kind, trees[s.kind]!, s.page, draft[s.kind], ctx).length : 0);
  const lock = lockedFrom(steps, missingOn);
  const gateTitle = steps[lock - 1]?.title ?? "";
  const notOpened = unvisited(steps, draft.visited ?? []);
  async function discard() {
    for (const u of ups) if (u.status !== "done") await discardFile(u.assetId).catch(() => {});
    removeKey(dKey(id));
    setDraft({ ...EMPTY_DRAFT, visited: [] });
    setErrors({}); setBlocked([]); setConfirm(null);
    setMsg(""); window.scrollTo?.(0, 0);
  }
  return (
    <div className="wizard">
      <nav className="card wizard-rail" aria-label="Steps">
        {steps.map((s, i) => {
          const miss = missingOn(s);
          const seen = (draft.visited ?? []).includes(s.id);
          const locked = i >= lock;
          return (
            <button key={i} className={`step-item${i === step ? " on" : ""}${seen ? "" : " unseen"}`} aria-current={i === step ? "step" : undefined} disabled={locked}
              title={locked ? `Finish ${gateTitle} first` : seen ? undefined : "Not opened yet"} onClick={() => go(i)}>
              <span className={`step-dot${seen && miss === 0 && s.kind !== "review" ? " done" : ""}`} aria-hidden="true">{seen && miss === 0 && s.kind !== "review" ? "✓" : i + 1}</span>
              <span className="grow ellipsis">{s.title}</span>
              {seen && miss > 0 && <span className="pill warn" title="Still needed">{miss}</span>}
              {!seen && !locked && s.kind !== "review" && <span className="unseen-dot" aria-label="not opened yet" />}
            </button>);
        })}
        {lock < steps.length && <p className="rail-note">Finish {gateTitle} to open the other pages.</p>}
        <button className="link danger-link" style={{ margin: "8px 8px 2px" }} onClick={() => setConfirm("discard")}>Discard draft…</button>
      </nav>
      <div className="wizard-main">
      <h1>{String(booking.answers.customer_name ?? "")} <span className="muted small">{booking.booking_id}</span></h1>
      <div className="progress" aria-label={`Step ${step + 1} of ${steps.length}`}><div style={{ width: `${progress}%` }} /></div>
      {unstarted && (
        <div className="banner" role="status">
          {startError && checkinDone
            ? <><strong>The lead could not be started.</strong> {startError} <button className="link" onClick={() => { tried.current = ""; onStart(draft.start); }}>Try again</button></>
            : <><strong>Not started yet.</strong> The lead starts as soon as the check-in is complete.</>}
        </div>)}
      <p className="muted small" style={{ margin: "6px 0 14px" }}>Step {step + 1} of {steps.length}: {cur.title}{total > 0 && ` · files ${done}/${total} sent`}</p>
      <label className="wizard-jump"><span className="muted small">Go to</span>
        <select aria-label="Go to page" value={step} onChange={(e) => go(Number(e.target.value))}>
          {steps.map((s, i) => <option key={s.id} value={i} disabled={i >= lock}>{i + 1}. {s.title}{missingOn(s) ? ` (${missingOn(s)} needed)` : ""}{(draft.visited ?? []).includes(s.id) || s.kind === "review" ? "" : " · not opened"}</option>)}
        </select></label>
      {cur.kind !== "review" && cur.page && (
        <FormRenderer kind={cur.kind} tree={trees[cur.kind]!} values={draft[cur.kind]} ctx={ctx} pages={[cur.page]} role="expert"
          bookingId={id} errors={errors[cur.kind]} onChange={set(cur.kind)} />
      )}
      {cur.kind === "review" && (
        <div>
          <h2>Before you submit</h2>
          {notOpened.length > 0 && (
            <div className="banner warn" role="status"><strong>{notOpened.length} page{notOpened.length === 1 ? "" : "s"} not opened yet.</strong> Check {notOpened.length === 1 ? "it" : "them"} before you submit:{" "}
              {notOpened.map((s, i) => <span key={s.id}>{i > 0 && ", "}<button className="link" onClick={() => go(steps.indexOf(s))}>{s.title}</button></span>)}</div>)}
          {gaps.length === 0 ? <p className="ok" role="status">Everything required is filled in.</p> : (
            <div className="card" role="alert"><strong>{gaps.length} thing{gaps.length === 1 ? "" : "s"} still needed</strong>
              <ul>{gaps.map((g) => <li key={`${g.kind}.${g.key}`}><button className="link" onClick={() => go(stepOf(g))}>{g.label}</button> <span className="muted small">({g.pageTitle})</span></li>)}</ul></div>)}
          {ups.some((u) => u.status !== "done") && <p className="muted">Photos still uploading: {total - done}. You can submit now; they keep sending.</p>}
          {msg && <p className="error" role="alert">{msg}</p>}
          <button className="primary bigbtn" disabled={busy || unstarted || gaps.length > 0} onClick={() => (notOpened.length ? setConfirm("submit") : void submit())}>Submit inspection</button>
        </div>
      )}
      {blocked.length > 0 && <div className="card" role="alert"><strong>Finish this step first</strong><p className="muted small">You cannot move on until these are done:</p><ul>{blocked.map((b) => <li key={b}>{b}</li>)}</ul></div>}
      {confirm === "discard" && (
        <Confirm title="Start this inspection again?" danger confirmLabel="Discard draft" onCancel={() => setConfirm(null)} onConfirm={() => void discard()}>
          <p>Every answer saved on this device for {booking.booking_id} is cleared and you start again at step 1. Photos that have not finished sending are dropped. This cannot be undone.</p>
          <p className="muted small">The lead stays yours and stays started; nothing has been sent to the office yet.</p>
        </Confirm>)}
      {confirm === "submit" && (
        <Confirm title={`Submit with ${notOpened.length} page${notOpened.length === 1 ? "" : "s"} not opened?`} confirmLabel="Submit anyway" onCancel={() => setConfirm(null)} onConfirm={() => { setConfirm(null); void submit(); }}>
          <p>You have not opened: {notOpened.map((s) => s.title).join(", ")}. Their questions are sent unanswered.</p>
        </Confirm>)}
      <div className="wizard-foot">
        <button onClick={() => go(step - 1)} disabled={step === 0}>Back</button>
        <span className="grow muted small" style={{ textAlign: "center" }}>Saved on this device</span>
        {cur.kind !== "review" && <button className="primary" onClick={next}>Next</button>}
      </div>
      </div>
    </div>
  );
}

