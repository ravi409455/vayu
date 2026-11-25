import { useEffect, useMemo, useState } from "react";
import { api, ApiError } from "../../../api/client";
import type { Booking, FormPage, FormSection, Inspection } from "../../../api/types";
import { useAuth } from "../../../auth";
import { missingFields } from "../../../lib/formSpec";
import { fmtStamp } from "../../../lib/format";
import { saveDirty } from "../../../lib/saveDirty";
import { isEmpty } from "../../../rules/rules";
import { AnswerSheet, defectOf, readableFields, type SheetFilter } from "../../../ui/AnswerSheet";
import { FormRenderer } from "../../../ui/FormRenderer";
import { type Stale, StaleDialog } from "../../../ui/StaleDialog";
import { Empty, useToast } from "../../../ui/kit";
import { OpsMediaEditor } from "./OpsMediaEditor";
import { SectionEditor } from "./SectionEditor";
import { type Activity, NO_ANSWERS, onlySection, type Part, PART_ORDER, type Parts, toMediaField, type Trees } from "./parts";

export function InspectionTab({ booking, insp, trees, activity, onSaved }: { booking: Booking; insp?: Inspection; trees: Trees; activity: Activity[]; onSaved: () => void }) {
  const { can } = useAuth();
  const { say, fail } = useToast();
  const [vals, setVals] = useState<Parts>(NO_ANSWERS);
  const [dirty, setDirty] = useState<Parts>(NO_ANSWERS);
  const [stale, setStale] = useState<Stale | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [filter, setFilter] = useState<SheetFilter>("all");
  const [editing, setEditing] = useState<{ part: Part; page: FormPage; section: FormSection } | null>(null);
  const [saving, setSaving] = useState(false);
  const rv = insp?.row_version;
  const fromServer = (i: Inspection, d: Parts): Parts => ({ inspection: { ...(i.answers.inspection ?? {}), ...d.inspection }, start: { ...(i.answers.start ?? {}), ...d.start }, end: { ...(i.answers.end ?? {}), ...d.end } });
  useEffect(() => { if (insp) setVals(fromServer(insp, dirty)); }, [insp?.id, rv]); // eslint-disable-line react-hooks/exhaustive-deps
  const edited = useMemo(() => {
    const out: Record<Part, Set<string>> = { inspection: new Set(), start: new Set(), end: new Set() };
    activity.filter((r) => r.kind === "inspection_edited" && r.by && r.by.role !== "expert").forEach((r) => r.keys.forEach((k) => { const [part, key] = k.split("."); if (part && key && part in out) out[part as Part].add(key); }));
    return out;
  }, [activity]);
  if (!insp) return <Empty title="No inspection yet">It shows here once the expert submits it.</Empty>;
  const ctxFor = (part: Part) => ({ booking: booking.answers, ...Object.fromEntries(PART_ORDER.filter((p) => p !== part).map((p) => [p, vals[p]])) });
  const parts = PART_ORDER.filter((p) => trees[p]).map((p) => ({ part: p, tree: trees[p]! }));
  const rows = parts.flatMap(({ part, tree }) => readableFields(part, tree, vals[part], ctxFor(part)).map((r) => ({ ...r, part, v: vals[part][r.f.key] })));
  const answered = rows.filter((r) => !isEmpty(r.v)).length;
  const defects = rows.map((r) => defectOf(r.f, r.v)).filter(Boolean) as string[];
  const editedCount = rows.filter((r) => edited[r.part].has(r.f.key)).length;
  const missing = parts.reduce((n, { part, tree }) => n + missingFields(part, tree, vals[part], ctxFor(part)).length, 0);
  const mineKeys = PART_ORDER.flatMap((p) => Object.keys(dirty[p]));
  const change = (part: Part) => (k: string, v: unknown) => { setVals({ ...vals, [part]: { ...vals[part], [k]: v } }); setDirty({ ...dirty, [part]: { ...dirty[part], [k]: v } }); setErrors({ ...errors, [k]: "" }); };
  const cancel = () => { setDirty(NO_ANSWERS); setErrors({}); setVals(fromServer(insp, NO_ANSWERS)); setEditing(null); };
  async function save(rowVersion = insp!.row_version) {
    setSaving(true);
    try {
      const r = await saveDirty((v, ch) => api(`inspections/${insp!.id}`, { method: "PATCH", body: { row_version: v, answers: ch } }), rowVersion, dirty);
      if (!r.ok) return setStale(r.stale);
      setDirty(NO_ANSWERS); setStale(null); setEditing(null); say("Saved. Ratings and Key Checks were recalculated."); onSaved();
    } catch (e) {
      if (e instanceof ApiError && e.body.errors) setErrors(e.body.errors as Record<string, string>);
      else if (e instanceof ApiError && e.code === "FIELD_ACCESS") setErrors(Object.fromEntries(((e.body.keys as string[]) ?? []).map((k) => [k, "You cannot change this now."])));
      else fail(e);
    } finally { setSaving(false); }
  }
  const canEdit = can("submissions.edit");
  const pageCounts = parts.flatMap(({ part, tree }) => tree.pages.map((p) => {
    const mine = rows.filter((r) => r.part === part && r.page.id === p.id);
    return { id: `${part}-p${p.id}`, title: p.title, n: mine.length, done: mine.filter((r) => !isEmpty(r.v)).length, defects: mine.filter((r) => defectOf(r.f, r.v)).length };
  })).filter((p) => p.n > 0);
  const major = defects.filter((d) => d === "Major").length;
  return (
    <>
      <section className="card summary-strip" aria-label="Inspection summary">
        <div><div className="muted small">Answered</div><div className="big">{answered} <span className="muted small">of {rows.length}</span></div>
          <div className="progress thin"><div style={{ width: `${rows.length ? (answered / rows.length) * 100 : 0}%` }} /></div></div>
        <div><div className="muted small">Defects</div><div className={`big${defects.length ? " bad-text" : ""}`}>{defects.length}</div><div className="muted small">{major} major · {defects.length - major} other</div></div>
        {(trees.inspection?.key_checks ?? []).length > 0 && <div><div className="muted small">Key Checks</div><div className="chips">{trees.inspection!.key_checks!.map((k) => <span key={k.key} className="chip">{k.label}: {insp.scores?.key_checks?.[k.key]?.value || "—"}</span>)}</div></div>}
        <div><div className="muted small">Required, not answered</div><div className={`big${missing ? " warn-text" : ""}`}>{missing}</div></div>
      </section>
      <div className="bar">
        <div className="seg" role="group" aria-label="Show">
          {([["all", `All ${rows.length}`], ["defects", `Defects ${defects.length}`], ["edited", `Edited by Ops ${editedCount}`], ["empty", `Not answered ${rows.length - answered}`]] as const).map(([k, l]) =>
            <button key={k} aria-pressed={filter === k} onClick={() => setFilter(k)}>{l}</button>)}
        </div>
        <span className="grow" />
        {insp.last_edited_by && <span className="muted small">Last edited by {insp.last_edited_by}, {fmtStamp(insp.last_edited_at)}</span>}
      </div>
      <div className="review">
        <nav className="card review-index" aria-label="Inspection pages">
          {pageCounts.map((p) => <a key={p.id} href={`#${p.id}`} onClick={(e) => { e.preventDefault(); document.getElementById(p.id)?.scrollIntoView({ behavior: "smooth", block: "start" }); }}>
            <span className="grow ellipsis">{p.title}</span>{p.defects > 0 && <span className="pill bad" title="Defects">{p.defects}</span>}<span className={`small ${p.done === p.n ? "ok" : "muted"}`} title="Answered">{p.done === p.n ? "✓" : `${p.done}/${p.n}`}</span></a>)}
        </nav>
        <div className="review-main">
          {parts.map(({ part, tree }) => (
            <AnswerSheet key={part} part={{ kind: part, tree, values: vals[part], ctx: ctxFor(part) }} filter={filter} edited={edited[part]} anchor={(p) => `${part}-p${p.id}`}
              onEdit={canEdit ? (page, section) => { cancel(); setEditing({ part, page, section }); } : undefined}
              editing={editing?.part === part ? { sectionId: editing.section.id, node: (
                <SectionEditor changed={mineKeys.length > 0} saving={saving} onSave={() => save()} onCancel={cancel}>
                  <FormRenderer kind={part} tree={tree} pages={onlySection(editing.page, editing.section)} values={vals[part]} ctx={ctxFor(part)} errors={errors} bookingId={booking.id} onChange={change(part)}
                    mediaEditor={(f, ids) => <OpsMediaEditor booking={booking} f={toMediaField(f, part, "")} ids={ids} onDone={onSaved} />} />
                </SectionEditor>) } : null} />
          ))}
          {filter !== "all" && rows.filter((r) => filter === "defects" ? defectOf(r.f, r.v) : filter === "edited" ? edited[r.part].has(r.f.key) : isEmpty(r.v)).length === 0 && <Empty>Nothing to show with this filter.</Empty>}
        </div>
      </div>
      {stale && <StaleDialog info={stale} mine={mineKeys} onRetry={() => save(stale.rowVersion)} onReload={() => { setDirty(NO_ANSWERS); setStale(null); setEditing(null); onSaved(); }} />}
    </>
  );
}
