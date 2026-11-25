import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { api, type Page } from "../../api/client";
import { useList, useRefresh } from "../../api/hooks";
import type { Delivery, FormSummary, Integration } from "../../api/types";
import { eventWord } from "../../lib/integrationDef";
import { Confirm, Empty, LoadError, Modal, PageHeader, Pill, useToast, when } from "../../ui/kit";
import { MoreMenu } from "../../ui/Menu";

export { eventWord };
const ERROR_WORD: Record<string, string> = {
  integration_disabled: "Integration switched off", request_failed: "The request could not be built", missing_path_value: "A value in the URL path was empty",
  timeout: "No answer in time", blocked_address: "Address not allowed (private network)", connection_error: "Could not connect",
  retries_exhausted: "Gave up after the last retry",
};
/** A delivery error as words ("http_503" -> "Server answered 503"). */
export const errorWord = (e: string) => ERROR_WORD[e] ?? (/^http_\d+$/.test(e) ? `Server answered ${e.slice(5)}` : e);
const STATUS_WORD: Record<string, string> = { success: "Delivered", failed: "Failed", retrying: "Retrying", pending: "Waiting" };

export function tone(status: string): "ok" | "warn" | "bad" | "info" {
  return status === "success" ? "ok" : status === "failed" ? "bad" : status === "retrying" ? "warn" : "info";
}

export function Integrations() {
  const { say, fail } = useToast();
  const refresh = useRefresh();
  const nav = useNavigate();
  const list = useList<Integration>("integrations", "integrations");
  const forms = useList<FormSummary>("forms", "forms");
  const [log, setLog] = useState<Integration | null>(null);
  const [deleting, setDeleting] = useState<Integration | null>(null);
  const eligible = (forms.data ?? []).filter((f) => f.type === "booking" || f.type === "custom");

  const test = useMutation({
    mutationFn: (i: Integration) => api<Delivery>(`integrations/${i.id}/test`, { body: {} }),
    onSuccess: (d) => say(d.status === "success" ? `Test sent: ${d.response_status}` : `Test failed: ${errorWord(d.error)}`, d.status !== "success"),
    onError: fail,
  });
  const remove = useMutation({ mutationFn: (i: Integration) => api(`integrations/${i.id}`, { method: "DELETE" }), onSuccess: () => void refresh("integrations"), onError: fail });

  return (
    <>
      <PageHeader title="Integrations" subtitle="Send an event to another system the moment it happens: one event, one request you design.">
        <button className="primary" disabled={eligible.length === 0} onClick={() => nav("/integrations/new")}>New integration</button></PageHeader>
      {list.isError && <LoadError error={list.error} what="integrations" onRetry={list.refetch} />}
      {list.data && list.data.length === 0 ? <Empty title="No integrations yet">Send bookings, PDFs and changes to another system the moment they happen.</Empty> :
      <div className="table-card"><table className="rows"><thead><tr><th>Name</th><th>Form</th><th>Sends when</th><th><span className="sr-only">Actions</span></th></tr></thead>
        <tbody>{(list.data ?? []).map((i) => (
          <tr key={i.id}>
            <td><span className="cell-main">{i.name}</span> {!i.is_active && <Pill tone="warn">Off</Pill>}
              {i.broken_refs.length > 0 && <> <Pill tone="warn">{`Uses ${i.broken_refs.length} field${i.broken_refs.length === 1 ? "" : "s"} that no longer exist${i.broken_refs.length === 1 ? "s" : ""}`}</Pill></>}
              <div className="cell-sub mono ellipsis" style={{ maxWidth: 360 }} title={i.url}>{i.method} {i.url}</div></td>
            <td>{(forms.data ?? []).find((f) => f.id === i.form)?.name ?? i.form_key}</td>
            <td><span className="chip">{eventWord(i.event)}</span></td>
            <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
              <button className="sm" onClick={() => test.mutate(i)}>Test</button>{" "}
              <MoreMenu label={`Actions for ${i.name}`} items={[
                { label: "Edit", onClick: () => nav(`/integrations/${i.id}`) },
                { label: "Duplicate", onClick: () => nav(`/integrations/new?copy=${i.id}`) },
                { label: "Deliveries", onClick: () => setLog(i) },
                { label: "Delete…", danger: true, onClick: () => setDeleting(i) },
              ]} /></td></tr>))}</tbody></table></div>}
      {deleting && <Confirm title={`Delete ${deleting.name}?`} danger confirmLabel="Delete integration" busy={remove.isPending} onCancel={() => setDeleting(null)}
        onConfirm={() => remove.mutate(deleting, { onSettled: () => setDeleting(null) })}><p>It stops sending at once. Its delivery log is removed too.</p></Confirm>}
      {log && <DeliveryLog integration={log} onClose={() => setLog(null)} />}
    </>
  );
}

function DeliveryLog({ integration, onClose }: { integration: Integration; onClose: () => void }) {
  const { say, fail } = useToast();
  const refresh = useRefresh();
  const [status, setStatus] = useState("");
  const q = useQuery({ queryKey: ["deliveries", integration.id, status], queryFn: ({ signal }) => api<Page<Delivery>>(`integrations/${integration.id}/deliveries`, { query: { status }, signal }) });
  const resend = useMutation({ mutationFn: (d: Delivery) => api(`deliveries/${d.id}/resend`, { body: {} }), onSuccess: () => { say("Re-sent."); void refresh("deliveries"); }, onError: fail });
  return (
    <Modal wide title={`Deliveries: ${integration.name}`} onClose={onClose}>
      <div className="bar">
        <div className="seg" role="group" aria-label="Status">
          {([["", "All"], ["success", "Delivered"], ["retrying", "Retrying"], ["failed", "Failed"]] as const).map(([k, l]) => <button key={k} aria-pressed={status === k} onClick={() => setStatus(k)}>{l}</button>)}
        </div>
        <span className="grow muted small" style={{ textAlign: "right" }}>{q.data ? `${q.data.count} message${q.data.count === 1 ? "" : "s"}` : ""}</span>
      </div>
      {q.data && q.data.results.length > 0 && (
        <div className="table-card"><table className="rows"><thead><tr><th>When</th><th>Event</th><th>Booking</th><th>Result</th><th><span className="sr-only">Actions</span></th></tr></thead>
          <tbody>{q.data.results.map((d) => (
            <tr key={d.id}><td className="nowrap">{when(d.created_at)}</td><td>{eventWord(d.event)}</td><td>{d.booking_id || "—"}</td>
              <td><Pill tone={tone(d.status)}>{STATUS_WORD[d.status] ?? d.status}</Pill>
                <div className="cell-sub">{[d.response_status && !/^http_/.test(d.error) ? `HTTP ${d.response_status}` : "", d.error ? errorWord(d.error) : "", d.attempts > 1 ? `${d.attempts} tries` : "", d.status === "retrying" && d.next_retry_at ? `next try ${when(d.next_retry_at)}` : ""].filter(Boolean).join(" · ")}</div></td>
              <td style={{ textAlign: "right" }}><button className="sm" onClick={() => resend.mutate(d)}>Re-send</button></td></tr>))}</tbody></table></div>)}
      {q.data && q.data.results.length === 0 && <Empty>{status ? "No deliveries with this result." : "No deliveries yet. Use Test to send one."}</Empty>}
    </Modal>
  );
}
