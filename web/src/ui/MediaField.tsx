/** A photo / video / file field: capture or pick, queue the upload, show what is there. */
import { Camera, Image as ImageIcon, ImageOff, Paperclip, Video as VideoIcon } from "lucide-react";
import { maxFiles } from "../lib/fieldTypes";
import { useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ApiError } from "../api/client";
import { LINK_REFRESH_MS } from "./MediaThumb";
import type { FormField } from "../api/types";
import { addFile, discardFile, isLocalId, uploadFor, useUploads } from "../lib/uploadManager";
import { CameraCapture } from "./CameraCapture";
import { keys } from "../api/keys";
import type { RenderProps } from "./FormRenderer";

export function MediaField({
  f,
  value,
  readOnly,
  onChange,
  p,
}: {
  f: FormField;
  value: unknown;
  readOnly: boolean;
  onChange: (v: unknown) => void;
  p: RenderProps;
}) {
  const single = f.type === "signature";
  const ids = single ? (value ? [String(value)] : []) : Array.isArray(value) ? (value as string[]) : [];
  const max = maxFiles(f);
  const mode = f.type === "file" ? "upload" : String(f.config.capture ?? "both"); // both | camera | upload
  useUploads(p.bookingId); // re-render as the files' uploads move on
  const input = useRef<HTMLInputElement>(null);
  const cam = useRef<HTMLInputElement>(null);
  const [err, setErr] = useState("");
  const [camera, setCamera] = useState(false);
  const accept = f.type === "photo" || f.type === "signature" ? "image/*" : f.type === "video" ? "video/*" : "image/*,application/pdf";
  const kind = f.type === "video" ? "video" : "photo";
  if (p.mediaEditor) return <>{p.mediaEditor(f, ids)}</>;

  async function pick(files: FileList | File[] | null, source: "camera" | "gallery") {
    if (!files) return;
    setErr("");
    let next = [...ids];
    for (const file of Array.from(files).slice(0, Math.max(0, max - ids.length))) {
      try {
        const id = p.preview
          ? `preview-${Date.now()}-${next.length}`
          : await addFile({
              bookingId: p.bookingId!,
              fieldKey: f.key,
              kind: f.type as "photo",
              file,
              name: file.name,
              source,
              keepOffline: true,
            });
        next = single ? [id] : [...next, id];
        onChange(single ? id : next);
      } catch (e) {
        setErr(
          e instanceof ApiError && e.status < 500 && e.code !== "HTTP_" + e.status
            ? e.message
            : "That file could not be added. Check its type and size, then try again.",
        );
      }
    }
  }
  const room = ids.length < max;
  const noun = f.type === "video" ? "video" : f.type === "file" ? "file" : "photo";
  return (
    <div>
      <div className="photo-grid">
        {ids.map((id) => {
          const u = uploadFor(id);
          return (
            <div key={id} data-testid="media-item" style={{ position: "relative" }}>
              {u?.preview ? (
                <img src={u.preview} alt="" />
              ) : id.startsWith("preview-") || isLocalId(id) ? (
                <div className="fake-photo">
                  <ImageIcon size={22} aria-hidden />
                </div>
              ) : (
                <RemoteThumb id={id} kind={f.type} mediaUrl={p.mediaUrl} />
              )}
              {u && u.status !== "done" && (
                <div
                  className="progress"
                  role="progressbar"
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-valuenow={Math.round(u.progress * 100)}
                  aria-label={`Upload ${u.status}`}
                >
                  <div style={{ width: `${Math.round(u.progress * 100)}%` }} />
                </div>
              )}
              {u?.status === "failed" && (
                <span className="error small">
                  {u.permanent
                    ? `Not accepted: ${u.error}. Remove it and try another.`
                    : isLocalId(u.assetId)
                      ? "No connection: kept on this device, sent when you are back online"
                      : "Not sent yet: will retry"}
                </span>
              )}
              {u?.deviceOnly && u.status !== "done" && (
                <span className="error small">This browser could not store it: kept only while this tab is open</span>
              )}
              {!readOnly && (
                <button
                  type="button"
                  className="link"
                  aria-label="Remove"
                  onClick={() => {
                    const rest = ids.filter((x) => x !== id);
                    onChange(single ? null : rest);
                    p.onMediaRemove?.(f, id);
                    if (!p.preview && p.bookingId && !id.startsWith("preview-")) void discardFile(id);
                  }}
                >
                  Remove
                </button>
              )}
            </div>
          );
        })}
      </div>
      {!readOnly && room && (
        <div className="media-actions">
          {mode !== "upload" && (
            <button type="button" className="btn-icon primary" onClick={() => setCamera(true)} aria-label={`Open camera: ${noun}`}>
              {kind === "video" ? <VideoIcon size={18} aria-hidden /> : <Camera size={18} aria-hidden />}
              <span>{kind === "video" ? "Record" : "Camera"}</span>
            </button>
          )}
          {mode !== "camera" && (
            <button type="button" className="btn-icon" onClick={() => input.current?.click()} aria-label={`Attach a ${noun}`}>
              <Paperclip size={18} aria-hidden />
              <span>Attach</span>
            </button>
          )}
          <span className="muted small">
            {ids.length}/{max}
          </span>
          {mode !== "camera" && (
            <input
              ref={input}
              type="file"
              hidden
              multiple={!single}
              accept={accept}
              data-testid={`file-${f.key}`}
              onChange={(e) => {
                void pick(e.target.files, "gallery");
                e.target.value = "";
              }}
            />
          )}
          {mode !== "upload" && (
            <input
              ref={cam}
              type="file"
              hidden
              accept={accept}
              capture="environment"
              data-testid={`camera-${f.key}`}
              onChange={(e) => {
                void pick(e.target.files, "camera");
                e.target.value = "";
              }}
            />
          )}
        </div>
      )}
      {camera && (
        <CameraCapture
          kind={kind}
          label={`${f.label || f.key}: ${kind === "video" ? "record" : "take a photo"}`}
          onClose={() => setCamera(false)}
          onFallback={() => {
            setCamera(false);
            cam.current?.click();
          }}
          onDone={(file) => {
            setCamera(false);
            void pick([file], "camera");
          }}
        />
      )}
      {err && (
        <p className="error" role="alert">
          {err}
        </p>
      )}
    </div>
  );
}

function RemoteThumb({ id, kind, mediaUrl }: { id: string; kind: string; mediaUrl?: RenderProps["mediaUrl"] }) {
  const q = useQuery({
    queryKey: keys.mediaUrl(id),
    enabled: !!mediaUrl,
    staleTime: 600_000,
    refetchInterval: LINK_REFRESH_MS,
    queryFn: () => mediaUrl!(id),
  });
  const u = q.data?.preview_url ?? q.data?.url;
  if (q.data?.removed)
    return (
      <div
        className="fake-photo"
        title="Deleted after the storage time set in Settings"
        aria-label="Deleted after the storage time set in Settings"
      >
        <ImageOff size={22} aria-hidden />
      </div>
    );
  if (!u)
    return <div style={{ aspectRatio: "4/3", background: "var(--hover)", borderRadius: 8 }} role="img" aria-label="Preview not ready" />;
  return kind === "video" ? <video src={q.data!.url} controls preload="metadata" /> : <img src={u} alt="" />;
}
