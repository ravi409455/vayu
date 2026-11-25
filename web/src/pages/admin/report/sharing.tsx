/** Sharing (docs/plan-reports.md §9): the picture library, shared themes and shared parts. */
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, uploadFile } from "../../../api/client";
import { useRefresh } from "../../../api/hooks";
import { Field, useToast } from "../../../ui/kit";
import { slugKey } from "../../../lib/fieldTypes";
import { withoutIds, type Definition, type Part } from "./model";
import { keys } from "../../../api/keys";

export type Picture = { id: string; name: string; size: number; url: string };
export type Usage = { template: number; form: string; draft?: number; published?: number };
export type SharedItem = {
  id: number;
  kind: "theme" | "snippet";
  key: string;
  name: string;
  revision: number;
  used_by: Usage[];
  content?: unknown;
};

export function usePictures() {
  return useQuery({ queryKey: keys.pdfPictures(), queryFn: ({ signal }) => api<Picture[]>("pdf-pictures", { signal }) });
}
export function useShared() {
  return useQuery({ queryKey: keys.pdfShared(), queryFn: ({ signal }) => api<SharedItem[]>("pdf-shared", { signal }) });
}
/** One version of a shared item's content (what a template using it shows). */
export function useSharedContent<T>(item: SharedItem | undefined, revision: number | undefined) {
  return useQuery({
    queryKey: keys.pdfShared(item?.id, revision),
    enabled: !!item && !!revision,
    queryFn: async () => (await api<SharedItem>(`pdf-shared/${item!.id}`, { query: { revision: String(revision) } })).content as T,
  });
}

/** "a-z, 0-9, _" key from a name: "Car C.I.D. theme" -> car_c_i_d_theme. */
export const keyOf = (name: string): string => slugKey(name, "x_", 60);

/** Choose a picture from the library, or upload a new one into it. */
export function PicturePicker({ label, onPick }: { label: string; onPick: (id: string) => void }) {
  const { fail } = useToast();
  const refresh = useRefresh();
  const pictures = usePictures();
  const upload = async (file: File) => {
    try {
      const r = await uploadFile<Picture>("pdf-pictures", file, "POST", { name: file.name.replace(/\.[^.]+$/, "") });
      await refresh(keys.pdfPictures());
      onPick(r.id);
    } catch (e) {
      fail(e);
    }
  };
  return (
    <span className="bar" style={{ margin: 0 }}>
      <select aria-label={label} value="" onChange={(e) => e.target.value && onPick(e.target.value)} style={{ width: "auto" }}>
        <option value="">{label}…</option>
        {(pictures.data ?? []).map((p) => (
          <option key={p.id} value={p.id}>
            {p.name}
          </option>
        ))}
      </select>
      <label className="link small" style={{ cursor: "pointer" }}>
        Upload new
        <input
          type="file"
          accept="image/png,image/jpeg"
          hidden
          aria-label={`${label}: upload`}
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) void upload(f);
          }}
        />
      </label>
    </span>
  );
}

/** Logos, watermarks and backgrounds: uploaded once, used by any template or theme. */
export function PictureLibrary({ readOnly }: { readOnly: boolean }) {
  const { fail } = useToast();
  const refresh = useRefresh();
  const pictures = usePictures();
  const [name, setName] = useState("");
  const act = async (fn: () => Promise<unknown>) => {
    try {
      await fn();
      await refresh(keys.pdfPictures());
    } catch (e) {
      fail(e);
    }
  };
  return (
    <>
      <p className="muted small">
        Pictures here can be used in any template's header, footer or watermark. The same picture uploaded twice is kept once.
      </p>
      <div className="rd-pics">
        {(pictures.data ?? []).map((p) => (
          <figure key={p.id} className="rd-pic">
            <img src={p.url} alt={p.name} />
            <input
              aria-label={`Name of ${p.name}`}
              defaultValue={p.name}
              disabled={readOnly}
              onBlur={(e) => {
                const v = e.target.value.trim();
                if (v && v !== p.name) void act(() => api(`pdf-pictures/${p.id}`, { method: "PATCH", body: { name: v } }));
              }}
            />
            {!readOnly && (
              <button
                type="button"
                className="link danger-link small"
                onClick={() => void act(() => api(`pdf-pictures/${p.id}`, { method: "DELETE" }))}
              >
                Remove
              </button>
            )}
          </figure>
        ))}
        {(pictures.data ?? []).length === 0 && <p className="muted small">No pictures yet.</p>}
      </div>
      {!readOnly && (
        <div className="bar">
          <input
            aria-label="New picture name"
            placeholder="Name, e.g. Logo (white)"
            value={name}
            onChange={(e) => setName(e.target.value)}
            style={{ maxWidth: 240 }}
          />
          <label className={`btn sm${name.trim() ? "" : " disabled"}`}>
            Upload a picture
            <input
              type="file"
              accept="image/png,image/jpeg"
              hidden
              disabled={!name.trim()}
              aria-label="Upload a picture"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f)
                  void act(async () => {
                    await uploadFile("pdf-pictures", f, "POST", { name: name.trim() });
                    setName("");
                  });
              }}
            />
          </label>
        </div>
      )}
    </>
  );
}

/** Save something as a shared item: a new one, or a new version of one (which every template
 *  using it then shows). */
export function ShareForm({
  kind,
  items,
  content,
  onSaved,
  label,
}: {
  kind: "theme" | "snippet";
  items: SharedItem[];
  content: unknown;
  label: string;
  onSaved: (item: SharedItem & { updated: string[] }) => void;
}) {
  const { fail } = useToast();
  const refresh = useRefresh();
  const [target, setTarget] = useState("");
  const [name, setName] = useState("");
  const existing = items.find((i) => String(i.id) === target);
  const save = async () => {
    try {
      const r = await api<SharedItem & { updated: string[] }>("pdf-shared", {
        body: { kind, key: existing?.key ?? keyOf(name), name: existing?.name ?? name.trim(), content },
      });
      await refresh(keys.pdfShared());
      setName("");
      setTarget("");
      onSaved(r);
    } catch (e) {
      fail(e);
    }
  };
  return (
    <div className="rd-share">
      <Field label={label}>
        <select aria-label={`${label}: where`} value={target} onChange={(e) => setTarget(e.target.value)}>
          <option value="">As a new {kind === "theme" ? "theme" : "shared part"}</option>
          {items.map((i) => (
            <option key={i.id} value={i.id}>
              Replace “{i.name}” (used by {i.used_by.map((u) => u.form).join(", ") || "nothing yet"})
            </option>
          ))}
        </select>
      </Field>
      {!existing && (
        <Field label="Name">
          <input
            aria-label={`${label}: name`}
            placeholder={kind === "theme" ? "e.g. Car C.I.D." : "e.g. Disclaimer"}
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </Field>
      )}
      {existing && (
        <p className="muted small">
          Saves a new version of “{existing.name}”. Every template using it moves to the new version: drafts change, live templates are
          republished.
        </p>
      )}
      <button type="button" className="sm" disabled={!existing && !name.trim()} onClick={() => void save()}>
        {existing ? "Save new version" : "Share"}
      </button>
    </div>
  );
}

/** What a shared part holds, saved from one part of a template. */
export function snippetContent(part: Part): { parts: Part[] } {
  return { parts: [withoutIds(part)] };
}

export type ThemeContent = Pick<Definition, "theme" | "bands" | "watermark">;
