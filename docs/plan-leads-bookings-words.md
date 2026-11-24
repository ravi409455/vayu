# Plan: experts say "lead", Ops say "booking" (user-facing words only)

Status: plan agreed, not built. Written 2026-11-24 from a scan of web, Android and server.

## The rule

The word depends on **who reads it**:

| Reader | Today | After |
|---|---|---|
| Expert (web expert pages, Android expert app, expert notifications, server messages experts get) | job / jobs, sometimes booking | **lead / leads** |
| Ops and Admin (web, Android Ops app, Ops notifications, admin screens, messages Ops get) | mostly booking, sometimes job | **booking / bookings** |
| Text both see (shared screens, sign-in, app-wide messages) | job | chosen by the signed-in role, never a mix |

"Job" disappears from everything a person can read.

## Not changing (code and data, invisible to people)

- Code names (`MyJobs.tsx`, `JobStore`, `jobSpan`, CSS `job-row`), API paths (`/sync/jobs`,
  `bookings/...`), database fields, event names, permission keys (`submissions.fill`), stored keys
  (IndexedDB `jobs`, `vayu:job:*`, `jobs-<user>.json`).
- Integration value names `job.booking_id`, `job.type`… are saved inside Admin's integrations and
  in webhooks partners receive: renaming them would break those. Only the **group label** shown in
  the picker changes ("Job" → "Booking").
- The PDF report and the public check page (read by customers): "Booking ID" stays.
- Stage words stay as agreed: Unassigned · Assigned · In progress · Uploading · Completed · Cancelled.

## Where the words are today (scan of 2026-11-24)

### Web, expert-facing → lead
- Menu and title: `Layout.tsx` "My jobs", `ui/TopBar.tsx` "My jobs".
- `pages/expert/MyJobs.tsx`: title "My jobs", search "Find a job" and its placeholder
  "Find: customer, booking ID, car, area", empty states "No jobs right now / New jobs show here…",
  "No job matches…", "No jobs in this view.", row label "Job X", panel "Job details".
- `pages/expert/Job.tsx`: "This job could not be opened.", "This job was cancelled.", "The job could
  not be started.", "The job starts as soon as…", "The job stays yours…", detail row "Booking".
- Web address `/jobs` stays (decision 3).

### Web, Ops/Admin-facing → booking
- `pages/ops/Today.tsx` "Today's jobs".
- `pages/ops/Problems.tsx` "No unassigned jobs today…".
- `pages/ops/Dashboards.tsx` "most jobs first", "No assigned jobs in this range.", column "Jobs".
- `pages/ops/Booking.tsx` "The job is marked Completed…", "Force release this job?", "The expert is
  taken off the job…".
- `pages/admin/Settings.tsx` 4 help texts ("A job that starts…", "completed jobs").
- `pages/admin/FormBuilder.tsx` "their own jobs" (2).
- `ui/AccessEditor.tsx` tip "An expert has the job…".
- `lib/integrationDef.ts` group label "Job", "job facts" (2); `integrations/IntegrationEditor.tsx`
  "no job exists yet", "the latest job".

### Android, expert app → lead
- Bottom tab "Jobs" (`ui/components/Bars.kt`), title "My jobs" and "Back to My jobs" (MyJobs.kt,
  Wizard.kt).
- `ui/expert/MyJobs.kt` ~12 texts (status line, empty states, "Getting your jobs…", "Jobs up to
  date.", "No job matches…", "That job is no longer on your list.", update notices).
- `ui/expert/Wizard.kt` ("This job's form isn't on the phone yet…", refusal texts for
  NOT_ASSIGNED / INVALID_STAGE / APP_TOO_OLD).
- `ui/expert/Uploads.kt` ("…from N jobs", "No job matches…").
- `core/draft/Outbox.kt` CLOSED_TEXT, `ui/UpdateScreen.kt` ("start new jobs").
- Search hints "Booking ID or customer" (MyJobs.kt), "Booking ID, customer or phone" (Uploads.kt).

### Android, Ops app → booking
- `ui/ops/Dashboard.kt` "N jobs", `ui/ops/Parts.kt` "Made when the job is done",
  `ui/ops/Booking.kt` force release / finish texts, "N jobs that day", `ui/ops/Lists.kt` updates
  empty text "Jobs started, submitted…".

### Android, both roles → by role
- Sign-in welcome "Your jobs are waiting" (`ui/Screens.kt`), sign-out warning "This phone still has
  N jobs…" (`ui/AppViewModel.kt`), notification channel name "Jobs and updates" (`Push.kt`, seen in
  the phone's settings; the channel id stays).

### Server → by who gets it
- Expert notifications: "New job: X" (`notify/handlers.py`, twice) → "New lead: X". Ops
  notifications already say booking.
- Messages only experts get (`bookings/submissions.py`): APP_TOO_OLD "start new jobs", NOT_ASSIGNED
  "This job is no longer assigned to you", ALREADY_STARTED "This job is already started",
  INVALID_STAGE "A … job cannot be started" → lead.
- Messages only Ops/Admin get: `bookings/services.py` (force-release, not started, type locked),
  `media/services.py` "Only a job waiting for its files…", `integrations/views.py` "empty for this
  job" → booking.
- Roles page permission text "Force-release a started job" (`accounts/catalog.py`) → booking.
- Stored notifications already sent keep "New job: …" in the bell list: a one-off data migration
  rewrites those titles to "New lead: …", so the list never mixes the two.

The scan above misses text split over several lines; step 1 below catches those.

## Steps (in this order)

1. **Word checker first.** A small script in CI that fails if a user-visible text says "job" (web
   and Android), or "booking" in expert-only files. It reads string literals and JSX text, and
   skips code names, comments and a short allow-list (integration value names `job.*`). Run it now
   to get the complete list, including multi-line texts.
2. **One word source per platform.** Web: `useWords()` returns `{one: "lead" | "booking", many,
   One, Many}` from the signed-in role. Android: the same as `Words.of(role)`. Shared screens use
   it; expert-only and Ops-only screens use their word directly.
3. **Web**: expert pages, then Ops/Admin pages.
4. **Android**: expert app, Ops app, shared texts, notification channel name.
5. **Server**: messages, notifications, permission text, the migration for stored notification
   titles. Phone apps that are not updated yet show the new server texts as they come.
6. **Tests**: update the tests that look for the old words; the checker from step 1 runs in CI from
   now on, so a new "job" anywhere fails the build.
7. **Look at every screen once** as an expert and as Ops (web and phone) and read the words.

## Decisions (settled with the user, 2026-11-24)

1. **The number stays "Booking ID" for experts too** (search hints, PDF, calls with Ops). Experts
   say "lead" for the thing, "Booking ID" for its number. The checker allows "Booking ID".
2. **The expert lead page keeps its detail row label "Booking"** (next to the ID). Allow-listed.
3. **Web address stays `/jobs`** (only on-screen words change). So the `/leads` address in the web
   section above is dropped.
4. **Admin screens say "booking"**, even in sentences about experts.
5. **Words follow the signed-in person** on any screen both can see.
6. **Expert list:** "My leads" (web menu, page title, phone title); phone bottom tab "Leads".
7. **Old "New job: …" notifications are rewritten** to "New lead: …" once, so the bell never mixes.
8. **Order:** web + server first (one change), then the Android apps in their own session from a
   note, as with the report change.
