// Keeps uploads running in the background while the person keeps filling the form, shows their
// progress, and picks interrupted ones up again after a refresh.
//
// A file is kept in IndexedDB from the moment it is picked until the server has checked its
// checksum ("verified"), so a refresh, a lost connection or a failed check never loses the only copy.
// Picked with no connection, it gets a stand-in id ("local-…") until the server gives it its own.
import { useSyncExternalStore } from "react";
import { api, ApiError } from "../api/client";
import { allJobs, deleteJob, putJob, type PendingUpload } from "./store";
import { report } from "./monitor";
import { abortTransfers, hashBlob, initiate, shrinkImage, transfer } from "./uploader";

export type UploadState = {
  assetId: string;                  // what the answer holds: the server's id, or "local-…" until it has one
  bookingId: string; fieldKey: string; name: string;
  status: "queued" | "uploading" | "done" | "failed"; progress: number; preview?: string; error?: string;
  permanent?: boolean;              // the server refused it: retrying will not help, remove or replace it
  deviceOnly?: boolean;             // the browser would not store it: lost if this tab closes
};

const LOCAL = "local-";
export const isLocalId = (id: unknown): id is string => typeof id === "string" && id.startsWith(LOCAL);

type Entry = { job: PendingUpload; state: UploadState; tries: number; timer?: ReturnType<typeof setTimeout> };
const entries = new Map<string, Entry>();          // by client UUID
const renamed = new Map<string, string>();          // "local-…" -> the server's id
const listeners = new Set<() => void>();
let version = 0;
let running = 0;
let gen = 0;                                        // bumped by reset(): work from before it is ignored
const queue: string[] = [];                         // client UUIDs waiting for a free slot
const MAX_RUNNING = 2;
export const RETRY_MS = 2000, RETRY_MAX_MS = 60_000;
const VERIFY_WAITS = [3000, 10_000, 30_000, 60_000, 120_000, 300_000];

let lastEmit = 0, emitTimer: ReturnType<typeof setTimeout> | undefined;
const emit = () => { version++; lastEmit = Date.now(); listeners.forEach((l) => l()); };
/** Progress ticks many times a second: tell the screens at most every 250 ms. */
const emitSoon = () => {
  if (emitTimer) return;
  emitTimer = setTimeout(() => { emitTimer = undefined; emit(); }, Math.max(0, 250 - (Date.now() - lastEmit)));
};
const set = (e: Entry, p: Partial<UploadState>, soon = false) => { e.state = { ...e.state, ...p }; soon ? emitSoon() : emit(); };

/** A refusal the server will repeat however often we ask (wrong type, too big, too many, not yours). */
function permanent(e: unknown): boolean {
  return e instanceof ApiError && [400, 403, 404, 409, 413, 415, 422].includes(e.status)
    && !["NOT_UPLOADING", "INCOMPLETE_UPLOAD", "CHECKSUM_MISMATCH"].includes(e.code);
}
const reason = (e: unknown) => (e instanceof ApiError ? e.message : "No connection");

function pump(): void {
  while (running < MAX_RUNNING && queue.length > 0) {
    const e = entries.get(queue.shift()!);
    if (e && e.state.status === "queued") void run(e);
  }
}

async function run(e: Entry): Promise<void> {
  const mine = gen;
  running++;
  set(e, { status: "uploading", error: undefined });
  try {
    const r = await transfer(e.job, (f) => { if (mine === gen) set(e, { progress: f }, true); });
    if (mine !== gen) return;
    if (!e.job.assetId) giveId(e, r.id);
    e.tries = 0;
    set(e, { status: "done", progress: 1 });
    if (r.status === "verified") forget(e);
    else watch(e, 0);
  } catch (err) {
    if (mine !== gen || !entries.has(e.job.clientUuid)) return;
    const stop = permanent(err);
    set(e, { status: "failed", error: reason(err), permanent: stop });
    // F-235: a refused file, or one still failing after a few tries, is reported (the reason only, no file data)
    if (stop || e.tries === 3) report(err, { where: "upload", kind: e.job.kind, code: err instanceof ApiError ? err.code : "network" });
    if (!stop) later(e);
  } finally {
    if (mine === gen) { running--; pump(); }
  }
}

