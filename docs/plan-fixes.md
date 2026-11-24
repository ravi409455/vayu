# Plan: fixes from the full review (2026-11-25)

Status: **agreed and finalised (2026-11-25), not started.** Source: [`review-report-2026-11-25.md`](review-report-2026-11-25.md)
(findings **C-01…C-03**, **H-01…H-23** in §3; every finding numbered **F-001…F-252** in §3b; first-pass
**R-01…R-38** in [`review-report-2026-11-24.md`](review-report-2026-11-24.md)).
Comes before the quality plan ([`plan-quality.md`](plan-quality.md)); the big refactors go there (§7).

## 1. How we work
- **Batch 0 first:** root-cause the CI failures (billing is fixed) until all 5 jobs are green on `main`.
  Nothing else merges before that.
- **One branch + PR per batch and layer** (e.g. `fix/b3-web`), tests first: every fix starts with a
  test that fails without it. CI green before merge.
- **Three parallel streams**, each in its own session and git worktree: **backend**, **web**,
  **Android**. A stream works through its batches in order. The lead session coordinates, reviews
  every PR against this plan and merges.
- **Cross-layer contracts land backend-first** (marked ⇄ below): the backend PR merges before the web
  or Android PR that uses it.
- **No scope creep:** an issue found while fixing goes to the lead as a note, not into the PR.
- Each PR updates `REQUIREMENTS.md` / docs when it changes agreed behaviour (REQUIREMENTS edits ride
  with the batch that changes the behaviour, never ahead of it).
- **Re-check first:** each batch starts by re-running the probe or check for each of its findings on
  current `main` (other sessions may have changed the code since the review baseline); a finding that
  no longer reproduces is dropped with a note. H-16 and H-21 were found by reading code only: reproduce
  them before fixing.
- **Tests:** every behaviour fix starts with a test that fails without it. Visual and accessibility
  fixes (contrast, focus, touch targets, layout) are checked with axe in the e2e run and with
  Roborazzi / Playwright screenshots instead.
- Local test data from the review (`REVIEW-…` and `RV-…` bookings, the revoked `REVIEW-key`) is
  deleted in batch 0.

## 2. Decisions taken (2026-11-25)
**Customer report**
- The PDF renders **automatically once**, when the booking completes. After that **nothing re-renders
  by itself**: Ops edits, files Ops add or replace, and anything else only mark the PDF **"out of date"**;
  Ops press **Regenerate** (one new PDF, one `pdf.ready`). The every-few-minutes sweep only retries
  failed or stuck renders. As written in REQUIREMENTS §7.
- Once the retention setting has purged a booking's photos, its **last PDF is kept** and Regenerate is
  disabled with a reason.
- During a two-expert **conflict the customer keeps the old report**; when Ops pick the inspection
  that counts, the PDF renders once automatically. If the **first** completion is already in conflict,
  there is **no report until Ops resolve** it; the first PDF is then made automatically.
- The report's **photo / video ZIP links expire 30 days after the first PDF** of the booking; a PDF
  regenerated after that **leaves those links out** instead of printing dead ones. The **verify page
  (QR) keeps working**.
- Ops ZIP links and webhook PDF / ZIP links stay at **7 days** (REQUIREMENTS §8).

**Permissions and sign-in**
- `api_keys.manage` and `integrations.manage`: **Admin-only, not grantable.**
- Form, PDF template and master list editing: **never for Ops** (not grantable).
- `users.sign_out_devices`: **off by default for Ops**; the Android Ops screen hides the action.
- Sign-in: **one message for every failure**; five wrong tries lock that **username from that address**
  (username + IP pair), not the whole account and not the whole address (many phones in India share
  one mobile-network IP). The per-IP throttle stays.
- Phone notices show **no customer details on the lock screen** (private visibility).
- **Experts don't see Ops' review changes** (ratings, Key Checks) in their activity.

**Submissions and versions**
- The expert never chooses a version: the phone pins the **latest published** version when the lead is
  started. If the Admin publishes a newer one before the offline start reaches the server, the
  inspection **keeps the version the expert filled**. The phone sends its pinned version; the server
  accepts it only if it really was the latest published version at the phone's start time (small
  allowance for clock drift); anything older is refused and Ops are alerted.
