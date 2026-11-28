import { useEffect, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api, ApiError } from "../../../api/client";
import { asList, useList, useRefresh } from "../../../api/hooks";
import type { Booking, FormSummary, Integration } from "../../../api/types";
import {
  bodyText,
  cleanPairs,
  EVENT_LABEL,
  hasBody,
  integrationForms,
  METHODS,
  parseBody,
  pickerHint,
  STARTER_BODY,
  type CatalogueEntry,
} from "../../../lib/integrationDef";
import { useCrumb } from "../../../ui/crumb";
import { Field, LoadError, PageHeader, useToast } from "../../../ui/kit";
import { JsonEditor } from "./JsonEditor";
import { FieldChecklist, PairRows } from "./Rows";
import { PickerHint, ValueInput } from "./ValueInput";
import { keys } from "../../../api/keys";

/** `bodyText` is what is in the JSON editor; `body` is the last text that parsed. */
type Draft = Omit<Integration, "id" | "form_key" | "broken_refs"> & { id?: string; bodyText: string };
const blank = (form: number, event: string): Draft => ({
  form,
  name: "",
  event,
  method: "POST",
  url: "",
  query: [],
  headers: [],
  body_mode: "standard",
  body: {},
  bodyText: "",
  include_data: true,
  include_pdf: event === "pdf.ready",
  include_image_zip: false,
  include_video_zip: false,
  fields: [],
  is_active: true,
});

/** What goes to the server (and to the preview): half-built rows are left out. */
export const configOf = (d: Draft) => ({
  form: d.form,
  name: d.name,
  event: d.event,
  method: d.method,
  url: d.url,
  query: cleanPairs(d.query),
  headers: cleanPairs(d.headers),
  body_mode: d.body_mode,
  body: d.body_mode === "custom" ? d.body : {},
  include_data: d.include_data,
  include_pdf: d.include_pdf,
  include_image_zip: d.include_image_zip,
  include_video_zip: d.include_video_zip,
  fields: d.fields,
  is_active: d.is_active,
});

type Shown = {
  method: string;
  url: string;
  headers: { name: string; value: string }[];
  body: string | null;
  sample: boolean;
  booking: string | null;
  broken_refs: string[];
};

