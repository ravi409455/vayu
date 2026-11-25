import { useContext, useLayoutEffect, useRef, useState } from "react";
import { caretPoint } from "../../../lib/caret";
import { GROUP_LABEL, jsonOpenToken, matchValues, type CatalogueEntry } from "../../../lib/integrationDef";
import { PickerHint, ValuePicker } from "./ValueInput";

const TYPE_WORD: Record<string, string> = {
  text: "text",
  number: "number",
  boolean: "yes/no",
  date: "date",
  datetime: "date and time",
  list: "list",
};

/** The custom body: JSON written by hand. Type {{ inside a string and the values of this form and
 *  event are suggested (arrows and Enter or Tab pick one); a string that is exactly one {{value}}
 *  keeps its type, {{value | text}} sends it as text. */
export function JsonEditor({
  value,
  onChange,
  catalogue,
  error,
}: {
  value: string;
  onChange: (v: string) => void;
  catalogue: CatalogueEntry[];
  error: string;
}) {
  const hint = useContext(PickerHint);
  const box = useRef<HTMLTextAreaElement>(null);
  const list = useRef<HTMLDivElement>(null);
  const [caret, setCaret] = useState(0);
  const [active, setActive] = useState(0);
  const [closedAt, setClosedAt] = useState(-1);
  const [picker, setPicker] = useState(false);
  const place = useRef<number | null>(null); // where the caret goes after an insert
  useLayoutEffect(() => {
    // after the new text is in the box
    if (place.current !== null && box.current) {
      box.current.focus();
      box.current.setSelectionRange(place.current, place.current);
      place.current = null;
    }
  });

  const open = jsonOpenToken(value, caret);
  const found = open && open.start !== closedAt ? matchValues(catalogue, open.fragment) : [];
  // the list sits under the line being typed, not over it
  const at = found.length > 0 && box.current ? caretPoint(box.current, caret) : null;
  const wide = box.current?.clientWidth ?? 600;
  useLayoutEffect(() => {
    list.current?.querySelector('[aria-selected="true"]')?.scrollIntoView?.({ block: "nearest" });
  }, [active, found.length]);

  function insert(ref: string, from: number, to: number, wrap: boolean) {
    const text = wrap ? `"{{${ref}}}"` : `{{${ref}}}`;
    onChange(value.slice(0, from) + text + value.slice(to));
    place.current = from + text.length;
    setCaret(from + text.length);
  }
  function key(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (found.length === 0) return;
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) => (a + (e.key === "ArrowDown" ? 1 : found.length - 1)) % found.length);
    } else if (e.key === "Enter" || e.key === "Tab") {
      e.preventDefault();
      insert(found[Math.min(active, found.length - 1)]!.ref, open!.start, caret, false);
    } else if (e.key === "Escape") {
      e.preventDefault();
      setClosedAt(open!.start);
    }
  }
  /** "+ value": at the caret, quoted when the caret is not inside a string already. */
  const addValue = (ref: string) => {
    const at = box.current?.selectionStart ?? value.length;
    const quotes = (value.slice(0, at).match(/(?<!\\)"/g) ?? []).length;
    insert(ref, at, at, quotes % 2 === 0);
    setPicker(false);
  };
  const format = () => {
    try {
      onChange(JSON.stringify(JSON.parse(value), null, 2));
    } catch {
      /* the error is shown */
    }
  };
  return (
    <div className="json-editor">
      <div className="bar">
        <span className="grow muted small">
          JSON. Type <code>{"{{"}</code> inside a string to pick a value.
        </span>
        <button type="button" className="sm" onMouseDown={(e) => e.preventDefault()} onClick={() => setPicker(true)}>
          + value
        </button>
        <button type="button" className="sm" disabled={!!error} onClick={format}>
          Format
        </button>
      </div>
      <div className="json-wrap">
        <textarea
          ref={box}
          className="mono"
          aria-label="Body (JSON)"
          spellCheck={false}
          rows={14}
          value={value}
          onChange={(e) => {
            setCaret(e.target.selectionStart);
            setActive(0);
            setClosedAt(-1);
            onChange(e.target.value);
          }}
          onKeyDown={key}
          onKeyUp={(e) => {
            if (!["ArrowDown", "ArrowUp", "Enter", "Tab", "Escape"].includes(e.key)) setCaret(e.currentTarget.selectionStart);
          }}
          onClick={(e) => setCaret(e.currentTarget.selectionStart)}
        />
        {found.length > 0 && at && (
          <div
            className="vpicker json-suggest"
            role="listbox"
            aria-label="Suggestions"
            ref={list}
            style={{ left: Math.max(4, Math.min(at.left, wide - 450)), top: at.top + at.line + 6 }}
          >
            {found.map((e, i) => (
              <div key={e.ref}>
                {(i === 0 || found[i - 1]!.group !== e.group) && <div className="vgroup">{GROUP_LABEL[e.group] ?? e.group}</div>}
                <button
                  type="button"
                  role="option"
                  aria-selected={i === active}
                  className={i === active ? "on" : ""}
                  title={e.ref}
                  onMouseDown={(ev) => ev.preventDefault()}
                  onClick={() => insert(e.ref, open!.start, caret, false)}
                >
                  {e.label} <span className="muted small">{TYPE_WORD[e.type] ?? e.type}</span>
                </button>
              </div>
            ))}
            {hint && <p className="muted small vhint">{hint}</p>}
          </div>
        )}
        {picker && <ValuePicker catalogue={catalogue} onPick={addValue} onClose={() => setPicker(false)} />}
      </div>
      {error ? (
        <p className="error small" data-testid="json-error">
          {error}
        </p>
      ) : (
        <p className="muted small">Valid JSON.</p>
      )}
    </div>
  );
}
