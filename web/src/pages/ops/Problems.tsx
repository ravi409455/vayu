import { useState } from "react";
import { Link } from "react-router-dom";
import { NEED_KIND, useNeeds, type Need } from "../../lib/problems";
import { fmtStamp } from "../../lib/format";
import { Empty, LoadError, PageHeader } from "../../ui/kit";

/** One inbox of everything that needs a person, most urgent first, filterable by kind. */
export function Problems() {
  const { needs, total, loading, error, refetch } = useNeeds();
  const [kind, setKind] = useState<Need["kind"] | "">("");
  const kinds = (Object.keys(NEED_KIND) as Need["kind"][]).filter((k) => needs.some((n) => n.kind === k));
  const shown = needs.filter((n) => !kind || n.kind === kind);
  return (
    <>
      <PageHeader title="Needs you" count={loading || error ? undefined : total} subtitle="Things a person has to sort out. Each one opens the booking." />
      {needs.length > 0 && (
        <div className="seg" role="group" aria-label="Kind" style={{ marginBottom: 12 }}>
          <button aria-pressed={kind === ""} onClick={() => setKind("")}>All {needs.length}</button>
          {kinds.map((k) => <button key={k} aria-pressed={kind === k} onClick={() => setKind(k)}>{NEED_KIND[k]} {needs.filter((n) => n.kind === k).length}</button>)}
        </div>)}
      {error ? <LoadError error={error} what="what needs you" onRetry={refetch} />
        : total > needs.length && <p className="muted small">Showing the first {needs.length} of {total}. Open Bookings to see the rest.</p>}
      {!loading && !error && needs.length === 0 && <Empty title="All clear">No unassigned bookings today, stuck uploads, conflicts, report problems or rejected type changes.</Empty>}
      {shown.length > 0 && (
        <div className="table-card inbox" role="list" aria-label="Needs you">
          {shown.map((n) => (
            <div key={n.key} className="inbox-row" role="listitem">
              <span className={`dot ${n.tone}`} aria-hidden="true" />
              <div className="grow" style={{ minWidth: 0 }}>
                <div className="need-title">{n.title}</div>
                <div className="need-meta">{n.meta}{n.at ? ` · since ${fmtStamp(n.at)}` : ""}</div>
              </div>
              <span className="chip">{NEED_KIND[n.kind]}</span>
              <Link className={`btn sm${n.tone === "bad" ? " primary" : ""}`} to={n.to}>{n.action}</Link>
            </div>))}
        </div>)}
    </>
  );
}
