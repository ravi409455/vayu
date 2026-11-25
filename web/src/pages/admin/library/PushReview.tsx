import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { api, ApiError } from "../../../api/client";
import { Modal, Pill, useToast } from "../../../ui/kit";
import { keys } from "../../../api/keys";

export type PushChange = { target: string; setting: string; from: unknown; to: unknown };
export type PushForm = {
  form: string;
  type: string;
  state: "draft" | "published_only";
  changes: PushChange[];
  problems: { form: string; path: string; code: string; message: string }[];
};
export type PushReport = { forms: PushForm[]; skipped: { form: string; reason: string }[]; blocked: boolean };

const show = (v: unknown) => (v === null || v === undefined ? "nothing" : typeof v === "object" ? JSON.stringify(v) : String(v));
export const describeChange = (c: PushChange) =>
  c.setting === "added"
    ? `${c.target}: added`
    : c.setting === "removed"
      ? `${c.target}: removed`
      : `${c.target}: ${c.setting.replace(/_/g, " ")} ${show(c.from)} → ${show(c.to)}`;

/** What "Save and update everywhere" would do, form by form, before anything is changed. The push
 *  button stays off until nothing is wrong; publishing automatically is off and needs a confirm. */
export function PushReview({
  itemId,
  itemName,
  revision,
  onClose,
  onDone,
}: {
  itemId: number;
  itemName: string;
  revision: number;
  onClose: () => void;
  onDone: () => void;
}) {
  const { fail } = useToast();
  const [publish, setPublish] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [result, setResult] = useState<PushReport | null>(null);
  const preview = useQuery({
    queryKey: keys.pushPreview(itemId, revision),
    queryFn: ({ signal }) => api<PushReport>(`library/${itemId}/push-preview`, { method: "POST", signal }),
  });
  const run = useMutation({
    mutationFn: () => api<PushReport>(`library/${itemId}/push`, { body: { revision, publish, confirm: publish && confirmed } }),
    onSuccess: (r) => {
      setResult(r);
      onDone();
    },
    onError: (e) => {
      if (e instanceof ApiError && e.code === "PUSH_BLOCKED") void preview.refetch();
      else fail(e);
    },
  });
  const r = preview.data;
  const count = r?.forms.length ?? 0;

  if (result) {
    return (
      <Modal
        title="Updated everywhere"
        onClose={onClose}
        actions={
          <button className="primary" onClick={onClose}>
            Close
          </button>
        }
      >
        <p role="status">
          {result.forms.length === 0
            ? "Every form was already up to date."
            : `${result.forms.length} form${result.forms.length === 1 ? "" : "s"} updated${publish ? " and published" : ": each has a draft ready to publish"}.`}
        </p>
        <ul>
          {result.forms.map((f) => (
            <li key={f.form}>
              <Link to="/forms">{f.form}</Link> <Pill tone={publish ? "ok" : "info"}>{publish ? "live" : "draft"}</Pill>
            </li>
          ))}
        </ul>
      </Modal>
    );
  }
  return (
    <Modal
      title={`Update “${itemName}” everywhere`}
      onClose={onClose}
      wide
      actions={
        <>
          <button onClick={onClose}>Cancel</button>
          <button
            className="primary"
            disabled={!r || r.blocked || count === 0 || run.isPending || (publish && !confirmed)}
            onClick={() => run.mutate()}
          >
            {count === 0
              ? "Nothing to update"
              : publish
                ? `Update and publish ${count} form${count === 1 ? "" : "s"}`
                : `Update ${count} form${count === 1 ? "" : "s"}`}
          </button>
        </>
      }
    >
      {preview.isLoading && <p className="muted">Checking every form…</p>}
      {r && (
        <>
          <p className="muted">
            The library wins over what a form has set for itself. Here is everything that would change. Nothing is saved until you press the
            button.
          </p>
          {r.forms.length === 0 && <p>Every form that uses this item is already up to date.</p>}
          {r.forms.map((f) => (
            <div className="card" key={f.form} style={{ marginBottom: 10 }}>
              <div className="bar">
                <strong>{f.form}</strong>
                <Pill tone={f.state === "draft" ? "info" : "warn"}>
                  {f.state === "draft" ? "its open draft is updated" : "a new draft is made (the live version stays)"}
                </Pill>
              </div>
              {f.changes.length === 0 ? (
                <p className="muted small">Only the item's revision number moves.</p>
              ) : (
                <ul className="small">
                  {f.changes.map((c, i) => (
                    <li key={i}>{describeChange(c)}</li>
                  ))}
                </ul>
              )}
              {f.problems.map((p, i) => (
                <p key={i} className="error" role="alert">
                  <strong>Fix first:</strong> {p.message} <span className="muted small">({p.path})</span>
                </p>
              ))}
            </div>
          ))}
          {r.skipped.length > 0 && <p className="muted small">Skipped (switched off): {r.skipped.map((s) => s.form).join(", ")}.</p>}
          {r.blocked && (
            <p className="error" role="alert">
              One or more forms would break. Fix the problems above (in those forms or in the item) and check again. Nothing was changed.
            </p>
          )}
          {count > 0 && !r.blocked && (
            <div className="card">
              <label className="check">
                <input
                  type="checkbox"
                  checked={publish}
                  onChange={(e) => {
                    setPublish(e.target.checked);
                    setConfirmed(false);
                  }}
                />{" "}
                Publish automatically after updating
              </label>
              {publish && (
                <label className="check" style={{ alignItems: "flex-start", marginTop: 6 }}>
                  <input type="checkbox" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} />
                  <span>
                    <strong>
                      I understand this puts {count} form{count === 1 ? "" : "s"} live for new inspections and cannot be undone.
                    </strong>
                    <br />
                    <span className="muted small">Inspections already started keep the version they began with.</span>
                  </span>
                </label>
              )}
            </div>
          )}
        </>
      )}
    </Modal>
  );
}
