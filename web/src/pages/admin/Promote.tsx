import { useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { api, ApiError } from "../../api/client";
import { useList } from "../../api/hooks";
import type { FormSummary } from "../../api/types";
import { Pill, useToast, PageHeader } from "../../ui/kit";
import { keys } from "../../api/keys";

type ImportResult = { form: number; draft_version: number; created: { form: boolean; master_list_items: number; library_items: number }; notes: string[] };

export function Promote() {
  const { say, fail } = useToast();
  const forms = useList<FormSummary>(keys.forms(), "forms");
  const file = useRef<HTMLInputElement>(null);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [conflicts, setConflicts] = useState<string[]>([]);
  const imp = useMutation({
    mutationFn: async (bundle: unknown) => api<ImportResult>("promote/import", { body: bundle }),
    onSuccess: (r) => { setConflicts([]); setResult(r); say("Imported as a draft."); },
    onError: (e) => {
      setResult(null);
      if (e instanceof ApiError && Array.isArray(e.body.conflicts)) setConflicts(e.body.conflicts as string[]);
      else fail(e);
    },
  });
  async function onFile(f: File | undefined) {
    if (!f) return;
    try { imp.mutate(JSON.parse(await f.text())); } catch { fail(new Error("That file is not a Vayu bundle.")); }
  }
  return (
    <>
      <PageHeader title="Promote forms" subtitle="Move a tested form from staging to production as a file." />
      <div className="grid2">
        <div className="card">
          <h2>Export from this server</h2>
          <table className="rows"><tbody>{(forms.data ?? []).filter((f) => f.published_version).map((f) => (
            <tr key={f.id}><td>{f.name} <Pill tone="ok">v{f.published_version!.number}</Pill></td>
              <td style={{ textAlign: "right" }}><a className="btn sm" href={`/api/v1/promote/export?version=${f.published_version!.id}`} download={`${f.key}-v${f.published_version!.number}.json`}>Download bundle</a></td></tr>))}</tbody></table>
        </div>
        <div className="card">
          <h2>Import into this server</h2>
          <input ref={file} type="file" accept="application/json,.json" aria-label="Bundle file" hidden onChange={(e) => { void onFile(e.target.files?.[0]); e.target.value = ""; }} />
          <button type="button" className="drop-zone" style={{ width: "100%", background: "none" }} onClick={() => file.current?.click()}
            onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); void onFile(e.dataTransfer.files?.[0]); }}>
            <strong style={{ color: "var(--ink)" }}>Choose a bundle file</strong><span className="small">or drop it here. It arrives as a draft; nothing goes live until you publish.</span></button>
          {conflicts.length > 0 && <><h3 className="error">Nothing was imported</h3>{conflicts.map((c, i) => <p key={i} className="error" role="alert">{c}</p>)}</>}
          {result && <div className="ok" role="status"><p>Draft created{result.created.form ? " (new form)" : ""}. <a href={`/forms/${result.form}`}>Open it</a></p>
            <p className="small">{result.created.library_items} library items and {result.created.master_list_items} list items added.</p>
            {result.notes.map((n, i) => <p key={i} className="small muted">{n}</p>)}</div>}
        </div>
      </div>
    </>
  );
}
