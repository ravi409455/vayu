import { useQuery } from "@tanstack/react-query";
import { api, type Page } from "../api/client";
import type { Booking } from "../api/types";
import { useAuth } from "../auth";
import { addDays, fmtSlot, fmtStamp, today } from "./format";
import { FLAG_NAME, timingFlags, type Flag } from "./timing";
import { keys } from "../api/keys";

export type Stuck = {
  id: string;
  booking: string;
  booking_id: string;
  field_key: string;
  status: string;
  expert: string;
  created_at: string;
};
export type PdfProblem = { booking: string; booking_id: string; status: string; error: string };
/** A report something changed under since it was made (Ops press Regenerate, F-219). */
export type StaleReport = { booking: string; booking_id: string; since: string };
/** One row of problems/reports: a failed or stuck render, or a PDF that changed under itself. */
type ReportRow = PdfProblem & { problem: "failed" | "stuck" | "out_of_date"; out_of_date_since: string | null };

/** problems/reports, failed and out of date apart. */
export function reportProblems(rows: ReportRow[] | undefined): { failed: PdfProblem[]; outOfDate: StaleReport[] } {
  return {
    failed: (rows ?? []).filter((r) => r.problem !== "out_of_date"),
    outOfDate: (rows ?? [])
      .filter((r) => r.problem === "out_of_date")
      .map((r) => ({ booking: r.booking, booking_id: r.booking_id, since: r.out_of_date_since ?? "" })),
  };
}

/** Everything that needs a person, from the four problem queues. Shared by the Problems page,
 *  the Today page, the sidebar badge and the top-bar bell (one cache, polled every minute). */
export function useProblems() {
  const { me, can } = useAuth();
  const on = !!me && me.role !== "expert" && can("bookings.view");
  const opts = { enabled: on, staleTime: 30_000, refetchInterval: 60_000 } as const;
  const stuck = useQuery({
    ...opts,
    queryKey: keys.problems("stuck"),
    queryFn: ({ signal }) => api<Stuck[]>("problems/stuck-uploads", { signal }),
  });
  const pdf = useQuery({
    ...opts,
    queryKey: keys.problems("pdf"),
    queryFn: ({ signal }) => api<ReportRow[]>("problems/reports", { signal }),
  });
  const conflicts = useQuery({
    ...opts,
    queryKey: keys.problems("conflict"),
    queryFn: ({ signal }) => api<Page<Booking>>("bookings", { query: { problem: "conflict" }, signal }),
  });
  const types = useQuery({
    ...opts,
    queryKey: keys.problems("type"),
    queryFn: ({ signal }) => api<Page<Booking>>("bookings", { query: { problem: "type_change" }, signal }),
  });
  // started late, and finished too quickly: two separate lists (last 7 days), each until someone marks it reviewed
  const t = today();
  const flagged = (flag: Flag) => ({
    ...opts,
    enabled: on && can("bookings.review_timing"),
    queryKey: keys.problems(flag, t),
    queryFn: ({ signal }: { signal: AbortSignal }) =>
      api<Page<Booking>>("bookings", {
        query: { timing: flag, reviewed: "0", date_from: addDays(t, -6), date_to: t, order: "schedule" },
        signal,
      }),
  });
  // times stamped on an unchecked phone clock (F-222), the same last 7 days: they never clear by themselves
  const unverified = useQuery({
    ...opts,
    queryKey: keys.problems("unverified", t),
    queryFn: ({ signal }) =>
      api<Page<Booking>>("bookings", {
        query: { problem: "unverified_time", date_from: addDays(t, -6), date_to: t, order: "schedule" },
        signal,
      }),
  });
  const late = useQuery(flagged("late"));
  const quick = useQuery(flagged("quick"));
  const reports = reportProblems(pdf.data);
  const lists = {
    stuck: stuck.data ?? [],
    pdf: reports.failed,
    out_of_date: reports.outOfDate,
    conflicts: conflicts.data?.results ?? [],
    types: types.data?.results ?? [],
    late: late.data?.results ?? [],
    quick: quick.data?.results ?? [],
    unverified: unverified.data?.results ?? [],
  };
  // a page shows the first 50; the number is the server's count
  const beyond = [conflicts, types, late, quick, unverified].reduce(
    (n, q) => n + Math.max(0, (q.data?.count ?? 0) - (q.data?.results.length ?? 0)),
    0,
  );
  return {
    ...lists,
    beyond,
    total:
      lists.stuck.length +
      lists.pdf.length +
      lists.out_of_date.length +
      lists.conflicts.length +
      lists.types.length +
      lists.late.length +
      lists.quick.length +
      lists.unverified.length +
      beyond,
    loading: stuck.isLoading || pdf.isLoading || conflicts.isLoading || types.isLoading,
    error: [stuck, pdf, conflicts, types, late, quick, unverified].find((q) => q.isError)?.error ?? null,
    refetch: () => Promise.all([stuck, pdf, conflicts, types, late, quick, unverified].map((q) => q.refetch())),
  };
}

