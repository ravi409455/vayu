// Which booking actions the server allows in which stage (backend bookings/services.py and stages.py).
// One rule for the booking page and the Bookings list, so neither offers what the server refuses.
import type { Booking } from "../api/types";

export type BookingAction = "assign" | "reschedule" | "cancel" | "release" | "type";

export function allowedActions(b: Pick<Booking, "stage">, can: (perm: string) => boolean): Set<BookingAction> {
  const s = b.stage;
  const out = new Set<BookingAction>();
  if (can("bookings.assign") && (s === "draft" || s === "assigned")) out.add("assign");
  if (can("bookings.reschedule") && (s === "draft" || s === "assigned")) out.add("reschedule");
  if (can("bookings.cancel") && (s === "draft" || s === "assigned" || s === "in_progress")) out.add("cancel");
  if (can("bookings.force_release") && s === "in_progress") out.add("release");
  if (can("bookings.edit") && (s === "draft" || s === "assigned")) out.add("type");
  return out;
}
