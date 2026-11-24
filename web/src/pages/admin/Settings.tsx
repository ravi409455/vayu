import { useEffect, useState } from "react";
import { useMutation } from "@tanstack/react-query";
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
        <Field label="Late-start grace (minutes)" help="A job that starts more than this after its booked date and time shows as “Started late”. Example: booked 10:00, grace 15 → a start after 10:15 is late.">
          {num(v.late_grace_minutes, (n) => setV({ ...v, late_grace_minutes: n }), "Late-start grace (minutes)")}
        </Field>
        <Field label="Minimum inspection time (minutes)" help="A job finished faster than this (Start to Submit) shows as “Too quick”. Used for any type without its own number below.">
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
        <p className="muted small">Times are the server's: when it got Start and when it got Submit. A job whose Start never reached the server is never flagged.</p>
      </section>
    </>
  );
}