export type Need = {
  key: string;
  kind: "unassigned" | "upload" | "conflict" | "report" | "type" | "late" | "quick" | "unverified";
  tone: "warn" | "bad";
  title: string;
  meta: string;
  to: string;
  action: string;
  at?: string;
};
export const NEED_KIND: Record<Need["kind"], string> = {
  unassigned: "Unassigned today",
  upload: "Stuck uploads",
  conflict: "Conflicts",
  report: "Reports",
  type: "Type changes",
  late: "Started late",
  quick: "Too quick",
  unverified: "Unverified times",
};

/** Everything that needs a person, as one list, most urgent first: today's jobs with no expert,
 *  conflicts, stuck uploads, failed or out-of-date reports, rejected type changes. */
export function useNeeds(): { needs: Need[]; total: number; loading: boolean; error: unknown; refetch: () => Promise<unknown> } {
  const p = useProblems();
  const { me, can } = useAuth();
  const day = today();
  const open = useQuery({
    enabled: !!me && me.role !== "expert" && can("bookings.view"),
    staleTime: 30_000,
    refetchInterval: 60_000,
    queryKey: keys.bookings("unassigned-today", day),
    queryFn: ({ signal }) =>
      api<Page<Booking>>("bookings", { query: { stage: "draft", date_from: day, date_to: day, order: "schedule" }, signal }),
  });
  const needs: Need[] = [
    ...p.conflicts.map((b) => ({
      key: `c${b.id}`,
      kind: "conflict" as const,
      tone: "bad" as const,
      title: `${b.booking_id}: two experts submitted`,
      meta: "Choose which inspection counts",
      to: `/booking/${b.id}`,
      action: "Resolve",
    })),
    ...(open.data?.results ?? []).map((b) => ({
      key: `a${b.id}`,
      kind: "unassigned" as const,
      tone: "warn" as const,
      title: `${b.booking_id} has no expert`,
      meta: `Today at ${String(b.answers.inspection_time ?? "")} · ${String(b.answers.customer_name ?? "")}`,
      to: `/booking/${b.id}`,
      action: "Assign",
    })),
    ...p.stuck.map((s) => ({
      key: `s${s.id}`,
      kind: "upload" as const,
      tone: "bad" as const,
      title: `Upload stuck: ${s.booking_id}`,
      meta: `${s.expert} · ${s.field_key} · ${s.status}`,
      to: `/booking/${s.booking}`,
      action: "Open",
      at: s.created_at,
    })),
    // a failed render is tried again by itself; an out-of-date one waits for Ops to press Regenerate (F-219)
    ...p.out_of_date.map((r) => ({
      key: `o${r.booking}`,
      kind: "report" as const,
      tone: "warn" as const,
      title: `Report out of date: ${r.booking_id}`,
      meta: r.since ? `Changes since ${fmtStamp(r.since)}` : "Changes since the PDF was made",
      to: `/booking/${r.booking}`,
      action: "Regenerate",
      at: r.since || undefined,
    })),
    ...p.pdf.map((r) => ({
      key: `p${r.booking}`,
      kind: "report" as const,
      tone: "bad" as const,
      title: `Report failed: ${r.booking_id}`,
      meta: r.error ? `${r.error}; it is tried again by itself` : "It is tried again by itself",
      to: `/booking/${r.booking}`,
      action: "Open",
    })),
    ...(["late", "quick"] as const).flatMap((flag) =>
      p[flag].map((b) => ({
        key: `${flag}${b.id}`,
        kind: flag,
        tone: "warn" as const,
        title: `${b.booking_id}: ${(timingFlags(b.timing).find((f) => f.flag === flag)?.words ?? FLAG_NAME[flag]).toLowerCase()}`,
        meta: `${fmtSlot(b.answers.inspection_date, b.answers.inspection_time)} · ${String(b.answers.customer_name ?? "")}`,
        to: `/booking/${b.id}`,
        action: "Review",
      })),
    ),
    ...p.unverified.map((b) => ({
      key: `u${b.id}`,
      kind: "unverified" as const,
      tone: "warn" as const,
      title: `${b.booking_id}: time not verified`,
      meta: `${fmtSlot(b.answers.inspection_date, b.answers.inspection_time)} · the phone's clock was not checked that day, so its times may be off`,
      to: `/booking/${b.id}`,
      action: "Open",
    })),
    ...p.types.map((b) => ({
      key: `t${b.id}`,
      kind: "type" as const,
      tone: "warn" as const,
      title: `${b.booking_id}: type change rejected`,
      meta: b.alerts?.find((a) => a.code === "TYPE_CHANGE_REJECTED")?.detail ?? "The expert started another type",
      to: `/booking/${b.id}`,
      action: "Open",
    })),
  ];
  const extra = p.beyond + Math.max(0, (open.data?.count ?? 0) - (open.data?.results.length ?? 0));
  return {
    needs,
    total: needs.length + extra,
    loading: p.loading || open.isLoading,
    error: p.error ?? (open.isError ? open.error : null),
    refetch: () => Promise.all([p.refetch(), open.refetch()]),
  };
}
