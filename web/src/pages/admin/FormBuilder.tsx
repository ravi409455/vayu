import { useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { api, ApiError, explain } from "../../api/client";
import { asList, useList, useRefresh } from "../../api/hooks";
import type { Check, FormField, FormPage, FormSection, FormSummary, FormVersion, MasterList, RatingConfig } from "../../api/types";
import { useAuth } from "../../auth";
import { AccessMatrix } from "../../ui/AccessMatrix";
import { ConditionBuilder, type FieldChoice } from "../../ui/ConditionBuilder";
import { Confirm, Field, Modal, NameDialog, Pill, Tabs, useToast } from "../../ui/kit";
import { defaultConfig, FIELD_TYPES, slugKey } from "../../lib/fieldTypes";
import { FieldEditor, type FieldDraft } from "./FieldEditor";

type Sel = { kind: "page"; id: number } | { kind: "section"; id: number } | { kind: "field"; id: number } | null;
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
  const [sel, setSel] = useState<Sel>(null);
  const [tab, setTab] = useState<"structure" | "checks" | "ratings">("structure");
  const [publish, setPublish] = useState<{ issues: Issue[]; warnings: Issue[]; done: boolean } | null>(null);
  const [adding, setAdding] = useState<{ section: FormSection } | null>(null);
  const [ask, setAsk] = useState<null | { title: string; label: string; ok: (v: string) => void }>(null);
  const [confirmDel, setConfirmDel] = useState<null | (() => void)>(null);
  const edit = can("forms.edit") && draft;
  const v = version.data;
  const reload = () => Promise.all([refresh("version"), refresh("form"), refresh("forms")]);

  const mutate = useMutation({
    mutationFn: (fn: () => Promise<unknown>) => fn(),
    onSuccess: () => reload(),
    onError: fail,
  });
  const run = (fn: () => Promise<unknown>) => mutate.mutate(fn);

  const choices = useFieldChoices(f, v);
  const categories = (v?.rating_config?.categories ?? []).map((c) => c.key);
  const selected = useMemo(() => {
    if (!v || !sel) return null;
    for (const p of v.pages) {
      if (sel.kind === "page" && p.id === sel.id) return { page: p };
      for (const s of p.sections) {
        if (sel.kind === "section" && s.id === sel.id) return { section: s };
        for (const fl of s.fields) if (sel.kind === "field" && fl.id === sel.id) return { field: fl };
      }
    }
    return null;
  }, [v, sel]);

  if (!f) return <p className="muted pad">Loading…</p>;

  async function startDraft() {
    try { await api(`forms/${id}/drafts`, { body: {} }); await reload(); } catch (e) { fail(e); }
  }
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

  return (
    <>
      <div className="bar">
        <h1 className="grow">{f.name} <span className="muted mono small">{f.key}</span></h1>
        {f.published_version && <Pill tone="ok">Live: v{f.published_version.number}</Pill>}
        {draft ? <Pill tone="info">Editing draft v{f.draft_version!.number}</Pill> : can("forms.edit") && <button className="primary" onClick={startDraft}>Start a new draft</button>}
        {draft && can("forms.publish") && <button className="primary" onClick={checkAndPublish}>Check &amp; publish…</button>}
        {f.kind === "inspection" && f.published_version && can("forms.promote") && (
          <a className="btn" href={`/api/v1/promote/export?version=${f.published_version.id}`} download>Export bundle</a>
        )}
      </div>
      {!draft && <p className="muted">This version is published and cannot be changed. Start a draft to make changes; the live version keeps working until you publish.</p>}
      {!v ? <p className="muted">No version yet.</p> : (
        <>
          <Tabs tabs={[{ id: "structure", label: "Questions" }, { id: "checks", label: "Key Checks" }, { id: "ratings", label: "Ratings" }]} value={tab} onChange={setTab} />
          {tab === "structure" && (
            <div className="split">
              <div className="card" aria-label="Structure">
                {v.pages.map((p) => (
                  <div key={p.id}>
                    <div className={`tree-item${sel?.kind === "page" && sel.id === p.id ? " on" : ""}`} onClick={() => setSel({ kind: "page", id: p.id })}>📄 {p.title}</div>
                    {p.sections.map((s) => (
                      <div className="indent" key={s.id}>
                        <div className={`tree-item${sel?.kind === "section" && sel.id === s.id ? " on" : ""}`} onClick={() => setSel({ kind: "section", id: s.id })}>▸ {s.title}{s.library && " 🔗"}</div>
                        {s.fields.map((fl) => (
                          <div className={`tree-item indent${sel?.kind === "field" && sel.id === fl.id ? " on" : ""}`} key={fl.id} onClick={() => setSel({ kind: "field", id: fl.id })}>
                            {fl.label || fl.key}{fl.required && " *"}{fl.library?.update_available && <Pill tone="warn">update</Pill>}
                          </div>
                        ))}
                        {edit && <button className="link indent" onClick={() => setAdding({ section: s })}>+ Add field</button>}
                      </div>
                    ))}
                    {edit && <button className="link indent" onClick={() => setAsk({ title: "Add a section", label: "Section name", ok: (title) => run(() => api(`pages/${p.id}/sections`, { body: { title } })) })}>+ Add section</button>}
                  </div>
                ))}
                {edit && <button className="link" onClick={() => setAsk({ title: "Add a page", label: "Page name", ok: (title) => run(() => api(`form-versions/${v.id}/pages`, { body: { title } })) })}>+ Add page</button>}
              </div>
              <div className="card">
                {!selected && <p className="muted">Choose a page, section or field on the left.</p>}
                {selected?.field && (
                  <FieldEditor field={selected.field} choices={choices} readOnly={!edit}
                    lists={(lists.data ?? []).map((l) => ({ key: l.key, name: l.name }))} categories={categories}
                    onSave={(d: FieldDraft) => run(async () => { await api(`fields/${selected.field!.id}`, { method: "PATCH", body: d }); say("Saved."); })}
                    onDelete={() => setConfirmDel(() => () => run(async () => { await api(`fields/${selected.field!.id}`, { method: "DELETE" }); setSel(null); }))} />
                )}
                {selected?.section && <ContainerEditor kind="section" item={selected.section} choices={choices} readOnly={!edit}
                  onSave={(b) => run(async () => { await api(`sections/${selected.section!.id}`, { method: "PATCH", body: b }); say("Saved."); })}
                  onDelete={() => setConfirmDel(() => () => run(async () => { await api(`sections/${selected.section!.id}`, { method: "DELETE" }); setSel(null); }))} />}
                {selected?.page && <ContainerEditor kind="page" item={selected.page} choices={choices} readOnly={!edit}
                  onSave={(b) => run(async () => { await api(`pages/${selected.page!.id}`, { method: "PATCH", body: b }); say("Saved."); })}
                  onDelete={() => setConfirmDel(() => () => run(async () => { await api(`pages/${selected.page!.id}`, { method: "DELETE" }); setSel(null); }))} />}
              </div>
            </div>
          )}
          {tab === "checks" && <Checks version={v} choices={choices} edit={edit} run={run} />}
          {tab === "ratings" && <Ratings version={v} sections={v.pages.flatMap((p) => p.sections.map((s) => s.title))} edit={edit} run={run} />}
        </>
      )}
      {ask && <NameDialog title={ask.title} label={ask.label} onCancel={() => setAsk(null)} onOk={(val) => { ask.ok(val); setAsk(null); }} />}
      {adding && <AddField section={adding.section} onClose={() => setAdding(null)}
        onAdd={(body) => { setAdding(null); run(async () => { await api(`sections/${adding.section.id}/fields`, { body }); }); }} />}
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

function ContainerEditor({ kind, item, choices, readOnly, onSave, onDelete }: {
  kind: "page" | "section"; item: FormPage | FormSection; choices: FieldChoice[]; readOnly: boolean;
  onSave: (b: Record<string, unknown>) => void; onDelete: () => void;
}) {
  const [d, setD] = useState({ title: item.title, visible: item.visible, show_if: item.show_if, access: item.access });
  const [for_, setFor] = useState(item.id);
  if (for_ !== item.id) { setFor(item.id); setD({ title: item.title, visible: item.visible, show_if: item.show_if, access: item.access }); }
  const locked = "locked" in item && item.locked;
  return (
    <div>
      <h2>{kind === "page" ? "Page" : "Section"}</h2>
      <fieldset disabled={readOnly} style={{ border: 0, padding: 0 }}>
        <Field label="Title"><input value={d.title} disabled={locked} onChange={(e) => setD({ ...d, title: e.target.value })} /></Field>
        <label className="check"><input type="checkbox" checked={d.visible} onChange={(e) => setD({ ...d, visible: e.target.checked })} /> Visible</label>
        <ConditionBuilder label="Show only if" value={d.show_if} onChange={(r) => setD({ ...d, show_if: r })} fields={choices} />
        <h3>Who can see or change everything inside</h3>
        <AccessMatrix value={d.access} onChange={(a) => setD({ ...d, access: a })} />
      </fieldset>
      {!readOnly && <div className="bar" style={{ marginTop: 14 }}><button className="primary" onClick={() => onSave(d)}>Save</button><button className="danger" onClick={onDelete}>Delete</button></div>}
    </div>
  );
}

function AddField({ section, onClose, onAdd }: { section: FormSection; onClose: () => void; onAdd: (b: Record<string, unknown>) => void }) {
  const [label, setLabel] = useState("");
  const [key, setKey] = useState("");
  const [type, setType] = useState("short_text");
  const groups = [...new Set(FIELD_TYPES.map((t) => t.group))];
  return (
    <Modal title={`Add a field to “${section.title}”`} onClose={onClose}
      actions={<><button onClick={onClose}>Cancel</button><button className="primary" disabled={!label || !key} onClick={() => onAdd({ key, label, type, config: defaultConfig(type) })}>Add</button></>}>
      <Field label="Label"><input value={label} onChange={(e) => { setLabel(e.target.value); if (!key || key === slugKey(label)) setKey(slugKey(e.target.value)); }} /></Field>
      <Field label="Key" help="Used by reports, the API and integrations. It can never change."><input value={key} onChange={(e) => setKey(e.target.value)} /></Field>
      <Field label="Type"><select value={type} onChange={(e) => setType(e.target.value)}>
        {groups.map((g) => <optgroup key={g} label={g}>{FIELD_TYPES.filter((t) => t.group === g).map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}</optgroup>)}</select></Field>
    </Modal>
  );
}

function Checks({ version, choices, edit, run }: { version: FormVersion; choices: FieldChoice[]; edit: boolean; run: (fn: () => Promise<unknown>) => void }) {
  const [adding, setAdding] = useState<{ rule: unknown; message: string; fields: string } | null>(null);
  return (
    <>
      <p className="muted">Key Checks warn when answers contradict each other. Ops see the message on the submission; they never block the expert.</p>
      <table><thead><tr><th>Message</th><th>Fields</th><th /></tr></thead>
        <tbody>{version.checks.map((c: Check) => (
          <tr key={c.id}><td>{c.message}</td><td className="mono">{c.fields.join(", ")}</td>
            <td>{edit && <button className="link" onClick={() => run(() => api(`checks/${c.id}`, { method: "DELETE" }))}>Delete</button>}</td></tr>))}</tbody></table>
      {edit && <button className="primary" style={{ marginTop: 10 }} onClick={() => setAdding({ rule: null, message: "", fields: "" })}>Add a check</button>}
      {adding && (
        <Modal title="New Key Check" onClose={() => setAdding(null)}
          actions={<><button onClick={() => setAdding(null)}>Cancel</button><button className="primary" disabled={!adding.message || !adding.fields || adding.rule === null}
            onClick={() => { const a = adding; setAdding(null); run(() => api(`form-versions/${version.id}/checks`, { body: { rule: a.rule, message: a.message, fields: a.fields.split(",").map((x) => x.trim()).filter(Boolean) } })); }}>Add</button></>}>
          <ConditionBuilder label="Problem when" value={adding.rule} onChange={(r) => setAdding({ ...adding, rule: r })} fields={choices} />
          <Field label="Message"><input value={adding.message} onChange={(e) => setAdding({ ...adding, message: e.target.value })} /></Field>
          <Field label="Field keys it points at" help="Comma separated, e.g. odometer, door"><input value={adding.fields} onChange={(e) => setAdding({ ...adding, fields: e.target.value })} /></Field>
        </Modal>
      )}
    </>
  );
}

const DEFAULT_RATING: RatingConfig = { categories: [], deductions: { minor: 0.25, major: 1, critical: 3 }, thresholds: { excellent: 4.5, good: 3.5, average: 2.5 } };

function Ratings({ version, sections, edit, run }: { version: FormVersion; sections: string[]; edit: boolean; run: (fn: () => Promise<unknown>) => void }) {
  const [cfg, setCfg] = useState<RatingConfig>({ ...DEFAULT_RATING, ...(version.rating_config ?? {}) });
  const cats = cfg.categories ?? [];
  const setCat = (i: number, p: Partial<NonNullable<RatingConfig["categories"]>[number]>) => setCfg({ ...cfg, categories: cats.map((c, j) => (j === i ? { ...c, ...p } : c)) });
  return (
    <>
      <p className="muted">Each category starts at 5. Every defect deducts points by severity (minimum 1). The overall rating is the average; a Critical defect caps it at “Average”. Experts never see any of this.</p>
      {cats.map((c, i) => (
        <div className="card" key={i}>
          <div className="grid2">
            <Field label="Category label"><input value={c.label} disabled={!edit} onChange={(e) => setCat(i, { label: e.target.value, key: c.key || slugKey(e.target.value) })} /></Field>
            <Field label="Key"><input value={c.key} disabled={!edit} onChange={(e) => setCat(i, { key: e.target.value })} /></Field>
          </div>
          <Field label="Sections counted in this category" help="Hold Ctrl/Cmd to pick several.">
            <select multiple disabled={!edit} value={c.sections} onChange={(e) => setCat(i, { sections: [...e.target.selectedOptions].map((o) => o.value) })} style={{ minHeight: 110 }}>
              {sections.map((s) => <option key={s}>{s}</option>)}</select></Field>
          {edit && <button className="link" onClick={() => setCfg({ ...cfg, categories: cats.filter((_, j) => j !== i) })}>Remove category</button>}
        </div>
      ))}
      {edit && <button onClick={() => setCfg({ ...cfg, categories: [...cats, { key: "", label: "", sections: [] }] })}>+ Add category</button>}
      <h3>Points taken off per defect</h3>
      <div className="grid2">
        {(["minor", "major", "critical"] as const).map((k) => (
          <Field key={k} label={k[0]!.toUpperCase() + k.slice(1)}><input type="number" step="0.25" disabled={!edit} value={cfg.deductions?.[k] ?? 0} onChange={(e) => setCfg({ ...cfg, deductions: { ...DEFAULT_RATING.deductions!, ...cfg.deductions, [k]: Number(e.target.value) } })} /></Field>))}
      </div>
      <h3>Overall word cut-offs (average at least…)</h3>
      <div className="grid2">
        {Object.entries(cfg.thresholds ?? {}).map(([w, n]) => (
          <Field key={w} label={w[0]!.toUpperCase() + w.slice(1)}><input type="number" step="0.1" disabled={!edit} value={n} onChange={(e) => setCfg({ ...cfg, thresholds: { ...cfg.thresholds, [w]: Number(e.target.value) } })} /></Field>))}
      </div>
      {edit && <button className="primary" style={{ marginTop: 10 }} onClick={() => run(() => api(`form-versions/${version.id}/rating-config`, { method: "PATCH", body: { config: cfg } }))}>Save ratings</button>}
    </>
  );
}

/** Field names a condition can point at: this form's fields plus the other forms' (booking, ops). */
function useFieldChoices(f: FormSummary | undefined, v: FormVersion | undefined): FieldChoice[] {
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

export { explain };
