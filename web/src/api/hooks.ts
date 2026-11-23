import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type Page } from "./client";

/** List endpoints are either a plain array or a DRF page: both give an array. */
export function asList<T>(x: unknown): T[] {
  if (Array.isArray(x)) return x as T[];
  if (x && typeof x === "object" && Array.isArray((x as Page<T>).results)) return (x as Page<T>).results;
  return [];
}

export function useList<T>(key: string, path: string, query?: Record<string, string | number | undefined>) {
  return useQuery({ queryKey: [key, query], queryFn: async () => asList<T>(await api(path, { query })) });
}

export function useRefresh() {
  const qc = useQueryClient();
  return (...keys: string[]) => Promise.all(keys.map((k) => qc.invalidateQueries({ queryKey: [k] })));
}
