import { Camera, Image as ImageIcon, ImageOff, MapPin, Paperclip, Video as VideoIcon } from "lucide-react";
import { maxFiles } from "../lib/fieldTypes";
import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, ApiError } from "../api/client";
import { fetchAll } from "../api/hooks";
import { ist } from "../lib/format";
import { LINK_REFRESH_MS } from "./MediaThumb";
import { useInspectionTypes } from "../api/labels";
import type { FormField, FormPage, FormVersion, MasterListItem, Option, User } from "../api/types";
import { addFile, discardFile, isLocalId, uploadFor, useUploads } from "../lib/uploadManager";
import { evaluateTree, type Answers, type Ctx, type Kind } from "../lib/formSpec";
import { CameraCapture } from "./CameraCapture";
import { Field } from "./kit";

export type RenderProps = {
  kind: Kind;
  tree: Pick<FormVersion, "pages" | "checks">;
  values: Answers;
  ctx?: Ctx;
  onChange: (key: string, value: unknown) => void;
  errors?: Record<string, string>;
  readOnly?: boolean;
  readOnlyKeys?: string[];            // fields changed only through their own action (expert, type)
  role?: string;
  bookingId?: string;                 // needed for photo / video / file fields
  preview?: boolean;                  // the builder's preview: nothing is uploaded or located
  pages?: FormPage[];                 // render only these pages (the wizard shows one at a time)
  mediaUrl?: (id: string) => Promise<{ url: string; preview_url: string | null; removed?: boolean } | null>;
  onMediaRemove?: (field: FormField, id: string) => void;
  mediaEditor?: (field: FormField, ids: string[]) => React.ReactNode;   // Ops: their own Replace / Add
};

/** Draws a form tree: only what is visible, with the right input for each type, and the
 *  access level the server assigned (view = read-only). Ratings and Key Checks never show to experts. */
export function FormRenderer(p: RenderProps) {
  const result = evaluateTree(p.kind, p.tree, p.values, p.ctx);
  const pages = p.pages ?? p.tree.pages;
  // one page / one section: their names ("Page 1", "Section 1") say nothing, so they are not shown
  const onePage = p.tree.pages.length === 1, oneSection = onePage && p.tree.pages[0]!.sections.length === 1;
  return (
    <div>
      {pages.map((page) => (
        <div key={page.id}>
          {p.pages === undefined && !onePage && <h2>{page.title}</h2>}
          {page.sections.map((s) => {
            const fields = s.fields.filter((f) => result.visible[f.key] && !(p.role === "expert" && (f.type === "derived" || f.type === "rating")));
            if (fields.length === 0) return null;
            return (
              <section className="card" key={s.id} aria-label={s.title}>
                {!oneSection && <h3 style={{ marginTop: 0 }}>{s.title}</h3>}
                {fields.map((f) => (
                  <FieldInput key={f.id} f={f} value={p.values[f.key]} derived={result.derived[f.key]} required={!!result.required[f.key]}
                    error={p.errors?.[f.key]} readOnly={p.readOnly || p.readOnlyKeys?.includes(f.key) || f.level === "view" || f.type === "derived" || f.type === "rating"}
                    onChange={(v) => p.onChange(f.key, v)} p={p} />
                ))}
              </section>
            );
          })}
        </div>
      ))}
    </div>
  );
}

