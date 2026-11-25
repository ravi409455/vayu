import { useState } from "react";
import { api } from "../../../api/client";
import type { Booking } from "../../../api/types";
import { useAuth } from "../../../auth";
import { addFile, discardFile, uploaded } from "../../../lib/uploadManager";
import { useToast } from "../../../ui/kit";
import { opsMayEdit } from "../../../lib/actions";
import type { MediaField } from "./parts";

/** Ops' add and replace for one field: saved straight away (upload, then attach), never a delete.
 *  The server checks the same rules: after submit, photos and videos, not blocked. */
export function useOpsFiles(booking: Booking, f: MediaField, onDone: () => void, onReplaced?: (id: string) => void) {
  const { can } = useAuth();
  const { say, fail } = useToast();
  const [busy, setBusy] = useState(false);
  async function put(files: File[], replaces?: string) {
    if (!files.length) return;
    setBusy(true);
    try {
      for (const file of files) {
        const id = await addFile({
          bookingId: booking.id,
          fieldKey: f.key,
          kind: f.type as "photo",
          file,
          name: file.name,
          source: "gallery",
          replaces,
        });
        // only a fully sent file goes into the inspection (a half-sent one must not push out a good one)
        try {
          await uploaded(id);
        } catch (e) {
          void discardFile(id);
          throw e;
        }
        await api(`media/${id}/attach`, { body: replaces ? { replaces } : {} });
        if (replaces) onReplaced?.(id);
      }
      say(replaces ? "Replaced. The old file is kept in the history." : "Added. It is checked in the background.");
    } catch (e) {
      fail(e);
    } finally {
      setBusy(false);
      onDone();
    }
  }
  return {
    allowed: can("media.manage") && opsMayEdit(booking) && f.opsOk,
    busy,
    put,
    accept: f.accept,
    noun: f.type === "photo" ? "photo" : f.type,
  };
}
