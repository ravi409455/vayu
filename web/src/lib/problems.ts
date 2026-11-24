import { useQuery } from "@tanstack/react-query";
import { api, type Page } from "../api/client";
import type { Booking } from "../api/types";
import { useAuth } from "../auth";
import { addDays, fmtSlot, today } from "./format";
import { FLAG_NAME, timingFlags, type Flag } from "./timing";

export type Stuck = { id: string; booking: string; booking_id: string; field_key: string; status: string; expert: string; created_at: string };
export type PdfProblem = { booking: string; booking_id: string; status: string; error: string };

/** Everything that needs a person, from the four problem queues. Shared by the Problems page,
 *  the Today page, the sidebar badge and the top-bar bell (one cache, polled every minute). */
export function useProblems() {
  const { me, can } = useAuth();
  const on = !!me && me.role !== "expert" && can("bookings.view");
  const opts = { enabled: on, staleTime: 30_000, refetchInterval: 60_000 } as const;
  const stuck = useQuery({ ...opts, queryKey: ["problems", "stuck"], queryFn: () => api<Stuck[]>("problems/stuck-uploads") });
  const pdf = useQuery({ ...opts, queryKey: ["problems", "pdf"], queryFn: () => api<PdfProblem[]>("problems/reports") });
  const conflicts = useQuery({ ...opts, queryKey: ["problems", "conflict"], queryFn: () => api<Page<Booking>>("bookings", { query: { problem: "conflict" } }) });
  const types = useQuery({ ...opts, queryKey: ["problems", "type"], queryFn: () => api<Page<Booking>>("bookings", { query: { problem: "type_change" } }) });
  // started late, and finished too quickly: two separate lists (last 7 days), each until someone marks it reviewed
  const t = today();
  const flagged = (flag: Flag) => ({ ...opts, enabled: on && can("bookings.review_timing"), queryKey: ["problems", flag, t],
    queryFn: () => api<Page<Booking>>("bookings", { query: { timing: flag, reviewed: "0", date_from: addDays(t, -6), date_to: t, order: "schedule" } }) });
  const late = useQuery(flagged("late"));
  const quick = useQuery(flagged("quick"));
  const lists = { stuck: stuck.data ?? [], pdf: pdf.data ?? [], conflicts: conflicts.data?.results ?? [], types: types.data?.results ?? [],
    late: late.data?.results ?? [], quick: quick.data?.results ?? [] };
  return { ...lists, total: lists.stuck.length + lists.pdf.length + lists.conflicts.length + lists.types.length + lists.late.length + lists.quick.length,
    loading: stuck.isLoading || pdf.isLoading || conflicts.isLoading || types.isLoading };
}

export type Need = { key: string; kind: "unassigned" | "upload" | "conflict" | "report" | "type" | "late" | "quick"; tone: "warn" | "bad"; title: string; meta: string; to: string; action: string; at?: string };
export const NEED_KIND: Record<Need["kind"], string> = { unassigned: "Unassigned today", upload: "Stuck uploads", conflict: "Conflicts", report: "Reports", type: "Type changes", late: "Started late", quick: "Too quick" };

/** Everything that needs a person, as one list, most urgent first: today's jobs with no expert,
 *  conflicts, stuck uploads, failed or out-of-date reports, rejected type changes. */
export function useNeeds(): { needs: Need[]; loading: boolean } {
  const p = useProblems();
  const { me, can } = useAuth();
  const t = new Date(); const day = `${t.getFullYear()}-${String(t.getMonth() + 1).padStart(2, "0")}-${String(t.getDate()).padStart(2, "0")}`;
  const open = useQuery({ enabled: !!me && me.role !== "expert" && can("bookings.view"), staleTime: 30_000, refetchInterval: 60_000,
    queryKey: ["bookings-page", "unassigned-today", day], queryFn: () => api<Page<Booking>>("bookings", { query: { stage: "draft", date_from: day, date_to: day, order: "schedule" } }) });
  const needs: Need[] = [
    ...p.conflicts.map((b) => ({ key: `c${b.id}`, kind: "conflict" as const, tone: "bad" as const, title: `${b.booking_id}: two experts submitted`, meta: "Choose which inspection counts", to: `/booking/${b.id}`, action: "Resolve" })),
    ...(open.data?.results ?? []).map((b) => ({ key: `a${b.id}`, kind: "unassigned" as const, tone: "warn" as const, title: `${b.booking_id} has no expert`, meta: `Today at ${String(b.answers.inspection_time ?? "")} · ${String(b.answers.customer_name ?? "")}`, to: `/booking/${b.id}`, action: "Assign" })),
    ...p.stuck.map((s) => ({ key: `s${s.id}`, kind: "upload" as const, tone: "bad" as const, title: `Upload stuck: ${s.booking_id}`, meta: `${s.expert} · ${s.field_key} · ${s.status}`, to: `/booking/${s.booking}`, action: "Open", at: s.created_at })),
    // a report is made again by itself after every change: only a failed one is a problem (tried again by itself too)
    ...p.pdf.map((r) => ({ key: `p${r.booking}`, kind: "report" as const, tone: "bad" as const, title: `Report failed: ${r.booking_id}`, meta: r.error ? `${r.error}; it is tried again by itself` : "It is tried again by itself", to: `/booking/${r.booking}`, action: "Open" })),
    ...(["late", "quick"] as const).flatMap((flag) => p[flag].map((b) => ({ key: `${flag}${b.id}`, kind: flag, tone: "warn" as const,
      title: `${b.booking_id}: ${(timingFlags(b.timing).find((f) => f.flag === flag)?.words ?? FLAG_NAME[flag]).toLowerCase()}`,
      meta: `${fmtSlot(b.answers.inspection_date, b.answers.inspection_time)} · ${String(b.answers.customer_name ?? "")}`, to: `/booking/${b.id}`, action: "Review" }))),
    ...p.types.map((b) => ({ key: `t${b.id}`, kind: "type" as const, tone: "warn" as const, title: `${b.booking_id}: type change rejected`, meta: b.alerts?.find((a) => a.code === "TYPE_CHANGE_REJECTED")?.detail ?? "The expert started another type", to: `/booking/${b.id}`, action: "Open" })),
  ];
  return { needs, loading: p.loading || open.isLoading };
}
