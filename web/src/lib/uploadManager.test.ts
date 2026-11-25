import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../api/client";
import type { PendingUpload } from "./store";

// The browser's store and the network are faked; the queue's own logic is real.
const db = new Map<string, PendingUpload>();
let putFails = false;
let putHook: (() => void) | null = null;
vi.mock("./store", () => ({
  putJob: async (j: PendingUpload) => { if (putFails) throw new Error("QuotaExceededError"); db.set(j.clientUuid, j); putHook?.(); },
  deleteJob: async (id: string) => { db.delete(id); },
  allJobs: async () => [...db.values()],
}));
type Plan = () => Promise<{ id: string; status: string }>;
const plans: Plan[] = [];
const transfer = vi.fn(async (s: { clientUuid: string; assetId?: string }) => (plans.shift() ?? (async () => ({ id: s.assetId || "srv-" + s.clientUuid, status: "verified" })))());
let initiateFails: Error | null = null;
vi.mock("./uploader", () => ({
  transfer: (s: never) => transfer(s),
  initiate: async (s: { clientUuid: string }) => { if (initiateFails) throw initiateFails; return { id: "srv-" + s.clientUuid, status: "pending", part_size: 1 }; },
  hashBlob: async () => "0".repeat(64),
  shrinkImage: async (b: Blob) => b,
  abortTransfers: vi.fn(),
}));
const reported = vi.fn();
vi.mock("./monitor", () => ({ report: (...a: unknown[]) => reported(...a) }));
const api = vi.fn(async (_path: string, _o?: unknown): Promise<unknown> => ({ status: "verified" }));
vi.mock("../api/client", async (orig) => ({ ...(await orig<typeof import("../api/client")>()), api: (p: string, o?: unknown) => api(p, o) }));

import { addFile, realId, resumeUploads, retryFailed, reset, RETRY_MS, uploadFor, useUploads } from "./uploadManager";
import { renderHook } from "@testing-library/react";

const add = (extra: Record<string, unknown> = {}) =>
  addFile({ bookingId: "b1", fieldKey: "door", kind: "file", file: new Blob(["x"], { type: "image/jpeg" }), name: "a.jpg", source: "camera", ...extra });
const flush = () => vi.advanceTimersByTimeAsync(0);
const states = () => renderHook(() => useUploads("b1")).result.current;

beforeEach(() => { vi.useFakeTimers(); reset(); db.clear(); plans.length = 0; transfer.mockClear(); api.mockClear(); putFails = false; initiateFails = null; });
afterEach(() => vi.useRealTimers());

describe("upload queue", () => {
  it("sends every file, not just the first two (C-03)", async () => {
    for (let i = 0; i < 5; i++) plans.push(() => new Promise((r) => setTimeout(() => r({ id: "m" + i, status: "verified" }), 100)));
    await Promise.all([add(), add(), add(), add(), add()]);
    await vi.advanceTimersByTimeAsync(1000);
    expect(transfer).toHaveBeenCalledTimes(5);
    expect(states().map((s) => s.status)).toEqual(["done", "done", "done", "done", "done"]);
  });

  it("never sends more than two at once", async () => {
    const gates: (() => void)[] = [];
    for (let i = 0; i < 4; i++) plans.push(() => new Promise((r) => gates.push(() => r({ id: "x" + i, status: "verified" }))));
    for (let i = 0; i < 4; i++) await add();
    await flush();
    expect(transfer).toHaveBeenCalledTimes(2);
    gates[0]!(); await flush();
    expect(transfer).toHaveBeenCalledTimes(3);
  });

  it("a failed file is tried again by itself, waiting longer each time (C-03)", async () => {
    plans.push(() => Promise.reject(new Error("network")), () => Promise.reject(new Error("network")));
    const id = await add();
    await flush();
    expect(uploadFor(id)?.status).toBe("failed");
    await vi.advanceTimersByTimeAsync(RETRY_MS);
    expect(transfer).toHaveBeenCalledTimes(2);
    await vi.advanceTimersByTimeAsync(RETRY_MS);            // second wait is twice as long
    expect(transfer).toHaveBeenCalledTimes(2);
    await vi.advanceTimersByTimeAsync(RETRY_MS);
    expect(transfer).toHaveBeenCalledTimes(3);
    expect(uploadFor(id)?.status).toBe("done");
  });

  it("a file the server refuses is not retried, and says why", async () => {
    plans.push(() => Promise.reject(new ApiError(409, { code: "TOO_MANY", detail: "'door' takes at most 1." })));
    const id = await add();
    await vi.advanceTimersByTimeAsync(RETRY_MAX());
    expect(transfer).toHaveBeenCalledTimes(1);
    expect(uploadFor(id)).toMatchObject({ status: "failed", permanent: true, error: "'door' takes at most 1." });
    expect(reported).toHaveBeenCalledWith(new Error("Upload failed: TOO_MANY"), { where: "upload", kind: "file", code: "TOO_MANY" });   // F-235, code only
    retryFailed();                                           // the person asked: try anyway
    await flush();
    expect(transfer).toHaveBeenCalledTimes(2);
  });

  it("coming back online retries at once", async () => {
    plans.push(() => Promise.reject(new Error("network")));
    await add();
    await flush();
    window.dispatchEvent(new Event("online"));
    await flush();
    expect(transfer).toHaveBeenCalledTimes(2);
  });
});

