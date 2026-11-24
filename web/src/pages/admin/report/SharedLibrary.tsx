/** The shared library: every shared theme and shared part, which reports use them, and an editor
 *  with a live preview. Saving makes a new version and moves every report using it (drafts at
 *  once; live reports get a new published version), so it is an explicit step, not autosave. */
import { ArrowLeft, Link2, Palette, Settings2 } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, type Page } from "../../../api/client";
import { useRefresh } from "../../../api/hooks";
import type { Booking, FormSummary, FormVersion } from "../../../api/types";
import { fmtDay } from "../../../lib/format";
import { useRefChoices } from "../../../lib/useChoices";
import { Confirm, Empty, Pill, useToast } from "../../../ui/kit";
import { findPart, locate, partName, removePart, shiftPart, themeOf, updatePage, updatePart, withIds, withoutTheme, type Definition, type Part } from "./model";
import { PagesPanel, type Sel } from "./PagesPanel";
import { PageSettings, PartSettings } from "./PartSettings";
import { Preview, type LayoutPage } from "./Preview";
import { ReportSettings } from "./ReportSettings";
import { useShared, type SharedItem, type ThemeContent, type Usage } from "./sharing";

type Template = { id: number; form: number; form_key: string; versions: { id: number; number: number; status: string }[] };
type TVersion = { id: number; definition: Definition };

/** "PDI (uses v4)", "EV (live uses v3, draft uses v4)": who uses an item, at which of its versions. */
export function usedBy(u: Usage[]): string {
  return u.map((x) => {
    const uses = x.published && x.draft && x.published !== x.draft ? `live uses v${x.published}, draft uses v${x.draft}`
      : `${x.published ? "" : "draft "}uses v${x.published ?? x.draft}`;
    return `${x.form} (${uses})`;
  }).join(" · ");
}

export function SharedLibrary({ templates, forms, editable }: { templates: Template[]; forms: FormSummary[]; editable: boolean }) {
  const items = useShared();
  const [open, setOpen] = useState<number | null>(null);
  const item = (items.data ?? []).find((i) => i.id === open);
  if (item) return <SharedEditor key={`${item.id}-${item.revision}`} item={item} all={items.data ?? []} templates={templates} forms={forms} editable={editable} onBack={() => setOpen(null)} />;
  const group = (kind: SharedItem["kind"]) => (items.data ?? []).filter((i) => i.kind === kind);
  const list = (kind: SharedItem["kind"], title: string, hint: string, Icon: typeof Palette) => (
    <section className="card stack" aria-label={title}>
      <div><h3>{title}</h3><p className="muted small">{hint}</p></div>
      {group(kind).length === 0 ? <p className="muted small">None yet. In a report, use “Share with other reports”.</p> : (
        <table className="rows"><thead><tr><th>Name</th><th>Version</th><th>Used by</th><th /></tr></thead>
          <tbody>{group(kind).map((i) => (
            <tr key={i.id}><td><Icon size={14} aria-hidden /> <strong>{i.name}</strong></td><td>v{i.revision}</td>
              <td className="small">{i.used_by.length ? usedBy(i.used_by) : <span className="muted">not used</span>}</td>
              <td><button type="button" className="sm" onClick={() => setOpen(i.id)}>{editable ? "Edit" : "View"}</button></td></tr>))}
          </tbody></table>)}
    </section>);
  if (items.isLoading) return <p className="muted">Loading…</p>;
  return (
    <div className="stack">
      {list("theme", "Themes", "Colours, fonts, header, footer and watermark. Change once, every report using it changes.", Palette)}
      {list("snippet", "Shared parts", "Parts used in several reports, e.g. the disclaimer.", Link2)}
    </div>
  );
}

function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value);
  useEffect(() => { const h = setTimeout(() => setV(value), ms); return () => clearTimeout(h); }, [value, ms]);
  return v;
}

const noIds = <T,>(x: T): T => JSON.parse(JSON.stringify(x, (k, v: unknown) => (k === "id" ? undefined : v))) as T;

