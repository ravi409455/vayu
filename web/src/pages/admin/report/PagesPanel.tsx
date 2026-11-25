import { closestCenter, DndContext, KeyboardSensor, PointerSensor, useSensor, useSensors, type DragEndEvent } from "@dnd-kit/core";
import { SortableContext, sortableKeyboardCoordinates, useSortable, verticalListSortingStrategy } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { ChevronDown, ChevronRight, Code, Columns2, Download, FileText, Link2, GripVertical, Image, LayoutList, ListOrdered, MoveVertical, QrCode, Scissors, Table2 } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import type { FormPage } from "../../../api/types";
import { addPart, blankPage, movePage, movePart, newPart, pageFromForm, pageOf, partName, sharedPart, uid, updatePart, type Definition, type Part, type PartType, type ReportPage, type SharedRef } from "./model";
import type { SharedItem } from "./sharing";

export type Sel = { kind: "page" | "part"; id: string } | null;

const ICON: Record<PartType, typeof Table2> = {
  table: Table2, photos: Image, text: FileText, columns: Columns2, verify: QrCode, button: Download, contents: ListOrdered, page_break: Scissors, spacer: MoveVertical, html: Code, snippet: Link2,
};
const ADD: { type: PartType; label: string; hint: string }[] = [
  { type: "table", label: "Table of checks", hint: "rows of check and answer" },
  { type: "photos", label: "Photos", hint: "a grid of photos" },
  { type: "text", label: "Text", hint: "headings, notes, disclaimer" },
  { type: "columns", label: "Side by side", hint: "e.g. photo next to a table" },
  { type: "verify", label: "Verify code", hint: "QR code for this report" },
  { type: "button", label: "Button link", hint: "download all photos or videos, verify" },
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

function AddMenu({ onPick, label = "+ Add to this page", small, snippets = [] }: { onPick: (t: PartType, ref?: SharedRef) => void; label?: string; small?: boolean; snippets?: SharedItem[] }) {
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
          {snippets.length > 0 && <div className="rd-add-h">Shared parts</div>}
          {snippets.map((sn) => (
            <button key={sn.id} type="button" role="menuitem" onClick={() => { setOpen(false); onPick("snippet", { key: sn.key, revision: sn.revision }); }}>
              <Link2 size={16} aria-hidden /><span><strong>{sn.name}</strong><span className="muted small">shared: change it once for every report</span></span>
            </button>))}
        </div>)}
    </div>
  );
}

