import { closestCenter, DndContext, KeyboardSensor, PointerSensor, useSensor, useSensors, type DragEndEvent } from "@dnd-kit/core";
import { SortableContext, sortableKeyboardCoordinates, useSortable, verticalListSortingStrategy } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { Code, Columns2, FileText, GripVertical, Image, LayoutList, ListOrdered, MoveVertical, QrCode, Scissors, Table2 } from "lucide-react";
import { useState, type ReactNode } from "react";
import type { FormPage } from "../../../api/types";
import { addPart, blankPage, movePage, movePart, newPart, pageFromForm, partName, updatePart, type Definition, type Part, type PartType, type ReportPage } from "./model";

export type Sel = { kind: "page" | "part"; id: string } | null;

const ICON: Record<PartType, typeof Table2> = {
  table: Table2, photos: Image, text: FileText, columns: Columns2, verify: QrCode, contents: ListOrdered, page_break: Scissors, spacer: MoveVertical, html: Code,
};
const ADD: { type: PartType; label: string; hint: string }[] = [
  { type: "table", label: "Table of checks", hint: "rows of check and answer" },
  { type: "photos", label: "Photos", hint: "a grid of photos" },
  { type: "text", label: "Text", hint: "headings, notes, disclaimer" },
  { type: "columns", label: "Side by side", hint: "e.g. photo next to a table" },
  { type: "verify", label: "Verify code", hint: "QR code for this report" },
  { type: "contents", label: "Contents list", hint: "pages and page numbers" },
  { type: "spacer", label: "Space", hint: "empty space" },
  { type: "page_break", label: "Page break", hint: "next part on a new page" },
  { type: "html", label: "Custom HTML", hint: "your own HTML and CSS, for experts" },
];

function Sortable({ id, children, disabled }: { id: string; children: (handle: ReactNode) => ReactNode; disabled: boolean }) {
  const s = useSortable({ id, disabled });
  const handle = disabled ? null : <span className="rd-grip" {...s.attributes} {...s.listeners} aria-label="Drag to move"><GripVertical size={13} aria-hidden /></span>;
  return <div ref={s.setNodeRef} style={{ transform: CSS.Transform.toString(s.transform), transition: s.transition, opacity: s.isDragging ? 0.5 : 1 }}>{children(handle)}</div>;
}

function AddMenu({ onPick, label = "+ Add to this page", small }: { onPick: (t: PartType) => void; label?: string; small?: boolean }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="rd-add">
      <button type="button" className={`link${small ? " small" : ""}`} aria-expanded={open} onClick={() => setOpen(!open)}>{label}</button>
      {open && (
        <div className="rd-add-menu" role="menu">
          {ADD.map((a) => { const I = ICON[a.type]; return (
            <button key={a.type} type="button" role="menuitem" onClick={() => { setOpen(false); onPick(a.type); }}>
              <I size={16} aria-hidden /><span><strong>{a.label}</strong><span className="muted small">{a.hint}</span></span>
            </button>); })}
        </div>)}
    </div>
  );
}

