# Android Ops: reports update by themselves (superseded)

> **Superseded by plan batch 2 (2026-11-25, `docs/plan-fixes.md` §2):** the PDF renders by itself
> only once, at completion. Changes mark it out of date (`out_of_date: true` on
> `GET bookings/{id}/report`), and Ops press Regenerate (`POST bookings/{id}/report/regenerate`,
> needs `reports.view` + `submissions.edit`). `regenerate: {allowed, reason}` says when it can't
> be pressed (conflict open, photos purged, a render running, not completed). `updating` is true
> only while a render runs. The notes below describe the old behaviour.

The web and the server no longer have a "regenerate" step. Bring the Ops app in line.

## What changed on the server

- A completed booking's PDF is made again **by itself** after any change it shows: inspection
  answers, photos/videos/files, Key Checks, ratings, booking details. A failed render is tried
  again by itself (every 30 min). Nobody regenerates by hand.
- `POST bookings/{id}/report/regenerate` is **gone** (404). The `reports.regenerate` permission
  is gone too.
- `GET bookings/{id}/report` no longer has `stale`. It has `updating: true` while a new revision
  is being made after a change.
- Its `url` is now `/api/v1/bookings/{id}/report/download`. Calling it (signed in) logs
  "downloaded" on the booking's Activity, then redirects (302) to the file. `preview_url` (view
  only, not logged) is unchanged.
- New: `POST bookings/{id}/report/shared` with `{"how": "pdf"}` (PDF sent from the phone's share
  sheet) or `{"how": "check_link"}` (check link copied or shared). Logged on Activity (who, when,
  revision).
- `GET problems/reports` lists only failed or stuck renders now (no `stale` field).
- New Activity kinds: `report_downloaded`, `report_shared` (changes: `revision`, `how`). Experts
  never get them.

## What to change in the app (Ops)

1. `ui/ops/Parts.kt` report card (around `remake()` / "Make it again"):
   - remove the "Make it again" button, `remake()`, the `reports.regenerate` check and the
     "Answers changed since this was made." note;
   - show "Updating…" while `updating` is true and refresh the card every few seconds until it is
     false.
2. Download: open the PDF through `report.url` (the `/download` address) with the app's session,
   not a stored signed link, so the download is logged.
3. Share (share sheet with the PDF, or the check link): call `report/shared` with `how` = `pdf`
   or `check_link` when the person shares.
4. `ui/ops/Lists.kt` Needs you (around line 358): drop the "Report out of date" item; a report
   problem is only "Report failed" (it retries by itself).
5. Activity lines: "X downloaded the report", "X shared the report PDF", "X copied the report's
   check link".
6. Tests: update `OpsFlowTest` / `OpsTextTest` cases that use regenerate, `stale` or
   "Make it again".
