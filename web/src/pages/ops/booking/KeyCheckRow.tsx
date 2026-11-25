import { useEffect, useState } from "react";
import type { KeyCheckValue } from "../../../api/types";
import { Pill } from "../../../ui/kit";

/** One Key Check on the Review tab: a text box; Save when changed; Reset brings back the
 *  worked-out value. */
export function KeyCheckRow({
  id,
  label,
  v,
  disabled,
  onSave,
}: {
  id: string;
  label: string;
  v?: KeyCheckValue;
  disabled: boolean;
  onSave: (text: string | null) => Promise<void>;
}) {
  const value = v?.value ?? "";
  const [text, setText] = useState(value);
  const [busy, setBusy] = useState(false);
  useEffect(() => setText(value), [value]);
  const changed = text !== value;
  const save = async (t: string | null) => {
    setBusy(true);
    try {
      await onSave(t);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="kc-row">
      <label className="kc-label" htmlFor={id}>
        {label}
        {v?.edited && <Pill tone="warn">Edited</Pill>}
      </label>
      <div className="kc-edit">
        <input
          id={id}
          value={text}
          disabled={disabled || busy}
          placeholder="Empty"
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && changed) void save(text);
            if (e.key === "Escape") setText(value);
          }}
        />
        {changed && (
          <button className="primary sm" disabled={busy} onClick={() => void save(text)}>
            Save
          </button>
        )}
        {changed && (
          <button className="sm" disabled={busy} onClick={() => setText(value)}>
            Cancel
          </button>
        )}
      </div>
      {v?.edited && !changed && (
        <div className="muted small">
          Automatic: {v.auto || "empty"} ·{" "}
          {!disabled && (
            <button className="link" disabled={busy} onClick={() => void save(null)}>
              Reset to automatic
            </button>
          )}
        </div>
      )}
    </div>
  );
}