/** One integration: the request on the left, what it would send on the right. */
export function IntegrationEditor() {
  const { id } = useParams();
  const [sp] = useSearchParams();
  const copy = sp.get("copy");
  const nav = useNavigate();
  const { say } = useToast();
  const refresh = useRefresh();
  const forms = useList<FormSummary>(keys.forms(), "forms");
  const eligible = integrationForms(forms.data ?? []);
  const source = id && id !== "new" ? id : copy;
  const loaded = useQuery({
    queryKey: keys.integration(source),
    queryFn: ({ signal }) => api<Integration>(`integrations/${source}`, { signal }),
    enabled: !!source,
  });
  const [d, setD] = useState<Draft | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    if (d) return;
    if (source && loaded.data) {
      const { id: _id, form_key: _k, broken_refs: _b, ...rest } = loaded.data;
      const withText = { ...rest, bodyText: bodyText(rest.body) };
      setD(id === "new" ? { ...withText, name: `${rest.name} (copy)`, is_active: false } : { ...withText, id: loaded.data.id });
    } else if (!source && eligible[0]) {
      // an inspection form first: it offers the most values
      const first = eligible.find((f) => f.type === "custom") ?? eligible[0];
      setD(blank(first.id, first.type === "booking" ? "booking.created" : "pdf.ready"));
    }
  }, [d, source, loaded.data, eligible, id]);
  const form = eligible.find((f) => f.id === d?.form);
  // the events this form can use (one table on the server)
  const events = useQuery({
    queryKey: keys.integrationEvents(d?.form),
    queryFn: ({ signal }) => api<string[]>("integrations/events", { query: { form: d!.form }, signal }),
    enabled: !!d?.form,
  });
  const eventOk = !!d && !!events.data?.includes(d.event);
  useEffect(() => {
    if (d && events.data?.length && !events.data.includes(d.event)) setD({ ...d, event: events.data[0]! });
  }, [d, events.data]);
  const catalogue = useQuery({
    queryKey: keys.catalogue(d?.form, d?.event),
    queryFn: ({ signal }) => api<CatalogueEntry[]>("integrations/catalogue", { query: { form: d!.form, event: d!.event }, signal }),
    enabled: eventOk,
  });
  // every field of the form, whatever the event: the checklist of the standard body lists these
  const everything = useQuery({
    queryKey: keys.catalogue(d?.form, "all"),
    queryFn: ({ signal }) => api<CatalogueEntry[]>("integrations/catalogue", { query: { form: d!.form }, signal }),
    enabled: !!d?.form,
  });
  useCrumb(d?.id ? d.name : "New integration");

  const save = useMutation({
    mutationFn: (v: Draft) =>
      v.id
        ? api<Integration>(`integrations/${v.id}`, { method: "PATCH", body: configOf(v) })
        : api<Integration>("integrations", { body: configOf(v) }),
    onSuccess: () => {
      say("Saved.");
      void refresh(keys.integrations(), keys.integration());
      nav("/integrations");
    },
    onError: (e) => setError(e instanceof ApiError ? e.message : "Could not save."),
  });
  if (loaded.isError) return <LoadError error={loaded.error} what="integration" onRetry={loaded.refetch} />;
  if (!d) return <p className="muted pad">Loading…</p>;
  const set = (p: Partial<Draft>) => {
    setError("");
    setD({ ...d, ...p });
  };
  const cat = catalogue.data ?? [];
  const parsed = d.body_mode === "custom" && hasBody(d.method) ? parseBody(d.bodyText) : null;
  const setText = (text: string) => {
    const p = parseBody(text);
    set({ bodyText: text, ...(p.ok ? { body: p.body } : {}) });
  };
  const setForm = (fid: number) => set({ form: fid }); // the event follows the form's list
  return (
    <PickerHint.Provider value={pickerHint(form?.type ?? "custom", d.event)}>
      <PageHeader
        title={d.id ? "Edit integration" : "New integration"}
        subtitle="Design the request another system receives. Pick values from the list instead of typing field names."
      />
      <div className="integration-editor">
        <div className="card">
          <Field label="Name">
            <input aria-label="Name" value={d.name} onChange={(e) => set({ name: e.target.value })} />
          </Field>
          <div className="grid2">
            <Field label="Form">
              <select aria-label="Form" value={d.form} onChange={(e) => setForm(Number(e.target.value))}>
                {eligible.map((f) => (
                  <option key={f.id} value={f.id}>
                    {f.name}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Send when" help="One event per integration. Make another integration for another event.">
              <select aria-label="Send when" value={d.event} onChange={(e) => set({ event: e.target.value })}>
                {(events.data ?? [d.event]).map((e) => (
                  <option key={e} value={e}>
                    {EVENT_LABEL[e]}
                  </option>
                ))}
              </select>
            </Field>
          </div>
          <div className="request-line">
            <Field label="Method">
              <select aria-label="Method" value={d.method} onChange={(e) => set({ method: e.target.value })}>
                {METHODS.map((m) => (
                  <option key={m}>{m}</option>
                ))}
              </select>
            </Field>
            <Field label="URL" help="Values can go in the path after the address, e.g. https://crm.example.com/leads/ + Booking ID.">
              <ValueInput label="URL" value={d.url} catalogue={cat} placeholder="https://" onChange={(v) => set({ url: v })} />
            </Field>
          </div>
          <h2 className="sub">Query parameters</h2>
          <PairRows what="Parameter" namePlaceholder="name" rows={d.query} catalogue={cat} onChange={(query) => set({ query })} />
          <h2 className="sub">Headers</h2>
          <PairRows
            what="Header"
            namePlaceholder="e.g. Authorization"
            rows={d.headers}
            catalogue={cat}
            onChange={(headers) => set({ headers })}
          />
          <p className="muted small">There is no signature: put the token the other system expects in a header, and use https.</p>
          <h2 className="sub">Body</h2>
          {!hasBody(d.method) ? (
            <p className="muted">No body is sent with {d.method}.</p>
          ) : (
            <>
              <div className="seg" role="group" aria-label="Body type">
                <button type="button" aria-pressed={d.body_mode === "standard"} onClick={() => set({ body_mode: "standard" })}>
                  Standard
                </button>
                <button
                  type="button"
                  aria-pressed={d.body_mode === "custom"}
                  onClick={() => {
                    const start = d.bodyText.trim() === "" ? STARTER_BODY : d.bodyText;
                    const p = parseBody(start);
                    set({ body_mode: "custom", bodyText: start, ...(p.ok ? { body: p.body } : {}) });
                  }}
                >
                  Custom
                </button>
              </div>
              {d.body_mode === "standard" ? (
                <>
                  <fieldset className="plain">
                    <legend>What to include</legend>
                    <label className="check">
                      <input type="checkbox" checked={d.include_data} onChange={(e) => set({ include_data: e.target.checked })} /> Data
                      (booking and {form?.type === "start" ? "check-in" : "inspection"} answers)
                    </label>
                    {form?.type !== "start" && (
                      <>
                        <label className="check">
                          <input type="checkbox" checked={d.include_pdf} onChange={(e) => set({ include_pdf: e.target.checked })} /> PDF
                          link (valid 7 days)
                        </label>
                        <label className="check">
                          <input
                            type="checkbox"
                            checked={d.include_image_zip}
                            onChange={(e) => set({ include_image_zip: e.target.checked })}
                          />{" "}
                          Image ZIP link
                        </label>
                        <label className="check">
                          <input
                            type="checkbox"
                            checked={d.include_video_zip}
                            onChange={(e) => set({ include_video_zip: e.target.checked })}
                          />{" "}
                          Video ZIP link
                        </label>
                      </>
                    )}
                  </fieldset>
                  {d.include_data && (
                    <FieldChecklist
                      fields={d.fields}
                      catalogue={everything.data ?? []}
                      parts={form?.type === "start" ? ["booking", "start"] : undefined}
                      onChange={(fields) => set({ fields })}
                    />
                  )}
                </>
              ) : (
                <JsonEditor value={d.bodyText} onChange={setText} catalogue={cat} error={parsed && !parsed.ok ? parsed.error : ""} />
              )}
            </>
          )}
          {d.id && (
            <label className="check" style={{ marginTop: 12 }}>
              <input type="checkbox" checked={d.is_active} onChange={(e) => set({ is_active: e.target.checked })} /> Active
            </label>
          )}
        </div>
        <Preview d={d} onError={setError} />
      </div>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <div className="bar" style={{ marginTop: 14 }}>
        <span className="grow" />
        <button onClick={() => nav("/integrations")}>Cancel</button>
        <button
          className="primary"
          disabled={save.isPending || !d.name.trim() || !d.url.trim() || (!!parsed && !parsed.ok)}
          onClick={() => save.mutate(d)}
        >
          Save
        </button>
      </div>
    </PickerHint.Provider>
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
    if (!d.url.trim()) {
      setShown(null);
      setProblem("");
      return;
    }
    let live = true;
    const t = setTimeout(() => {
      api<Shown>("integrations/preview", { body: JSON.parse(cfg) })
        .then((r) => {
          if (live) {
            setShown(r);
            setProblem("");
          }
        })
        .catch((e: unknown) => {
          if (live) {
            setShown(null);
            setProblem(e instanceof ApiError ? e.message : "The preview could not be made.");
          }
        });
    }, 400);
    return () => {
      live = false;
      clearTimeout(t);
    };
  }, [cfg, d.url]);
  async function find() {
    if (!ref.trim()) {
      setJob(null);
      return;
    }
    const r = asList<Booking>(await api("bookings", { query: { search: ref.trim() } }));
    const hit = r.find((b) => b.booking_id.toLowerCase() === ref.trim().toLowerCase()) ?? r[0];
    if (hit) setJob({ id: hit.id, ref: hit.booking_id });
    else onError(`No booking found for “${ref}”.`);
  }
  return (
    <div className="card request-preview" aria-label="Request preview">
      <h2 className="sub">Preview</h2>
      <div className="bar">
        <input
          aria-label="Preview with booking"
          placeholder="Booking ID (default: latest)"
          value={ref}
          onChange={(e) => setRef(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") void find();
          }}
        />
        <button type="button" onClick={() => void find()}>
          Use
        </button>
      </div>
      {problem && (
        <div className="banner bad" role="alert">
          {problem}
        </div>
      )}
      {shown && (
        <>
          <p className="muted small">
            {shown.sample
              ? "Sample values: no booking exists yet for this form."
              : `Values of ${job?.ref ?? "the latest booking"}. Nothing is sent from here.`}
          </p>
          {shown.broken_refs.length > 0 && (
            <div className="banner warn">Uses {shown.broken_refs.join(", ")}, which the form no longer has. They are sent as empty.</div>
          )}
          <pre
            className="mono"
            data-testid="preview-request"
          >{`${shown.method} ${shown.url}\n${shown.headers.map((h) => `${h.name}: ${h.value}`).join("\n")}${shown.body ? `\n\n${shown.body}` : ""}`}</pre>
        </>
      )}
      {!shown && !problem && <p className="muted">Enter the URL to see the request.</p>}
    </div>
  );
}
