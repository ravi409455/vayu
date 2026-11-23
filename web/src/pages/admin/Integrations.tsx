import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { api, type Page } from "../../api/client";
import { useList, useRefresh } from "../../api/hooks";
import type { Delivery, FormSummary, Integration } from "../../api/types";
import { Field, Modal, Pill, Tabs, useToast, when, PageHeader } from "../../ui/kit";

const EVENT_LABEL: Record<string, string> = {
  "booking.created": "Booking created", "booking.updated": "Booking updated (incl. assignment and stage)", "booking.deleted": "Booking deleted",
  "inspection.started": "Inspection started", "inspection.submitted": "Inspection submitted", "media.completed": "All media verified (Completed)",
  "pdf.ready": "PDF ready (also on regenerate)", "alert.conflict": "Conflict alert", "alert.stuck_upload": "Stuck upload alert",
};
const blank = (form: number): Partial<Integration> => ({ form, name: "", url: "", events: ["pdf.ready"], include_data: true, include_pdf: true, include_image_zip: false, include_video_zip: false, fields: [], template: "" });

export function tone(status: string): "ok" | "warn" | "bad" | "info" {
  return status === "success" ? "ok" : status === "failed" ? "bad" : status === "retrying" ? "warn" : "info";
}

export function Integrations() {
  const { say, fail } = useToast();
  const refresh = useRefresh();
  const list = useList<Integration>("integrations", "integrations");
  const forms = useList<FormSummary>("forms", "forms");
  const events = useQuery({ queryKey: ["events"], queryFn: () => api<string[]>("integrations/events") });
  const [edit, setEdit] = useState<Partial<Integration> | null>(null);
  const [secret, setSecret] = useState<string | null>(null);
  const [log, setLog] = useState<Integration | null>(null);
  const eligible = (forms.data ?? []).filter((f) => f.type === "booking" || f.type === "custom");

  const save = useMutation({
    mutationFn: (i: Partial<Integration>) => i.id ? api<Integration>(`integrations/${i.id}`, { method: "PATCH", body: i }) : api<Integration>("integrations", { body: i }),
    onSuccess: (r) => { setEdit(null); if (r.secret) setSecret(r.secret); else say("Saved."); void refresh("integrations"); },
    onError: fail,
  });
  const test = useMutation({
    mutationFn: (i: Integration) => api<Delivery>(`integrations/${i.id}/test`, { body: {} }),
    onSuccess: (d) => say(d.status === "success" ? `Test sent: ${d.response_status}` : `Test failed: ${d.error}`, d.status !== "success"),
    onError: fail,
  });
  const rotate = useMutation({
    mutationFn: (i: Integration) => api<Integration>(`integrations/${i.id}/rotate-secret`, { body: {} }),
    onSuccess: (r) => setSecret(r.secret ?? null),
    onError: fail,
  });
  const remove = useMutation({ mutationFn: (i: Integration) => api(`integrations/${i.id}`, { method: "DELETE" }), onSuccess: () => void refresh("integrations"), onError: fail });

  return (
    <>
      <PageHeader title="Integrations" subtitle="Send events to other systems the moment they happen."
        tip="A webhook posts a message to a web address when something happens (a booking is created, a PDF is ready...). Every message is signed with a secret so the receiver can trust it. An integration on the booking form gets booking events; on an inspection form it gets every event for that inspection type.">
        <button className="primary" disabled={eligible.length === 0} onClick={() => setEdit(blank(eligible[0]!.id))}>New integration</button></PageHeader>
      <table><thead><tr><th>Name</th><th>Form</th><th>URL</th><th>Events</th><th /></tr></thead>
        <tbody>{(list.data ?? []).map((i) => (
          <tr key={i.id}>
            <td>{i.name} {!i.is_active && <Pill tone="warn">Off</Pill>}</td><td className="mono">{i.form_key}</td><td className="mono small">{i.url}</td><td className="small">{i.events.join(", ")}</td>
            <td style={{ textAlign: "right" }}>
              <button className="link" onClick={() => setEdit(i)}>Edit</button><button className="link" onClick={() => test.mutate(i)}>Test</button>
              <button className="link" onClick={() => setLog(i)}>Deliveries</button><button className="link" onClick={() => rotate.mutate(i)}>New secret</button>
              <button className="link" onClick={() => confirm(`Delete ${i.name}?`) && remove.mutate(i)}>Delete</button></td></tr>))}</tbody></table>
      {edit && <Editor value={edit} onChange={setEdit} events={events.data ?? []} forms={eligible} onSave={() => save.mutate(edit)} onClose={() => setEdit(null)} fail={fail} />}
      {secret && <Modal title="Signing secret" onClose={() => setSecret(null)}><p>Copy it now. It is shown only once.</p><pre className="mono card" data-testid="secret">{secret}</pre></Modal>}
      {log && <DeliveryLog integration={log} onClose={() => setLog(null)} />}
    </>
  );
}

