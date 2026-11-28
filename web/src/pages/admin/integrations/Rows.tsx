import { Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import type { CatalogueEntry } from "../../../lib/integrationDef";
import { ValueInput } from "./ValueInput";

/** Name and value rows (query parameters, headers). The value can hold picked values. */
export function PairRows({
  rows,
  onChange,
  catalogue,
  what,
  namePlaceholder,
}: {
  rows: { key: string; value: string }[];
  onChange: (r: { key: string; value: string }[]) => void;
  catalogue: CatalogueEntry[];
  what: string;
  namePlaceholder: string;
}) {
  const set = (i: number, p: Partial<{ key: string; value: string }>) => onChange(rows.map((r, j) => (j === i ? { ...r, ...p } : r)));
  return (
    <div className="body-rows">
      {rows.map((r, i) => (
        <div className="brow-line" key={i}>
          <input
            aria-label={`${what} name ${i + 1}`}
            placeholder={namePlaceholder}
            value={r.key}
            onChange={(e) => set(i, { key: e.target.value })}
          />
          <div className="grow">
            <ValueInput
              label={`${what} value ${i + 1}`}
              value={r.value}
              catalogue={catalogue}
              placeholder="text or a picked value"
              onChange={(v) => set(i, { value: v })}
            />
          </div>
          <button
            type="button"
            className="icon-btn"
            aria-label={`Remove ${what.toLowerCase()} ${i + 1}`}
            onClick={() => onChange(rows.filter((_, j) => j !== i))}
          >
            <Trash2 size={14} aria-hidden />
          </button>
        </div>
      ))}
      <button type="button" onClick={() => onChange([...rows, { key: "", value: "" }])}>
        <Plus size={14} aria-hidden /> Add {what.toLowerCase()}
      </button>
    </div>
  );
}

/** The standard body's field filter: everything, or only the ticked fields of the booking form and
 *  [parts] (the inspection form; the Check-in form's own answers on the Check-in form). */
export function FieldChecklist({
  fields,
  onChange,
  catalogue,
  parts = ["booking", "inspection"],
}: {
  fields: string[];
  onChange: (f: string[]) => void;
  catalogue: CatalogueEntry[];
  parts?: string[];
}) {
  const [only, setOnly] = useState(fields.length > 0); // "only these", even before the first tick
  const [q, setQ] = useState("");
  const options = catalogue.filter((e) => parts.includes(e.group));
  const keys = [...new Map(options.map((e) => [e.ref.split(".")[1]!, e])).entries()].filter(
    ([k, e]) => fields.includes(k) || `${e.label} ${k}`.toLowerCase().includes(q.toLowerCase()),
  );
  const toggle = (k: string) => onChange(fields.includes(k) ? fields.filter((x) => x !== k) : [...fields, k]);
  return (
    <fieldset className="plain">
      <legend>Fields to send</legend>
      <div className="seg" role="group" aria-label="Which fields">
        <button
          type="button"
          aria-pressed={!only}
          onClick={() => {
            setOnly(false);
            onChange([]);
          }}
        >
          All fields
        </button>
        <button type="button" aria-pressed={only} onClick={() => setOnly(true)}>
          Only these
        </button>
      </div>
      {only && fields.length === 0 && <p className="muted small">Tick the fields to send. With none ticked, all are sent.</p>}
      {only && (
        <input role="searchbox" aria-label="Search fields" placeholder="Search fields…" value={q} onChange={(e) => setQ(e.target.value)} />
      )}
      {only && (
        <div className="checklist" role="group" aria-label="Fields">
          {keys.map(([k, e]) => (
            <label className="check" key={k}>
              <input type="checkbox" checked={fields.includes(k)} onChange={() => toggle(k)} /> {e.label}{" "}
              <span className="muted small mono">{k}</span>
            </label>
          ))}
        </div>
      )}
    </fieldset>
  );
}