function SharedEditor({ item, all, templates, forms, editable, onBack }: {
  item: SharedItem; all: SharedItem[]; templates: Template[]; forms: FormSummary[]; editable: boolean; onBack: () => void;
}) {
  const { say, fail } = useToast();
  const refresh = useRefresh();
  const theme = item.kind === "theme";
  // the preview borrows a report that uses the item (else the first one): its form, booking, theme
  const users = templates.filter((t) => item.used_by.some((u) => u.template === t.id));
  const [tid, setTid] = useState((users[0] ?? templates[0])?.id ?? 0);
  const host = templates.find((t) => t.id === tid);
  const form = forms.find((f) => f.id === host?.form);
  const hostVersion = host && (host.versions.find((v) => v.status === "draft") ?? host.versions[host.versions.length - 1]);
  const hv = useQuery({ queryKey: ["pdf-version", hostVersion?.id], enabled: !!hostVersion, queryFn: () => api<TVersion>(`pdf-template-versions/${hostVersion!.id}`) });
  const content = useQuery({ queryKey: ["pdf-shared", item.id, item.revision], queryFn: async () => (await api<SharedItem>(`pdf-shared/${item.id}`)).content });
  const formVersionId = form?.draft_version?.id ?? form?.published_version?.id;
  const tree = useQuery({ queryKey: ["form-version", formVersionId], enabled: !!formVersionId, queryFn: () => api<FormVersion>(`form-versions/${formVersionId}`) });
  const choices = useRefChoices(host?.form ?? 0);
  const sample = useQuery({ queryKey: ["pdf-sample", form?.inspection_type], enabled: !!form?.inspection_type,
    queryFn: async () => (await Promise.all(["completed", "submitted"].map((stage) => api<Page<Booking>>("bookings", { query: { type: form!.inspection_type, stage } })))).flatMap((r) => r.results) });
  const [bookingId, setBookingId] = useState("");
  const chosen = bookingId || sample.data?.[0]?.id || "";

  // what is edited: a shared part as one page of parts; a theme as a whole report wearing it
  const [def, setDef] = useState<Definition | null>(null);
  const [dirty, setDirty] = useState(false);
  useEffect(() => {
    if (content.data === undefined || (theme && !hv.data)) return;
    if (theme) setDef(withIds({ ...withoutTheme(hv.data!.definition), theme_ref: undefined, ...(content.data as ThemeContent) }));
    else setDef(withIds({ schema: 2, pages: [{ title: item.name, style: "normal", parts: (content.data as { parts: Part[] }).parts }] }));
  }, [content.data, hv.data]); // eslint-disable-line react-hooks/exhaustive-deps
  const edit = (d: Definition) => { setDef(d); setDirty(true); };
  const [sel, setSel] = useState<Sel>(null);
  const [settings, setSettings] = useState(theme);
  const [confirm, setConfirm] = useState(false);

  // live preview: for a part, the host's look with this part's page alone; for a theme, the whole report
  const shown = useDebounced(def, 500);
  const [preview, setPreview] = useState<{ pdf: string; pages: LayoutPage[] } | null>(null);
  const [rendering, setRendering] = useState(false);
  const ticket = useRef(0);
  useEffect(() => {
    if (!shown || !hv.data || !hostVersion || !chosen) return;
    const n = ++ticket.current;
    const body = theme ? shown : { ...hv.data.definition, pages: shown.pages };
    setRendering(true);
    api<{ pdf: string; pages: LayoutPage[] }>(`pdf-template-versions/${hostVersion.id}/preview`, { body: { booking: chosen, definition: body } })
      .then((r) => { if (n === ticket.current) setPreview(r); })
      .catch((e) => { if (n === ticket.current) fail(e); })
      .finally(() => { if (n === ticket.current) setRendering(false); });
  }, [shown, chosen, hv.data]); // eslint-disable-line react-hooks/exhaustive-deps

  const sectionNames = useMemo(() => Object.fromEntries((tree.data?.pages ?? []).flatMap((p) => p.sections.map((s) => [`inspection.${s.key}`, s.title]))), [tree.data]);
  const sections = useMemo(() => (tree.data?.pages ?? []).flatMap((p) => p.sections.filter((s) => s.key).map((s) => ({
    value: `inspection.${s.key}`, label: `${p.title} → ${s.title} (${s.fields.length})`, fields: s.fields.map((f) => ({ key: f.key, label: f.label || f.key, type: f.type })) }))), [tree.data]);
  const fields = useMemo(() => choices.map((c) => ({ value: c.value, label: c.label, type: c.type })), [choices]);
  const snippets = all.filter((i) => i.kind === "snippet" && i.id !== item.id);       // never inside itself

  async function save() {
    if (!def) return;
    setConfirm(false);
    const body = theme ? themeOf(def) : { parts: noIds(def.pages[0]?.parts ?? []) };
    try {
      const r = await api<SharedItem & { updated: string[] }>("pdf-shared", { body: { kind: item.kind, key: item.key, name: item.name, content: body } });
      setDirty(false);
      await refresh("pdf-shared", "pdf-version", "pdf-templates");
      say(`Saved as version ${r.revision}.${r.updated.length ? ` Updated: ${r.updated.join(", ")}.` : ""}`);
    } catch (e) { fail(e); }
  }

  const part = def && sel?.kind === "part" ? findPart(def, sel.id) : null;
  const page = def && sel?.kind === "page" ? def.pages.find((p) => p.id === sel.id) : null;
  const names = useMemo(() => {
    const out: Record<string, string> = {};
    const walk = (ps: Part[]) => ps.forEach((p) => { out[p.id!] = partName(p, sectionNames); if (p.type === "columns") p.columns.forEach((c) => walk(c.parts)); });
    def?.pages.forEach((pg) => walk(pg.parts));
    return out;
  }, [def, sectionNames]);
  return (
    <>
      <div className="bar rd-top">
        <button type="button" onClick={onBack}><ArrowLeft size={14} aria-hidden /> Shared library</button>
        <strong>{item.name}</strong><Pill tone="info">{theme ? "Theme" : "Shared part"} v{item.revision}</Pill>
        <span className="muted small">{dirty ? "Not saved yet" : item.used_by.length ? `Used by ${usedBy(item.used_by)}` : "Not used by any report"}</span>
        <span className="grow" />
        <label className="bar small muted" style={{ margin: 0 }}>Preview in
          <select aria-label="Report for the preview" value={tid} onChange={(e) => setTid(Number(e.target.value))}>
            {templates.map((t) => <option key={t.id} value={t.id}>{forms.find((f) => f.id === t.form)?.name ?? t.form_key}</option>)}</select></label>
        <select aria-label="Booking for the preview" value={chosen} onChange={(e) => setBookingId(e.target.value)} style={{ maxWidth: 240 }}>
          {(sample.data ?? []).length === 0 && <option value="">No completed booking of this form yet</option>}
          {(sample.data ?? []).map((bk) => <option key={bk.id} value={bk.id}>{bk.booking_id} · {fmtDay(bk.answers.inspection_date)}</option>)}</select>
        {theme && <button type="button" onClick={() => setSettings(true)}><Settings2 size={14} aria-hidden /> Header, colours, watermark</button>}
        {editable && <button className="primary" disabled={!dirty} onClick={() => setConfirm(true)}>Save as version {item.revision + 1}</button>}
      </div>
      {confirm && (
        <Confirm title={`Save “${item.name}” as version ${item.revision + 1}?`} confirmLabel="Save" onCancel={() => setConfirm(false)} onConfirm={() => void save()}>
          {item.used_by.length
            ? <><p>Every report using it changes: {usedBy(item.used_by)}.</p><p className="muted small">Drafts change at once. A live report gets a new published version with this change, so reports made from now on use it. PDFs already made stay as they are.</p></>
            : <p>No report uses it yet.</p>}
        </Confirm>)}
      {settings && def && <ReportSettings def={def} onChange={edit} onClose={() => setSettings(false)} readOnly={!editable} themes={[]} only={["bands", "look", "images", "pictures"]} title={`Theme: ${item.name}`} />}
      {!def ? <p className="muted">Loading…</p> : (
        <div className={`rd-layout${theme ? " no-left" : ""}`}>
          {!theme && <aside className="card rd-left" aria-label="Parts">
            <div className="rd-h">Parts</div>
            <PagesPanel def={def} sel={sel} onSelect={setSel} onChange={edit} formPages={[]} sections={sectionNames} readOnly={!editable} snippets={snippets} onePage />
          </aside>}
          <section className="rd-mid" aria-label="Preview">
            <div className="rd-status muted small">{rendering ? "Updating…" : chosen ? (theme ? "The whole report, wearing this theme." : "This part on its own, in the report's look.") : "Complete one booking inspected with this form to see a preview."}</div>
            {preview ? <Preview pdf={preview.pdf} pages={preview.pages} selected={sel?.kind === "part" ? sel.id : null} names={names} onSelect={(id) => !theme && setSel({ kind: "part", id })} />
              : <Empty title={chosen ? "Drawing…" : "Nothing to show yet"} />}
          </section>
          <aside className="card rd-right" aria-label="Settings">
            {!theme && part && sel?.kind === "part" ? (
              <PartSettings key={sel.id} part={part} ctx={{ sections, fields, readOnly: !editable, snippets }}
                onChange={(p) => edit(updatePart(def, sel.id, p))}
                onDelete={() => { edit(removePart(def, sel.id)); setSel(null); }}
                onMove={(by) => edit(shiftPart(def, sel.id, by))}
                onDuplicate={() => {
                  const w = locate(def, sel.id); if (!w) return;
                  const copy = withIds({ schema: 2, pages: [{ title: "", parts: [noIds(part)] }] }).pages[0]!.parts[0]!;
                  edit(w.set([...w.list.slice(0, w.index + 1), copy, ...w.list.slice(w.index + 1)])); setSel({ kind: "part", id: copy.id! });
                }} />
            ) : !theme && page && sel?.kind === "page" ? (
              <fieldset disabled={!editable} className="rd-fieldset">
                <PageSettings page={page} fields={fields} onChange={(p) => edit(updatePage(def, sel.id, p))} onDelete={() => {}} />
              </fieldset>
            ) : (
              <div className="rd-settings-body">
                <p className="muted small">{theme
                  ? "Change the header, footer, colours, fonts and watermark with the button above. The preview shows a whole report wearing the theme."
                  : "Click a part in the preview or the list to change it; “+ Add to this page” adds one."}</p>
                <p className="muted small">Nothing changes in any report until you press <strong>Save as version {item.revision + 1}</strong>.</p>
              </div>)}
          </aside>
        </div>)}
    </>
  );
}
