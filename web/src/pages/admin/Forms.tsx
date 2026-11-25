import { useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../../api/client";
import { useList, useRefresh } from "../../api/hooks";
import type { FormSummary, FormType } from "../../api/types";
import { useAuth } from "../../auth";
import { Empty, Field, LoadError, Modal, PageHeader, Pill, useToast } from "../../ui/kit";
import { slugKey } from "../../lib/fieldTypes";
import { ImportDialog } from "./builder/ImportForm";
import { keys } from "../../api/keys";

export const TYPE_LABEL: Record<FormType, string> = { booking: "Booking form", start: "Start form", end: "End form", custom: "Custom form" };
const SYSTEM_ORDER: FormType[] = ["booking", "start", "end"];

function Versions({ x }: { x: FormSummary }) {
  return (<>
    <td>{x.published_version ? <Pill tone="ok">v{x.published_version.number}</Pill> : <Pill tone="warn">Not published</Pill>}</td>
    <td>{x.draft_version ? <Pill tone="warn">Draft v{x.draft_version.number}</Pill> : <span className="muted">—</span>}</td>
  </>);
}

export function Forms() {
  const { can } = useAuth();
  const { fail } = useToast();
  const nav = useNavigate();
  const refresh = useRefresh();
  const forms = useList<FormSummary>(keys.forms(), "forms");
  const [open, setOpen] = useState(false);
  const file = useRef<HTMLInputElement>(null);
  const [bundle, setBundle] = useState<unknown>(null);
  const [f, setF] = useState({ name: "", key: "" });
  const [keyEdited, setKeyEdited] = useState(false);     // until the Admin types a key, it follows the name
  const create = useMutation({
    mutationFn: () => api<FormSummary>("forms", { body: f }),
    onSuccess: (r) => { void refresh(keys.forms()); nav(`/forms/${r.id}`); },
    onError: fail,
  });
  const system = SYSTEM_ORDER.map((t) => (forms.data ?? []).find((x) => x.type === t)).filter((x): x is FormSummary => !!x);
  const custom = (forms.data ?? []).filter((x) => x.type === "custom");
  return (
    <>
      <PageHeader title="Forms">
        {can("forms.promote") && <button onClick={() => file.current?.click()}>Import</button>}
        {can("forms.edit") && <button className="primary" onClick={() => setOpen(true)}>New custom form</button>}</PageHeader>
      {forms.isError && <LoadError error={forms.error} what="forms" onRetry={forms.refetch} />}
      <input ref={file} type="file" accept="application/json,.json" aria-label="Form file to import" hidden onChange={async (e) => {
        const f = e.target.files?.[0];
        e.target.value = "";
        if (!f) return;
        try { setBundle(JSON.parse(await f.text())); } catch { fail(new Error("That file is not a Vayu form file.")); }
      }} />
      <section className="table-card" style={{ marginBottom: 16 }}>
        <div className="table-title stacked"><h2>System forms</h2><p>Always there: the booking, and the start and end of every inspection.</p></div>
        <table className="rows" aria-label="System forms">
          <thead><tr><th>Name</th><th>Live version</th><th>Draft</th></tr></thead>
          <tbody>{system.map((x) => (
            <tr key={x.id} className="click" onClick={() => nav(`/forms/${x.id}`)}>
              {/* the Admin may rename a system form: the muted label still says which one it is */}
              <td><Link className="cell-main" to={`/forms/${x.id}`} onClick={(e) => e.stopPropagation()}>{x.name}</Link>{" "}
                <span className="muted small">{TYPE_LABEL[x.type]}</span></td>
              <Versions x={x} />
            </tr>))}</tbody>
        </table>
      </section>
      <section className="table-card">
        <div className="table-title stacked"><h2>Inspection forms</h2><p>What experts fill in, one per kind of inspection.</p></div>
        <table className="rows" aria-label="Custom forms">
          <thead><tr><th>Name</th><th>Live version</th><th>Draft</th></tr></thead>
          <tbody>{custom.map((x) => (
            <tr key={x.id} className="click" onClick={() => nav(`/forms/${x.id}`)}>
              <td><Link className="cell-main" to={`/forms/${x.id}`} onClick={(e) => e.stopPropagation()}>{x.name}</Link>{!x.is_active && <> <Pill>Switched off</Pill></>}</td>
              <Versions x={x} />
            </tr>))}</tbody>
        </table>
        {custom.length === 0 && <Empty title="No inspection forms yet">Create one for each kind of inspection.</Empty>}
      </section>
      {bundle !== null && <ImportDialog bundle={bundle as never} forms={forms.data ?? []} onClose={() => setBundle(null)} />}
      {open && (
        <Modal title="New custom form" onClose={() => setOpen(false)}
          actions={<><button onClick={() => setOpen(false)}>Cancel</button><button className="primary" disabled={!f.name || !f.key} onClick={() => create.mutate()}>Create</button></>}>
          <Field label="Name" help="This is what Ops pick from when they create a booking."><input aria-label="Name" value={f.name} onChange={(e) => setF({ name: e.target.value, key: keyEdited ? f.key : slugKey(e.target.value) })} /></Field>
          <Field label="Key" help="Used by the API and reports. It can never change."><input aria-label="Key" value={f.key} onChange={(e) => { setKeyEdited(true); setF({ ...f, key: e.target.value }); }} /></Field>
        </Modal>
      )}
    </>
  );
}
