# Plan: inspection timing (too quick, started late) and a Settings page

Status: **built and committed** (`73be9c6`). For Admin and Ops only; Experts never see any of it. *(Status corrected 2026-11-25.)*

## What the user asked
"Duration of each inspection is an important aspect." Admin sets time limits on a new Settings page;
Ops and Admin get quick views and numbers for jobs that **finished too quickly** or **started late**.

## Decisions (asked one by one, 2026-11-24)
| # | Question | Answer |
|---|---|---|
| 1 | Minimum duration: one number or per type? | **Per inspection type**, plus a default for any type without its own. |
| 2 | Late-start grace: per type? | **One number for all** (default 15 min, as today). |
| 3 | Who sees / edits Settings? | **Admin edits, Ops views.** |
| 4 | Where do the views show? | **All four**: Today cards, Bookings tabs, Dashboard metrics, a badge on the job page. |
| 5 | Which clock? | **Server times only.** Start = when the server got Start; finish = when it got Submit. |
| 6 | Starting numbers | **PDI 30, Used car 45, EV 40**, default 30. |
| 7 | Also in "Needs you"? | **Yes**, until someone clicks **Mark reviewed**. |

Small calls made while planning (say if any is wrong):
- **Late start and too-quick finish are two separate problems** (changed 2026-11-24 after the
  user's review): each has its own "Mark reviewed" (who and when, in the job's timeline), its own
  Bookings tab, its own Today card and its own "Needs you" group. A job that is both shows both,
  and reviewing one leaves the other open.
- "Needs you" lists unreviewed flagged jobs from the **last 7 days** (older ones are still in the
  Bookings tabs and Dashboard), so switching this on does not dump months of history on Ops.
- Lateness is measured against the **current** booked date + time (after any reschedule).
- A job whose start never reached the server (offline start, only the submit arrived) has **no
  duration and no lateness**: it is never flagged, rather than flagged by mistake.
- Changing a limit re-flags old jobs at once (the stored numbers are raw minutes; the comparison
  uses today's limits).

## Example
DEMO-20, Used car, booked 10:00. Server got Start at 10:40 and Submit at 11:05.
- Late: 40 min > 15 min grace → **Started late (40 min)**.
- Duration: 25 min < 45 min (Used car) → **Too quick (25 min, min 45)**.

## Backend
- `apps/core` model **`Setting`** (key → JSON value) with one key `timing`:
  `{"late_grace_minutes": 15, "min_minutes_default": 30, "min_minutes_by_type": {"pdi": 30, ...}}`.
  No row = the defaults in `apps/core/app_settings.py`. Later settings are new keys, no new tables.
- `GET /api/v1/settings/timing` (`settings.view`), `PUT` (`settings.edit`, Admin only); every change
  writes an audit entry with old → new.
- `Booking.late_minutes` and `Booking.duration_minutes` (int, null): stamped at Start and Submit
  (and on reschedule for late), backfilled by migration, also stamped by `seed_demo`.
- `Booking.late_reviewed_by / _at` and `quick_reviewed_by / _at`;
  `POST bookings/<id>/timing-review` with `{"flag": "late"}` or `{"flag": "quick"}`.
- Bookings list filter `timing=late|quick` (+ `reviewed=0|1`, for that flag), counts follow the same query.
  Refused (403) for anyone without `bookings.review_timing`.
- Booking serializer adds `timing` {late_minutes, duration_minutes, late, quick, min_minutes,
  late_reviewed_by/_at, quick_reviewed_by/_at} only for users with `bookings.review_timing`.
- Dashboard summary: `late`, `quick` counts and % per period, previous period and per expert;
  uses the setting instead of the hard-coded 15 minutes.
- Permissions: `settings.view` (Ops default), `settings.edit` (Admin only),
  `bookings.review_timing` (Ops default) — data migration grants Ops defaults.

## Web
- **Settings page** (`/settings`): late grace, default minimum, one row per active inspection
  type. Read-only for Ops.
- **Today**: cards "Started late" and "Too quick" (today), click opens the Bookings tab.
  Schedule uses the setting for the red "late" mark. Long gaps read as "2 h 5 min", "4 days 22 h".
- **Bookings**: tabs "Started late", "Too quick" with counts; work with existing filters.
- **Dashboard**: "Started late" and "Too quick" headline numbers vs previous period; per-expert columns.
- **Job page**: badge "Started 40 min late" / "Took 25 min (min 45)" and a **Mark reviewed** button per flag.
- **Needs you**: two new groups, "Started late" and "Too quick", for unreviewed jobs (last 7 days).

## Tests
pytest (setting API + perms + audit, stamping, filters, summary), Vitest (labels / needs), one
Playwright check (Admin changes a limit, Today card and Bookings tab follow). OpenAPI and
REQUIREMENTS.md updated.