function FieldInput({ f, value, derived, required, error, readOnly, onChange, p }: {
  f: FormField; value: unknown; derived: unknown; required: boolean; error?: string; readOnly: boolean; onChange: (v: unknown) => void; p: RenderProps;
}) {
  const label = `${f.label || f.key}${required ? " *" : ""}`;
  const err = error === "required" ? "This is needed." : error;
  const uid = useId();
  const ids = { help: `${uid}-help`, error: `${uid}-err` };
  // the control says it is required, whether it is wrong, and which text explains it (F-179)
  const described = [f.helper_text && ids.help, err && ids.error].filter(Boolean).join(" ") || undefined;
  const common = { disabled: readOnly, "aria-label": f.label || f.key, "aria-required": required || undefined, "aria-invalid": err ? true : undefined, "aria-describedby": described };
  const str = (value ?? "") as string | number;
  let input: ReactNode;
  switch (f.type) {
    case "long_text": input = <textarea {...common} value={String(str)} onChange={(e) => onChange(e.target.value)} />; break;
    case "number": case "currency":
      input = <input {...common} type="number" inputMode="decimal" value={String(str)} placeholder={f.type === "currency" ? "₹" : String(f.config.unit ?? "")}
        onChange={(e) => onChange(e.target.value === "" ? null : Number(e.target.value))} />; break;
    case "phone": input = <input {...common} type="tel" value={String(str)} onChange={(e) => onChange(e.target.value)} />; break;
    case "date": case "time": case "datetime":
      input = f.config.auto === true
        ? <AutoStamp type={f.type} value={value as string | undefined} label={f.label || f.key} disabled={readOnly} preview={p.preview} onChange={onChange} />
        : f.type === "date" ? <input {...common} type="date" value={String(str)} onChange={(e) => onChange(e.target.value)} />
        : f.type === "time" ? <input {...common} type="time" value={String(str)} onChange={(e) => onChange(e.target.value)} />
        : <input {...common} type="datetime-local" value={String(str).slice(0, 16)} onChange={(e) => onChange(e.target.value)} />;
      break;
    case "image": {
      if (p.role !== "expert" && !p.preview) return null;                 // shown to the expert, not in Ops' views
      const asset = typeof f.config.asset === "string" ? f.config.asset : "";
      return <div className="field"><span className="label-row">{f.label}</span>{asset ? <img className="static-image" src={`/api/v1/form-assets/${asset}`} alt={f.label || "Picture"} /> : <p className="muted">No picture yet.</p>}{f.helper_text && <span className="help">{f.helper_text}</span>}</div>;
    }
    case "yes_no":
      input = <Choices name={f.key} disabled={readOnly} label={f.label} value={value === true ? "yes" : value === false ? "no" : ""} plain options={[{ key: "yes", label: "Yes" }, { key: "no", label: "No" }]} onChange={(k) => onChange(k === "yes")} />; break;
    case "single_choice": {
      const opts = (f.config.options as Option[]) ?? [];
      input = f.config.display === "dropdown" || (f.config.display !== "buttons" && opts.length > 5)
        ? <select {...common} value={String(str)} onChange={(e) => onChange(e.target.value || null)}><option value="">Choose…</option>{opts.map((o) => <option key={o.key} value={o.key}>{o.label}</option>)}</select>
        : <Choices name={f.key} disabled={readOnly} label={f.label} value={String(str)} options={opts} onChange={(k) => onChange(value === k ? null : k)} />;
      break;
    }
    case "multi_choice": {
      const opts = (f.config.options as Option[]) ?? [];
      const chosen = Array.isArray(value) ? (value as string[]) : [];
      input = <div role="group" aria-label={f.label}>{opts.map((o) => (
        <label className="check" key={o.key}><input type="checkbox" disabled={readOnly} checked={chosen.includes(o.key)}
          onChange={(e) => onChange(e.target.checked ? [...chosen, o.key] : chosen.filter((x) => x !== o.key))} /> {o.label}</label>))}</div>;
      break;
    }
    case "form_choice": input = <TypeSelect value={String(str)} disabled={readOnly} label={f.label} onChange={(v) => onChange(v || null)} />; break;
    case "master_list": input = <ListSelect list={String(f.config.list ?? "")} value={String(str)} disabled={readOnly} label={f.label} onChange={(v) => onChange(v || null)} />; break;
    case "user_picker": input = <UserSelect role={String(f.config.role ?? "expert")} value={value as number | null} disabled={readOnly} label={f.label} onChange={onChange} />; break;
    case "gps": input = <Gps value={value as { lat: number; lng: number } | undefined} disabled={readOnly} onChange={onChange} preview={p.preview} auto={f.config.auto !== false} />; break;
    case "photo": case "video": case "file": case "signature":
      input = <MediaField f={f} value={value} readOnly={readOnly} onChange={onChange} p={p} />; break;
    case "derived":
      input = <p><strong>{derived === true ? String(f.config.true_label ?? "Yes") : String(f.config.false_label ?? "No")}</strong></p>; break;
    case "rating": input = <p className="muted">Calculated from the defects found.</p>; break;
    default: input = <input {...common} value={String(str)} onChange={(e) => onChange(e.target.value)} />;
  }
  return <Field bare label={label} help={f.helper_text || undefined} error={err} ids={ids}>{input}</Field>;
}

/** Picked answers read at a glance: green when fine, red only for a defect; Yes / No stays neutral. */
function Choices({ name, options, value, onChange, disabled, label, plain }: { name: string; options: { key: string; label: string; is_defect?: boolean }[]; value: string; onChange: (k: string) => void; disabled: boolean; label: string; plain?: boolean }) {
  return (
    <div role="radiogroup" aria-label={label} style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
      {options.map((o) => (
        <button type="button" key={o.key} role="radio" aria-checked={value === o.key} disabled={disabled} name={name}
          className={`choice${plain ? " plain" : o.is_defect ? " defect" : ""}`} onClick={() => onChange(o.key)}>{o.label}</button>
      ))}
    </div>
  );
}

