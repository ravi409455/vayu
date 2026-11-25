import { useState } from "react";
import { api } from "../../../api/client";
import type { Booking, Inspection, User } from "../../../api/types";
import { useAuth } from "../../../auth";
import { fmtStamp } from "../../../lib/format";
import { useToast } from "../../../ui/kit";

export function ConflictBanner({ booking, insps, experts, onResolved }: { booking: Booking; insps: Inspection[]; experts: User[]; onResolved: () => void }) {
  const { can } = useAuth();
  const { fail, say } = useToast();
  const [keep, setKeep] = useState("");
  const [sending, setSending] = useState(false);
  const who = (id: number) => experts.find((u) => u.id === id)?.name ?? `#${id}`;
  const submitted = insps.filter((i) => i.status === "submitted");
  return (
    <div className="banner bad" role="alert">
      <strong>Two experts submitted this booking.</strong> Choose which inspection counts; the other is kept but set aside.
      {can("bookings.edit") && submitted.length > 1 && (
        <div className="bar" style={{ marginTop: 8, marginBottom: 0 }}>
          <select aria-label="Inspection to keep" value={keep} onChange={(e) => setKeep(e.target.value)} style={{ maxWidth: 320 }}><option value="">Choose…</option>{submitted.map((i) => <option key={i.id} value={i.id}>{who(i.expert)} · {fmtStamp(i.submitted_at)}</option>)}</select>
          <button className="primary" disabled={!keep || sending} onClick={async () => { setSending(true); try { await api(`bookings/${booking.id}/resolve-conflict`, { body: { inspection: keep } }); say("Resolved."); onResolved(); } catch (e) { fail(e); } finally { setSending(false); } }}>Keep this one</button>
        </div>)}
    </div>
  );
}
