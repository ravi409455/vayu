import { useState } from "react";
import type { User } from "../../../api/types";
import { fmtSlot, fmtStamp } from "../../../lib/format";
import { InfoTip } from "../../../ui/InfoTip";
import { mediaUrl } from "../../../ui/MediaThumb";
import type { Activity } from "./parts";

/** Admin only (the server sends the old file's id to nobody else): open a replaced file. */
function openOld(id: string) {
  const w = window.open("", "_blank"); // opened now, so the pop-up blocker allows it
  if (w) w.opener = null; // the storage page gets no handle on this one
  void mediaUrl(id).then((l) => {
    if (l?.url && w) w.location.href = l.url;
    else w?.close();
  });
}

/** One line per thing that happened, newest first. */
export function activityText(
  r: Activity,
  expertName: (id: unknown) => string,
  label: (k: string) => string,
  typeLabel: (k: unknown) => string,
): string {
  const by = r.by?.name ?? "The system";
  const c = r.changes;
  if (r.kind === "created") return `Created by ${by}`;
  if (r.kind === "inspection_edited") return `${by} changed ${r.keys.length} answer${r.keys.length === 1 ? "" : "s"}`;
  if (r.kind === "ratings_changed") return `${by} changed the ratings`;
  if (r.kind === "report_downloaded") return `${by} downloaded the report`;
  if (r.kind === "report_shared")
    return `${by} ${(c?.how as unknown as string) === "pdf" ? "shared the report PDF" : "copied the report's check link"}`;
  if (r.kind === "key_checks_changed") {
    const moved = Object.entries(c ?? {}) as [string, [string | null, string | null]][];
    return moved.length
      ? `${by} changed ${moved.map(([k, [a, b]]) => `${label(k)}: ${a || "empty"} → ${b || "empty"}`).join("; ")}`
      : `${by} changed ${r.keys.map(label).join(", ") || "Key Checks"}`;
  }
  if (r.kind === "media_replaced") return `${by} replaced a file in ${r.keys.map(label).join(", ") || "the inspection"}`;
  if (r.kind === "media_added") return `${by} added a file to ${r.keys.map(label).join(", ") || "the inspection"}`;
  if (r.kind === "finished_without_files") {
    const n = Number(c?.missing?.[1] ?? c?.missing ?? 0);
    const req = Number(c?.required ?? 0);
    const why = { customer_waiting: "customer is waiting", phone_lost: "phone lost or broken", other: "other" }[String(c?.reason ?? "")];
    const which = r.keys.filter((k) => k !== "stage").map(label);
    return `Finished by ${by} without ${n} file${n === 1 ? "" : "s"}${req ? ` (${req} required)` : ""}${which.length ? `: ${which.join(", ")}` : ""}${
      why ? ` · ${why}` : ""
    }${c?.note ? ` · "${String(c.note)}"` : ""}`;
  }
  if (r.kind === "late_reviewed") return `Late start reviewed by ${by}`;
  if (r.kind === "quick_reviewed") return `Quick finish reviewed by ${by}`;
  const stage = c.stage?.[1];
  if (stage === "completed") return "Completed: every file uploaded";
  if (stage === "submitted") return `Submitted by ${by}`;
  if (stage === "in_progress") return `Started by ${by}`;
  if (stage === "cancelled") return `Cancelled by ${by}`;
  if (stage === "assigned" && c.stage?.[0] === "in_progress") return `Force-released by ${by}`;
  if (c.assigned_expert) return `${c.assigned_expert[0] ? "Reassigned" : "Assigned"} to ${expertName(c.assigned_expert[1])} by ${by}`;
  if (c.inspection_date || c.inspection_time) return `Rescheduled to ${fmtSlot(c.inspection_date?.[1], c.inspection_time?.[1])} by ${by}`;
  if (c.inspection_type) return `Type changed to ${typeLabel(c.inspection_type[1])} by ${by}`;
  if (c.conflict) return `Conflict resolved by ${by}`;
  return `${by} changed ${r.keys.map(label).join(", ") || "the booking"}`;
}

