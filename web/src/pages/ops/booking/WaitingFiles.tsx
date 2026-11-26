import { useQuery } from "@tanstack/react-query";
import { CircleCheck, CircleDashed, Upload } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api } from "../../../api/client";
import { keys } from "../../../api/keys";
import type { Booking } from "../../../api/types";
import { LoadError, Modal, useToast } from "../../../ui/kit";
import type { MediaField } from "./parts";
import { useOpsFiles } from "./useOpsFiles";

export type Missing = {
  part: string;
  key: string;
  label: string;
  count: number;
  required: boolean;
  ids: string[];
  of: number;
  page: string;
  section: string;
};
type Phone = { last_seen_at: string | null; files: number | null } | null;

const REASONS = [
  ["customer_waiting", "Customer is waiting for the report"],
  ["phone_lost", "Expert's phone is lost or broken"],
  ["other", "Other"],
] as const;

const plural = (n: number, w: string) => `${n} ${w}${n === 1 ? "" : "s"}`;
function ago(iso: string, now = Date.now()) {
  const min = Math.max(0, Math.round((now - new Date(iso).getTime()) / 60000));
  if (min < 60) return plural(min, "min");
  const h = Math.round(min / 60);
  return h < 48 ? `${h} h` : plural(Math.round(h / 24), "day");
}

/** What Ops read about the expert's phone: still sending (wait), or likely lost (upload here). */
export function phoneLine(expert: string, p: Phone, now = Date.now()) {
  const who = expert || "The expert";
  const holds = p?.files ? `, still holds ${plural(p.files, "file")}` : "";
  if (!p?.last_seen_at)
    return `${who}'s phone is signed out or never checked in. Get the files from ${expert || "them"} and upload them here.`;
  const stale = now - new Date(p.last_seen_at).getTime() > 2 * 3600_000;
  return stale
    ? `${who}'s phone: not seen for ${ago(p.last_seen_at, now)}${holds}. It may be lost. Get the files from ${expert || "them"} and upload them here.`
    : `${who}'s phone: seen ${ago(p.last_seen_at, now)} ago${holds}. Usually wait. If stuck, ask ${expert || "them"} to open Vayu on Wi-Fi.`;
}

/** A job waiting for the expert's files: one row per field with an Upload in place of the missing
 *  ones. Ops can finish at any time, required files missing too, with a reason (owner, 2026-11-27);
 *  the report then uses its stand-in image and files that arrive later mark it out of date. */
