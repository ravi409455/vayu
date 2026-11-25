import { useQuery } from "@tanstack/react-query";
import { api } from "./client";
import { fetchAll } from "./hooks";
import type { MasterListItem } from "./types";

export type InspectionType = { key: string; label: string; available: boolean };

/** The custom forms by name: what Ops pick when they book. `available` = switched on and published. */
export function useInspectionTypes(): InspectionType[] {
  const q = useQuery({ queryKey: ["inspection-types"], staleTime: 60_000, queryFn: ({ signal }) => api<InspectionType[]>("inspection-types", { signal }) });
  return q.data ?? [];
}

/** key -> the custom form's name (what used to be the inspection type's label). */
export function useTypeLabels(): (key: unknown) => string {
  const map = new Map(useInspectionTypes().map((t) => [t.key, t.label]));
  return (key) => (key === undefined || key === null || key === "" ? "" : map.get(String(key)) ?? String(key));
}

/** key -> label for a master list (cities, car models, inspection types...). */
export function useLabels(list: string): (key: unknown) => string {
  const q = useQuery({ queryKey: ["list-items", list], staleTime: 300_000, queryFn: ({ signal }) => fetchAll<MasterListItem>(`master-lists/${list}/items`, undefined, signal) });
  const map = new Map((q.data ?? []).map((i) => [i.key, i.label]));
  return (key) => (key === undefined || key === null || key === "" ? "" : map.get(String(key)) ?? String(key));
}

export const STAGE_LABEL: Record<string, string> = {
  draft: "Unassigned", assigned: "Assigned", in_progress: "In progress", submitted: "Uploading", completed: "Completed", cancelled: "Cancelled",
};
export const STAGE_TONE: Record<string, "ok" | "warn" | "bad" | "info" | undefined> = {
  draft: "warn", assigned: undefined, in_progress: "info", submitted: "info", completed: "ok", cancelled: "bad",
};