// already said by the line itself, or bookkeeping rather than an answer
const NOT_DETAIL = new Set(["stage", "conflict", "alert", "revision", "how", "missing", "media"]);
const NO_DETAIL_KINDS = new Set([
  "key_checks_changed",
  "report_downloaded",
  "report_shared",
  "alert_cleared",
  "late_reviewed",
  "quick_reviewed",
]);

/** "Customer phone: 98… → 97…", one line per changed value (only values this person may see). */
export function activityDetails(
  r: Activity,
  expertName: (id: unknown) => string,
  label: (k: string) => string,
  typeLabel: (k: unknown) => string,
): string[] {
  if (NO_DETAIL_KINDS.has(r.kind)) return [];
  const show = (k: string, v: unknown): string => {
    if (v === null || v === undefined || v === "" || (Array.isArray(v) && v.length === 0)) return "empty";
    if (k === "assigned_expert") return expertName(v);
    if (k === "inspection_type") return typeLabel(v);
    if (typeof v === "boolean") return v ? "Yes" : "No";
    if (Array.isArray(v)) return v.map((x) => show("", x)).join(", ");
    if (typeof v === "object") return JSON.stringify(v);
    return String(v);
  };
  return (
    Object.entries(r.changes ?? {})
      .filter(([k, v]) => !NOT_DETAIL.has(k) && Array.isArray(v) && v.length === 2)
      // "Assigned to Ravi" already says it all; a reassignment still shows who had it before
      .filter(([k, [a]]) => !(k === "assigned_expert" && (a === null || a === undefined)))
      .map(([k, [a, b]]) => `${label(k)}: ${show(k, a)} → ${show(k, b)}`)
  );
}

export function ActivityCard({
  rows,
  experts,
  labels,
  typeLabel,
}: {
  rows: Activity[];
  experts: User[];
  labels: (k: string) => string;
  typeLabel: (k: unknown) => string;
}) {
  const [all, setAll] = useState(false);
  const name = (id: unknown) => {
    const u = experts.find((x) => x.id === id);
    return u ? u.name || u.username : "an expert";
  };
  const shown = all ? rows : rows.slice(0, 6);
  return (
    <section className="card" aria-label="Activity">
      <h2 className="rail-h">Activity</h2>
      {rows.length === 0 && <p className="muted small">Nothing yet.</p>}
      <ol className="timeline">
        {shown.map((r, i) => (
          <li key={i} className={r.kind === "inspection_edited" || r.kind === "edited" ? "edit" : r.changes.stage ? "stage" : ""}>
            <ActivityLine text={activityText(r, name, labels, typeLabel)} details={activityDetails(r, name, labels, typeLabel)} />
            {typeof r.changes.media?.[0] === "string" && (
              <button className="link small" onClick={() => openOld(String(r.changes.media![0]))}>
                Open the old file
              </button>
            )}
            <div className="muted small">{fmtStamp(r.at)}</div>
          </li>
        ))}
      </ol>
      {rows.length > 6 && (
        <button className="link" onClick={() => setAll(!all)}>
          {all ? "Show less" : `Show all ${rows.length}`}
        </button>
      )}
    </section>
  );
}

/** The line; when it changed values, hovering it (or the "i": focus or tap) shows old → new. */
function ActivityLine({ text, details }: { text: string; details: string[] }) {
  if (details.length === 0) return <div>{text}</div>;
  return (
    <div>
      <InfoTip label="What changed" before={<span className="activity-line">{text}</span>}>
        <span className="activity-details">
          {details.map((d, i) => {
            const at = d.indexOf(": ");
            return (
              <span key={i}>
                <strong>{d.slice(0, at)}</strong>
                {d.slice(at)}
              </span>
            );
          })}
        </span>
      </InfoTip>
    </div>
  );
}
