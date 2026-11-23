import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, type Page } from "../../api/client";
import { STAGE_LABEL, STAGE_TONE, useLabels } from "../../api/labels";
import type { Booking } from "../../api/types";
import { Pill } from "../../ui/kit";

export function Search() {
  const [term, setTerm] = useState("");
  const car = useLabels("car_make_model");
  const q = useQuery({ queryKey: ["search", term], enabled: term.trim().length >= 2, queryFn: () => api<Page<Booking>>("bookings", { query: { search: term.trim() } }) });
  return (
    <>
      <h1>Search</h1>
      <input autoFocus aria-label="Search everything" placeholder="Booking ID, customer name, phone (last 4+ digits), chassis number, car" value={term} onChange={(e) => setTerm(e.target.value)} style={{ maxWidth: 560 }} />
      {term.trim().length >= 2 && (
        <table style={{ marginTop: 14 }}>
          <thead><tr><th>Booking</th><th>Customer</th><th>Car</th><th>Stage</th></tr></thead>
          <tbody>{(q.data?.results ?? []).map((b) => <tr key={b.id}><td><Link to={`/booking/${b.id}`}>{b.booking_id}</Link></td><td>{String(b.answers.customer_name ?? "")}</td><td>{car(b.answers.car_make_model)}</td><td><Pill tone={STAGE_TONE[b.stage]}>{STAGE_LABEL[b.stage]}</Pill></td></tr>)}</tbody>
        </table>
      )}
      {q.data && q.data.results.length === 0 && <p className="muted pad">No match.</p>}
    </>
  );
}
