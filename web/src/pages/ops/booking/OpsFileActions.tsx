import { Plus, RefreshCw } from "lucide-react";
import type { Booking } from "../../../api/types";
import { FilePick } from "./FilePick";
import type { MediaField } from "./parts";
import { useOpsFiles } from "./useOpsFiles";

/** Replace and Add under the Media preview (or Add alone on an empty field). Add stays visible
 *  but greyed out when the field is full, so people see why they can only replace. */
export function OpsFileActions({ booking, f, count, replaceId, onDone, onReplaced, hint }: { booking: Booking; f: MediaField; count: number; replaceId?: string; onDone: () => void; onReplaced?: (id: string) => void; hint?: string }) {
  const ops = useOpsFiles(booking, f, onDone, onReplaced);
  if (!ops.allowed) return null;
  const room = f.max - count;
  const add = (
    <FilePick className="btn sm" busy={ops.busy} disabled={room <= 0} accept={ops.accept} multiple={room > 1} label={`Add to ${f.label}`}
      title={room <= 0 ? `Full (${count} of ${f.max}). Replace a ${ops.noun} instead.` : undefined} onPick={(fs) => void ops.put(fs.slice(0, room))}>
      <Plus size={14} aria-hidden /> Add {ops.noun}</FilePick>);
  if (!replaceId) return add;
  return (
    <div className="ops-file-actions">
      <div className="ops-file-btns">
        <FilePick className="btn sm primary" busy={ops.busy} accept={ops.accept} label={`Replace this ${ops.noun}`} onPick={(fs) => void ops.put(fs.slice(0, 1), replaceId)}>
          <RefreshCw size={14} aria-hidden /> Replace</FilePick>
        {add}
      </div>
      <p className="muted small">{ops.busy ? "Uploading…" : `${count} of ${f.max} in this field${room <= 0 ? " (full)" : ""}. Saves straight away.${hint ? ` ${hint}` : ""}`}</p>
    </div>);
}
