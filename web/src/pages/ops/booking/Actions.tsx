import { useQuery } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { api } from "../../../api/client";
import { fetchAll } from "../../../api/hooks";
import { keys } from "../../../api/keys";
import { useInspectionTypes, useTypeLabels } from "../../../api/labels";
import type { Booking, MasterListItem, User } from "../../../api/types";
import { Confirm, Field, Modal } from "../../../ui/kit";

export function Actions({ kind, booking, experts, onClose, onDone, fail }: { kind: "assign" | "reschedule" | "cancel" | "release" | "type"; booking: Booking; experts: User[]; onClose: () => void; onDone: () => void; fail: (e: unknown) => void }) {
  const [expert, setExpert] = useState(String(booking.assigned_expert ?? ""));
  const [date, setDate] = useState(String(booking.answers.inspection_date ?? ""));
  const [time, setTime] = useState(String(booking.answers.inspection_time ?? ""));
  const [reason, setReason] = useState("");
  const [type, setType] = useState(booking.inspection_type);
  const reasons = useQuery({ queryKey: keys.listItems(kind === "cancel" ? "cancel_reason" : "reschedule_reason"), enabled: kind === "cancel" || kind === "reschedule", queryFn: ({ signal }) => fetchAll<MasterListItem>(`master-lists/${kind === "cancel" ? "cancel_reason" : "reschedule_reason"}/items`, undefined, signal) });
  const types = useInspectionTypes();
  const typeLabel = useTypeLabels();
  const [busy, setBusy] = useState(false);
  const sending = useRef(false);                   // a double click sends once (F-112)
  const go = async (path: string, body: unknown) => {
    if (sending.current) return;
    sending.current = true; setBusy(true);
    try { await api(`bookings/${booking.id}/${path}`, { body }); onDone(); } catch (e) { fail(e); } finally { sending.current = false; setBusy(false); }
  };
  if (kind === "release") return <Confirm title="Force release this booking?" danger confirmLabel="Force release" onCancel={onClose} onConfirm={() => go("force-release", {})}><p>The expert is taken off the booking. If they still have a draft on their phone and submit it later, Ops will see a conflict to resolve.</p></Confirm>;
  const title = { assign: "Assign an expert", reschedule: "Reschedule", cancel: "Cancel this booking", type: "Change inspection type" }[kind];
  const ok = kind === "assign" ? !!expert : kind === "reschedule" ? !!date && !!time && !!reason : kind === "cancel" ? !!reason : !!type && type !== booking.inspection_type;
  const submit = () => kind === "assign" ? go("assign", { expert: Number(expert) }) : kind === "reschedule" ? go("reschedule", { date, time, reason }) : kind === "cancel" ? go("cancel", { reason }) : go("change-type", { inspection_type: type });
  return (
    <Modal title={title} onClose={onClose} actions={<><button onClick={onClose}>Back</button><button className={kind === "cancel" ? "danger" : "primary"} disabled={!ok || busy} onClick={submit}>{title}</button></>}>
      {kind === "assign" && <Field label="Expert"><select aria-label="Expert" value={expert} onChange={(e) => setExpert(e.target.value)}><option value="">Choose…</option>{experts.filter((u) => u.is_active).map((u) => <option key={u.id} value={u.id}>{u.name || u.username}</option>)}</select></Field>}
      {kind === "reschedule" && <><Field label="New date"><input aria-label="New date" type="date" value={date} onChange={(e) => setDate(e.target.value)} /></Field><Field label="New time"><input aria-label="New time" type="time" value={time} onChange={(e) => setTime(e.target.value)} /></Field></>}
      {(kind === "reschedule" || kind === "cancel") && <Field label="Reason"><select aria-label="Reason" value={reason} onChange={(e) => setReason(e.target.value)}><option value="">Choose…</option>{(reasons.data ?? []).filter((r) => !r.archived).map((r) => <option key={r.key} value={r.key}>{r.label}</option>)}</select></Field>}
      {kind === "type" && <Field label="Inspection type"><select aria-label="Inspection type" value={type} onChange={(e) => setType(e.target.value)}>{types.filter((t) => t.available).map((t) => <option key={t.key} value={t.key}>{typeLabel(t.key)}</option>)}</select></Field>}
    </Modal>
  );
}