export function PagesPanel({ def, sel, onSelect, onChange, formPages, sections, readOnly, snippets = [], bad = new Set(), onePage = false }: {
  def: Definition; sel: Sel; onSelect: (s: Sel) => void; onChange: (d: Definition) => void;
  formPages: FormPage[]; sections: Record<string, string>; readOnly: boolean; snippets?: SharedItem[]; bad?: Set<string>;
  /** a shared part: one list of parts, no pages to add */
  onePage?: boolean;
}) {
  const sharedNames = Object.fromEntries(snippets.map((x) => [x.key, x.name]));
  // pages fold up so a long report fits; the page of the part being changed opens by itself
  const [closed, setClosed] = useState<Set<string>>(() => new Set(def.pages.slice(1).map((p) => p.id!)));
  const toggle = (id: string) => setClosed((c) => { const n = new Set(c); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  useEffect(() => {
    if (sel?.kind !== "part") return;
    const pg = pageOf(def, sel.id);
    if (pg && closed.has(pg.id!)) setClosed((c) => { const n = new Set(c); n.delete(pg.id!); return n; });
  }, [sel]); // eslint-disable-line react-hooks/exhaustive-deps -- opens the page only when the selection moves; the person may fold it again
  const make = (type: PartType, ref?: SharedRef) => (ref ? sharedPart(ref) : newPart(type, firstSection));
  const [adding, setAdding] = useState(false);
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 4 } }), useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }));
  const firstSection = Object.keys(sections)[0];
  const onDragEnd = (e: DragEndEvent) => {
    const a = String(e.active.id), o = e.over ? String(e.over.id) : null;
    if (!o || a === o) return;
    if (a.startsWith("pg:") && o.startsWith("pg:")) onChange(movePage(def, a.slice(3), o.slice(3)));
    else if (a.startsWith("pt:") && o.startsWith("pt:")) onChange(movePart(def, a.slice(3), o.slice(3)));
  };
  const add = (page: ReportPage, type: PartType, ref?: SharedRef) => {
    const part = make(type, ref);
    const after = sel?.kind === "part" && pageOf(def, sel.id)?.id === page.id ? sel.id : null;
    onChange(addPart(def, page.id!, part, after));
    onSelect({ kind: "part", id: part.id! });
  };
  const addInto = (cols: Extract<Part, { type: "columns" }>, k: number, type: PartType, ref?: SharedRef) => {
    const part = make(type, ref);
    onChange(updatePart(def, cols.id!, { columns: cols.columns.map((c, i) => (i === k ? { ...c, parts: [...c.parts, part] } : c)) }));
    onSelect({ kind: "part", id: part.id! });
  };
  const newPage = (p: ReportPage) => { onChange({ ...def, pages: [...def.pages, p] }); onSelect({ kind: "page", id: p.id! }); setAdding(false); };

  const parts = (list: Part[], depth: number): ReactNode => (
    <SortableContext items={list.map((p) => `pt:${p.id}`)} strategy={verticalListSortingStrategy}>
      {list.map((p) => { const I = ICON[p.type]; return (
        <Sortable key={p.id} id={`pt:${p.id}`} disabled={readOnly}>{(handle) => (
          <>
            <div className={`rd-part${sel?.kind === "part" && sel.id === p.id ? " on" : ""}${bad.has(p.id!) ? " bad" : ""}`} style={{ marginLeft: depth * 14 }}>
              {handle}
              <button type="button" className="rd-part-name" onClick={() => onSelect({ kind: "part", id: p.id! })}>
                <I size={14} aria-hidden /><span className="ellipsis">{partName(p, sections, sharedNames)}</span>
              </button>
              {bad.has(p.id!) ? <span className="rd-badge bad" title="Uses a field or section the form does not have">fix</span> : null}
              {p.type === "snippet" ? <span className="rd-badge" title="Shared with other reports">shared</span> : null}
              {p.show_if ? <span className="rd-badge" title="Only shown sometimes">if</span> : null}
            </div>
            {p.type === "columns" && p.columns.map((c, k) => (
              <div key={k} className="rd-col" style={{ marginLeft: (depth + 1) * 14 }}>
                <span className="rd-col-h">Column {k + 1}{c.width ? ` · ${c.width}%` : ""}</span>
                {parts(c.parts, depth + 1)}
                {!readOnly && <AddMenu small label="+ Add" snippets={snippets} onPick={(t, r) => addInto(p, k, t, r)} />}
              </div>))}
          </>)}
        </Sortable>); })}
    </SortableContext>
  );

  return (
    <div className="rd-pages-panel">
      {def.pages.length > 1 && (
        <div className="bar small" style={{ margin: "0 0 4px" }}>
          <button type="button" className="link small" onClick={() => setClosed(new Set())}>Open all</button>
          <button type="button" className="link small" onClick={() => setClosed(new Set(def.pages.map((p) => p.id!)))}>Fold all</button>
        </div>)}
      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}>
        <SortableContext items={def.pages.map((p) => `pg:${p.id}`)} strategy={verticalListSortingStrategy}>
          {def.pages.map((pg, i) => (
            <Sortable key={pg.id} id={`pg:${pg.id}`} disabled={readOnly}>{(handle) => (
              <section className="rd-pg" aria-label={`Page ${i + 1}: ${pg.title}`}>
                <div className={`rd-pg-h${sel?.kind === "page" && sel.id === pg.id ? " on" : ""}`}>
                  {handle}
                  <button type="button" className="rd-fold" aria-expanded={!closed.has(pg.id!)} aria-label={`${closed.has(pg.id!) ? "Open" : "Fold"} page ${i + 1}`} onClick={() => toggle(pg.id!)}>
                    {closed.has(pg.id!) ? <ChevronRight size={14} aria-hidden /> : <ChevronDown size={14} aria-hidden />}</button>
                  <button type="button" className="rd-pg-name" onClick={() => onSelect({ kind: "page", id: pg.id! })}>
                    <span className="rd-pg-n">{i + 1}</span><span className="ellipsis">{pg.title || "Untitled page"}</span>
                  </button>
                  {pg.style === "full" && <span className="rd-badge">full page</span>}
                  {pg.style === "cover" && <span className="rd-badge">cover</span>}
                  {pg.show_if ? <span className="rd-badge" title="Only shown sometimes">if</span> : null}
                </div>
                {closed.has(pg.id!) ? <span className="muted small rd-folded">{pg.parts.length} part{pg.parts.length === 1 ? "" : "s"}{pg.parts.some((p) => bad.has(p.id!)) ? " · has something to fix" : ""}</span> : (
                  <>
                    {parts(pg.parts, 0)}
                    {!readOnly && <AddMenu snippets={snippets} onPick={(t, r) => add(pg, t, r)} />}
                  </>)}
              </section>)}
            </Sortable>))}
        </SortableContext>
      </DndContext>
      {def.pages.length === 0 && <p className="muted small">No pages yet. Start with “+ Add page”: pick a page of the form and get a ready page to adjust.</p>}
      {!readOnly && !onePage && (
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
              {snippets.map((sn) => (
                <button key={sn.id} type="button" role="menuitem" onClick={() => newPage({ id: uid(), title: sn.name, style: "normal", parts: [sharedPart({ key: sn.key, revision: sn.revision })] })}>
                  <Link2 size={16} aria-hidden /><span><strong>{sn.name}</strong><span className="muted small">a page with this shared part</span></span></button>))}
            </div>)}
        </div>)}
    </div>
  );
}
