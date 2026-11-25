import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type Page } from "./client";

/** List endpoints are either a plain array or a DRF page: both give an array. */
export function asList<T>(x: unknown): T[] {
  if (Array.isArray(x)) return x as T[];
  if (x && typeof x === "object" && Array.isArray((x as Page<T>).results)) return (x as Page<T>).results;
  return [];
}

type Query = Record<string, string | number | undefined>;
const MAX_PAGES = 40;          // ponytail: 2000 rows at 50 a page; lists that can grow past that need paging on screen

/** Every row of a list endpoint: follows the server's pages to the end. */
export async function fetchAll<T>(path: string, query?: Query, signal?: AbortSignal): Promise<T[]> {
  const out: T[] = [];
  for (let page = 1; page <= MAX_PAGES; page++) {
    const r = await api(path, { query: page === 1 ? query : { ...query, page }, signal });
    if (Array.isArray(r)) return r as T[];
    if (!r || typeof r !== "object" || !Array.isArray((r as Page<T>).results)) return out;
    out.push(...(r as Page<T>).results);
    if (!(r as Page<T>).next) return out;
  }
  return out;
}

/** Every row of a list, cached under a key from `keys` (the query is added to it). */
export function useList<T>(key: readonly unknown[], path: string, query?: Query) {
  return useQuery({ queryKey: query ? [...key, query] : key, queryFn: ({ signal }) => fetchAll<T>(path, query, signal) });
}

/** Refresh by `keys` prefixes: `refresh(keys.booking())` reaches every booking query. */
export function useRefresh() {
  const qc = useQueryClient();
  return (...ks: readonly unknown[][]) => Promise.all(ks.map((k) => qc.invalidateQueries({ queryKey: k })));
}
