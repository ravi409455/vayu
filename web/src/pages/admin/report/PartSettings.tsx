import { ArrowDown, ArrowUp, Copy, Trash2 } from "lucide-react";
import { useRef, useState, type ReactNode } from "react";
import { ConditionBuilder } from "../../../ui/ConditionBuilder";
import { Field, Modal } from "../../../ui/kit";
import { fillGrid, LINKS, PART_LABEL, type Box, type Cell, type Look, type Part, type ReportPage, type Row, type Source, type StyleRule } from "./model";
import { RichText, ValuePicker } from "./RichText";
import { ShareForm, snippetContent, type SharedItem } from "./sharing";
import { NO_TEXT_TYPES } from "../../../lib/fieldTypes";

export type SectionChoice = { value: string; label: string; fields: { key: string; label: string; type: string }[] };
export type Ctx = { sections: SectionChoice[]; fields: { value: string; label: string; type: string }[]; readOnly: boolean; snippets?: SharedItem[] };


/** A row of buttons for a small set of choices. */
function Seg<T extends string | number>({ label, value, options, onChange }: { label: string; value: T; options: [T, string][]; onChange: (v: T) => void }) {
  return (
    <div className="seg sm" role="group" aria-label={label}>
      {options.map(([v, l]) => <button key={String(v)} type="button" aria-pressed={value === v} onClick={() => onChange(v)}>{l}</button>)}
    </div>
  );
}

/** A folded group of settings, with a one-line summary of what is set. */
function More({ title, summary, children }: { title: string; summary: string; children: ReactNode }) {
  return (
    <details className="rd-more">
      <summary><span>{title}</span><span className="muted small">{summary}</span></summary>
      <div className="rd-more-body">{children}</div>
    </details>
  );
}

function Toggle({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return <label className="check"><input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} /> {label}</label>;
}

export function PageSettings({ page, onChange, onDelete, fields }: { page: ReportPage; onChange: (p: Partial<ReportPage>) => void; onDelete?: () => void; fields: Ctx["fields"] }) {
  return (
    <div className="rd-settings-body">
      <Field label="Page name" help="Shown in the pages list and in a contents list.">
        <input value={page.title} onChange={(e) => onChange({ title: e.target.value })} />
      </Field>
      <Field label="Page style">
        <Seg
          label="Page style"
          value={page.style ?? "normal"}
          options={[
            ["normal", "Normal"],
            ["cover", "Cover"],
            ["full", "Full page"],
          ]}
          onChange={(style) => onChange({ style })}
        />
      </Field>
      <p className="muted small">
        {page.style === "full"
          ? "No header or footer: for a divider or a full-page design."
          : page.style === "cover"
            ? "Uses the cover header and footer (Report settings)."
            : "Uses the normal header and footer (Report settings)."}{" "}
        Each page starts on a new sheet; long pages carry on over several.
      </p>
      <ConditionBuilder
        label="Show this page only if"
        value={page.show_if ?? null}
        onChange={(r) => onChange({ show_if: r ?? undefined })}
        fields={fields}
      />
      {onDelete && (
        <button type="button" className="danger" onClick={onDelete}>
          <Trash2 size={14} aria-hidden /> Delete page
        </button>
      )}
    </div>
  );
}

