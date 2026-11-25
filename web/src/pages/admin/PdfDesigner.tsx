import { AlertTriangle, ChevronsLeft, ChevronsRight, Settings2 } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { api, ApiError, type Page } from "../../api/client";
import { useList, useRefresh } from "../../api/hooks";
import type { Booking, FormSummary, FormVersion } from "../../api/types";
import { useAuth } from "../../auth";
import { fmtDay } from "../../lib/format";
import { useRefChoices } from "../../lib/useChoices";
import { Confirm, Empty, LoadError, PageHeader, Pill, useToast } from "../../ui/kit";
import { MoreMenu } from "../../ui/Menu";
import { findPart, locate, partName, removePart, replaceRef, sharedPart, shiftPart, unlinkShared, updatePage, updatePart, withIds, type Definition, type Part } from "./report/model";
import { PagesPanel, type Sel } from "./report/PagesPanel";
import { PageSettings, PartSettings, type SectionChoice } from "./report/PartSettings";
import { Preview, type LayoutPage } from "./report/Preview";
import { ReportSettings } from "./report/ReportSettings";
import { useShared, type SharedItem } from "./report/sharing";
import { SharedLibrary } from "./report/SharedLibrary";
import { keys } from "../../api/keys";

type Template = { id: number; form: number; form_key: string; versions: { id: number; number: number; status: string }[] };
type TVersion = { id: number; template: number; number: number; status: string; definition: Definition; row_version: number };
type Issue = { code: string; message: string; part?: string | null; ref?: string; suggestion?: string | null };
type Unused = { key: string; label: string; section: string };

export function PdfDesigner() {
  const { can } = useAuth();
  const { fail } = useToast();
  const refresh = useRefresh();
  const templates = useList<Template>(keys.pdfTemplates(), "pdf-templates");
  const forms = useList<FormSummary>(keys.forms(), "forms");
  const [tid, setTid] = useState<number | "library" | null>(null);
  const library = tid === "library";
  const t = library ? null : (templates.data ?? []).find((x) => x.id === tid) ?? (templates.data ?? [])[0] ?? null;
  const formName = (x: Template) => (forms.data ?? []).find((f) => f.id === x.form)?.name ?? x.form_key;
  const editable = can("pdf_templates.edit");
  const withoutTemplate = (forms.data ?? []).filter((f) => f.type === "custom" && !(templates.data ?? []).some((x) => x.form === f.id));
  const make = useMutation({ mutationFn: (form: number) => api<Template>("pdf-templates", { body: { form } }), onSuccess: (r) => { void refresh(keys.pdfTemplates()); setTid(r.id); }, onError: fail });
  return (
    <>
      <PageHeader title="PDF templates">
        {editable && withoutTemplate.length > 0 && (
          <select aria-label="Create a template for" value="" onChange={(e) => e.target.value && make.mutate(Number(e.target.value))} style={{ maxWidth: 240 }}>
            <option value="">+ New template for…</option>{withoutTemplate.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}</select>)}
      </PageHeader>
      {templates.isError && <LoadError error={templates.error} what="PDF templates" onRetry={templates.refetch} />}
      <div className="tabs" role="tablist" aria-label="Templates">{(templates.data ?? []).map((x) => (
        <button key={x.id} role="tab" aria-selected={(t?.id ?? null) === x.id} className={t?.id === x.id ? "on" : ""} onClick={() => setTid(x.id)}>{formName(x)}</button>))}
        <button role="tab" aria-selected={library} className={`rd-libtab${library ? " on" : ""}`} onClick={() => setTid("library")}>Shared library</button></div>
      {library ? <SharedLibrary templates={templates.data ?? []} forms={forms.data ?? []} editable={editable} />
        : t ? <Designer key={t.id} template={t} form={(forms.data ?? []).find((f) => f.id === t.form)} editable={editable} refresh={() => refresh(keys.pdfTemplates())}
        copyTargets={withoutTemplate} onOpen={setTid} />
        : <Empty title="No PDF templates yet">Create one for an inspection form with “New template for…”.</Empty>}
    </>
  );
}

/** Every part of the definition with its name (for the preview's outlines). */
function names(d: Definition, sections: Record<string, string>, shared: Record<string, string>): Record<string, string> {
  const out: Record<string, string> = {};
  const walk = (parts: Part[]) => parts.forEach((p) => { out[p.id!] = partName(p, sections, shared); if (p.type === "columns") p.columns.forEach((c) => walk(c.parts)); });
  d.pages.forEach((pg) => walk(pg.parts));
  return out;
}

function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value);
  useEffect(() => { const h = setTimeout(() => setV(value), ms); return () => clearTimeout(h); }, [value, ms]);
  return v;
}

