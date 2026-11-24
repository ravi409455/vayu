import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import type { Booking } from "../api/types";
import { useAuth } from "../auth";

/** The time limits Admin sets on the Settings page (server: /settings/timing). */
export type TimingSettings = { late_grace_minutes: number; min_minutes_default: number; min_minutes_by_type: Record<string, number> };
export const DEFAULT_TIMING: TimingSettings = { late_grace_minutes: 15, min_minutes_default: 30, min_minutes_by_type: {} };

/** The limits, for anyone who may see the Settings page (Admin, Ops); the defaults otherwise. */
export function useTiming(): TimingSettings {
  const { can } = useAuth();
  const q = useQuery({ queryKey: ["settings", "timing"], enabled: can("settings.view"), staleTime: 60_000,
    queryFn: () => api<TimingSettings>("settings/timing") });
  return q.data ?? DEFAULT_TIMING;
}

/** 40 -> "40 min", 125 -> "2 h 5 min", 7125 -> "4 days 22 h". */
export function fmtMinutes(m: number | null): string {
  if (m === null) return "—";
  if (m < 60) return `${m} min`;
  if (m < 24 * 60) return `${Math.floor(m / 60)} h${m % 60 ? ` ${m % 60} min` : ""}`;
  const d = Math.floor(m / 1440), h = Math.floor((m % 1440) / 60);
  return `${d} day${d === 1 ? "" : "s"}${h ? ` ${h} h` : ""}`;
}

export type Flag = "late" | "quick";
export const FLAG_NAME: Record<Flag, string> = { late: "Started late", quick: "Too quick" };

/** The flags a job has, each said on its own (two different problems, reviewed apart):
 *  late -> "Started 40 min late", quick -> "Took 25 min (min 45)". Empty: nothing to flag. */
export function timingFlags(t: Booking["timing"]): { flag: Flag; words: string; reviewedBy: string | null; reviewedAt: string | null }[] {
  if (!t) return [];
  return [
    ...(t.late ? [{ flag: "late" as const, words: `Started ${fmtMinutes(t.late_minutes)} late`, reviewedBy: t.late_reviewed_by, reviewedAt: t.late_reviewed_at }] : []),
    ...(t.quick ? [{ flag: "quick" as const, words: `Took ${fmtMinutes(t.duration_minutes)} (min ${t.min_minutes})`, reviewedBy: t.quick_reviewed_by, reviewedAt: t.quick_reviewed_at }] : []),
  ];
}
