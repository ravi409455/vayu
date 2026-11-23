import { useEffect, useRef, useState } from "react";

type Choice = { value: string; label: string };
const TAGS = new Set(["P", "BR", "STRONG", "B", "EM", "I", "U", "S", "UL", "OL", "LI", "A", "SPAN", "H2", "H3", "H4", "BLOCKQUOTE", "HR"]);

/** The same small set of tags the server keeps; every other tag is unwrapped and every attribute
 *  but class and a safe href is dropped (so nothing in a template can run in the browser). */
export function cleanHtml(html: string): string {
  const doc = new DOMParser().parseFromString(`<div>${html}</div>`, "text/html");
  const walk = (node: Element) => {
    for (const child of [...node.children]) {
      walk(child);
      if (!TAGS.has(child.tagName)) { child.replaceWith(...child.childNodes); continue; }
      for (const a of [...child.attributes]) {
        const safe = a.name === "class" || (a.name === "href" && /^(https:|mailto:|tel:)/i.test(a.value));
        if (!safe) child.removeAttribute(a.name);
      }
    }
  };
  const root = doc.body.firstElementChild!;
  for (const bad of root.querySelectorAll("script,style,iframe,object,embed,img,svg,math")) bad.remove();
  walk(root);
  return root.innerHTML;
}

/** Formatted text for a report: bold, italic, lists, a heading, colours, and values from the
 *  inspection ({{ inspection.colour }}). The server keeps only a small set of tags, so pasted
 *  styling or scripts never reach a report. */
export function RichText({ value, onChange, choices, label }: { value: string; onChange: (html: string) => void; choices: Choice[]; label: string }) {
  const el = useRef<HTMLDivElement>(null);
  const [source, setSource] = useState(false);
  useEffect(() => {                                   // outside changes (another part picked)
    if (el.current && el.current.innerHTML !== value) el.current.innerHTML = cleanHtml(value);
  }, [value, source]);
  const emit = () => el.current && onChange(el.current.innerHTML);
  const run = (cmd: string, arg?: string) => { el.current?.focus(); document.execCommand(cmd, false, arg); emit(); };
  const wrap = (cls: string) => {
    const sel = window.getSelection();
    const text = sel && sel.rangeCount ? sel.toString() : "";
    if (text) run("insertHTML", `<span class="${cls}">${text.replace(/&/g, "&amp;").replace(/</g, "&lt;")}</span>`);
  };
  return (
    <div className="rd-rich">
      <div className="rd-rich-bar" role="toolbar" aria-label={`${label} formatting`}>
        <button type="button" onMouseDown={(e) => e.preventDefault()} onClick={() => run("bold")} aria-label="Bold"><b>B</b></button>
        <button type="button" onMouseDown={(e) => e.preventDefault()} onClick={() => run("italic")} aria-label="Italic"><i>I</i></button>
        <button type="button" onMouseDown={(e) => e.preventDefault()} onClick={() => run("underline")} aria-label="Underline"><u>U</u></button>
        <button type="button" onMouseDown={(e) => e.preventDefault()} onClick={() => run("formatBlock", "h2")} aria-label="Heading">H</button>
        <button type="button" onMouseDown={(e) => e.preventDefault()} onClick={() => run("formatBlock", "p")} aria-label="Plain text">¶</button>
        <button type="button" onMouseDown={(e) => e.preventDefault()} onClick={() => run("insertUnorderedList")} aria-label="Bullet list">•</button>
        <button type="button" onMouseDown={(e) => e.preventDefault()} onClick={() => run("insertOrderedList")} aria-label="Numbered list">1.</button>
        <select aria-label="Colour" value="" onMouseDown={(e) => e.stopPropagation()} onChange={(e) => { if (e.target.value) wrap(e.target.value); }}>
          <option value="">Colour…</option><option value="tone-brand">Brand red</option><option value="tone-ok">Green</option>
          <option value="tone-warn">Amber</option><option value="tone-bad">Red</option><option value="tone-muted">Grey</option></select>
        <select aria-label="Insert a value" value="" onChange={(e) => { if (e.target.value) run("insertText", `{{ ${e.target.value} }}`); }}>
          <option value="">Insert a value…</option>
          <optgroup label="Report">
            {[["sys.booking_id", "Booking ID"], ["sys.car", "Car"], ["sys.inspection_type", "Inspection type"], ["sys.expert", "Expert"],
              ["sys.inspected_on", "Inspected on"], ["sys.overall", "Expert rating"], ["sys.issues", "Number of issues"],
              ["sys.not_checked_list", "Not able to check (list)"], ["sys.generated_at", "Generated at"], ["sys.verify_url", "Verify link"]].map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </optgroup>
          <optgroup label="Answers">{choices.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}</optgroup>
        </select>
        <button type="button" className="link" onClick={() => setSource(!source)}>{source ? "Done" : "HTML"}</button>
      </div>
      {source
        ? <textarea aria-label={`${label} (HTML)`} className="mono" rows={8} value={value} onChange={(e) => onChange(e.target.value)} />
        : <div ref={el} className="rd-rich-area" contentEditable suppressContentEditableWarning role="textbox" aria-multiline="true" aria-label={label} onInput={emit} onBlur={emit} />}
    </div>
  );
}
