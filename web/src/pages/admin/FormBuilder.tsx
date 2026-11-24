import { Eye, Rocket } from "lucide-react";
import { useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { api, ApiError, uploadFile } from "../../api/client";
import { useList, useRefresh } from "../../api/hooks";
import type { Check, FormField, FormPage, FormSummary, FormVersion, MasterList } from "../../api/types";
import { useAuth } from "../../auth";
import { photoOfDefault } from "../../lib/fieldTypes";
import { applyDrag, isEmptyBody, reorderBody, type Ref } from "../../lib/tree";
import { type FieldChoice } from "../../ui/ConditionBuilder";
import { Confirm, Field, InfoTip, Modal, NameDialog, PageHeader, Pill, Tabs, useToast } from "../../ui/kit";
import { AddFieldDialog, AddSectionDialog } from "./builder/AddDialogs";
import { Canvas, type Sel } from "./builder/Canvas";
import { Ratings } from "./builder/FormExtras";
import { KeyChecks } from "./builder/KeyChecks";
import { ContainerEditor } from "./builder/Inspector";
import { LibraryBox } from "./builder/LibraryBox";
import { PreviewDialog } from "./builder/PreviewDialog";
import { DuplicateDialog } from "./ImportForm";
import { FieldEditor, type FieldDraft, type ValidationDraft } from "./FieldEditor";
import { useCrumb } from "../../ui/crumb";
import { MoreMenu } from "../../ui/Menu";

type Issue = { path: string; code: string; message: string };

export function FormBuilder() {
  const id = Number(useParams().id);
  const { can } = useAuth();
  const { say, fail } = useToast();
  const refresh = useRefresh();
  const form = useQuery({ queryKey: ["form", id], queryFn: () => api<FormSummary>(`forms/${id}`) });
  const f = form.data;
  useCrumb(f?.name);
  const vid = f?.draft_version?.id ?? f?.published_version?.id;
  const draft = !!f?.draft_version;
  const version = useQuery({ queryKey: ["version", vid], enabled: !!vid, queryFn: () => api<FormVersion>(`form-versions/${vid}`) });
  const lists = useList<MasterList>("master-lists", "master-lists");
  const v = version.data;
  const [local, setLocal] = useState<FormPage[] | null>(null);
  const [sel, setSel] = useState<Sel>(null);
  const [pageId, setPageId] = useState<number | null>(null);
  const [tab, setTab] = useState<"structure" | "keychecks" | "ratings">("structure");
  const [publish, setPublish] = useState<{ issues: Issue[]; warnings: Issue[]; done: boolean } | null>(null);
  const [adding, setAdding] = useState<null | { kind: "field" | "section" | "page"; id: number }>(null);
  const [preview, setPreview] = useState(false);
  const [discard, setDiscard] = useState(false);
  const [duplicating, setDuplicating] = useState(false);
  const [renaming, setRenaming] = useState<string | null>(null);
  const [visibility, setVisibility] = useState<string[] | null>(null);
  const [confirmDel, setConfirmDel] = useState<null | (() => void)>(null);
  const edit = can("forms.edit") && draft;
  const pages: FormPage[] = local ?? v?.pages ?? [];
  const reload = async () => { await Promise.all([refresh("version"), refresh("form"), refresh("forms")]); setLocal(null); };
  const run = async (fn: () => Promise<unknown>, done?: string) => {
    try { await fn(); if (done) say(done); await reload(); } catch (e) { setLocal(null); fail(e); await reload(); }
  };
  const choices = useFieldChoices(f, v);
  const setSwitch = useMutation({
    mutationFn: (body: { use_start?: boolean; use_end?: boolean }) => api(`form-versions/${vid}/settings`, { method: "PATCH", body }),
    onSuccess: () => { void reload(); },
    onError: fail,
  });
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
  const ns = nsOf(f.type);
  const sectionOptions = pages.flatMap((p) => p.sections.filter((s) => !s.locked).map((s) => ({ id: s.id, label: `${p.title} › ${s.title}` })));

  return (
    <>
      <PageHeader title={<>{f.name} {draft ? <Pill tone="warn">Draft v{f.draft_version!.number}</Pill> : f.published_version ? <Pill tone="ok">Live v{f.published_version.number}</Pill> : null}</>}
        subtitle={draft ? `${f.published_version ? `Live: v${f.published_version.number}. ` : ""}Experts keep using the live version until you publish.` : "This version is live and cannot be changed. Start a draft to make changes."}>
        {v && <button onClick={() => setPreview(true)}><Eye size={15} aria-hidden /> Preview</button>}
        <MoreMenu label="More form actions" items={[
          { label: "Rename", onClick: () => setRenaming(f.name), hidden: !can("forms.edit") },
          { label: "Who sees submissions", onClick: () => setVisibility(f.submission_roles ?? ["expert", "ops"]), hidden: f.type !== "custom" },
          { label: "Export", onClick: () => { window.location.href = `/api/v1/promote/export?version=${f.published_version!.id}`; }, hidden: !(f.published_version && can("forms.promote")) },
          { label: "Duplicate as new form", onClick: () => setDuplicating(true), hidden: !(f.type === "custom" && can("forms.edit")) },
          { label: "Discard draft", danger: true, onClick: () => setDiscard(true), hidden: !(draft && can("forms.edit")) },
        ]} />
        {!draft && can("forms.edit") && <button className="primary" onClick={startDraft}>Start a new draft</button>}
        {draft && can("forms.publish") && <button className="primary" disabled={!v} onClick={checkAndPublish}><Rocket size={15} aria-hidden /> Check &amp; publish…</button>}
      </PageHeader>
      {!v ? <p className="muted">No version yet.</p> : (
        <>
          <Tabs tabs={[{ id: "structure", label: "Questions" },
            ...(f.type === "custom" ? [{ id: "keychecks", label: "Key Checks" }, { id: "ratings", label: "Ratings" }] : [])]} value={tab} onChange={(t) => setTab(t as typeof tab)} />
          {tab === "structure" && (
            <div className="builder">
              <Canvas pages={pages} pageId={pageId} sel={sel} onSelect={onSelect} onPage={setPageId} readOnly={!edit} onDrag={onDrag}
                onAddPage={() => setAdding({ kind: "page", id: 0 })} onAddSection={(pid) => setAdding({ kind: "section", id: pid })} onAddField={(sid) => setAdding({ kind: "field", id: sid })} />
              <aside className="card inspector" aria-label="Settings">
                {!found && (
                  <div aria-label="Form settings">
                    <div className="insp-head"><div className="grow"><h2>Form settings</h2><p className="muted small">{f.type === "custom" ? "Inspection form" : `The ${f.type} form`} · key <span className="mono">{f.key}</span></p></div></div>
                    {f.type === "custom" && <>
                      <label className="check"><input type="checkbox" checked={v.use_start !== false} disabled={!edit || setSwitch.isPending} onChange={(e) => setSwitch.mutate({ use_start: e.target.checked })} /> Begins with the start form</label>
                      <label className="check"><input type="checkbox" checked={v.use_end !== false} disabled={!edit || setSwitch.isPending} onChange={(e) => setSwitch.mutate({ use_end: e.target.checked })} /> Ends with the end form
                        <InfoTip>When on, the expert fills in the start form first and the end form last, and rules here may use start.* and end.* answers. When off, those steps are skipped for this form. Changes apply to this draft and are frozen when you publish.</InfoTip></label>
                      <div className="field"><span className="label-row">Who sees submissions</span>
                        <div className="bar" style={{ margin: 0 }}><span className="muted small grow">{(f.submission_roles ?? ["expert", "ops"]).join(", ")} and Admin</span><button className="sm" onClick={() => setVisibility(f.submission_roles ?? ["expert", "ops"])}>Change</button></div></div>
                    </>}
                    <p className="muted small" style={{ borderTop: "1px solid var(--line)", paddingTop: 10 }}>Click a page, a section or a question to change it. Drag the grips to reorder.</p>
                  </div>)}
                {found?.field && (
                  <FieldEditor field={found.field} choices={choices} readOnly={!edit || !!found.field.library || found.section!.locked} kind={f.type}
                    siblings={found.section!.fields.filter((x) => x.id !== found.field!.id)}
                    parents={{ section: found.section!.access, page: found.page.access }}
                    lists={(lists.data ?? []).map((l) => ({ key: l.key, name: l.name }))} categories={categories}
                    checks={v.checks.filter((c) => c.fields.includes(found.field!.key))}
                    onSave={(d: FieldDraft, vals?: ValidationDraft[]) => run(async () => {
                      await api(`fields/${found.field!.id}`, { method: "PATCH", body: d });
                      if (vals) await saveValidations(v.id, v.checks.filter((c) => c.fields.includes(found.field!.key)), vals);
                    }, "Saved.")}
                    onDelete={() => setConfirmDel(() => () => run(async () => { await api(`fields/${found.field!.id}`, { method: "DELETE" }); setSel(null); }))}
                    extra={<>
                      {edit && !found.section!.locked && sectionOptions.length > 1 && (
                        <div className="field"><span className="label-row"><label htmlFor="move-field">Move to section</label></span>
                          <select id="move-field" value={found.section!.id} onChange={(e) => move({ kind: "field", id: found.field!.id }, { kind: "section", id: Number(e.target.value) })}>
                            {sectionOptions.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}</select></div>)}
                    </>}
                    outside={<LibraryBox kind="field" id={found.field.id} library={found.field.library} readOnly={!edit} onDone={reload} />} />
                )}
                {found?.section && !found.field && (
                  <ContainerEditor kind="section" item={found.section} pages={pages} choices={choices} formKind={f.type} parentAccess={found.page.access} readOnly={!edit}
                    onSave={(b) => run(() => api(`sections/${found.section!.id}`, { method: "PATCH", body: b }), "Saved.")}
                    onMove={(pid) => move({ kind: "section", id: found.section!.id }, { kind: "page", id: pid })} onChanged={reload}
                    onDelete={() => setConfirmDel(() => () => run(async () => { await api(`sections/${found.section!.id}`, { method: "DELETE" }); setSel(null); }))} />
                )}
                {found?.page && !found.section && (
                  <ContainerEditor kind="page" item={found.page} pages={pages} choices={choices} formKind={f.type} readOnly={!edit}
                    onSave={(b) => run(() => api(`pages/${found.page.id}`, { method: "PATCH", body: b }), "Saved.")} onMove={() => {}} onChanged={reload}
                    onDelete={() => setConfirmDel(() => () => run(async () => { await api(`pages/${found.page.id}`, { method: "DELETE" }); setSel(null); }))} />
                )}
              </aside>
            </div>
          )}
          {tab === "keychecks" && <KeyChecks version={v} choices={choices} edit={edit} run={(fn) => void run(fn, "Key Checks saved.")} />}
          {tab === "ratings" && <Ratings version={v} sections={pages.flatMap((p) => p.sections.map((s) => s.title))} edit={edit} run={(fn) => void run(fn)} />}
        </>
      )}
      {adding?.kind === "page" && <NameDialog title="Add a page" label="Page name" onCancel={() => setAdding(null)} onOk={(title) => { setAdding(null); void run(() => api(`form-versions/${v!.id}/pages`, { body: { title } })); }} />}
      {adding?.kind === "section" && <AddSectionDialog onClose={() => setAdding(null)}
        onBlank={(title) => { const pid = adding.id; setAdding(null); void run(() => api(`pages/${pid}/sections`, { body: { title } })); }}
        onLibrary={(item, link) => { const pid = adding.id; setAdding(null); void run(() => api(`pages/${pid}/sections/from-library`, { body: { library_item: item, link } })); }} />}
      {adding?.kind === "field" && <AddFieldDialog sectionTitle={pages.flatMap((p) => p.sections).find((s) => s.id === adding.id)?.title ?? ""} onClose={() => setAdding(null)}
        onAdd={(body) => { const sid = adding.id; setAdding(null); void run(async () => {
          const { __file, ...rest } = body as { __file?: File } & Record<string, unknown>;
          if (__file) { const up = await uploadFile<{ id: string }>("form-assets", __file); rest.config = { asset: up.id }; }
          if (rest.type === "photo") {                // a photo added under a check shows that check
            const of = photoOfDefault(pages.flatMap((p) => p.sections).find((s) => s.id === sid)?.fields ?? []);
            if (of) rest.config = { ...(rest.config as Record<string, unknown>), photo_of: of };
          }
          const r = await api<FormField>(`sections/${sid}/fields`, { body: rest }); setSel({ kind: "field", id: r.id });
        }); }}
        onLibrary={(item, link) => { const sid = adding.id; setAdding(null); void run(async () => { const r = await api<FormField>(`sections/${sid}/fields/from-library`, { body: { library_item: item, link } }); setSel({ kind: "field", id: r.id }); }); }} />}
      {visibility && (
        <Modal title="Who can see this form's submissions" onClose={() => setVisibility(null)}
          actions={<><button onClick={() => setVisibility(null)}>Cancel</button>
            <button className="primary" disabled={!can("forms.edit")} onClick={async () => { try { await api(`forms/${id}`, { method: "PATCH", body: { submission_roles: visibility } }); say("Saved."); setVisibility(null); await reload(); } catch (e) { fail(e); } }}>Save</button></>}>
          <p className="muted">Choose who can open the answers of this form after they are submitted. Someone left out sees nothing of it: not on the booking, not in search, not in the report, not in downloads.
            <InfoTip>This is about seeing the finished submission. Experts can always fill in and submit their own bookings. Per-field access (the Access tab on each field) still applies on top for everyone who is allowed.</InfoTip></p>
          <label className="check"><input type="checkbox" checked disabled /> Admin (always)</label>
          {(["ops", "expert"] as const).map((r) => (
            <label className="check" key={r}><input type="checkbox" checked={visibility.includes(r)}
              onChange={(e) => setVisibility(e.target.checked ? [...visibility, r] : visibility.filter((x) => x !== r))} /> {r === "ops" ? "Ops" : "Experts (their own bookings only)"}</label>
          ))}
        </Modal>
      )}
      {renaming !== null && (
        <Modal title="Rename this form" onClose={() => setRenaming(null)}
          actions={<><button onClick={() => setRenaming(null)}>Cancel</button>
            <button className="primary" disabled={!renaming.trim() || renaming.trim() === f.name} onClick={async () => { try { await api(`forms/${id}`, { method: "PATCH", body: { name: renaming.trim() } }); say("Renamed."); setRenaming(null); await reload(); } catch (e) { fail(e); } }}>Save</button></>}>
          <Field label="Name" help={f.type === "custom" ? "This is what Ops pick from when they create a booking." : "Only the name changes. This form stays the form of its kind."}>
            <input aria-label="Name" value={renaming} onChange={(e) => setRenaming(e.target.value)} /></Field>
        </Modal>)}
      {duplicating && <DuplicateDialog form={f} onClose={() => setDuplicating(false)} />}
      {preview && v && <PreviewDialog tree={{ pages, checks: v.checks }} kind={ns} onClose={() => setPreview(false)} />}
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


/** Field names a condition can point at: this form's fields plus the other forms' (booking, start,
 *  end). A custom form only offers start / end while it begins / ends with them. */
export function useFieldChoices(f: FormSummary | undefined, v: FormVersion | undefined): FieldChoice[] {
  const forms = useList<FormSummary>("forms", "forms");
  const wanted = (x: FormSummary) => x.type !== "custom" && x.type !== f?.type && !!x.published_version
    && !(f?.type === "custom" && ((x.type === "start" && v?.use_start === false) || (x.type === "end" && v?.use_end === false)));
  const others = (forms.data ?? []).filter(wanted);
  const tree = useQuery({
    queryKey: ["choice-trees", others.map((o) => o.published_version!.id).join(",")],
    enabled: others.length > 0,
    queryFn: async () => Promise.all(others.map(async (o) => ({ ns: o.type as string, v: await api<FormVersion>(`form-versions/${o.published_version!.id}`) }))),
  });
  return useMemo(() => {
    const out: FieldChoice[] = [];
    const add = (ns: string, ver: FormVersion | undefined) => ver?.pages.forEach((p) => p.sections.forEach((s) => s.fields.forEach((fl: FormField) => out.push({ value: `${ns}.${fl.key}`, label: `${ns}: ${fl.label || fl.key}`, type: fl.type }))));
    add(f ? nsOf(f.type) : "inspection", v);
    (tree.data ?? []).filter((t) => others.some((o) => o.type === t.ns)).forEach((t) => add(t.ns, t.v));
    return out;
  }, [f?.type, v, tree.data, others.length]); // eslint-disable-line react-hooks/exhaustive-deps
}

/** Saves a field's validations: removed ones are deleted, new ones created, changed ones updated. */
async function saveValidations(versionId: number, before: Check[], after: ValidationDraft[]) {
  for (const c of before) if (!after.some((a) => a.id === c.id)) await api(`checks/${c.id}`, { method: "DELETE" });
  for (const a of after) {
    const old = before.find((c) => c.id === a.id);
    if (!old) await api(`form-versions/${versionId}/checks`, { body: { rule: a.rule, message: a.message, fields: a.fields } });
    else if (JSON.stringify([old.rule, old.message]) !== JSON.stringify([a.rule, a.message])) await api(`checks/${a.id}`, { method: "PATCH", body: { rule: a.rule, message: a.message } });
  }
}

/** The name a form's answers go by in rules: the custom form is "inspection". */
export const nsOf = (type: string) => (type === "custom" ? "inspection" : type) as "booking" | "start" | "end" | "inspection";