export function PartSettings({ part, onChange, onDelete, onDuplicate, onMove, ctx, onShared, onUnlink }: {
  part: Part; onChange: (p: Partial<Part>) => void; onDelete: () => void; onDuplicate: () => void; onMove: (by: -1 | 1) => void; ctx: Ctx;
  onShared?: (item: SharedItem & { updated: string[] }) => void; onUnlink?: () => void;
}) {
  const set = onChange as (p: Record<string, unknown>) => void;
  const box = ("box" in part ? part.box : undefined) ?? {};
  const setBox = (b: Partial<Box>) => set({ box: { ...box, ...b } });
  const t = part.type;
  const titled = t === "table" || t === "photos" || t === "contents" || t === "html";
  return (
    <div className="rd-settings-body">
      <div className="bar" style={{ margin: 0 }}>
        <strong className="grow">{PART_LABEL[t]}</strong>
        <button type="button" className="icon-btn" aria-label="Move up" onClick={() => onMove(-1)}><ArrowUp size={15} aria-hidden /></button>
        <button type="button" className="icon-btn" aria-label="Move down" onClick={() => onMove(1)}><ArrowDown size={15} aria-hidden /></button>
        <button type="button" className="icon-btn" aria-label="Duplicate" onClick={onDuplicate}><Copy size={15} aria-hidden /></button>
        <button type="button" className="icon-btn danger" aria-label="Delete" onClick={onDelete}><Trash2 size={15} aria-hidden /></button>
      </div>
      <fieldset disabled={ctx.readOnly} className="rd-fieldset">
        {titled && <Field label="Title"><input value={("title" in part && part.title) || ""} placeholder="Optional" onChange={(e) => set({ title: e.target.value })} /></Field>}
        {t === "table" && <TableSettings part={part} set={set} ctx={ctx} />}
        {t === "photos" && <PhotoSettings part={part} set={set} ctx={ctx} />}
        {t === "text" && (
          <>
            <RichText label="Text" value={part.html} onChange={(html) => set({ html })} choices={ctx.fields.filter((f) => !NO_TEXT_TYPES.includes(f.type))} />
            <Field label="Columns"><Seg label="Text columns" value={part.columns ?? 1} options={[[1, "1"], [2, "2"]]} onChange={(columns) => set({ columns })} /></Field>
            <Field label="Size"><Seg label="Text size" value={part.size ?? "normal"} options={[["fine", "Fine print"], ["small", "Small"], ["normal", "Normal"], ["large", "Large"], ["title", "Title"]]} onChange={(size) => set({ size })} /></Field>
            <Field label="Align"><Seg label="Align" value={part.align ?? "left"} options={[["left", "Left"], ["center", "Centre"], ["right", "Right"], ["justify", "Justify"]]} onChange={(align) => set({ align })} /></Field>
          </>
        )}
        {t === "columns" && (
          <>
            <p className="muted small">Pick the parts inside each column in the pages list on the left; “+ Add” under a column adds to it.</p>
            <Field label="Columns"><Seg label="Number of columns" value={part.columns.length} options={[[2, "2"], [3, "3"]]}
              onChange={(n) => set({ columns: n > part.columns.length ? [...part.columns, { parts: [] }] : part.columns.slice(0, n) })} /></Field>
            <div className="grid2">
              {part.columns.map((c, i) => (
                <Field key={i} label={`Column ${i + 1} width %`}><input type="number" min={10} max={90} placeholder="auto" value={c.width ?? ""}
                  onChange={(e) => set({ columns: part.columns.map((x, j) => (j === i ? { ...x, width: e.target.value ? Number(e.target.value) : undefined } : x)) })} /></Field>))}
            </div>
            <Field label="Gap (mm)"><input type="number" min={0} max={20} value={part.gap ?? 6} onChange={(e) => set({ gap: Number(e.target.value) })} /></Field>
            <Field label="Line up"><Seg label="Line up" value={part.align ?? "top"} options={[["top", "Top"], ["middle", "Middle"]]} onChange={(align) => set({ align })} /></Field>
          </>
        )}
        {t === "html" && <HtmlSettings part={part} set={set} ctx={ctx} />}
        {t === "snippet" && <SnippetSettings part={part} set={set} items={ctx.snippets ?? []} onUnlink={onUnlink} />}
        {t === "button" && (
          <>
            <Field label="Opens"><select value={part.link} onChange={(e) => { const l = LINKS.find(([v]) => v === e.target.value)!; set({ link: l[0], label: l[2] }); }}>
              {LINKS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></Field>
            <Field label="Button text"><input value={part.label} onChange={(e) => set({ label: e.target.value })} /></Field>
            <Field label="Align"><Seg label="Align" value={part.align ?? "center"} options={[["left", "Left"], ["center", "Centre"], ["right", "Right"]]} onChange={(align) => set({ align })} /></Field>
            <p className="muted small">{part.link === "verify" ? "Opens the page that proves the report is genuine." :
              `One tap downloads a ZIP of every ${part.link === "photos" ? "photo" : "video"} of the inspection, in folders by section. The link keeps working for as long as the report does. Hidden when there are none.`}</p>
          </>)}
        {t === "verify" && <Field label="Code size (mm)"><input type="number" min={15} max={120} value={part.size ?? 40} onChange={(e) => set({ size: Number(e.target.value) })} /></Field>}
        {t === "contents" && <Field label="Columns"><Seg label="Contents columns" value={part.columns ?? 1} options={[[1, "1"], [2, "2"]]} onChange={(columns) => set({ columns })} /></Field>}
        {t === "spacer" && <Field label="Height (mm)"><input type="number" min={1} max={200} value={part.height ?? 10} onChange={(e) => set({ height: Number(e.target.value) })} /></Field>}
        <More title="When to show" summary={[part.show_if ? "only sometimes" : "always", "hide_when_empty" in part && part.hide_when_empty === false ? "shown when empty" : "hidden when empty"].join(" · ")}>
          {t !== "page_break" && t !== "spacer" && <Toggle label="Hide when there is nothing to show" checked={("hide_when_empty" in part ? part.hide_when_empty : undefined) !== false} onChange={(v) => set({ hide_when_empty: v })} />}
          <ConditionBuilder label="Show only if" value={part.show_if ?? null} onChange={(r) => set({ show_if: r ?? undefined })} fields={ctx.fields} />
        </More>
        {t !== "page_break" && t !== "spacer" && (
          <More title="Page breaks" summary={[
            ("new_page" in part && part.new_page) ? "new page" : "", ("keep_together" in part && part.keep_together) ? "kept together" : "",
            ("keep_title" in part ? part.keep_title : undefined) !== false ? "title kept with rows" : ""].filter(Boolean).join(" · ") || "none"}>
            <Toggle label="Start on a new page" checked={!!("new_page" in part && part.new_page)} onChange={(v) => set({ new_page: v || undefined })} />
            <Toggle label="Keep together on one page" checked={!!("keep_together" in part && part.keep_together)} onChange={(v) => set({ keep_together: v || undefined })} />
            <Toggle label="Keep the title with the first rows" checked={("keep_title" in part ? part.keep_title : undefined) !== false} onChange={(v) => set({ keep_title: v })} />
          </More>)}
        {t !== "page_break" && t !== "spacer" && (
          <More title="Box" summary={[box.border && box.border !== "none" ? `${box.border} border` : "", box.background && box.background !== "none" ? "tinted" : "", box.padding ? `${box.padding} mm padding` : ""].filter(Boolean).join(" · ") || "plain"}>
            <div className="grid2">
              <Field label="Space above (mm)"><input type="number" min={0} max={60} value={box.space_above ?? 0} onChange={(e) => setBox({ space_above: Number(e.target.value) })} /></Field>
              <Field label="Space below (mm)"><input type="number" min={0} max={60} value={box.space_below ?? 3} onChange={(e) => setBox({ space_below: Number(e.target.value) })} /></Field>
              <Field label="Padding (mm)"><input type="number" min={0} max={20} value={box.padding ?? 0} onChange={(e) => setBox({ padding: Number(e.target.value) })} /></Field>
              <Field label="Border"><select value={box.border ?? "none"} onChange={(e) => setBox({ border: e.target.value as Box["border"] })}>
                <option value="none">None</option><option value="all">All sides</option><option value="bottom">Bottom</option><option value="left">Left</option></select>
                </Field>
              <Field label="Border colour"><select value={box.border_color ?? "muted"} onChange={(e) => setBox({ border_color: e.target.value })}>{TONES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></Field>
              <Field label="Background"><select value={box.background ?? "none"} onChange={(e) => setBox({ background: e.target.value })}><option value="none">None</option>{TONES.filter(([v]) => v !== "text").map(([v, l]) => <option key={v} value={v}>{l} tint</option>)}</select></Field>
            </div>
            <Toggle label="Round corners" checked={!!box.round} onChange={(v) => setBox({ round: v })} />
          </More>)}
        {t !== "page_break" && t !== "snippet" && onShared && (
          <More title="Share with other reports" summary="e.g. a disclaimer used by every report">
            <ShareForm kind="snippet" label="Save this part as a shared part" items={ctx.snippets ?? []} content={snippetContent(part)} onSaved={onShared} />
          </More>)}
      </fieldset>
    </div>
  );
}

const TONES: [string, string][] = [["brand", "Brand"], ["text", "Text"], ["ok", "Green"], ["warn", "Amber"], ["bad", "Red"], ["muted", "Grey"]];

function TableSettings({ part, set, ctx }: { part: Extract<Part, { type: "table" }>; set: (p: Record<string, unknown>) => void; ctx: Ctx }) {
  const src = part.source;
  const look: Look = part.look ?? {};
  const setLook = (l: Partial<Look>) => set({ look: { ...look, ...l } });
  const setSrc = (s: Source) => set({ source: s });
  const fields = ctx.fields.filter((f) => !NO_TEXT_TYPES.includes(f.type));
  const kind = src.kind;
  const sec = kind === "section" ? ctx.sections.find((s) => s.value === src.section) : undefined;
  return (
    <>
      <Field label="Which checks">
        <div className="rd-choices">
          {([["section", "All checks in a form section", "New checks added to the form appear by themselves."], ["fields", "Checks I pick", ""],
            ["defects", "All problems found", "Every answer marked as a problem, with its section."], ["grid", "A grid", "Rows and columns you name; each cell is one field (e.g. tyres)."]] as const).map(([k, l, h]) => (
            <label key={k} className={`rd-choice${kind === k ? " on" : ""}`}>
              <input type="radio" name={`src-${part.id}`} checked={kind === k} onChange={() => setSrc(
                k === "section" ? { kind: "section", section: ctx.sections[0]?.value ?? "inspection.section_1" }
                  : k === "fields" ? { kind: "fields", rows: [] } : k === "defects" ? { kind: "defects" }
                    : { kind: "grid", columns: [{ label: "Column 1" }], rows: [{ label: "Row 1", cells: [{ text: "" }] }] })} />
              <span><strong>{l}</strong>{h && <span className="muted small"> {h}</span>}</span>
            </label>))}
        </div>
      </Field>
      {src.kind === "section" && (
        <>
          <Field label="Form section">
            <select value={src.section} onChange={(e) => setSrc({ ...src, section: e.target.value, exclude: [] })}>
              {!sec && <option value={src.section}>{src.section} (not in the form)</option>}
              {ctx.sections.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}</select>
          </Field>
          {sec && (
            <Field label="Leave out" help="Photos never print in a table; they go in a photo grid.">
              <div className="chips">{(src.exclude ?? []).map((k) => (
                <button key={k} type="button" className="chip" onClick={() => setSrc({ ...src, exclude: (src.exclude ?? []).filter((x) => x !== k) })}>
                  {sec.fields.find((f) => f.key === k)?.label ?? k} ✕</button>))}
                <select aria-label="Leave out a check" value="" onChange={(e) => e.target.value && setSrc({ ...src, exclude: [...(src.exclude ?? []), e.target.value] })} style={{ width: "auto" }}>
                  <option value="">+ Leave out…</option>
                  {sec.fields.filter((f) => !NO_TEXT_TYPES.includes(f.type) && !(src.exclude ?? []).includes(f.key)).map((f) => <option key={f.key} value={f.key}>{f.label}</option>)}</select>
              </div>
            </Field>)}
          <Field label="When a check has no answer" help="Leave empty to hide the row."><input placeholder="e.g. Not mentioned" value={src.fallback ?? ""} onChange={(e) => setSrc({ ...src, fallback: e.target.value || undefined })} /></Field>
        </>
      )}
      {src.kind === "fields" && <RowsEditor rows={src.rows} onChange={(rows) => setSrc({ ...src, rows })} fields={fields} sections={ctx.sections} />}
      {src.kind === "grid" && <GridBox src={src} onChange={setSrc} fields={fields} />}
      {(src.kind === "fields" || src.kind === "section") && (
        <Field label="Checks per row"><Seg label="Checks per row" value={part.per_row ?? 1} options={[[1, "1"], [2, "2"], [3, "3"], [4, "4"]]} onChange={(per_row) => set({ per_row })} /></Field>)}
      <More title="Look" summary={[look.header ?? (src.kind === "defects" || src.kind === "grid") ? "header row" : "", look.stripes ?? true ? "stripes" : "", look.lines ?? "rows", look.emphasis ? "big numbers" : ""].filter(Boolean).join(" · ")}>
        <Toggle label="Header row (repeats on each page)" checked={look.header ?? (src.kind === "defects" || src.kind === "grid")} onChange={(v) => setLook({ header: v })} />
        <Toggle label="Stripes" checked={look.stripes ?? true} onChange={(v) => setLook({ stripes: v })} />
        <Field label="Lines"><Seg label="Lines" value={look.lines ?? "rows"} options={[["all", "All cells"], ["rows", "Rows"], ["none", "None"]]} onChange={(lines) => setLook({ lines })} /></Field>
        <Field label="Row height"><Seg label="Row height" value={look.height ?? "normal"} options={[["compact", "Compact"], ["normal", "Normal"], ["roomy", "Roomy"]]} onChange={(height) => setLook({ height })} /></Field>
        {src.kind !== "grid" && src.kind !== "defects" && <Field label={`Label column ${look.label_width ?? 55}%`}><input type="range" min={15} max={85} value={look.label_width ?? 55} onChange={(e) => setLook({ label_width: Number(e.target.value) })} /></Field>}
        <Toggle label="Muted labels, bold answers" checked={!!look.kv} onChange={(v) => setLook({ kv: v })} />
        {src.kind === "grid" && <Toggle label="Big numbers (ratings, totals)" checked={!!look.emphasis} onChange={(v) => setLook({ emphasis: v })} />}
      </More>
      <More title="Style rules" summary={part.style_rules?.length ? `${part.style_rules.length} rule${part.style_rules.length > 1 ? "s" : ""}` : "none"}>
        <StyleRules rules={part.style_rules ?? []} onChange={(r) => set({ style_rules: r.length ? r : undefined })} grid={src.kind === "grid"} />
      </More>
    </>
  );
}

function RowsEditor({ rows, onChange, fields, sections }: { rows: Row[]; onChange: (r: Row[]) => void; fields: Ctx["fields"]; sections: SectionChoice[] }) {
  const setRow = (i: number, p: Partial<Row>) => onChange(rows.map((r, j) => (j === i ? { ...r, ...p } : r)));
  return (
    <div className="rd-rows">
      {rows.map((r, i) => (
        <div key={i} className="rd-row">
          <select aria-label="Field" value={r.field} onChange={(e) => setRow(i, { field: e.target.value })}>
            <option value="">Choose a field…</option>{fields.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}</select>
          <input aria-label="Report label" placeholder="Label (default: the field's)" value={r.label ?? ""} onChange={(e) => setRow(i, { label: e.target.value || undefined })} />
          <input aria-label="When empty" placeholder="When empty" value={r.fallback ?? ""} onChange={(e) => setRow(i, { fallback: e.target.value || undefined })} />
          <button type="button" className="link" aria-label="Remove row" onClick={() => onChange(rows.filter((_, j) => j !== i))}>✕</button>
        </div>))}
      <div className="bar" style={{ margin: 0 }}>
        <button type="button" className="link" onClick={() => onChange([...rows, { field: "" }])}>+ Add row</button>
        <select aria-label="Add all checks of a section" value="" style={{ width: "auto" }} onChange={(e) => {
          const s = sections.find((x) => x.value === e.target.value);
          if (s) onChange([...rows, ...s.fields.filter((f) => !NO_TEXT_TYPES.includes(f.type)).map((f) => ({ field: `inspection.${f.key}` }))]);
        }}><option value="">+ Add all from a section…</option>{sections.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}</select>
      </div>
    </div>
  );
}

/** The grid needs room: a summary here, the editor in a wide window. */
function GridBox({ src, onChange, fields }: { src: Extract<Source, { kind: "grid" }>; onChange: (s: Source) => void; fields: Ctx["fields"] }) {
  const [open, setOpen] = useState(false);
  const filled = src.rows.reduce((n, r) => n + r.cells.filter((c) => "field" in c).length, 0);
  return (
    <>
      <div className="rd-gridbox">
        <span><strong>{src.columns.length}</strong> column{src.columns.length === 1 ? "" : "s"} × <strong>{src.rows.length}</strong> row{src.rows.length === 1 ? "" : "s"}, {filled} cell{filled === 1 ? "" : "s"} with a field</span>
        <span className="muted small">{src.columns.map((c) => c.label).join(" · ")}</span>
        <button type="button" className="sm" onClick={() => setOpen(true)}>Edit grid</button>
      </div>
      {open && <Modal title="Edit grid" wide onClose={() => setOpen(false)} actions={<button className="primary" onClick={() => setOpen(false)}>Done</button>}>
        <GridEditor src={src} onChange={onChange} fields={fields} />
      </Modal>}
    </>
  );
}

function GridEditor({ src, onChange, fields }: { src: Extract<Source, { kind: "grid" }>; onChange: (s: Source) => void; fields: Ctx["fields"] }) {
  const known = new Set(fields.filter((f) => f.value.startsWith("inspection.")).map((f) => f.value.slice(11)));
  const cellValue = (c: Cell | undefined) => (c && "field" in c ? c.field : "");
  return (
    <div className="rd-grid">
      <div className="tbl-wrap">
        <table className="rd-grid-t">
          <thead><tr><th><span className="sr-only">Actions</span></th>{src.columns.map((c, i) => (
            <th key={i}><input aria-label={`Column ${i + 1} name`} value={c.label} onChange={(e) => onChange({ ...src, columns: src.columns.map((x, j) => (j === i ? { ...x, label: e.target.value } : x)) })} /></th>))}
            <th><button type="button" className="link" onClick={() => onChange({ ...src, columns: [...src.columns, { label: `Column ${src.columns.length + 1}` }], rows: src.rows.map((r) => ({ ...r, cells: [...r.cells, { text: "" }] })) })}>+ Column</button></th></tr></thead>
          <tbody>{src.rows.map((r, i) => (
            <tr key={i}>
              <th><input aria-label={`Row ${i + 1} name`} value={r.label} onChange={(e) => onChange({ ...src, rows: src.rows.map((x, j) => (j === i ? { ...x, label: e.target.value } : x)) })} /></th>
              {src.columns.map((_, c) => (
                <td key={c}>
                  <select aria-label={`Row ${i + 1} column ${c + 1}`} value={cellValue(r.cells[c])} onChange={(e) =>
                    onChange({ ...src, rows: src.rows.map((x, j) => (j === i ?
                    { ...x, cells: src.columns.map((__, k) => (k === c ? (e.target.value ? { field: e.target.value } : { text: "" }) : (x.cells[k] ?? { text: "" }))) } : x)) })}>
                  <option value="">—</option>{fields.map((f) => <option key={f.value} value={f.value}>{f.label}</option>)}</select></td>))}
              <td><button type="button" className="link" aria-label={`Remove row ${i + 1}`} onClick={() => onChange({ ...src, rows: src.rows.filter((_, j) => j !== i) })}>✕</button></td>
            </tr>))}</tbody>
        </table>
      </div>
      <div className="bar" style={{ margin: 0 }}>
        <button type="button" className="link" onClick={() => onChange({ ...src, rows: [...src.rows, { label: `Row ${src.rows.length + 1}`, cells: src.columns.map(() => ({ text: "" })) }] })}>+ Row</button>
        <form className="bar" style={{ margin: 0 }} onSubmit={(e) => { e.preventDefault(); const prefix = String(new FormData(e.currentTarget).get("prefix") ?? ""); onChange(fillGrid(src, prefix, known)); }}>
          <input name="prefix" aria-label="Field names start with" placeholder="e.g. tyre" style={{ width: 90 }} />
          <button type="submit" className="sm">Fill automatically</button>
        </form>
      </div>
      <p className="muted small">“Fill automatically” picks the field named start_row_column for each cell, e.g. tyre_driver_front_tread.</p>
    </div>
  );
}

function PhotoSettings({ part, set, ctx }: { part: Extract<Part, { type: "photos" }>; set: (p: Record<string, unknown>) => void; ctx: Ctx }) {
  const src = part.source;
  const photos = ctx.fields.filter((f) => f.type === "photo");
  const frame = part.frame ?? {};
  return (
    <>
      <Field label="Photos from">
        <Seg label="Photos from" value={src.kind} options={[["section", "A form section"], ["fields", "Fields I pick"], ["issues", "Every issue photo"]]}
          onChange={(k) => set({ source: k === "section" ? { kind: "section", section: ctx.sections[0]?.value ?? "inspection.section_1" } : k === "fields" ? { kind: "fields", fields: [] } : { kind: "issues" } })} />
      </Field>
      {src.kind === "section" && (
        <Field label="Form section"><select value={src.section} onChange={(e) => set({ source: { ...src, section: e.target.value } })}>
          {ctx.sections.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}</select></Field>)}
      {src.kind === "fields" && (
        <Field label="Photo fields">
          <div className="chips">{src.fields.map((f) => (
            <button key={f} type="button" className="chip" onClick={() => set({ source: { ...src, fields: src.fields.filter((x) => x !== f) } })}>{photos.find((p) => p.value === f)?.label ?? f} ✕</button>))}
            <select aria-label="Add a photo field" value="" style={{ width: "auto" }} onChange={(e) => e.target.value && set({ source: { ...src, fields: [...src.fields, e.target.value] } })}>
              <option value="">+ Add…</option>{photos.filter((p) => !src.fields.includes(p.value)).map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}</select>
          </div>
        </Field>)}
      {src.kind !== "issues" && <Field label="Which photos"><Seg label="Which photos" value={part.which ?? "all"} options={[["all", "All"], ["issues", "Only issue photos"], ["first", "First of each"]]} onChange={(which) => set({ which })} /></Field>}
      <Field label="Photos per row"><Seg label="Photos per row" value={part.per_row ?? 2} options={[[1, "1"], [2, "2"], [3, "3"], [4, "4"]]} onChange={(per_row) => set({ per_row })} /></Field>
      <More title="Photo shape and caption" summary={`${part.shape ?? "4:3"} · ${({ fill: "fill and crop", whole: "whole photo", top: "crop, keep top" } as const)[part.fit ?? "fill"]} · caption:
        ${({ label: "photo name", check: "check and answer", custom: "own text", none: "none" } as const)[part.caption ?? "label"]}`}>
        <Field label="Box shape"><Seg label="Box shape" value={part.shape ?? "4:3"} options={[["4:3", "4:3"], ["16:9", "16:9"], ["1:1", "Square"], ["original", "As taken"]]} onChange={(shape) => set({ shape })} /></Field>
        <Field label="When the photo does not fit"><Seg label="Fit" value={part.fit ?? "fill"} options={[["fill", "Fill and crop"], ["whole", "Show whole"], ["top", "Crop, keep top"]]} onChange={(fit) => set({ fit })} /></Field>
        <Field label="Caption"><Seg label="Caption" value={part.caption ?? "label"} options={[["label", "Photo name"], ["check", "Check + answer"], ["custom", "Own text"], ["none", "None"]]} onChange={(caption) => set({ caption })} /></Field>
        {part.caption === "custom" && <Field label="Caption text"><input value={part.caption_text ?? ""} onChange={(e) => set({ caption_text: e.target.value })} /></Field>}
        <div className="grid2">
          <Field label="Border"><select value={frame.border ?? "none"} onChange={(e) => set({ frame: { ...frame, border: e.target.value } })}><option value="none">None</option><option value="grey">Thin grey</option><option value="brand">Thin brand</option></select></Field>
          <Field label="Gap (mm)"><input type="number" min={0} max={12} value={frame.gap ?? 4} onChange={(e) => set({ frame: { ...frame, gap: Number(e.target.value) } })} /></Field>
        </div>
        <Toggle label="Round corners" checked={frame.round ?? true} onChange={(v) => set({ frame: { ...frame, round: v } })} />
      </More>
    </>
  );
}

const WHEN: [StyleRule["when"], string][] = [["problem", "the answer is a problem"], ["critical", "severity is critical"], ["major", "severity is major"],
  ["minor", "severity is minor"], ["bad", "the answer is red"], ["warn", "the answer is amber"], ["ok", "the answer is green"],
  ["not_checked", "it was not able to be checked"], ["empty", "there is no answer"]];

/** "When the answer is a problem: red label" — later rules win over earlier ones. */
function StyleRules({ rules, onChange, grid }: { rules: StyleRule[]; onChange: (r: StyleRule[]) => void; grid: boolean }) {
  const setRule = (i: number, p: Partial<StyleRule>) => onChange(rules.map((r, j) => (j === i ? clean({ ...r, ...p }) : r)));
  const tone = (label: string, v: string | undefined, onPick: (v: string | undefined) => void, tints = false) => (
    <Field label={label}><select value={v ?? ""} onChange={(e) => onPick(e.target.value || undefined)}>
      <option value="">{tints ? "None" : "Unchanged"}</option>
      {TONES.filter(([k]) => !tints || k !== "text").map(([k, l]) => <option key={k} value={k}>{tints ? `${l} tint` : l}</option>)}</select></Field>);
  return (
    <div className="rd-rules">
      {rules.map((r, i) => (
        <div key={i} className="rd-rule">
          <div className="bar" style={{ margin: 0 }}>
            <label className="grow">When <select aria-label={`Rule ${i + 1} when`} value={r.when} onChange={(e) => setRule(i, { when: e.target.value as StyleRule["when"] })}>
              {WHEN.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></label>
            <button type="button" className="link" aria-label={`Remove rule ${i + 1}`} onClick={() => onChange(rules.filter((_, j) => j !== i))}>✕</button>
          </div>
          <div className="grid2">
            {!grid && tone("Label colour", r.label, (label) => setRule(i, { label }))}
            {tone("Answer colour", r.value, (value) => setRule(i, { value }))}
            {tone(grid ? "Cell tint" : "Row tint", r.background, (background) => setRule(i, { background }), true)}
          </div>
          <Toggle label="Bold" checked={!!r.bold} onChange={(bold) => setRule(i, { bold: bold || undefined })} />
        </div>))}
      <button type="button" className="link" onClick={() => onChange([...rules, { when: "problem", value: "bad" }])}>+ Add rule</button>
      <p className="muted small">Severity comes from the answer options in the form builder. When two rules match, the lower one wins.</p>
    </div>
  );
}

function clean(r: StyleRule): StyleRule {
  return Object.fromEntries(Object.entries(r).filter(([, v]) => v !== undefined)) as StyleRule;
}

function HtmlSettings({ part, set, ctx }: { part: Extract<Part, { type: "html" }>; set: (p: Record<string, unknown>) => void; ctx: Ctx }) {
  const area = useRef<HTMLTextAreaElement>(null);
  const insert = (text: string) => {                   // at the cursor, or at the end
    const el = area.current, at = el?.selectionStart ?? part.html.length, to = el?.selectionEnd ?? at;
    set({ html: part.html.slice(0, at) + text + part.html.slice(to) });
  };
  return (
    <>
      <p className="muted small">For what the other parts cannot do. Plain HTML and CSS with values like {"{{ inspection.colour }}"}. No scripts, links or pictures; the CSS only styles this part. Colours: var(--brand), var(--ok), var(--bad)…</p>
      <Field label="HTML">
        <div className="bar" style={{ margin: "0 0 4px" }}><ValuePicker choices={ctx.fields.filter((f) => !NO_TEXT_TYPES.includes(f.type))} onPick={insert} /></div>
        <textarea ref={area} aria-label="HTML" className="mono" rows={10} spellCheck={false} value={part.html} onChange={(e) => set({ html: e.target.value })} />
      </Field>
      <Field label="CSS" help="e.g. .note { color: var(--brand) }">
        <textarea aria-label="CSS" className="mono" rows={6} spellCheck={false} value={part.css ?? ""} onChange={(e) => set({ css: e.target.value || undefined })} />
      </Field>
    </>
  );
}

function SnippetSettings({ part, set, items, onUnlink }: { part: Extract<Part, { type: "snippet" }>; set: (p: Record<string, unknown>) => void; items: SharedItem[]; onUnlink?: () => void }) {
  const item = items.find((i) => i.key === part.ref.key);
  return (
    <>
      {item ? <p>Shared part <strong>{item.name}</strong>, version {part.ref.revision}{item.revision > part.ref.revision ? ` (newest: ${item.revision})` : ""}.</p>
        : <p className="tone-bad">The shared part “{part.ref.key}” is not on this server.</p>}
      {item && <p className="muted small">Used by: {item.used_by.map((u) => u.form).join(", ")}. To change it for every report, change a copy here and save it back with “Share with other reports”, replacing “{item.name}”.</p>}
      <div className="bar">
        {item && item.revision > part.ref.revision && <button type="button" className="sm" onClick={() => set({ ref: { ...part.ref, revision: item.revision } })}>Use the newest version</button>}
        {item && onUnlink && <button type="button" className="sm" onClick={onUnlink}>Stop sharing (copy it into this report)</button>}
      </div>
    </>
  );
}
