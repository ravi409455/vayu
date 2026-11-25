import { X } from "lucide-react";
import { createContext, useContext, useEffect, useLayoutEffect, useRef, useState } from "react";
import { GROUP_LABEL, insertValue, joinParts, labelFor, parseParts, removeValue, type CatalogueEntry } from "../../../lib/integrationDef";

/** Why the list holds what it holds (set by the editor for its form and event). */
export const PickerHint = createContext("");

const TYPE_WORD: Record<string, string> = {
  text: "text",
  number: "number",
  boolean: "yes/no",
  date: "date",
  datetime: "date and time",
  list: "list",
};

/** The searchable list of values a text can hold. Pick with the mouse or type and press Enter. */
export function ValuePicker({
  catalogue,
  onPick,
  onClose,
}: {
  catalogue: CatalogueEntry[];
  onPick: (ref: string) => void;
  onClose: () => void;
}) {
  const [q, setQ] = useState("");
  const hint = useContext(PickerHint);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const away = (e: MouseEvent) => {
      if (box.current && !box.current.contains(e.target as Node)) onClose();
    };
    document.addEventListener("mousedown", away);
    return () => document.removeEventListener("mousedown", away);
  }, [onClose]);
  const words = q.toLowerCase().split(/\s+/).filter(Boolean);
  const shown = catalogue.filter((e) => words.every((w) => `${e.label} ${e.ref} ${GROUP_LABEL[e.group] ?? ""}`.toLowerCase().includes(w)));
  const groups = [...new Set(shown.map((e) => e.group))];
  return (
    <div className="vpicker" ref={box}>
      <input
        autoFocus
        role="searchbox"
        aria-label="Search values"
        placeholder="Search values…"
        value={q}
        onChange={(e) => setQ(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Escape") {
            e.preventDefault();
            e.stopPropagation();
            onClose();
          }
          if (e.key === "Enter") {
            e.preventDefault();
            if (shown[0]) onPick(shown[0].ref);
          }
        }}
      />
      <div role="listbox" aria-label="Values">
        {groups.map((g) => (
          <div key={g}>
            <div className="vgroup">{GROUP_LABEL[g] ?? g}</div>
            {shown
              .filter((e) => e.group === g)
              .map((e) => (
                <button type="button" role="option" aria-selected={false} key={e.ref} title={e.ref} onClick={() => onPick(e.ref)}>
                  {e.label}
                  <span className="muted small"> {TYPE_WORD[e.type] ?? e.type}</span>
                </button>
              ))}
          </div>
        ))}
        {shown.length === 0 && <p className="muted small pad">Nothing matches. This form and event do not offer it.</p>}
      </div>
      {hint && <p className="muted small vhint">{hint}</p>}
    </div>
  );
}

/** A text that can hold values. Values show as chips (delete one with ×, or Backspace after it);
 *  type {{ or press "+ value" to add one. The saved text is plain `…{{ref}}…`. */
export function ValueInput({
  value,
  onChange,
  catalogue,
  label,
  placeholder,
}: {
  value: string;
  onChange: (v: string) => void;
  catalogue: CatalogueEntry[];
  label: string;
  placeholder?: string;
}) {
  const parts = parseParts(value);
  const [at, setAt] = useState<{ part: number; caret: number } | null>(null);
  const focus = useRef<number | null>(null); // which text gets the caret after an edit
  const inputs = useRef<Record<number, HTMLInputElement | null>>({});
  useLayoutEffect(() => {
    if (focus.current !== null) {
      inputs.current[focus.current]?.focus();
      focus.current = null;
    }
  });
  const last = parts.length - 1;

  /** `{{` just typed before the caret opens the list (and is not kept); a pasted {{value}} stays and becomes a chip. */
  const typed = (i: number, text: string, caret: number) => {
    const open = text.slice(0, caret).endsWith("{{");
    const clean = open ? text.slice(0, caret - 2) + text.slice(caret) : text;
    onChange(joinParts(parts.map((p, j) => (j === i ? { t: clean } : p))));
    if (open) setAt({ part: i, caret: caret - 2 });
  };
  const pick = (ref: string) => {
    if (!at) return;
    const r = insertValue(value, at.part, at.caret, ref);
    onChange(r.value);
    focus.current = r.focus;
    setAt(null);
  };
  const key = (i: number, e: React.KeyboardEvent<HTMLInputElement>) => {
    const el = e.currentTarget;
    if (e.key === "Backspace" && i > 0 && el.selectionStart === 0 && el.selectionEnd === 0) {
      e.preventDefault();
      onChange(removeValue(value, i - 1));
      focus.current = i - 2;
    }
  };
  /** At the caret of the text being edited, else at the end. */
  const addValue = () => {
    const i = Object.keys(inputs.current)
      .map(Number)
      .find((n) => inputs.current[n] === document.activeElement);
    const part = i ?? last;
    const p = parts[part];
    setAt({ part, caret: i !== undefined ? (inputs.current[i]!.selectionStart ?? 0) : p && "t" in p ? p.t.length : 0 });
  };
  return (
    <div className="vinput" role="group" aria-label={label}>
      {parts.map((p, i) =>
        "t" in p ? (
          <input
            key={i}
            ref={(el) => {
              inputs.current[i] = el;
            }}
            aria-label={label}
            className={i === last ? "grow" : ""}
            size={Math.max(2, p.t.length + 1)}
            placeholder={parts.length === 1 && i === 0 ? placeholder : undefined}
            value={p.t}
            onChange={(e) => typed(i, e.target.value, e.target.selectionStart ?? e.target.value.length)}
            onKeyDown={(e) => key(i, e)}
          />
        ) : (
          (() => {
            const l = labelFor(catalogue, p.r);
            return (
              <span
                key={i}
                className={`vchip${l.known ? "" : " gone"}`}
                title={l.known ? p.r : `${p.r} is not offered for this form and event`}
              >
                {l.label}
                <button
                  type="button"
                  aria-label={`Remove ${l.label}`}
                  onClick={() => {
                    onChange(removeValue(value, i));
                  }}
                >
                  <X size={12} aria-hidden />
                </button>
              </span>
            );
          })()
        ),
      )}
      <button
        type="button"
        className="sm vplus"
        aria-label={`Insert a value into ${label}`}
        onMouseDown={(e) => e.preventDefault()}
        onClick={addValue}
      >
        + value
      </button>
      {at && <ValuePicker catalogue={catalogue} onPick={pick} onClose={() => setAt(null)} />}
    </div>
  );
}
