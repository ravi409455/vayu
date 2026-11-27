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
  /** `replaces`: one file in place of that one. `slots`: file i takes the place of slots[i] (files
   *  that never arrived), so one pick fills several gaps. */
  async function put(files: File[], replaces?: string, slots?: string[]) {
    if (!files.length) return;
    setBusy(true);
    try {
      for (const [i, file] of files.entries()) {
        const replacesThis = slots ? slots[i] : replaces;
        if (!replacesThis && slots) break;
        const id = await addFile({
          bookingId: booking.id,
          fieldKey: f.key,
          kind: f.type as "photo",
          file,
          name: file.name,
          source: "gallery",
          replaces: replacesThis,
        });
        // only a fully sent file goes into the inspection (a half-sent one must not push out a good one)
        try {
          await uploaded(id);
        } catch (e) {
          void discardFile(id);
          throw e;
        }
        await api(`media/${id}/attach`, { body: replacesThis ? { replaces: replacesThis } : {} });
        if (replacesThis && !slots) onReplaced?.(id);
      }
      say(
        slots
          ? "Uploaded. It is checked in the background."
          : replaces
            ? "Replaced. The old file is kept in the history."
            : "Added. It is checked in the background.",
      );
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
