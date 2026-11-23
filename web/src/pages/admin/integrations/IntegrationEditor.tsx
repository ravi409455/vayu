import { useEffect, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api, ApiError } from "../../../api/client";
import { asList, useList, useRefresh } from "../../../api/hooks";
import type { Booking, FormSummary, Integration } from "../../../api/types";
import { cleanPairs, cleanRows, EVENT_LABEL, eventsFor, hasBody, METHODS, type CatalogueEntry } from "../../../lib/integrationDef";
import { useCrumb } from "../../../ui/crumb";
import { Field, PageHeader, useToast } from "../../../ui/kit";
import { BodyBuilder } from "./BodyBuilder";
import { FieldChecklist, PairRows } from "./Rows";
import { ValueInput } from "./ValueInput";

type Draft = Omit<Integration, "id" | "form_key" | "broken_refs"> & { id?: string };
const blank = (form: number, event: string): Draft => ({ form, name: "", event, method: "POST", url: "", query: [], headers: [], body_mode: "standard", body: { rows: [] }, include_data: true, include_pdf: event === "pdf.ready", include_image_zip: false, include_video_zip: false, fields: [], is_active: true });

/** What goes to the server (and to the preview): half-built rows are left out. */
export const configOf = (d: Draft) => ({
  form: d.form, name: d.name, event: d.event, method: d.method, url: d.url, query: cleanPairs(d.query), headers: cleanPairs(d.headers),
  body_mode: d.body_mode, body: d.body_mode === "custom" ? { rows: cleanRows(d.body.rows ?? []) } : {},
  include_data: d.include_data, include_pdf: d.include_pdf, include_image_zip: d.include_image_zip, include_video_zip: d.include_video_zip, fields: d.fields, is_active: d.is_active,
});

type Shown = { method: string; url: string; headers: { name: string; value: string }[]; body: string | null; sample: boolean; booking: string | null; broken_refs: string[] };

/** One integration: the request on the left, what it would send on the right. */
export function IntegrationEditor() {
  const { id } = useParams();
  const [sp] = useSearchParams();
  const copy = sp.get("copy");
  const nav = useNavigate();
  const { say } = useToast();
  const refresh = useRefresh();
  const forms = useList<FormSummary>("forms", "forms");
  const eligible = (forms.data ?? []).filter((f) => f.type === "booking" || f.type === "custom");
  const source = id && id !== "new" ? id : copy;
  const loaded = useQuery({ queryKey: ["integration", source], queryFn: () => api<Integration>(`integrations/${source}`), enabled: !!source });
  const [d, setD] = useState<Draft | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    if (d) return;
    if (source && loaded.data) {
      const { id: _id, form_key: _k, broken_refs: _b, ...rest } = loaded.data;
      setD(id === "new" ? { ...rest, name: `${rest.name} (copy)`, is_active: false } : { ...rest, id: loaded.data.id });
    } else if (!source && eligible[0]) setD(blank(eligible[0].id, eligible[0].type === "booking" ? "booking.created" : "pdf.ready"));
  }, [d, source, loaded.data, eligible, id]);
  const form = eligible.find((f) => f.id === d?.form);
  const catalogue = useQuery({ queryKey: ["catalogue", d?.form, d?.event], queryFn: () => api<CatalogueEntry[]>("integrations/catalogue", { query: { form: d!.form, event: d!.event } }), enabled: !!d?.form && !!d?.event });
  useCrumb(d?.id ? d.name : "New integration");

  const save = useMutation({
    mutationFn: (v: Draft) => (v.id ? api<Integration>(`integrations/${v.id}`, { method: "PATCH", body: configOf(v) }) : api<Integration>("integrations", { body: configOf(v) })),
    onSuccess: () => { say("Saved."); void refresh("integrations", "integration"); nav("/integrations"); },
    onError: (e) => setError(e instanceof ApiError ? e.message : "Could not save."),
  });
  if (!d) return <p className="muted pad">Loading…</p>;
  const set = (p: Partial<Draft>) => { setError(""); setD({ ...d, ...p }); };
  const cat = catalogue.data ?? [];
  const setForm = (fid: number) => {
    const f = eligible.find((x) => x.id === fid)!;
    set({ form: fid, event: eventsFor(f.type).includes(d.event) ? d.event : eventsFor(f.type)[0]! });
  };
  return (
    <>
      <PageHeader title={d.id ? "Edit integration" : "New integration"} subtitle="Design the request another system receives. Pick values from the list instead of typing field names." />
      <div className="integration-editor">
        <div className="card">
          <Field label="Name"><input aria-label="Name" value={d.name} onChange={(e) => set({ name: e.target.value })} /></Field>
          <div className="grid2">
            <Field label="Form"><select aria-label="Form" value={d.form} disabled={!!d.id} onChange={(e) => setForm(Number(e.target.value))}>{eligible.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}</select></Field>
            <Field label="Send when" help="One event per integration. Make another integration for another event."><select aria-label="Send when" value={d.event} onChange={(e) => set({ event: e.target.value })}>
              {eventsFor(form?.type ?? "custom").map((e) => <option key={e} value={e}>{EVENT_LABEL[e]}</option>)}</select></Field>
          </div>
          <div className="request-line">
            <Field label="Method"><select aria-label="Method" value={d.method} onChange={(e) => set({ method: e.target.value })}>{METHODS.map((m) => <option key={m}>{m}</option>)}</select></Field>
            <Field label="URL" help="Values can go in the path after the address, e.g. https://crm.example.com/leads/ + Booking ID."><ValueInput label="URL" value={d.url} catalogue={cat} placeholder="https://" onChange={(v) => set({ url: v })} /></Field>
          </div>
          <h3>Query parameters</h3>
          <PairRows what="Parameter" namePlaceholder="name" rows={d.query} catalogue={cat} onChange={(query) => set({ query })} />
          <h3>Headers</h3>
          <PairRows what="Header" namePlaceholder="e.g. Authorization" rows={d.headers} catalogue={cat} onChange={(headers) => set({ headers })} />
          <p className="muted small">There is no signature: put the token the other system expects in a header, and use https.</p>
          <h3>Body</h3>
          {!hasBody(d.method) ? <p className="muted">No body is sent with {d.method}.</p> : (
            <>
              <div className="seg" role="group" aria-label="Body type">
                <button type="button" aria-pressed={d.body_mode === "standard"} onClick={() => set({ body_mode: "standard" })}>Standard</button>
                <button type="button" aria-pressed={d.body_mode === "custom"} onClick={() => set({ body_mode: "custom" })}>Custom</button>
              </div>
              {d.body_mode === "standard" ? (
                <>
                  <fieldset className="plain"><legend>What to include</legend>
                    <label className="check"><input type="checkbox" checked={d.include_data} onChange={(e) => set({ include_data: e.target.checked })} /> Data (booking and inspection answers)</label>
                    <label className="check"><input type="checkbox" checked={d.include_pdf} onChange={(e) => set({ include_pdf: e.target.checked })} /> PDF link (valid 7 days)</label>
                    <label className="check"><input type="checkbox" checked={d.include_image_zip} onChange={(e) => set({ include_image_zip: e.target.checked })} /> Image ZIP link</label>
                    <label className="check"><input type="checkbox" checked={d.include_video_zip} onChange={(e) => set({ include_video_zip: e.target.checked })} /> Video ZIP link</label></fieldset>
                  {d.include_data && <FieldChecklist fields={d.fields} catalogue={cat} onChange={(fields) => set({ fields })} />}
                </>
              ) : <BodyBuilder rows={d.body.rows ?? []} catalogue={cat} onChange={(rows) => set({ body: { rows } })} />}
            </>)}
          {d.id && <label className="check" style={{ marginTop: 12 }}><input type="checkbox" checked={d.is_active} onChange={(e) => set({ is_active: e.target.checked })} /> Active</label>}
        </div>
        <Preview d={d} onError={setError} />
      </div>
      {error && <p className="error" role="alert">{error}</p>}
      <div className="bar" style={{ marginTop: 14 }}>
        <span className="grow" />
        <button onClick={() => nav("/integrations")}>Cancel</button>
        <button className="primary" disabled={save.isPending || !d.name.trim() || !d.url.trim()} onClick={() => save.mutate(d)}>Save</button>
      </div>
    </>
  );
}