export function PagesPanel({ def, sel, onSelect, onChange, formPages, sections, readOnly }: {
  def: Definition; sel: Sel; onSelect: (s: Sel) => void; onChange: (d: Definition) => void;
  formPages: FormPage[]; sections: Record<string, string>; readOnly: boolean;
}) {
  const [adding, setAdding] = useState(false);
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 4 } }), useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }));
  const firstSection = Object.keys(sections)[0];
  const onDragEnd = (e: DragEndEvent) => {
    const a = String(e.active.id), o = e.over ? String(e.over.id) : null;
    if (!o || a === o) return;
    if (a.startsWith("pg:") && o.startsWith("pg:")) onChange(movePage(def, a.slice(3), o.slice(3)));
    else if (a.startsWith("pt:") && o.startsWith("pt:")) onChange(movePart(def, a.slice(3), o.slice(3)));
  };
  const add = (page: ReportPage, type: PartType) => {
    const part = newPart(type, firstSection);
    const after = sel?.kind === "part" && JSON.stringify(page.parts).includes(`"id":"${sel.id}"`) ? sel.id : null;
    onChange(addPart(def, page.id!, part, after));
    onSelect({ kind: "part", id: part.id! });
  };
  const addInto = (cols: Extract<Part, { type: "columns" }>, k: number, type: PartType) => {
    const part = newPart(type, firstSection);
    onChange(updatePart(def, cols.id!, { columns: cols.columns.map((c, i) => (i === k ? { ...c, parts: [...c.parts, part] } : c)) }));
    onSelect({ kind: "part", id: part.id! });
  };
  const newPage = (p: ReportPage) => { onChange({ ...def, pages: [...def.pages, p] }); onSelect({ kind: "page", id: p.id! }); setAdding(false); };

  const parts = (list: Part[], depth: number): ReactNode => (
    <SortableContext items={list.map((p) => `pt:${p.id}`)} strategy={verticalListSortingStrategy}>
      {list.map((p) => { const I = ICON[p.type]; return (
        <Sortable key={p.id} id={`pt:${p.id}`} disabled={readOnly}>{(handle) => (
          <>
            <div className={`rd-part${sel?.kind === "part" && sel.id === p.id ? " on" : ""}`} style={{ marginLeft: depth * 14 }}>
              {handle}
              <button type="button" className="rd-part-name" onClick={() => onSelect({ kind: "part", id: p.id! })}>
                <I size={14} aria-hidden /><span className="ellipsis">{partName(p, sections)}</span>
              </button>
              {p.show_if ? <span className="rd-badge" title="Only shown sometimes">if</span> : null}
            </div>
            {p.type === "columns" && p.columns.map((c, k) => (
              <div key={k} className="rd-col" style={{ marginLeft: (depth + 1) * 14 }}>
                <span className="rd-col-h">Column {k + 1}{c.width ? ` · ${c.width}%` : ""}</span>
                {parts(c.parts, depth + 1)}
                {!readOnly && <AddMenu small label="+ Add" onPick={(t) => addInto(p, k, t)} />}
              </div>))}
          </>)}
        </Sortable>); })}
    </SortableContext>
  );

  return (
    <div className="rd-pages-panel">
      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}>
        <SortableContext items={def.pages.map((p) => `pg:${p.id}`)} strategy={verticalListSortingStrategy}>
          {def.pages.map((pg, i) => (
            <Sortable key={pg.id} id={`pg:${pg.id}`} disabled={readOnly}>{(handle) => (
              <section className="rd-pg" aria-label={`Page ${i + 1}: ${pg.title}`}>
                <div className={`rd-pg-h${sel?.kind === "page" && sel.id === pg.id ? " on" : ""}`}>
                  {handle}
                  <button type="button" className="rd-pg-name" onClick={() => onSelect({ kind: "page", id: pg.id! })}>
                    <span className="rd-pg-n">{i + 1}</span><span className="ellipsis">{pg.title || "Untitled page"}</span>
                  </button>
                  {pg.style === "full" && <span className="rd-badge">full page</span>}
                  {pg.style === "cover" && <span className="rd-badge">cover</span>}
                  {pg.show_if ? <span className="rd-badge" title="Only shown sometimes">if</span> : null}
                </div>
                {parts(pg.parts, 0)}
                {!readOnly && <AddMenu onPick={(t) => add(pg, t)} />}
              </section>)}
            </Sortable>))}
        </SortableContext>
      </DndContext>
      {def.pages.length === 0 && <p className="muted small">No pages yet. Start with “+ Add page”: pick a page of the form and get a ready page to adjust.</p>}
      {!readOnly && (
        <div className="rd-add">
          <button type="button" className="sm" aria-expanded={adding} onClick={() => setAdding(!adding)}><LayoutList size={14} aria-hidden /> Add page</button>
          {adding && (
            <div className="rd-add-menu wide" role="menu" aria-label="Add page">
              <div className="rd-add-h">Make a page from a form page</div>
              {formPages.map((fp) => (
                <button key={fp.id} type="button" role="menuitem" onClick={() => newPage(pageFromForm(fp))}>
                  <Table2 size={16} aria-hidden /><span><strong>{fp.title}</strong><span className="muted small">{fp.sections.length} section{fp.sections.length === 1 ? "" : "s"}: a table each, then its issue photos</span></span>
                </button>))}
              <div className="rd-add-h">Or start from</div>
              <button type="button" role="menuitem" onClick={() => newPage(blankPage("blank"))}><FileText size={16} aria-hidden /><span><strong>Blank page</strong></span></button>
              <button type="button" role="menuitem" onClick={() => newPage(blankPage("divider"))}><ListOrdered size={16} aria-hidden /><span><strong>Divider</strong><span className="muted small">big title and the contents list</span></span></button>
              <button type="button" role="menuitem" onClick={() => newPage(blankPage("verify"))}><QrCode size={16} aria-hidden /><span><strong>Verify page</strong><span className="muted small">QR code and link</span></span></button>
            </div>)}
        </div>)}
    </div>
  );
}