- Work an app started **before its version became too old** is accepted (Ops alerted); new starts still
  need the update.
- A **second submit by the same expert** on a lead they already submitted is **refused** ("Already
  submitted; Ops can edit it"); the same request id still returns the first result.

**Media**
- iPhone **HEIC photos** are converted on the server into a **separate JPEG copy** for previews and the
  PDF (new dependency `pillow-heif`); the original stays as sent.
- Videos recorded in the app: **720p at about 2.5 Mbps** (about 19 MB per minute, 1 minute max).

**Built in this round**
- **Unverified time** end to end (phone sends it; server stores it; Ops problem list shows it).
- **APK download page** on the web portal (signed in).
- **API keys can assign, reassign, cancel, reschedule and change type** (REQUIREMENTS §8 "full CRUD").
- **Web portal errors go to Sentry** (no request bodies or customer text; source maps uploaded to
  Sentry, not published). *Owner action:* create the Sentry "web" project and put its DSN in the env file.

**Other**
- Staff web pages must work from **768 px (tablet) up**; customer pages (verify, download) from 375 px.
- `setup_platform` re-run: **only adds what is missing**; `--force` replaces the setup's forms,
  templates and lists after the server name is typed back, by **publishing new versions** (never
  deleting; live inspections keep their pinned versions).
- **Default 1 file per field** everywhere (server, web, Android, builder). All real setup forms set
  their own maximum, so nothing in use changes; the demo seed and any library item without a maximum
  get one set explicitly.
- **Documents and signatures follow the photo retention setting**; cancelled bookings are purged too
  (by cancel date).
- Refactors → quality plan, right after this round. **Android library upgrade = last batch** here.

## 3. Triage rule
- **Fix:** every Critical and High; every Medium and Low whose right answer is clear and that touches
  a file a batch already touches or costs under an hour.
- **Quality plan (§7):** structural work (cycles, registries, typed models, state holders, splitting big
  files, linters, test reorganisation, API documentation).
- **Won't fix (§8):** with a one-line reason each.
- **Before launch (§9):** deployment items.

## 4. Batches
Each line: finding IDs → what to do. Layer streams: **[B]** backend, **[W]** web, **[A]** Android.

### Batch 0 · CI green (lead, ≈½ day)
- H-01 / R-01: re-run CI on `main`; RCA every failing job; fix until backend, web, e2e, android, docker
  are green. Expected: R-02 e2e system-form type label (show the type next to the name), R-03
  flaky `OpsFlowTest` (wait for the list before clicking), plus whatever the RCA finds.
- R-28: e2e uses free default ports (5199 / 8099) so it can't hit the dev stack.
- F-156: `scripts/local.sh` starts the worker with the env file, so pushes work locally.
- Delete the review's local test data.
- **Done:** 5 green jobs on `main`, branch protection requires them.

### Batch 1 · Unblock (lead, ≈½ day, before the streams start)
- H-04 / R-07: fix the 22 mypy errors in the setup code; commit `setup_platform`, `seed_test_data`,
  `freeze_forms`, `apps/core/setup/`, their tests and the `SERVER_KIND` settings.
- H-10 / F-203: add `cryptography` to the runtime dependencies; test that signs a real RS256 token
  without mocks.
- Docs: R-08 / R-37 plan status lines, F-246 stale docs, R-27 README (Android build, env path).
  F-229 (REQUIREMENTS) is updated batch by batch with the behaviour it describes.

### Batch 2 · The customer's report is right [B] (≈1½ days)
- C-01 / F-098: no render and no completion while a conflict is open; the report uses the inspection
  Ops kept (one helper "the counted inspection", used everywhere).
- C-02 / F-001: "Not able to check" counts the real option keys (`not_able_to_check`, `not_checked`);
  test on the frozen PDI / Used Car / EV forms.
- H-05 / F-053 / F-101: a second submit by the same expert on a submitted / completed booking is
  refused ("already submitted; Ops can edit"); same request id still returns the first result.
- H-06 / F-099: customer ZIP holds only files referenced by the counted inspection.
- H-08 / F-102: force-release closes the expert's draft (`released`); a data migration closes any
  extra drafts that exist today, then a DB rule allows one open draft per expert per booking.
- H-18 / F-172: the verify page keeps showing a report that has a ready PDF, even when a later render
  failed (keep `ready` + store the failure separately); "could not be found" only when it truly doesn't
  exist.
- F-219 / decision: every automatic re-render path becomes "mark out of date": the event handler
  (`reports/handlers.py`), Ops-added files (`media/services.rebuild_report`) and the sweep
  (`reports/tasks.sweep_reports`, which keeps only retries of failed / stuck renders). Regenerate
  button renders; `pdf.ready` once per render.
- F-220 / decision: after purge, the last PDF is frozen; Regenerate disabled with a reason.
- R-09 / decision: photo / video ZIP links expire 30 days after the booking's first PDF; a later
  PDF leaves them out once expired.
- Decision: first completion in conflict makes no report until resolved; resolving renders once.
- F-110 / decision: HEIC photos get a separate JPEG copy at verify time (`pillow-heif`), used for
  previews and the PDF; the original is untouched (consistent with F-107).
- F-118: render claims the report before reading data. F-119: report uses the layout of the
  inspection's pinned version. F-109: external API inspection PATCH targets the counted inspection.
- F-107: `verify_asset` safe to run twice, never rewrites the original in place. F-162: the
  synchronous `CHECKSUM_MISMATCH` path can't happen (verification is asynchronous): remove it; web
  and Android read "failed" from upload progress and re-send (see F-115).

### Batch 3 · Uploads never get stuck [W] [A] ⇄ [B] (≈2 days)
**Backend first ⇄**
- H-20 / F-104 / F-105 / decision: `start` takes the phone's pinned `form_version` and keeps it if it
  was the latest published version at the phone's start time (clock allowance); older → refused, Ops
  alerted. The sync payload keeps every form version the phone's open drafts use. **Do this first** in
  the backend stream: Android batch 3 waits for it.
- R-35 / F-131 / decision: work started before the app version became too old, or on a form switched
  off since, is accepted (Ops alerted); new starts still need the update.
- F-122: the expert's per-field limit ignores failed uploads.
- F-244: video uploads are checked to be real videos (type and container).

**Web**
- C-03 / F-135: the queue starts the next file when one finishes; failed files retry with backoff.
- H-15 / F-137: a submitted lead resumes its pending uploads after a reload.
- H-16 / F-138: opening a lead never deletes another device's or tab's unfinished uploads.
- F-072: sign-out stops the queue; F-151: keep the file until the server has checked it;
  F-152: IndexedDB save failures shown; F-143: offline picked photo kept with the right reason;
  F-125: two tabs on one lead: warn instead of silent overwrite; F-235: upload failures reported
  (Sentry, batch 7).

**Android**
- H-21 / F-106: a file the server refuses is shown with the reason and can be removed or replaced;
  the rest of the submission goes on.
- H-22 / F-139 / F-146: drafts of leads that left the list are listed (Uploads) with Send / Discard;
  sign-out message matches Uploads.
- F-115: a checksum failure after "sent" is re-sent; "Free up" never deletes the only copy.
- F-144 / F-017: one bad draft doesn't stop the others; any exception keeps the worker retrying; new
  work doesn't wait behind backoff.
- R-12 / F-087 / F-019: decoding, hashing and fsync off the main thread.
- F-047: no `!!` crash when a draft is pruned while its screen is open.
- R-33: push token save retried through WorkManager. F-117: expired session handled while running;
  single-flight refresh. F-116: clock change after first sync detected.
- F-128 orphan draft files cleaned; F-129 disk full handled; F-155 unconfirmed shot cleaned;
  F-192 picker result survives re-creation; F-154 heartbeat after uploads; F-134 an unreadable draft file is reported, not silently skipped.

### Batch 4 · Ops can trust the screens [B] [W] [A] (≈3 days)
**Backend**
- H-07 / F-100: an edit accepts an unchanged stored value whose only problem is that its option is
  archived or its user inactive; every other check, including rules that link fields, still runs.
- H-09 / F-002 / F-136 / F-205 / F-206: stuck-upload check runs from the scheduler (hourly, using
  `STUCK_UPLOAD_HOURS`), with a test; raises bell, push and webhook, following the existing 24-hour repeat rule.
- H-13 / F-208: Completed and Ops "finish" emit `booking.updated` with the stage change.
- F-207: one `booking.updated` per assignment. F-142: reassigning the same expert sends no second
  "New lead". F-140: a push batch continues after one network error. F-141: earlier user's device on
  the same phone stops getting pushes.
- F-221: type-change alerts can be cleared. F-239: that alert goes to the right type's integrations.
- F-068: expert notices never carry hidden fields' values; F-240: no raw keys in expert notices.
- F-237 / decision: experts don't see Ops review activity. F-238: no overrides on unsubmitted
  inspections. F-241: check-in answers stored. F-149: stuck list forgets abandoned files; expert told on
  force-release. F-150: "submitted" and "completed" as two events in order.
- F-007 (part): fix the broken "between 0 and None" message. F-120: text longer than its column gives a named error.
- F-010 / decision: default 1 file per field on the server.

**Web**
- H-14 / F-158 / F-103 / F-111 / F-153 / F-036: pickers (experts, users) read every page; Today and
  My leads load by date range with "load more"; bell counts come from a count.
- H-17 / F-171 / F-113 / R-13: every query shows its error state; one error boundary with Reload; a
  failed lazy page reloads once.
- H-19 / F-173: dialogs move and trap focus, close on Escape, return focus.
- F-112: actions disabled while sending (no double submit). F-114: quick rating clicks don't conflict
  with yourself. F-011 / F-126: actions shown only in stages the server allows (one shared rule).
- F-177: Ops Today uses the agreed stage words. F-178 contrast; F-179 errors tied to inputs; F-184 error
  toasts stay and are announced; F-185 skip link; F-186 axe fixes; F-187 touch targets; F-190 one
  pattern per meaning; R-14 search focus ring; R-24 page titles; F-032 toast timer.
- F-175 / decision: layouts fixed down to 768 px; customer pages down to 375 px.
- F-012 / F-124 / F-132: "today" and dates in India time. F-010: default 1 file in the builder and forms.
- F-015: PDF designer saves before switching template and only then says "saved".
- F-127: submit errors shown on the right part; "Copy check link" logged only when copying worked.
- F-224: every permission the Roles screen offers Ops has a visible effect on the web, or is removed from the screen.
- F-085 ⇄: Bookings filter debounced; counts use a count endpoint (backend batch 4 adds it first). F-086: upload progress doesn't
  re-render the whole wizard. F-094: signed media links refreshed when stale.
- F-063: `/zip/:token` and `/verify/:token` only call their own endpoints. F-064: `noopener`.
- F-176: ZIP page polls slower and retries; F-189 download page wording; F-183 customer pages title and
  favicon.

**Android**
- H-23 / F-174: camera permission denied for good → "Allow camera in Settings" button.
- F-182: warn when the microphone isn't allowed. F-147: "Discard draft" asks first. F-148: say when
  notices are blocked.
- F-145: tapping a notice opens its lead even after Android closed the app. F-181: Ops keep the open
  booking after process death. F-193: Back on Ops Bookings / Dashboard goes to Today.
- F-194 font scale 1.3; F-195 sign-in keyboard; F-196 cancelled lead says so; F-197 contradicting
  status texts; F-198 locked wizard pages look disabled; F-202 photo grid columns.
- R-15 / F-200 / F-201: "lead" for experts, "booking" for Ops, never "job" (≈35 strings + notification
  channel). F-191 / F-199: colour tokens match web.
- F-075 / decision: notices private on the lock screen. F-223 / decision: Ops sign-out action hidden.
- F-130: reminders computed in IST. F-010: default 1 file.

### Batch 5 · Privacy, security and cost [B] [W] [A] (≈1½ days)
**Backend**
- H-02 / R-04: deleting a booking removes all its files (assets, previews, print copies, PDF, ZIPs)
  after commit; F-121: create and delete are atomic and lock the booking. F-069 / F-081: removed and expired copies (print copies, ZIPs) deleted from R2.
- H-03 / R-05: Sentry without request bodies or local variables; test.
- R-18 / decision: retention covers cancelled bookings and documents / signatures.
- F-054 / decision: `api_keys.manage`, `integrations.manage` not grantable; R-34 / decision: form, PDF
  template, master list editing not grantable; migration removes existing grants. R-23: drop the unused
  `submissions.delete` permission.
- F-055 / decision: one sign-in failure message; lock per username + IP pair.
- F-056: a role change ends existing app tokens. F-057: create with `assigned_expert` needs
  `bookings.assign`. F-058: login CSRF. F-059: bad promotion bundle → 400. F-061: push-token docstring
  vs code: the code is the intended rule (commit `68ef852`), so correct the docstring. F-062 / F-232: audit rows for access-deciding form
  settings and the missing config changes. F-233: generated passwords not printed.
- F-074 / F-211: access logs drop tokens and search terms. F-209: R2 calls with timeouts on the request
  path. F-210: Celery task time limits; health checks R2 and workers. F-084: separate queues for
  uploads, ZIPs, webhooks / pushes, purge.
- F-213: wipe guards check the database name, not only the settings module. F-216: `PUBLIC_BASE_URL`
  required in production.
- F-223 / decision: `users.sign_out_devices` off by default for Ops (data migration).

**Web**
- R-06 / F-072: sign-out clears drafts (localStorage) and queued files (IndexedDB), warning first when
  work is unsent (F-242). R-21: source maps not published. R-20: react-router patch update.

**Android**
- F-073 / F-077: sign-out wipes drafts and every leftover file / pref (after the unsent check).
- R-19: tokens wrapped with an Android Keystore key; the update **moves existing tokens** into the
  new store on first start, so no phone is signed out (an expert offline must stay signed in).
- F-088 / decision: recorded video 720p at about 2.5 Mbps; gallery videos keep the 300 MB limit.
- F-095: Ops offline cache capped.

### Batch 6 · Speed and setup [B] (≈2 days)
- H-12 / F-079: `/sync/jobs` with a fixed number of queries (prefetch), test with `django_assert_max_num_queries`;
  F-089 / F-090 smaller N+1s; R-22: query-count tests on the 5 main lists.
- R-17 / F-091: indexes for booking filters and media queries. F-092: dashboard summary uses
  aggregates. F-093: PDF render caches photos; retries don't sleep in the PDF worker.
- F-080 / F-108: a failed ZIP build is shown as failed and can be retried.
- F-082: `bench_pdf` fails on an empty PDF; F-083: load test covers `/sync/jobs`.
- H-11 / F-204 / decision: `setup_platform` adds only what is missing; `--force` (server name typed
  back) publishes new versions of the setup's forms / templates / lists, never deletes. F-004: production setup no longer imports the demo module.
- F-215 / F-227: runbook for a fresh server (J8).
- F-214: backend CI 30 min → split pytest across processes (`pytest-xdist`) or jobs.

### Batch 7 · New pieces [B] [W] [A] (≈2 days)
- F-222 / decision: **unverified time** ⇄ phone sends it, server stores it, Ops problem list and booking
  page show it.
- F-226 / decision: **APK download page** on the web (signed in, latest release, checksum).
- F-228 / decision: **API keys** can assign, reassign, cancel, reschedule, change type; each action
  is a flag on the key (like `allow_delete`, off by default), audited, webhooks fire; OpenAPI updated.
- R-36 / decision (**blocked until the owner adds the Sentry web DSN**): **web Sentry** (no bodies / customer text, source maps uploaded to Sentry); F-235
  upload failures reported. F-218: Android release mapping uploaded to Sentry.
- F-225 / F-133: gallery photos are not stamped (REQUIREMENTS).

### Batch 8 · Android library upgrade [A] (≈1 day)
- F-217 / F-236: Compose BOM, AGP, Kotlin and the rest to current stable; drop the two unneeded
  dependencies. F-050 / R-26: lint passes (baseline for false positives) and runs in CI. F-169:
  `./gradlew test` passes for the release variant. Screenshot tests and a phone check after the upgrade.

## 5. Order and dependencies
1. Batch 0 → Batch 1 (lead, sequential).
2. Then three streams in parallel, each in its own worktree:
   - **Backend:** B3 contract part first (H-20, R-35) → B2 → rest of B3 → B4 → B5 → B6 → B7.
   - **Web:** B3 → B4 → B5 → B7 (APK page and Sentry wait for the backend B7 endpoints).
   - **Android:** B3 (after backend B3 contract merges) → B4 → B5 → B7 → B8.
3. Files shared across streams (e.g. `shared/rule-vectors`, `openapi.yaml`) change only in the backend
   stream; other streams rebase.
4. **Data migrations, in this order** (all in the backend stream): B2 close extra drafts → B2 one-open-
   draft rule → B2 report status / out-of-date fields → B5 remove grants of now non-grantable
   permissions → B5 `users.sign_out_devices` off for Ops → B5 drop `submissions.delete` → B7 API-key
   action flags → B7 unverified-time field. Each is reversible or has a written reason why not.
5. **Estimate:** about 14 days of work (B0 ½, B1 ½, B2 1½, B3 2, B4 3, B5 1½, B6 2, B7 2, B8 1);
   roughly 6–7 calendar days with three streams, plus whatever the CI root cause needs.

## 6. Tests and done-when
- Every fix has a test that fails without it (unit, Robolectric, Vitest or Playwright as fits); the
  journeys that failed (J2, J6, J8 in report §4) get an end-to-end test each.
- Per batch: CI green, coverage gates hold, the batch's findings re-checked by the lead against the
  report evidence, PR merged.
- **Round done when:** all batches merged; a short re-review of the 3 Critical and 23 High findings
  confirms each is gone (probe scripts in `docs/review-2026-11-25/probes/` re-run); the phone pass
  re-run for H-20–H-23; report §2 scorecard re-scored.

## 7. To the quality plan (structural, after this round)
F-003 import cycle; F-005 split `media/services.py`; F-006 / F-021 / F-022 / F-023 shared helpers and
rules out of views; F-007 (rest) one source of answer messages; F-008 / F-044 stage, status and event
enums; F-009 / F-027 / F-028 / F-029 / F-030 / F-037 / F-038 shared definitions (stage words, media
types, "empty answer", fields list); F-013 split `pages/ops/Booking.tsx`; F-014 query-key factory; F-016
report designer helpers; F-018 Android Ops state holder; F-020 shared answer-rule vectors for Android;
F-024 / F-031 / F-034 / F-039 / F-040 dead code, long functions, long lines; F-025 small hacks; F-026 /
F-033 stale comments; F-035 page imports; F-041 / F-042 / R-25 hot spots; F-043 / F-049 field-type
registry (Q3); F-045 ratings by section key; F-046 / F-048 web linter (Q1); F-051 / F-052 coroutine
and recomposition clean-up; F-159 / F-163 / F-164 / F-168 / F-170 tests for untested risky paths and test
layout; F-160 / F-161 / R-10 error shapes and OpenAPI (Q6); F-165 pagination consistency; F-166 / R-11
generated / typed API models; F-167 request cancellation; F-212 / F-231 / R-16 logging (Q4); F-230 /
F-234 unused packages, dev advisories; F-247 / R-38 history for metrics; F-243 deactivate warning from
the phone's real state; F-123 reversible data migrations.

## 8. Won't fix (reason)
| IDs | Reason |
|---|---|
| F-060 | Header values are plain by decision (integrations plan); now Admin-only (F-054). |
| F-065 | 2.5 MB JSON cap is right. |
| F-066 | Hiding pages the server allows is by design. |
| F-067 | Certificate pinning: rotation risk outweighs the gain for this app. |
| F-070 | 7-day Ops / webhook links are the agreed rule (REQUIREMENTS §8). |
| F-071 | Search terms in staff URLs: staff-only, TLS; tokens and terms leave access logs (F-074). |
| F-076 | Opening a video in an outside player needs a signed link; it expires. |
| F-157 | Force-stop pausing work is Android's rule. |
| F-180 | Verify page leaves out the registration number on purpose (privacy). |
| F-188 | Staff tables on phones: staff web is tablet-and-up by decision. |
| F-245 | Swagger stays Admin-only; integrators get `openapi.yaml`. |
| R-30 | Picture-in-use scan is fine at today's size (noted ceiling). |
| F-097 | A full PDF preview after each pause is what designers expect; it is debounced. |
| F-041, F-042, F-078, F-096, F-248, F-249, F-250, F-252 | Notes / information, no change. |

## 9. Before launch (not this round)
F-251 / R-29 hosting, Caddy, CSP, backups and restore test, monitoring; R-32 restrict the Firebase API
key; staging load test (`perf/`, `loadtest/`).
