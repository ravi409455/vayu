import {
  closestCenter, DndContext, KeyboardSensor, PointerSensor, useSensor, useSensors, type DragEndEvent,
} from "@dnd-kit/core";
import { SortableContext, sortableKeyboardCoordinates, useSortable, verticalListSortingStrategy } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { EyeOff, FileText, GitBranch, GripVertical, Link2, Lock, PanelLeftClose, PanelLeftOpen, Plus, ShieldCheck } from "lucide-react";
import { useState } from "react";
import type { FormField, FormPage, FormSection } from "../../../api/types";
import type { Ref } from "../../../lib/tree";
import { iconFor, typeSummary } from "../../../lib/fieldTypes";
import { Pill, pressable } from "../../../ui/kit";

export type Sel = Ref | null;
const sid = (r: Ref) => `${r.kind}:${r.id}`;
const parse = (id: string | number): Ref => { const [kind, n] = String(id).split(":"); return { kind: kind as Ref["kind"], id: Number(n) }; };

export function Handle({ listeners, attributes, label }: { listeners?: object; attributes?: object; label: string }) {
  return <button type="button" className="grip" aria-label={label} title="Drag to reorder" {...attributes} {...listeners}><GripVertical size={16} aria-hidden /></button>;
}

function PageTab({ page, active, onSelect, readOnly }: { page: FormPage; active: boolean; onSelect: () => void; readOnly: boolean }) {
  const s = useSortable({ id: sid({ kind: "page", id: page.id }), data: { kind: "page" }, disabled: readOnly });
  const fields = page.sections.reduce((n, x) => n + x.fields.length, 0);
  return (
    <div ref={s.setNodeRef} style={{ transform: CSS.Transform.toString(s.transform), transition: s.transition, opacity: s.isDragging ? 0.5 : 1 }}
      className={`rail-item${active ? " on" : ""}`} {...pressable(onSelect)}>
      {!readOnly && <Handle listeners={s.listeners} attributes={s.attributes} label={`Move page ${page.title}`} />}
      <FileText size={15} aria-hidden />
      <span className="grow ellipsis">{page.title}</span>
      {page.gate && <span title="People must finish this page before moving on"><Lock size={13} aria-label="Gated" /></span>}
      <span className="muted small">{fields}</span>
    </div>
  );
}

function FieldRow({ field, selected, onSelect, readOnly }: { field: FormField; selected: boolean; onSelect: () => void; readOnly: boolean }) {
  const s = useSortable({ id: sid({ kind: "field", id: field.id }), data: { kind: "field" }, disabled: readOnly });
  const Icon = iconFor(field.type);
  const logic = !!(field.show_if || field.required_if);
  const access = Object.keys(field.access ?? {}).length > 0;
  return (
    <div ref={s.setNodeRef} style={{ transform: CSS.Transform.toString(s.transform), transition: s.transition, opacity: s.isDragging ? 0.5 : 1 }}
      className={`field-row${selected ? " on" : ""}`} onClick={(e) => { e.stopPropagation(); onSelect(); }} role="button" tabIndex={0}
      onKeyDown={(e) => { if (e.key === "Enter" && e.target === e.currentTarget) onSelect(); }}>
      {!readOnly && <Handle listeners={s.listeners} attributes={s.attributes} label={`Move field ${field.label || field.key}`} />}
      <span className="type-badge sm"><Icon size={14} aria-hidden /></span>
      <span className="grow ellipsis" title={field.key}><strong>{field.label || field.key}</strong>{(field.required || !!field.required_if) && <span className="req" aria-label="required"> *</span>}</span>
      <span className="type-tag">{typeSummary(field)}</span>
      {!field.visible && <span title="Hidden"><EyeOff size={14} aria-label="Hidden" /></span>}
      {logic && <span title="Has rules (shows or is required only sometimes)"><GitBranch size={14} aria-label="Has rules" /></span>}
      {access && <span title="Custom access"><ShieldCheck size={14} aria-label="Custom access" /></span>}
      {field.library && <span title="Linked to the library"><Link2 size={14} aria-label="Library" /></span>}
      {field.is_system && <Pill>system</Pill>}
    </div>
  );
}

function SectionCard({ section, selected, selectedField, onSelect, onSelectField, onAddField, readOnly }: {
  section: FormSection; selected: boolean; selectedField: number | null; onSelect: () => void; onSelectField: (id: number) => void; onAddField: () => void; readOnly: boolean;
}) {
  const s = useSortable({ id: sid({ kind: "section", id: section.id }), data: { kind: "section" }, disabled: readOnly });
  return (
    <section ref={s.setNodeRef} aria-label={section.title} style={{ transform: CSS.Transform.toString(s.transform), transition: s.transition, opacity: s.isDragging ? 0.5 : 1 }}
      className={`sec-card${selected ? " on" : ""}`}>
      <header className="sec-head" {...pressable(onSelect)}>
        {!readOnly && <Handle listeners={s.listeners} attributes={s.attributes} label={`Move section ${section.title}`} />}
        <strong className="grow">{section.title}</strong>
        {section.library && <Pill tone={section.library.update_available ? "warn" : "info"}><Link2 size={11} aria-hidden /> Library{section.library.update_available ? ": update" : ""}</Pill>}
        <span className="muted small">{section.fields.length} field{section.fields.length === 1 ? "" : "s"}</span>
      </header>
      <SortableContext items={section.fields.map((f) => sid({ kind: "field", id: f.id }))} strategy={verticalListSortingStrategy}>
        <div className="sec-body">
          {section.fields.map((f) => <FieldRow key={f.id} field={f} selected={selectedField === f.id} onSelect={() => onSelectField(f.id)} readOnly={readOnly} />)}
          {section.fields.length === 0 && <p className="muted small" style={{ padding: "8px 4px" }}>Empty. Drag a field here or add one.</p>}
        </div>
      </SortableContext>
      {!readOnly && !section.locked && <button type="button" className="add-row" onClick={onAddField}><Plus size={14} aria-hidden /> Add field</button>}
    </section>
  );
}

