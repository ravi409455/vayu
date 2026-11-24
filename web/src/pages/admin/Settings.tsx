import { useEffect, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import { useRefresh } from "../../api/hooks";
import { useInspectionTypes } from "../../api/labels";
import { useAuth } from "../../auth";
import { useTiming, type TimingSettings } from "../../lib/timing";
import { Field, PageHeader, useToast } from "../../ui/kit";

/** Settings Admin changes (Ops may look): today the time limits for late starts and too-quick jobs. */
export function Settings() {
  const { can } = useAuth();
  const edit = can("settings.edit");
  const saved = useTiming();
  const types = useInspectionTypes();
  const { say, fail } = useToast();
  const refresh = useRefresh();
  const [v, setV] = useState<TimingSettings>(saved);
  useEffect(() => setV(saved), [saved]);
  const save = useMutation({
    mutationFn: () => api("settings/timing", { method: "PUT", body: v }),
    onSuccess: () => { say("Saved. Flags use the new limits now."); void refresh("settings"); void refresh("bookings-page"); },
    onError: fail,
  });
  const num = (value: number, set: (n: number) => void, label: string) => (
    <input type="number" min={0} max={1440} step={1} aria-label={label} disabled={!edit} value={value}
      onChange={(e) => set(Math.max(0, Math.round(Number(e.target.value) || 0)))} style={{ width: 90 }} />
  );
  const byType = (key: string, n: number | undefined) => {
    const next = { ...v.min_minutes_by_type };
    if (n === undefined) delete next[key]; else next[key] = n;
    setV({ ...v, min_minutes_by_type: next });
  };
  return (
    <>
      <PageHeader title="Settings" subtitle={edit ? undefined : "Only Admin can change these."}>
        {edit && <button className="primary" disabled={save.isPending || JSON.stringify(v) === JSON.stringify(saved)} onClick={() => save.mutate()}>Save</button>}
      </PageHeader>
      <section className="card stack" aria-label="Time limits">
        <h3>Time limits</h3>
        <Field label="Late-start grace (minutes)" help="A booking that starts more than this after its booked date and time shows as “Started late”. Example: booked 10:00, grace 15 → a start after 10:15 is late.">
          {num(v.late_grace_minutes, (n) => setV({ ...v, late_grace_minutes: n }), "Late-start grace (minutes)")}
        </Field>
        <Field label="Minimum inspection time (minutes)" help="A booking finished faster than this (Start to Submit) shows as “Too quick”. Used for any type without its own number below.">
          {num(v.min_minutes_default, (n) => setV({ ...v, min_minutes_default: n }), "Minimum inspection time (minutes)")}
        </Field>
        <table className="rows"><thead><tr><th>Inspection type</th><th>Minimum minutes</th><th></th></tr></thead>
          <tbody>{types.map((t) => {
            const own = v.min_minutes_by_type[t.key];
            return (
              <tr key={t.key}><td>{t.label}</td>
                <td>{own === undefined ? <span className="muted">{v.min_minutes_default} (default)</span> : num(own, (n) => byType(t.key, n), `Minimum minutes for ${t.label}`)}</td>
                <td>{edit && (own === undefined
                  ? <button className="link" onClick={() => byType(t.key, v.min_minutes_default)}>Set own number</button>
                  : <button className="link" onClick={() => byType(t.key, undefined)}>Use default</button>)}</td></tr>);
          })}</tbody></table>
        <p className="muted small">Times are the server's: when it got Start and when it got Submit. A booking whose Start never reached the server is never flagged.</p>
      </section>
      <MediaRetention edit={edit} />
    </>
  );
}

type MediaSettings = { photo_days: number; video_days: number };

/** How long original photos and videos stay on the server (0: for ever). */
function MediaRetention({ edit }: { edit: boolean }) {
  const { say, fail } = useToast();
  const refresh = useRefresh();
  const q = useQuery({ queryKey: ["settings", "media"], queryFn: () => api<MediaSettings>("settings/media") });
  const [v, setV] = useState<MediaSettings | null>(null);
  useEffect(() => { if (q.data) setV(q.data); }, [q.data]);
  const save = useMutation({
    mutationFn: () => api("settings/media", { method: "PUT", body: v }),
    onSuccess: () => { say("Saved. Older files are removed within the hour."); void refresh("settings"); },
    onError: fail,
  });
  if (!v) return null;
  const row = (key: keyof MediaSettings, label: string) => (
    <Field label={label} help="0 keeps them for ever. Otherwise 30 to 3650 days, counted from when the file was uploaded.">
      <input type="number" min={0} max={3650} step={1} aria-label={label} disabled={!edit} value={v[key]} style={{ width: 90 }}
        onChange={(e) => setV({ ...v, [key]: Math.max(0, Math.round(Number(e.target.value) || 0)) })} />
      <span className="muted small"> {v[key] ? `days` : "kept for ever"}</span>
    </Field>);
  const bad = (n: number) => n !== 0 && (n < 30 || n > 3650);
  return (
    <section className="card stack" aria-label="Photo and video storage">
      <div className="bar"><h3 className="grow">Photo and video storage</h3>
        {edit && <button className="primary" disabled={save.isPending || bad(v.photo_days) || bad(v.video_days) || JSON.stringify(v) === JSON.stringify(q.data)} onClick={() => save.mutate()}>Save</button>}</div>
      {row("photo_days", "Keep photos for (days)")}
      {row("video_days", "Keep videos for (days)")}
      <p className="muted small">After that, the original photos and videos of completed bookings are deleted from the server for good. Reports already made keep their pictures, but the report's Download photos and Download videos buttons then tell the customer the files are no longer available. Bookings not yet completed are never touched.</p>
    </section>
  );
}
