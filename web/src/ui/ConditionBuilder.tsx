import { useEffect, useState } from "react";
import { InfoTip } from "./InfoTip";
import { fromRule, OPS, toRule, type Cond, type OpId, type Row } from "../lib/conditions";

export type FieldChoice = { value: string; label: string };

/** Builds a JsonLogic rule from rows ("Door is dent AND Odometer > 100"). A rule it cannot draw
 *  stays editable as raw JSON, so nothing written elsewhere is ever lost. */
export function ConditionBuilder({ value, onChange, fields, label, tip }: {
  value: unknown; onChange: (rule: unknown) => void; fields: FieldChoice[]; label: string; tip?: string;
}) {
  const parsedProp = fromRule(value);
  // Rows being typed are not complete rules yet, so the builder keeps them itself and only
  // reports a rule upward when it changes.
  const [cond, setCond] = useState<Cond>(parsedProp ?? { join: "and", rows: [] });
  useEffect(() => {
    if (parsedProp && JSON.stringify(toRule(cond)) !== JSON.stringify(value ?? null)) setCond(parsedProp);
  }, [value]); // eslint-disable-line react-hooks/exhaustive-deps
  const parsed = parsedProp === null ? null : cond;
  const [raw, setRaw] = useState(parsedProp === null);
  const [text, setText] = useState(() => JSON.stringify(value ?? null, null, 1));
  const [err, setErr] = useState("");
  useEffect(() => { setText(JSON.stringify(value ?? null, null, 1)); }, [value]);

  if (raw || parsed === null) {
    return (
      <div className="card" aria-label={label}>
        <strong>{label} (advanced)</strong>
        <textarea aria-label={`${label} JSON`} value={text} onChange={(e) => {
          setText(e.target.value);
          try { onChange(JSON.parse(e.target.value)); setErr(""); } catch { setErr("This is not valid JSON yet."); }
        }} />
        {err && <p className="error">{err}</p>}
        {parsed !== null && <button className="link" onClick={() => setRaw(false)}>Use the simple builder</button>}
      </div>
    );
  }
  const set = (c: Cond) => { setCond(c); onChange(toRule(c)); };
  const upd = (i: number, patch: Partial<Row>) => set({ ...parsed, rows: parsed.rows.map((r, j) => (j === i ? { ...r, ...patch } : r)) });
  return (
    <div className="card" aria-label={label}>
      <div><strong>{label}</strong>{tip && <> <InfoTip label={`About ${label}`}>{tip}</InfoTip></>}</div>
      {parsed.rows.length === 0 && <p className="muted small">Always. Add a condition to limit it.</p>}
      {parsed.rows.map((r, i) => (
        <div className="cond-row" key={i}>
          {i > 0 && (
            <select aria-label="Join" value={parsed.join} onChange={(e) => set({ ...parsed, join: e.target.value as "and" | "or" })} style={{ maxWidth: 80 }}>
              <option value="and">and</option><option value="or">or</option>
            </select>
          )}
          <select aria-label="Field" value={r.field} onChange={(e) => upd(i, { field: e.target.value })}>
            <option value="">Choose a field…</option>
            {fields.map((f) => <option key={f.value} value={f.value}>{f.label}</option>)}
          </select>
          <select aria-label="Operator" value={r.op} onChange={(e) => upd(i, { op: e.target.value as OpId })}>
            {OPS.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
          </select>
          {r.op !== "filled" && r.op !== "empty" && (
            <input aria-label="Value" value={r.value} onChange={(e) => upd(i, { value: e.target.value })} placeholder={r.op === "in" ? "a, b, c" : "value"} />
          )}
          <button className="link" aria-label="Remove condition" onClick={() => set({ ...parsed, rows: parsed.rows.filter((_, j) => j !== i) })}>✕</button>
        </div>
      ))}
      <button className="link" onClick={() => set({ ...parsed, rows: [...parsed.rows, { field: "", op: "==", value: "" }] })}>+ Add condition</button>{" "}
      <button className="link" onClick={() => setRaw(true)}>Edit as JSON</button>
    </div>
  );
}