function Editor({ value, onChange, events, forms, onSave, onClose, fail }: { value: Partial<Integration>; onChange: (v: Partial<Integration>) => void; events: string[]; forms: FormSummary[]; onSave: () => void; onClose: () => void; fail: (e: unknown) => void }) {
  const [sample, setSample] = useState("");
  const set = (p: Partial<Integration>) => onChange({ ...value, ...p });
  async function render() {
    try { setSample((await api<{ rendered: string }>("integrations/render-sample", { body: { form: value.form, template: value.template ?? "" } })).rendered); } catch (e) { fail(e); setSample(""); }
  }
  const toggle = (e: string) => set({ events: value.events?.includes(e) ? value.events.filter((x) => x !== e) : [...(value.events ?? []), e] });
  return (
    <Modal title={value.id ? "Edit integration" : "New integration"} onClose={onClose}
      actions={<><button onClick={onClose}>Cancel</button><button className="primary" disabled={!value.name || !value.url || !(value.events?.length)} onClick={onSave}>Save</button></>}>
      <Field label="Name"><input aria-label="Name" value={value.name ?? ""} onChange={(e) => set({ name: e.target.value })} /></Field>
      <Field label="Form"><select aria-label="Form" value={value.form} disabled={!!value.id} onChange={(e) => set({ form: Number(e.target.value) })}>{forms.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}</select></Field>
      <Field label="Webhook URL" help="Must be https and reachable from the internet."><input aria-label="Webhook URL" value={value.url ?? ""} onChange={(e) => set({ url: e.target.value })} /></Field>
      <h3>Send when…</h3>
      {events.map((e) => <label className="check" key={e}><input type="checkbox" checked={!!value.events?.includes(e)} onChange={() => toggle(e)} /> {EVENT_LABEL[e] ?? e}</label>)}
      <h3>What to include</h3>
      <label className="check"><input type="checkbox" checked={!!value.include_data} onChange={(e) => set({ include_data: e.target.checked })} /> Full data (booking and inspection answers)</label>
      <label className="check"><input type="checkbox" checked={!!value.include_pdf} onChange={(e) => set({ include_pdf: e.target.checked })} /> PDF link (valid 7 days)</label>
      <label className="check"><input type="checkbox" checked={!!value.include_image_zip} onChange={(e) => set({ include_image_zip: e.target.checked })} /> Image ZIP link</label>
      <label className="check"><input type="checkbox" checked={!!value.include_video_zip} onChange={(e) => set({ include_video_zip: e.target.checked })} /> Video ZIP link</label>
      <Field label="Only these field keys (empty = all)" help="Comma separated."><input value={(value.fields ?? []).join(", ")} onChange={(e) => set({ fields: e.target.value.split(",").map((x) => x.trim()).filter(Boolean) })} /></Field>
      <Field label="Custom body template (optional)" help="Use {{ field.customer_name }}, {{ booking.booking_id }}, {{ event }}, {{ pdf_url }}. Leave empty to send the standard JSON.">
        <textarea value={value.template ?? ""} onChange={(e) => set({ template: e.target.value })} /></Field>
      <button onClick={render}>Preview with a real booking</button>
      {sample && <pre className="mono card" aria-label="Template preview">{sample}</pre>}
      {value.id && <label className="check"><input type="checkbox" checked={value.is_active !== false} onChange={(e) => set({ is_active: e.target.checked })} /> Active</label>}
    </Modal>
  );
}

function DeliveryLog({ integration, onClose }: { integration: Integration; onClose: () => void }) {
  const { say, fail } = useToast();
  const refresh = useRefresh();
  const [status, setStatus] = useState("");
  const q = useQuery({ queryKey: ["deliveries", integration.id, status], queryFn: () => api<Page<Delivery>>(`integrations/${integration.id}/deliveries`, { query: { status } }) });
  const resend = useMutation({ mutationFn: (d: Delivery) => api(`deliveries/${d.id}/resend`, { body: {} }), onSuccess: () => { say("Re-sent."); void refresh("deliveries"); }, onError: fail });
  return (
    <Modal title={`Deliveries: ${integration.name}`} onClose={onClose}>
      <select aria-label="Status" value={status} onChange={(e) => setStatus(e.target.value)} style={{ maxWidth: 180 }}>
        <option value="">All</option><option value="success">Delivered</option><option value="retrying">Retrying</option><option value="failed">Failed</option></select>
      <table><thead><tr><th>When</th><th>Event</th><th>Booking</th><th>Result</th><th /></tr></thead>
        <tbody>{(q.data?.results ?? []).map((d) => (
          <tr key={d.id}><td>{when(d.created_at)}</td><td className="small">{d.event}</td><td>{d.booking_id}</td>
            <td><Pill tone={tone(d.status)}>{d.status}</Pill> <span className="small muted">{d.response_status ?? ""} {d.error} {d.attempts > 1 ? `· ${d.attempts} tries` : ""}</span></td>
            <td><button className="link" onClick={() => resend.mutate(d)}>Re-send</button></td></tr>))}</tbody></table>
      {(q.data?.results ?? []).length === 0 && <p className="muted">Nothing here yet.</p>}
    </Modal>
  );
}