function ListSelect({ list, value, onChange, disabled, label }: { list: string; value: string; onChange: (v: string) => void; disabled: boolean; label: string }) {
  const q = useQuery({ queryKey: ["list-items", list], enabled: !!list, staleTime: 300_000, queryFn: ({ signal }) => fetchAll<MasterListItem>(`master-lists/${list}/items`, undefined, signal) });
  const items = (q.data ?? []).filter((i) => !i.archived || i.key === value);
  return <select aria-label={label} disabled={disabled} value={value} onChange={(e) => onChange(e.target.value)}><option value="">Choose…</option>{items.map((i) => <option key={i.key} value={i.key}>{i.label}</option>)}</select>;
}

function TypeSelect({ value, onChange, disabled, label }: { value: string; onChange: (v: string) => void; disabled: boolean; label: string }) {
  const types = useInspectionTypes().filter((t) => t.available || t.key === value);
  return <select aria-label={label} disabled={disabled} value={value} onChange={(e) => onChange(e.target.value)}><option value="">Choose…</option>{types.map((t) => <option key={t.key} value={t.key}>{t.label}</option>)}</select>;
}

function UserSelect({ role, value, onChange, disabled, label }: { role: string; value: number | null | undefined; onChange: (v: unknown) => void; disabled: boolean; label: string }) {
  const q = useQuery({ queryKey: ["users-by-role", role], retry: false, staleTime: 300_000, queryFn: ({ signal }) => fetchAll<User>("users", { role }, signal) });
  if (q.isError) return <input aria-label={label} disabled value={value ?? ""} readOnly />;
  return <select aria-label={label} disabled={disabled} value={value ?? ""} onChange={(e) => onChange(e.target.value ? Number(e.target.value) : null)}>
    <option value="">Choose…</option>{(q.data ?? []).filter((u) => u.is_active).map((u) => <option key={u.id} value={u.id}>{u.name || u.username}</option>)}</select>;
}

/** Browser location, taken by itself as soon as the field appears. If it is refused or not
 *  available the field just says so (and offers another try): it never blocks the job. */
const pad = (n: number) => String(n).padStart(2, "0");
/** "Now" in the shapes the server stores, in India time: 2026-11-23, 15:30, 2026-11-23T15:30:00+05:30. */
export function nowAs(type: string, d = new Date()): string {
  const at = ist(d);
  if (type === "date") return at.day;
  if (type === "time") return at.hhmm;
  return `${at.day}T${at.hhmm}:${pad(at.seconds)}+05:30`;
}

