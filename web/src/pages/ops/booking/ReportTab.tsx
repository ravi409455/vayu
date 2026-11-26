import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Download, RefreshCw } from "lucide-react";
import { api, ApiError } from "../../../api/client";
import { useRefresh } from "../../../api/hooks";
import { keys } from "../../../api/keys";
import type { Booking } from "../../../api/types";
import { useAuth } from "../../../auth";
import { fmtStamp } from "../../../lib/format";
import { reportError } from "../../../lib/problems";
import { Empty, LoadError, Pill, useToast } from "../../../ui/kit";
import { PdfPreview } from "./PdfPreview";
import type { Activity } from "./parts";

type ReportInfo = {
  verify_url?: string;
  revision: number;
  status: string;
  updating: boolean;
  generated_at: string | null;
  filename: string;
  error: string;
  url: string | null;
  preview_url?: string | null;
  /** something it shows changed since this PDF was made; Ops press Regenerate (F-219) */
  out_of_date?: boolean;
  regenerate?: { allowed: boolean; reason: string | null };
};

/** After Regenerate: keep looking until a new revision shows (the worker may not have started yet),
 *  for at most two minutes. */
export type Waiting = { revision: number | null; until: number };

/** The booking's report (null: none yet). While it is being made, look every few seconds. */
export function useReport(bookingId: string, enabled = true, waiting: Waiting | null = null) {
  return useQuery({
    queryKey: keys.bookingPart(bookingId, "report"),
    retry: false,
    enabled,
    refetchInterval: (x) => {
      const d = x.state.data;
      if (d?.updating) return 3000;
      return waiting && Date.now() < waiting.until && (d?.revision ?? null) === waiting.revision ? 3000 : false;
    },
    queryFn: async () => {
      try {
        return await api<ReportInfo>(`bookings/${bookingId}/report`);
      } catch (e) {
        if (e instanceof ApiError && e.status === 404) return null;
        throw e;
      }
    },
  });
}

/** The PDF: made when the booking completes. Later changes do not touch it: it shows "Out of date"
 *  and Ops press Regenerate when they are done (F-219). Downloads and shares are logged; the list
 *  below shows who and when. */
export function ReportTab({ booking, activity }: { booking: Booking; activity: Activity[] }) {
  const { say, fail } = useToast();
  const refresh = useRefresh();
  const { can } = useAuth();
  const [waiting, setWaiting] = useState<Waiting | null>(null);
  const q = useReport(booking.id, can("reports.view"), waiting);
  const r = q.data;
  // a new revision arrived: nothing left to wait for
  const watching = !!waiting && Date.now() < waiting.until && (r?.revision ?? null) === waiting.revision;
  const regen = useMutation({
    // one press, one request: the button is off while it runs
    mutationFn: () => api(`bookings/${booking.id}/report/regenerate`, { body: {} }),
    onSuccess: () => {
      say("Making the new PDF. It shows here by itself.");
      setWaiting({ revision: r?.revision ?? null, until: Date.now() + 120_000 });
      void q.refetch();
      void refresh(keys.problems());
    },
    onError: (e) => {
      fail(e);
      void q.refetch();
    },
  });
  const why = r?.regenerate && !r.regenerate.allowed ? (r.regenerate.reason ?? "") : "";
  const busy = regen.isPending || !!r?.updating || watching;
  // no report at all (its first render was lost or had no layout): Ops can make it from here
  const firstMissing = q.isSuccess && !r && booking.stage === "completed" && !booking.conflict;
  if (q.isError) return <LoadError error={q.error} what="report" onRetry={q.refetch} />;
  if (q.isPending && can("reports.view")) return <p className="muted pad">Loading…</p>;
  const passedOn = activity.filter((a) => a.kind === "report_downloaded" || a.kind === "report_shared");
  async function copyCheckLink() {
    try {
      if (!navigator.clipboard) throw new Error("no clipboard");
      await navigator.clipboard.writeText(r!.verify_url!);
    } catch {
      say("Could not copy here. Select the link and copy it yourself.", true);
      return;
    }
    try {
      // logged only once it really was copied
      await api(`bookings/${booking.id}/report/shared`, { body: { how: "check_link" } });
      say("Check link copied.");
      void refresh(keys.bookingPart(booking.id, "activity"));
    } catch (e) {
      fail(e);
    }
  }
  return (
    <>
      <div className="bar">
        {r && (
          <>
            <Pill tone={r.updating ? "warn" : r.status === "ready" ? "ok" : r.status === "failed" ? "bad" : "warn"}>
              {r.updating ? "Updating…" : r.status === "ready" ? "Ready" : r.status === "failed" ? "Failed" : "Being made"}
            </Pill>
            {r.out_of_date && !r.updating && <Pill tone="warn">Out of date</Pill>}
            <span className="muted small">
              Revision {r.revision} · {fmtStamp(r.generated_at)}
            </span>
          </>
        )}
        <span className="grow" />
        {(r || firstMissing) && can("submissions.edit") && (
          <button
            disabled={busy || !!why}
            title={why || undefined}
            onClick={() => {
              if (!regen.isPending) regen.mutate();
            }}
          >
            <RefreshCw size={15} aria-hidden /> {busy ? "Making…" : r ? "Regenerate" : "Make the PDF"}
          </button>
        )}
        {r?.verify_url && r.status === "ready" && <button onClick={() => void copyCheckLink()}>Copy check link</button>}
        {r?.url && (
          <a
            className="btn primary"
            href={r.url}
            download={r.filename}
            onClick={() => setTimeout(() => void refresh(keys.bookingPart(booking.id, "activity")), 1500)}
          >
            <Download size={15} aria-hidden /> Download PDF
          </a>
        )}
      </div>
      {(r?.updating || watching) && <p className="muted small">The new PDF is being made. This page shows it by itself.</p>}
      {r?.out_of_date && !busy && (
        <div className="banner warn">Out of date: changes since this PDF. Press Regenerate when you are done to make a new one.</div>
      )}
      {r && why && can("submissions.edit") && <p className="muted small">Regenerate is off: {why}</p>}
      {r?.error && !r.updating && <div className="banner bad">Problem: {reportError(r.error)}. It is tried again by itself.</div>}
      {!r && !firstMissing && <Empty title="No report yet">It is made automatically when the booking is Completed.</Empty>}
      {!r && firstMissing && (
        <Empty title="No report yet">
          This booking is Completed but its PDF was not made{busy ? "" : ". Press Make the PDF to make it now"}.
        </Empty>
      )}
      {r?.preview_url && <PdfPreview url={r.preview_url} />}
      {r && (
        <section className="card" aria-label="Downloads and shares" style={{ marginTop: 14 }}>
          <h3 style={{ marginTop: 0 }}>Downloads and shares</h3>
          {passedOn.length === 0 ? (
            <p className="muted small">Nobody has downloaded or shared it yet.</p>
          ) : (
            <ul className="plain-list">
              {passedOn.map((a, i) => (
                <li key={i}>
                  <strong>{a.by?.name ?? "Someone"}</strong>{" "}
                  {a.kind === "report_downloaded"
                    ? "downloaded the PDF"
                    : (a.changes as Record<string, unknown>).how === "pdf"
                      ? "shared the PDF"
                      : "copied the check link"}{" "}
                  <span className="muted small">
                    · revision {String((a.changes as Record<string, unknown>).revision ?? "")} · {fmtStamp(a.at)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
    </>
  );
}
