# Android: experts say "lead", Ops say "booking" (done: batch 4, fix/b4-android)

The web and the server are done. Rules and decisions: docs/plan-leads-bookings-words.md (read it
first). In short:

- Expert app: **lead / leads**. List title "My leads", bottom tab "Leads". The number stays
  **"Booking ID"** (search hints keep it).
- Ops app: **booking / bookings**.
- Text both can see (sign-in, sign-out warning, notification channel name): the signed-in
  person's word, never a mix.
- "Job" never on screen. Code names (`MyJobs.kt`, `JobStore`, `jobs-<user>.json`), API paths
  (`sync/jobs`) and the notification channel **id** stay.

## What the server already sends (no app change needed for these)

- Expert notifications: "New lead: X" (old ones in the bell were rewritten).
- Expert refusals: "Update the app to start new leads.", "This lead is no longer assigned to
  you.", "This lead is already started.", "A … lead cannot be started.", "Lead not found.",
  "A … lead takes no new files." Ops get the same with "booking".

## Texts to change (scan of 2026-11-24; the checker below finds the rest)

Expert app → lead:
- `ui/components/Bars.kt` bottom tab "Jobs" → "Leads".
- `ui/expert/MyJobs.kt`: "My jobs" (title), status texts ("No signal. Showing the jobs saved…",
  "Jobs up to date.", "Getting your jobs…", "Updating jobs"), "No job matches…", "That job is no
  longer on your list.", "This job's form isn't on the phone yet…", "Update the app to start new
  jobs.", "Update needed to start new jobs. Started jobs can still be finished.", bell empty text
  "New jobs, changed times and cancellations show here."
- `ui/expert/Wizard.kt`: "This job's form isn't on the phone yet…", "Back to My jobs", refusal texts
  for NOT_ASSIGNED / INVALID_STAGE / APP_TOO_OLD.
- `ui/expert/Uploads.kt`: "…from N jobs", "No job matches…".
- `core/draft/Outbox.kt` CLOSED_TEXT "This job is closed on the server…".
- `ui/UpdateScreen.kt` "You need it to start new jobs. A job you already started…".

Ops app → booking:
- `ui/ops/Dashboard.kt` "N jobs", `ui/ops/Parts.kt` "Made when the job is done",
  `ui/ops/Booking.kt` force release ("Force release this job?", "taken off the job", "The job can
  be assigned…"), finish ("The job is marked Completed…"), "N jobs that day",
  `ui/ops/Lists.kt` updates empty text "Jobs started, submitted and completed…".

Both, by role:
- `ui/Screens.kt` welcome "Your jobs are waiting." and the placeholder screen texts.
- `ui/AppViewModel.kt` sign-out warning "This phone still has N jobs and N files…".
- `Push.kt` channel name "Jobs and updates" (id unchanged): name by role, e.g. "Leads and updates"
  / "Bookings and updates".

## Guard

Add a unit test like `web/src/words.test.ts` / `backend/apps/core/tests/test_words.py`: read every
string literal in `app/src/main/java` (not comments, not one-word lowercase code keys) and fail on
"job"/"jobs" as a word, and on "booking" in `ui/expert/` except "Booking ID". Update tests that look
for the old words (`OpsFlowTest`, `OpsTextTest`, expert tests).