/** Failed for a reason that may pass (connection, server busy): try again, waiting longer each time. */
function later(e: Entry): void {
  const wait = Math.min(RETRY_MAX_MS, RETRY_MS * 2 ** e.tries++);
  clearTimeout(e.timer);
  e.timer = setTimeout(() => requeue(e), wait);
}
function requeue(e: Entry): void {
  clearTimeout(e.timer);
  if (!entries.has(e.job.clientUuid) || e.state.status === "uploading" || e.state.status === "queued") return;
  set(e, { status: "queued", error: undefined, permanent: undefined });
  queue.push(e.job.clientUuid);
  pump();
}

/** The bytes are there; the server checks the checksum a little later. Keep the copy until it says
 *  "verified"; if the check failed, send it again (the server restarts the upload for the same file). */
function watch(e: Entry, n: number): void {
  const mine = gen;
  clearTimeout(e.timer);
  e.timer = setTimeout(async () => {
    const r = await api<{ status: string }>(`media/${e.job.assetId}`).catch(() => null);
    if (mine !== gen || !entries.has(e.job.clientUuid)) return;
    if (r?.status === "verified" || r?.status === "purged") forget(e);
    else if (r?.status === "failed") { set(e, { status: "failed", error: "The file arrived damaged. Sending it again." }); requeue(e); }
    else if (n + 1 < VERIFY_WAITS.length) watch(e, n + 1);       // still checking; a later visit picks it up again
  }, VERIFY_WAITS[n]);
}
function forget(e: Entry): void {
  clearTimeout(e.timer);
  void deleteJob(e.job.clientUuid).catch(() => {});
}

/** A file picked offline gets the server's id once it is registered; the answer swaps it in (see `realId`). */
function giveId(e: Entry, id: string): void {
  renamed.set(e.state.assetId, id);
  e.job = { ...e.job, assetId: id };
  set(e, { assetId: id });
  void putJob(e.job).catch(() => {});
}

function track(job: PendingUpload, deviceOnly = false): Entry {
  const e: Entry = { job, tries: 0, state: {
    assetId: job.assetId || LOCAL + job.clientUuid, bookingId: job.bookingId, fieldKey: job.fieldKey, name: job.name,
    status: "queued", progress: 0, deviceOnly: deviceOnly || undefined,
    preview: job.kind === "photo" || job.kind === "signature" ? URL.createObjectURL(job.blob) : undefined } };
  entries.set(job.clientUuid, e);
  queue.push(job.clientUuid);
  emit();
  pump();
  return e;
}

/** Called when someone picks or takes a file: shrink, checksum, keep it on this device, register it
 *  and upload it in the background. Resolves with the id the answer should hold at once: the
 *  server's, or (with `keepOffline`, when there is no connection) a stand-in that is swapped later. */
export async function addFile(args: { bookingId: string; fieldKey: string; kind: PendingUpload["kind"]; file: Blob; name: string; source: "camera" | "gallery"; replaces?: string; keepOffline?: boolean }): Promise<string> {
  const mine = gen;                           // signed out while this file was being prepared: keep nothing
  await Promise.all([...discarding]);          // a retake right after Remove must not meet the old file at the limit
  const blob = args.kind === "photo" ? await shrinkImage(args.file) : args.file;
  const spec = { clientUuid: crypto.randomUUID(), bookingId: args.bookingId, fieldKey: args.fieldKey, kind: args.kind, contentType: blob.type || "application/octet-stream", sha256: await hashBlob(blob), source: args.source, blob, ...(args.replaces ? { replaces: args.replaces } : {}) };
  let assetId = "";
  try { assetId = (await initiate(spec)).id; }
  catch (e) { if (e instanceof ApiError || !args.keepOffline) throw e; }     // a refusal is shown; no connection is not
  if (mine !== gen) throw new Error("Signed out.");
  const job: PendingUpload = { ...spec, kind: args.kind, name: args.name, assetId };
  const kept = await putJob(job).then(() => true, () => false);       // private window or a full disk: say so
  if (mine !== gen) { await deleteJob(job.clientUuid).catch(() => {}); throw new Error("Signed out."); }   // signed out while it was being stored
  return track(job, !kept).state.assetId;
}

