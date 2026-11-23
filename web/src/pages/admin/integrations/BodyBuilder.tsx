import { Plus, Trash2 } from "lucide-react";
import type { BodyRow } from "../../../api/types";
import { asKind, blankRow, fixedKind, kindOf, MAX_DEPTH, typedFixed, type CatalogueEntry, type RowKind } from "../../../lib/integrationDef";
import { ValueInput } from "./ValueInput";

/** The rows of a custom body: a name, and a value picked from the system, a fixed value, or a group
 *  of more rows. Only what is mapped here leaves; the preview shows the JSON it makes. */
export function BodyBuilder({ rows, onChange, catalogue, depth = 1, prefix = "" }: { rows: BodyRow[]; onChange: (r: BodyRow[]) => void; catalogue: CatalogueEntry[]; depth?: number; prefix?: string }) {
  const set = (i: number, r: BodyRow) => onChange(rows.map((x, j) => (j === i ? r : x)));
  return (
    <div className="body-rows">
      {rows.map((r, i) => {
        const n = `${prefix}${i + 1}`;
        const kind = kindOf(r);
        return (
          <div className="brow" key={i}>
            <div className="brow-line">
              <input aria-label={`Key ${n}`} placeholder="name" value={r.key} onChange={(e) => set(i, { ...r, key: e.target.value })} />
              <select aria-label={`Row type ${n}`} value={kind} onChange={(e) => set(i, asKind(r, e.target.value as RowKind))}>
                <option value="value">Value from the system</option><option value="fixed">Fixed value</option>
                <option value="group" disabled={depth >= MAX_DEPTH}>Group of rows</option></select>
              {kind === "value" && (
                <>
                  <div className="grow"><ValueInput label={`Value ${n}`} value={r.value ?? ""} catalogue={catalogue} placeholder="pick a value or type text" onChange={(v) => set(i, { ...r, value: v })} /></div>
                  <label className="check small"><input type="checkbox" aria-label={`Send as text ${n}`} checked={!!r.as_text} onChange={(e) => set(i, { ...r, as_text: e.target.checked })} /> as text</label>
                </>)}
              {kind === "fixed" && (
                <>
                  <select aria-label={`Fixed type ${n}`} value={fixedKind(r.fixed)} onChange={(e) => set(i, { key: r.key, fixed: typedFixed(e.target.value as "text" | "number" | "yesno", e.target.value === "yesno" ? "false" : "") })}>
                    <option value="text">Text</option><option value="number">Number</option><option value="yesno">Yes / No</option></select>
                  {fixedKind(r.fixed) === "yesno"
                    ? <select aria-label={`Fixed value ${n}`} value={String(r.fixed)} onChange={(e) => set(i, { key: r.key, fixed: e.target.value === "true" })}><option value="true">Yes</option><option value="false">No</option></select>
                    : <input aria-label={`Fixed value ${n}`} className="grow" type={fixedKind(r.fixed) === "number" ? "number" : "text"} value={String(r.fixed ?? "")} onChange={(e) => set(i, { key: r.key, fixed: typedFixed(fixedKind(r.fixed), e.target.value) })} />}
                </>)}
              {kind === "group" && <span className="grow muted small">Rows inside {r.key || "this group"}:</span>}
              <button type="button" className="icon-btn" aria-label={`Remove row ${n}`} onClick={() => onChange(rows.filter((_, j) => j !== i))}><Trash2 size={14} aria-hidden /></button>
            </div>
            {kind === "group" && <div className="brow-group"><BodyBuilder rows={r.rows ?? []} onChange={(x) => set(i, { ...r, rows: x })} catalogue={catalogue} depth={depth + 1} prefix={`${n}.`} /></div>}
          </div>);
      })}
      <div className="bar">
        <button type="button" onClick={() => onChange([...rows, blankRow("value")])}><Plus size={14} aria-hidden /> Add row</button>
        {depth < MAX_DEPTH && <button type="button" onClick={() => onChange([...rows, blankRow("group")])}><Plus size={14} aria-hidden /> Add group</button>}
      </div>
    </div>
  );
}