describe("keeping the copy (F-151, F-152)", () => {
  it("keeps the browser's copy until the server has checked the checksum", async () => {
    plans.push(async () => ({ id: "m1", status: "uploaded" }));
    api.mockResolvedValueOnce({ status: "uploaded" }).mockResolvedValueOnce({ status: "verified" });
    await add();
    await flush();
    expect(db.size).toBe(1);
    await vi.advanceTimersByTimeAsync(3000);
    expect(db.size).toBe(1);
    await vi.advanceTimersByTimeAsync(10_000);
    expect(db.size).toBe(0);
  });

  it("a file that arrived damaged is sent again", async () => {
    plans.push(async () => ({ id: "m1", status: "uploaded" }));
    api.mockResolvedValueOnce({ status: "failed" });
    await add();
    await vi.advanceTimersByTimeAsync(3000);
    expect(transfer).toHaveBeenCalledTimes(2);
  });

  it("says so when the browser would not store the file", async () => {
    putFails = true;
    const id = await add();
    expect(uploadFor(id)?.deviceOnly).toBe(true);
  });
});

describe("no connection when picked (F-143)", () => {
  it("keeps the photo under a stand-in id and swaps in the server's once sent", async () => {
    initiateFails = new TypeError("Failed to fetch");
    plans.push(async () => ({ id: "m9", status: "verified" }));
    const id = await add({ keepOffline: true });
    expect(id).toMatch(/^local-/);
    expect(db.size).toBe(1);
    await flush();
    expect(realId(id)).toBe("m9");
    expect(uploadFor(id)?.assetId).toBe("m9");
  });

  it("a refusal from the server is still an error", async () => {
    initiateFails = new ApiError(400, { code: "INVALID_CONTENT_TYPE", detail: "nope" });
    await expect(add({ keepOffline: true })).rejects.toThrow("nope");
  });

  it("without keepOffline (Ops) no connection is an error", async () => {
    initiateFails = new TypeError("Failed to fetch");
    await expect(add()).rejects.toThrow("Failed to fetch");
  });
});

describe("sign-out (F-072) and resume (H-15)", () => {
  it("sign-out stops the queue and forgets every file", async () => {
    plans.push(() => new Promise(() => {}), () => new Promise(() => {}));
    for (let i = 0; i < 3; i++) await add();
    reset();
    await flush();
    expect(states()).toEqual([]);
    expect(transfer).toHaveBeenCalledTimes(2);              // the third never starts under the next person
  });

  it("a file still being prepared when the person signs out is not kept", async () => {
    let release!: () => void;
    initiateFails = null;
    const gate = new Promise<void>((r) => { release = r; });
    const pending = addFile({ bookingId: "b1", fieldKey: "door", kind: "file", file: { size: 1, type: "image/jpeg", slice: () => ({ arrayBuffer: () => gate.then(() => new ArrayBuffer(1)) }) } as unknown as Blob, name: "a", source: "camera" });
    reset();
    release();
    await expect(pending).rejects.toThrow("Signed out.");
    expect(db.size).toBe(0);
    expect(states()).toEqual([]);
  });

  it("a sign-out while the file is being stored leaves nothing behind", async () => {
    putHook = () => reset();                                // the person signs out during the save
    await expect(add()).rejects.toThrow("Signed out.");
    putHook = null;
    expect(db.size).toBe(0);
    expect(states()).toEqual([]);
  });

  it("resumes what the browser kept, once", async () => {
    db.set("u1", { clientUuid: "u1", bookingId: "b1", fieldKey: "door", kind: "file", contentType: "image/jpeg", name: "a", sha256: "", assetId: "m1", source: "camera", blob: new Blob(["x"]) });
    expect(await resumeUploads("b1")).toBe(1);
    expect(await resumeUploads("b1")).toBe(0);
    await flush();
    expect(transfer).toHaveBeenCalledTimes(1);
  });
});

function RETRY_MAX() { return 120_000; }
