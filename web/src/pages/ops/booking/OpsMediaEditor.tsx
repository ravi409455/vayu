import { useState } from "react";
import type { Booking } from "../../../api/types";
import { Thumb } from "../../../ui/MediaThumb";
import { OpsFileActions } from "./OpsFileActions";
import type { MediaField } from "./parts";

/** A media field in the Inspection edit view: the files as plain thumbnails, then the same
 *  Replace / Add bar as the Media tab. With several files, click one to pick what Replace swaps. */
export function OpsMediaEditor({ booking, f, ids, onDone }: { booking: Booking; f: MediaField; ids: string[]; onDone: () => void }) {
  const [sel, setSel] = useState<string | null>(null);
  const video = f.type === "video";
  const current = sel && ids.includes(sel) ? sel : ids[0];
  const pick = ids.length > 1;
  return (
    <div>
      {ids.length === 0 && <p className="muted small">No {video ? "videos" : "files"} yet.</p>}
      {ids.length > 0 && (
        <div className="photo-grid">
          {ids.map((id, i) =>
            pick ? (
              <button
                key={id}
                type="button"
                className={`tile-btn${id === current ? " on" : ""}`}
                data-testid="media-item"
                aria-pressed={id === current}
                aria-label={`${f.label} ${i + 1}`}
                onClick={() => setSel(id)}
              >
                <Thumb id={id} video={video} />
              </button>
            ) : (
              <Thumb key={id} id={id} video={video} />
            ),
          )}
        </div>
      )}
      <OpsFileActions
        booking={booking}
        f={f}
        count={ids.length}
        replaceId={current}
        onDone={onDone}
        onReplaced={setSel}
        hint={pick ? `Replace swaps the selected ${f.type}; click another to pick it.` : undefined}
      />
    </div>
  );
}
