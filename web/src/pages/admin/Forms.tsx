import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { api, type Page } from "../../api/client";
import { asList, useList, useRefresh } from "../../api/hooks";
import type { FormSummary, MasterListItem } from "../../api/types";
import { useAuth } from "../../auth";
import { Field, Modal, Pill, useToast } from "../../ui/kit";
import { slugKey } from "../../lib/fieldTypes";
import { useQuery } from "@tanstack/react-query";

const KIND: Record<string, string> = { booking: "Booking form", ops: "Check-in & wrap-up form", inspection: "Inspection form" };

export function Forms() {
  const { can } = useAuth();
  const { fail } = useToast();
  const nav = useNavigate();
  const refresh = useRefresh();
  const forms = useList<FormSummary>("forms", "forms");
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ name: "", key: "", kind: "inspection", inspection_type: "" });
  const types = useQuery({ queryKey: ["types"], queryFn: async () => asList<MasterListItem>(await api<Page<MasterListItem>>("master-lists/inspection_type/items")) });
  const create = useMutation({
    mutationFn: () => api<FormSummary>("forms", { body: { ...f, inspection_type: f.kind === "inspection" ? f.inspection_type : "" } }),
    onSuccess: (r) => { void refresh("forms"); nav(`/forms/${r.id}`); },
    onError: fail,
  });
  return (
    <>
      <div className="bar"><h1 className="grow">Forms</h1>
        {can("forms.edit") && <button className="primary" onClick={() => setOpen(true)}>New form</button>}</div>
      <table>
        <thead><tr><th>Name</th><th>Kind</th><th>Type</th><th>Live version</th><th>Draft</th></tr></thead>
        <tbody>{(forms.data ?? []).map((x) => (
          <tr key={x.id}>
            <td><Link to={`/forms/${x.id}`}>{x.name}</Link> <span className="muted mono">{x.key}</span></td>
            <td>{KIND[x.kind]}</td><td>{x.inspection_type || "—"}</td>
            <td>{x.published_version ? <Pill tone="ok">v{x.published_version.number}</Pill> : <Pill tone="warn">Not published</Pill>}</td>
            <td>{x.draft_version ? <Pill tone="info">v{x.draft_version.number} draft</Pill> : "—"}</td>
          </tr>))}</tbody>
      </table>
      {open && (
        <Modal title="New form" onClose={() => setOpen(false)}
          actions={<><button onClick={() => setOpen(false)}>Cancel</button><button className="primary" disabled={!f.name || !f.key || (f.kind === "inspection" && !f.inspection_type)} onClick={() => create.mutate()}>Create</button></>}>
          <Field label="Kind"><select aria-label="Kind" value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })}>
            <option value="inspection">Inspection form (one per inspection type)</option>
            <option value="booking">Booking form (only one)</option>
            <option value="ops">Check-in &amp; wrap-up form (only one)</option></select></Field>
          <Field label="Name"><input aria-label="Name" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value, key: f.key || slugKey(e.target.value) })} /></Field>
          <Field label="Key" help="Used by the API and reports. It can never change."><input value={f.key} onChange={(e) => setF({ ...f, key: e.target.value })} /></Field>
          {f.kind === "inspection" && (
            <Field label="Inspection type"><select aria-label="Inspection type" value={f.inspection_type} onChange={(e) => setF({ ...f, inspection_type: e.target.value })}>
              <option value="">Choose…</option>{(types.data ?? []).filter((t) => !t.archived).map((t) => <option key={t.key} value={t.key}>{t.label}</option>)}</select></Field>
          )}
        </Modal>
      )}
    </>
  );
}
