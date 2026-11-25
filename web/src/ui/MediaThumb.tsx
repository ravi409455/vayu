import { useQuery } from "@tanstack/react-query";
import { FileText, ImageOff } from "lucide-react";
import { api, ApiError } from "../api/client";
import { keys } from "../api/keys";

/** `removed`: deleted after the storage time Admin set (Settings); no links then. */
export type MediaLinks = { url: string; preview_url: string | null; content_type?: string; removed?: boolean };
export const REMOVED_NOTE = "Deleted after the storage time set in Settings";
export const mediaUrl = (id: string) => api<MediaLinks>(`media/${id}/url`)
  .catch((e) => (e instanceof ApiError && e.code === "MEDIA_REMOVED" ? { url: "", preview_url: null, removed: true } : null));
/** A document (a PDF) has no picture to show: it gets a document tile instead. */
export const isPdf = (l: MediaLinks) => l.content_type === "application/pdf";

/** Signed links last an hour on the server (MEDIA_URL_TTL): a page left open gets fresh ones before then. */
export const LINK_REFRESH_MS = 50 * 60_000;

/** The signed links of one uploaded file (shared cache: a gallery and a sheet ask once). */
export function useMediaUrl(id: string) {
  // a file still being checked has no link yet: ask again every 3 s for a minute
  return useQuery({ queryKey: keys.mediaUrl(id), staleTime: 600_000, queryFn: () => mediaUrl(id),
    refetchInterval: (q) => (!q.state.data ? (q.state.dataUpdateCount < 20 ? 3000 : false) : LINK_REFRESH_MS) }).data;
}

/** A small picture (or the first frame of a video, or a PDF tile) of one uploaded file. */
export function Thumb({ id, video, size }: { id: string; video?: boolean; size?: number }) {
  const links = useMediaUrl(id);
  const style = size ? { width: size, height: (size * 3) / 4 } : undefined;
  if (!links) return <span className="thumb empty" style={style} role="img" aria-label="Not ready yet" />;
  if (links.removed) return <span className="thumb doc" style={style} aria-label={REMOVED_NOTE} title={REMOVED_NOTE}><ImageOff size={size ? 16 : 24} aria-hidden />{!size && "Deleted"}</span>;
  if (isPdf(links)) return <span className="thumb doc" style={style} aria-label="PDF"><FileText size={size ? 16 : 24} aria-hidden />{!size && "PDF"}</span>;
  return video
    ? <video className="thumb" style={style} src={links.url} preload="metadata" muted />
    : <img className="thumb" style={style} src={links.preview_url ?? links.url} alt="" loading="lazy" />;
}
