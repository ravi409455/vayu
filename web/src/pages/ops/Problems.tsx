import { Link } from "react-router-dom";
import { useProblems } from "../../lib/problems";
import { fmtStamp } from "../../lib/format";
import { Empty, PageHeader, Pill } from "../../ui/kit";

/** Things that need a person, grouped by kind. Each row opens the booking. */
export function Problems() {
  const p = useProblems();
  const groups = [
    { title: "Uploads stuck", rows: p.stuck.map((s) => ({ to: `/booking/${s.booking}`, id: s.booking_id, text: `${s.field_key} · ${s.expert}`, meta: `${s.status} since ${fmtStamp(s.created_at)}` })) },
    { title: "Conflicts", rows: p.conflicts.map((b) => ({ to: `/booking/${b.id}`, id: b.booking_id, text: "Two experts submitted this booking", meta: String(b.answers.customer_name ?? "") })) },
    { title: "Rejected type changes", rows: p.types.map((b) => ({ to: `/booking/${b.id}`, id: b.booking_id, text: b.alerts?.find((a) => a.code === "TYPE_CHANGE_REJECTED")?.detail ?? "The expert started another type", meta: "" })) },
    { title: "PDF problems", rows: p.pdf.map((r) => ({ to: `/booking/${r.booking}`, id: r.booking_id, text: r.error || (r.stale ? "Out of date: regenerate after the edits" : r.status), meta: "" })) },
  ];
  return (
    <>
      <PageHeader title="Problems" count={p.loading ? undefined : p.total} />
      {!p.loading && p.total === 0 && <Empty title="All clear">No stuck uploads, conflicts, rejected type changes or PDF problems.</Empty>}
      {groups.filter((g) => g.rows.length > 0).map((g) => (
        <section key={g.title} className="table-card" aria-label={g.title} style={{ marginBottom: 14 }}>
          <h2 className="table-title">{g.title} <Pill tone="bad">{g.rows.length}</Pill></h2>
          <table className="rows"><tbody>{g.rows.map((r, i) => (
            <tr key={i}><td style={{ width: 140 }}><Link className="cell-main" to={r.to}>{r.id}</Link></td><td>{r.text}</td><td className="muted small">{r.meta}</td>
              <td style={{ textAlign: "right" }}><Link className="btn sm" to={r.to}>Open</Link></td></tr>))}</tbody></table>
        </section>))}
    </>
  );
}
