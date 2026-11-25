import { FileText, ImageOff } from "lucide-react";
import { isPdf, REMOVED_NOTE, useMediaUrl } from "../../../ui/MediaThumb";

export function PreviewMedia({ id, video }: { id: string; video: boolean }) {
  const links = useMediaUrl(id);
  if (!links) return <div className="preview-media empty" role="img" aria-label="Not ready yet" />;
  if (links.removed)
    return (
      <div className="preview-media doc" role="note">
        <ImageOff size={40} aria-hidden />
        <span>{REMOVED_NOTE}.</span>
      </div>
    );
  if (isPdf(links))
    return (
      <a className="preview-media doc" href={links.url} target="_blank" rel="noreferrer">
        <FileText size={40} aria-hidden />
        <span>Open the PDF</span>
      </a>
    );
  return video ? (
    <video className="preview-media" src={links.url} controls preload="metadata" />
  ) : (
    <a href={links.url} target="_blank" rel="noreferrer">
      <img className="preview-media" src={links.preview_url ?? links.url} alt="" />
    </a>
  );
}
