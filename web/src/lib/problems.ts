import { useQuery } from "@tanstack/react-query";
import { api, type Page } from "../api/client";
import type { Booking } from "../api/types";
import { useAuth } from "../auth";

export type Stuck = { id: string; booking: string; booking_id: string; field_key: string; status: string; expert: string; created_at: string };
export type PdfProblem = { booking: string; booking_id: string; status: string; stale: boolean; error: string };

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
  const lists = { stuck: stuck.data ?? [], pdf: pdf.data ?? [], conflicts: conflicts.data?.results ?? [], types: types.data?.results ?? [] };
  return { ...lists, total: lists.stuck.length + lists.pdf.length + lists.conflicts.length + lists.types.length,
    loading: stuck.isLoading || pdf.isLoading || conflicts.isLoading || types.isLoading };
}
