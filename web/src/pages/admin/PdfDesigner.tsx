import { useEffect, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { api, csrfToken } from "../../api/client";
import { useList, useRefresh } from "../../api/hooks";
import type { FormSummary } from "../../api/types";
import { Trash2 } from "lucide-react";
import { useAuth } from "../../auth";
import { ConditionBuilder } from "../../ui/ConditionBuilder";
import { Confirm, Field, PageHeader, Pill, useToast } from "../../ui/kit";
import { useRefChoices, type RefChoice } from "../../lib/useChoices";

type Row = { label: string; field: string };
export type Block = {
  type: string; show_if?: unknown; font_size?: string; title?: string; text?: string; rows?: Row[];
  photo?: string; columns?: number; items?: { field: string; index?: number; caption?: string }[]; height?: number;
};
export type Definition = { filename?: string; type_code?: string; branding?: { title?: string; color?: string; watermark?: boolean }; blocks: Block[] };
type Template = { id: number; form: number; form_key: string; versions: { id: number; number: number; status: string }[] };
type TVersion = { id: number; template: number; number: number; status: string; definition: Definition; row_version: number };

export const BLOCK_LABEL: Record<string, string> = {
  cover: "Cover + info grid", table: "Two-column table", ratings: "Ratings row", documents: "Documents grid",
  photos: "Photo grid", heading: "Heading", text: "Text", page_break: "Page break", spacer: "Spacer",
};

/** A starter block of this type. */
export function newBlock(type: string): Block {
  switch (type) {
    case "cover": case "table": case "documents": return { type, rows: [], ...(type !== "cover" ? { title: "" } : {}) };
    case "ratings": return { type, title: "Overall Rating" };
    case "photos": return { type, title: "Photos", columns: 2, items: [] };
    case "heading": case "text": return { type, text: "" };
    case "spacer": return { type, height: 20 };
    default: return { type };
  }
}

export function moveBlock(blocks: Block[], from: number, to: number): Block[] {
  if (to < 0 || to >= blocks.length) return blocks;
  const out = [...blocks];
  const [b] = out.splice(from, 1);
  out.splice(to, 0, b!);
  return out;
}

export function PdfDesigner() {
  const { can } = useAuth();
  const { say, fail } = useToast();
  const refresh = useRefresh();
  const templates = useList<Template>("pdf-templates", "pdf-templates");
  const forms = useList<FormSummary>("forms", "forms");
  const [tid, setTid] = useState<number | null>(null);
  const t = (templates.data ?? []).find((x) => x.id === tid) ?? null;
  const editable = can("pdf_templates.edit");
  const withoutTemplate = (forms.data ?? []).filter((f) => f.type === "custom" && !(templates.data ?? []).some((x) => x.form === f.id));
  const make = useMutation({ mutationFn: (form: number) => api<Template>("pdf-templates", { body: { form } }), onSuccess: (r) => { void refresh("pdf-templates"); setTid(r.id); }, onError: fail });
  return (
    <>
      <PageHeader title="PDF templates" subtitle="How each inspection becomes a report: the blocks, the labels, the branding."
        tip="Every inspection form has one template. Build a draft, preview it with a real booking, then publish. Reports made afterwards use the new layout; old reports are not changed until regenerated.">
        {editable && withoutTemplate.length > 0 && (
          <select aria-label="Create a template for" value="" onChange={(e) => e.target.value && make.mutate(Number(e.target.value))} style={{ maxWidth: 240 }}>
            <option value="">+ New template for…</option>{withoutTemplate.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}</select>)}
      </PageHeader>
      <div className="bar">{(templates.data ?? []).map((x) => <button key={x.id} className={tid === x.id ? "primary" : ""} onClick={() => setTid(x.id)}>{x.form_key}</button>)}</div>
      {t ? <Designer key={t.id} template={t} editable={editable} say={say} fail={fail} refresh={() => refresh("pdf-templates")} /> : <p className="muted">Pick a template, or create one for an inspection form.</p>}
    </>
  );
}

function Designer({ template, editable, say, fail, refresh }: { template: Template; editable: boolean; say: (m: string) => void; fail: (e: unknown) => void; refresh: () => unknown }) {
  const draftMeta = template.versions.find((v) => v.status === "draft");
  const latest = template.versions[template.versions.length - 1];
  const vid = (draftMeta ?? latest)?.id;
  const ver = useQuery({ queryKey: ["pdf-version", vid], enabled: !!vid, queryFn: () => api<TVersion>(`pdf-template-versions/${vid}`) });
  const choices = useRefChoices(template.form);
  const [def, setDef] = useState<Definition>({ blocks: [] });
  const [sel, setSel] = useState<number | null>(null);
  const [previewUrl, setPreviewUrl] = useState("");
  const [bookingId, setBookingId] = useState("");
  const v = ver.data;
  const reload = useRefresh();
  useEffect(() => { if (v) setDef({ ...v.definition, blocks: v.definition.blocks ?? [] }); }, [v]);
  const draft = v?.status === "draft";
  const ok = editable && draft;
  const [discard, setDiscard] = useState(false);
  async function discardDraft() {
    try { await api(`pdf-template-versions/${v!.id}`, { method: "DELETE" }); setDiscard(false); say("Draft discarded. The live layout is unchanged."); await reload("pdf-version"); await reload("pdf-templates"); await refresh(); }
    catch (e) { setDiscard(false); fail(e); }
  }

  const save = async (): Promise<TVersion | null> => {
    try {
      const r = await api<TVersion>(`pdf-template-versions/${v!.id}`, { method: "PATCH", body: { definition: def, row_version: v!.row_version } });
      await reload("pdf-version");
      return r;
    } catch (e) { fail(e); return null; }
  };
  async function publish() {
    const saved = await save();
    if (!saved) return;
    try {
      await api(`pdf-template-versions/${v!.id}/publish`, { body: { row_version: saved.row_version } });
      say("Published. New PDFs use this layout."); await reload("pdf-version"); void refresh();
    } catch (e) { fail(e); }
  }
  async function preview() {
    if (ok && !(await save())) return;          // a published layout cannot change: just render it
    const res = await fetch(`/api/v1/pdf-template-versions/${v!.id}/preview`, { method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken() }, body: JSON.stringify({ booking: bookingId.trim() }) });
    if (!res.ok) { say("Preview failed: pick a submitted booking inspected with this form."); return; }
    setPreviewUrl(URL.createObjectURL(await res.blob()));
  }
  const setBlock = (i: number, p: Partial<Block>) => setDef({ ...def, blocks: def.blocks.map((b, j) => (j === i ? { ...b, ...p } : b)) });
  const b = sel !== null ? def.blocks[sel] : undefined;

  return (
    <>
      <div className="bar">
        {draftMeta ? <Pill tone="info">Draft v{draftMeta.number}</Pill> : <Pill tone="ok">Live v{latest?.number}</Pill>}
        {editable && !draftMeta && <button onClick={async () => { try { await api(`pdf-templates/${template.id}/drafts`, { body: {} }); await refresh(); } catch (e) { fail(e); } }}>Start a new draft</button>}
        {ok && <><button onClick={async () => { if (await save()) say("Saved."); }}>Save</button>
          {template.versions.some((x) => x.status === "published") && <button className="danger" onClick={() => setDiscard(true)}><Trash2 size={14} aria-hidden /> Discard draft</button>}
          <button className="primary" onClick={publish}>Publish</button></>}
        <span className="grow" />
        <input style={{ maxWidth: 300 }} placeholder="Booking (internal id) for the preview" value={bookingId} onChange={(e) => setBookingId(e.target.value)} />
        <button onClick={preview} disabled={!bookingId}>Preview PDF</button>
      </div>
      {discard && <Confirm title="Discard this draft?" danger confirmLabel="Discard draft" onCancel={() => setDiscard(false)} onConfirm={discardDraft}><p>Your unpublished changes to this layout are thrown away. The live layout is not affected.</p></Confirm>}
      <div className="split">
        <div className="card">
          <h3>Layout</h3>
          <Field label="File name"><input disabled={!ok} value={def.filename ?? "{booking_id}{type_code}.pdf"} onChange={(e) => setDef({ ...def, filename: e.target.value })} /></Field>
          <Field label="Type code (added to the name)"><input disabled={!ok} value={def.type_code ?? ""} onChange={(e) => setDef({ ...def, type_code: e.target.value })} /></Field>
          <Field label="Header title"><input disabled={!ok} value={def.branding?.title ?? ""} onChange={(e) => setDef({ ...def, branding: { ...def.branding, title: e.target.value } })} /></Field>
          <Field label="Header colour"><input type="color" disabled={!ok} value={def.branding?.color ?? "#a62830"} onChange={(e) => setDef({ ...def, branding: { ...def.branding, color: e.target.value } })} /></Field>
          <label className="check"><input type="checkbox" disabled={!ok} checked={!!def.branding?.watermark} onChange={(e) => setDef({ ...def, branding: { ...def.branding, watermark: e.target.checked } })} /> Watermark</label>
          <h3>Blocks</h3>
          {def.blocks.map((blk, i) => (
            <div key={i} className={`tree-item${sel === i ? " on" : ""}`} onClick={() => setSel(i)}>
              <span className="grow">{BLOCK_LABEL[blk.type]}{blk.title ? ` · ${blk.title}` : blk.text ? ` · ${blk.text.slice(0, 18)}` : ""}</span>
              {ok && <><button className="link" aria-label="Move up" onClick={(e) => { e.stopPropagation(); setDef({ ...def, blocks: moveBlock(def.blocks, i, i - 1) }); setSel(Math.max(0, i - 1)); }}>↑</button>
                <button className="link" aria-label="Move down" onClick={(e) => { e.stopPropagation(); setDef({ ...def, blocks: moveBlock(def.blocks, i, i + 1) }); setSel(Math.min(def.blocks.length - 1, i + 1)); }}>↓</button></>}
            </div>
          ))}
          {ok && <select aria-label="Add a block" value="" onChange={(e) => { if (e.target.value) { setDef({ ...def, blocks: [...def.blocks, newBlock(e.target.value)] }); setSel(def.blocks.length); } }}>
            <option value="">+ Add a block…</option>{Object.entries(BLOCK_LABEL).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>}
        </div>
        <div>
          {b && sel !== null && <BlockEditor block={b} ok={ok} choices={choices} onChange={(p) => setBlock(sel, p)} onDelete={() => { setDef({ ...def, blocks: def.blocks.filter((_, j) => j !== sel) }); setSel(null); }} />}
          {previewUrl && <iframe title="PDF preview" src={previewUrl} style={{ width: "100%", height: 700, border: "1px solid var(--line)", borderRadius: 10, marginTop: 12 }} />}
        </div>
      </div>
    </>
  );
}

function BlockEditor({ block, ok, choices, onChange, onDelete }: { block: Block; ok: boolean; choices: RefChoice[]; onChange: (p: Partial<Block>) => void; onDelete: () => void }) {
  const t = block.type;
  const rows = block.rows ?? [];
  const setRow = (i: number, p: Partial<Row>) => onChange({ rows: rows.map((r, j) => (j === i ? { ...r, ...p } : r)) });
  const mediaChoices = choices.filter((c) => ["photo", "signature", "file"].includes(c.type));
  return (
    <div className="card">
      <h3>{BLOCK_LABEL[t]}</h3>
      <fieldset disabled={!ok} style={{ border: 0, padding: 0 }}>
        {(t === "table" || t === "documents" || t === "ratings" || t === "photos") && <Field label="Title"><input value={block.title ?? ""} onChange={(e) => onChange({ title: e.target.value })} /></Field>}
        {(t === "heading" || t === "text") && <Field label="Text"><textarea value={block.text ?? ""} onChange={(e) => onChange({ text: e.target.value })} /></Field>}
        {t === "spacer" && <Field label="Height"><input type="number" min={1} max={200} value={block.height ?? 20} onChange={(e) => onChange({ height: Number(e.target.value) })} /></Field>}
        {t === "cover" && <Field label="Hero photo"><select value={block.photo ?? ""} onChange={(e) => onChange({ photo: e.target.value || undefined })}><option value="">None</option>{mediaChoices.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}</select></Field>}
        {(t === "cover" || t === "table" || t === "documents") && (
          <>
            <strong>Rows (what the report calls each value)</strong>
            {rows.map((r, i) => (
              <div className="cond-row" key={i}>
                <input aria-label="Report label" placeholder="Label on the report" value={r.label} onChange={(e) => setRow(i, { label: e.target.value })} />
                <select aria-label="Field" value={r.field} onChange={(e) => setRow(i, { field: e.target.value, label: r.label || (choices.find((c) => c.value === e.target.value)?.label.split(": ")[1] ?? "") })}>
                  <option value="">Choose a field…</option>{choices.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}</select>
                <button className="link" aria-label="Remove row" onClick={() => onChange({ rows: rows.filter((_, j) => j !== i) })}>✕</button>
              </div>))}
            <button className="link" onClick={() => onChange({ rows: [...rows, { label: "", field: "" }] })}>+ Add row</button>
          </>
        )}
        {t === "photos" && (
          <>
            <Field label="Photos per row"><select value={block.columns ?? 2} onChange={(e) => onChange({ columns: Number(e.target.value) })}><option>1</option><option>2</option><option>3</option></select></Field>
            {(block.items ?? []).map((it, i) => (
              <div className="cond-row" key={i}>
                <select aria-label="Photo field" value={it.field} onChange={(e) => onChange({ items: block.items!.map((x, j) => (j === i ? { ...x, field: e.target.value } : x)) })}>
                  <option value="">Choose a photo field…</option>{mediaChoices.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}</select>
                <input aria-label="Which photo (0 = first)" type="number" min={0} value={it.index ?? 0} onChange={(e) => onChange({ items: block.items!.map((x, j) => (j === i ? { ...x, index: Number(e.target.value) } : x)) })} style={{ maxWidth: 80 }} />
                <input aria-label="Caption" placeholder="Caption" value={it.caption ?? ""} onChange={(e) => onChange({ items: block.items!.map((x, j) => (j === i ? { ...x, caption: e.target.value } : x)) })} />
                <button className="link" aria-label="Remove photo" onClick={() => onChange({ items: block.items!.filter((_, j) => j !== i) })}>✕</button>
              </div>))}
            <button className="link" onClick={() => onChange({ items: [...(block.items ?? []), { field: "", index: 0, caption: "" }] })}>+ Add a photo</button>
          </>
        )}
        {t !== "page_break" && t !== "spacer" && (
          <>
            <Field label="Text size"><select value={block.font_size ?? "medium"} onChange={(e) => onChange({ font_size: e.target.value })}><option value="small">Small</option><option value="medium">Medium</option><option value="large">Large</option></select></Field>
            <ConditionBuilder label="Show this block only if" value={block.show_if ?? null} onChange={(r) => onChange({ show_if: r ?? undefined })} fields={choices.map((c) => ({ value: c.value, label: c.label }))} />
          </>
        )}
      </fieldset>
      {ok && <button className="danger" onClick={onDelete}>Delete block</button>}
    </div>
  );
}
