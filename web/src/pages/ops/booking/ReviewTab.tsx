import { useRef } from "react";
import { api } from "../../../api/client";
import type { Booking, Inspection } from "../../../api/types";
import { useAuth } from "../../../auth";
import { InfoTip } from "../../../ui/InfoTip";
import { Empty, Pill, useToast } from "../../../ui/kit";
import { KeyCheckRow } from "./KeyCheckRow";
import { Seg } from "./Seg";
import { opsMayEdit } from "../../../lib/actions";
import type { Trees } from "./parts";

const WORDS = ["excellent", "good", "average", "bad"];

/** Ops review a booking: Key Checks (their own text wins), the overall word and category ratings. */
export function ReviewTab({ booking, insp, trees, onSaved }: { booking: Booking; insp?: Inspection; trees: Trees; onSaved: () => void }) {
  const { can } = useAuth();
  const { say, fail } = useToast();
  // Quick clicks: each save waits for the one before and sends the row version it got back, so
  // Ops never get "changed by someone" against themselves (F-114).
  const rv = useRef(insp?.row_version ?? 0);
  if (insp && insp.row_version > rv.current) rv.current = insp.row_version;
  const chain = useRef<Promise<void>>(Promise.resolve());
  if (!insp) return <Empty title="No inspection yet">Key Checks and ratings are worked out once the expert submits.</Empty>;
  const kcs = trees.inspection?.key_checks ?? [];
  const kcOpen = opsMayEdit(booking);
  const s = insp.scores;
  const cats = trees.inspection?.rating_config?.categories ?? [];
  function send(body: Record<string, unknown>): Promise<void> {
    const next = chain.current.then(async () => {
      try {
        const r = await api<Inspection>(`inspections/${insp!.id}/overrides`, { method: "PATCH", body: { row_version: rv.current, ...body } });
        rv.current = r.row_version;
        say("Saved."); onSaved();
      } catch (e) { fail(e); }
    });
    chain.current = next;
    return next;
  }
  const edit = can("ratings.override");
  const nums = [1, 2, 3, 4, 5].map((n) => ({ v: n, label: String(n) }));
  return (
    <div className="stack">
      {kcs.length > 0 && <section className="card" aria-label="Key Checks">
        <div className="sheet-head"><h3>Key Checks <InfoTip>Worked out from the answers (or the default). Type over any of them; your text stays even if the answers change, until you reset it.</InfoTip></h3>
          {!kcOpen && <span className="muted small">Editable once the expert submits.</span>}</div>
        <div className="kc-rows">
          {kcs.map((kc) => <KeyCheckRow key={kc.key} id={`kc-${kc.key}`} label={kc.label} v={s?.key_checks?.[kc.key]} disabled={!edit || !kcOpen}
            onSave={(text) => send({ key_checks: { [kc.key]: text } })} />)}
        </div>
      </section>}
      <section className="card">
        <div className="sheet-head"><h3>Overall</h3><span className="pill">{s?.overall?.word ?? "—"}</span><span className="muted small">average {s?.overall?.average ?? "—"} · suggested {s?.overall?.suggested_word ?? "—"}</span>{s?.overall?.overridden && <Pill tone="warn">Overridden</Pill>}</div>
        <Seg label="Overall word" value={s?.overall?.overridden ? s.overall.word : null} suggested={s?.overall?.suggested_word} options={WORDS.map((w) => ({ v: w, label: w[0]!.toUpperCase() + w.slice(1) }))} disabled={!edit} onPick={(v) => send({ overall: v })} />
      </section>
      <section className="card">
        <h3 style={{ marginTop: 0 }}>Ratings</h3>
        <div className="rating-rows">
          {cats.map((c) => {
            const r = s?.ratings?.[c.key];
            return (
              <div key={c.key} className="rating-row">
                <div className="grow"><strong>{c.label}</strong> <span className="muted small">Suggested {r?.suggested ?? "—"}</span> {r?.overridden && <Pill tone="warn">Overridden</Pill>}</div>
                <Seg label={`${c.label} rating`} value={r?.overridden ? r.value : null} suggested={r?.suggested} options={nums} disabled={!edit} onPick={(v) => send({ ratings: { [c.key]: v } })} />
              </div>);
          })}
          {cats.length === 0 && <p className="muted">This form has no rating categories.</p>}
        </div>
      </section>
    </div>
  );
}
