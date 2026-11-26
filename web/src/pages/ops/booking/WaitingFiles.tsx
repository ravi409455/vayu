import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../../../api/client";
import { keys } from "../../../api/keys";
import type { Booking } from "../../../api/types";
import { Confirm, LoadError, useToast } from "../../../ui/kit";

type Missing = { part: string; key: string; label: string; count: number; required: boolean };

/** A job waiting for the expert's files. When they will not come (a lost phone), Ops upload the
 *  required ones in Media, then finish it without the rest (the report is made then). */
export function WaitingFiles({ booking, onFinished, onMedia }: { booking: Booking; onFinished: () => void; onMedia: () => void }) {
  const { fail, say } = useToast();
  const [asking, setAsking] = useState(false);
  const q = useQuery({
    queryKey: keys.bookingPart(booking.id, "missing-files", booking.row_version),
    queryFn: ({ signal }) => api<{ missing: Missing[]; can_finish: boolean }>(`bookings/${booking.id}/missing-files`, { signal }),
  });
  const missing = q.data?.missing ?? [];
  // a failed load is never "nothing missing"
  if (q.isError) return <LoadError error={q.error} what="the files this booking waits for" onRetry={q.refetch} />;
  if (!missing.length) return null;
  const total = missing.reduce((n, m) => n + m.count, 0);
  const need = missing.filter((m) => m.required);
  const finish = async () => {
    setAsking(false);
    try {
      await api(`bookings/${booking.id}/finish`, { method: "POST" });
      say("Finished. The report is being made.");
      onFinished();
    } catch (e) {
      fail(e);
    }
  };
  return (
    <div className="banner warn" role="status" aria-label="Waiting for files">
      <strong>
        Waiting for {total} file{total === 1 ? "" : "s"} from the expert:
      </strong>{" "}
      {missing.map((m) => `${m.label}${m.count > 1 ? ` (${m.count})` : ""}${m.required ? " · required" : ""}`).join(", ")}.
      <div className="muted small">
        If they will not come (a lost or broken phone): upload {need.length ? "the required ones" : "any you have"} in Media, then finish
        without the rest. Files that arrive later are still added to the report.
      </div>
      <div className="bar" style={{ marginTop: 8, marginBottom: 0 }}>
        {need.length > 0 && <button onClick={onMedia}>Open Media</button>}
        <button
          className="primary"
          disabled={!q.data?.can_finish}
          title={need.length ? `Upload first: ${need.map((m) => m.label).join(", ")}` : undefined}
          onClick={() => setAsking(true)}
        >
          Finish without the missing files
        </button>
      </div>
      {asking && (
        <Confirm title="Finish without the missing files?" confirmLabel="Finish" onConfirm={finish} onCancel={() => setAsking(false)}>
          The booking is marked Completed and the report is made without {total} file{total === 1 ? "" : "s"}. If the expert's phone sends
          them later, they are added and the report is made again.
        </Confirm>
      )}
    </div>
  );
}
