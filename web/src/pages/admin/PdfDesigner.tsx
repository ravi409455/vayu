import { AlertTriangle, Settings2 } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { api, ApiError, type Page } from "../../api/client";
import { useList, useRefresh } from "../../api/hooks";
import type { Booking, FormSummary, FormVersion } from "../../api/types";
import { useAuth } from "../../auth";
import { fmtDay } from "../../lib/format";
import { useRefChoices } from "../../lib/useChoices";
import { Confirm, Empty, PageHeader, Pill, useToast } from "../../ui/kit";
import { MoreMenu } from "../../ui/Menu";
import { findPart, locate, partName, removePart, shiftPart, updatePage, updatePart, withIds, type Definition, type Part } from "./report/model";
import { PagesPanel, type Sel } from "./report/PagesPanel";
import { PageSettings, PartSettings, type SectionChoice } from "./report/PartSettings";
import { Preview, type LayoutPage } from "./report/Preview";
import { ReportSettings } from "./report/ReportSettings";

type Template = { id: number; form: number; form_key: string; versions: { id: number; number: number; status: string }[] };
type TVersion = { id: number; template: number; number: number; status: string; definition: Definition; row_version: number };
type Issue = { code: string; message: string };
type Unused = { key: string; label: string; section: string };

export function PdfDesigner() {
  const { can } = useAuth();
  const { fail } = useToast();
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
      {t ? <Designer key={t.id} template={t} form={(forms.data ?? []).find((f) => f.id === t.form)} editable={editable} refresh={() => refresh("pdf-templates")} />
        : <Empty title="No PDF templates yet">Create one for an inspection form with “New template for…”.</Empty>}
    </>
  );
}

/** Every part of the definition with its name (for the preview's outlines). */
function names(d: Definition, sections: Record<string, string>): Record<string, string> {
  const out: Record<string, string> = {};
  const walk = (parts: Part[]) => parts.forEach((p) => { out[p.id!] = partName(p, sections); if (p.type === "columns") p.columns.forEach((c) => walk(c.parts)); });
  d.pages.forEach((pg) => walk(pg.parts));
  return out;
}

function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value);
  useEffect(() => { const h = setTimeout(() => setV(value), ms); return () => clearTimeout(h); }, [value, ms]);
  return v;
}

