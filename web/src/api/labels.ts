import { useQuery } from "@tanstack/react-query";
import { api } from "./client";
import { asList } from "./hooks";
import type { MasterListItem } from "./types";

/** key -> label for a master list (cities, car models, inspection types...). */
export function useLabels(list: string): (key: unknown) => string {
  const q = useQuery({ queryKey: ["list-items", list], staleTime: 300_000, queryFn: async () => asList<MasterListItem>(await api(`master-lists/${list}/items`)) });
  const map = new Map((q.data ?? []).map((i) => [i.key, i.label]));
  return (key) => (key === undefined || key === null || key === "" ? "" : map.get(String(key)) ?? String(key));
}

export const STAGE_LABEL: Record<string, string> = {
  draft: "Not assigned", assigned: "Assigned", in_progress: "In progress", submitted: "Uploading", completed: "Completed", cancelled: "Cancelled",
};
export const STAGE_TONE: Record<string, "ok" | "warn" | "bad" | "info" | undefined> = {
  draft: undefined, assigned: "info", in_progress: "warn", submitted: "warn", completed: "ok", cancelled: "bad",
};
