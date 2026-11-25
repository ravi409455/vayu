import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { api, ApiError } from "../../../api/client";
import { useRefresh } from "../../../api/hooks";
import type { FormSummary } from "../../../api/types";
import { slugKey } from "../../../lib/fieldTypes";
import { Field, Modal, useToast } from "../../../ui/kit";
import { keys } from "../../../api/keys";

type Bundle = { schema?: number; form?: { key?: string; name?: string; type?: string; kind?: string } };
type Result = { form: number; draft_version: number; created: { form: boolean; library_items: number }; notes: string[] };

/** Where a bundle can go: into the form it came from (as a new draft), or, for a custom form, as a
 *  brand-new form. Library items that already exist here are never overwritten. */
export function ImportDialog({ bundle, forms, onClose }: { bundle: Bundle; forms: FormSummary[]; onClose: () => void }) {
  const { fail } = useToast();
  const nav = useNavigate();
  const refresh = useRefresh();
  const type = bundle.form?.type ?? (bundle.form?.kind === "inspection" ? "custom" : bundle.form?.kind);
  const system = type === "booking" || type === "start" || type === "end";
  const existing = forms.find((f) => (system ? f.type === type : f.type === "custom" && f.key === bundle.form?.key));
  const [mode, setMode] = useState<"draft" | "new">(existing || system ? "draft" : "draft");
  const [name, setName] = useState(bundle.form?.name ? `${bundle.form.name} (copy)` : "");
  const [key, setKey] = useState(slugKey(`${bundle.form?.key ?? "form"} copy`));
  const [keyEdited, setKeyEdited] = useState(false);
  const [conflicts, setConflicts] = useState<string[]>([]);
  const [done, setDone] = useState<Result | null>(null);
  const asNew = mode === "new" && !system;
  const go = useMutation({
    mutationFn: () => api<Result>("promote/import", { body: bundle, query: asNew ? { as_new_key: key, as_new_name: name } : undefined }),
    onSuccess: (r) => {
      setDone(r);
      void refresh(keys.forms());
    },
    onError: (e) => {
      if (e instanceof ApiError && Array.isArray(e.body.conflicts)) setConflicts(e.body.conflicts as string[]);
      else fail(e);
    },
  });
  if (done) {
    return (
      <Modal
        title="Imported as a draft"
        onClose={onClose}
        actions={
          <>
            <button onClick={onClose}>Close</button>
            <button className="primary" onClick={() => nav(`/forms/${done.form}`)}>
              Open the form
            </button>
          </>
        }
      >
        <p role="status">
          {done.created.form ? "A new form was created." : "A new draft was added to the form."} Nothing is live until you publish it.
        </p>
        {done.notes.length > 0 && (
          <>
            <h3>Differences from the library here</h3>
            <ul className="small">
              {done.notes.map((n, i) => (
                <li key={i}>{n}</li>
              ))}
            </ul>
          </>
        )}
        {done.notes.length === 0 && (
          <p className="muted small">The library here already matched the file, or did not need anything added.</p>
        )}
      </Modal>
    );
  }
  return (
    <Modal
      title={`Import “${bundle.form?.name ?? "form"}”`}
      onClose={onClose}
      actions={
        <>
          <button onClick={onClose}>Cancel</button>
          <button
            className="primary"
            disabled={go.isPending || (asNew && (!name.trim() || !/^[a-z][a-z0-9_]{1,62}$/.test(key)))}
            onClick={() => go.mutate()}
          >
            Import as a draft
          </button>
        </>
      }
    >
      <p className="muted">
        An import never goes live by itself and never overwrites the library. You review the draft and publish it yourself.
      </p>
      {!system && existing && (
        <div role="radiogroup" aria-label="Where to import">
          <label className="check">
            <input type="radio" name="mode" checked={mode === "draft"} onChange={() => setMode("draft")} /> As a new draft of “
            {existing.name}”
          </label>
          <label className="check">
            <input type="radio" name="mode" checked={mode === "new"} onChange={() => setMode("new")} /> As a new form (a copy)
          </label>
        </div>
      )}
      {system && <p>This file replaces the content of the {type} form as a new draft.</p>}
      {!system && !existing && <p>No form with the key “{bundle.form?.key}” exists here, so a new form is created.</p>}
      {asNew && (
        <>
          <Field label="Name of the new form">
            <input
              aria-label="Name of the new form"
              value={name}
              onChange={(e) => {
                setName(e.target.value);
                if (!keyEdited) setKey(slugKey(e.target.value));
              }}
            />
          </Field>
          <Field label="Key" help="Used by the API and reports. It can never change.">
            <input
              aria-label="Key"
              value={key}
              onChange={(e) => {
                setKeyEdited(true);
                setKey(e.target.value);
              }}
            />
          </Field>
        </>
      )}
      {conflicts.length > 0 && (
        <div role="alert" className="error">
          <strong>This file conflicts with what is here:</strong>
          <ul>
            {conflicts.map((c, i) => (
              <li key={i}>{c}</li>
            ))}
          </ul>
        </div>
      )}
    </Modal>
  );
}

/** Copy a custom form under a new name and key (library links, ratings, Key Checks and the PDF template come along). */
export function DuplicateDialog({ form, onClose }: { form: FormSummary; onClose: () => void }) {
  const { fail } = useToast();
  const nav = useNavigate();
  const refresh = useRefresh();
  const [name, setName] = useState(`${form.name} (copy)`);
  const [key, setKey] = useState(slugKey(`${form.key} copy`));
  const [keyEdited, setKeyEdited] = useState(false);
  const dup = useMutation({
    mutationFn: () => api<Result>(`forms/${form.id}/duplicate`, { body: { key, name } }),
    onSuccess: (r) => {
      void refresh(keys.forms());
      nav(`/forms/${r.form}`);
    },
    onError: fail,
  });
  return (
    <Modal
      title={`Duplicate “${form.name}”`}
      onClose={onClose}
      actions={
        <>
          <button onClick={onClose}>Cancel</button>
          <button
            className="primary"
            disabled={dup.isPending || !name.trim() || !/^[a-z][a-z0-9_]{1,62}$/.test(key)}
            onClick={() => dup.mutate()}
          >
            Duplicate
          </button>
        </>
      }
    >
      <p className="muted">
        The copy starts as a draft with the same pages, fields, library links, ratings, Key Checks and PDF template. It is a separate form
        from then on.
      </p>
      <Field label="Name of the copy">
        <input
          aria-label="Name of the copy"
          value={name}
          onChange={(e) => {
            setName(e.target.value);
            if (!keyEdited) setKey(slugKey(e.target.value));
          }}
        />
      </Field>
      <Field label="Key" help="Used by the API and reports. It can never change.">
        <input
          aria-label="Key"
          value={key}
          onChange={(e) => {
            setKeyEdited(true);
            setKey(e.target.value);
          }}
        />
      </Field>
    </Modal>
  );
}
