import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";

export type MediaLinks = { url: string; preview_url: string | null };
export const mediaUrl = (id: string) => api<MediaLinks>(`media/${id}/url`).catch(() => null);

/** The signed links of one uploaded file (shared cache: a gallery and a sheet ask once). */
export function useMediaUrl(id: string) {
  return useQuery({ queryKey: ["media-url", id], staleTime: 600_000, queryFn: () => mediaUrl(id) }).data;
}

/** A small picture (or the first frame of a video) of one uploaded file. */
export function Thumb({ id, video, size }: { id: string; video?: boolean; size?: number }) {
  const links = useMediaUrl(id);
  const style = size ? { width: size, height: (size * 3) / 4 } : undefined;
  if (!links) return <span className="thumb empty" style={style} aria-label="Not ready yet" />;
  return video
    ? <video className="thumb" style={style} src={links.url} preload="metadata" muted />
    : <img className="thumb" style={style} src={links.preview_url ?? links.url} alt="" loading="lazy" />;
}
