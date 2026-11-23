import { useEffect, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { api, csrfToken, type Page } from "../../api/client";
import { useList, useRefresh } from "../../api/hooks";
import type { Booking, FormSummary } from "../../api/types";
import { Trash2 } from "lucide-react";
import { useAuth } from "../../auth";
import { ConditionBuilder } from "../../ui/ConditionBuilder";
import { Confirm, Empty, Field, PageHeader, Pill, useToast } from "../../ui/kit";
import { MoreMenu } from "../../ui/Menu";
import { fmtDay } from "../../lib/format";
import { useRefChoices, type RefChoice } from "../../lib/useChoices";

type Row = { field: string; label?: string };
/** One part of a report page (schema 2). Phase 3 replaces this screen with the full designer. */
export type Block = {
  type: string; show_if?: unknown; title?: string; html?: string; height?: number; per_row?: number;
  source?: { kind: string; rows?: Row[]; fields?: string[]; section?: string };
};
type ReportPage = { title: string; style?: string; parts: Block[] };
export type Definition = { schema: 2; filename?: string; pages: ReportPage[]; [k: string]: unknown };
type Template = { id: number; form: number; form_key: string; versions: { id: number; number: number; status: string }[] };
type TVersion = { id: number; template: number; number: number; status: string; definition: Definition; row_version: number };

export const BLOCK_LABEL: Record<string, string> = {
  table: "Table of checks", photos: "Photos", text: "Text", verify: "Verify code", page_break: "Page break", spacer: "Spacer",
};

/** A starter part of this type. */
export function newBlock(type: string): Block {
  switch (type) {
    case "table": return { type, title: "", source: { kind: "fields", rows: [] } };
    case "photos": return { type, title: "Photos", per_row: 2, source: { kind: "fields", fields: [] } };
    case "text": return { type, html: "" };
    case "spacer": return { type, height: 10 };
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

/** The parts of every page as one list, and a way to change that list back into pages. */
export function flatParts(def: Definition): { page: number; part: Block }[] {
  return (def.pages ?? []).flatMap((p, page) => p.parts.map((part) => ({ page, part })));
}
export function withParts(def: Definition, flat: { page: number; part: Block }[]): Definition {
  const pages = (def.pages ?? []).length ? def.pages : [{ title: "Page 1", parts: [] }];
  return { ...def, pages: pages.map((p, i) => ({ ...p, parts: flat.filter((x) => x.page === i).map((x) => x.part) })) };
}

export function PdfDesigner() {
  const { can } = useAuth();
  const { say, fail } = useToast();
  const refresh = useRefresh();
  const templates = useList<Template>("pdf-templates", "pdf-templates");
  const forms = useList<FormSummary>("forms", "forms");
  const [tid, setTid] = useState<number | null>(null);
  const t = (templates.data ?? []).find((x) => x.id === tid) ?? (templates.data ?? [])[0] ?? null;
  const formName = (x: Template) => (forms.data ?? []).find((f) => f.id === x.form)?.name ?? x.form_key;
  const editable = can("pdf_templates.edit");
  const withoutTemplate = (forms.data ?? []).filter((f) => f.type === "custom" && !(templates.data ?? []).some((x) => x.form === f.id));
  const make = useMutation({ mutationFn: (form: number) => api<Template>("pdf-templates", { body: { form } }), onSuccess: (r) => { void refresh("pdf-templates"); setTid(r.id); }, onError: fail });
  return (
    <>
      <PageHeader title="PDF templates">
        {editable && withoutTemplate.length > 0 && (
          <select aria-label="Create a template for" value="" onChange={(e) => e.target.value && make.mutate(Number(e.target.value))} style={{ maxWidth: 240 }}>
            <option value="">+ New template for…</option>{withoutTemplate.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}</select>)}
      </PageHeader>
      <div className="tabs" role="tablist" aria-label="Templates">{(templates.data ?? []).map((x) => (
        <button key={x.id} role="tab" aria-selected={(t?.id ?? null) === x.id} className={t?.id === x.id ? "on" : ""} onClick={() => setTid(x.id)}>{formName(x)}</button>))}</div>
      {t ? <Designer key={t.id} template={t} form={(forms.data ?? []).find((f) => f.id === t.form)} editable={editable} say={say} fail={fail} refresh={() => refresh("pdf-templates")} />
        : <Empty title="No PDF templates yet">Create one for an inspection form with “New template for…”.</Empty>}
    </>
  );
}

function Designer({ template, form, editable, say, fail, refresh }: { template: Template; form?: FormSummary; editable: boolean; say: (m: string) => void; fail: (e: unknown) => void; refresh: () => unknown }) {
  const draftMeta = template.versions.find((v) => v.status === "draft");
  const latest = template.versions[template.versions.length - 1];
  const vid = (draftMeta ?? latest)?.id;
  const ver = useQuery({ queryKey: ["pdf-version", vid], enabled: !!vid, queryFn: () => api<TVersion>(`pdf-template-versions/${vid}`) });
  const choices = useRefChoices(template.form);
  // bookings that can show this layout: inspected with this form, newest first
  const sample = useQuery({ queryKey: ["pdf-sample", form?.inspection_type], enabled: !!form?.inspection_type,
    queryFn: async () => (await Promise.all(["completed", "submitted"].map((stage) => api<Page<Booking>>("bookings", { query: { type: form!.inspection_type, stage } })))).flatMap((r) => r.results) });
  const [def, setDef] = useState<Definition>({ schema: 2, pages: [] });
  const [sel, setSel] = useState<number | null>(null);
  const [previewUrl, setPreviewUrl] = useState("");
  const [rendering, setRendering] = useState(false);
  const [bookingId, setBookingId] = useState("");
  const [changed, setChanged] = useState(false);
  const v = ver.data;
  const reload = useRefresh();
  useEffect(() => { if (v) { setDef({ ...v.definition, pages: v.definition.pages ?? [] }); setChanged(false); } }, [v]);
  const chosen = bookingId || sample.data?.[0]?.id || "";
  const draft = v?.status === "draft";
  const ok = editable && draft;
  const [discard, setDiscard] = useState(false);
  async function discardDraft() {
    try { await api(`pdf-template-versions/${v!.id}`, { method: "DELETE" }); setDiscard(false); say("Draft discarded. The live layout is unchanged."); await reload("pdf-version"); await reload("pdf-templates"); await refresh(); }
    catch (e) { setDiscard(false); fail(e); }
  }
  const edit = (d: Definition) => { setDef(d); setChanged(true); };
  const save = async (): Promise<TVersion | null> => {
    try {
      const r = await api<TVersion>(`pdf-template-versions/${v!.id}`, { method: "PATCH", body: { definition: def, row_version: v!.row_version } });
      setChanged(false);
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
    if (!v || !chosen) return;
    setRendering(true);
    try {
      if (ok && changed && !(await save())) return;          // a published layout cannot change: just render it
      const res = await fetch(`/api/v1/pdf-template-versions/${v.id}/preview`, { method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken() }, body: JSON.stringify({ booking: chosen }) });
      if (!res.ok) { say("Preview failed: pick a submitted booking inspected with this form."); return; }
      setPreviewUrl(URL.createObjectURL(await res.blob()));
    } finally { setRendering(false); }
  }
  useEffect(() => { if (v && chosen) void preview(); }, [v?.id, chosen]); // eslint-disable-line react-hooks/exhaustive-deps
  const flat = flatParts(def);
  const setFlat = (f: { page: number; part: Block }[]) => edit(withParts(def, f));
  const setBlock = (i: number, p: Partial<Block>) => setFlat(flat.map((x, j) => (j === i ? { ...x, part: { ...x.part, ...p } } : x)));
  const b = sel !== null ? flat[sel]?.part : undefined;
  const label = (blk: Block) => blk.title || (blk.html ? blk.html.replace(/<[^>]+>/g, "").slice(0, 24) : BLOCK_LABEL[blk.type] ?? blk.type);
  const lastPage = Math.max(0, (def.pages ?? []).length - 1);

  return (
    <>
      <div className="bar">
        {draftMeta ? <Pill tone="warn">Draft v{draftMeta.number}</Pill> : <Pill tone="ok">Live v{latest?.number}</Pill>}
        <span className="muted small grow">{draftMeta ? `${template.versions.some((x) => x.status === "published") ? "Reports use the live version until you publish. " : ""}${changed ? "Unsaved changes." : "Saved."}` : "This layout is live. Start a draft to change it."}</span>
        {editable && !draftMeta && <button className="primary" onClick={async () => { try { await api(`pdf-templates/${template.id}/drafts`, { body: {} }); await refresh(); } catch (e) { fail(e); } }}>Start a new draft</button>}
        {ok && <>
          <MoreMenu label="More template actions" items={[{ label: "Discard draft", danger: true, onClick: () => setDiscard(true), hidden: !template.versions.some((x) => x.status === "published") }]} />
          <button disabled={!changed} onClick={async () => { if (await save()) say("Saved."); }}>Save</button>
          <button className="primary" onClick={publish}>Publish</button></>}
      </div>
      {discard && <Confirm title="Discard this draft?" danger confirmLabel="Discard draft" onCancel={() => setDiscard(false)} onConfirm={discardDraft}><p>Your unpublished changes to this layout are thrown away. The live layout is not affected.</p></Confirm>}
      <div className="pdf-layout">
        <aside className="card pdf-blocks" aria-label="Blocks">
          <button className={`tree-item${sel === null ? " on" : ""}`} onClick={() => setSel(null)} style={{ width: "100%", border: 0, background: sel === null ? undefined : "none" }}>Page settings</button>
          <div className="rail-h" style={{ margin: "10px 8px 4px" }}>Blocks, top to bottom</div>
          {flat.map(({ page, part: blk }, i) => (
            <div key={i}>
              {(i === 0 || flat[i - 1]!.page !== page) && <div className="rail-h" style={{ margin: "8px 8px 2px" }}>{def.pages[page]?.title || `Page ${page + 1}`}</div>}
              <div className={`tree-item${sel === i ? " on" : ""}`} onClick={() => setSel(i)} role="button" tabIndex={0} onKeyDown={(e) => e.key === "Enter" && setSel(i)}>
                <span className="grow ellipsis" title={BLOCK_LABEL[blk.type]}>{label(blk)}</span>
                {ok && <span className="row-tools"><button className="link" aria-label="Move up" onClick={(e) => { e.stopPropagation(); setFlat(moveBlock(flat as never, i, i - 1) as never); setSel(Math.max(0, i - 1)); }}>↑</button>
                  <button className="link" aria-label="Move down" onClick={(e) => { e.stopPropagation(); setFlat(moveBlock(flat as never, i, i + 1) as never); setSel(Math.min(flat.length - 1, i + 1)); }}>↓</button></span>}
              </div>
            </div>
          ))}
          {ok && <select aria-label="Add a block" value="" style={{ marginTop: 8 }} onChange={(e) => { if (e.target.value) { setFlat([...flat, { page: lastPage, part: newBlock(e.target.value) }]); setSel(flat.length); } }}>
            <option value="">+ Add a block…</option>{Object.entries(BLOCK_LABEL).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>}
        </aside>
        <section className="pdf-preview" aria-label="Preview">
          <div className="bar">
            <span className="muted small">Preview with</span>
            <select aria-label="Booking for the preview" value={chosen} onChange={(e) => setBookingId(e.target.value)} style={{ maxWidth: 360 }}>
              {(sample.data ?? []).length === 0 && <option value="">No completed booking of this form yet</option>}
              {(sample.data ?? []).map((bk) => <option key={bk.id} value={bk.id}>{bk.booking_id} · {String(bk.answers.customer_name ?? "")} · {fmtDay(bk.answers.inspection_date)}</option>)}
            </select>
            <span className="grow" />
            <button className="sm" disabled={!chosen || rendering} onClick={preview}>{rendering ? "Rendering…" : changed ? "Save and refresh" : "Refresh"}</button>
            {previewUrl && <a className="btn sm" href={previewUrl} target="_blank" rel="noreferrer">Open full PDF</a>}
          </div>
          {previewUrl ? <iframe title="PDF preview" src={previewUrl} className="pdf-frame" />
            : <Empty title={chosen ? "Rendering the preview…" : "Nothing to preview yet"}>{chosen ? "" : "Complete one booking inspected with this form to see the layout with real answers."}</Empty>}
        </section>
        <aside className="card pdf-settings" aria-label={b ? "Block settings" : "Page settings"}>
          {b && sel !== null ? <BlockEditor block={b} ok={ok} choices={choices} onChange={(p) => setBlock(sel, p)} onDelete={() => { setFlat(flat.filter((_, j) => j !== sel)); setSel(null); }} /> : <>
            <h3 style={{ marginTop: 0 }}>Page settings</h3>
            <Field label="File name" tip="Values like {{ sys.booking_id }} are filled in for each report."><input disabled={!ok} value={def.filename ?? "{{ sys.booking_id }}.pdf"} onChange={(e) => edit({ ...def, filename: e.target.value })} /></Field>
            <p className="muted small">The full designer (pages, header and footer, colours, photo layouts) arrives in the next release. Templates made here keep working there.</p>
          </>}
        </aside>
      </div>
    </>
  );
}

function BlockEditor({ block, ok, choices, onChange, onDelete }: { block: Block; ok: boolean; choices: RefChoice[]; onChange: (p: Partial<Block>) => void; onDelete: () => void }) {
  const t = block.type;
  const src = block.source ?? { kind: "fields" };
  const rows = src.rows ?? [];
  const setRows = (r: Row[]) => onChange({ source: { ...src, rows: r } });
  const setRow = (i: number, p: Partial<Row>) => setRows(rows.map((r, j) => (j === i ? { ...r, ...p } : r)));
  const fields = src.fields ?? [];
  const setFields = (f: string[]) => onChange({ source: { ...src, fields: f } });
  const mediaChoices = choices.filter((c) => c.type === "photo");
  return (
    <div className="card">
      <h3>{BLOCK_LABEL[t] ?? t}</h3>
      <fieldset disabled={!ok} style={{ border: 0, padding: 0 }}>
        {(t === "table" || t === "photos") && <Field label="Title"><input value={block.title ?? ""} onChange={(e) => onChange({ title: e.target.value })} /></Field>}
        {t === "text" && <Field label="Text" tip="Simple formatting is kept (bold, lists). Values like {{ inspection.colour }} are filled in."><textarea value={block.html ?? ""} onChange={(e) => onChange({ html: e.target.value })} /></Field>}
        {t === "spacer" && <Field label="Height (mm)"><input type="number" min={1} max={200} value={block.height ?? 10} onChange={(e) => onChange({ height: Number(e.target.value) })} /></Field>}
        {t === "table" && src.kind === "fields" && (
          <>
            <strong>Rows (what the report calls each value)</strong>
            {rows.map((r, i) => (
              <div className="pdf-row" key={i}>
                <input aria-label="Report label" placeholder="Label on the report (default: the field's label)" value={r.label ?? ""} onChange={(e) => setRow(i, { label: e.target.value || undefined })} />
                <button className="link" aria-label="Remove row" onClick={() => setRows(rows.filter((_, j) => j !== i))}>✕</button>
                <select aria-label="Field" value={r.field} onChange={(e) => setRow(i, { field: e.target.value })}>
                  <option value="">Choose a field…</option>{choices.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}</select>
              </div>))}
            <button className="link" onClick={() => setRows([...rows, { field: "" }])}>+ Add row</button>
          </>
        )}
        {t === "table" && src.kind !== "fields" && <p className="muted small">This table is filled from {src.kind === "section" ? `the form section ${src.section}` : src.kind}. Change it in the full designer.</p>}
        {t === "photos" && src.kind === "fields" && (
          <>
            <Field label="Photos per row"><select value={block.per_row ?? 2} onChange={(e) => onChange({ per_row: Number(e.target.value) })}><option>1</option><option>2</option><option>3</option><option>4</option></select></Field>
            {fields.map((f, i) => (
              <div className="cond-row" key={i}>
                <select aria-label="Photo field" value={f} onChange={(e) => setFields(fields.map((x, j) => (j === i ? e.target.value : x)))}>
                  <option value="">Choose a photo field…</option>{mediaChoices.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}</select>
                <button className="link" aria-label="Remove photo" onClick={() => setFields(fields.filter((_, j) => j !== i))}>✕</button>
              </div>))}
            <button className="link" onClick={() => setFields([...fields, ""])}>+ Add a photo field</button>
          </>
        )}
        {t !== "page_break" && t !== "spacer" && (
          <ConditionBuilder label="Show this block only if" value={block.show_if ?? null} onChange={(r) => onChange({ show_if: r ?? undefined })} fields={choices.map((c) => ({ value: c.value, label: c.label }))} />
        )}
      </fieldset>
      {ok && <button className="danger" onClick={onDelete}>Delete block</button>}
    </div>
  );
}