export function WaitingFiles({
  booking,
  fields,
  expert,
  onFinished,
}: {
  booking: Booking;
  fields: MediaField[];
  expert: string;
  onFinished: () => void;
}) {
  const { fail, say } = useToast();
  const [asking, setAsking] = useState(false);
  const [reason, setReason] = useState<string>("customer_waiting");
  const [note, setNote] = useState("");
  // rows Ops uploaded here: "checking" until the server verifies them, then done (with the time)
  const [mine, setMine] = useState<Record<string, { at: string; row: Missing }>>({});
  const q = useQuery({
    queryKey: keys.bookingPart(booking.id, "missing-files", booking.row_version),
    queryFn: ({ signal }) =>
      api<{ missing: Missing[]; can_finish: boolean; phone: Phone }>(`bookings/${booking.id}/missing-files`, { signal }),
    refetchInterval: Object.keys(mine).length ? 5000 : false, // our uploads are being checked
  });
  const missing = q.data?.missing ?? [];
  const id = (m: { part: string; key: string }) => `${m.part}.${m.key}`;
  const all = missing.length > 0 || Object.keys(mine).length > 0;
  // every file in: the server completes the job by itself, so the page reloads without the banner
  useEffect(() => {
    if (q.isSuccess && !missing.length && Object.keys(mine).length) onFinished();
  }, [q.isSuccess, missing.length, mine, onFinished]);
  // a failed load is never "nothing missing"
  if (q.isError) return <LoadError error={q.error} what="the files this booking waits for" onRetry={q.refetch} />;
  if (!all) return null;
  const total = missing.reduce((n, m) => n + m.count, 0);
  const need = missing.filter((m) => m.required).reduce((n, m) => n + m.count, 0);
  const done = Object.values(mine).filter((d) => !missing.some((m) => id(m) === id(d.row)));
  const rows = [...missing].sort((a, b) => Number(b.required) - Number(a.required));
  const finish = async () => {
    try {
      await api(`bookings/${booking.id}/finish`, { method: "POST", body: { reason, ...(note.trim() ? { note: note.trim() } : {}) } });
      setAsking(false);
      say("Finished. The report is being made.");
      onFinished();
    } catch (e) {
      fail(e);
    }
  };
  return (
    <>
      <div className="banner warn missing-box" role="status" aria-label="Waiting for files">
        <strong>
          {total ? `Waiting for ${plural(total, "file")} from the expert${need ? `, ${need} required` : ""}` : "Checking your uploads"}
        </strong>
        {q.data && total > 0 && <div className="small">{phoneLine(expert, q.data.phone)}</div>}
        <ul className="missing-list">
          {rows.map((m) => (
            <MissingRow
              key={id(m)}
              booking={booking}
              m={m}
              f={fields.find((f) => f.part === m.part && f.key === m.key)}
              checking={!!mine[id(m)]}
              onUploaded={() => {
                setMine((x) => ({ ...x, [id(m)]: { at: new Date().toTimeString().slice(0, 5), row: m } }));
                void q.refetch();
              }}
            />
          ))}
          {done.map((d) => (
            <li key={id(d.row)} className="missing-row done">
              <CircleCheck size={18} aria-hidden className="ok-text" />
              <div className="grow">
                {d.row.page} › {d.row.section} › <b>{d.row.label}</b>
                <div className="muted small">Uploaded by you, {d.at}</div>
              </div>
              <span className="pill ok">Done</span>
            </li>
          ))}
        </ul>
        {total > 0 && (
          <div className="bar" style={{ marginTop: 8, marginBottom: 0 }}>
            <span className="muted small grow">Upload them, or finish now and send a partial report.</span>
            <button onClick={() => setAsking(true)}>Finish without the missing files</button>
          </div>
        )}
      </div>
      {/* outside the banner, so the dialog keeps its own colours */}
      {asking && (
        <Modal
          title={`Finish without ${plural(total, "file")}?`}
          onClose={() => setAsking(false)}
          actions={
            <>
              <button onClick={() => setAsking(false)}>Cancel</button>
              <button className="primary" onClick={() => void finish()}>
                Finish
              </button>
            </>
          }
        >
          <p className="muted" style={{ marginTop: 0 }}>
            {need ? `${need} ${need === 1 ? "is" : "are"} required. ` : ""}
            The report is made now with the usual stand-in image in their place. If the files arrive later, the report goes out of date and
            you can regenerate it.
          </p>
          <label className="field">
            <span>Reason</span>
            <select value={reason} onChange={(e) => setReason(e.target.value)}>
              {REASONS.map(([k, l]) => (
                <option key={k} value={k}>
                  {l}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Note (optional)</span>
            <input value={note} maxLength={300} onChange={(e) => setNote(e.target.value)} />
          </label>
        </Modal>
      )}
    </>
  );
}

function MissingRow({
  booking,
  m,
  f,
  checking,
  onUploaded,
}: {
  booking: Booking;
  m: Missing;
  f?: MediaField;
  checking: boolean;
  onUploaded: () => void;
}) {
  const { say } = useToast();
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const field: MediaField = f ?? {
    key: m.key,
    label: m.label,
    type: "photo",
    part: m.part as MediaField["part"],
    section: m.section,
    max: m.of,
    opsOk: false,
    accept: "",
  };
  const ops = useOpsFiles(booking, field, () => {});
  const noun = field.type === "photo" ? "photo" : field.type;
  // one pick fills the gaps in the order picked; extra files are not used
  const take = async (list: FileList | null) => {
    const files = [...(list ?? [])];
    if (!files.length) return;
    await ops.put(files.slice(0, m.ids.length), undefined, m.ids);
    // after the upload's own message, so this one is the one left on screen
    if (files.length > m.ids.length)
      say(`Only ${m.ids.length} ${m.ids.length === 1 ? "was" : "were"} missing; ${plural(files.length - m.ids.length, noun)} not used.`);
    onUploaded();
  };
  const can = ops.allowed && !ops.busy && !checking;
  return (
    <li
      className={`missing-row${over ? " drop" : ""}`}
      onDragOver={(e) => {
        if (!can) return;
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setOver(false);
        if (can) void take(e.dataTransfer.files);
      }}
    >
      <CircleDashed size={18} aria-hidden className={m.required ? "bad-text" : "muted"} />
      <div className="grow">
        {m.page} › {m.section} › <b>{m.label}</b>
        <div className="muted small">
          {checking || ops.busy ? "Checking your upload…" : `${m.count} of ${plural(m.of, noun)} not arrived`}
        </div>
      </div>
      <span className={`pill ${m.required ? "bad" : ""}`}>{m.required ? "Required" : "Optional"}</span>
      {ops.allowed ? (
        <>
          <button className="sm" disabled={!can} aria-label={`Upload ${m.label}`} onClick={() => input.current?.click()}>
            <Upload size={14} aria-hidden /> Upload
          </button>
          <input
            ref={input}
            type="file"
            hidden
            multiple={m.ids.length > 1}
            accept={ops.accept}
            onChange={(e) => {
              void take(e.target.files);
              e.target.value = "";
            }}
          />
        </>
      ) : (
        <span className="muted small" title="Admin has blocked uploads by Ops on this field">
          No Ops upload
        </span>
      )}
    </li>
  );
}