function Designer({ template, form, editable, refresh }: { template: Template; form?: FormSummary; editable: boolean; refresh: () => unknown }) {
  const { say, fail } = useToast();
  const reload = useRefresh();
  const draftMeta = template.versions.find((v) => v.status === "draft");
  const latest = template.versions[template.versions.length - 1];
  const vid = (draftMeta ?? latest)?.id;
  const ver = useQuery({ queryKey: ["pdf-version", vid], enabled: !!vid, queryFn: () => api<TVersion>(`pdf-template-versions/${vid}`) });
  const formVersionId = form?.draft_version?.id ?? form?.published_version?.id;
  const tree = useQuery({ queryKey: ["form-version", formVersionId], enabled: !!formVersionId, queryFn: () => api<FormVersion>(`form-versions/${formVersionId}`) });
  const choices = useRefChoices(template.form);
  const sample = useQuery({ queryKey: ["pdf-sample", form?.inspection_type], enabled: !!form?.inspection_type,
    queryFn: async () => (await Promise.all(["completed", "submitted"].map((stage) => api<Page<Booking>>("bookings", { query: { type: form!.inspection_type, stage } })))).flatMap((r) => r.results) });
  const [def, setDef] = useState<Definition | null>(null);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState<"saved" | "saving" | "error">("saved");
  const rowVersion = useRef(0);
  const [sel, setSel] = useState<Sel>(null);
  const [bookingId, setBookingId] = useState("");
  const [settings, setSettings] = useState(false);
  const [discard, setDiscard] = useState(false);
  const [showWarnings, setShowWarnings] = useState(false);
  const [preview, setPreview] = useState<{ pdf: string; pages: LayoutPage[] } | null>(null);
  const [rendering, setRendering] = useState(false);
  const [checks, setChecks] = useState<{ issues: Issue[]; unused: Unused[] }>({ issues: [], unused: [] });
  const v = ver.data;
  const draft = v?.status === "draft";
  const ok = editable && draft;
  const chosen = bookingId || sample.data?.[0]?.id || "";

  useEffect(() => { if (v) { setDef(withIds({ ...v.definition, pages: v.definition.pages ?? [] })); rowVersion.current = v.row_version; setDirty(false); setSaving("saved"); } }, [v]);

  const sections: SectionChoice[] = useMemo(() => (tree.data?.pages ?? []).flatMap((p) => p.sections.filter((s) => s.key).map((s) => ({
    value: `inspection.${s.key}`, label: `${p.title} → ${s.title} (${s.fields.length})`, fields: s.fields.map((f) => ({ key: f.key, label: f.label || f.key, type: f.type })) }))), [tree.data]);
  const sectionNames = useMemo(() => Object.fromEntries((tree.data?.pages ?? []).flatMap((p) => p.sections.map((s) => [`inspection.${s.key}`, s.title]))), [tree.data]);
  const fieldChoices = useMemo(() => choices.map((c) => ({ value: c.value, label: c.label, type: c.type })), [choices]);

  const edit = (d: Definition) => { setDef(d); setDirty(true); };

  // autosave: the draft follows every change, a moment after it
  const saved = useDebounced(def, 700);
  const saveChain = useRef<Promise<unknown>>(Promise.resolve());
  const save = (d: Definition) => {
    saveChain.current = saveChain.current.then(async () => {
      setSaving("saving");
      try {
        const r = await api<TVersion>(`pdf-template-versions/${v!.id}`, { method: "PATCH", body: { definition: d, row_version: rowVersion.current } });
        rowVersion.current = r.row_version;
        setSaving("saved");
      } catch (e) {
        setSaving("error");
        if (e instanceof ApiError && e.code === "STALE_DRAFT") say("Someone else changed this draft. Reload the page to see their version.");
        else fail(e);
      }
    });
    return saveChain.current;
  };
  useEffect(() => { if (ok && dirty && saved) { setDirty(false); void save(saved); } }, [saved]); // eslint-disable-line react-hooks/exhaustive-deps

  // live preview and checks, a moment after each change (unsaved edits included)
  const shown = useDebounced(def, 500);
  const ticket = useRef(0);
  useEffect(() => {
    if (!shown || !v) return;
    const n = ++ticket.current;
    void api<{ issues: Issue[]; unused: Unused[] }>(`pdf-template-versions/${v.id}/checks`, { body: { definition: shown } }).then((r) => { if (n === ticket.current) setChecks(r); }).catch(() => {});
    if (!chosen) return;
    setRendering(true);
    api<{ pdf: string; pages: LayoutPage[] }>(`pdf-template-versions/${v.id}/preview`, { body: { booking: chosen, definition: shown } })
      .then((r) => { if (n === ticket.current) setPreview(r); })
      .catch((e) => { if (n === ticket.current) fail(e); })
      .finally(() => { if (n === ticket.current) setRendering(false); });
  }, [shown, chosen, v?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  async function publish() {
    if (!def || !v) return;
    await save(def);
    try {
      await api(`pdf-template-versions/${v.id}/publish`, { body: { row_version: rowVersion.current } });
      say("Published. New and re-made reports use this layout."); await reload("pdf-version"); void refresh();
    } catch (e) { fail(e); setShowWarnings(true); }
  }
  async function discardDraft() {
    try { await api(`pdf-template-versions/${v!.id}`, { method: "DELETE" }); setDiscard(false); say("Draft discarded. The live layout is unchanged."); await reload("pdf-version"); await refresh(); }
    catch (e) { setDiscard(false); fail(e); }
  }
  function openPdf() {
    if (!preview) return;
    const blob = new Blob([Uint8Array.from(atob(preview.pdf), (c) => c.charCodeAt(0))], { type: "application/pdf" });
    window.open(URL.createObjectURL(blob), "_blank", "noopener");
  }

  if (!def || !v) return <p className="muted">Loading…</p>;
  const part = sel?.kind === "part" ? findPart(def, sel.id) : null;
  const page = sel?.kind === "page" ? def.pages.find((p) => p.id === sel.id) : null;
  const nameMap = names(def, sectionNames);
  const warnCount = checks.issues.length + checks.unused.length;
  return (
    <>
      <div className="bar rd-top">
        {draftMeta ? <Pill tone="warn">Draft v{draftMeta.number}, not live yet</Pill> : <Pill tone="ok">Live v{latest?.number}</Pill>}
        <span className="muted small">{!draft ? "Start a draft to change it." : saving === "saving" ? "Saving…" : saving === "error" ? "Not saved" : "All changes saved"}</span>
        <span className="grow" />
        <label className="bar small muted" style={{ margin: 0 }}>Show with
          <select aria-label="Booking for the preview" value={chosen} onChange={(e) => setBookingId(e.target.value)} style={{ maxWidth: 280 }}>
            {(sample.data ?? []).length === 0 && <option value="">No completed booking of this form yet</option>}
            {(sample.data ?? []).map((bk) => <option key={bk.id} value={bk.id}>{bk.booking_id} · {String(bk.answers.customer_name ?? "")} · {fmtDay(bk.answers.inspection_date)}</option>)}
          </select></label>
        <div className="menu-wrap">
          <button type="button" aria-expanded={showWarnings} className={checks.issues.length ? "danger" : ""} onClick={() => setShowWarnings(!showWarnings)}>
            <AlertTriangle size={14} aria-hidden /> {warnCount ? `${warnCount} warning${warnCount === 1 ? "" : "s"}` : "No warnings"}</button>
          {showWarnings && (
            <div className="menu rd-warn" role="dialog" aria-label="Warnings">
              {checks.issues.map((i, k) => <div key={k} className="rd-warn-row bad"><strong>Must fix</strong> {i.message}</div>)}
              {checks.unused.length > 0 && <div className="rd-warn-row"><strong>{checks.unused.length} form field{checks.unused.length === 1 ? " is" : "s are"} not in this report</strong>
                <ul>{checks.unused.slice(0, 12).map((u) => <li key={u.key}>{u.section} → {u.label}</li>)}{checks.unused.length > 12 && <li>…and {checks.unused.length - 12} more</li>}</ul></div>}
              {warnCount === 0 && <p className="muted small" style={{ padding: 8 }}>Every field of the form is in the report and nothing points at a missing field.</p>}
            </div>)}
        </div>
        <button type="button" onClick={() => setSettings(true)}><Settings2 size={14} aria-hidden /> Report settings</button>
        <MoreMenu label="More template actions" items={[
          { label: "Open the PDF", onClick: openPdf, hidden: !preview },
          { label: "Discard draft", danger: true, onClick: () => setDiscard(true), hidden: !ok || !template.versions.some((x) => x.status === "published") },
        ]} />
        {editable && !draftMeta && <button className="primary" onClick={async () => { try { await api(`pdf-templates/${template.id}/drafts`, { body: {} }); await refresh(); } catch (e) { fail(e); } }}>Start a new draft</button>}
        {ok && <button className="primary" onClick={publish}>Publish</button>}
      </div>
      {discard && <Confirm title="Discard this draft?" danger confirmLabel="Discard draft" onCancel={() => setDiscard(false)} onConfirm={discardDraft}><p>Your unpublished changes to this layout are thrown away. The live layout is not affected.</p></Confirm>}
      {settings && <ReportSettings def={def} onChange={edit} onClose={() => setSettings(false)} readOnly={!ok} />}
      <div className="rd-layout">
        <aside className="card rd-left" aria-label="Pages">
          <div className="rd-h">Pages</div>
          <PagesPanel def={def} sel={sel} onSelect={setSel} onChange={edit} formPages={tree.data?.pages ?? []} sections={sectionNames} readOnly={!ok} />
        </aside>
        <section className="rd-mid" aria-label="Preview">
          <div className="rd-status muted small">{rendering ? "Updating…" : chosen ? "This is the real PDF. Click a part to change it." : "Complete one booking inspected with this form to see the report with real answers."}</div>
          {preview ? <Preview pdf={preview.pdf} pages={preview.pages} selected={sel?.kind === "part" ? sel.id : null} names={nameMap} onSelect={(id) => setSel({ kind: "part", id })} />
            : <Empty title={chosen ? "Drawing the report…" : "Nothing to show yet"} />}
        </section>
        <aside className="card rd-right" aria-label="Settings">
          {part && sel?.kind === "part" ? (
            <PartSettings key={sel.id} part={part} ctx={{ sections, fields: fieldChoices, readOnly: !ok }}
              onChange={(p) => edit(updatePart(def, sel.id, p))}
              onDelete={() => { edit(removePart(def, sel.id)); setSel(null); }}
              onMove={(by) => edit(shiftPart(def, sel.id, by))}
              onDuplicate={() => { const w = locate(def, sel.id); if (!w) return; const copy = withIds({ schema: 2, pages: [{ title: "", parts: [JSON.parse(JSON.stringify(part, (k, val) => (k === "id" ? undefined : val)))] }] }).pages[0]!.parts[0]!; edit(w.set([...w.list.slice(0, w.index + 1), copy, ...w.list.slice(w.index + 1)])); setSel({ kind: "part", id: copy.id! }); }} />
          ) : page && sel?.kind === "page" ? (
            <fieldset disabled={!ok} className="rd-fieldset">
              <PageSettings page={page} fields={fieldChoices} onChange={(p) => edit(updatePage(def, sel.id, p))} onDelete={() => { edit({ ...def, pages: def.pages.filter((p) => p.id !== sel.id) }); setSel(null); }} />
            </fieldset>
          ) : (
            <div className="rd-settings-body">
              <p className="muted small">Click a part in the report or in the pages list to change it. The pages list shows the report from top to bottom; each page starts on a new sheet.</p>
              <p className="muted small">Header, footer, colours, fonts, watermark and the file name are in <button type="button" className="link" onClick={() => setSettings(true)}>Report settings</button>.</p>
            </div>
          )}
        </aside>
      </div>
    </>
  );
}

