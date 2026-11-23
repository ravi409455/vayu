import { staleInfo } from "../api/client";
import type { Stale } from "../ui/StaleDialog";

export type SaveOutcome = { ok: true; value: unknown } | { ok: false; stale: Stale } ;

/** Sends only the changed fields. A 409 "changed by someone" comes back as data, not an error,
 *  so the screen can ask what to do; any other failure is thrown. */
export async function saveDirty(send: (rowVersion: number, changed: Record<string, unknown>) => Promise<unknown>, rowVersion: number, changed: Record<string, unknown>): Promise<SaveOutcome> {
  try {
    return { ok: true, value: await send(rowVersion, changed) };
  } catch (e) {
    const s = staleInfo(e);
    if (s) return { ok: false, stale: s };
    throw e;
  }
}
