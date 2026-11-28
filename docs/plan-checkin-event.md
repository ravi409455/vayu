# Plan: `checkin.completed` integration event (+ "Hide from customer" off for integrations)

Agreed with the owner on 2026-11-28 (grill-me, then three review rounds, the last against
`docs/engineering-standards.md`). Status: **built** (one PR, 2026-11-28).

## Why
When an expert checks in, the company runs things outside Vayu: a Slack message, a message to the
customer ("the expert has arrived"), a location check (their own tool compares the GPS point with the
address) and a CRM / sheet update. Today only `inspection.started` exists: it fires the moment the
check-in reaches the server, before the selfie has uploaded, so it carries no selfie link, and it can
only be set up per inspection form.

## What happens today (unchanged)
- The phone saves the check-in first. Offline, it waits in the phone's outbox and is sent when the
  phone is online again (`Outbox.sendStart`): files are registered, then the start (with the check-in
  answers) is sent, then the file bytes upload.
- The server creates the `Inspection` with the check-in answers (`submissions._start`) and emits
  `inspection.started`. Each file is checked by `media.tasks.verify` and becomes `verified`.
- The check-in is one shared form (type `start`): selfie (photo, required), `checkin_gps`,
  `checkin_time` (both automatic), plus anything an Admin adds.

## The rules agreed with the owner
1. New event `checkin.completed`, "Check-in completed". `inspection.started` stays as it is.
2. It fires when the check-in reaches Vayu (late if the phone was offline) and carries the real
   check-in time.
3. It waits for **every file the check-in names**, up to **5 minutes** after the check-in reached
   Vayu. All verified sooner: it fires then. Else it fires at 5 minutes and lists what is missing.
4. Every check-in fires it (a reassigned or redone booking checks in again), with its number
   (1st, 2nd …) and that check-in's expert.
5. **Set up once, on the Check-in form.** One integration covers PDI, Used car and EV. The
   inspection type and form travel with each event. Inspection forms do not offer this event.
6. An Admin can put in: every booking field, every check-in answer as filled (GPS, time, files as
   links), the inspection type and form, the expert (name, phone), when it reached Vayu, minutes late
   against the booked slot, "phone clock not trusted", the missing files. No distance maths in Vayu.
7. Minutes late use the **phone's** check-in time; the server's time only when the phone clock is not
   trusted. The booking's own "started late" flag (server clock) is unchanged.
8. File links are the usual 7-day links.
9. "Hide from customer" no longer applies to integrations: every event, its photo links and its ZIPs
   get hidden files too. It still covers the report, the report's download links and the Ops ZIP.

## Design

### 1. When it fires (apps/bookings, apps/media)
- `Inspection` + two fields (one migration, `bookings`):
  - `checkin_due_at` DateTime null: set in `_start` to `now + 5 min` when `start_version` is not
    null. Null on every inspection made before this change, so old jobs never fire.
  - `checkin_sent_at` DateTime null: set once, when it fires.
  - Partial index on `checkin_due_at` where `checkin_sent_at IS NULL` (only check-ins waiting).
- New `apps/bookings/checkin.py`:
  - `files(insp) -> set[str]`: ids the check-in answers name
    (`referenced_ids(insp.start_version, insp.answers["start"])`, as `expected_media` does).
  - `maybe_fire(insp_id, now=None)`: one transaction, `select_for_update` on the inspection. Skip if
    `checkin_sent_at` is set, `checkin_due_at` is null, or the booking is gone. Fire when every file
    in `files(insp)` is `verified`, or `now >= checkin_due_at`. Firing: set `checkin_sent_at`, work
    out `missing` (labels of check-in fields whose files are not verified), and emit after commit
    (`core_tasks.after_commit`) `checkin.completed` with `booking`, `booking_id`, `inspection`,
    `missing`. The row lock makes it exactly once when two callers race.