/** Takes back a file the person removed: stop sending it, forget it, and tell the server so it no
 *  longer counts towards the field's limit (a retake would otherwise be refused). */
const discarding = new Set<Promise<void>>();       // removals the server has not confirmed yet

export function discardFile(assetId: string): Promise<void> {
  const p = doDiscard(assetId).finally(() => discarding.delete(p));
  discarding.add(p);
  return p;
}

async function doDiscard(assetId: string): Promise<void> {
  const e = find(assetId);
  const serverId = e ? e.job.assetId : renamed.get(assetId) ?? assetId;
  if (e) {
    clearTimeout(e.timer);
    entries.delete(e.job.clientUuid);
    if (e.state.preview) URL.revokeObjectURL(e.state.preview);
    emit();
    await deleteJob(e.job.clientUuid).catch(() => {});
  } else await allJobs().then((all) => all.filter((j) => j.assetId === serverId).forEach((j) => void deleteJob(j.clientUuid))).catch(() => {});
  if (serverId && !isLocalId(serverId))
    await api(`media/${serverId}`, { method: "DELETE" }).catch(() => {});      // best effort: the server cleans up stragglers
}

function find(id: string): Entry | undefined {
  const real = renamed.get(id) ?? id;
  for (const e of entries.values()) if (e.state.assetId === real || e.state.assetId === id) return e;
  return undefined;
}

/** After a refresh, or on the submitted lead's page: carry on with everything for this booking that
 *  has not been checked by the server yet. */
export async function resumeUploads(bookingId: string): Promise<number> {
  const jobs = (await allJobs().catch(() => [] as PendingUpload[])).filter((j) => j.bookingId === bookingId && !entries.has(j.clientUuid));
  jobs.forEach((j) => track(j));
  return jobs.length;
}

/** "Retry uploads", and the connection coming back: try every failed file now. */
export function retryFailed(): void {
  entries.forEach((e) => { if (e.state.status === "failed") { e.tries = 0; requeue(e); } });
}
if (typeof window !== "undefined") {
  window.addEventListener("online", () => entries.forEach((e) => { if (e.state.status === "failed" && !e.state.permanent) requeue(e); }));
  // files the browser could not store are lost with the tab: ask before it closes
  window.addEventListener("beforeunload", (ev) => {
    if ([...entries.values()].some((e) => e.state.deviceOnly && e.state.status !== "done")) ev.preventDefault();
  });
}

/** Sign-out: stop sending, drop every file from memory (and its preview), so nothing carries on
 *  under the next person. What is kept in IndexedDB is dealt with by the sign-out itself. */
export function reset(): void {
  gen++;
  abortTransfers();
  entries.forEach((e) => { clearTimeout(e.timer); if (e.state.preview) URL.revokeObjectURL(e.state.preview); });
  entries.clear();
  renamed.clear();
  queue.length = 0;
  running = 0;
  emit();
}

export function useUploads(bookingId?: string): UploadState[] {
  useSyncExternalStore((l) => { listeners.add(l); return () => { listeners.delete(l); }; }, () => version);
  return [...entries.values()].map((e) => e.state).filter((s) => !bookingId || s.bookingId === bookingId);
}
export const uploadFor = (assetId: string): UploadState | undefined => find(assetId)?.state;
/** The server's id for a file picked offline, once it has one. */
export const realId = (id: string): string | undefined => renamed.get(id);

/** Resolves once the file's bytes are on the server; rejects if sending fails or it was taken back. */
export function uploaded(assetId: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const check = () => {
      const s = uploadFor(assetId);
      if (s?.status === "done") { listeners.delete(check); resolve(); }
      else if (!s || s.status === "failed") { listeners.delete(check); reject(new Error(s?.error || "The upload did not finish. Try again.")); }
    };
    listeners.add(check);
    check();
  });
}
export function summary(list: UploadState[]): { done: number; total: number } {
  return { done: list.filter((s) => s.status === "done").length, total: list.length };
}
/** For tests. */
export const _reset = reset;
