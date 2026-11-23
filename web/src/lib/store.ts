// Things that must survive a page refresh. Drafts are small (localStorage); pictures and videos
// waiting to upload are blobs (IndexedDB), so a refresh or a closed tab loses nothing.
const hasLS = () => { try { return typeof localStorage !== "undefined"; } catch { return false; } };

export function loadJSON<T>(key: string, fallback: T): T {
  if (!hasLS()) return fallback;
  try { const raw = localStorage.getItem(key); return raw ? (JSON.parse(raw) as T) : fallback; } catch { return fallback; }
}
export function saveJSON(key: string, value: unknown): void {
  if (hasLS()) try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* storage full or blocked: the draft just is not kept */ }
}
export function removeKey(key: string): void {
  if (hasLS()) try { localStorage.removeItem(key); } catch { /* nothing to do */ }
}

export type PendingUpload = {
  clientUuid: string; bookingId: string; fieldKey: string; kind: "photo" | "video" | "file" | "signature";
  contentType: string; name: string; sha256: string; assetId: string; source: "camera" | "gallery"; blob: Blob;
};

const DB = "vayu-uploads";
function open(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const r = indexedDB.open(DB, 1);
    r.onupgradeneeded = () => r.result.createObjectStore("jobs", { keyPath: "clientUuid" });
    r.onsuccess = () => resolve(r.result);
    r.onerror = () => reject(r.error);
  });
}
async function tx<T>(mode: IDBTransactionMode, fn: (s: IDBObjectStore) => IDBRequest<T>): Promise<T> {
  const db = await open();
  return new Promise((resolve, reject) => {
    const req = fn(db.transaction("jobs", mode).objectStore("jobs"));
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}
export const putJob = (j: PendingUpload) => tx("readwrite", (s) => s.put(j));
export const deleteJob = (id: string) => tx("readwrite", (s) => s.delete(id));
export const allJobs = () => tx<PendingUpload[]>("readonly", (s) => s.getAll());