- Callers:
  1. `_start`: after commit, queue `checkin_check.delay(insp_id)` (Celery), which calls
     `maybe_fire` in the worker (a check-in without files fires at once). The Start request does no
     event work itself: only the queue message (about 1 ms).
  2. `media.tasks.verify_asset`, after `verified` and after `check_completion`: if the booking has
     an inspection still waiting (`checkin_sent_at` null, `checkin_due_at` set) whose `files()` hold
     this id, queue `checkin_check.delay(insp_id)`. Never `maybe_fire` inline: an error there would
     stop `verify_asset` after the file is marked verified and skip `check_completion`.
  3. New beat entry `checkin-due` every 60 s: inspections with `checkin_sent_at` null and
     `checkin_due_at <= now` → `maybe_fire`. **This is the 5-minute timer** (no per-inspection
     countdown task: one mechanism, survives worker restarts; fires 5 to 6 minutes after arrival).
- Tasks live in new `apps/bookings/tasks.py`: `checkin_check(insp_id)` and `checkin_due()` (the
  beat). Both `soft_time_limit=30, time_limit=60`, safe to run twice (the row lock and
  `checkin_sent_at` decide), routed to the `notify` queue (`CELERY_TASK_ROUTES`), which the main
  worker already consumes. `checkin_due` handles at most 200 per run (oldest first); the next run
  takes the rest.
- Constants in one place (`checkin.py`): `WAIT = timedelta(minutes=5)`, `BATCH = 200`.
- `unverified_time` moves into `_start` (passed in; today the view sets it after `start()`
  returns, which is after the commit, so a check-in without files would fire before the flag is set).

### 2. Where it goes (apps/integrations)
- `core.events.NAMES`, `webhooks.EVENTS`, `webhooks.PUBLIC`: add `checkin.completed`.
- `webhooks.targets`: `checkin.completed` → active integrations on the **Check-in form**
  (`form__type=start`) with that event; nothing else gets it.
