// The saved Bookings views (Today, Unassigned...) and their counts: the Bookings page and the
// Ops home ask the same questions, so a number and its list always agree.
import { useQuery } from "@tanstack/react-query";
import { api, type Page } from "../api/client";
import { keys } from "../api/keys";
import type { Booking } from "../api/types";
import { addDays, today } from "./format";

export type View = "today" | "unassigned" | "in_progress" | "uploading" | "upcoming" | "completed" | "late" | "quick" | "all";

/** What each saved view asks the server for (on top of the person's own filters). */
export function viewQuery(view: View, now = new Date()): Record<string, string> {
  const t = today(now);
  switch (view) {
    case "today":
      return { date_from: t, date_to: t, order: "schedule" };
    case "unassigned":
      return { stage: "draft", order: "schedule" };
    case "in_progress":
      return { stage: "in_progress", order: "schedule" };
    case "uploading":
      return { stage: "submitted" };
    case "upcoming":
      return { date_from: addDays(t, 1), order: "schedule" };
    case "completed":
      return { stage: "completed" };
    case "late":
      return { timing: "late" }; // Admin / Ops only (the limits are on the Settings page)
    case "quick":
      return { timing: "quick" };
    default:
      return {};
  }
}

/** How many bookings a query matches: the same question the list asks, so a number and its list agree. */
export function useCount(query: Record<string, string>, enabled = true) {
  return useQuery({
    queryKey: keys.bookings("count", query),
    enabled,
    staleTime: 30_000,
    queryFn: ({ signal }) => api<Page<Booking>>("bookings", { query, signal }),
  }).data?.count;
}
