import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { api, ApiError, explain } from "../../api/client";
import { STAGE_LABEL, STAGE_TONE, useLabels } from "../../api/labels";
import type { Booking, FormVersion } from "../../api/types";
import { useRefresh } from "../../api/hooks";
import { missingFields, splitOpsPages, submittable, visiblePages, type Answers } from "../../lib/formSpec";
import { loadJSON, removeKey, saveJSON } from "../../lib/store";
import { resumeUploads, summary, useUploads, retryFailed } from "../../lib/uploadManager";
import { FormRenderer } from "../../ui/FormRenderer";
import { Pill } from "../../ui/kit";

type Tree = Pick<FormVersion, "pages" | "checks"> & { id: number };
type Session = { startUuid: string; submitUuid: string; inspectionId: string; form: Tree; opsForm: Tree | null; versionId: number };
type Draft = { inspection: Answers; ops: Answers; step: number };
const sKey = (id: string) => `vayu:job:${id}`;
const dKey = (id: string) => `vayu:draft:${id}`;

export function Job() {
  const id = useParams().id!;
  const refresh = useRefresh();
  const booking = useQuery({ queryKey: ["job", id], queryFn: () => api<Booking>(`bookings/${id}`), refetchInterval: (q) => (q.state.data?.stage === "submitted" ? 4000 : false) });
  const [session, setSession] = useState<Session | null>(() => loadJSON<Session | null>(sKey(id), null));
  const b = booking.data;
  const [error, setError] = useState("");
  const car = useLabels("car_make_model");
  const city = useLabels("city");
  const type = useLabels("inspection_type");

  const start = useMutation({
    mutationFn: async () => {
      const startUuid = session?.startUuid ?? crypto.randomUUID();
      const r = await api<{ inspection: { id: string; form_version: number }; form: Tree; ops_form: Tree | null }>(`bookings/${id}/start`, {
        body: { client_uuid: startUuid, client_started_at: new Date().toISOString(), inspection_type: b?.inspection_type } });
      const s: Session = { startUuid, submitUuid: session?.submitUuid ?? crypto.randomUUID(), inspectionId: r.inspection.id, form: r.form, opsForm: r.ops_form, versionId: r.inspection.form_version };
      saveJSON(sKey(id), s);
      return s;
    },
    onSuccess: (s) => { setSession(s); void refresh("job"); },
    onError: (e) => setError(explain(e)),
  });

  if (booking.isLoading) return <p className="muted pad">Loading…</p>;
  if (!b) return <p className="error pad">This job could not be opened.</p>;
  const canWork = b.stage === "assigned" || b.stage === "in_progress";
  return (
    <div style={{ maxWidth: 680 }}>
      <p><Link to="/jobs">← My jobs</Link></p>
      {(!session || !canWork) && (
        <>
          <div className="bar"><h1 className="grow">{String(b.answers.customer_name ?? "")}</h1><Pill tone={STAGE_TONE[b.stage]}>{STAGE_LABEL[b.stage] ?? b.stage}</Pill></div>
          <div className="card">
            <p><strong>{car(b.answers.car_make_model)}</strong> · {type(b.inspection_type)}</p>
            <p>{String(b.answers.inspection_date ?? "")} at {String(b.answers.inspection_time ?? "")} · {city(b.answers.city)}</p>
            <p>{String(b.answers.address ?? "")}</p>
            <p><a href={`tel:${String(b.answers.customer_phone ?? "")}`}>📞 {String(b.answers.customer_phone ?? "")}</a></p>
            <p className="muted small">Booking {b.booking_id}</p>
          </div>
          {b.stage === "assigned" && <><p className="muted">Check the details above, then start when you reach the car.</p>
            <button className="primary bigbtn" onClick={() => start.mutate()} disabled={start.isPending}>Start inspection</button></>}
          {b.stage === "in_progress" && !session && <button className="primary bigbtn" onClick={() => start.mutate()}>Continue inspection</button>}
          {!canWork && <Finished booking={b} />}
          {error && <p className="error" role="alert">{error}</p>}
        </>
      )}
      {session && canWork && <Wizard booking={b} session={session} onSubmitted={() => { removeKey(dKey(id)); removeKey(sKey(id)); setSession(null); void refresh("job"); }} />}
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
      {booking.stage === "cancelled" && <p>This job was cancelled.</p>}
      {ups.some((u) => u.status === "failed") && <button onClick={retryFailed}>Retry uploads</button>}
    </div>
  );
}

