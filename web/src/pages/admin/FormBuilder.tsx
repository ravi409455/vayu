import { Download, Eye, Rocket, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { api, ApiError } from "../../api/client";
import { useList, useRefresh } from "../../api/hooks";
import type { FormField, FormPage, FormSummary, FormVersion, MasterList } from "../../api/types";
import { useAuth } from "../../auth";
import { applyDrag, isEmptyBody, reorderBody, type Ref } from "../../lib/tree";
import { type FieldChoice } from "../../ui/ConditionBuilder";
import { Confirm, Modal, NameDialog, PageHeader, Pill, Tabs, useToast } from "../../ui/kit";
import { AddFieldDialog, AddSectionDialog } from "./builder/AddDialogs";
import { Canvas, type Sel } from "./builder/Canvas";
import { Checks, Ratings } from "./builder/FormExtras";
import { ContainerEditor } from "./builder/Inspector";
import { LibraryBox } from "./builder/LibraryBox";
import { PreviewDialog } from "./builder/PreviewDialog";
import { FieldEditor, type FieldDraft } from "./FieldEditor";

type Issue = { path: string; code: string; message: string };

export function FormBuilder() {
  const id = Number(useParams().id);
  const { can } = useAuth();
  const { say, fail } = useToast();
  const refresh = useRefresh();
  const form = useQuery({ queryKey: ["form", id], queryFn: () => api<FormSummary>(`forms/${id}`) });
  const f = form.data;
  const vid = f?.draft_version?.id ?? f?.published_version?.id;
  const draft = !!f?.draft_version;
  const version = useQuery({ queryKey: ["version", vid], enabled: !!vid, queryFn: () => api<FormVersion>(`form-versions/${vid}`) });
  const lists = useList<MasterList>("master-lists", "master-lists");
  const v = version.data;
  const [local, setLocal] = useState<FormPage[] | null>(null);
  const [sel, setSel] = useState<Sel>(null);
  const [pageId, setPageId] = useState<number | null>(null);
  const [tab, setTab] = useState<"structure" | "checks" | "ratings">("structure");
  const [publish, setPublish] = useState<{ issues: Issue[]; warnings: Issue[]; done: boolean } | null>(null);
  const [adding, setAdding] = useState<null | { kind: "field" | "section" | "page"; id: number }>(null);
  const [preview, setPreview] = useState(false);
  const [discard, setDiscard] = useState(false);
  const [confirmDel, setConfirmDel] = useState<null | (() => void)>(null);
  const edit = can("forms.edit") && draft;
  const pages: FormPage[] = local ?? v?.pages ?? [];
  const reload = async () => { await Promise.all([refresh("version"), refresh("form"), refresh("forms")]); setLocal(null); };
  const run = async (fn: () => Promise<unknown>, done?: string) => {
    try { await fn(); if (done) say(done); await reload(); } catch (e) { setLocal(null); fail(e); await reload(); }
  };
  const choices = useFieldChoices(f, v);
  const categories = (v?.rating_config?.categories ?? []).map((c) => c.key);

  const found = useMemo(() => {
    if (!sel) return null;
    for (const p of pages) {
      if (sel.kind === "page" && p.id === sel.id) return { page: p };
      for (const s of p.sections) {
        if (sel.kind === "section" && s.id === sel.id) return { page: p, section: s };
        for (const fl of s.fields) if (sel.kind === "field" && fl.id === sel.id) return { page: p, section: s, field: fl };
      }
    }
    return null;
  }, [pages, sel]);

  const discardDraft = useMutation({
    mutationFn: () => api(`forms/${id}/draft`, { method: "DELETE" }),
    onSuccess: async () => { setDiscard(false); setSel(null); say("Draft discarded. The live version is unchanged."); await reload(); },
    onError: (e) => { setDiscard(false); fail(e); },
  });

  if (!f) return <p className="muted pad">Loading…</p>;

  function onSelect(r: Ref) {
    setSel(r);
    for (const p of pages) if ((r.kind === "page" && p.id === r.id) || p.sections.some((s) => (r.kind === "section" && s.id === r.id) || s.fields.some((x) => r.kind === "field" && x.id === r.id))) setPageId(p.id);
  }
  async function onDrag(active: Ref, over: Ref) {
    if (!edit || !v) return;
    const after = applyDrag(pages, active, over);
    const body = reorderBody(pages, after);
    if (isEmptyBody(body)) return;
    setLocal(after);                                            // show it at once; the server confirms
    await run(() => api(`form-versions/${v.id}/reorder`, { body }));
  }
  const move = (active: Ref, over: Ref) => onDrag(active, over);

  async function startDraft() { await run(() => api(`forms/${id}/drafts`, { body: {} }), "Draft started."); }
  async function checkAndPublish() {
    if (!v) return;
    try {
      const r = await api<{ issues: Issue[] }>(`form-versions/${v.id}/validate`, { body: {} });
      setPublish({ issues: r.issues, warnings: [], done: false });
    } catch (e) { fail(e); }
  }
  async function doPublish() {
    if (!v) return;
    try {
      const r = await api<{ warnings: Issue[] }>(`form-versions/${v.id}/publish`, { body: { row_version: v.row_version } });
      setPublish({ issues: [], warnings: r.warnings, done: true });
      say("Published.");
      await reload();
    } catch (e) {
      if (e instanceof ApiError && Array.isArray(e.body.issues)) setPublish({ issues: e.body.issues as Issue[], warnings: [], done: false });
      else fail(e);
    }
  }
  const publishedExists = !!f.published_version;
  const sectionOptions = pages.flatMap((p) => p.sections.filter((s) => !s.locked).map((s) => ({ id: s.id, label: `${p.title} › ${s.title}` })));

  return (
    <>
      <PageHeader title={<>{f.name} <span className="muted mono small">{f.key}</span></>}
        subtitle={draft ? "You are editing a draft. Experts keep using the live version until you publish." : "This version is live and cannot be changed. Start a draft to make changes."}
        tip="A form is built in a draft, tried in the preview, then published. Once published it never changes; edits go into the next draft. Every inspection stays on the version it started with.">
        {f.published_version && <Pill tone="ok">Live: v{f.published_version.number}</Pill>}
        {draft && <Pill tone="info">Draft v{f.draft_version!.number}</Pill>}
        {v && <button onClick={() => setPreview(true)}><Eye size={15} aria-hidden /> Preview</button>}
        {f.kind === "inspection" && f.published_version && can("forms.promote") && (
          <a className="btn" href={`/api/v1/promote/export?version=${f.published_version.id}`} download><Download size={15} aria-hidden /> Export</a>)}
        {draft && can("forms.edit") && <button className="danger" onClick={() => setDiscard(true)}><Trash2 size={15} aria-hidden /> Discard draft</button>}
        {!draft && can("forms.edit") && <button className="primary" onClick={startDraft}>Start a new draft</button>}
        {draft && can("forms.publish") && <button className="primary" onClick={checkAndPublish}><Rocket size={15} aria-hidden /> Check &amp; publish…</button>}
      </PageHeader>
      {!v ? <p className="muted">No version yet.</p> : (
        <>
          <Tabs tabs={[{ id: "structure", label: "Questions" }, { id: "checks", label: "Key Checks" }, { id: "ratings", label: "Ratings" }]} value={tab} onChange={setTab} />
          {tab === "structure" && (
            <div className="builder">
              <Canvas pages={pages} pageId={pageId} sel={sel} onSelect={onSelect} onPage={setPageId} readOnly={!edit} onDrag={onDrag}
                onAddPage={() => setAdding({ kind: "page", id: 0 })} onAddSection={(pid) => setAdding({ kind: "section", id: pid })} onAddField={(sid) => setAdding({ kind: "field", id: sid })} />
              <aside className="card inspector" aria-label="Settings">
                {!found && <div className="empty-state"><p><strong>Nothing selected</strong></p><p>Click a page, a section or a field to change its settings. Drag the grips to reorder.</p></div>}
                {found?.field && (
                  <FieldEditor field={found.field} choices={choices} readOnly={!edit} kind={f.kind}
                    parents={{ section: found.section!.access, page: found.page.access }}
                    lists={(lists.data ?? []).map((l) => ({ key: l.key, name: l.name }))} categories={categories}
                    onSave={(d: FieldDraft) => run(() => api(`fields/${found.field!.id}`, { method: "PATCH", body: d }), "Saved.")}
                    onDelete={() => setConfirmDel(() => () => run(async () => { await api(`fields/${found.field!.id}`, { method: "DELETE" }); setSel(null); }))}
                    extra={<>
                      {edit && !found.section!.locked && sectionOptions.length > 1 && (
                        <div className="field"><span className="label-row"><label htmlFor="move-field">Move to section</label></span>
                          <select id="move-field" value={found.section!.id} onChange={(e) => move({ kind: "field", id: found.field!.id }, { kind: "section", id: Number(e.target.value) })}>
                            {sectionOptions.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}</select></div>)}
                      <LibraryBox kind="field" id={found.field.id} library={found.field.library} readOnly={!edit} onDone={reload} />
                    </>} />
                )}
                {found?.section && !found.field && (
                  <ContainerEditor kind="section" item={found.section} pages={pages} choices={choices} formKind={f.kind} parentAccess={found.page.access} readOnly={!edit}
                    onSave={(b) => run(() => api(`sections/${found.section!.id}`, { method: "PATCH", body: b }), "Saved.")}
                    onMove={(pid) => move({ kind: "section", id: found.section!.id }, { kind: "page", id: pid })} onChanged={reload}
                    onDelete={() => setConfirmDel(() => () => run(async () => { await api(`sections/${found.section!.id}`, { method: "DELETE" }); setSel(null); }))} />
                )}
                {found?.page && !found.section && (
                  <ContainerEditor kind="page" item={found.page} pages={pages} choices={choices} formKind={f.kind} readOnly={!edit}
                    onSave={(b) => run(() => api(`pages/${found.page.id}`, { method: "PATCH", body: b }), "Saved.")} onMove={() => {}} onChanged={reload}
                    onDelete={() => setConfirmDel(() => () => run(async () => { await api(`pages/${found.page.id}`, { method: "DELETE" }); setSel(null); }))} />
                )}
              </aside>
            </div>
          )}
          {tab === "checks" && <Checks version={v} choices={choices} edit={edit} run={(fn) => void run(fn)} />}
          {tab === "ratings" && <Ratings version={v} sections={pages.flatMap((p) => p.sections.map((s) => s.title))} edit={edit} run={(fn) => void run(fn)} />}
        </>
      )}
      {adding?.kind === "page" && <NameDialog title="Add a page" label="Page name" onCancel={() => setAdding(null)} onOk={(title) => { setAdding(null); void run(() => api(`form-versions/${v!.id}/pages`, { body: { title } })); }} />}
      {adding?.kind === "section" && <AddSectionDialog onClose={() => setAdding(null)}
        onBlank={(title) => { const pid = adding.id; setAdding(null); void run(() => api(`pages/${pid}/sections`, { body: { title } })); }}
        onLibrary={(item, link) => { const pid = adding.id; setAdding(null); void run(() => api(`pages/${pid}/sections/from-library`, { body: { library_item: item, link } })); }} />}
      {adding?.kind === "field" && <AddFieldDialog sectionTitle={pages.flatMap((p) => p.sections).find((s) => s.id === adding.id)?.title ?? ""} onClose={() => setAdding(null)}
        onAdd={(body) => { const sid = adding.id; setAdding(null); void run(async () => { const r = await api<FormField>(`sections/${sid}/fields`, { body }); setSel({ kind: "field", id: r.id }); }); }}
        onLibrary={(item, link) => { const sid = adding.id; setAdding(null); void run(async () => { const r = await api<FormField>(`sections/${sid}/fields/from-library`, { body: { library_item: item, link } }); setSel({ kind: "field", id: r.id }); }); }} />}
      {preview && v && <PreviewDialog tree={{ pages, checks: v.checks }} kind={f.kind} onClose={() => setPreview(false)} />}
      {discard && (
        <Confirm title="Discard this draft?" danger confirmLabel="Discard draft" onCancel={() => setDiscard(false)} onConfirm={() => discardDraft.mutate()}>
          <p>Everything changed since the last published version is thrown away. {publishedExists ? "The live version is not affected." : "This form was never published, so there is nothing to go back to: publish it or keep editing."}</p>
        </Confirm>)}
      {confirmDel && <Confirm title="Delete this?" danger confirmLabel="Delete" onCancel={() => setConfirmDel(null)} onConfirm={() => { confirmDel(); setConfirmDel(null); }}>
        <p>Its key stays reserved, so old answers, PDFs and integrations never get confused.</p></Confirm>}
      {publish && <PublishDialog state={publish} onClose={() => setPublish(null)} onPublish={doPublish} />}
    </>
  );
}

export function PublishDialog({ state, onClose, onPublish }: { state: { issues: Issue[]; warnings: Issue[]; done: boolean }; onClose: () => void; onPublish: () => void }) {
  const blocked = state.issues.length > 0;
  return (
    <Modal title={state.done ? "Published" : blocked ? "Fix these first" : "Ready to publish"} onClose={onClose}
      actions={<><button onClick={onClose}>Close</button>{!state.done && !blocked && <button className="primary" onClick={onPublish}>Publish now</button>}</>}>
      {state.issues.map((i, n) => <p key={n} className="error" role="alert"><strong>{i.path}</strong>: {i.message}</p>)}
      {state.warnings.length > 0 && (
        <>
          <h3>Not shown in the PDF yet</h3>
          {state.warnings.map((w, n) => <p key={n} className="small"><Pill tone="warn">Heads-up</Pill> {w.message}</p>)}
          <p className="muted small">The version is live. Add these to the PDF template if the report should show them.</p>
        </>
      )}
      {!blocked && !state.done && <p>Once published this version can never be changed. Experts will use it for every new inspection.</p>}
    </Modal>
  );
}


/** Field names a condition can point at: this form's fields plus the other forms' (booking, ops). */
export function useFieldChoices(f: FormSummary | undefined, v: FormVersion | undefined): FieldChoice[] {
  const forms = useList<FormSummary>("forms", "forms");
  const others = (forms.data ?? []).filter((x) => x.kind !== f?.kind && x.kind !== "inspection" && x.published_version);
  const tree = useQuery({
    queryKey: ["choice-trees", others.map((o) => o.published_version!.id).join(",")],
    enabled: others.length > 0,
    queryFn: async () => Promise.all(others.map(async (o) => ({ kind: o.kind, v: await api<FormVersion>(`form-versions/${o.published_version!.id}`) }))),
  });
  return useMemo(() => {
    const out: FieldChoice[] = [];
    const add = (kind: string, ver: FormVersion | undefined) => ver?.pages.forEach((p) => p.sections.forEach((s) => s.fields.forEach((fl: FormField) => out.push({ value: `${kind}.${fl.key}`, label: `${kind}: ${fl.label || fl.key}` }))));
    add(f?.kind ?? "inspection", v);
    (tree.data ?? []).forEach((t) => add(t.kind, t.v));
    return out;
  }, [f?.kind, v, tree.data]);
}


