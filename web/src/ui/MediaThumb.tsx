import { useQuery } from "@tanstack/react-query";
import { FileText } from "lucide-react";
import { api } from "../api/client";

export type MediaLinks = { url: string; preview_url: string | null; content_type?: string };
export const mediaUrl = (id: string) => api<MediaLinks>(`media/${id}/url`).catch(() => null);
/** A document (a PDF) has no picture to show: it gets a document tile instead. */
export const isPdf = (l: MediaLinks) => l.content_type === "application/pdf";

/** The signed links of one uploaded file (shared cache: a gallery and a sheet ask once). */
export function useMediaUrl(id: string) {
  // a file still being checked has no link yet: ask again every 3 s for a minute
  return useQuery({ queryKey: ["media-url", id], staleTime: 600_000, queryFn: () => mediaUrl(id),
    refetchInterval: (q) => (!q.state.data && q.state.dataUpdateCount < 20 ? 3000 : false) }).data;
}

/** A small picture (or the first frame of a video, or a PDF tile) of one uploaded file. */
export function Thumb({ id, video, size }: { id: string; video?: boolean; size?: number }) {
  const links = useMediaUrl(id);
  const style = size ? { width: size, height: (size * 3) / 4 } : undefined;
  if (!links) return <span className="thumb empty" style={style} aria-label="Not ready yet" />;
  if (isPdf(links)) return <span className="thumb doc" style={style} aria-label="PDF"><FileText size={size ? 16 : 24} aria-hidden />{!size && "PDF"}</span>;
  return video
    ? <video className="thumb" style={style} src={links.url} preload="metadata" muted />
    : <img className="thumb" style={style} src={links.preview_url ?? links.url} alt="" loading="lazy" />;
}
