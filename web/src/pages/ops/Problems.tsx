import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, type Page } from "../../api/client";
import type { Booking } from "../../api/types";
import { Empty, Pill, Tabs, when, PageHeader } from "../../ui/kit";

type Tab = "stuck" | "conflicts" | "types" | "pdf";
type Stuck = { id: string; booking: string; booking_id: string; field_key: string; status: string; expert: string; created_at: string };
type PdfProblem = { booking: string; booking_id: string; status: string; stale: boolean; error: string };

export function Problems() {
  const [tab, setTab] = useState<Tab>("stuck");
  const stuck = useQuery({ queryKey: ["problems", "stuck"], queryFn: () => api<Stuck[]>("problems/stuck-uploads") });
  const pdf = useQuery({ queryKey: ["problems", "pdf"], queryFn: () => api<PdfProblem[]>("problems/reports") });
  const conflicts = useQuery({ queryKey: ["problems", "conflict"], queryFn: () => api<Page<Booking>>("bookings", { query: { problem: "conflict" } }) });
  const types = useQuery({ queryKey: ["problems", "type"], queryFn: () => api<Page<Booking>>("bookings", { query: { problem: "type_change" } }) });
  const counts = { stuck: stuck.data?.length ?? 0, conflicts: conflicts.data?.count ?? 0, types: types.data?.count ?? 0, pdf: pdf.data?.length ?? 0 };
  const label = (t: string, n: number) => `${t}${n ? ` (${n})` : ""}`;
  return (
    <>
      <PageHeader title="Problems" />
      <Tabs value={tab} onChange={setTab} tabs={[{ id: "stuck", label: label("Stuck uploads", counts.stuck) }, { id: "conflicts", label: label("Conflicts", counts.conflicts) }, { id: "types", label: label("Rejected type changes", counts.types) }, { id: "pdf", label: label("PDF problems", counts.pdf) }]} />
      {tab === "stuck" && <Rows empty="No uploads are stuck." head={["Booking", "File", "Expert", "Since"]} rows={(stuck.data ?? []).map((s) => [<Link to={`/booking/${s.booking}`}>{s.booking_id}</Link>, `${s.field_key} · ${s.status}`, s.expert, when(s.created_at)])} />}
      {tab === "conflicts" && <Rows empty="No conflicts." head={["Booking", "Conflict", "Stage"]} rows={(conflicts.data?.results ?? []).map((b) => [<Link to={`/booking/${b.id}`}>{b.booking_id}</Link>, <Pill tone="bad">{b.conflict === "TWO_EXPERTS" ? "Two experts inspected it" : "A released draft arrived"}</Pill>, b.stage])} />}
      {tab === "types" && <Rows empty="No rejected type changes." head={["Booking", "What happened"]} rows={(types.data?.results ?? []).map((b) => [<Link to={`/booking/${b.id}`}>{b.booking_id}</Link>, (b.alerts ?? []).filter((a) => a.code === "TYPE_CHANGE_REJECTED").map((a) => a.detail).join(" ")])} />}
      {tab === "pdf" && <Rows empty="Every report is up to date." head={["Booking", "Problem"]} rows={(pdf.data ?? []).map((p) => [<Link to={`/booking/${p.booking}`}>{p.booking_id}</Link>, <>{p.status === "failed" && <Pill tone="bad">Failed: {p.error}</Pill>} {p.stale && <Pill tone="warn">Edited, not regenerated</Pill>}</>])} />}
    </>
  );
}

function Rows({ head, rows, empty }: { head: string[]; rows: React.ReactNode[][]; empty: string }) {
  if (rows.length === 0) return <Empty title="All clear">{empty}</Empty>;
  return <table><thead><tr>{head.map((h) => <th key={h}>{h}</th>)}</tr></thead><tbody>{rows.map((r, i) => <tr key={i}>{r.map((c, j) => <td key={j}>{c}</td>)}</tr>)}</tbody></table>;
}