function Wizard({ booking, session, onSubmitted }: { booking: Booking; session: Session; onSubmitted: () => void }) {
  const id = booking.id;
  const [draft, setDraft] = useState<Draft>(() => loadJSON<Draft>(dKey(id), { inspection: {}, ops: {}, step: 0 }));
  const [errors, setErrors] = useState<Record<string, Record<string, string>>>({});
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const ups = useUploads(id);
  useEffect(() => { void resumeUploads(id); }, [id]);
  useEffect(() => { saveJSON(dKey(id), draft); }, [id, draft]);

  const insp = session.form;
  const ops = session.opsForm;
  const ctx = { booking: booking.answers, inspection: draft.inspection, ops: draft.ops };
  const steps = useMemo(() => {
    const out: { id: string; title: string; kind: "ops" | "inspection" | "review"; page?: Tree["pages"][number] }[] = [];
    const split = ops ? splitOpsPages(visiblePages("ops", ops, draft.ops, ctx)) : { checkIn: [], wrapUp: [] };
    split.checkIn.forEach((p) => out.push({ id: `o${p.id}`, title: p.title, kind: "ops", page: p }));
    visiblePages("inspection", insp, draft.inspection, ctx).forEach((p) => out.push({ id: `i${p.id}`, title: p.title, kind: "inspection", page: p }));
    split.wrapUp.forEach((p) => out.push({ id: `o${p.id}`, title: p.title, kind: "ops", page: p }));
    out.push({ id: "review", title: "Review & submit", kind: "review" });
    return out;
  }, [insp, ops, draft.inspection, draft.ops, booking.answers]); // eslint-disable-line react-hooks/exhaustive-deps
  const step = Math.min(draft.step, steps.length - 1);
  const cur = steps[step]!;
  const set = (kind: "ops" | "inspection") => (key: string, v: unknown) => setDraft((d) => ({ ...d, [kind]: { ...d[kind], [key]: v } }));
  const go = (n: number) => { setMsg(""); setDraft((d) => ({ ...d, step: Math.max(0, Math.min(steps.length - 1, n)) })); window.scrollTo?.(0, 0); };

  const gaps = [
    ...missingFields("inspection", insp, draft.inspection, ctx).map((g) => ({ ...g, kind: "inspection" as const })),
    ...(ops ? missingFields("ops", ops, draft.ops, ctx).map((g) => ({ ...g, kind: "ops" as const })) : []),
  ];
  const stepOf = (g: (typeof gaps)[number]) => steps.findIndex((s) => s.kind === g.kind && s.page && (g.kind === "inspection" ? insp : ops!).pages[g.page]?.id === s.page.id);

  async function submit() {
    setBusy(true);
    setMsg("");
    try {
      await api(`bookings/${id}/submit`, { body: {
        client_submission_uuid: session.submitUuid, form_version: session.versionId,
        answers: { inspection: submittable("inspection", insp, draft.inspection, ctx), ops: ops ? submittable("ops", ops, draft.ops, ctx) : {} } } });
      onSubmitted();
    } catch (e) {
      if (e instanceof ApiError && e.code === "INVALID_ANSWERS") {
        const errs = (e.body.errors ?? {}) as Record<string, string>;
        setErrors({ inspection: errs, ops: errs });
        setMsg("Some answers need another look: " + Object.keys(errs).join(", "));
      } else setMsg(explain(e));
    } finally { setBusy(false); }
  }

  const { done, total } = summary(ups);
  const progress = Math.round((step / (steps.length - 1)) * 100);
  return (
    <div>
      <h1>{String(booking.answers.customer_name ?? "")} <span className="muted small">{booking.booking_id}</span></h1>
      <div className="progress" aria-label={`Step ${step + 1} of ${steps.length}`}><div style={{ width: `${progress}%` }} /></div>
      <p className="muted small" style={{ margin: "6px 0 14px" }}>Step {step + 1} of {steps.length}: {cur.title}{total > 0 && ` · files ${done}/${total} sent`}</p>
      {cur.kind !== "review" && cur.page && (
        <FormRenderer kind={cur.kind} tree={cur.kind === "ops" ? ops! : insp} values={draft[cur.kind]} ctx={ctx} pages={[cur.page]} role="expert"
          bookingId={id} errors={errors[cur.kind]} onChange={set(cur.kind)} />
      )}
      {cur.kind === "review" && (
        <div>
          <h2>Before you submit</h2>
          {gaps.length === 0 ? <p className="ok" role="status">Everything required is filled in.</p> : (
            <div className="card" role="alert"><strong>{gaps.length} thing{gaps.length === 1 ? "" : "s"} still needed</strong>
              <ul>{gaps.map((g) => <li key={`${g.kind}.${g.key}`}><button className="link" onClick={() => go(stepOf(g))}>{g.label}</button> <span className="muted small">({g.pageTitle})</span></li>)}</ul></div>)}
          {ups.some((u) => u.status !== "done") && <p className="muted">Photos still uploading: {total - done}. You can submit now; they keep sending.</p>}
          {msg && <p className="error" role="alert">{msg}</p>}
          <button className="primary bigbtn" disabled={busy || gaps.length > 0} onClick={submit}>Submit inspection</button>
        </div>
      )}
      <div className="bar" style={{ marginTop: 16 }}>
        <button onClick={() => go(step - 1)} disabled={step === 0}>Back</button>
        <span className="grow" />
        {cur.kind !== "review" && <button className="primary" onClick={() => go(step + 1)}>Next</button>}
      </div>
    </div>
  );
}