function Designer({ template, form, editable, refresh, copyTargets, onOpen }: {
  template: Template; form?: FormSummary; editable: boolean; refresh: () => unknown; copyTargets: FormSummary[]; onOpen: (id: number) => void;
}) {
  const { say, fail } = useToast();
  const sharedItems = useShared();
  const themes = (sharedItems.data ?? []).filter((i) => i.kind === "theme");
  const snippets = (sharedItems.data ?? []).filter((i) => i.kind === "snippet");
  const sharedNames = Object.fromEntries(snippets.map((i) => [i.key, i.name]));
  const importInput = useRef<HTMLInputElement>(null);
  const [importing, setImporting] = useState<unknown>(null);
  const [copying, setCopying] = useState(false);
  const [pagesShown, setPagesShown] = useState(() => { try { return localStorage.getItem("rd-pages") !== "hidden"; } catch { return true; } });
  const showPages = (v: boolean) => { setPagesShown(v); try { localStorage.setItem("rd-pages", v ? "shown" : "hidden"); } catch { /* private window */ } };
  const reload = useRefresh();
  const draftMeta = template.versions.find((v) => v.status === "draft");
  const latest = template.versions[template.versions.length - 1];
  const vid = (draftMeta ?? latest)?.id;
  const ver = useQuery({ queryKey: keys.pdfVersion(vid), enabled: !!vid, queryFn: ({ signal }) => api<TVersion>(`pdf-template-versions/${vid}`, { signal }) });
  const formVersionId = form?.draft_version?.id ?? form?.published_version?.id;
  const tree = useQuery({ queryKey: keys.formVersion(formVersionId), enabled: !!formVersionId, queryFn: ({ signal }) => api<FormVersion>(`form-versions/${formVersionId}`, { signal }) });
  const choices = useRefChoices(template.form);
  const sample = useQuery({ queryKey: keys.pdfSample(form?.inspection_type), enabled: !!form?.inspection_type,
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
  const [preview, setPreview] = useState<{ pdf: string; pages: LayoutPage[]; checks?: { page: number; code: string; message: string }[] } | null>(null);
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
  // leaving (another template, the library, another page) with an edit not sent yet: send it now (F-015)
  const pending = useRef<Definition | null>(null);
  pending.current = ok && dirty ? def : null;
  const flush = useRef(save);
  flush.current = save;
  useEffect(() => () => { if (pending.current) void flush.current(pending.current); }, []);
  useEffect(() => {
    const warn = (e: BeforeUnloadEvent) => { if (pending.current) e.preventDefault(); };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, []);

  // live preview and checks, a moment after each change (unsaved edits included)
  const shown = useDebounced(def, 500);
  const ticket = useRef(0);
  useEffect(() => {
    if (!shown || !v) return;
    const n = ++ticket.current;
    void api<{ issues: Issue[]; unused: Unused[] }>(`pdf-template-versions/${v.id}/checks`, { body: { definition: shown } }).then((r) => { if (n === ticket.current) setChecks(r); }).catch(() => {});
    if (!chosen) return;
    setRendering(true);
    api<{ pdf: string; pages: LayoutPage[]; checks: { page: number; code: string; message: string }[] }>(`pdf-template-versions/${v.id}/preview`, { body: { booking: chosen, definition: shown } })
      .then((r) => { if (n === ticket.current) setPreview(r); })
      .catch((e) => { if (n === ticket.current) fail(e); })
      .finally(() => { if (n === ticket.current) setRendering(false); });
  }, [shown, chosen, v?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  async function publish() {
    if (!def || !v) return;
    await save(def);
    try {
      await api(`pdf-template-versions/${v.id}/publish`, { body: { row_version: rowVersion.current } });
      say("Published. New and re-made reports use this layout."); await reload(keys.pdfVersion()); void refresh();
    } catch (e) { fail(e); setShowWarnings(true); }
  }
  async function discardDraft() {
    try { await api(`pdf-template-versions/${v!.id}`, { method: "DELETE" }); setDiscard(false); say("Draft discarded. The live layout is unchanged."); await reload(keys.pdfVersion()); await refresh(); }
    catch (e) { setDiscard(false); fail(e); }
  }
  async function exportFile() {
    if (!v) return;
    try {
      if (ok && def) await save(def);
      const file = await api<unknown>(`pdf-template-versions/${v.id}/export`);
      const a = document.createElement("a");
      a.href = URL.createObjectURL(new Blob([JSON.stringify(file, null, 1)], { type: "application/json" }));
      a.download = `${template.form_key}-report-v${v.number}.json`;
      a.click();
      URL.revokeObjectURL(a.href);
    } catch (e) { fail(e); }
  }
  async function importFile() {
    const file = importing;
    setImporting(null);
    try {
      const r = await api<TVersion & { issues: Issue[]; notes: string[] }>(`pdf-templates/${template.id}/import`, { body: file });
      await refresh(); await reload(keys.pdfVersion(), keys.pdfShared(), keys.pdfPictures());
      say([`Imported into draft v${r.number}.`, ...r.notes, r.issues.length ? `${r.issues.length} thing${r.issues.length === 1 ? "" : "s"} to fix: see warnings.` : ""].filter(Boolean).join(" "));
      if (r.issues.length) setShowWarnings(true);
    } catch (e) { fail(e); }
  }
  async function unlink(p: Extract<Part, { type: "snippet" }>) {
    const item = snippets.find((x) => x.key === p.ref.key);
    if (!item || !def) return;
    try {
      const r = await api<SharedItem>(`pdf-shared/${item.id}`, { query: { revision: String(p.ref.revision) } });
      edit(unlinkShared(def, p.id!, (r.content as { parts: Part[] }).parts));
      setSel(null);
    } catch (e) { fail(e); }
  }
  function openPdf() {
    if (!preview) return;
    const blob = new Blob([Uint8Array.from(atob(preview.pdf), (c) => c.charCodeAt(0))], { type: "application/pdf" });
    window.open(URL.createObjectURL(blob), "_blank", "noopener");
  }

  if (!def || !v) return <p className="muted">Loading…</p>;
  const part = sel?.kind === "part" ? findPart(def, sel.id) : null;
  const page = sel?.kind === "page" ? def.pages.find((p) => p.id === sel.id) : null;
  const nameMap = names(def, sectionNames, sharedNames);
  const bad = new Set(checks.issues.map((i) => i.part).filter((x): x is string => !!x));
  const layoutChecks = preview?.checks ?? [];
  const warnCount = checks.issues.length + checks.unused.length + layoutChecks.length;
  return (
    <>
      <div className="bar rd-top">
        {draftMeta ? <Pill tone="warn">Draft v{draftMeta.number}, not live yet</Pill> : <Pill tone="ok">Live v{latest?.number}</Pill>}
        <span className="muted small">{!draft ? "Start a draft to change it." : saving === "saving" ? "Saving…" : saving === "error" ? "Not saved" : dirty ? "Unsaved changes…" : "All changes saved"}</span>
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
              {checks.issues.map((i, k) => (
                <div key={k} className="rd-warn-row bad"><strong>Must fix</strong> {i.message}
                  <div className="bar" style={{ margin: "4px 0 0" }}>
                    {i.part && <button type="button" className="link small" onClick={() => { setSel({ kind: "part", id: i.part! }); setShowWarnings(false); }}>Show the part</button>}
                    {ok && i.part && i.ref && i.suggestion && (
                      <button type="button" className="sm" onClick={() => { const p = findPart(def, i.part!); if (p) edit(updatePart(def, i.part!, replaceRef(p, i.ref!, i.suggestion!))); }}>Use {i.suggestion}</button>)}
                  </div>
                </div>))}
              {layoutChecks.map((c, k) => <div key={`l${k}`} className="rd-warn-row"><strong>Layout, page {c.page}</strong> {c.message}</div>)}
              {checks.unused.length > 0 && <div className="rd-warn-row"><strong>{checks.unused.length} form field{checks.unused.length === 1 ? " is" : "s are"} not in this report</strong>
                <ul>{checks.unused.slice(0, 12).map((u) => <li key={u.key}>{u.section} → {u.label}</li>)}{checks.unused.length > 12 && <li>…and {checks.unused.length - 12} more</li>}</ul></div>}
              {warnCount === 0 && <p className="muted small" style={{ padding: 8 }}>Every field of the form is in the report and nothing points at a missing field.</p>}
            </div>)}
        </div>
        <button type="button" onClick={() => setSettings(true)}><Settings2 size={14} aria-hidden /> Report settings</button>
        <MoreMenu label="More template actions" items={[
          { label: "Open the PDF", onClick: openPdf, hidden: !preview },
          { label: "Export (backup file)", onClick: () => void exportFile() },
          { label: "Import a template file…", onClick: () => importInput.current?.click(), hidden: !editable },
          { label: "Copy to another form…", onClick: () => setCopying(true), hidden: !editable || copyTargets.length === 0 },
          { label: "Discard draft", danger: true, onClick: () => setDiscard(true), hidden: !ok || !template.versions.some((x) => x.status === "published") },
        ]} />
        {editable && !draftMeta && <button className="primary" onClick={async () => { try { await api(`pdf-templates/${template.id}/drafts`, { body: {} }); await refresh(); } catch (e) { fail(e); } }}>Start a new draft</button>}
        {ok && <button className="primary" onClick={publish}>Publish</button>}
      </div>
      {discard && <Confirm title="Discard this draft?" danger confirmLabel="Discard draft" onCancel={() => setDiscard(false)} onConfirm={discardDraft}><p>Your unpublished changes to this layout are thrown away. The live layout is not affected.</p></Confirm>}
      {settings && <ReportSettings def={def} onChange={edit} onClose={() => setSettings(false)} readOnly={!ok} themes={themes} />}
      <input ref={importInput} type="file" accept="application/json,.json" hidden aria-label="Template file" onChange={async (e) => {
        const f = e.target.files?.[0];
        e.target.value = "";
        if (!f) return;
        try { setImporting(JSON.parse(await f.text())); } catch { say("That file is not a template file (JSON)."); }
      }} />
      {importing !== null && (
        <Confirm title="Import this template file?" confirmLabel="Import" onCancel={() => setImporting(null)} onConfirm={() => void importFile()}>
          <p>Everything in the file replaces this template's draft: pages, parts, settings, pictures and shared items. The live layout does not change until you publish.</p>
          <p className="muted small">Anything the file uses that this form does not have is listed under warnings and marked “fix” in the pages list, with the closest match to use instead.</p>
        </Confirm>)}
      {copying && <CopyDialog targets={copyTargets} onCancel={() => setCopying(false)} onCopy={async (formId) => {
        try { const r = await api<{ id: number }>(`pdf-templates/${template.id}/copy`, { body: { form: formId } }); setCopying(false); await refresh(); onOpen(r.id); say("Copied. The new template is a draft; check its warnings."); }
        catch (e) { fail(e); }
      }} />}
      <div className={`rd-layout${pagesShown ? "" : " no-left"}`}>
        {!pagesShown && <button type="button" className="rd-rail" onClick={() => showPages(true)} aria-label="Show the pages list"><ChevronsRight size={16} aria-hidden /><span>Pages</span></button>}
        {pagesShown && <aside className="card rd-left" aria-label="Pages">
          <div className="rd-h bar" style={{ margin: 0 }}><span className="grow">Pages</span>
            <button type="button" className="icon-btn" aria-label="Hide the pages list" title="Hide the pages list" onClick={() => showPages(false)}><ChevronsLeft size={15} aria-hidden /></button></div>
          <PagesPanel def={def} sel={sel} onSelect={setSel} onChange={edit} formPages={tree.data?.pages ?? []} sections={sectionNames} readOnly={!ok} snippets={snippets} bad={bad} />
        </aside>}
        <section className="rd-mid" aria-label="Preview">
          <div className="rd-status muted small">{rendering ? "Updating…" : chosen ? "This is the real PDF. Click a part to change it." : "Complete one booking inspected with this form to see the report with real answers."}</div>
          {preview ? <Preview pdf={preview.pdf} pages={preview.pages} selected={sel?.kind === "part" ? sel.id : null} names={nameMap} onSelect={(id) => setSel({ kind: "part", id })} />
            : <Empty title={chosen ? "Drawing the report…" : "Nothing to show yet"} />}
        </section>
        <aside className="card rd-right" aria-label="Settings">
          {part && sel?.kind === "part" ? (
            <PartSettings key={sel.id} part={part} ctx={{ sections, fields: fieldChoices, readOnly: !ok, snippets }}
              onShared={ok ? (item) => {
                const w = locate(def, sel.id); if (!w) return;
                const linked = { ...sharedPart({ key: item.key, revision: item.revision }), id: sel.id };
                edit(w.set(w.list.map((x, i) => (i === w.index ? linked : x))));
                say(item.updated.length ? `Shared. Also updated: ${item.updated.join(", ")}.` : "Shared. Add it to other reports from “+ Add to this page”.");
              } : undefined}
              onUnlink={ok && part.type === "snippet" ? () => void unlink(part) : undefined}
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


function CopyDialog({ targets, onCancel, onCopy }: { targets: FormSummary[]; onCancel: () => void; onCopy: (form: number) => void }) {
  const [form, setForm] = useState(targets[0]?.id ?? 0);
  return (
    <Confirm title="Copy this template" confirmLabel="Copy" onCancel={onCancel} onConfirm={() => onCopy(form)}>
      <p>Start another form's report from this layout. The copy is a draft; anything its form does not have shows as a warning to fix.</p>
      <label className="small">For the form <select aria-label="Copy for the form" value={form} onChange={(e) => setForm(Number(e.target.value))}>
        {targets.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}</select></label>
    </Confirm>
  );
}
