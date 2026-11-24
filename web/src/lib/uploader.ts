// Direct-to-storage upload, as the API describes it: initiate -> PUT each part to its signed URL
// -> complete -> the server checks the SHA-256. Resumable: ask which parts are already there.
import { sha256 } from "@noble/hashes/sha256";
import { bytesToHex } from "@noble/hashes/utils";
import { api } from "../api/client";

export const MAX_EDGE = 2048;
const SLICE = 4 * 1024 * 1024;

/** SHA-256 of a Blob without loading all of it into memory (videos can be 300 MB). */
export async function hashBlob(blob: Blob): Promise<string> {
  const h = sha256.create();
  for (let at = 0; at < blob.size; at += SLICE) h.update(new Uint8Array(await blob.slice(at, at + SLICE).arrayBuffer()));
  return bytesToHex(h.digest());
}

/** Sizes the picture to at most 2048 px on its long edge as JPEG. Anything the browser cannot
 *  decode (or a picture that is already small) is sent as it is. */
export async function shrinkImage(file: Blob): Promise<Blob> {
  if (!file.type.startsWith("image/") || file.type === "image/png" && file.size < 300_000) return file;
  try {
    const bmp = await createImageBitmap(file);
    const scale = Math.min(1, MAX_EDGE / Math.max(bmp.width, bmp.height));
    if (scale === 1 && file.type === "image/jpeg") { bmp.close(); return file; }
    const c = document.createElement("canvas");
    c.width = Math.round(bmp.width * scale);
    c.height = Math.round(bmp.height * scale);
    c.getContext("2d")!.drawImage(bmp, 0, 0, c.width, c.height);
    bmp.close();
    return await new Promise<Blob>((res) => c.toBlob((b) => res(b ?? file), "image/jpeg", 0.85));
  } catch { return file; }
}

export type Part = { part_number: number; url?: string };
type Initiated = { id: string; status: string; part_size: number; parts?: Part[] };

function putPart(url: string, body: Blob, onBytes: (n: number) => void): Promise<string> {
  return new Promise((resolve, reject) => {
    const x = new XMLHttpRequest();
    x.open("PUT", url);
    x.upload.onprogress = (e) => onBytes(e.loaded);
    x.onload = () => {
      const etag = x.getResponseHeader("ETag");
      if (x.status >= 200 && x.status < 300 && etag) resolve(etag);
      else reject(new Error(`part upload failed (${x.status})`));
    };
    x.onerror = () => reject(new Error("network"));
    x.send(body);
  });
}

export type UploadSpec = {
  clientUuid: string; bookingId: string; fieldKey: string; kind: string; contentType: string;
  sha256: string; source: "camera" | "gallery"; blob: Blob;
  replaces?: string;                 // Ops: the file this one takes the place of
};

/** Registers the upload with the server (safe to repeat: same client UUID, same asset). */
export function initiate(s: UploadSpec): Promise<Initiated> {
  return api<Initiated>("media/initiate", { body: {
    booking: s.bookingId, client_uuid: s.clientUuid, field_key: s.fieldKey, kind: s.kind,
    content_type: s.contentType, size: s.blob.size, sha256: s.sha256, source: s.source,
    ...(s.replaces ? { replaces: s.replaces } : {}) } });
}

/** Sends what is missing and finishes. Returns when the server says "verified". */
export async function transfer(s: UploadSpec, onProgress: (fraction: number) => void): Promise<void> {
  let init = await initiate(s);
  if (init.status === "verified") { onProgress(1); return; }
  const size = s.blob.size;
  const have = new Map<number, string>();
  if (init.status === "pending") {
    const prog = await api<{ uploaded_parts: { part_number: number; etag: string }[] }>(`media/${init.id}`);
    prog.uploaded_parts.forEach((p) => have.set(p.part_number, p.etag));
  }
  const parts = init.parts ?? [];
  let done = 0;
  for (const p of parts) {
    const slice = s.blob.slice((p.part_number - 1) * init.part_size, Math.min(size, p.part_number * init.part_size));
    if (have.has(p.part_number) || !p.url) { done += slice.size; continue; }
    let etag = "";
    for (let attempt = 0; ; attempt++) {
      try { etag = await putPart(p.url, slice, (n) => onProgress((done + n) / size)); break; }
      catch (e) { if (attempt >= 3) throw e; await new Promise((r) => setTimeout(r, 500 * 2 ** attempt)); }
    }
    have.set(p.part_number, etag);
    done += slice.size;
    onProgress(done / size);
  }
  if (init.status === "pending") {
    init = await api<Initiated>(`media/${init.id}/complete`, { body: {
      parts: [...have].map(([part_number, etag]) => ({ part_number, etag })) } });
  }
  onProgress(1);
}