/** The whole request as it would be sent, for a real job (the latest, or one picked by Booking ID) or sample values. */
function Preview({ d, onError }: { d: Draft; onError: (m: string) => void }) {
  const [job, setJob] = useState<{ id: string; ref: string } | null>(null);
  const [ref, setRef] = useState("");
  const [shown, setShown] = useState<Shown | null>(null);
  const [problem, setProblem] = useState("");
  const cfg = JSON.stringify({ ...configOf(d), booking: job?.id });
  useEffect(() => {
    if (!d.url.trim()) { setShown(null); setProblem(""); return; }
    let live = true;
    const t = setTimeout(() => {
      api<Shown>("integrations/preview", { body: JSON.parse(cfg) })
        .then((r) => { if (live) { setShown(r); setProblem(""); } })
        .catch((e: unknown) => { if (live) { setShown(null); setProblem(e instanceof ApiError ? e.message : "The preview could not be made."); } });
    }, 400);
    return () => { live = false; clearTimeout(t); };
  }, [cfg, d.url]);
  async function find() {
    if (!ref.trim()) { setJob(null); return; }
    const r = asList<Booking>(await api("bookings", { query: { search: ref.trim() } }));
    const hit = r.find((b) => b.booking_id.toLowerCase() === ref.trim().toLowerCase()) ?? r[0];
    if (hit) setJob({ id: hit.id, ref: hit.booking_id }); else onError(`No booking found for “${ref}”.`);
  }
  return (
    <div className="card request-preview" aria-label="Request preview">
      <h3>Preview</h3>
      <div className="bar">
        <input aria-label="Preview with booking" placeholder="Booking ID (default: latest)" value={ref} onChange={(e) => setRef(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") void find(); }} />
        <button type="button" onClick={() => void find()}>Use</button>
      </div>
      {problem && <div className="banner bad" role="alert">{problem}</div>}
      {shown && (
        <>
          <p className="muted small">{shown.sample ? "Sample values: no job exists yet for this form." : `Values of ${job?.ref ?? "the latest job"}. Nothing is sent from here.`}</p>
          {shown.broken_refs.length > 0 && <div className="banner warn">Uses {shown.broken_refs.join(", ")}, which the form no longer has. They are sent as empty.</div>}
          <pre className="mono" data-testid="preview-request">{`${shown.method} ${shown.url}\n${shown.headers.map((h) => `${h.name}: ${h.value}`).join("\n")}${shown.body ? `\n\n${shown.body}` : ""}`}</pre>
        </>)}
      {!shown && !problem && <p className="muted">Enter the URL to see the request.</p>}
    </div>
  );
}