/** Pages on the left, the sections and fields of the chosen page in the middle. Everything can
 *  be dragged (or moved with the keyboard: focus the grip, Space, arrow keys, Space). */
export function Canvas({ pages, pageId, sel, onSelect, onPage, onDrag, onAddPage, onAddSection, onAddField, readOnly }: {
  pages: FormPage[]; pageId: number | null; sel: Sel; onSelect: (r: Ref) => void; onPage: (id: number) => void;
  onDrag: (active: Ref, over: Ref) => void; onAddPage: () => void; onAddSection: (pageId: number) => void; onAddField: (sectionId: number) => void; readOnly: boolean;
}) {
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }), useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }));
  const page = pages.find((p) => p.id === pageId) ?? pages[0];
  // the pages list folds to page numbers, giving the questions and the settings more room
  const [folded, setFolded] = useState(() => { try { return localStorage.getItem("vayu:builder-pages") === "folded"; } catch { return false; } });
  const fold = (v: boolean) => { setFolded(v); try { localStorage.setItem("vayu:builder-pages", v ? "folded" : "open"); } catch { /* not remembered */ } };
  function end(e: DragEndEvent) {
    if (!e.over) return;
    onDrag(parse(e.active.id), parse(e.over.id));
  }
  return (
    <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={end}>
      <div className={`builder-cols${folded ? " folded" : ""}`}>
        {folded ? (
          <aside className="rail" aria-label="Pages">
            <button type="button" className="icon-only" aria-label="Show pages" title="Show pages" onClick={() => fold(false)}><PanelLeftOpen size={16} aria-hidden /></button>
            {pages.map((p, i) => <button key={p.id} type="button" className={`rail-num${p.id === page?.id ? " on" : ""}`} title={p.title} aria-label={`Page ${i + 1}: ${p.title}`}
              onClick={() => { onPage(p.id); onSelect({ kind: "page", id: p.id }); }}>{i + 1}</button>)}
          </aside>
        ) : (
        <aside className="rail" aria-label="Pages">
          <div className="rail-title rail-title-row">Pages
            <button type="button" className="icon-only" aria-label="Hide pages" title="Hide pages" onClick={() => fold(true)}><PanelLeftClose size={15} aria-hidden /></button></div>
          <SortableContext items={pages.map((p) => sid({ kind: "page", id: p.id }))} strategy={verticalListSortingStrategy}>
            {pages.map((p) => <PageTab key={p.id} page={p} active={p.id === page?.id} onSelect={() => { onPage(p.id); onSelect({ kind: "page", id: p.id }); }} readOnly={readOnly} />)}
          </SortableContext>
          {!readOnly && <button type="button" className="add-row" onClick={onAddPage}><Plus size={14} aria-hidden /> Add page</button>}
        </aside>)}
        <div className="canvas" aria-label="Questions">
          {page && (
            <>
              {/* eslint-disable-next-line jsx-a11y/click-events-have-key-events, jsx-a11y/no-static-element-interactions -- the same as the page's tab in the rail, which takes the keyboard */}
              <div className="canvas-head" onClick={() => onSelect({ kind: "page", id: page.id })}>
                <h2>{page.title}</h2>
                {page.gate && <Pill tone="warn"><Lock size={11} aria-hidden /> Must be finished to continue</Pill>}
                {!page.visible && <Pill>Hidden</Pill>}
              </div>
              <SortableContext items={page.sections.map((s) => sid({ kind: "section", id: s.id }))} strategy={verticalListSortingStrategy}>
                {page.sections.map((s) => (
                  <SectionCard key={s.id} section={s} selected={sel?.kind === "section" && sel.id === s.id} selectedField={sel?.kind === "field" ? sel.id : null}
                    onSelect={() => onSelect({ kind: "section", id: s.id })} onSelectField={(id) => onSelect({ kind: "field", id })} onAddField={() => onAddField(s.id)} readOnly={readOnly} />
                ))}
              </SortableContext>
              {page.sections.length === 0 && <div className="empty-state">This page has no sections yet.</div>}
              {!readOnly && <button type="button" className="add-section" onClick={() => onAddSection(page.id)}><Plus size={16} aria-hidden /> Add section</button>}
            </>
          )}
        </div>
      </div>
    </DndContext>
  );
}