- One table decides which events a form can use (`webhooks.EVENTS_FOR`, by form type:
  booking → `booking.*`; inspection (custom) → every event except `checkin.completed`;
  check-in (start) → `checkin.completed`). `serializers.clean_integration`, `Catalogue` and the
  `events` endpoint (`?form=` returns that form's list) all read it; the old "booking form only
  booking events" `if` goes. Web `eventsFor` uses the endpoint's answer instead of its own list.
- `views`: `Catalogue` (and preview / test) accept the Check-in form. `_booking_for`: for the
  Check-in form, the newest booking with an inspection that has a check-in.
- `webhooks._context`: also keep `missing`.

### 3. What it sends (apps/integrations/values.py, webhooks.py)
- `AVAILABLE["checkin.completed"] = _START | {"checkin"}`. For a Check-in-form integration the
  picker shows: Booking form fields, Check-in fields, Booking details (`job.*`), Check-in details,
  check-in photo links, Event. No inspection, wrap-up, results, PDF or ZIP.
  `values.versions` for the Check-in form: `booking` + `start` (the published Check-in version).
- New `job.form` ("Inspection form": form name and version of that inspection).
- `checkin.late_minutes` = check-in time − booked slot (`timing.slot`); check-in time =
  `client_started_at`, or the server's `started_at` when the clock is untrusted or the phone sent
  none (older app). No slot set: null.
- New group `"checkin": "Check-in details"`: `checkin.number`, `checkin.expert`,
  `checkin.expert_phone`, `checkin.time` (phone, `client_started_at`), `checkin.received_at`
  (server), `checkin.late_minutes`, `checkin.unverified_time`, `checkin.missing_files`.
- `Resolver.inspection()`: when the delivery names an inspection (`d.context["inspection"]`) use
  that one, so a 2nd check-in sends its own answers, expert and photos.
- `Resolver._link("photos.<key>")` for this event: only that inspection's check-in files.
- Standard body for this event: `data = {booking, start}` (each scoped by the integration's
  `fields`) and a `checkin` object (number, expert, time, received_at, late_minutes,
  unverified_time, missing_files, photos `{key: [links]}`), `job` (type, form). Sample body: same
  shape, made-up values.

### 4. "Hide from customer" off for integrations
- `Resolver._link("photos.*")`: drop the `customer_hidden` check.
- `zips.request_zip(..., for_customer=True)`; integrations (`values._link`,
  `webhooks.build_payload`) pass `False`, so hidden keys are not added to `excluded`. New
  `MediaZip.with_hidden` (bool, default False, migration in `media`), part of the cache lookup.
- `media.views.ZipDownload`: the "rebuild without hidden fields" check only when `with_hidden` is
  False. Report ZIP links, report photo blocks, Ops ZIP: unchanged. External API sends no files.

### 5. Web
- `IntegrationEditor`: the form list also offers the Check-in form; the event list comes from
  `integrations/events?form=<id>` (the server's `EVENTS_FOR`), so the Check-in form shows only
  "Check-in completed" and other forms never show it. `eventsFor` in `integrationDef.ts` is removed.
- `integrationDef.ts`: label, picker hint ("Waits up to 5 minutes for the check-in photos; a phone
  that was offline sends it when it is back online, with the real check-in time").
- `FieldEditor` tip for "Hide from customer": remove "partner integrations".

### 6. Docs
- `docs/integrations/webhooks.md`: the event, where it is set up, its body, the 5-minute rule,
  late delivery after offline, once per check-in, which time is which.
- `docs/guides/admin.md`: setting it up on the Check-in form; what "Hide from customer" covers now.
- `REQUIREMENTS.md`: the new event and the narrower "Hide from customer" rule.
- This plan's status line when done.
- `backend/openapi.yaml` and `docs/error-codes.md` regenerated if they change.

### 7. Tests (100% gates on bookings, media, integrations)
- Fires: at once with no files; when the last check-in file is verified; at 5 minutes with
  `missing`; exactly once when verify and the sweep race; never for old inspections
  (`checkin_due_at` null) or a form without check-in; again for a 2nd check-in with number 2 and
  its own expert, answers and photos; not for a deleted booking; offline check-in fires with the
  phone's time and late minutes from it; untrusted clock uses server time; `unverified_time` is set
  before it fires.
- Routing: one Check-in-form integration gets a PDI and a Used-car check-in, each with its own
  `job.type`; inspection-form integrations never get it; the serializer refuses the wrong pairs.
- Picker for the Check-in form; preview picks a booking with a check-in; sample body.
- Hidden: integration photo links and ZIP include hidden files; report, report ZIP links and Ops ZIP
  leave them out; an integration ZIP link is not rebuilt without them; the PR #48 integration tests
  flip.
- Web: form and event lists, label and hint, FieldEditor tip.

### 8. Live inspections must never be affected (owner, 2026-11-28)
- No Android change; experts need no new app.
- Speed: inside the phone's requests the only new work is queueing one task after Start
  (about 1 ms). The check, the webhook rows and the sending run in the background worker (webhooks
  are already sent by a worker today).
- Isolation without hiding errors (standards §2.5: never swallow an error): Start and
  `verify_asset` only queue `checkin_check`; they never run event code, so a bug in it cannot fail
  them. A failing `checkin_check` or `checkin_due` raises as any task does: logged as `exception`
  and reported to Sentry. The check-in stays `checkin_sent_at` null, so the next `checkin_due`
  run tries it again.
- Migration: two nullable columns and one partial index on `bookings_inspection`; nothing is
  rewritten; reversible. Deployed like every release.
- Test: Start and `verify_asset` still succeed (same answer to the phone, `check_completion` still
  runs) when `maybe_fire` raises.

### 9. Logging (standards §2d)
- `checkin.waiting` (info) when the check-in is stored with files to wait for: booking uuid,
  inspection id, file count.
- `checkin.fired` (info): booking uuid, inspection id, check-in number, waited seconds, missing
  count, `timed_out` true/false. Never labels' values, links or answers.
- Delivery success / failure is already logged by `deliver`.

### 10. What leaves the system (standards §2.7)
Through an integration an Admin set up on the Check-in form: booking fields, check-in answers
(GPS point, times), the expert's name and **phone number**, check-in photo links (7 days), and,
after this change, files marked "Hide from customer". All approved by the owner on 2026-11-28.

## Order of work
Each step starts with its failing tests (standards §2.1).
1. Migrations, `checkin.py`, tasks, `_start` / `verify_asset` / beat hooks, `unverified_time` move.
2. Integrations: event, routing, serializer, views, picker, Resolver, bodies; tests.
3. Hide rule change; flipped tests. 4. Web, docs, openapi. 5. Full checks, PR.

## Review
### Round 1 (fixes already in the design above)
- Fire after commit only, never inside the lock. `missing` is fixed at fire time (in the delivery
  context); links are built at send time, so a retry may link a selfie that arrived meanwhile.
- Files Ops upload in place of a missing one count (ids read from the answers at fire time).
- Expert = who checked in (`inspection.expert`), not the current assignee.
- Other event listeners (bell, reports, log) ignore unknown names; a retried start returns the
  existing inspection before anything runs, so nothing fires twice.

### Round 2 (this pass)
1. **Check-in form changes routing, not just the picker.** Today a form must be booking or inspection
   (`serializers`, `Catalogue`, preview). Added: section 2 (targets, serializer pair rules, views,
   preview booking) and section 5 (editor form and event lists).
2. **Race with the clock flag.** No atomic requests: `_start` commits before the view sets
   `unverified_time`, so a check-in without files could fire first. Moved into `_start`.
3. **Simpler timer.** A countdown task per check-in plus a sweep is two mechanisms. The 60 s beat
   alone is the timer (5 to 6 minutes), and it survives a worker restart.
4. **Standard body for this event** had no clear shape; now `data.booking`, `data.start`, `checkin`,
   `job`, each scoped by `fields`.
5. **Preview** on the Check-in form would pick a booking without a check-in; now it picks one with.
6. **Which "phone time".** `checkin.time` = `client_started_at` (the moment the expert pressed
   Start, sent by the phone); the `checkin_time` answer is the same moment stamped into the form and
   also available as a check-in field.

### Round 3 (against `docs/engineering-standards.md`)
1. **§2.5 No silent failure** — the plan said errors in the new code are "logged and swallowed".
   Replaced: Start and `verify_asset` only queue a task; the task fails loudly (Sentry) and the beat
   retries it.
2. **Real bug found with it** — calling `maybe_fire` inline in `verify_asset` could have stopped
   that task after a file was marked verified and skipped `check_completion`, leaving a booking stuck
   in Submitted. Now a queued task, after `check_completion`.
3. **§2a / §2.4 one definition** — "which events a form may use" was an `if` in the serializer and a
   separate list in the web. Now one table (`EVENTS_FOR`) read by the serializer, catalogue and
   events endpoint; the web asks the server.
4. **§2c tasks** — time limits, queue (`notify`), batch size for the beat, index for its filter.
5. **§2b no magic values** — `WAIT` and `BATCH` named once.
6. **§2d logging** — `checkin.waiting` and `checkin.fired` with ids only (section 9).
7. **§2.7 / §2e outgoing data** — the list of what leaves is written down (section 10); the expert's
   phone number is new outgoing personal data, approved by the owner.
8. **§2.10 docs** — `REQUIREMENTS.md` and the status line added.
9. **§2.1 test first** — written into the order of work.
10. **Late minutes** — fallback when the phone sent no start time (older app) and when no slot is set.

### Risks the owner accepted
- Hidden files ("Hide from customer", e.g. payment screenshots) reach every integration; an Admin must
  not put those fields into a message that goes to customers.
- Photo links stop working after 7 days.
- On weak signal the "expert arrived" message can come up to 6 minutes after the check-in reached
  Vayu (waiting for the selfie); an offline check-in arrives later still, with its real time.

### Left out on purpose
- Distance between the GPS point and the address (the owner's tool does it).
- Links to non-photo check-in files (video / document): none exist on the check-in today; add a
  `link.files.<key>` when one is added.