/** A date or time the Admin set to "automatic": stamped when the page opens, never typed. */
function AutoStamp({ type, value, label, disabled, preview, onChange }: { type: string; value?: string; label: string; disabled: boolean; preview?: boolean; onChange: (v: unknown) => void }) {
  const done = useRef(false);
  useEffect(() => {
    if (done.current || value || disabled || preview) return;
    done.current = true;
    onChange(nowAs(type));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const shown = value ? (type === "datetime" ? new Date(value).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" }) : value) : preview ? "Stamped when the expert opens this page" : "…";
  return <p className="auto-stamp" data-testid={`auto-${label}`}>{shown} <span className="muted small">(automatic)</span></p>;
}

function Gps({ value, onChange, disabled, preview, auto = true }: { value?: { lat: number; lng: number; accuracy?: number }; onChange: (v: unknown) => void; disabled: boolean; preview?: boolean; auto?: boolean }) {
  const [state, setState] = useState<"idle" | "busy" | "unavailable">("idle");
  const asked = useRef(false);
  function capture() {
    if (!("geolocation" in navigator)) return setState("unavailable");
    setState("busy");
    navigator.geolocation.getCurrentPosition(
      (pos) => { setState("idle"); onChange({ lat: +pos.coords.latitude.toFixed(6), lng: +pos.coords.longitude.toFixed(6), accuracy: Math.round(pos.coords.accuracy) }); },
      () => setState("unavailable"), { enableHighAccuracy: true, timeout: 10_000 });
  }
  useEffect(() => {
    if (asked.current || value || disabled || preview || !auto) return;
    asked.current = true;
    capture();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <div aria-live="polite">
      {value ? <p className="ok" data-testid="gps-value"><MapPin size={14} aria-hidden /> {value.lat}, {value.lng}{value.accuracy !== undefined && <span className="muted small"> (±{value.accuracy} m)</span>}</p>
        : state === "busy" ? <p className="muted" role="status">Finding your location…</p>
        : state === "unavailable" ? <p className="muted" role="status">GPS unavailable</p>
        : preview ? <p className="muted small">{auto ? "Taken automatically when the expert opens this page." : "The expert taps a button to capture it."}</p> : null}
      {!disabled && !preview && !auto && !value && state === "idle" && <button type="button" onClick={capture}>Capture my location</button>}
      {!disabled && !preview && (value || state === "unavailable") && state !== "busy" && <button type="button" className="link" onClick={capture}>{value ? "Update location" : "Try again"}</button>}
    </div>
  );
}

function MediaField({ f, value, readOnly, onChange, p }: { f: FormField; value: unknown; readOnly: boolean; onChange: (v: unknown) => void; p: RenderProps }) {
  const single = f.type === "signature";
  const ids = (single ? (value ? [String(value)] : []) : Array.isArray(value) ? (value as string[]) : []);
  const max = maxFiles(f);
  const mode = f.type === "file" ? "upload" : String(f.config.capture ?? "both");     // both | camera | upload
  useUploads(p.bookingId);                       // re-render as the files' uploads move on
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
        const id = p.preview ? `preview-${Date.now()}-${next.length}` : await addFile({ bookingId: p.bookingId!, fieldKey: f.key, kind: f.type as "photo", file, name: file.name, source, keepOffline: true });
        next = single ? [id] : [...next, id];
        onChange(single ? id : next);
      } catch (e) { setErr(e instanceof ApiError && e.status < 500 && e.code !== "HTTP_" + e.status ? e.message : "That file could not be added. Check its type and size, then try again."); }
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
              {u?.preview ? <img src={u.preview} alt="" /> : id.startsWith("preview-") || isLocalId(id) ? <div className="fake-photo"><ImageIcon size={22} aria-hidden /></div> : <RemoteThumb id={id} kind={f.type} mediaUrl={p.mediaUrl} />}
              {u && u.status !== "done" && <div className="progress" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(u.progress * 100)} aria-label={`Upload ${u.status}`}><div style={{ width: `${Math.round(u.progress * 100)}%` }} /></div>}
              {u?.status === "failed" && <span className="error small">{u.permanent ? `Not accepted: ${u.error}. Remove it and try another.` : isLocalId(u.assetId) ? "No connection: kept on this device, sent when you are back online" : "Not sent yet: will retry"}</span>}
              {u?.deviceOnly && u.status !== "done" && <span className="error small">This browser could not store it: kept only while this tab is open</span>}
              {!readOnly && <button type="button" className="link" aria-label="Remove" onClick={() => { const rest = ids.filter((x) => x !== id); onChange(single ? null : rest); p.onMediaRemove?.(f, id); if (!p.preview && p.bookingId && !id.startsWith("preview-")) void discardFile(id); }}>Remove</button>}
            </div>
          );
        })}
      </div>
      {!readOnly && room && (
        <div className="media-actions">
          {mode !== "upload" && (
            <button type="button" className="btn-icon primary" onClick={() => setCamera(true)} aria-label={`Open camera: ${noun}`}>
              {kind === "video" ? <VideoIcon size={18} aria-hidden /> : <Camera size={18} aria-hidden />}<span>{kind === "video" ? "Record" : "Camera"}</span></button>)}
          {mode !== "camera" && (
            <button type="button" className="btn-icon" onClick={() => input.current?.click()} aria-label={`Attach a ${noun}`}><Paperclip size={18} aria-hidden /><span>Attach</span></button>)}
          <span className="muted small">{ids.length}/{max}</span>
          {mode !== "camera" && <input ref={input} type="file" hidden multiple={!single} accept={accept} data-testid={`file-${f.key}`} onChange={(e) => { void pick(e.target.files, "gallery"); e.target.value = ""; }} />}
          {mode !== "upload" && <input ref={cam} type="file" hidden accept={accept} capture="environment" data-testid={`camera-${f.key}`} onChange={(e) => { void pick(e.target.files, "camera"); e.target.value = ""; }} />}
        </div>
      )}
      {camera && <CameraCapture kind={kind} label={`${f.label || f.key}: ${kind === "video" ? "record" : "take a photo"}`} onClose={() => setCamera(false)}
        onFallback={() => { setCamera(false); cam.current?.click(); }} onDone={(file) => { setCamera(false); void pick([file], "camera"); }} />}
      {err && <p className="error" role="alert">{err}</p>}
    </div>
  );
}

function RemoteThumb({ id, kind, mediaUrl }: { id: string; kind: string; mediaUrl?: RenderProps["mediaUrl"] }) {
  const q = useQuery({ queryKey: ["media-url", id], enabled: !!mediaUrl, staleTime: 600_000, refetchInterval: LINK_REFRESH_MS, queryFn: () => mediaUrl!(id) });
  const u = q.data?.preview_url ?? q.data?.url;
  if (q.data?.removed) return <div className="fake-photo" title="Deleted after the storage time set in Settings" aria-label="Deleted after the storage time set in Settings"><ImageOff size={22} aria-hidden /></div>;
  if (!u) return <div style={{ aspectRatio: "4/3", background: "var(--hover)", borderRadius: 8 }} role="img" aria-label="Preview not ready" />;
  return kind === "video" ? <video src={q.data!.url} controls preload="metadata" /> : <img src={u} alt="" />;
}
