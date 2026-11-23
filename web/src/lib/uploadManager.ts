// Keeps uploads running in the background while the person keeps filling the form, shows their
// progress, and picks interrupted ones up again after a refresh.
import { useSyncExternalStore } from "react";
import { api } from "../api/client";
import { allJobs, deleteJob, putJob, type PendingUpload } from "./store";
import { hashBlob, initiate, shrinkImage, transfer } from "./uploader";

export type UploadState = { assetId: string; bookingId: string; fieldKey: string; name: string; status: "queued" | "uploading" | "done" | "failed"; progress: number; preview?: string; error?: string };

const states = new Map<string, UploadState>();
const listeners = new Set<() => void>();
let version = 0;
let running = 0;
const queue: PendingUpload[] = [];
const emit = () => { version++; listeners.forEach((l) => l()); };
const set = (id: string, p: Partial<UploadState>) => { const cur = states.get(id); if (cur) { states.set(id, { ...cur, ...p }); emit(); } };

async function pump(): Promise<void> {
  while (running < 2 && queue.length > 0) {
    const job = queue.shift()!;
    running++;
    set(job.assetId, { status: "uploading" });
    transfer(job, (f) => set(job.assetId, { progress: f }))
      .then(async () => { set(job.assetId, { status: "done", progress: 1 }); await deleteJob(job.clientUuid).catch(() => {}); })
      .catch((e: Error) => { set(job.assetId, { status: "failed", error: e.message }); queue.push(job); })
      .finally(() => { running--; });
  }
}

/** Tracks a file that is already registered with the server. */
function track(job: PendingUpload): void {
  if (!states.has(job.assetId))
    states.set(job.assetId, { assetId: job.assetId, bookingId: job.bookingId, fieldKey: job.fieldKey, name: job.name, status: "queued", progress: 0, preview: job.kind === "photo" || job.kind === "signature" ? URL.createObjectURL(job.blob) : undefined });
  queue.push(job);
  emit();
  void pump();
}

/** Called when someone picks or takes a file: shrink, checksum, register, and upload in the
 *  background. Resolves with the server's media id so the answer can point at it at once. */
export async function addFile(args: { bookingId: string; fieldKey: string; kind: PendingUpload["kind"]; file: Blob; name: string; source: "camera" | "gallery" }): Promise<string> {
  const blob = args.kind === "photo" ? await shrinkImage(args.file) : args.file;
  const spec = { clientUuid: crypto.randomUUID(), bookingId: args.bookingId, fieldKey: args.fieldKey, kind: args.kind, contentType: blob.type || "application/octet-stream", sha256: await hashBlob(blob), source: args.source, blob };
  const init = await initiate(spec);
  const job: PendingUpload = { ...spec, kind: args.kind, name: args.name, assetId: init.id };
  await putJob(job).catch(() => {});          // kept until it is sent, even across a refresh
  track(job);
  return init.id;
}

/** Takes back a file the person removed: stop sending it, forget it, and tell the server so it no
 *  longer counts towards the field's limit (a retake would otherwise be refused). */
export async function discardFile(assetId: string): Promise<void> {
  const i = queue.findIndex((j) => j.assetId === assetId);
  const job = i >= 0 ? queue.splice(i, 1)[0] : undefined;
  const st = states.get(assetId);
  states.delete(assetId);
  emit();
  if (job) await deleteJob(job.clientUuid).catch(() => {});
  else if (st) await allJobs().then((all) => all.filter((j) => j.assetId === assetId).forEach((j) => void deleteJob(j.clientUuid))).catch(() => {});
  await api(`media/${assetId}`, { method: "DELETE" }).catch(() => {});      // best effort: the server cleans up stragglers
}

/** After a refresh: carry on with everything for this booking that never finished. */
export async function resumeUploads(bookingId: string): Promise<number> {
  const jobs = (await allJobs().catch(() => [] as PendingUpload[])).filter((j) => j.bookingId === bookingId && !states.has(j.assetId));
  jobs.forEach(track);
  return jobs.length;
}

export function retryFailed(): void {
  states.forEach((s, id) => { if (s.status === "failed") set(id, { status: "queued", error: undefined }); });
  void pump();
}

export function useUploads(bookingId?: string): UploadState[] {
  useSyncExternalStore((l) => { listeners.add(l); return () => { listeners.delete(l); }; }, () => version);
  return [...states.values()].filter((s) => !bookingId || s.bookingId === bookingId);
}
export const uploadFor = (assetId: string) => states.get(assetId);
export function summary(list: UploadState[]): { done: number; total: number } {
  return { done: list.filter((s) => s.status === "done").length, total: list.length };
}
/** For tests. */
export function _reset(): void { states.clear(); queue.length = 0; running = 0; emit(); }
