import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { api } from "../../api/client";
import { useList, useRefresh } from "../../api/hooks";
import type { ApiKeyRow, FormSummary } from "../../api/types";
import { Field, Modal, Pill, useToast, when, PageHeader } from "../../ui/kit";

/** "a, b" -> ["a", "b"]; "*" -> ["*"] (every field, only when typed on purpose);
 *  empty means no access at all (fail closed). */
export function parseFields(s: string): string[] {
  const t = s.trim();
  if (t === "*") return ["*"];
  return t.split(",").map((x) => x.trim()).filter((x) => x && x !== "*");
}

export function ApiKeys() {
  const { say, fail } = useToast();
  const refresh = useRefresh();
  const keys = useList<ApiKeyRow>("api-keys", "api-keys");
  const forms = useList<FormSummary>("forms", "forms");
  const eligible = (forms.data ?? []).filter((f) => f.type === "booking" || f.type === "custom");
  const [edit, setEdit] = useState<{ id?: string; name: string; allow_delete: boolean; scope: Record<string, string> } | null>(null);
  const [shown, setShown] = useState<string | null>(null);
  const save = useMutation({
    mutationFn: (e: NonNullable<typeof edit>) => {
      const forms: Record<string, string[]> = {};
      for (const [k, v] of Object.entries(e.scope)) {
        const fields = parseFields(v);
        if (fields.length > 0) forms[k] = fields;      // no fields listed = the form is left out
      }
      const body = { name: e.name, allow_delete: e.allow_delete, scope: { forms } };
      return e.id ? api<ApiKeyRow>(`api-keys/${e.id}`, { method: "PATCH", body }) : api<ApiKeyRow>("api-keys", { body });
    },
    onSuccess: (r) => { setEdit(null); if (r.key) setShown(r.key); else say("Saved."); void refresh("api-keys"); },
    onError: fail,
  });
  const revoke = useMutation({ mutationFn: (k: ApiKeyRow) => api(`api-keys/${k.id}/revoke`, { body: {} }), onSuccess: () => { say("Revoked. It stopped working immediately."); void refresh("api-keys"); }, onError: fail });
  return (
    <>
      <PageHeader title="API keys" subtitle={<>Let another system read and write bookings. API docs: <a href="/api/v1/docs" target="_blank" rel="noreferrer">/api/v1/docs</a></>}
        tip="Each key only sees the forms and fields you give it. A key is shown once when created and can be revoked instantly. Deleting bookings is off unless you turn it on for that key.">
        <button className="primary" onClick={() => setEdit({ name: "", allow_delete: false, scope: {} })}>New key</button></PageHeader>
      <table><thead><tr><th>Name</th><th>Key starts with</th><th>Can access</th><th>Last used</th><th /></tr></thead>
        <tbody>{(keys.data ?? []).map((k) => (
          <tr key={k.id}><td>{k.name} {k.revoked_at && <Pill tone="bad">Revoked</Pill>} {k.allow_delete && <Pill tone="warn">Can delete</Pill>}</td>
            <td className="mono">vk_{k.prefix}_…</td>
            <td className="small">{Object.entries(k.scope.forms).map(([f, v]) => `${f}: ${v.join(", ")}`).join(" · ")}</td>
            <td>{when(k.last_used_at) || "never"}</td>
            <td style={{ textAlign: "right" }}>{!k.revoked_at && <>
              <button className="link" onClick={() => setEdit({ id: k.id, name: k.name, allow_delete: k.allow_delete, scope: Object.fromEntries(Object.entries(k.scope.forms).map(([f, v]) => [f, v.join(", ")])) })}>Edit</button>
              <button className="link" onClick={() => confirm(`Revoke ${k.name}? It stops working immediately.`) && revoke.mutate(k)}>Revoke</button></>}</td></tr>))}</tbody></table>
      {edit && (
        <Modal title={edit.id ? "Edit API key" : "New API key"} onClose={() => setEdit(null)}
          actions={<><button onClick={() => setEdit(null)}>Cancel</button><button className="primary" disabled={!edit.name || Object.values(edit.scope).every((v) => parseFields(v).length === 0)} onClick={() => save.mutate(edit)}>Save</button></>}>
          <Field label="Name"><input value={edit.name} onChange={(e) => setEdit({ ...edit, name: e.target.value })} /></Field>
          <h3>Forms and fields</h3>
          <p className="muted small">Type <code>*</code> for every field, or field keys separated by commas. Leave empty for no access.</p>
          {eligible.map((f) => (
            <Field key={f.id} label={`${f.name} (${f.key})`}><input aria-label={`Fields of ${f.key}`} placeholder="no access (type * for every field)" value={edit.scope[f.key] ?? ""} onChange={(e) => setEdit({ ...edit, scope: { ...edit.scope, [f.key]: e.target.value } })} /></Field>))}
          <label className="check"><input type="checkbox" checked={edit.allow_delete} onChange={(e) => setEdit({ ...edit, allow_delete: e.target.checked })} /> Allow deleting bookings (audited)</label>
        </Modal>
      )}
      {shown && <Modal title="Your new API key" onClose={() => setShown(null)}><p>Copy it now. It is shown only once and cannot be recovered.</p><pre className="mono card" data-testid="api-key">{shown}</pre></Modal>}
    </>
  );
}
