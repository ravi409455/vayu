# Full review: backend, web and Android (2026-11-24/25)

Method: [`docs/review-strategy.md`](review-strategy.md), all six phases. This report replaces the
first-pass report of the evening of 2026-11-24 (its findings R-01 … R-38 are kept and referenced).

## 0. How this review was done

| Phase | What happened |
|---|---|
| 0. Measure | Every tool run on the baseline: backend ruff, mypy, migrations check, pip-audit, full pytest with coverage; web tsc, Vitest, vite build, npm audit, full Playwright; Android unit tests ×2, Roborazzi, Kover, lint, release build + APK scan; OpenAPI regeneration; CI history. Extra measurements by reviewers: query counts on every main endpoint, `bench_pdf`, a 164-screenshot crawl of the web app, upload-queue and form-rule probes, role-rule probes against the API. |
| 1. Map | Code size, biggest and most-changed files per layer, import graph of the backend apps. |
| 2. Journeys | J1, J2, J3, J5, J7 driven end to end against the local API with `REVIEW-` data; J4, J6, J8 traced in code (appendix K). |
| 3. Aspect passes | 11 senior reviewers in parallel, one per slice, each answering every checklist question of `review-strategy.md` §4 for its layer by reading the code: backend quality, backend correctness, backend security & privacy, backend performance / API / ops, web quality, web behaviour & security, web UX & accessibility (in a browser), Android quality, Android behaviour & security, Android on a real phone (OnePlus IV2201, Android 13), product / requirements / journeys. |
| 4. Cross-check | The lead reviewer re-checked **every Critical and High** in the code (and the probes) before accepting it. Result: 3 Critical, 23 High accepted; 2 merged as duplicates found independently by two reviewers; 1 raised to Critical; 2 lowered to Medium. Verdicts are in §3. |
| 5–6. Report and plan | This document, the scorecard (§2), the fix plan (§6) and the full notes of every reviewer (appendices A–K). |

**Baseline.** The latest code on 2026-11-24 23:40 IST: commit `ab75050` (`main`, newest on any
branch) plus all uncommitted work, frozen as git ref `refs/review/baseline` = `ba4b7df`
(`git show refs/review/baseline:<path>`). Everything was reviewed read-only; no repo file was changed.

**Honest limits.** Not done in this round: a screen reader, Lighthouse, Safari / Firefox, tablet width,
a real staging server and load test, blocking R2 / FCM / Sentry on the running stack (judged from code
and library defaults), live Firebase pushes (no credential locally), `setup_platform` on the shared
database (run only on throwaway copies), mutation testing by editing code (judged from which tests
touch each line). Each appendix lists what its reviewer could not check.

**Test data left in the local database** (safe to delete, all named `REVIEW-…`): bookings
`REVIEW-SEC-555c39`, `REVIEW-SEC-b9272f`, `REVIEW-J1B`, `REVIEW-J2` and their media; API key
`REVIEW-key` (revoked); bookings RV-D1, RV-D2, RV-T1, RV-T2 from the phone pass; `expert19`'s test devices were signed out.

## 1. Numbers

| Check | Result |
|---|---|
| Code size (non-test) | backend 17.8 k lines, web 10.1 k, Android 8.8 k |
| Backend tests | **2991 passed**, coverage **94 %**, run time **29 min** (7 first-run errors were another session holding the test database; they pass on re-run) |
| Backend static | ruff clean; mypy clean on committed code, **22 errors in the uncommitted setup code**; migrations in sync; pip-audit: no known vulnerabilities |
| Backend functions | 920 functions, 310 without type hints, 120 uses of `Any`, 20 functions over 60 lines (longest 496) |
| API | 136 routes, every one with a permission class; OpenAPI in sync but **345 generation errors**, ~94 of ~150 operations without a response schema; 131 error codes, 110 undocumented; 4 different error body shapes |
| Phone sync speed | `/sync/jobs`: **225 queries / 0.9 s for 22 jobs**, 1556 queries for 253 jobs, 3596 queries / 4.4 s with `since=` (target 500 ms) |
| PDF | `bench_pdf` reports PASS for an empty PDF; with a shown photo field: 8.2 MB in 11.5 s |
| Cost (estimate) | about 0.2–0.35 GB stored per inspection, mostly video |
| Web | tsc clean (strict, 0 `any`); Vitest **1763 passed**; Playwright **55 passed, 1 failed**; npm audit 2 moderate; main bundle 85 KB gzip; source maps published |
| Web crawl | 164 screenshots (3 roles × every page × 1280 / 375 px × light / dark × states); every staff page scrolls sideways at 375 px |
| Android | 111 unit tests, **1 flaky** (failed 1 of 2 runs); Roborazzi pass; Kover lines 87.2 %, branches 64.4 %; lint 5 errors (false positives) + 48 outdated dependencies; release APK 6.5 MB; 57 `!!`; libraries pinned at Dec-2024 versions; `./gradlew test` (release variant) fails 48 tests |
| Requirements | 104 rules traced to server / web / Android / test (appendix K) |
| Role rules | every role rule in REQUIREMENTS tried through the API (Ops can't delete submissions or edit templates, Experts only their own leads, Admin refused on the app) was refused; H-05 is a gap those rules didn't cover |
| CI | only 2 green runs in the last 100; newest run: android and e2e **failing** |

## 2. Scorecard
Good = nothing above Low · OK = Medium only · Weak = a High · Bad = a Critical · — = not applicable.

| # | Aspect | Backend | Web | Android |
|---|---|---|---|---|
| 1 | Requirements fit | **Weak** (H-13, H-09) | OK | OK |
| 2 | Product and delivery | **Weak** | **Weak** | **Weak** |
| 3 | Product metrics | OK | — | OK |
| 4 | Long-term maintenance | **Weak** | OK | OK |
| 5 | Setup and form content | **Weak** (H-04, H-11) | — | — |
| 6 | Structure and modularity | OK (all 9 apps in one import cycle) | OK | OK (Ops side has no ViewModel) |
| 7 | Reuse and duplication | **Weak** (C-02) | OK | OK |
| 8 | Clean code | OK | OK | OK |
| 9 | Design principles | OK | OK | OK |
| 10 | Comments | Good | Good | Good |
| 11 | Types and static checks | OK | OK | OK |
| 12 | Dependencies | **Weak** (H-10) | Good | OK |
| 13 | Correctness and edge cases | **Bad** (C-01, C-02) | **Weak** (H-14) | **Weak** (H-20) |
| 14 | Error handling | **Weak** (H-05) | **Weak** (H-17) | **Weak** (H-21) |
| 15 | Data integrity | **Weak** (H-02, H-08) | — | **Weak** (H-20) |
| 16 | Offline and sync | — | **Bad** (C-03) | **Weak** (H-20–H-22; the phone pass showed normal offline work arriving intact, the Weak comes from edge cases traced in code) |
| 17 | Notifications and alerts | **Weak** (H-09, H-10) | Good | Good |
| 18 | API contracts | OK | **Weak** (H-14) | Good |
| 19 | Testing | OK | OK | OK |
| 20 | Security | **Weak** (H-05) | Good | Good |
| 21 | Privacy and retention | **Weak** (H-02, H-03) | OK | OK |
| 22 | Performance | **Weak** (H-12) | OK | OK |
| 23 | Running cost | OK | — | OK |
| 24 | Web UX and accessibility | — | **Weak** (H-17–H-19) | — |
| 25 | Android UX and platform | — | — | **Weak** (H-23) |
| 26 | Design and wording | Good | OK | OK |
| 27 | Logging and observability | **Weak** | **Weak** (R-36) | OK |
| 28 | External services | OK | — | OK |
| 29 | Build, CI and dev setup | **Weak** (H-01) | **Weak** | **Weak** |
| 30 | Documentation | OK | OK | OK |
| 31 | Deployment readiness | before launch | before launch | before launch |

**Totals after cross-check: 3 Critical, 23 High, 96 Medium, 107 Low, 20 Notes.** The 23 High are the 19 in §3b plus H-01…H-04 from the first pass. (245 separate findings in §3b after merging 7 duplicates; plus the 38 first-pass findings R-01…R-38, a few of which reappear in §3b as worse variants).
The Criticals and Highs are below; every Medium and Low, with its evidence, is in the appendices.

## 3. Critical and High findings (cross-checked)
Each line says who found it, and how the lead reviewer confirmed it.

### Critical
**C-01 · Backend · A late expert's submit replaces the customer's report before Ops choose.**
When work from the expert a booking was moved away from arrives on a completed booking, the booking
is marked "two experts" but the report is re-rendered from the newest inspection, the one Ops have
not chosen. The customer's verify link and the `pdf.ready` webhook get the wrong findings (probe:
odometer changed to 99999). *Where:* `bookings/submissions.py:279-305`, `reports/handlers.py:21-24`,
`reports/context.py:21-22`. *Confirmed:* the handler re-renders any completed booking and
`latest_inspection` is the newest submitted one. *Fix:* no render or completion while a conflict is
open; the report uses the inspection Ops kept. **S** (appendix B)

**C-02 · Backend · Customer PDFs will show "Not able to check: 0" once the real forms are live.** The report counts answers equal
to `not_checked`; the real PDI, Used Car and EV forms use `not_able_to_check` (55 uses vs 4).
*Where:* `reports/context.py:186-189`, frozen forms in `apps/core/setup/frozen/`. *Confirmed* by grep; the setup's report templates print this count (`apps/core/setup/reports.py`), so PDI and Used Car reports are affected. The frozen forms are not live yet, so no customer has received one. Raised from High because a wrong report would reach the customer. *Fix:* one option key for "not able to
check" (or a list of keys) and a test on the real forms. **S** (appendix A)

**C-03 · Web · The expert's upload queue never starts the 3rd and later files.** The queue starts
two uploads and never starts another when one finishes; a failed file says "Will retry" and is never
retried. Proved in a browser: 5 files, 2 sent, 3 left. With H-15 (no resume after reload) the files
never arrive, the booking stays "Uploading" and no report is made. *Where:*
`web/src/lib/uploadManager.ts:18-27` (`.finally(() => { running--; })` never calls `pump()`).
*Confirmed* in code. *Fix:* call `pump()` in `finally`; retry failed jobs with backoff. **S** (appendix F)

### High
| ID | Layer | Finding | Where | Confirmed by lead | Size |
|---|---|---|---|---|---|
| H-01 | all | CI mostly not running (billing), and red where it runs (= R-01) | `gh run list` | yes | S |
| H-02 | B | Deleting a booking leaves all its files in R2 for ever (= R-04) | `bookings/services.py:250` | yes | S |
| H-03 | B | Backend Sentry sends request bodies and local variables (= R-05) | `settings/base.py:174` | yes, SDK defaults read | S |
| H-04 | B | Production setup code not committed, 22 type errors (= R-07) | `git status` | yes | S |
| H-05 | B | An expert can submit again with a new request id and replace a finished inspection; the report rebuilds from it, without Ops' Key Checks. Found independently by two reviewers (probe: chassis changed to `REVIEW-TAMPERED`) | `submissions.py:236-256` | yes (2 probes) | S |
| H-06 | B | The customer's photo / video ZIP holds every verified file on the booking: the rejected expert's photos and Ops' unattached uploads too | `reports/media_links.py:34-80` | yes | S |
| H-07 | B | Any booking edit fails (`INVALID_ANSWERS`) once its lead owner or expert is deactivated, or its city or car model archived | `bookings/services.py:124`, `forms/fieldtypes.py:281,298` | probe | S |
| H-08 | B | Force-release, then the same expert starts again: two drafts, submit fills the old released one; the new draft is orphaned | `bookings/services.py:209-220`, `submissions.py:241` | probe | S |
| H-09 | B | The stuck-upload alert never fires (no bell, push or webhook); the Needs-you list still shows stuck uploads, which hides it. Found by 4 reviewers | `media/management/commands/flag_stuck_uploads.py`; no beat entry | yes | S |
| H-10 | B | Push notifications can't work in production: RS256 signing needs `cryptography`, missing from the runtime install (only a dev tool pulls it in) | `notify/push.py:10`, `pyproject.toml` | yes (`uv tree --no-dev`) | S |
| H-11 | B | Re-running `setup_platform` reverts the Admin's published form edits, publishes the Admin's open draft, overwrites the shared disclaimer; with a real form change it crashes | `apps/core/setup/build.py` | throwaway-DB run | M |
| H-12 | B | `/sync/jobs`, the phone's main call, is N+1: 225 queries for 22 jobs, 3596 queries / 4.4 s for 253 | `bookings` sync view | measured | S |
| H-13 | B | Booking reaching Completed (or Ops "finish") is not sent as `booking.updated`; REQUIREMENTS §8 says stage changes are | events in `media/services.py` completion | probe | S |
| H-14 | W | Lists stop at the first 50 rows: users, experts in pickers, Today, My leads (an expert with > 50 leads loses the oldest). Found by two reviewers | `web/src/api/hooks.ts:11` | yes | S |
| H-15 | W | A submitted lead never resumes its uploads after a reload; files sit in the browser | `pages/expert/Job.tsx`, `lib/uploader.ts` | browser probe | S |
| H-16 | W | Opening a lead on the web deletes the same expert's unfinished uploads from another device or tab | `lib/uploader.ts` resume code | code only: **reproduce before fixing** | S |
| H-17 | W | A failed load shows as empty: "All clear", "No leads right now", "all assigned", or "Loading…" for ever; Ops act on a false all-clear | many pages, no `isError` handling | 164-shot crawl with forced errors | M |
| H-18 | B/W | The customer verify page says a genuine report "could not be found" after any server error and whenever a later re-render fails | `reports/tasks.py:96` sets `failed` on the same row; `Verify` filters `ready` | yes | S |
| H-19 | W | Dialogs (48 uses): focus not moved or trapped, Escape does nothing, focus lost on close | `web/src/ui/kit.tsx` Modal | yes | S |
| H-20 | A/B | Offline start pins version N on the phone, but the start call doesn't send it, so the server pins the newest; the phone also deletes forms no longer pinned by the server. If Admin publishes while an expert works offline, the work can't be submitted. Found by two reviewers | `core/api/Api.kt:99-105`, `core/sync/JobStore.kt:81-82`, `submissions.py:159` | yes | S |
| H-21 | A | After Submit, one file the server refuses (video > 300 MB, wrong type) blocks the whole submission for ever, with no message, and it can't be removed | `core/draft/Outbox.kt` | code trace: **reproduce before fixing** | S |
| H-22 | A | A draft for a lead that left the list is invisible but counts as unsent: it blocks sign-out on this phone and sign-in on any other | `core/draft`, sign-out guard | code trace | S |

**Lowered in cross-check:** "every assignment sends `booking.updated` twice" (High → Medium: receivers
get duplicates, nothing is lost); one reviewer's separate "stuck alert" entries merged into H-09.

## 3b. Every finding by topic
All findings from the eleven reviewers, grouped by topic, most severe first (Critical and High are explained in §3; the evidence for every line is in the appendix named). Severities are the **final** ones after the cross-check; rows marked *duplicate* are the same problem found by another reviewer and are not counted. Appendix headings keep the reviewers' original ratings.


### Code cleanup and structure (42: 1 Critical, 1 High, 18 Medium, 20 Low, 2 Note)
| ID | Sev. | Layer | Finding | App. |
|---|---|---|---|---|
| F-001 | Critical | Backend | The report's "Not able to check" count expects a key that the real forms do not use | A |
| F-002 | High | Backend | The stuck-upload alert is a command that nothing runs | A |
| F-003 | Medium | Backend | Every app imports every other: one import cycle, and `core` sits on top instead of at the bottom | A |
| F-004 | Medium | Backend | The production setup builds its reports from the demo module | A |
| F-005 | Medium | Backend | media/services.py has six jobs and moves bookings between stages without the stage rules | A |
| F-006 | Medium | Backend | "Which inspection counts" and "who changed this" are copied across apps | A |
| F-007 | Medium | Backend | The server's per-answer messages are thrown away; clients rewrite them, and one message is broken | A |
| F-008 | Medium | Backend | Booking stages, inspection status and media status are bare strings everywhere | A |
| F-009 | Medium | Backend | Booking stage words are written in the server and in many web places | A |
| F-010 | Medium | Web | Default "most files" per field differs between web, Ops view, field editor and server | E |
| F-011 | Medium | Web | Booking page offers Reschedule and Assign in stages the server refuses (and the list page uses a different rule) | E |
| F-012 | Medium | Web | Web rules use the UTC date as `_today`; server uses India time | E |
| F-013 | Medium | Web | `pages/ops/Booking.tsx` is the hot spot: 825 lines, 17 components, stage rules inside | E |
| F-014 | Medium | Web | Query keys are loose strings; invalidations miss or hit nothing | E |
| F-015 | Medium | Web | PDF designer autosave drops the last edit on tab switch and says "All changes saved" while it is not | E |
| F-016 | Medium | Web | Report designer copies its own helpers | E |
| F-017 | Medium | Android | One bad draft stops the outbox for every draft, and the worker gives up for good | H |
| F-018 | Medium | Android | Ops has no state holder: loading, actions and business rules live in composables | H |
| F-019 | Medium | Android | InspectionModel hashes whole files and fsyncs on the main thread | H |
| F-020 | Medium | Android | The server's answer rules are hand-copied with no shared vectors, and already differ | H |
| F-021 | Low | Backend | Smaller copies of the same rule | A |
| F-022 | Low | Backend | A booking error helper is imported by five other modules, and private helpers are used across modules | A |
| F-023 | Low | Backend | Business rules inside views | A |
| F-024 | Low | Backend | Long functions and dead code | A |
| F-025 | Low | Backend | Small hacks | A |
| F-026 | Low | Backend | Stale or wrong comments | A |
| F-027 | Low | Web | Stage words typed five times in the web (plus Android) | E |
| F-028 | Low | Web | "Media types" list in nine places with different members | E |
| F-029 | Low | Web | Three definitions of "empty answer" disagree on blank text | E |
| F-030 | Low | Web | Two hooks build the same "fields of all forms" list | E |
| F-031 | Low | Web | Dead code and test-only exports | E |
| F-032 | Low | Web | A second toast is hidden early by the first toast's timer | E |
| F-033 | Low | Web | Stale or misplaced comments | E |
| F-034 | Low | Web | Very long lines | E |
| F-035 | Low | Web | Pages import components from other pages | E |
| F-036 | Low | Web | Page size 50 hard-coded in the client | E |
| F-037 | Low | Android | Two `answered()` functions with different rules | H |
| F-038 | Low | Android | Small helpers copied many times | H |
| F-039 | Low | Android | An extra request just to say "Updated." | H |
| F-040 | Low | Android | Misplaced and stacked doc comments | H |
| F-041 | Note | Backend | Hot spots (non-test .py, changes from `git log --name-only`) | A |
| F-042 | Note | Android | Hot spots | H |

### Design principles (10: 5 Medium, 5 Low)
| ID | Sev. | Layer | Finding | App. |
|---|---|---|---|---|
| F-043 | Medium | Backend | Field types handled by `if` chains spread over many modules | A |
| F-044 | Medium | Backend | Event names are bare strings with no list of what exists | A |
| F-045 | Medium | Backend | Rating categories point at section titles, not section keys | A |
| F-046 | Medium | Web | No linter runs, yet 21 comments switch a lint rule off | E |
| F-047 | Medium | Android | `drafts.get(id)!!` crashes the app when a draft is pruned while its Submitted screen is open | H |
| F-048 | Low | Backend | Escape hatches and lint gaps | A |
| F-049 | Low | Web | Field types handled by four separate switches | E |
| F-050 | Low | Android | `lintDebug` fails with 5 errors, so lint can't simply be added to CI (worse variant of R-26) | H |
| F-051 | Low | Android | `runCatching` around suspend calls, and other unsafe casts | H |
| F-052 | Low | Android | Unstable Ops parameters and repeated parsing make recomposition and CPU cost high | H |

### Security (15: 1 High, 2 Medium, 9 Low, 3 Note)
| ID | Sev. | Layer | Finding | App. |
|---|---|---|---|---|
| F-053 | High | Backend | An expert can submit again on their own submitted or completed booking and replace the inspection the report uses | C |
| F-054 | Medium | Backend | Two grantable permissions are in effect Admin access: `api_keys.manage` and `integrations.manage` | C |
| F-055 | Medium | Backend | Anyone can lock any account, and the login answer says which usernames exist or are disabled | C |
| F-056 | Low | Backend | Access tokens outlive a promotion to Admin: "Admins are refused on the app" holds only at sign-in | C |
| F-057 | Low | Backend | Creating a booking with `assigned_expert` skips the `bookings.assign` permission | C |
| F-058 | Low | Backend | Login is not CSRF-protected (login CSRF) | C |
| F-059 | Low | Backend | A malformed promotion bundle gives a 500 instead of a 400 | C |
| F-060 | Low | Backend | Webhook header secrets are returned in clear to every holder of integrations.manage | C |
| F-061 | Low | Backend | The push-token docstring promises "only the device that sent it last"; the code pushes to every device holding the token | C |
| F-062 | Low | Backend | Form settings that decide who sees submissions are changed without an audit row | C |
| F-063 | Low | Web | `/zip/:token` and `/verify/:token` paths can be pointed at any same-origin API GET, which is then polled every 1.5 s | F |
| F-064 | Low | Web | "Open the old file" opens a window without `noopener` | F |
| F-065 | Note | Backend | JSON bodies are capped at 2.5 MB (`DATA_UPLOAD_MAX_MEMORY_SIZE`) | C |
| F-066 | Note | Web | The UI hides pages the server allows (by design) | F |
| F-067 | Note | Android | No certificate pinning | I |

### Privacy and data retention (11: 6 Medium, 4 Low, 1 Note)
| ID | Sev. | Layer | Finding | App. |
|---|---|---|---|---|
| F-068 | Medium | Backend | Changed values of fields hidden from experts go into the expert's notification | C |
| F-069 | Medium | Backend | Copies of customer files stay in R2 after removal and after the retention purge | C |
| F-070 | Medium | Backend | Ops ZIP links and webhook ZIP/PDF links give anyone 7 days of access to all customer photos, signatures and documents | C |
| F-071 | Medium | Web | Customer phone numbers and names go into URLs and API query strings | F |
| F-072 | Medium | Web | R-06 variant: after sign-out, the upload queue keeps running in the tab and retries under the next person | F |
| F-073 | Medium | Android | After sign-out, the person's drafts (customer answers, stamped photos) stay on the phone | I |
| F-074 | Low | Backend | Gunicorn access logs keep customer search terms and bearer tokens from URLs | C |
| F-075 | Low | Android | Reminder and problem notices show customer name and address on the lock screen | I |
| F-076 | Low | Android | Ops "Open" hands a signed storage URL to an outside app | I |
| F-077 | Low | Android | Leftovers not wiped at sign-out | I |
| F-078 | Note | Backend | Where customer personal data is written | C |

### Performance and cost (19: 1 High, 9 Medium, 7 Low, 2 Note)
| ID | Sev. | Layer | Finding | App. |
|---|---|---|---|---|
| F-079 | High | Backend | `/sync/jobs` (the expert phone's main call) runs queries per job; 0.9 s for 22 jobs on the local data | D |
| F-080 | Medium | Backend | A ZIP whose build fails or whose worker is restarted stays "Preparing…" for 7 days | D |
| F-081 | Medium | Backend | Expired ZIPs are never deleted from R2, and each new request after 7 days stores another full copy | D |
| F-082 | Medium | Backend | `bench_pdf` reports PASS for an empty PDF; the documented benchmark can't be trusted | D |
| F-083 | Medium | Backend | The load test skips the expert phone's real path | D |
| F-084 | Medium | Backend | One Celery queue (4 slots) serves upload checks, ZIP builds, webhooks, pushes and purge; ZIP builds have no limit; tasks are lost on restart | D |
| F-085 | Medium | Web | 10 API requests per keystroke in the Bookings filter, and each count fetches 50 full bookings | F |
| F-086 | Medium | Web | Every upload progress event re-renders the whole wizard (about 38 full-form rule evaluations) | F |
| F-087 | Medium | Android | Disk IO and hashing on the main thread in the inspection flow | I |
| F-088 | Medium | Android | Videos are not compressed; gallery videos go up as picked | I |
| F-089 | Low | Backend | Smaller N+1s on admin lists and the external API | D |
| F-090 | Low | Backend | Inspection access levels are recomputed up to 4× per inspection | D |
| F-091 | Low | Backend | No index for the upload queries that scan all media | D |
| F-092 | Low | Backend | The dashboard summary loads full booking rows for an unbounded date range | D |
| F-093 | Low | Backend | Every PDF render re-reads every photo from R2; failed attempts sleep inside the only PDF worker | D |
| F-094 | Low | Web | Signed media links go stale on pages left open over an hour | F |
| F-095 | Low | Android | The Ops offline cache grows without limit while signed in | I |
| F-096 | Note | Backend | Estimate per inspection and per month (R2 storage; egress is free on R2) | D |
| F-097 | Note | Web | The PDF designer renders a full preview after each pause | F |

### Correctness and error handling (34: 1 Critical, 6 High, 11 Medium, 14 Low, 2 Note; 3 duplicates marked)
| ID | Sev. | Layer | Finding | App. |
|---|---|---|---|---|
| F-098 | Critical | Backend | Late expert's submit silently replaces the customer's report before Ops resolve the conflict | B |
| F-099 | High | Backend | Customer photo/video ZIP holds every verified file on the booking, not the counted inspection's | B |
| F-100 | High | Backend | Any booking edit fails once its lead owner or expert leaves, or its city or car model is archived | B |
| F-101 | High | Backend | A second submit with a new request id makes a second counted inspection with no conflict *(duplicate of F-053)* | B |
| F-102 | High | Backend | Force-release then re-start by the same expert leaves two drafts; submit fills the old, released one | B |
| F-103 | High | Web | "My leads" shows only the 50 most recently created bookings | F |
| F-104 | High | Android | The phone deletes the forms its own drafts are pinned to, so the work can never be sent | I |
| F-105 | High | Android | Start ignores the version the phone pinned, so answers are checked against a different form *(duplicate of F-104)* | I |
| F-106 | High | Android | After Submit, one refused file blocks the whole submission forever, silently, and the file cannot be removed | I |
| F-107 | Medium | Backend | verify_asset is not safe to run twice and rewrites the original in place | B |
| F-108 | Medium | Backend | A ZIP build that fails stays "Preparing…" for 7 days | B |
| F-109 | Medium | Backend | External API inspection PATCH writes to whatever inspection is newest (draft or superseded), last-write-wins | B |
| F-110 | Medium | Backend | HEIC photos are accepted but never appear in the customer PDF | B |
| F-111 | Medium | Web | Experts, users and today's schedule also stop at 50 | F |
| F-112 | Medium | Web | Double-click sends Ops actions twice (assign, reschedule, cancel, delete, conflict, review) | F |
| F-113 | Medium | Web | A missing booking or a server error shows "Loading…" forever, and Today says "all assigned" when the API is down | F |
| F-114 | Medium | Web | Quick clicks on ratings, Overall or Key Checks get "changed by someone" against yourself | F |
| F-115 | Medium | Android | A server-side checksum failure after the phone marked the file "sent" is never re-sent; "Free up" can delete the only copy | I |
| F-116 | Medium | Android | Time marked "verified" forever after the first sync; a later phone-clock change goes undetected | I |
| F-117 | Medium | Android | An expired session is not handled while the app runs; refresh has no single-flight and shares the 20/min login throttle | I |
| F-118 | Low | Backend | Render reads booking and inspection before claiming, so an edit in between can be lost | B |
| F-119 | Low | Backend | Report uses the newest PDF layout for inspections pinned to older form versions | B |
| F-120 | Low | Backend | Text limits larger than columns give an unnamed 400 | B |
| F-121 | Low | Backend | Booking create and delete are not atomic; delete emits before deleting and does not lock | B |
| F-122 | Low | Backend | Expert's per-field limit counts failed uploads | B |
| F-123 | Low | Backend | Data migrations cannot be reversed and one imports live app code | B |
| F-124 | Low | Web | The web works out `_today` in UTC; the server uses IST | F |
| F-125 | Low | Web | Two tabs on one lead silently overwrite each other's draft | F |
| F-126 | Low | Web | The booking page offers actions the server always refuses | F |
| F-127 | Low | Web | Submit errors are spread over all parts by key; "Copy check link" is logged even when copying fails | F |
| F-128 | Low | Android | Orphan files in the drafts folder are never cleaned | I |
| F-129 | Low | Android | Disk full crashes the app while typing | I |
| F-130 | Low | Android | Reminders use the phone's time zone for IST booking times | I |
| F-131 | Low | Android | An offline-started job on an app below the minimum version can never be sent until the app is updated | I |
| F-132 | Note | Web | Dates use the browser's time zone | F |
| F-133 | Note | Android | Gallery photos are stamped, but the requirement says "gallery photos are not stamped" *(duplicate of F-225)* | I |
| F-134 | Note | Android | A draft file that cannot be parsed is silently ignored | I |

### Offline, sync and notifications (22: 1 Critical, 3 High, 9 Medium, 8 Low, 1 Note; 1 duplicate marked)
| ID | Sev. | Layer | Finding | App. |
|---|---|---|---|---|
| F-135 | Critical | Web | Upload queue never starts the 3rd and later files | F |
| F-136 | High | Backend | "Photos stuck" alerts are never raised *(duplicate of F-002)* | B |
| F-137 | High | Web | A submitted lead never resumes its uploads after a reload | F |
| F-138 | High | Web | Opening a lead on the web deletes another device's unfinished uploads | F |
| F-139 | High | Android | A draft for a job that has left the list is invisible, and it blocks sign-out and a new phone forever | I |
| F-140 | Medium | Backend | Push batch aborts on the first network error, with no retry | B |
| F-141 | Medium | Backend | A promised push rule is not built: earlier user's device on the same phone still gets pushes | B |
| F-142 | Medium | Backend | Assigning the same expert again sends a second "New lead" | B |
| F-143 | Medium | Web | Offline, a picked photo is refused with a wrong reason and not kept | F |
| F-144 | Medium | Android | Uploads can stall for hours: new work waits behind a worker in exponential backoff; any non-API exception ends the queue | I |
| F-145 | Medium | Android | Tapping a notice after Android closed the app opens the old screen, not the lead | J |
| F-146 | Medium | Android | Sign-out blocked by drafts that can never be sent; the message contradicts Uploads | J |
| F-147 | Medium | Android | "Discard draft" on the lead list and lead page deletes the work in one tap | J |
| F-148 | Medium | Android | When notices are blocked, nothing tells the expert or Ops | J |
| F-149 | Low | Backend | Stuck-upload list never forgets failed or abandoned files; no notice to the expert on force-release | B |
| F-150 | Low | Backend | "submitted" and "completed" arrive together | B |
| F-151 | Low | Web | The browser forgets a file before the server has checked its checksum | F |
| F-152 | Low | Web | IndexedDB save failures are swallowed | F |
| F-153 | Low | Web | Bell counts stop at 50; web experts get no new-lead signal | F |
| F-154 | Low | Android | The heartbeat is not sent after uploads finish | I |
| F-155 | Low | Android | A shot left unconfirmed when the app dies stays on the phone forever | J |
| F-156 | Low | Android | The local stack never sends pushes | J |
| F-157 | Note | Android | Force-stop pauses all sending until the app is opened | J |

### API contracts and testing (12: 6 Medium, 6 Low; 1 duplicate marked)
| ID | Sev. | Layer | Finding | App. |
|---|---|---|---|---|
| F-158 | High | Web | Lists silently stop at the first 50 rows (users, experts, today's schedule, my leads) *(duplicate of F-103)* | E |
| F-159 | Medium | Backend | The riskiest flows have no test, and every bug above was found in an untested path | B |
| F-160 | Medium | Backend | Four different error shapes; 110 of 131 error codes documented nowhere; no 4xx in OpenAPI | D |
| F-161 | Medium | Backend | The OpenAPI file and the "no breaking API changes" gate cover under half the responses (worse variant of R-10) | D |
| F-162 | Medium | Backend | `CHECKSUM_MISMATCH` on upload completion can never happen in production | D |
| F-163 | Medium | Web | The upload pipeline and the expert Job page have no unit tests | E |
| F-164 | Medium | Android | Background workers and draft deletion have no tests and sit outside the coverage gate | H |
| F-165 | Low | Backend | Pagination is inconsistent and `page_size` is ignored | D |
| F-166 | Low | Web | `types.ts` is hand-written and has drifted from the serializers | E |
| F-167 | Low | Web | `api()` ignores the cancel signal TanStack Query passes | E |
| F-168 | Low | Web | Test files are grouped by session, not by subject; e2e gaps | E |
| F-169 | Low | Android | `./gradlew test` (and `koverLog`) fails 48 tests in the release variant | H |
| F-170 | Low | Android | ApiContractTest only checks Api.kt, and `getValue()` throws outside ApiError | H |

### UX, accessibility and wording (32: 4 High, 8 Medium, 16 Low, 4 Note)
| ID | Sev. | Layer | Finding | App. |
|---|---|---|---|---|
| F-171 | High | Web | A failed load shows as empty, "All clear" or a "Loading…" that never ends | G |
| F-172 | High | Web | The buyer is told a genuine report "could not be found" | G |
| F-173 | High | Web | Dialogs: focus not moved or trapped, Escape does nothing, focus lost on close | G |
| F-174 | High | Android | One camera denial blocks the check-in; no way back from the app | J |
| F-175 | Medium | Web | At phone width (375 px) every staff page scrolls sideways; some content breaks | G |
| F-176 | Medium | Web | Photo / video ZIP page gives up for good on the first error and polls fast enough to hit the limit | G |
| F-177 | Medium | Web | Ops Today breaks the agreed stage words | G |
| F-178 | Medium | Web | Text below contrast minimum (both themes) | G |
| F-179 | Medium | Web | Form errors and required state not tied to the inputs | G |
| F-180 | Medium | Web | The verify page cannot tell the buyer it is about THIS car or THIS copy | G |
| F-181 | Medium | Android | Ops lose the open booking when Android closes the app in the background | J |
| F-182 | Medium | Android | Videos are recorded without sound, with no warning, when the microphone is not allowed | J |
| F-183 | Low | Web | Customer link previews and tab show "Vayu", no favicon | G |
| F-184 | Low | Web | Error toasts vanish after 4 s and are announced politely | G |
| F-185 | Low | Web | No skip link; long tab path before the content | G |
| F-186 | Low | Web | axe findings: small ARIA and structure errors | G |
| F-187 | Low | Web | Touch targets under 24 px at phone width | G |
| F-188 | Low | Web | Tables on a phone hide the important columns | G |
| F-189 | Low | Web | Small wording and link issues on the download page | G |
| F-190 | Low | Web | Mixed patterns and colours for the same meaning | G |
| F-191 | Low | Android | Two colour tokens differ from web | H |
| F-192 | Low | Android | A gallery or file pick is dropped if the app is re-created while the picker is open | J |
| F-193 | Low | Android | Back on Ops Bookings or Dashboard leaves the app | J |
| F-194 | Low | Android | Font size 1.3: dates cut off and bell counts cover the bell | J |
| F-195 | Low | Android | Sign-in: the keyboard hides the password and Sign in, and its key says Done | J |
| F-196 | Low | Android | A cancelled lead's page does not say it is cancelled | J |
| F-197 | Low | Android | Status texts that contradict themselves | J |
| F-198 | Low | Android | Locked wizard pages look tappable and do nothing | J |
| F-199 | Note | Web | Web and Android colour tokens have drifted | G |
| F-200 | Note | Android | "job" wording (R-15): exact count for the fix | H |
| F-201 | Note | Android | Off-rule "job" words seen on the phone (known R-15; listed for the fix) | J |
| F-202 | Note | Android | Ops photo grid uses 3 columns on a wide phone | J |

### Logging, external services, CI, setup, docs (48: 3 High, 22 Medium, 18 Low, 5 Note; 2 duplicates marked)
| ID | Sev. | Layer | Finding | App. |
|---|---|---|---|---|
| F-203 | High | Backend | Push notifications cannot work in production: `cryptography` is missing from the production install | A |
| F-204 | High | Backend | Re-running `setup_platform` reverts Admin's live form edits, publishes Admin's draft and overwrites the shared disclaimer; with a real spec change it crashes | D |
| F-205 | High | Backend | The "stuck upload" alert is never sent: the only code that emits it is a command nothing schedules *(duplicate of F-002)* | D |
| F-206 | High | All | Stuck-upload alerts never fire: no webhook, no Ops bell/push *(duplicate of F-002)* | K |
| F-207 | Medium | All | Every assignment sends `booking.updated` twice to integrations | K |
| F-208 | High | All | "Completed" (and Ops "finish") is never sent as a `booking.updated` stage change | K |
| F-209 | Medium | Backend | R2 calls have no timeouts on the web request path, so a slow R2 can take the whole API down | C |
| F-210 | Medium | Backend | Celery tasks that read R2 have no time limit, and health does not check R2 or the workers | C |
| F-211 | Medium | Backend | Access logs hold customer search terms and the report/ZIP bearer tokens | D |
| F-212 | Medium | Backend | A booking's story can't be followed in the logs: task logs carry no request id or booking, and key failures log nothing | D |
| F-213 | Medium | Backend | The wipe guards trust the settings module, not the database they are wiping | D |
| F-214 | Medium | Backend | Backend CI takes about 30 minutes before the coverage gates even start | D |
| F-215 | Medium | Backend | A fresh server setup (J8) is not documented, and the README's env instructions don't work | D |
| F-216 | Medium | Backend | `PUBLIC_BASE_URL` falls back to `http://localhost:8000` in production | D |
| F-217 | Medium | Android | The whole Android stack is about 2 years behind | H |
| F-218 | Medium | Android | Release crash reports have unreadable stack traces | I |
| F-219 | Medium | All | Reports regenerate on every change, and each revision fires `pdf.ready` to customer-facing integrations | K |
| F-220 | Medium | All | Media retention + auto-regenerate silently strips photos from a customer's PDF | K |
| F-221 | Medium | All | Rejected type-change alerts can never be cleared from Needs you | K |
| F-222 | Medium | All | "Unverified time" is half-built: the phone computes it, nobody receives it | K |
| F-223 | Medium | All | Ops can't sign a person's phone out on the web | K |
| F-224 | Medium | All | The role matrix promises things the web never shows (Ops) | K |
| F-225 | Medium | All | Gallery photos get the camera stamp, with the pick time and current GPS | K |
| F-226 | Medium | All | No APK download page on the web | K |
| F-227 | Medium | All | No runbook for a fresh server (J8) | K |
| F-228 | Medium | All | API keys can't assign, reassign, cancel, reschedule or change type | K |
| F-229 | Medium | All | REQUIREMENTS.md not updated for six agreed changes | K |
| F-230 | Low | Backend | Unused and undeclared packages | A |
| F-231 | Low | Backend | Log noise | D |
| F-232 | Low | Backend | Audit log gaps for configuration changes | D |
| F-233 | Low | Backend | Generated passwords are printed to stdout | D |
| F-234 | Low | Web | Dev advisories and major versions behind | E |
| F-235 | Low | Web | Upload failures are never reported | F |
| F-236 | Low | Android | Two dependencies not needed | H |
| F-237 | Low | All | Experts see Ops review activity (ratings and Key Check changes) | K |
| F-238 | Low | All | Ops can set rating overrides on an unsubmitted inspection | K |
| F-239 | Low | All | Type-change-rejected alert goes to integrations of the rejected type | K |
| F-240 | Low | All | Expert notifications show raw keys | K |
| F-241 | Low | All | Check-in answers are validated at Start but not kept | K |
| F-242 | Low | All | Web sign-out is not blocked while work is unsent | K |
| F-243 | Low | All | Deactivate warning is generic, not based on the phone's real state | K |
| F-244 | Low | All | Video uploads are not checked to be videos | K |
| F-245 | Low | All | Swagger is Admin-only, so API integrators can't read it | K |
| F-246 | Low | All | Stale or wrong docs | K |
| F-247 | Low | All | History needed for metrics is overwritten | K |
| F-248 | Note | Backend | Versions that will need a planned upgrade | A |
| F-249 | Note | Backend | Behaviour per service | C |
| F-250 | Note | Backend | Fidelity of the mapping to Clappia (script comparison) | D |
| F-251 | Note | Backend | Known gaps seen in `infra/` (before launch; Caddy, backups and CSP are already known) | D |
| F-252 | Note | All | Notification rules built slightly differently from android-requirements | K |

## 4. Journeys (summary; full step tables in appendix K)
| ID | Journey | Result |
|---|---|---|
| J1 | Booking → assign → inspection → upload → submit → PDF → webhook → customer link | Pass, except: double `booking.updated` on assign, no event on Completed (H-13), C-02 in the PDF |
| J2 | Same with trouble (offline, reload, app killed, job moved) | **Fail**: C-01, C-03, H-15, H-16, H-20–H-22 |
| J3 | Ops review, edit, regenerate | Pass with Mediums: every edit re-renders and fires `pdf.ready` to customer-facing integrations |
| J4 | Admin form change and publish | Code: pass; e2e 1 failure (R-02); offline experts hit H-20 |
| J5 | Sign-in and devices | Pass; Ops can't sign a phone out on the web; web sign-out keeps drafts (R-06) |
| J6 | Notices and pushes | **Fail in production**: H-10, H-09 |
| J7 | Integrations and API | Pass with Mediums (duplicates, no completion event, API keys can't assign or cancel) |
| J8 | Fresh setup and self-update | **Fail**: H-11, H-04; no runbook; no APK download page on the web |

## 5. Android on a real phone
Tested on a OnePlus IV2201 (Android 13) over adb against the local server; full notes and 70
screenshots in appendix J and [`review-2026-11-25/phone/`](review-2026-11-25/phone/).
Scores: 25 Android UX **Weak**, 16 Offline (device) OK, 17 Notifications OK, 26 Wording OK.

**What held up well:** answers and photos taken in airplane mode, and a full submit done offline, all
reached the server exactly as entered; unsent photos went up after Android killed the app, without
opening it; under 1 % janky frames scrolling the Ops photo grid and My leads; cold start 1.1–1.3 s.

**H-23 · Android · One "Don't allow" on the camera makes check-in impossible.** Android never asks
again and the app has no button to open its settings (the only settings link in the app is for
location, `ui/expert/Fields.kt:354`). The expert can't take the check-in selfie, so can't start the
lead. *Confirmed* by grep. *Fix:* when the permission is permanently denied, show "Allow camera in
Settings" with `ACTION_APPLICATION_DETAILS_SETTINGS` (reuse the location code). **S**

**Device Mediums:** tapping a notice after Android closed the app opens the last screen, not the new
lead (`MainActivity.kt:50-54`, reproduced twice); sign-out blocked by "2 jobs not sent" while Uploads
says "Everything is sent": a cancelled lead's draft is never cleared (confirms H-22 on a device); Ops
lose the open booking after Android closes the app; "Discard draft" deletes work in one tap with no
question; no hint in the app when notifications are blocked; videos record silently, with no warning,
when the microphone isn't allowed.

**Setup notes from the device pass:** `scripts/local.sh` starts the Celery worker without the env file,
so pushes are never sent on the local stack (worked around by hand); USB adb kept dropping, Wi-Fi adb
used instead. Not tested: reboot, battery saver, a small phone, two phones swapping users, gallery
picking (it would upload the owner's personal photos), self-update (needs a release row every phone
would see). Test bookings made: RV-D1 (left "in progress"), RV-D2 (cancelled), RV-T1, RV-T2, all with
`REVIEW-` customer names.

## 6. Fix plan
Order by harm, grouped so each batch touches the same files.

1. **Unblock (½ day):** H-01 CI green (billing, R-02, R-03), H-04 commit the setup, H-10 add
   `cryptography` and a test that signs a real token.
2. **Customer report is right (1 day):** C-01, C-02, H-05, H-06, H-08, H-18; one test per case on the
   real frozen forms.
3. **Uploads never get stuck (1½ days):** C-03, H-15, H-16 (web); H-20, H-21, H-22, H-23 (Android + start
   contract); each with a test that kills / reloads mid-way.
4. **Ops can trust the screens (1 day):** H-14 pagination, H-17 error states, H-07 edits after
   deactivation / archiving, H-09 stuck alert, H-13 completion event, H-19 dialogs.
5. **Privacy and cost (1 day):** H-02, H-03, R-06, R-09, R-18, ZIP / print-copy clean-up (appendix C).
6. **Speed and setup (1½ days):** H-12 sync N+1, H-11 safe re-run of `setup_platform`.
7. **Then the Mediums** by appendix, folded into `docs/plan-quality.md` (Q1–Q7), and the Lows as files
   are touched.

---
# Appendices: full notes of every reviewer
Probe scripts the reviewers wrote to prove findings are in [`review-2026-11-25/probes/`](review-2026-11-25/probes/) (paths like `scratchpad/review/...` below refer to them); screenshots in [`review-2026-11-25/web/`](review-2026-11-25/web/) and [`review-2026-11-25/phone/`](review-2026-11-25/phone/). The first pass is [`review-report-2026-11-24.md`](review-report-2026-11-24.md) (R-01 … R-38).
Each appendix is that reviewer's complete notes: coverage, scores, every finding with evidence,
strengths. IDs inside the appendices are local to that appendix.


## Appendix A: Backend: code quality

### Coverage
- Files: 141 non-test, non-migration .py files in backend/apps and backend/vayu (18,096 lines).
  - Read in full (about 75 files): accounts/*, core/* (except the demo data bodies), core/setup/*,
    core/management/commands/* (except seed_demo bodies), forms/{models,fieldtypes,rules,services,
    system_fields,ratings,access,assets,legacy,urls,views}, bookings/*, media/*, notify/*,
    scoring/{engine,service}, reports/{context,tasks,handlers,models}, integrations/apikeys,
    vayu/settings/{base,prod}, vayu/{celery,urls}, and the working-tree diff of the settings.
  - Partly read (structure, the lines in question, and grep across them): forms/{serializers,library,
    library_push,promote}, reports/{render,service,views,shared,transfer,definition,placeholders,
    media_links}, integrations/{values,webhooks,views,ext_views,models,tasks}, scoring/keychecks,
    core/{demo_pdi,demo_forms}, management/commands/seed_demo (these are mostly data tables).
- Tools run (in backend/): `uv run ruff check .` (passes); `uv run mypy apps vayu` (22 errors in
  7 files, all in the uncommitted setup code = R-07); `uv pip list --outdated`; `uv tree --no-dev
  --frozen`; an AST script that finds functions over 60 lines, big classes, module names used
  nowhere else, untyped functions and modules with no docstring; an import graph built from every
  `from apps.X` line (lazy imports included) plus a strongly-connected-component check; read-only
  `manage.py shell` with local settings; a python check that blocks `cryptography` and calls
  `jwt.encode(..., "RS256")`; git hot-spot count (`git log --name-only`).
- Not checked: `pip-audit` (not installed; I did not download it). The licence of each package.
  An end-to-end render of a report built from the real setup forms (the local database has no
  inspection on those forms, see finding 2). Comparing the Android and web code in depth; I only
  checked the server rules that also live there (phone, stage words, refusal messages, key regex).

### Scores
| Aspect | Score | One-line reason with evidence |
|---|---|---|
| 4 Long-term maintenance | Weak | `flag_stuck_uploads` is not run by anything, so the stuck-upload alert never fires (High); hot spots submissions.py 24 changes / 467 lines, media/services.py 20 / 556; one `ponytail:` note (notify/tasks.py:47), and its limit is still fine |
| 6 Structure and modularity | OK | all 9 apps form one import cycle; `core` imports every other app; the production setup depends on `demo_pdi`; media/services.py does 6 jobs and moves bookings to Completed itself |
| 7 Reuse and duplication | Weak | report "Not able to check" looks for option key `not_checked` but the real forms use `not_able_to_check` (High); "the inspection that counts" query copied 8 times; booking/inspection "who changed it" stamp copied 7 times |
| 8 Clean code | OK | 20 functions over 60 lines (up to 496); 9 unused module-level names; booking `stage` written as a bare string about 170 times |
| 9 Design principles (SOLID) | OK | field-type `if` chains in 5+ modules; event names are bare strings in 41 emit sites and 4 listener lists; ratings tied to section titles |
| 10 Comments and in-code docs | Good | most modules say what they own; a few stale comments (events.py, media/models.py status, Inspection.status, seed_master_lists) — Low only |
| 11 Types and static checks | OK | 8 `type: ignore` (one bare), 120 uses of `Any`; 310 of 920 functions have no type hints at all; mypy is not strict; `noqa: BLE001` marks 8 lines but ruff never checks BLE |
| 12 Dependencies | Weak | production image has no `cryptography`, so the RS256 signing in notify/push.py fails and no push is ever sent (High); `pyjwt` is used but not declared; `factory-boy` unused |

### Findings

#### HIGH · 12 Dependencies · Push notifications cannot work in production: `cryptography` is missing from the production install
- Where: backend/apps/notify/push.py:34-35; backend/pyproject.toml:5-26; backend/Dockerfile:9
- What: `_access_token` signs a Google service-account JWT with `jwt.encode(..., algorithm="RS256")`.
  PyJWT needs the `cryptography` package for RS256. The production image runs `uv sync --frozen
  --no-dev`, and in that install `cryptography` is missing: only `moto` (a dev tool) pulls it in.
  `pyjwt` itself is not declared either. It only arrives through `djangorestframework-simplejwt`.
- Evidence: `uv tree --no-dev --frozen | grep -i crypto` prints nothing, while `pyjwt v2.15.1` sits
  under simplejwt. In uv.lock, only `moto` and `joserfc` depend on cryptography. When I block the
  `cryptography` import and call `jwt.encode({'a':1}, 'x', algorithm='RS256')`, I get
  `NotImplementedError Algorithm 'RS256' could not be found. Do you have cryptography installed?`.
  The tests never see this: apps/notify/tests/test_notify.py:152 mocks `fcm.send`, and the dev
  environment has cryptography through moto.
- Why: once `FIREBASE_CREDENTIALS_FILE` is set on the server, every `push` task fails. Experts do
  not hear about new leads, and Ops do not hear about problems (docs/android-requirements.md:124).
  The bell list still works, so nobody notices quickly.
- Fix: add `pyjwt[crypto]` (or `pyjwt` and `cryptography`) to `dependencies`. Add one test that
  signs with a throwaway RSA key and does not mock the signing. Size S.

#### HIGH · 7 Reuse and duplication · The report's "Not able to check" count expects a key that the real forms do not use
- Where: backend/apps/reports/context.py:186-189, :234; backend/apps/core/setup/reports.py:44,
  :108, :119; backend/apps/core/setup/clappia.py:212 (SPELLING) and :277 (`slug(o)`)
- What: the report counts and lists "Not able to check" answers, and greys those rows, only when
  the chosen option key is exactly `not_checked`. The comment calls this "the option sets'
  convention". The demo forms follow it (demo_pdi NCHK, demo_forms.py:361). The real forms that
  `setup_platform` installs are built from Clappia. There, `spell()` turns the answer into
  "Not Able to Check" and `slug()` turns that into the key `not_able_to_check`.
- Evidence: counting option keys in the frozen forms: pdi `not_checked`=1 (the OBD "Not Checked"),
  `not_able_to_check`=21; used_car 1 / 16; ev 0 / 18. `grep -rn "not_able_to_check" apps` finds
  no code that reads it. The cover grid in core/setup/reports.py:106-109 prints
  `{{ sys.not_checked }}`, and the summary prints `{{ sys.not_checked_list }}`. I could not
  reproduce this end to end: the local database has no submitted inspection on the setup forms.
- Why: an expert answers "Not Able to Check" on, say, 3 PDI checks. The customer's PDF then says
  "Not able to check: 0" with an empty list, and those rows are not greyed. The report
  understates what was not inspected. This follows the brief's "wrong report to a customer" line,
  so it may deserve Critical once it is reproduced.
- Fix: one shared constant, or better an option flag (`"not_checked": true`, like `is_defect`) set by
  the converter and read by context.py, plus a test on a frozen form. Size S.

#### HIGH · 4 Long-term maintenance · The stuck-upload alert is a command that nothing runs
- Where: backend/apps/media/management/commands/flag_stuck_uploads.py:1-18;
  backend/vayu/settings/base.py:129-134 (CELERY_BEAT_SCHEDULE); infra/docker-compose.prod.yml:13-45
- What: the only place that emits `alert.stuck_upload` (outside seed_demo) is a management command.
  It is not in the beat schedule. Compose, scripts and docs never call it either: a grep for
  `flag_stuck_uploads` outside the file finds nothing.
- Evidence: the beat schedule lists only retry-webhooks, sweep-reports, purge-media and
  late-starts. Compose runs only migrate, gunicorn, the workers and beat.
- Why: REQUIREMENTS.md:168 promises a stuck-upload webhook event, and the Android requirements
  promise an Ops push. Neither ever fires. A partner that subscribes to `alert.stuck_upload`
  (offered in integrations/webhooks.py:28-30) gets nothing. Only someone who knows the command
  exists can trigger it.
- Fix: turn it into a Celery task and add it to `CELERY_BEAT_SCHEDULE` (every 5 to 15 min). Size S.

#### MEDIUM · 6 Structure and modularity · Every app imports every other: one import cycle, and `core` sits on top instead of at the bottom
- Where: graph of all `from apps.X` imports (output in scratchpad be_imports.txt). Examples:
  accounts/views.py:80 → notify; core/views.py:12-13 → accounts; core/setup/testdata.py:17-24 →
  accounts, bookings, forms, media; forms/library_push.py:13 → integrations (top level);
  forms/assets.py:11 → media (top level); scoring/service.py:72 → bookings; media/services.py:335
  → reports.
- What: a strongly-connected-component check over the graph gives one component holding all 9
  apps. There are 15 two-way pairs, e.g. accounts↔core, bookings↔core, bookings↔media,
  bookings↔scoring, core↔forms, forms↔reports, forms↔scoring, media↔reports. `core` mixes the
  shared kernel (errors, phone, tasks, app_settings) with demo and setup code, and that code
  imports everything. The many lazy in-function imports (`from apps.x import y` inside functions,
  about 60 of them) exist only to break these cycles.
- Why: no app can be read, tested or changed alone. A new top-level import can deadlock app loading
  at start-up. Moving the setup or demo code later means untangling it from the kernel.
- Fix: move `core/setup`, `demo_*`, seed_demo, seed_test_data, freeze_forms and e2e_reset into a new
  `apps/platform_setup` app that is allowed to depend on all others. Keep `core` import-free of
  other apps (move `SettingView` out, or pass audit in). Turn notify's PREFS and media's `err`
  helpers into data or kernel code. Size M.

#### MEDIUM · 6 Structure and modularity · The production setup builds its reports from the demo module
- Where: backend/apps/core/setup/reports.py:72, :161-172; backend/apps/core/demo_pdi.py:1195-1635
- What: `setup_platform` is documented as safe on production. It calls `demo_pdi.pdf_definition(...)`
  to get the look, the verify page and the bands for every real report, then patches the result
  by matching on titles and text ("Verify this report", "open the link", `bands.normal.header.right[0]`).
  core/setup/reports.py also re-declares `_sec`, `_heading` and `_cols`, copied from
  demo_pdi.py:1148-1184.
- Why: a harmless edit to the demo report changes production reports. Examples: renaming the
  "Verify this report" page (StopIteration at :162) or rewording "open the link" (the button
  silently disappears). Someone cleaning up demo code can break `setup_platform`.
- Fix: move the shared look into a setup-owned module (or a frozen JSON like the forms). Make
  demo_pdi read it, not the other way round. Size S.

#### MEDIUM · 6 Structure / 9 SOLID · media/services.py has six jobs and moves bookings between stages without the stage rules
- Where: backend/apps/media/services.py:37-556 (556 lines, 20 changes: hot spot #3);
  :413-435 `check_completion`, :530-556 `finish_without_missing`; bookings/stages.py:2-13
- What: one module holds permission checks (`writable_booking`, `hidden_fields`), the upload
  protocol, Ops attach/replace, deletion, booking completion and "finish without files". The
  Submitted → Completed move is written twice here, with bare strings, and bypasses
  `stages.can_transition`. It also writes `last_change` without `last_edited_by` / `last_edited_at`
  (:428-429, :546-548), unlike `bookings.services._touch`.
- Why: the stage machine has two owners. A new rule for leaving "submitted" (say, block when a
  payment is unverified) must be added in bookings and in media, and a reviewer will look only in
  bookings. Ops who finish a job show up in `last_change` but not in `last_edited_by`, so the
  "edited by" data disagree.
- Fix: move the two stage changes into a `bookings.services.complete(b, actor, ...)` that uses
  `can_transition` and `_touch`. Split media/services.py into access, upload and ops-edit
  modules. Size M.

#### MEDIUM · 7 Reuse and duplication · "Which inspection counts" and "who changed this" are copied across apps
- Where: the counted inspection,
  `inspections.filter(status="submitted").order_by("-submitted_at").first()`: reports/context.py:22
  (already a function, `latest_inspection`), media/services.py:242, :419, :506, :544,
  media/tasks.py:65, integrations/webhooks.py:205, integrations/values.py:313.
  The change stamp (`row_version += 1; last_edited_by/at; last_change = {...}`):
  bookings/services.py:83-86, bookings/submissions.py:361-365, :421-424,
  media/services.py:316-319, :428-429, :474-477, :546-548. The stale-version error payload:
  bookings/services.py:107-110, bookings/submissions.py:344-347, :408-411.
  The live published version: forms/services.py:84, bookings/services.py:35, bookings/submissions.py:31
  (`latest_published`), core/setup/build.py:57, core/setup/testdata.py:216,
  core/setup/reports.py:205, rules.py:436; for templates with the bare string "published":
  reports/tasks.py:29, reports/shared.py:140, core/setup/reports.py:212.
- Why: these are business rules ("the latest submitted one counts", "every edit is stamped").
  When Ops resolve a conflict, the rule may become "the kept one counts" rather than "the newest".
  Eight copies will not all be updated. media :428 already differs from the others (no
  last_edited_by).
- Fix: `Inspection.objects.counted(booking)`, `stamp(obj, actor, keys)`, `stale_error(obj, code)`,
  `FormVersion.objects.live(form)`, each in its owning app. Size S.

#### MEDIUM · 7 Reuse and duplication · The server's per-answer messages are thrown away; clients rewrite them, and one message is broken
- Where: backend/apps/forms/rules.py:208-209 (`type_errors[key] = e.code`);
  forms/fieldtypes.py:215 and :319; android/.../core/forms/Checks.kt:59-72 (`refusalText`)
- What: `clean_answer` writes an English message for every refusal, but `validate_answers` keeps only
  the code. Each client keeps its own code → words table, e.g. Android
  `"PATTERN_MISMATCH" -> "Wrong format."`. So a form's own `pattern_message` (set by the Admin) is
  lost when the server is the one that refuses. The server text is also wrong where it is used:
  currency calls `_number(..., lo=0)` with no `hi`, so its message would read
  "Must be between 0 and None.".
- Why: an Admin writes "Use the 17-character chassis number" as the pattern message. If the phone's
  check misses a case and the server refuses, the expert sees "Wrong format." The same rule's
  wording lives in three places (server, web, Android) and has already drifted ("This number is
  out of range." vs "Must be between …").
- Fix: return `{code, message}` from validate_answers (pattern_message included), let clients show
  the message, and fix the `hi=None` text. Size M (touches clients).

#### MEDIUM · 9 Design principles (SOLID) · Field types handled by `if` chains spread over many modules
- Where: forms/fieldtypes.py:79-180 (`validate_config`, 102 lines) and :239-366 (`clean_answer`, 128
  lines), ALLOWED_KEYS :32-54, models.FieldType :256-278; reports/context.py:41-81 (`display`);
  core/setup/testdata.py:166-210 (`fill`); integrations/values.py:27-29 (HIDDEN, TYPES);
  media/services.py:29-34 and :234-237; forms/rules.py:20-23. Counts of `t ==` / `type in (...)`
  tests per file: fieldtypes 12, testdata 12, context 11, values 4, media/tasks 3, rules 3.
- What: adding a field type means editing at least 6 modules, with nothing to say which. The "media
  types" set is written three times with the same value: rules.MEDIA (rules.py:23),
  values.HIDDEN (values.py:27), context.MEDIA (context.py:17). media.models.KINDS differs (no
  "image"). The "system-filled" set exists twice too (rules.py:21 as a set, access.py:35 as a
  tuple).
- Why: a new type (say "barcode") is easy to half-add. The report then prints raw values, webhooks
  send media ids as values, and test data skips it, with no error anywhere.
- Fix: one `FIELD_TYPES` registry in forms (per type: config keys, validator, cleaner, is_media,
  display), read by reports, integrations and setup. Size M.

#### MEDIUM · 9 Design principles (SOLID) · Event names are bare strings with no list of what exists
- Where: 41 `events.emit("…")` calls in 10 files; listeners: notify/handlers.py:12-18 and :69-70,
  reports/handlers.py:8 and :12, integrations/webhooks.py:28-39, integrations/values.py:34-38;
  core/events.py:1-2
- What: 15 event names are typed by hand where they are emitted and again where they are heard.
  A typo in either place is silent: `emit` takes any string and listeners compare strings.
- Why: renaming "inspection.updated" in one emitter would stop the PDF from being made again
  (reports/handlers.py:8), and no test or type check would say so.
- Fix: an `Event` StrEnum in core/events.py used by emitters and listeners, and an `emit` that
  refuses unknown names. Size S.

#### MEDIUM · 8 Clean code · Booking stages, inspection status and media status are bare strings everywhere
- Where: about 170 stage-word literals across 30 files (submissions.py 28, media/services.py 22,
  services.py 18, notify/handlers.py 15, forms/access.py 13, dashboards.py 11). STAGES is defined
  twice: bookings/stages.py:1 and forms/access.py:7. answers_filter.py:9 and submissions.py:11
  import the forms copy, not the bookings one. Inspection.status (draft/submitted/superseded) and
  MediaAsset.status (pending/uploading/uploaded/verified/failed/purged) have no choices at all.
- Why: one misspelt `"in-progress"` becomes a filter that silently matches nothing. Adding a stage
  means a grep across 30 files.
- Fix: `Stage`, `InspectionStatus`, `MediaStatus` TextChoices with `choices=` on the fields; keep one
  STAGES. Size M (mechanical).

#### MEDIUM · 7 Reuse and duplication · Booking stage words are written in the server and in many web places
- Where: backend/apps/bookings/dashboards.py:36-37 (STAGE_LABELS for the CSV); web/src/api/labels.ts:28,
  web/src/ui/AccessMatrix.tsx:5, web/src/ui/AccessEditor.tsx:7-10,
  web/src/pages/admin/builder/PreviewDialog.tsx:9, web/src/pages/ops/Today.tsx:27
- What: the agreed words ("submitted" → "Uploading") are written out by hand in six places.
- Why: when the owner renames a stage again (as happened with lead/booking), the CSV export and some
  web screens will show the old word.
- Fix: the server sends the labels (e.g. in `/inspection-types` or a small `/labels` endpoint), or
  web keeps one copy (labels.ts) and the CSV reads the same list. Size S.

#### MEDIUM · 9 Design principles (SOLID) · Rating categories point at section titles, not section keys
- Where: forms/ratings.py:1-17 (a patch-up for renames); scoring/service.py:31, :44;
  scoring/engine.py:68-73; core/setup/convert.py:41-64; forms/models.py:230-232 (Section.key,
  "a permanent name … so a report can point at" it)
- What: sections got a permanent `key` for exactly this purpose, but ratings still match on
  `section.title`. A rename only works because `rename_section_title` rewrites the config. Any
  other path (promote import, library section accept-update, setup `_fill`) can leave a category
  pointing at a title that no longer exists.
- Why: a category that matches no section rates 5/5 ("no defects"). The customer then sees
  "Engine 5/5" even though engine checks failed. This is only partly guarded by `config_issues` at
  publish time.
- Fix: store section keys in `categories[].sections` (a migration maps titles to keys); delete
  ratings.py. Size M.

#### LOW · 7 Reuse and duplication · Smaller copies of the same rule
- Where and what:
  - Device sign-out written 3 times: accounts/services.py:59-61, accounts/views.py:149-150, :192-195.
  - "device_id from the token" written 4 times: accounts/views.py:147, :164, :193; notify/views.py:13-14.
  - Avatar size check twice with the same message: accounts/views.py:123-124 and avatars.py:27-28.
  - `INSPECTIONS` tuple twice: core/setup/forms.py:9-11 and core/setup/convert.py:10-12.
  - Text-to-key slug written 3 ways: forms/models.py:217, core/setup/clappia.py:41-45,
    core/demo_forms.py:333.
  - Flush + empty bucket + re-seed role grants: core/setup/testdata.py:63-76 and
    core/management/commands/e2e_reset.py:25-46.
  - S3 client built 3 ways: media/storage.py:8-13, e2e_reset.py:34-36 (hard-coded "test" keys),
    local_bucket.py:15-18.
  - Part ↔ form type maps: forms/models.py:40-42 (NAMESPACE, PARTS), answers_filter.py:17-19, :77,
    rules.py:12, media/services.py:514 (a third order: start, inspection, end).
  - ROLES tuple: forms/fieldtypes.py:24, forms/access.py:6 (bare strings instead of `Role`).
  - Ratings 1–5: fieldtypes.py:253, scoring/service.py:105, engine.py:76; severities:
    fieldtypes.py:23, reports/context.py:217, engine.py:10.
  - `setup_platform` creates users without the phone rule or the password validators that the API
    uses (setup_platform.py:50-52 vs accounts/serializers.py:28-35, :46-50). A CSV phone
    "98765 43210" is stored as typed, not as "+919876543210".
- Fix: one helper each, in the owning app. Size S each.

#### LOW · 6 Structure and modularity · A booking error helper is imported by five other modules, and private helpers are used across modules
- Where: `bookings.services.err` (a 1:1 wrapper of CodedError, services.py:25-26) imported by
  media/services.py:16, media/views.py:11, reports/{service,transfer,shared,media_links,views}.py,
  integrations/views.py. bookings/submissions.py:19-27 imports the private `_changed` and `_lock`.
  avatars.py:19-20 has another 1:1 wrapper (`_bad`).
- Why: reports and integrations depend on bookings only for an error helper, which feeds the cycle
  in the finding above. Private names used from outside the module are easy to break.
- Fix: use `CodedError` directly; make `lock`/`changed` public, or move submissions' use behind a
  public function. Size S.

#### LOW · 6 Structure and modularity · Business rules inside views
- Where: accounts/views.py:79-109 (profile and notification rules), :236-259 (the "last admin"
  rule, activate and deactivate); forms/views.py:407-482 (the same lock_draft → set → row_version+1
  → save → audit block 3 times: VersionSettings, RatingConfigView, KeyChecksView);
  integrations/views.py:65-160 (`_clean_integration`, 96 lines of validation).
- Why: the rules cannot be reused, for example from a future import or the API-key path. The three
  copied blocks will drift (forms/ratings.py:15-17 already bumps differently, with an F()
  expression).
- Fix: move each rule into its app's services module; one `save_draft_setting(version, **fields)`.
  Size S.

#### LOW · 8 Clean code · Long functions and dead code
- Where: functions over 60 lines (20). The worst: demo_pdi.py:296 `pdi_pages` (496), :1195
  `pdf_definition` (440), fieldtypes.py:239 `clean_answer` (128), reports/render.py:357 `css` (113),
  clappia.py:327 `convert` (111), core/setup/reports.py:70 `definition` (110),
  fieldtypes.py:79 `validate_config` (102), seed_demo.py:326 `_more_bookings` (101),
  clappia.py:108 `translate` (100), integrations/views.py:65 `_clean_integration` (96),
  testdata.py:313 `build_days` (96), media/services.py:151 `initiate` (81),
  promote.py:342 `import_bundle` (78). Big classes: seed_demo `Command` (520 lines, 15 methods),
  `BookingViewSet` (223 lines, 22 methods), integrations `Resolver` (156 lines).
  Dead names (used nowhere, tests included unless stated): accounts/serializers.py:96 `ROLE_VALUES`;
  forms/services.py:24 `item_label` (tests only); core/demo_forms.py:15 `NOT_OK`;
  seed_demo.py:48 `DEFECT`; core/setup/clappia.py:225-226 `ALWAYS_PHOTO_SECTIONS` and
  `ALWAYS_PHOTO` (replaced by `ALWAYS_SECTIONS`/`ALWAYS` at :454-460); clappia.py:533 `stats`;
  core/setup/build.py:146 `describe`. core/setup/reports.py:207 re-imports `validate_definition`
  from a module it already imported as `reports` (:201).
- Why: two near-identical constant sets in clappia.py invite editing the wrong one. Long data
  functions hide the few real rules among them.
- Fix: delete the dead names; move the demo/PDI data into JSON like `setup/frozen`. Size S.

#### LOW · 8 Clean code · Small hacks
- Where: media/services.py:444 (`str(asset.id) in json.dumps(i.answers)` decides "used");
  bookings/submissions.py:66-69 (a fake `_Role` user); submissions.py:389 (`except Exception` where
  only `CodedError` can come from `booking_form_version`); testdata.py:250 (a conditional
  expression used as a statement).
- Why: the json.dumps check matches an id anywhere in the answers, Key Check text included.
  A broad except hides real database errors from search.
- Fix: check the media fields; catch `CodedError`. Size S.

#### LOW · 10 Comments and in-code docs · Stale or wrong comments
- Where:
  - core/events.py:1-2: "Phase 9 delivers them to webhooks; until then they can be observed …".
    Integrations, reports and notify have all subscribed for a long time (*/apps.py ready()).
  - media/models.py:26: `# pending | verified`. Real values: pending, uploading, uploaded,
    verified, failed, purged.
  - bookings/models.py:91: `# draft | submitted`. `superseded` is also written
    (submissions.py:449).
  - reports/context.py:186: "the option sets' convention" is not true for the real forms (finding 2).
  - forms/management/commands/seed_master_lists.py: "City and car make/model start empty: admins
    fill them". `setup_platform` fills them (core/setup/lists.py:53-66).
  - 24 of 81 modules over 40 lines have no module docstring (mostly views/models/serializers,
    e.g. forms/views.py, reports/views.py, bookings/services.py).
- Fix: update the lines. Size S.

#### LOW · 11 Types and static checks · Escape hatches and lint gaps
- Where: 8 `type: ignore` (all in the files listed here):
  - webhooks.py:277 is bare and hides `re.match(...)` returning None.
  - integrations/views.py:84 and accounts/services.py:55-56 could be removed by narrowing with
    an `assert`.
  - forms/serializers.py:194, core/errors.py:14, accounts/models.py:27 and webhooks.py:80 are
    justified (DRF and urllib3 stubs).
  - 120 uses of `Any` (rules.py 19, values.py 17, fieldtypes.py 9). 310 of 920 functions have no
    annotation at all.
  - pyproject.toml:63-67: mypy runs only with `check_untyped_defs`, no `disallow_untyped_defs`
    even for the pure modules (scoring/engine, forms/rules, forms/fieldtypes), and
    `ignore_missing_imports = true` globally.
  - 8 `# noqa: BLE001` comments (rules.py:34, core/views.py:33,37, submissions.py:389,
    webhooks.py:327,346, reports/tasks.py:65,93) refer to a rule ruff never runs: pyproject
    selects only E, F, I, B, UP, DJ. So new broad `except Exception` lines get no warning, and
    there are no complexity (C90), simplify (SIM) or unused-noqa (RUF100) checks either.
- Why: the lint config looks stricter than it is. The mypy errors in the new setup code (R-07)
  show how little the current settings catch.
- Fix: add `BLE`, `RUF100`, `C901` (max-complexity ~15) to ruff; add a `[[tool.mypy.overrides]]`
  with `disallow_untyped_defs` for scoring/*, forms/rules.py, forms/fieldtypes.py, core/*. Size S.

#### LOW · 12 Dependencies · Unused and undeclared packages
- Where: pyproject.toml:34 `factory-boy`: no `import factory` anywhere. `pyjwt`: used directly
  (notify/push.py:10) but not declared (finding 1). `python-dateutil` is not used by us (it comes
  through botocore and celery). That is fine.
- Fix: drop factory-boy; declare pyjwt. Size S.

#### NOTE · 12 Dependencies · Versions that will need a planned upgrade
- `uv pip list --outdated`: django 5.2.19 (latest 6.1.3; 5.2 is LTS, supported to April 2028), so
  no rush. mypy 1.19 → 2.4 and django-stubs 5.2 → 6.1 come together with Django. sentry-sdk 2.75
  → 3.0, held by `~=2.20`. redis 6.4 → 8.2, held by `<7`. python-json-logger 3.3 → 4.2. pytest
  8 → 9 and pytest-cov 6 → 7, held by `~=`. Patch releases waiting: boto3, botocore, moto, regex.
  Not audited for CVEs (pip-audit not run).

#### NOTE · 4 Long-term maintenance · Hot spots (non-test .py, changes from `git log --name-only`)
| File | Changes | Lines | Risk |
|---|---|---|---|
| bookings/submissions.py | 24 | 467 | offline conflict rules + Ops edits + search visibility in one file |
| bookings/views.py | 22 | 317 | `_filtered` grows a branch per new filter (60 lines) |
| media/services.py | 20 | 556 | six jobs, owns a stage change (finding above) |
| forms/views.py | 16 | 553 | 30 view classes, copied lock/save blocks |
| core/management/commands/seed_demo.py | 15 | 585 | demo data kept in step with every feature |
| reports/views.py, forms/serializers.py, forms/models.py | 15 each | 404 / 310 / 396 | — |
| reports/render.py | 11 | 570 | 113-line CSS builder; has uncommitted edits now |
The only `ponytail:` note (notify/tasks.py:47, "a rescheduled job already reported late isn't
reported again") is still an acceptable limit. There are no TODO or FIXME notes.

### Strengths worth keeping
- `ruff check` is clean, and all mypy errors are in the new, uncommitted setup code. The rest
  type-checks (`uv run mypy apps vayu`: 22 errors in 7 files, all core/setup + freeze_forms + a test).
- The pure logic is separate and testable: scoring/engine.py has no database access, and
  forms/rules.py evaluates JsonLogic over plain data against shared vectors (rules.py:1-2).
- Errors are one consistent type, with machine codes: `CodedError` (core/errors.py) everywhere,
  and the exception handler turns DataError into 400s without logging customer values
  (core/exceptions.py:21-29).
- Most modules open with a docstring that says what they own and why (e.g. media/zips.py,
  notify/push.py, bookings/sync.py, forms/access.py).
- Production settings refuse to start without Sentry (prod.py:16-17). Seed and wipe commands
  guard on settings (e2e_reset.py:19, local_bucket.py:13, testdata.py:48-60).


## Appendix B: Backend: correctness, data, notifications, tests

### Coverage
- Files read in full (about 45): bookings/{models,stages,services,submissions,views,timing,dashboards,answers_filter,sync,activity,serializers}.py; media/{models,services,views,tasks,zips,storage}.py + management/flag_stuck_uploads.py; reports/{models,handlers,tasks,service,context,media_links,placeholders}.py + render.py (images, photos, uncommitted diff); notify/{models,handlers,tasks,push,views}.py; integrations/{models,webhooks,tasks}.py + ext_views.py (bulk and inspection parts); accounts/{models,services,views,permissions,roles,authentication,audit}.py; forms/{services,library_push,system_fields}.py + fieldtypes.clean_answer + rules.validate_answers + models (constraints); core/{events,tasks,errors,exceptions,app_settings}.py; settings base/test, infra/docker-compose.prod.yml.
- Migrations: listed all 57; read every data migration that rewrites rows (bookings 0006, 0008; forms 0019; integrations 0002, 0004; notify 0002); grep for AlterField/RemoveField/RunSQL in the rest.
- Tests: read bookings/tests/{conftest,test_submissions (parts),test_timing (parts),test_lifecycle (parts)}, media/tests/test_offline_reassign.py, notify/tests/test_notify.py (parts); grep over all test folders for the key paths.
- Tools run:
  - `manage.py makemigrations --check --dry-run` (local settings) → "No changes detected".
  - Probe tests I wrote in the scratchpad (`review/probe/test_probe.py`, `test_probe2.py`), run against a separate test database (`DB_NAME=vayu_review`, so the test DB was `test_vayu_review`), 6 tests, all executed. Output quoted in the findings. They did not touch the repo, the demo data or the main test DB.
- NOT checked: forms/library.py, promote.py and rules.py beyond the parts named above; integrations/values.py and integrations/views.py (skimmed only); reports/{views,transfer,shared,definition}.py; scoring engine/keychecks (only service.recompute). Real concurrency (two workers at once) was judged from the code, not run. Push arriving on a real phone not checked (Android slice). Coverage numbers not run (the full suite was not allowed).

### Scores
| Aspect | Score | One-line reason with evidence |
|---|---|---|
| 13 Correctness and edge cases | Bad | A late second expert's submit on a completed booking re-renders the customer's report from their inspection before Ops choose (probe: `CONFLICT 200 completed TWO_EXPERTS render calls: 1 report uses expert: expert3 odometer 99999`) |
| 14 Error handling | Weak | A re-submit with a new request id creates a second counted inspection (probe `RESUBMIT 200 None 2 ''`); push and ZIP tasks have no failure path |
| 15 Data integrity and migrations | Weak | Force-release then re-start leaves two drafts per expert, and submit fills the old one (probe `RESTART ... [(True,'submitted'),(False,'draft')]`); no DB rule stops this. Migrations are safe; there are no pending changes. |
| 17 Notifications and alerts | Weak | "Photos stuck" alerts never fire: `flag_stuck_uploads` is in no beat schedule, cron or test; duplicate "New lead"; push_token_at promise not built |
| 19 Testing | OK | Covered paths have sharp tests (exhaustive stage matrix, idempotency, retries), but all 6 bugs I reproduced sit in untested paths |

### Findings

#### CRITICAL · 13 Correctness · Late expert's submit silently replaces the customer's report before Ops resolve the conflict
- Where: backend/apps/bookings/submissions.py:279-287 and :305; backend/apps/reports/handlers.py:21-24; backend/apps/reports/context.py:21-22; backend/apps/media/services.py:413-425
- What: on a booking that is already completed, a submit from the expert it was moved away from marks `TWO_EXPERTS`. But `_changed` still emits `booking.updated`, and the report handler re-renders any completed booking. The render uses `latest_inspection` (newest `submitted_at`), which is the inspection Ops have not chosen yet. `check_completion` has no conflict guard either, so a `submitted` booking in conflict also completes and renders from whichever inspection is newest.
- Evidence: probe (Ravi started; Ops force-release and give the job to Sana; Sana submits, so the booking is completed; then Ravi's offline submit arrives with odometer 99999):
  `CONFLICT 200 completed TWO_EXPERTS render calls: 1 report uses expert: expert3 odometer 99999`
- Why: the customer's verify link and the ERP `pdf.ready` webhook get the rejected expert's findings (here a different odometer) while Ops still see "Two experts inspected". If Ops later keep Sana's inspection, the report flips back. The customer may already have seen or downloaded the wrong one.
- Fix: while `b.conflict` is set, skip the render and `check_completion`; render once in `resolve_conflict`. `latest_inspection` should pick the inspection Ops kept (or the booking's counted one), not the newest. Size S.

#### HIGH · 13 Correctness · Customer photo/video ZIP holds every verified file on the booking, not the counted inspection's
- Where: backend/apps/reports/media_links.py:34-36, :70-80 (docstring :6-7 says "never ... Ops' own uploads")
- What: `_assets` filters only by booking, `verified`, not replaced, and kind. Photos from a superseded inspection, the other expert's photos during or after a conflict, and Ops uploads never attached to any answer (up to `LOOSE_LIMIT`=10 per field, media/services.py:99) all go into the customer ZIP. `photo_count` in the PDF counts them too.
- Evidence: code above. Nothing restricts the ZIP to `expected_media(latest_inspection)`.
- Why: after Ops keep Sana's inspection, a buyer who taps "All photos" in the PDF still gets Ravi's photos, which may be of the wrong car. An Ops person's half-done upload (closed tab) is also sent to the customer.
- Fix: limit `_assets` to the ids referenced by the counted inspection's answers (`expected_media`). Size S.

#### HIGH · 13 Correctness · Any booking edit fails once its lead owner or expert leaves, or its city or car model is archived
- Where: backend/apps/bookings/services.py:124-125 (whole merged form re-cleaned); backend/apps/forms/fieldtypes.py:281-282 (archived refused), :298 (inactive user refused); system fields lead_owner, assigned_expert, city, car_make_model (forms/system_fields.py:13-24)
- What: `edit` merges the new keys into the stored answers and validates everything again. A stored value that was valid when saved now fails.
- Evidence: probes:
  `LEAD_OWNER 400 {'code': 'INVALID_ANSWERS', ... 'errors': {'lead_owner': 'INVALID_USER'}}` (Ops user deactivated, then Ops change only the customer name)
  `CITY 400 {... 'errors': {'city': 'ARCHIVED_OPTION'}}` (city archived, then the same edit)
- Why: when an Ops person leaves, Admin deactivates them and every open booking they owned can no longer be edited, not even a phone-number typo, until someone re-picks the owner (if their role may edit that field at that stage). The same happens to every booking in a city that is archived. `edit_inspection` (submissions.py:353-354) has the same pattern for inspection answers that use master lists.
- Fix: validate only the keys that changed, or accept an unchanged stored value (archived or inactive) in `clean_answer` when it equals the old value. Size S.

#### HIGH · 14 Error handling · A second submit with a new request id makes a second counted inspection with no conflict
- Where: backend/apps/bookings/submissions.py:236-256, :294-305
- What: idempotency is keyed only on `client_submission_uuid`. When the expert has no draft left (already submitted) and sends `form_version`, the "offline start" path creates a fresh Inspection and submits it. `_advance` matches no branch, so there is no conflict and no alert. The booking now has two `submitted` inspections from one expert. Reports, webhooks and `check_completion` all use the newest.
- Evidence: probe `RESUBMIT 200 None 2 ''` (status 200, no error code, 2 submitted inspections, conflict empty).
- Why: a phone that loses its stored submission id (reinstall, cleared data, or a bug that regenerates the id on retry) sends the job again. The newer copy silently becomes the report, also on a completed booking (the `booking.updated` event triggers a re-render), and Ops' edits to the first inspection are lost from view.
- Fix: in `submit`, refuse (or treat as a duplicate) when this expert already has a `submitted` inspection on the booking. Size S.

#### HIGH · 15 Data integrity · Force-release then re-start by the same expert leaves two drafts; submit fills the old, released one
- Where: backend/apps/bookings/services.py:209-220 (old draft kept as `draft`); submissions.py:147-170 (start creates a new draft); :241 (`.first()` picks the oldest draft); own_filter :72-75
- What: force-release does not close the expert's draft. If the same expert starts again, a second draft is created. Submit takes the oldest one, the released draft pinned to the old form versions. The new draft stays `draft` for ever.
- Evidence: probe `RESTART 200 False 200 [(True, 'submitted'), (False, 'draft')]` (the first inspection got submitted; the new one is an orphan draft).
- Why: (1) The answers the phone filled on the newly pinned form are validated against the old pinned version. If Admin published a change in between, the submit fails with UNKNOWN_FIELD, or the report is built on the old layout. (2) `own_filter` treats any draft as "theirs", so if Ops later give the booking to another expert, the first expert still sees it in lists and sync for good. (3) No DB rule enforces one draft per expert per booking.
- Fix: in `force_release`, mark the expert's draft (for example `released`); in `submit`, use the newest draft; add a partial unique constraint (booking, expert) where status='draft'. Size S.

#### HIGH · 17 Notifications · "Photos stuck" alerts are never raised
- Where: backend/apps/media/management/commands/flag_stuck_uploads.py (only emitter of `alert.stuck_upload`); vayu/settings/base.py:129-134 (beat schedule has no entry); infra/docker-compose.prod.yml (no cron)
- What: the only code that emits `alert.stuck_upload` is a management command that nothing runs and no test calls.
- Evidence: `grep -rnI flag_stuck_uploads backend docs infra scripts` finds only the command file itself. The beat schedule lists retry-webhooks, sweep-reports, purge-media and late-starts only.
- Why: REQUIREMENTS.md:168 lists stuck-upload alerts as a webhook event, and :185 puts stuck uploads in the problem queue. Ops never get the bell or push, and the ERP never gets the webhook, while a job waits for photos for days.
- Fix: add a beat entry for a task that runs the same loop, plus a test. Size S.

#### MEDIUM · 14 Error handling · verify_asset is not safe to run twice and rewrites the original in place
- Where: backend/apps/media/tasks.py:33-62; media/services.py:347-370
- What: a photo larger than 2048 px is overwritten at `asset.key` with a shrunk JPEG, but `sha256` and `size` stay those of the original. A second verify run that reads the object after the shrink (two `complete` calls racing, or a manual re-queue) fails the checksum, runs `storage.delete(asset.key)` and sets status `failed`, or saves `verified` after the file was deleted. Both runs also do a full `asset.save()`.
- Evidence: code lines 40-44 (mismatch path deletes the file) and 51-53 (in-place overwrite). The only guard is `status == "verified"` read at the start, without a lock.
- Why: a rare but silent loss of a customer photo.
- Fix: claim with a conditional update (`status__in=("uploaded",)` → `verifying`), and store the shrunk copy under a new key or update sha and size. Size S.

#### MEDIUM · 14 Error handling · A ZIP build that fails stays "Preparing…" for 7 days
- Where: backend/apps/media/zips.py:96-107, :110-139
- What: `build_zip` has no `except`. A storage error leaves `status="building"`, and `request_zip` keeps returning that row while it is fresh (7 days), because only `failed` is rebuilt.
- Evidence: zips.py:102 `if z is not None and z.status != "failed" and fresh(z): return z`; build_zip sets nothing on error.
- Why: an Ops download, or the customer's "All photos" link (media_links → request_zip), spins for a week after one R2 hiccup.
- Fix: catch the error, mark `failed`, and treat an old `building` row as failed. Size S.

#### MEDIUM · 17 Notifications · Push batch aborts on the first network error, with no retry
- Where: backend/apps/notify/tasks.py:12-29; notify/push.py:36-38, :49-52
- What: `requests.post` exceptions (timeout, DNS) and `raise_for_status` on the token call are not caught. The task dies, the rest of the batch is never pushed, and nothing retries it.
- Evidence: no try/except in `push` or `send`; `@shared_task` without autoretry.
- Why: one slow FCM call during a busy minute means every phone in that batch (for example all Ops for a conflict) gets no push. They only see the notice when they next open the app.
- Fix: catch `requests.RequestException` per device, and add `autoretry_for` with backoff for the token fetch. Size S.

#### MEDIUM · 17 Notifications · A promised push rule is not built: earlier user's device on the same phone still gets pushes
- Where: backend/apps/notify/views.py:18-20 (docstring: "pushes go only to the device that sent it last (see tasks.push)"); notify/tasks.py:22-28; `push_token_at` is written (views.py:31-32) but never read
- What: `tasks.push` sends to every non-revoked device of the user. If expert A's sign-out never reached the server and expert B signs in on the same phone, A's device row still holds the same FCM token.
- Evidence: `grep -rn push_token_at apps` shows writes and tests only, no read in tasks.
- Why: B's phone wakes for A's notices (the content stays private because the phone fetches with B's token, but B gets phantom alerts or a duplicate of their own). The doc and comment say this cannot happen.
- Fix: in `PushTokenView`, clear the same token on other devices, or in `push` skip a device whose token is held by a newer device. Size S.

#### MEDIUM · 17 Notifications · Assigning the same expert again sends a second "New lead"
- Where: backend/apps/bookings/services.py:154-170 (no "same expert" check; assigned→assigned is legal); notify/handlers.py:93-97
- Evidence: probe `NEWLEAD ['New lead: SA37926', 'New lead: SA37926']` (two assign calls with the same expert).
- Why: an Ops double-click, or the bulk tool re-saving, sends the expert duplicate pushes and adds a timeline row and a row_version bump.
- Fix: return early when `expert.id == b.assigned_expert_id`. Size S.

#### MEDIUM · 13 Correctness · External API inspection PATCH writes to whatever inspection is newest (draft or superseded), last-write-wins
- Where: backend/apps/integrations/ext_views.py:173-178, :191-197
- What: `latest_inspection` orders by `created_at` over all statuses. With no `row_version` the server uses the current one. The service user is Admin-role, so every field is editable at every stage.
- Why: an ERP write during an expert's draft is overwritten when the expert submits (submit replaces `insp.answers`). A write after a conflict can land on the superseded inspection and never reach the report.
- Fix: target the counted submitted inspection only; refuse drafts. Size S.

#### MEDIUM · 13 Correctness · HEIC photos are accepted but never appear in the customer PDF
- Where: backend/apps/media/services.py:30 (image/heic allowed); media/tasks.py:47 (no preview for HEIC); reports/render.py:68-71 (PIL cannot open HEIC, so "Photo not available"); web/src/ui/FormRenderer.tsx:212 and web/src/pages/ops/Booking.tsx:431 accept `image/*`
- Why: an Ops person on a Mac or iPhone browser adds a HEIC photo; the customer's report shows a grey "Photo not available" box. The ZIP names it `.bin` (zips.py:62-63).
- Fix: convert HEIC to JPEG in `verify_asset` (pillow-heif), or refuse HEIC at initiate. Size S.

#### LOW · 13 Correctness · Render reads booking and inspection before claiming, so an edit in between can be lost
- Where: backend/apps/reports/tasks.py:75-89
- What: an edit committed between line 75 (reads) and the claim at 84 sets `stale=True`, which the claim resets to False. The edit's own render returns "busy", so the PDF misses the edit and `sweep_reports` cannot see it.
- Fix: claim first, then load booking and inspection. Size S.

#### LOW · 13 Correctness · Report uses the newest PDF layout for inspections pinned to older form versions
- Where: backend/apps/reports/tasks.py:27-29; context.py:253-255 (missing field → row dropped)
- Why: rows that exist only in one version silently disappear from an older inspection's report. Note only.
- Fix: none needed now; document it, or pin the template version at submit. Size M.

#### LOW · 15 Data integrity · Text limits larger than columns give an unnamed 400
- Where: forms/fieldtypes.py:26 (short_text 200) vs bookings/models.py:13, :24-25 (booking_id, car_make_model, chassis_no 64)
- What: a 65–200 character booking ID, or a chassis number on submit (`_advance` copies it at submissions.py:304), hits a DataError. The handler turns it into `INVALID_INPUT "A value is not acceptable."` with no field key.
- Why: an expert's offline submit with a long chassis value fails with no hint which field is wrong.
- Fix: cap system short_text keys at the column size in `SYSTEM_FIELDS` config. Size S.

#### LOW · 15 Data integrity · Booking create and delete are not atomic; delete emits before deleting and does not lock
- Where: backend/apps/bookings/services.py:89-101, :250-257
- What: create saves, then logs activity and emits events outside one transaction. Delete records the audit row and emits `booking.deleted` (webhook rows are created and sent at once in autocommit), then deletes. The stage check runs on an unlocked copy, so an Ops delete of a "draft" can race an assign.
- Fix: wrap both in `transaction.atomic` + `_lock`. Size S.

#### LOW · 14 Error handling · Expert's per-field limit counts failed uploads
- Where: backend/apps/media/services.py:222-224
- What: `failed` rows (bad checksum, unreadable image) count toward `max_count`. A retake with a new client_uuid on a 1-photo field gets `TOO_MANY` unless the app first deletes the failed one.
- Fix: `.exclude(status="failed")`. Size S.

#### LOW · 17 Notifications · Stuck-upload list never forgets failed or abandoned files; no notice to the expert on force-release
- Where: media/services.py:495-498 (failed and cancelled or superseded bookings stay "stuck" for good); services.py:209-220 + notify/handlers.py:119 (`stage` is QUIET, so a force-released expert hears nothing)
- Fix: exclude cancelled and completed bookings and failed rows from `stuck_uploads`; decide whether a force-release should tell the expert. Size S.

#### LOW · 17 Notifications · "submitted" and "completed" arrive together
- Where: bookings/submissions.py:267-270 → media/services.py:432; handlers.py:16-18
- What: a job with every file already in gives Ops two pushes in the same second.
- Fix: skip `inspection.submitted` notices when the booking completes in the same request. Size S.

#### LOW · 15 Migrations · Data migrations cannot be reversed and one imports live app code
- Where: bookings/migrations/0006_split_ops_answers.py (noop reverse, loads all rows without `.iterator()`); bookings/migrations/0008_timing.py:9 (`from apps.bookings import timing`, so a later change to timing changes this migration); integrations/migrations/0002_request_designer.py (drops `events`, `template`, `secret` with noop reverse)
- Why: pre-launch, so no data at risk now. A rollback past these cannot restore data. `makemigrations --check` is clean.
- Fix: copy the timing helpers into 0008; note in release steps that these are one-way. Size S.

#### MEDIUM · 19 Testing · The riskiest flows have no test, and every bug above was found in an untested path
- Where: tests folders (grep results)
- What: there is no test for: `flag_stuck_uploads` (0 references); report or webhook content during a TWO_EXPERTS conflict; the customer ZIP contents after `resolve_conflict` (only `test_review_fixes` touches superseded, and only the stage); a second submit with a new uuid; restart after force-release; `build_zip` failure; `verify_asset` run twice; `push` with a network error; editing a booking after a user is deactivated or a list item archived.
- Hand mutation check (read the test, decided whether breaking one line fails it):
  1. `stages.can_transition`: test_lifecycle.py:13 lists the full legal matrix → any changed line fails. Strong.
  2. `services.edit` row_version check: test_lifecycle STALE_BOOKING → fails. Strong.
  3. `submissions.submit` uuid replay: test_submit_marks_submitted_and_is_idempotent → fails. Strong for the same uuid, blind to a new uuid (bug above).
  4. `check_completion` exactly once: media/tests/test_upload.py:290 counts `inspection.completed == 1` → fails. Strong, but nothing checks the conflict case.
  5. `timing.stamp_late`: test_timing.py:48-53 asserts 40/25 minutes with a local-time slot → a UTC slot fails it. Strong.
  6. `notify.tasks.late_starts` once per job: test_notify.py:196-211 → fails. Strong.
  7. `reports.tasks.render_report` stale → render again: test_reports.py:690-698 (`len(calls) == 2`) → fails. Strong; the read-before-claim race is untested.
  8. `webhooks._retry` schedule: test_webhooks.py:339-345 checks every gap and `retries_exhausted` after 7 → fails. Strong.
  9. `media_links._assets` scope: only counts are tested (test_media_links), never which files → removing a filter line would pass. Weak.
- Fix: add the probe tests above (6 short tests) as regression tests. Size S.

### Strengths worth keeping
- Optimistic locking plus row locks on every booking and inspection write (`_lock`, `select_for_update`, row_version 409 with who and what changed): services.py:104-139, submissions.py:340-347.
- Side effects deferred to commit: pushes, webhook sends and report renders all go through `core_tasks.after_commit` (notify/handlers.py:158, webhooks.py:174, reports/handlers.py:24), and delete_asset cleans R2 only after commit (media/services.py:484-490).
- Webhook delivery is claimed with a conditional update, stores metadata only, rebuilds the body at send time, and guards SSRF at connect time (webhooks.py:75-115, tasks.py:13-17).
- The stage machine is one small table, and the test checks it exhaustively (stages.py, test_lifecycle.py:13-15).
- Report render has one-at-a-time claim, stale re-run, failure alert once, and a sweep for killed workers (reports/tasks.py:84-136).


## Appendix C: Backend: security, privacy, external services

### Coverage
- Files read: about 60, all of them fully except where noted. Folders: `vayu/settings/*` (5), `vayu/urls.py`; `apps/accounts` (urls, views, authentication, permissions, roles, services, serializers, models, audit, avatars, catalog); `apps/core` (urls, views, middleware, exceptions, errors, logging, app_settings, phone, events, tasks, models, plus the guards in the management commands e2e_reset, seed_demo, seed_test_data/setup/testdata, local_bucket); `apps/bookings` (urls, views, models, serializers, services, submissions, activity, sync, answers_filter; dashboards only the CSV/permission parts); `apps/forms` (urls, views, access, assets, promote, the DraftOnly guard in models, serializers validate paths); `apps/media` (all: urls, views, services, models, storage, tasks, zips); `apps/reports` (urls, views, models, media_links, tasks, handlers, placeholders, render: images, parts, WeasyPrint call); `apps/integrations` (urls, views, ext_views, apikeys, models, webhooks, tasks, values: render only); `apps/notify` (urls, views, push, tasks, handlers); `backend/Dockerfile`, `.dockerignore`, `infra/Caddyfile`, `infra/docker-compose.prod.yml`.
- Tools run:
  - `manage.py check --deploy` with prod settings. Only W008 (TLS redirect, which Caddy does) and W021 (HSTS preload) came back.
  - `git ls-files | grep` for secrets. Only `.env.example` is tracked; `.env.local` is ignored.
  - Read-only `manage.py shell` queries with local settings: forms, levels, R2 listing.
  - curl and python `requests` against http://localhost:8000:
    - an expert IDOR sweep over 25 routes;
    - a login enumeration probe;
    - a 30 MB and a 3 MB JSON body sent to login;
    - an end-to-end probe (script `scratchpad/review/resubmit_probe.py`) that created two bookings `REVIEW-SEC-b9272f` (left at assigned, first try failed) and `REVIEW-SEC-555c39` (customer "REVIEW-Security probe").
- NOT checked:
  - `forms/fieldtypes.py`, `forms/rules.py`, `forms/library*.py`, `forms/services.py`, `reports/context.py|definition.py|transfer.py|shared.py|service.py`, `integrations/values.py` (beyond render), `scoring/*`, `core/setup/*` and the demo seed files were skimmed or not read. Answer validation (`validate_answers`) is trusted, not reviewed.
  - I did not block R2, FCM or Sentry on the running stack, because the owner is using it. Behaviour when they are down comes from reading the code and library defaults.
  - Django sessions: I did not test what a password change does to other web sessions; Django's own session-hash check is assumed.
  - I could not check the R2 bucket's settings (public access, CORS, lifecycle rules): they are not in the repo.

### Scores
| Aspect | Score | One-line reason with evidence |
|---|---|---|
| 20 Security | Weak | An expert can submit a second inspection on a completed booking and replace what Ops and the customer report see (High, proven with a REVIEW- booking). Role, object and field checks otherwise held in a 25-route expert IDOR sweep. |
| 21 Privacy and data retention | OK | Medium only: changed values of fields hidden from experts go into their notifications; ZIP and print copies are left in R2 after the retention purge or a removal; 7-day ZIP links need no sign-in; access logs keep search terms. |
| 28 External services | OK | Medium only: boto3 has no timeouts (60 s × 5 tries) on the request path with 4 sync gunicorn workers; Celery verify and ZIP tasks have no time limit; health does not check R2. FCM and webhooks have timeouts. |

### Findings

#### HIGH · 20 Security · An expert can submit again on their own submitted or completed booking and replace the inspection the report uses
- Where: `backend/apps/bookings/submissions.py:241-256` (the "offline start that never reached us" path), `:275-305` (`_advance` does nothing for `submitted` or `completed`); `backend/apps/reports/context.py:21-22` (`latest_inspection` = newest submitted); `backend/apps/reports/handlers.py:21-24` (`booking.updated` on a completed booking renders the report again).
- What:
  - `submit` looks only for a *draft* by the actor. When it finds none (because theirs is already submitted), it creates a new inspection from any published `form_version` of the booking's type and saves it as `submitted`.
  - There is no stage check. The new inspection becomes the "latest", so the booking's chassis column, Ops' view, webhooks and the PDF all switch to it.
  - The Key Checks and ratings Ops made on the first inspection stay on the old row.
  - Experts do not hold `submissions.edit`.
- Evidence: steps (script `resubmit_probe.py`):
  1. Ops creates `REVIEW-SEC-555c39`, assigned to `expert`.
  2. The expert uploads the selfie, starts, and submits with chassis `REVIEW-GENUINE`. The booking becomes `completed`.
  3. The same expert POSTs `/bookings/<id>/submit` again with a new `client_submission_uuid`, `form_version: 7` and chassis `REVIEW-TAMPERED`. The answer is **200**.
  4. Result:
     ```
     inspection ab228eb7… submitted … REVIEW-GENUINE
     inspection 4f31c0e3… submitted … REVIEW-TAMPERED
     chassis column REVIEW-TAMPERED | latest REVIEW-TAMPERED
     ```
  5. The timeline only shows `('changed', ['inspection'], {})`.
- Why: an expert who wants to hide a fault (or a buggy app retry with a fresh UUID) rewrites a finished, Ops-reviewed inspection. The customer's PDF is made again from the new answers, without the Key Checks, and nobody is warned. The same path lets an expert whose job was moved away submit onto a booking another expert already completed. That one is flagged as a conflict, but the report is still rebuilt from the newest inspection before Ops resolve it. Arguably Critical (a wrong report reaches a customer).
- Fix: in `submit`, refuse (409 `ALREADY_SUBMITTED`) when the actor already has a submitted or superseded inspection on this booking and the UUID is new; never let a non-assigned submit change `latest_inspection` for the report before Ops resolve the conflict. S.

#### MEDIUM · 21 Privacy · Changed values of fields hidden from experts go into the expert's notification
- Where: `backend/apps/notify/handlers.py:119-121` and `:60-65` (`_changed`); `:79` (`who` = customer_name).
- What:
  - When Ops edit an assigned or in-progress booking, the expert gets a bell row. If one key changed, the body reads "Label: old → new"; for several keys, it lists their names.
  - Only `QUIET` keys are skipped. The booking form's field levels (`levels_for(..., "expert", stage)`) are never checked.
  - The customer name is put in every body whatever its level.
  - Bell rows are kept 30 days and served by `GET /notifications`.
- Evidence:
  ```python
  elif "assigned_expert" not in changes and set(changes) - QUIET:
      to_user(expert, b, "changed", f"{bid} details changed",
              _changed({k: v for k, v in changes.items() if k not in QUIET}))
  ```
  Local data has no booking field hidden from experts today (shell: `assigned [] in_progress []`), so this is latent, not shown live.
- Why: an Admin hides, for example, "quoted price" or "lead source" from experts. Ops change it from 5000 to 6000, and the expert's phone shows "Quoted price: 5000 → 6000". This breaks the field access matrix that `activity.for_user` respects on the same data.
- Fix: filter `changes` (and `who`) through `levels_for(booking_form_version(), "expert", b.stage)` before building the body, the same way `activity.for_user` does. S.

#### MEDIUM · 20 Security · Two grantable permissions are in effect Admin access: `api_keys.manage` and `integrations.manage`
- Where: `backend/apps/accounts/catalog.py:28-29` (both grantable); `backend/apps/integrations/apikeys.py:27-37` (keys act as an **Admin-role** service user); `backend/apps/bookings/services.py:252` (Admin deletes any booking); `backend/apps/integrations/views.py:232-244,282-309` (Preview and Test send build the full payload of **any** booking).
- What:
  - Anyone granted `api_keys.manage` can mint a key with scope `["*"]` and `allow_delete`. Through `/ext/...` that key then edits any field regardless of field access and deletes completed bookings (Admin-only on the web).
  - Anyone granted `integrations.manage` can POST `/integrations/preview` with `{"booking": <any uuid>, include_data: true, fields: []}`. The response holds every answer of that booking, start and end included, ignoring hidden fields and `submission_roles`. Test send POSTs the same data to any public URL.
- Evidence: the `Preview.post` body returns `"body": json.dumps(...)` of `build_payload`; `_booking_for` does `get_object_or_404(Booking, pk=...)` with no scope or field check. `service_user()` has `role=Role.ADMIN`.
- Why: an Admin who ticks "Manage API keys" for Ops on the Roles page gives Ops Admin delete power and full data access without knowing it.
- Fix: mark both `grantable=False`, or label them "Admin-equivalent" in the catalog and the Roles UI. S.

#### MEDIUM · 20 Security · Anyone can lock any account, and the login answer says which usernames exist or are disabled
- Where: `backend/apps/accounts/services.py:31-47`; `backend/vayu/settings/base.py:91` (`login: 20/min` per IP).
- What:
  - Five wrong passwords lock the account for 15 minutes, whoever sends them.
  - A disabled or locked account is reported as such *before* the password is checked.
  - An unknown username skips the hash, so it answers faster.
- Evidence:
  ```
  POST /auth/login {"username":"api-key-service","password":"wrong"} -> 403 {"code":"ACCOUNT_DISABLED"}
  POST /auth/login {"username":"review-nobody-xyz",...}             -> 401 INVALID_CREDENTIALS
  ```
- Why: usernames follow a pattern (`expert3`, `expert4`…). One script at 20 tries per minute per IP keeps every expert locked out on inspection day. The different answers confirm which accounts exist.
- Fix: return the same 401 for unknown, disabled and wrong-password; check the password before saying "locked"; add a per-IP failure counter (or a longer window with a CAPTCHA-free backoff) instead of a hard per-account lock. S.

#### MEDIUM · 21 Privacy · Copies of customer files stay in R2 after removal and after the retention purge
- Where:
  - `backend/apps/media/services.py:325,480`: `MediaZip.objects...delete()` deletes the row but not the object `zips/<id>.zip`.
  - `:481`: `delete_asset` removes the original and the preview but not the print copies `print/<id>-1000.jpg` and `-600.jpg`.
  - `backend/apps/media/tasks.py:88`: the purge covers only `photo` and `video`. Signatures and documents (`file`) are never purged.
  - No task removes ZIPs older than 7 days.
- What: the "Photo and video storage" setting promises the files are deleted, but ZIP copies (photos, signatures, documents), print copies and all `file`/`signature` uploads stay for ever.
- Evidence: read-only listing of the local bucket: `zip objects 2 with a row 1 orphans 1`. The orphan is a full photo ZIP with no DB row, so nothing will ever delete it.
- Why: a customer asks for their photos and ID copy to be removed. Ops replace or remove them, or the 90-day purge runs, but the old ZIP (with the signature and RC copy) and the print JPEGs remain readable by anyone holding the R2 key, and are counted in the storage bill. This is worse than R-04 / R-18: it happens without any booking being deleted.
- Fix: delete `z.key` whenever a MediaZip row is deleted (a model `delete` or a `post_delete` signal); add `print_keys` to `delete_asset`; add a daily task for ZIPs older than ZIP_LINK_DAYS; decide the retention rule for `file`/`signature`. S.

#### MEDIUM · 21 Privacy · Ops ZIP links and webhook ZIP/PDF links give anyone 7 days of access to all customer photos, signatures and documents
- Where: `backend/apps/media/views.py:147-163` (`ZipDownload`: `AllowAny`, signed token); `backend/apps/media/zips.py:18` (`image` = photo + signature + file); `backend/apps/integrations/webhooks.py:213-226` (PDF presigned for `WEBHOOK_LINK_DAYS`, ZIP link unauthenticated).
- What: the "Download ZIP" link Ops paste into Slack, and the links in webhook bodies, are bearer links valid for 7 days. They cannot be revoked one by one, and an opening is not logged anywhere (`Download` of the PDF *is* logged on the timeline; ZIPs are not).
- Evidence: `token_for` is `TimestampSigner(...).sign(zip_id)` with `max_age=ZIP_LINK_DAYS*86400`; the view has `authentication_classes = []`.
- Why: a Slack message forwarded outside the company, or a webhook receiver's logs, gives a stranger the customer's signature and document scans for a week with no trace.
- Fix: for the Ops ZIP, require a signed-in session (redirect to login) or shorten it to hours; log each download on the booking timeline; leave out `signature`/`file` from shared links unless asked. S.

#### MEDIUM · 28 External services · R2 calls have no timeouts on the web request path, so a slow R2 can take the whole API down
- Where: `backend/apps/media/storage.py:8-13` (a `Config` without `connect_timeout`, `read_timeout` or `retries`); `infra/docker-compose.prod.yml:16` (`gunicorn -w 4`, sync, default 30 s timeout). Calls made inside a request: `media/initiate` (create_multipart), `GET media/<id>` (list_parts), `complete` (list_parts + complete), report `Preview` (reads every photo), `FormAssetUpload`, the `Pictures` POST.
- What:
  - botocore's defaults are a 60 s connect timeout, a 60 s read timeout, and up to 5 attempts.
  - With R2 slow, four phones polling upload progress are enough to fill every worker. Login and every other endpoint then queue, and gunicorn kills the workers after 30 s (502).
  - The resulting `EndpointConnectionError` is not caught (500, HTML).
- Evidence: `client()` builds `boto3.client("s3", ..., config=Config(signature_version="s3v4", s3={"addressing_style": "path"}))`, with no timeouts. A new client is also built on every call.
- Why: on a field day with patchy R2 (or a Cloudflare incident), Ops cannot open the Today page because upload polls hold every worker.
- Fix: `Config(connect_timeout=5, read_timeout=15, retries={"max_attempts": 2, "mode": "standard"})`, cache the client per process, and map `BotoCoreError`/`ClientError` to a 503 `STORAGE_UNAVAILABLE`. S.

#### MEDIUM · 28 External services · Celery tasks that read R2 have no time limit, and health does not check R2 or the workers
- Where: `backend/apps/media/tasks.py:27` (`verify_asset`), `backend/apps/media/zips.py:110` (`build_zip`) are plain `@shared_task` with no limits; `infra/docker-compose.prod.yml:27` (`worker -Q default -c 4` also carries webhooks and pushes); `backend/apps/core/views.py:24-43` (checks DB and Redis only).
- What:
  - A hung R2 stream blocks a worker slot for ever: no soft or hard limit, and boto3's 60 s read timeout restarts per chunk.
  - Four big video ZIPs or verifies at once stop webhooks and push for everyone.
  - Nothing reports R2 as down: health stays "ok", and only individual task errors reach Sentry.
- Evidence: `reports/tasks.py:72` and `integrations/tasks.py:20` do set limits; media tasks do not.
- Why: jobs stay in "submitted" (files never verified) and webhooks to the ERP stop, while the dashboard looks healthy.
- Fix: add `soft_time_limit` to `verify_asset` (for example 600) and `build_zip` (for example 1800), give ZIPs their own queue, and add an R2 `head_bucket` to `/health` or to a beat task that alerts. S.

#### LOW · 20 Security · Access tokens outlive a promotion to Admin: "Admins are refused on the app" holds only at sign-in
- Where: `backend/apps/accounts/views.py:52-55` (the check happens only at login); `:236-259` (`perform_update` revokes devices only on deactivate); `backend/apps/accounts/authentication.py:16-21` (no role check).
- What: an Ops user promoted to Admin keeps a working app session (refresh lasts 60 days) with every Admin permission on the phone.
- Evidence: code as cited. Promoting someone never touches `Device`.
- Why: Admin powers (delete any booking, reset passwords via the API) end up on a phone, against REQUIREMENTS, and that phone's tokens sit in plain SharedPreferences (R-19).
- Fix: revoke devices when the role changes, and refuse JWT auth for `role == admin` in `DeviceJWTAuthentication`. S.

#### LOW · 20 Security · Creating a booking with `assigned_expert` skips the `bookings.assign` permission
- Where: `backend/apps/bookings/views.py:22` (create needs only `bookings.create`); `backend/apps/bookings/services.py:96-97`.
- What: `services.create` assigns the expert straight from the answers. `edit` forbids `assigned_expert` (`ACTION_ONLY`) but `create` does not, and field levels are not checked on create either.
- Why: if an Admin removes "Assign experts" from Ops but leaves "Create bookings", Ops can still assign by creating.
- Fix: in `create`, require `bookings.assign` when `assigned_expert` is present, and apply `levels_for(version, role, "draft")` as `edit` does. S.

#### LOW · 20 Security · Login is not CSRF-protected (login CSRF)
- Where: `backend/apps/accounts/views.py:37` (`authentication_classes = []`, so DRF does no CSRF check).
- What: another site can sign a browser into an attacker's Vayu account.
- Why: low impact here (internal staff tool), but an expert could end up filling an inspection under someone else's login without noticing.
- Fix: `@method_decorator(csrf_protect)` on the web branch, or check `Origin` against `CSRF_TRUSTED_ORIGINS`. S.

#### LOW · 20 Security · A malformed promotion bundle gives a 500 instead of a 400
- Where: `backend/apps/forms/promote.py:177-187` (`p.get("sections")`, `s.get("fields")` on values that may be strings); `:198-245`; `_conflicts` and `_import_lists` index `f["key"]`, `m["items"]` outside the try.
- What: only `_check_content` catches KeyError, TypeError and AttributeError; `_check_shape`, `_conflicts` and `_import_lists` run before it or outside it.
- Why: an Admin importing a hand-edited bundle gets a blank 500 and a Sentry event with the whole bundle in its locals (R-05).
- Fix: wrap the whole import in the same `except (KeyError, TypeError, AttributeError) → INVALID_BUNDLE`. S.

#### LOW · 20 Security · Webhook header secrets are returned in clear to every holder of integrations.manage
- Where: `backend/apps/integrations/views.py:163-170` (`"headers": i.headers`); `models.py:17`.
- What: tokens put in headers (`X-Token: abc`) are stored in plain text and sent back in every GET and listing.
- Fix: mask values on read (show the last 4 characters) and keep the value when PATCH sends the mask back. S.

#### LOW · 20 Security · The push-token docstring promises "only the device that sent it last"; the code pushes to every device holding the token
- Where: `backend/apps/notify/views.py:17-20` vs `backend/apps/notify/tasks.py:23-28`.
- What: if the same FCM token sits on two live devices of different people (a shared phone, nobody signed out), both people's notices wake that phone. The content is not leaked (the push carries only the id, and the app reads its own rows), so harm is small. The stated rule is not implemented.
- Fix: when saving a token, clear it from every other device row (`Device.objects.filter(push_token=token).exclude(pk=device_id).update(push_token="")`). S.

#### LOW · 21 Privacy · Gunicorn access logs keep customer search terms and bearer tokens from URLs
- Where: `infra/docker-compose.prod.yml:16` (`--access-logfile -`); query and path values such as `/bookings?search=<name or phone>`, `/verify/<report token>`, `/zips/<signed token>`, `/verify/<token>/photos`.
- What: the default access log line includes the full path and query.
- Why: anyone with log access can rebuild customer lookups and reuse the report and ZIP links (R-09).
- Fix: use a custom `--access-logformat` without the query string, and with token path segments redacted. S.

#### LOW · 20 Security · Form settings that decide who sees submissions are changed without an audit row
- Where: `backend/apps/forms/views.py:94-98` (FormViewSet uses the default `update`, with no `perform_update` audit).
- What: PATCH `/forms/<id>` with `submission_roles` or `is_active` is not in the audit log. Field `access` edits are audited only as part of the later publish.
- Fix: add `perform_update` with `audit.record("form.update", ...)` listing the changed attributes. S.

#### NOTE · 28 External services · Behaviour per service
| Service | Receives | Keys live in | When down or slow | How we notice |
|---|---|---|---|---|
| R2 / S3 | All media, previews, print copies, PDFs, ZIPs, form pictures, APKs | env `S3_ACCESS_KEY_ID/SECRET` in `.env.prod` (one key, full bucket) | Request path: up to minutes per call, then 500 or 502 (see Medium above). Tasks: hang without limit | Sentry only (health stays ok) |
| Firebase FCM | Only `{"id": "<bell row id>"}` and the device token (`notify/tasks.py:25`) | Service-account JSON path `FIREBASE_CREDENTIALS_FILE`; access token cached in Redis 50 min | 10 s timeout per call; an exception aborts the rest of that push batch (no retry); bell rows are still saved | `log.warning` and Sentry |
| Sentry | Exceptions with request body and locals (R-05) | `SENTRY_DSN` env (required in prod) | SDK queues in the background and drops; no effect on requests | n/a |
| Webhook receivers | Full answers (booking, inspection, start, end) unless `fields` is set; 7-day PDF and ZIP links | Admin-entered URL and headers in the DB | 10 s timeout, retries 1m to 12h, then `failed`; the SSRF guard checks DNS and the connected peer | Delivery log in the web UI |
| Redis (broker, cache) | Booking ids in task arguments, throttle counters, FCM token | internal network, no password | Login, verify and the zip endpoints throttle via the cache, so they answer 500 (not checked live); `.delay()` after commit raises | health 503 |

#### NOTE · 21 Privacy · Where customer personal data is written
DB:
- `Booking.answers` and its columns (name, phone, address, city).
- `Inspection.answers` (owner phone, GPS, etc.).
- `Notification.body` (customer name and changed values; 30 days).
- `Delivery.booking_ref` and `context.booking_id_change`.
- `AuditLog.summary` (Booking ID only). `BookingActivity.changes` keeps only SAFE_KEYS (good).

R2: originals; previews; `print/`; `reports/<booking>/rev<n>.pdf` (old revision deleted; current never purged); `zips/`.

Other copies:
- Logs: access-log URLs; Sentry (R-05).
- Webhooks: full data.
- Push: id only (good).
- CSV export: counts only, with `csv_safe` (good).
- Public verify page: Booking ID, car, type, date, overall word.

Retention:
- Bells: 30 days.
- Photos and videos: setting, completed bookings only (R-18).
- Files, signatures, PDFs, ZIPs, print copies, MediaZip rows, Delivery rows, Device rows, AuditLog: kept for ever.
- No erasure path for one customer apart from deleting the booking (which leaves R2 files, R-04).

#### NOTE · 20 Security · JSON bodies are capped at 2.5 MB (`DATA_UPLOAD_MAX_MEMORY_SIZE`)
A 3 MB login body gets Django's HTML 400 page; a 2 MB body gets 401. This protects against large bodies, but a promotion bundle carries pictures as base64 (2 MB each). Two pictures in one bundle will fail with an HTML 400 that the UI cannot read. This is a usability limit, not a hole.

### Strengths worth keeping
- Object scoping is consistent. An expert got 404 or 403 on another expert's booking for every one of 25 routes tried (booking, activity, inspections, inspection, media, media url, media list, report, download, zip, forms, submit, users, audit, integrations, api-keys, settings, forms, PDF templates). `stuck-uploads` and search returned only their own bookings.
- The SSRF guard is solid: https only, DNS checked, then the actually connected peer is checked (`webhooks.py:75-115`), redirects are off, and path values are percent-encoded with `safe=""`. WeasyPrint is limited to `data:` URLs (`render.py:520`); report text uses a Jinja sandbox with only names allowed, plus nh3 and a `url(`/`@import` filter (`placeholders.py`).
- Field access fails closed in reads, search (`searchable_stages`), the answer filter (`_visible`), the timeline and ZIP exclusions. Hidden keys are refused on write whatever the value, so a 403 cannot be used to guess values (`services.py:117-121`).
- Secrets: API keys are stored as SHA-256 hashes and compared in constant time; report tokens have 192 bits; signed ZIP tokens; avatars are re-encoded with EXIF and GPS removed and a pixel limit; the audit log is append-only via a DB trigger (`accounts/migrations/0002`).
- Wipe commands are guarded (`e2e_reset` refuses non-e2e settings, `seed_demo` an allow-list, `seed_test_data` needs `SERVER_KIND` plus the name typed back). `check --deploy` is clean apart from W008 and W021.


## Appendix D: Backend: setup, API, performance, cost, logging, CI

### Coverage
- Files read: about 45. Folders: `backend/vayu/settings/*`, `vayu/urls.py`, `vayu/celery.py`, `apps/*/urls.py`, `apps/bookings/{views,serializers,models,sync,dashboards}.py`, parts of `submissions.py` and `activity.py`, `apps/forms/access.py` (levels_for), `apps/media/{models,tasks,zips,views}.py`, parts of `services.py`, `apps/reports/{tasks,render(print_image),context(photo_items/media)}.py`, parts of `views.py`, `apps/integrations/{views(body/list),ext_views,webhooks(payload)}.py`, `apps/notify/views.py`, `apps/core/{views,middleware,logging,exceptions,errors,app_settings}.py`, all of `apps/core/setup/{build,lists,forms,reports}.py`, the guard and wipe parts of `testdata.py` and the photo rules in `clappia.py`, the commands `setup_platform`, `seed_test_data`, `freeze_forms`, `e2e_reset`, `bench_pdf`, `flag_stuck_uploads`, the guard in `seed_demo`, `infra/*`, `backend/Dockerfile`, `.github/workflows/ci.yml`, `perf/locustfile.py`, `scripts/local.sh`, `README.md`, `docs/local.md`, `docs/benchmarks.md`, `.env.example`, `docs/clappia/README.md`, and the `mapping_worklist.json` summary.
- Tools run:
  - I copied `vayu_local` into a throwaway database (`pg_dump | psql`, so I only read `vayu_local`). On the copy I counted queries for 47 GETs with `CaptureQueriesContext` and the Django test client, as admin, ops and expert. I then copied every booking 12 times (49 → 588 bookings, 384 inspections) and counted again.
  - On the same copy: `bench_pdf` (150 photos), and `manage.py check --deploy` with prod settings.
  - Local bucket sizes and DB table sizes (read-only).
  - `spectacular` regenerated and diffed against the committed file, then a YAML scan of `openapi.yaml`.
  - An error-code grep (131 codes) against docs, web and Android.
  - `setup_platform`: on a fresh throwaway database with its own throwaway bucket, I ran it twice, then simulated Admin edits and ran it again (inside rollbacks).
  - A script that compares the frozen forms with the Clappia read-out field by field.
  - `gh run list` / `gh run view` for CI timings.
  - Afterwards I deleted both throwaway databases and the bucket. Git state is unchanged.
- Not checked:
  - The p95 load test. Locust needs staging, and the local stack is shared with the owner's review.
  - Real R2 object sizes and real phone photo and video sizes. The demo media are synthetic (about 21 KB per photo), so the cost figures are estimates from code settings and REQUIREMENTS volumes.
  - Whether web and Android parse responses the same way (other slices cover that).
  - CI history before the last 12 runs.
  - A fresh clone in a container. I only checked that every command and file the docs name exists.

### Scores
| Aspect | Score | One-line reason with evidence |
|---|---|---|
| 5 Setup and form content | Weak | A second run is idempotent (no changes), but a re-run reverts Admin's published edits, takes over and publishes Admin's draft, and overwrites the shared disclaimer. With a real spec change it crashes (`build.py:64-72,100`). The mapping to Clappia is faithful. |
| 18 API contracts | OK | Committed OpenAPI = generated, but 94 of about 150 operations have no response schema and there are 0 documented 4xx. Errors come in 4 shapes, and 110 of 131 codes are undocumented. |
| 22 Performance | Weak | `/sync/jobs` is N+1: 225 queries / 0.9 s for 22 jobs, 1556 queries for 253 jobs, 3596 queries with `since`. `bench_pdf` passes with an empty PDF. Other lists are flat (bookings: 23 queries at 588 rows). |
| 23 Running cost | OK | About 0.2–0.35 GB per inspection, mostly video. Expired ZIPs (full copies of the media) are never deleted from R2. |
| 27 Logging and observability | Weak | The stuck-upload alert is never emitted (nothing schedules it). Access logs carry customer search terms and report tokens. Task logs can't be tied to a request or a booking. |
| 29 Build, CI and dev setup | OK | Backend pytest alone takes 28.5 min in CI. The README env path is broken, and the J8 setup commands are not documented. (CI being red is R-01.) |
| 31 Deployment readiness | OK (notes) | `PUBLIC_BASE_URL` defaults to localhost in prod and is missing from `.env.example`. Other gaps are listed below. |

### Findings

#### HIGH · 5 Setup and form content · Re-running `setup_platform` reverts Admin's live form edits, publishes Admin's draft and overwrites the shared disclaimer; with a real spec change it crashes
- Where: `backend/apps/core/setup/build.py:57-73` (compares against the live version and takes over any existing draft), `build.py:100` (deletes the draft's fields), `apps/core/setup/reports.py:186-195` (`shared.save` of theme and disclaimer on every run), `reports.py:216-219`. The claim in `apps/core/management/commands/setup_platform.py:5-7` ("Safe on any server … never deletes anything") is false.
- What:
  - "Unchanged" means "the live version equals the setup spec". After an Admin changes the form in the builder, the next run publishes the setup spec over it.
  - If the Admin has a draft open, the setup uses *that* draft: it deletes its fields and publishes it.
  - The theme and disclaimer shared items are re-saved from the setup files on every run.
  - When a spec really changed, `_fill` creates the new sections while the old ones still exist, so every section key becomes `<key>_2`. Report templates then point at missing sections, and the whole run crashes with `SHARED_BLOCKED` (it rolls back).
- Evidence: on throwaway DB `vayu_review_setup`:
  1. Run 1 published everything. Run 2 printed "unchanged" for all forms, and table counts were identical.
  2. Admin changed a booking-form label and published v2. `build.apply` for booking then printed `published v3` with `admin label kept? False`.
  3. Admin edited the disclaimer to rev 2 ("ADMIN LEGAL"). `_shared` then wrote `disclaimer after rev 3 False`.
  4. The full re-run raised: `SHARED_BLOCKED … "PDI: Section 'car_documents' is not a section of the form."`
  5. The new PDI live version had sections `['air_conditioning_2', 'axle_2', …]`, and the Admin's open draft (id 8, label "ADMIN DRAFT WORK") had been taken over and published without the edit.
- Why: in production, someone re-runs setup to add a new city or to ship one form fix. The Admin's agreed changes to the booking form and the legal disclaimer silently go back to the setup copy, and Admin's half-done draft is published under their name. Alternatively the command dies with a traceback, so setup changes can never be shipped to a live server.
- Fix: setup only creates what is missing. Once a form, template or shared item exists, report "differs from setup" and change nothing unless `--force <form>` is given. Never touch a draft it did not create. Keep section keys when refilling. Size M.

#### HIGH · 22 Performance · `/sync/jobs` (the expert phone's main call) runs queries per job; 0.9 s for 22 jobs on the local data
- Where: `backend/apps/bookings/sync.py:37-57`. Per booking it calls `current_versions(b)` (`submissions.py:61`, one query), `b.inspections.filter(...).first()` (`sync.py:45`, one query) and `BookingSerializer(b)` (reschedules and FKs are not prefetched, because `jobs_for` only uses `select_related("report")`, `sync.py:31`). With `since` it also calls `activity.for_user` per booking, which runs `levels_for` (4 queries plus a loop over all fields) per booking and per inspection part (`activity.py:35,50`).
- What: query count and time grow with the number of jobs. This is the call every expert phone makes to load "My leads".
- Evidence (test client, expert user):
  - Local data (22 jobs): 225 queries, 901 ms, 869 KB.
  - Copy with 253 jobs: 1556 queries, 2.1–7.2 s.
  - `?since=…`: 3596 queries, 4.4 s.
  - `?have=<all>`: 1493 queries.
  - Top tables: `bookings_inspection` 506, `accounts_user` 270, `bookings_reschedulelog` 253.
- Why: REQUIREMENTS asks for p95 under 500 ms with 175 experts. A single expert with a normal 3-week list already takes about 0.9 s on a laptop, and each sync with `since` (the "Ops changed" banner) is 2–3× worse. Morning syncs from 150 phones will queue on 4 gunicorn sync workers.
- Fix:
  - `prefetch_related("reschedules__by", "inspections")` plus `select_related` of the FKs on `jobs_for`.
  - Compute `current_versions` and the draft from the prefetched inspections.
  - Cache `levels_for(version, role, stage)` per request (one dict, as `BookingSerializer` already does).
  - Add a query-count test.
  - Size M.

#### HIGH · 27 Logging and observability · The "stuck upload" alert is never sent: the only code that emits it is a command nothing schedules
- Where: `backend/apps/media/management/commands/flag_stuck_uploads.py:13` is the only `events.emit("alert.stuck_upload")`. `vayu/settings/base.py:122-127` (`CELERY_BEAT_SCHEDULE`) has no entry for it. `infra/docker-compose.prod.yml` has no cron, and no doc mentions running it.
- What: notify handlers (`apps/notify/handlers.py:14,25`) and webhooks (`apps/integrations/webhooks.py:30,38`) are wired for `alert.stuck_upload`, but the event never fires in a deployed stack.
- Evidence: `grep -rn "flag_stuck_uploads"` finds only the command itself. `grep -rn "alert.stuck_upload"` finds only the handlers, the webhook catalogue, the command and seed_demo.
- Why: a phone's photos stop uploading. Ops are never notified and an integration listening for `alert.stuck_upload` never receives it. The booking just sits in "Uploading" until someone happens to open the Problems page. Together with the next finding (verify tasks lost on restart), stuck files are noticed only by chance.
- Fix: add `"flag-stuck-uploads": {"task": …, "schedule": 900}` (make the command body a task) and a test that the beat schedule names it. Size S.

#### MEDIUM · 22 Performance · A ZIP whose build fails or whose worker is restarted stays "Preparing…" for 7 days
- Where: `backend/apps/media/zips.py:110-139` (no `except`, so a failure never sets `failed`; no time limit), `zips.py:100-103` (`request_zip` returns any non-failed ZIP younger than 7 days).
- What: if streaming a file from R2 fails, or the worker is killed mid-build (a deploy), the row stays `status="building"`. Every later request (Ops button, customer report link `media_links.py:80`, webhook payload `webhooks.py:224`) gets that same row back.
- Evidence: the code path. `build_zip` only writes `status` on success (line 136) or on "no assets" (line 118). `request_zip` line 102 `if z is not None and z.status != "failed" and fresh(z): return z`.
- Why: a customer taps "Download photos" on their report and sees "Preparing…" forever for a week. Ops cannot get the files to send instead, and the webhook receiver gets a dead link.
- Fix: wrap the build in try/except and set `failed`. In `request_zip`, treat a `building` row older than about 30 min as failed. Give `build_zip` a `soft_time_limit`. Size S.

#### MEDIUM · 23 Running cost · Expired ZIPs are never deleted from R2, and each new request after 7 days stores another full copy
- Where: `backend/apps/media/zips.py:92-107` (a new `MediaZip` and object when the old one is stale; the old object stays). The only ZIP deletion is in `media/tasks.py:102-105` (`purge_expired`, only for bookings whose media were purged, and retention defaults to 0 = keep forever, `core/app_settings.py:11`). The repo has no R2 lifecycle rule (`grep -i lifecycle` finds nothing).
- What: ZIPs are full uncompressed copies of photos or videos (`ZIP_STORED`). There is one per kind, per set of hidden fields (each role and the customer link get separate ZIPs), and per 7-day window. None is ever removed.
- Evidence: code as cited. Local bucket: `zips/` 2 objects, both kept.
- Why: at REQUIREMENTS volume (500 inspections/month, 3–10 videos each) a single video ZIP per job copies about 100–250 MB. That can roughly double R2 storage. Each webhook with `include_video_zip` that re-fires after a week adds another copy.
- Fix: an R2 lifecycle rule that expires `zips/` after `ZIP_LINK_DAYS` (one bucket setting), plus deleting stale `MediaZip` rows in the hourly purge. Size S.

#### MEDIUM · 22 Performance · `bench_pdf` reports PASS for an empty PDF; the documented benchmark can't be trusted
- Where: `backend/apps/reports/management/commands/bench_pdf.py:44` (default `--field door_photo`) and lines 87-90 (no check that photos were rendered). `docs/benchmarks.md` §1.
- What: if the field is missing or hidden from reports, the PDF has no photos and the command still prints PASS.
- Evidence (copy of local data):
  - `bench_pdf --photos 150` gave `150 photos -> 0.0 MB PDF in 0.8 s (PASS…)`. `door_photo` is not in the PDI form.
  - `--field bonnet_photo` gave 0.0 MB, PASS; a debug spy showed `photo_items: 0 … visible: False`.
  - `--field cover_photo` gave `8.2 MB PDF in 11.5 s`, peak RSS 326 MB. `docs/benchmarks.md` says 1.7 MB in 16.3 s.
- Why: the "150 photos within 2 minutes" requirement can be signed off on staging from a run that rendered nothing.
- Fix: count `<img>` tags (or PDF pages) and fail unless it equals `--photos`. Pick a report-visible photo field automatically. Size S.

#### MEDIUM · 22 Performance · The load test skips the expert phone's real path
- Where: `perf/locustfile.py:58-76` (experts call `/bookings` and `/auth/me`, and log in with `"client": "web"`). The phone uses `GET sync/jobs` (`android/.../core/api/Api.kt:96`). `loadtest/` is an empty folder.
- What: the 175 simulated experts never call `/sync/jobs`, the heaviest endpoint measured above.
- Evidence: the file contents. My measurements: `/bookings` for an expert takes 24 queries / 109 ms, `/sync/jobs` takes 225+ queries / 900 ms.
- Why: the p95 < 500 ms run on staging would pass while real phones are slow.
- Fix: the expert user does JWT login and `sync/jobs?have=…&since=…`. Delete `loadtest/`. Size S.

#### MEDIUM · 18 API contracts · Four different error shapes; 110 of 131 error codes documented nowhere; no 4xx in OpenAPI
- Where: `backend/apps/core/errors.py` (`{"code","detail",…}`), DRF `ValidationError` in views (for example `bookings/views.py:80,97,102,116,130`, `dashboards.py:90`), DRF `NotFound` and `PermissionDenied`.
- What:
  - The same kind of mistake gets different bodies. Some carry a `code` and some don't, and 404s say "Not found." or "No Booking matches the given query.".
  - The code list lives only in code.
  - `openapi.yaml` has 0 documented 4xx responses.
- Evidence: test client.
  - `/bookings?timing=x` → `{"timing":"Use late or quick."}`
  - `/sync/jobs?have=x` → `{"code":"INVALID_QUERY",…}`
  - `/bookings/<uuid>` → `{"detail":"No Booking matches the given query."}`
  - `/dashboards/volume?group=x` → `{"detail":"group must be one of …"}`
  - `/bookings?page=99` → 404 `{"detail":"Invalid page."}`
  - Grep: 131 distinct `err("…")`/`CodedError("…")` codes. 110 appear in no file under `docs/`, in `REQUIREMENTS.md` or in `openapi.yaml`, for example `STALE_BOOKING`, `UUID_CONFLICT`, `CHECKSUM_MISMATCH`, `ACCOUNT_LOCKED`, `PASSWORD_CHANGE_REQUIRED`, `DEVICE_REVOKED`, `LINK_EXPIRED`.
- Why: an integrator (and the Android app) can't write one error parser. A client keyed on `code` treats `{"timing": …}` as "unknown error".
- Fix: the exception handler wraps every DRF error as `{"code": <default_code>, "detail", "fields"?}`. Generate an error-code table in `docs/integrations.md` from the code list. Size M.

#### MEDIUM · 18 API contracts · The OpenAPI file and the "no breaking API changes" gate cover under half the responses (worse variant of R-10)
- Where: `backend/openapi.yaml`, CI step "no breaking API changes (oasdiff)" (`.github/workflows/ci.yml:31-45`).
- What: the committed file matches the generator (I regenerated it and the diff was empty). But 94 of the 150-odd non-DELETE operations have no response body schema at all, and the `Booking` schema lacks the `timing` key added in `BookingSerializer.to_representation` (`bookings/serializers.py:52`). oasdiff therefore can't see changes to most responses.
- Evidence: YAML scan.
  - `non-delete ops with no response body schema: 94`, including `/api/v1/sync/jobs get` (`{'200': {'description': 'No response body'}}`), `/auth/login`, `/auth/me`, `/api-keys`, `/bookings/{id}/media`.
  - `Booking props has timing: False`.
- Why: renaming a field in `sync/jobs` or `auth/me` passes CI and breaks every installed phone, which can't be force-updated quickly.
- Fix: `@extend_schema(responses=…)` (inline serializers) on the APIViews the apps use, starting with sync/jobs, auth, media, notifications and app/latest. Size M.

#### MEDIUM · 18 API contracts · `CHECKSUM_MISMATCH` on upload completion can never happen in production
- Where: `backend/apps/media/services.py:370-373`.
- What: `verify_asset.delay(...)` is queued, then the code immediately runs `refresh_from_db()` and checks `status == "failed"`. That works only with eager Celery (tests). In production verification hasn't run yet, so the client always gets `uploaded`.
- Evidence: code. `CELERY_TASK_ALWAYS_EAGER = False` in `base.py:131`. Only `e2e.py` and `test.py` make it eager.
- Why: a corrupted upload is reported as fine. The phone may delete its local copy, and the file later flips to `failed` with nobody told (see the stuck-upload alert finding).
- Fix: drop the dead branch and document that the phone must poll `media/<id>` (or return 202 "verifying"). Make sure the stuck/failed alert covers `failed`. Size S.

#### MEDIUM · 27 Logging and observability · Access logs hold customer search terms and the report/ZIP bearer tokens
- Where: `infra/docker-compose.prod.yml` (`gunicorn … --access-logfile -`, default format logs the full request line), with tokens in URLs: `reports/urls.py` `verify/<token>` and `verify/<token>/<link>`, `media/urls.py` `zips/<token>`.
- What: the request line includes the query string and path tokens.
- Evidence (`.local/api.log`, same request-line format):
  - `"GET /api/v1/bookings?search=S&stage=completed …"`: search is by customer name or phone digits (`bookings/views.py:117-126`).
  - 66 lines of `GET /api/v1/verify/<full token>`.
- Why: anyone who can read server logs (or a log service they are shipped to) can open a customer's report and photos. The token never expires (R-09). A phone number typed into search ends up in plain logs.
- Fix: a gunicorn `access_log_format` without the query string, with `/verify/*` and `/zips/*` tokens masked (or a small logging filter). Size S.

#### MEDIUM · 27 Logging and observability · A booking's story can't be followed in the logs: task logs carry no request id or booking, and key failures log nothing
- Where:
  - `apps/core/logging.py` (request id only in a contextvar set by `middleware.py`). Celery tasks run with `request_id="-"`, and the Celery worker hijacks the root logger, so `.local/worker.log` is plain text (`[… INFO/SpawnPoolWorker-1] Task …retry_due[…] succeeded`), not the JSON format of `base.py:LOGGING`.
  - Silent failure paths:
    - `media/tasks.py:40-44` (checksum mismatch: file deleted, status failed, no log)
    - `media/tasks.py:56-60` (unreadable image: deleted, no log)
    - `zips.py:110-139` (ZIP failure)
    - webhook success
    - push success (`notify/tasks.py`)
- What: beyond R-16 (few log calls), the existing lines can't be joined. API logs and task logs share no id, and lines carry no booking id field.
- Evidence: I traced booking REVIEW-J1B. The DB has 11 `BookingActivity` rows (created → assigned → stage changes → edits), 26 media rows, 12 deliveries and the report row. The worker log has only Celery's generic "Task … succeeded" lines, with no booking. So the story comes from the database only. Why a photo became `failed` is recorded nowhere.
- Why: when an expert says "my photos vanished", the only trace is a `failed` status with no reason or time.
- Fix:
  - `CELERY_WORKER_HIJACK_ROOT_LOGGER=False`.
  - Pass the request id in task headers (one `before_task_publish` / `task_prerun` signal pair).
  - Use `logger.info(…, extra={"booking": …, "media": …})` on the five silent paths.
  - Size S.

#### MEDIUM · 22 Performance · One Celery queue (4 slots) serves upload checks, ZIP builds, webhooks, pushes and purge; ZIP builds have no limit; tasks are lost on restart
- Where: `infra/docker-compose.prod.yml` (`worker -Q default -c 4`), `base.py:115` (only `render_report` is routed away), `zips.py:110` (no `time_limit`; temp file on container disk). There is no `CELERY_TASK_ACKS_LATE` or prefetch setting.
- What:
  - Four video-ZIP builds take every slot. A ZIP streams up to 10 videos × 300 MB (`media/services.py:31` limit) to `/tmp`, so up to 3 GB per build. Meanwhile `verify_asset` waits, so uploads show as unverified and jobs stay in "Uploading".
  - A deploy restart drops already-fetched tasks (no `acks_late`). Their assets stay `uploaded` forever, and nothing alerts (see the HIGH finding above).
- Evidence: config and code as cited.
- Why: on a busy evening, one customer and one webhook asking for video ZIPs can delay every expert's photo check for minutes, and Ops see jobs not completing.
- Fix: a separate `zips` queue with `-c 1`, a `soft_time_limit`, and `task_acks_late=True` + `worker_prefetch_multiplier=1` for `verify_asset`. Size S.

#### MEDIUM · 5 Setup and form content · The wipe guards trust the settings module, not the database they are wiping
- Where: `backend/apps/core/setup/testdata.py:50-62` (`SERVER_KIND` from settings; the "real bookings" check runs only when kind is `test`), `vayu/settings/local.py:6-16` and `e2e.py:5-15` (`os.environ.setdefault`, so DB/S3 environment variables already set win), `local.py:29` hard-codes `SERVER_KIND, SERVER_NAME = "local", "local"`. `e2e_reset.py:19` checks only `SETTINGS_MODULE`.
- What: run inside the production container (which has `DB_*` and `S3_*` set from `.env.prod`), `python manage.py seed_test_data --settings vayu.settings.local --confirm local --password …` passes all three guards and wipes the production database and bucket. `e2e_reset --settings vayu.settings.e2e` does the same with no confirmation at all.
- Evidence: code as cited (the guard reads `settings.SERVER_KIND`, which `local.py` fixes to "local" regardless of `DB_HOST`).
- Why: one wrong flag during a support session deletes every booking and photo. Backups are not set up yet (before launch).
- Fix: store the server kind in the database (a row written by `setup_platform`, "production" by default) and check that. Always run the "bookings not made by test data" guard. Size S.

#### MEDIUM · 29 Build, CI and dev setup · Backend CI takes about 30 minutes before the coverage gates even start
- Where: `.github/workflows/ci.yml:50-59`.
- What: one pytest process runs 2983 tests in 28.5 min. Then 9 more pytest runs re-execute subsets for the 100% gates. That is roughly another 10–20 min, which I could not observe because every recent run fails at step 1.
- Evidence: `gh run view` for the latest run (ab75050's predecessor):
  - The step "Run uv run pytest --cov --cov-fail-under=85" ran 18:10:29 → 18:39:01.
  - Its result: `1 failed, 2983 passed … in 1708.80s (0:28:28)`, failing `test_sharing.py::test_damaged_pictures_in_a_file` (`'INVALID_IMAGE' == 'INVALID_BUNDLE'`).
  - "critical areas need 100% branch coverage" was skipped.
- Why: a 45-minute red-or-green loop is one reason CI is ignored (R-01).
- Fix: `pytest -n auto` (xdist, one DB per worker). Compute the 100% gates from the single `.coverage` with `coverage report --include=… --fail-under=100` instead of re-running tests. Size S.

#### MEDIUM · 29 Build, CI and dev setup · A fresh server setup (J8) is not documented, and the README's env instructions don't work
- Where: `README.md` "Local secrets", `.env.example`, `backend/manage.py:6`.
- What:
  - The README says to run `uv run --env-file .env.local python manage.py runserver`, but `manage.py` defaults to `vayu.settings.prod`, which requires `SENTRY_DSN` and secure cookies.
  - `.env.example` lists `R2_*` and `SENTRY_ENVIRONMENT`, which no settings file reads. It says "Local development uses the STAGING bucket", which contradicts `docs/local.md` (s3proxy).
  - It lacks `PUBLIC_BASE_URL`, `VERIFY_BASE_URL`, `VAYU_SERVER_KIND`, `VAYU_SERVER_NAME`, `MIN_APP_VERSION` and `STUCK_UPLOAD_HOURS`.
  - No doc mentions `setup_platform`, the users CSV or `seed_test_data`.
- Evidence: a grep of the settings' `env("…")` names against `.env.example`. `grep -rn "setup_platform\|seed_test_data" docs/*.md README.md` returns nothing (review docs excluded).
- Why: the first production setup will be done from memory, and the env file copied from `.env.example` misses the variables that decide links and wipe safety.
- Fix: a `docs/setup-server.md` (env list, `migrate`, `setup_platform --users`, first sign-in). Sync `.env.example` with `env()` calls and add a test that compares them. Size S.

#### MEDIUM · 31 Deployment readiness · `PUBLIC_BASE_URL` falls back to `http://localhost:8000` in production
- Where: `backend/vayu/settings/base.py:123`, not required in `prod.py` and missing from `.env.example`. It is used for webhook ZIP links (`integrations/webhooks.py:226-227`).
- What: a production server set up from `.env.example` sends webhook payloads with `image_zip_url: "http://localhost:8000/zip/…"`.
- Evidence: code as cited, and the `.env.example` grep above.
- Why: the receiving system (the CRM) gets dead links for every booking until someone notices.
- Fix: in `prod.py`, `PUBLIC_BASE_URL = env("PUBLIC_BASE_URL")` with no default, so startup fails without it. Size S.

#### LOW · 22 Performance · Smaller N+1s on admin lists and the external API
- Where:
  - `integrations/views.py:169` (`values.broken_refs(i)` per integration)
  - `forms` list (2 queries per form)
  - `library` list (3 per item)
  - `integrations/ext_views.py:79` (`booking_form()` query per booking in `ext/bookings` list)
- Evidence: test client.
  - `/integrations`: 71 queries / 400–650 ms for 7 integrations (`forms_field` 31, `forms_formversion` 19).
  - `/forms`: 21 queries for 7.
  - `/library`: 21 for 7.
- Why: slow Admin pages as integrations grow. Up to 50 extra queries per page for API clients.
- Fix: compute once per request and pass it in. Size S.

#### LOW · 22 Performance · Inspection access levels are recomputed up to 4× per inspection
- Where: `bookings/serializers.py:84-89,97` and `forms/access.py:55-71` (4 queries plus a loop over every field, about 574 fields on PDI, per call, no cache).
- Evidence:
  - `/bookings/<id>/inspections` with 1 inspection: 23 queries (admin), 29 (ops).
  - `/inspections/<id>`: 20 / 26 queries, 60–270 ms.
- Why: grows with the number of inspections per booking (conflicts) and with form size.
- Fix: a per-request `levels_for` cache in the serializer context (the booking serializer already does this). Size S.

#### LOW · 22 Performance · No index for the upload queries that scan all media
- Where: `media/models.py:26,31`.
  - `stuck_uploads()` (`media/services.py:495-498`) filters on `status` and `created_at`.
  - `purge_expired` (`media/tasks.py:92-94`) filters on `kind`, `created_at` and `status`.
  - `pg_indexes` shows only `booking_id`, `uploaded_by_id`, `replaced_by_id` and `client_uuid` on `media_mediaasset`.
- Why: at 500 jobs × 60–150 photos, about 50k rows/month (≈0.6M/year), every Problems page load and every hourly purge does a full scan. Booking filters are R-17.
- Fix: a partial index on `created_at` where `status NOT IN ('verified','purged')`, and one on `(kind, created_at)`. Size S.

#### LOW · 22 Performance · The dashboard summary loads full booking rows for an unbounded date range
- Where: `bookings/dashboards.py:153-155` (`list(Booking.objects.filter(...))`, which includes the `answers` JSON, about 2 KB each, for 2× the range). `_bounds` (`dashboards.py:114-123`) has no maximum span.
- Why: `?date_from=2020-01-01` on a year of data loads tens of thousands of rows into a gunicorn sync worker (30 s default timeout).
- Fix: `.only(...)` the 8 columns used, and cap the span (for example 366 days). Size S.

#### LOW · 22 Performance · Every PDF render re-reads every photo from R2; failed attempts sleep inside the only PDF worker
- Where:
  - `reports/render.py:60-67`: per photo, one DB query plus `storage.exists` (HEAD) plus `storage.read` (GET). 150 photos means 150 queries and 300 R2 calls on each re-render after an Ops edit.
  - `reports/tasks.py:57-68`: retries `time.sleep(15)` inside the `pdf` worker (`-c 1`), and all three attempts share one 300 s soft limit, so a slow first failure is reported as `timeout`.
- Why: slower renders and a wrong failure reason on Ops' Problems page.
- Fix: fetch the asset rows in one query. Use Celery `retry(countdown=…)` instead of sleeping. Size S.

#### LOW · 18 API contracts · Pagination is inconsistent and `page_size` is ignored
- Where: `base.py:85-86` (`PageNumberPagination`, `PAGE_SIZE 50`, no `page_size_query_param`).
- What:
  - Paginated: bookings, users, audit-logs, deliveries, `ext/bookings`.
  - Plain unbounded arrays: integrations, forms, library, master-lists, `problems/reports`, `problems/stuck-uploads`, pdf-templates, `sync/jobs`.
  - `notifications` returns `{unread, results}`, capped.
  - An out-of-range page returns 404.
- Evidence: `/bookings?page_size=200` gave the same 48.5 KB as the default. `/bookings?page=99` gave 404 `{"detail":"Invalid page."}`.
- Fix: document it. Add `page_size_query_param` with a max. Plain lists are fine where they are bounded. Size S.

#### LOW · 27 Logging and observability · Log noise
- Where:
  - `core/views.py:41` logs every health probe at INFO.
  - `weasyprint.progress` logs about 8 INFO lines per PDF, because root is INFO (`base.py:LOGGING`).
  - drf_spectacular prints 200 `W002` warnings on every `manage.py check` and `migrate` (seen in `check --deploy`), and the prod compose runs `migrate` on every API start.
- Fix: set `weasyprint` to WARNING, log health checks only when unhealthy, and silence `drf_spectacular.W002` until R-10 is fixed. Size S.

#### LOW · 27 Logging and observability · Audit log gaps for configuration changes
- Where:
  - `reports/views.py:297-312`: PDF picture rename and delete are not audited (upload is, through `assets.create_asset`).
  - `notify/management/commands/publish_apk.py`: publishing a new app version is not audited.
- Why: "who removed the logo?" or "who pushed the APK?" can't be answered.
- Fix: two `audit.record` calls. Size S.

#### LOW · 5 Setup and form content · Generated passwords are printed to stdout
- Where: `setup_platform.py:82-86`.
- Why: when run through `docker compose run` or CI, the first-login passwords stay in container logs. They are forced to change at first sign-in, so the exposure is short.
- Fix: write them to a 0600 file, or require passwords in the CSV. Size S.

#### NOTE · 5 Setup and form content · Fidelity of the mapping to Clappia (script comparison)
- The data copies are byte-identical to `docs/clappia/*.json`.
- Comparing each Clappia field (formulas, viewers and lookups left out; sections moved to start / end / ratings / Key Checks excluded) with the frozen forms, only 5–6 labels per form are missing:
  - "Radiator Code Support Remark" and "Chasis Remark": left out because their show-rule references a non-field. This is recorded in `frozen/pdi.json` notes.
  - "Engine Capacity" (text): replaced by "Engine Capacity (in CC)".
  - "Driver/Passenger Side Body Chasis": present, relabelled "Chassis".
  - "Car KM Reading" photo (Used Car) and "Auxiliary Battery" radio (EV): relabelled or moved.
- The `required` differences (5–8 per form) are all photos or videos, and come from the agreed photo rules in `clappia.py:476-522`.
- The option-set differences I first found were my label matching hitting the same-named field in another section. On recheck, option sets match, for example the chassis checks include "Not Able to Check".
- Verdict: faithful. The two dropped remark fields should be confirmed with the owner.

#### NOTE · 23 Running cost · Estimate per inspection and per month (R2 storage; egress is free on R2)
- Inputs:
  - REQUIREMENTS: 500 inspections/month, 60–150 photos and 3–10 videos each.
  - Phone photos: ≤2048 px, about 500 KB JPEG (`android/.../Media.kt:26-27`).
  - Server copies per photo: preview 480 px q75 (`media/tasks.py:54-55`), plus print copies at 1000 px and 600 px q80 (`render.py:52,72-75`), so about 0.7 MB stored per photo in total.
  - Video: CameraX `Quality.HD` with no duration limit (`Tools.kt:172`), about 20–40 MB per 30–60 s. The server cap is 300 MB per video.
  - PDF: about 2–8 MB (bench: 8.2 MB for 150 noise photos), with one revision kept.
- Per inspection: photos about 70 MB + videos about 120–240 MB + PDF about 5 MB ≈ **0.2–0.32 GB**. Each ZIP that is requested adds a full copy of the photos and/or videos, which is never deleted (finding above).
- Per month at 1× volume:
  - Storage grows by about 100–160 GB/month (up to about 250 GB with ZIPs). After 12 months that is about 1.2–3 TB, or **about $18–45/month** at $0.015/GB-month. Retention is off by default (`photo_days: 0`).
  - Class A operations: about 7 per photo (multipart parts, preview, print copies), about 0.4M/month, which costs about $2.
- At 10×: about 12–30 TB/year, which is about $180–450/month in storage. Videos and ZIP copies are what drive it, so the cheapest levers are the ZIP lifecycle and a video length or bitrate cap.
- The database is negligible: the largest table locally is 1.5 MB, and submitted inspection `answers` average 2.2 KB.

#### NOTE · 31 Deployment readiness · Known gaps seen in `infra/` (before launch; Caddy, backups and CSP are already known)
- Caddy proxies only `api:8000` (`infra/Caddyfile`). Nothing serves the web build, the `/verify/<token>` page or the `/zip/<token>` page that `PUBLIC_BASE_URL` links point to.
- No container healthchecks. `migrate` runs on every API start (`docker-compose.prod.yml`, api command), which races if the API is ever scaled.
- Gunicorn uses defaults: 4 sync workers, 30 s timeout, no `--max-requests`. The access log has no request id.
- One Redis instance holds the Celery broker, the cache and the throttle counters, with no `maxmemory` policy or persistence settings.
- The beat schedule file is in `/tmp` (fine), but `flag_stuck_uploads` is not scheduled (HIGH above).
- No R2 lifecycle rules (`zips/`, abandoned multipart uploads).
- `check --deploy` with prod settings shows only W008 (TLS redirect at Caddy, fine) and W021 (HSTS preload, optional), plus the 200 spectacular warnings.

### Strengths worth keeping
- The booking list is flat, not N+1: 30 queries at 49 rows and 23 at 588 rows. Levels are cached per (role, stage) in `bookings/serializers.py:38-47`.
- `setup_platform` is truly idempotent when nothing changed. The second run on a fresh DB printed "unchanged" for all 9 items, with identical row counts and a 0.9 s run.
- The committed `openapi.yaml` equals the generated one (empty diff), and CI enforces that plus oasdiff.
- The PDF render is bounded and safe. `render_report` has soft and hard limits (300/330 s), a single-flight claim per booking, and `sweep_reports` recovery (`reports/tasks.py:72-136`). 150 photos rendered in 11.5 s with 326 MB peak RSS.
- The request-id middleware validates the client id before echoing or logging it (`core/middleware.py:7,15-17`). `exceptions.py:23-28` logs only the SQL state, never the refused value.


## Appendix E: Web: code quality, API contracts, tests

### Coverage
- files read: all 124 files in `web/src` (root, `api/`, `lib/`, `rules/`, `ui/`, `pages/` admin/ops/expert, `pages/admin/builder`, `pages/admin/report`, `pages/admin/integrations`, `pages/admin/library`, every `*.test.*`), plus `web/package.json`, `vite.config.ts`, `tsconfig.json`, `playwright.config.ts`, the list of tests in every `web/e2e/*.spec.ts`. Backend read to compare contracts: `backend/apps/bookings/{views,serializers,services,activity}.py`, `apps/accounts/{views,serializers}.py`, `apps/forms/{views,serializers,fieldtypes}.py`, `apps/media/{views,services}.py`, `vayu/settings/base.py` (pagination, time zone).
- tools run: `npx tsc --noEmit` (clean, 8 s); `npx vitest run` (26 files, 1763 tests, all pass, 11.6 s; `integrations.test.tsx` alone 9 s); `npm outdated`; `npm audit` (with and without dev); grep counts for type escapes / lint disables / TODO; a shell script listing exports not used outside their own file (stand-in for depcheck/knip, which are not installed); `git log --since=2026-01-01` change counts for hot spots.
- NOT checked: hand mutation testing by editing code (the brief forbids editing the repo; I reasoned from the test assertions instead, see 19); Playwright e2e not run (brief); bundle size; no live API calls (contract compared by reading serializers for 11 endpoints).

### Scores
| Aspect | Score | One-line reason with evidence |
|---|---|---|
| 4 Long-term maintenance | OK | Hot spots `pages/ops/Booking.tsx` (825 lines, 12 changes this year), `FieldEditor.tsx` (283, 15), `FormBuilder.tsx` (296, 13), `PdfDesigner.tsx` (320, 12); 0 TODO/FIXME/ponytail notes. |
| 6 Structure and modularity | OK | Folder layout followed and pure logic is in `lib/` with tests, but `Booking.tsx` holds 17 components plus stage rules; pages import components from other pages. |
| 7 Reuse and duplication | OK | Same rule written several times with different values: media `max_count` default (4 copies, 3 values), stage words (5 copies), media type list (9 copies), report-designer helpers copied. |
| 8 Clean code | OK | Clear names and short pure functions; 310 lines over 200 characters; some dead exports; autosave can drop the last edit. |
| 9 Design principles | OK | Field-type `switch`/`if` chains in 4 places (renderer, answer view, summary, default config) with no registry; otherwise small focused components. |
| 10 Comments | Good | Comments explain *why* almost everywhere; 4 stale or misplaced ones (Low). |
| 11 Types and static checks | OK | `strict` + `noUncheckedIndexedAccess`, tsc clean, 0 `any`, 0 `@ts-ignore`; but no ESLint at all while 21 `eslint-disable … exhaustive-deps` comments pretend one runs. |
| 12 Dependencies | Good | All 11 runtime deps used; one known runtime advisory (react-router, already R-20); dev-only critical advisory in vitest/tinypool; majors behind. |
| 18 API contracts | Weak | Every `useList` and several `Page<…>` callers read only page 1 of a 50-row paginated list (Users, experts, Today, My leads). `types.ts` is hand-written and has drifted. |
| 19 Testing | OK | Tests check behaviour (render + role queries + mocked fetch) and the 1478 shared rule vectors are strong; the upload pipeline and the expert Job page have no unit test. |

### Findings

#### HIGH · 18 API contracts · Lists silently stop at the first 50 rows (users, experts, today's schedule, my leads)
- Where: `web/src/api/hooks.ts:5-13` (`asList` returns `results` of a DRF page, `useList` never asks for page 2); server `backend/vayu/settings/base.py:87-88` (`PageNumberPagination`, `PAGE_SIZE: 50`), `backend/apps/accounts/views.py:214` (users ordered by username, paginated). Callers: `pages/admin/Users.tsx:18`, `pages/ops/Booking.tsx:77`, `pages/ops/Bookings.tsx:99`, `pages/ops/Today.tsx:37-39` (`Page<Booking>` results only), `pages/expert/MyJobs.tsx:42` (bookings ordered `-created_at`, `apps/bookings/models.py:59`), `ui/FormRenderer.tsx:144` and `ui/AnswerSheet.tsx:38` (`users-by-role`), `pages/admin/Audit.tsx:37` and `pages/ops/Dashboards.tsx:161` (`users-all`), `lib/useTrees.ts:10` (forms).
- What: the server pages every list at 50; the web treats page 1 as the whole list and shows no "more" for these screens.
- Evidence: `export function asList<T>(x: unknown): T[] { … if (… Array.isArray((x as Page<T>).results)) return (x as Page<T>).results;` and `useList` calls `api(path, { query })` once with no `page`.
- Why: with 51+ users the Admin cannot see, edit, reset or deactivate the users after "page 1" alphabetically (e.g. a leaving expert stays active); Ops cannot pick expert #51 in the Assign dialog, the Expert filter or the Today lanes; on a day with 51+ bookings the Today schedule drops boxes (the KPI numbers, which use `count`, then disagree with the lanes); an expert with 51+ leads in total loses the oldest-created ones from "My leads" and every filter count is wrong.
- Fix: make `useList` follow `next` (or pass `page_size`/`pagination_class=None` on small catalogue endpoints like users/forms) and page the Today and My leads lists; add one test that serves a 2-page response. Size M.

#### MEDIUM · 7 Reuse and duplication · Default "most files" per field differs between web, Ops view, field editor and server
- Where: server `backend/apps/forms/fieldtypes.py:30` `DEFAULT_MAX_COUNT = {"photo": 10, "video": 3, "file": 5}`; web `ui/FormRenderer.tsx:205` and `lib/wizard.ts:49` (`video ? 3 : 10` → file 10); `pages/ops/Booking.tsx:427` (`file: 5`); `pages/admin/FieldEditor.tsx:134` shows `cfg.max_count ?? 1`; `lib/fieldTypes.ts:31` new fields get `video ? 1 : 5`. Android `core/forms/FormTree.kt:35` also uses file 10.
- What: four copies of one rule with three different answers.
- Evidence: see the quoted lines; a file field saved without `max_count` is 5 on the server, 10 for the expert, 5 for Ops, and the builder shows "At most 1".
- Why: an expert on web attaches 6–10 documents, the counter says "6/10", and the server refuses the extra ones ("Add at most 5") at upload or submit; an Admin reading "At most 1" in the builder believes the limit is 1.
- Fix: send the effective `max_count` in the form tree (server fills the default) and delete the client defaults. Size S.

#### MEDIUM · 7 Reuse / 9 Design · Booking page offers Reschedule and Assign in stages the server refuses (and the list page uses a different rule)
- Where: `pages/ops/Booking.tsx:89,108-109` (`live` = not cancelled/completed; Assign shown unless cancelled) vs `pages/ops/Bookings.tsx:120-121` (Reschedule only draft/assigned; Assign hidden for in_progress/submitted) vs server `backend/apps/bookings/services.py:161-164,176-177`.
- What: the stage rules for actions are re-typed in each page; the detail page's copy drifted from the server.
- Evidence: Booking.tsx `{can("bookings.reschedule") && live && <button …>Reschedule</button>}`; server `if b.stage not in ("draft", "assigned"): raise err("INVALID_STAGE", …)`. Assign shows "Reassign" on a completed booking; server: `can_transition(completed → assigned)` is refused.
- Why: an Ops user on an in-progress or uploading booking opens Reschedule, picks date, time and reason, presses the button and only then gets "A in_progress booking cannot be rescheduled."
- Fix: one `allowedActions(booking)` helper in `lib/` used by both pages, or better an `actions` list in the booking response. Size S.

#### MEDIUM · 7 Reuse and duplication · Web rules use the UTC date as `_today`; server uses India time
- Where: `web/src/lib/formSpec.ts:11` `const today = () => new Date().toISOString().slice(0, 10);` vs `lib/format.ts:5` (local date) and server `backend/apps/bookings/services.py:30` / `apps/media/services.py:514` (`timezone.localdate()`, `TIME_ZONE = "Asia/Kolkata"`); Android uses `LocalDate.now()`.
- What: `_today` is a documented rule variable (`shared/rule-vectors/SCHEMA.md:34`); the web feeds it yesterday's date between 00:00 and 05:30 IST.
- Evidence: the line above; the shared vectors pass `today` in, so they cannot catch where it comes from.
- Why: once an Admin writes a rule such as "date must not be after today", an expert working on the web after midnight sees a different required/valid result than the server, which then refuses the submit with INVALID_ANSWERS (or the reverse).
- Fix: use `today()` from `lib/format.ts` (local) or the server time the API already returns. Size S.

#### MEDIUM · 11 Types and static checks · No linter runs, yet 21 comments switch a lint rule off
- Where: `web/package.json` (no eslint/plugin-react-hooks; nothing in `node_modules/.bin`); 21 `// eslint-disable-line react-hooks/exhaustive-deps` e.g. `pages/expert/Job.tsx:126,139,148,157`, `pages/ops/Booking.tsx:303,350`, `pages/admin/FormBuilder.tsx:282`, `pages/admin/PdfDesigner.tsx:137,152`.
- What: hook dependency mistakes are the main bug class in this code and nothing checks them; the disable comments are decoration.
- Evidence: `ls node_modules/.bin | grep eslint` → nothing; `grep -rn eslint-disable src | wc -l` → 21. Example of an unchecked case: `FormBuilder.tsx:282` memo depends on `others.length` only.
- Why: a missing dependency (stale value after a refetch) ships unnoticed; reviewers trust the comments.
- Fix: add ESLint with `react-hooks` (rules-of-hooks + exhaustive-deps) to CI. Size S.

#### MEDIUM · 6 Structure and modularity · `pages/ops/Booking.tsx` is the hot spot: 825 lines, 17 components, stage rules inside
- Where: `web/src/pages/ops/Booking.tsx` (Detail, ActivityCard, ConflictBanner, WaitingFiles, BookingTab, InspectionTab, OpsMediaEditor, useOpsFiles, FilePick, OpsFileActions, MediaTab, PreviewMedia, ReviewTab, KeyCheckRow, PdfPreview, ReportTab, Actions); rules at 88-89, 467 (`opsMayEdit`), 662 (`kcOpen`), 427 (`MAX_DEFAULT`), 173-203 (`activityText`). `Today.tsx:16-17` imports `Actions` from it and `useCount/viewQuery` from `Bookings.tsx`.
- What: one file owns five tabs, the action dialogs and business rules; other pages depend on it.
- Evidence: `wc -l` 825; 12 commits this year; line 797 is 418 characters.
- Why: every Ops change touches this file, merge conflicts and review misses are likely, and the drift in the finding above came from rules living here.
- Fix: one file per tab under `pages/ops/booking/`, `Actions` to `ui/` or `pages/ops/actions.tsx`, stage rules to `lib/`. Size M.

#### MEDIUM · 19 Testing · The upload pipeline and the expert Job page have no unit tests
- Where: `lib/uploader.ts` (hash, multipart resume, retry), `lib/uploadManager.ts` (queue, requeue on failure, discard), `lib/store.ts` (IndexedDB), `pages/expert/Job.tsx` (start, auto-start after check-in, submit), `pages/ops/Booking.tsx:471-491` (Ops add/replace). The only test touching uploads mocks the manager away: `ui/mediaRemove.test.tsx:8`.
- What: the most data-loss-prone code (J1/J2) is covered only by a few Playwright journeys (J3, J3c, J3d, camera).
- Evidence (would a one-line break fail a test?):
  - `rules/rules.ts` `evaluateForm`: yes, 1478 shared vectors + robustness tests.
  - `api/client.ts` CSRF/401/426: yes, `shell.test.tsx:93-120`.
  - `lib/formSpec.ts` `missingFields`/`submittable`: yes for logic (`formSpec.test.ts`), no for the `_today` source.
  - `Job.tsx:177` reuse of `session.submitUuid` (idempotent retry): no test; replacing it with `crypto.randomUUID()` passes everything (Vitest; e2e has no retry case).
  - `Booking.tsx:482` `await uploaded(id)` before `attach` ("a half-sent file must not push out a good one"): no test; deleting the line passes.
  - `uploader.ts:80` skip parts the server already has / `:82-85` retry loop: no unit test; only e2e J3d may notice.
- Why: a refactor of upload or submit can lose an expert's photos or double-submit and CI stays green.
- Fix: unit tests for `transfer` (resume + retry with a fake XHR/api), `uploadManager` (failure requeue, discard), and a Job page test for submit payload and retry. Size M.

#### MEDIUM · 6 Structure / state · Query keys are loose strings; invalidations miss or hit nothing
- Where: `pages/ops/Booking.tsx:82` refreshes `"board"` (no query uses that key since `/board` became a redirect, `App.tsx:54`) and not `"problems"`; master-list items cached as `"list-items"` (`api/labels.ts:21`, `ui/FormRenderer.tsx:133`, staleTime 5 min) but the Admin screen edits under `"master-list-items"` (`pages/admin/MasterLists.tsx:19,25,30`); one form version is cached under `"version"`, `"form-version"`, `"live-trees"`, `"pinned-trees"`, `"ref-trees"`, `"choice-trees"` (`FormBuilder.tsx:37,272`, `PdfDesigner.tsx:89`, `lib/useTrees.ts:13,21`, `lib/useChoices.ts:20`).
- What: there is no key factory, so each screen guesses names when invalidating.
- Evidence: `grep -rn '"board"' src` finds only the layout state and this refresh call.
- Why: after Ops resolve a conflict, reassign or finish without files, the "Needs you" badge and bell keep the old item for up to a minute; after an Admin renames a city, dropdowns and labels in the same tab show the old name for 5 minutes.
- Fix: a small `keys.ts` (`keys.booking(id)`, `keys.listItems(list)`, …) and invalidate by prefix; drop `"board"`; add `"problems"` to the booking reload. Size S.

#### MEDIUM · 8 Clean code · PDF designer autosave drops the last edit on tab switch and says "All changes saved" while it is not
- Where: `pages/admin/PdfDesigner.tsx:120-137` (save fires only from a 700 ms debounced value), `:214` status uses `saving` only, `:49` `<Designer key={t.id}>` remounts on template switch.
- What: an edit made less than 0.7 s before switching template tab, opening Shared library or leaving the page is never sent; during that window the status line reads "All changes saved".
- Evidence: `useEffect(() => { if (ok && dirty && saved) { setDirty(false); void save(saved); } }, [saved]);` — no flush on unmount; status text `saving === "saving" ? "Saving…" : … : "All changes saved"` ignores `dirty`.
- Why: an Admin types a disclaimer change, clicks another template, and the change is gone with no warning.
- Fix: show "Unsaved…" while `dirty`, and flush `save(def)` in the unmount cleanup (or on `beforeunload`). Size S.

#### MEDIUM · 7 Reuse and duplication · Report designer copies its own helpers
- Where: `useDebounced` in `PdfDesigner.tsx:64` and `report/SharedLibrary.tsx:87`; `Template` type in both (`:20`, `:21`); "copy without ids" four times (`PdfDesigner.tsx:293`, `SharedLibrary.tsx:93 noIds`, `report/model.ts:243`, `report/sharing.tsx:124`); sample-bookings query and `sections`/`sectionNames` memos in both (`PdfDesigner.tsx:91-114`, `SharedLibrary.tsx:112-148`); "which page holds this part" written inline twice in `report/PagesPanel.tsx:67,82` while `model.ts:92 pageOf` exists and is used only by a test; `sharing.tsx:26 keyOf` re-implements `lib/fieldTypes.ts:39 slugKey` with a different prefix (`x_` vs `f_`) and length (60 vs 63).
- What: the same small functions exist 2–4 times.
- Why: a fix in one copy (e.g. how ids are stripped) leaves the other screens with the old behaviour.
- Fix: move these into `report/model.ts` / a `useDebounced` in `lib/`, reuse `pageOf` and `slugKey`. Size S.

#### LOW · 7 Reuse and duplication · Stage words typed five times in the web (plus Android)
- Where: `api/labels.ts:27`, `ui/AccessEditor.tsx:6`, `ui/AccessMatrix.tsx:4`, `pages/admin/builder/PreviewDialog.tsx:9`, `pages/ops/Today.tsx:27`; Android `ui/ops/OpsCommon.kt:100`.
- What: the agreed stage words live in five maps.
- Why: the next wording change (as happened for "Uploading") will miss one.
- Fix: import `STAGE_LABEL` everywhere (AccessEditor can add its tips beside it). Size S.

#### LOW · 7 Reuse and duplication · "Media types" list in nine places with different members
- Where: `lib/fieldTypes.ts:18`, `lib/wizard.ts:40`, `ui/AnswerSheet.tsx:12`, `pages/ops/Booking.tsx:440`, `pages/admin/FieldEditor.tsx:149`, `report/PartSettings.tsx:12` (+image), `report/model.ts:191` (+image), `builder/KeyChecks.tsx:17` (+image, derived, rating), `lib/formSpec.ts:46,64` (derived, rating, image).
- Why: adding a media type (e.g. audio) means finding all nine; missing one shows a file id as text.
- Fix: export the sets from `lib/fieldTypes.ts` and reuse them. Size S.

#### LOW · 7 Reuse and duplication · Three definitions of "empty answer" disagree on blank text
- Where: `rules/rules.ts:58` (trims strings), `ui/AnswerSheet.tsx:15` and `pages/ops/Booking.tsx:360` (do not trim).
- Why: an answer of spaces counts as "answered" in the Ops summary but as missing for the rules, so "Answered 12 of 12" and "Required, not answered 1" can show together.
- Fix: use `isEmpty` from `rules/rules.ts`. Size S.

#### LOW · 7 Reuse and duplication · Two hooks build the same "fields of all forms" list
- Where: `pages/admin/FormBuilder.tsx:266 useFieldChoices` and `lib/useChoices.ts:12 useRefChoices` (same start/end switch logic, different query keys `choice-trees` / `ref-trees`).
- Fix: one hook in `lib/`. Size S.

#### LOW · 8 Clean code · Dead code and test-only exports
- Where: `ui/AccessMatrix.tsx` (only `shell.test.tsx:13` uses it; screens use `AccessEditor`), `api/types.ts:95 AuditRow` (also wrong: server sends `actor_username`) and `:97 Role_`, `pages/admin/Forms.tsx:12 TYPE_LABEL`, `lib/typeIcons.ts:12 export { Binary }`, `lib/uploadManager.ts:107 _reset` ("for tests", no test uses it), `report/model.ts:92 pageOf` (test only), `pages/ops/Today.tsx:25 export { dayWindow }` and `pages/admin/Integrations.tsx:11 export { eventWord }` (re-exports kept for tests), `report/PartSettings` `PageSettings onDelete={() => {}}` at `SharedLibrary.tsx:219`.
- Evidence: export-usage script output (listed in Coverage).
- Fix: delete, and point tests at the real modules. Size S.

#### LOW · 18 API contracts · `types.ts` is hand-written and has drifted from the serializers
- Where: `api/types.ts:41-42` `MasterList.items` and `MasterListItem.list` are never sent (`apps/forms/serializers.py:36,47`); `Booking` (`:43`) lacks `released_by`, `released_draft_expected`, `reschedules`, `withdrawn_expert` (`apps/bookings/serializers.py:27-30`); `Me` lacks `notify_prefs`, `locked_until`; 11 more response types are declared privately inside pages (`Activity`, `ReportInfo`, `Missing`, `Stats`, `Summary`, `Template`×2, `TVersion`×2, `Verify`, `ZipState`); `asList` returns `[]` for any unexpected shape (`api/hooks.ts:8`), hiding a contract break as "empty".
- Compared (11 endpoints): `auth/me`, `users`, `bookings` list/detail, `bookings/{id}/inspections`, `bookings/{id}/activity`, `bookings/{id}/missing-files`, `forms`, `form-versions/{id}`, `master-lists/{key}/items`, `audit-logs`, `problems/stuck-uploads`, `inspection-types`. Fields the web reads all exist; the mismatches are extra/missing declared fields, not wrong reads.
- Fix: generate types from the OpenAPI schema once R-10 is fixed; until then move page-local types into `api/types.ts`. Size M.

#### LOW · 8 Clean code · A second toast is hidden early by the first toast's timer
- Where: `ui/kit.tsx:36-39` (`setTimeout(() => setT(null), 4000)` never cleared).
- Why: "Saved." at 0 s then an error at 3 s: the error disappears at 4 s, after one second.
- Fix: keep the timer id and clear it on each `say`. Size S.

#### LOW · 10 Comments · Stale or misplaced comments
- Where: `ui/FormRenderer.tsx:150-151` (Gps doc comment sits above `pad`/`nowAs`); `lib/problems.ts:36-37` and `pages/ops/Problems.tsx:21` list the problem kinds without "Started late"/"Too quick"; `api/labels.ts:20` names "inspection types" as a master list (they are forms now, see `:15`); `api/client.ts:1-2` says every call handles 426, but `uploadFile` (`:89-101`) does not.
- Fix: move/update the four comments. Size S.

#### LOW · 8 Clean code · Very long lines
- Where: 310 non-test lines over 200 characters, 29 over 300; `pages/ops/Booking.tsx:797` is 418.
- Why: reviews and diffs of one line hide several changes (JSX, logic and text on one line).
- Fix: run Prettier (or a print width) in CI. Size S.

#### LOW · 6 Structure · Pages import components from other pages
- Where: `pages/ops/Today.tsx:16-17` (`Actions` from `./Booking`, `useCount`/`viewQuery` from `./Bookings`), `pages/admin/LibraryEditor.tsx:15` (`FieldEditor` from a page), `pages/admin/FormBuilder.tsx:20` (`DuplicateDialog` from `ImportForm`).
- Fix: shared pieces to `ui/` or `lib/`. Size S.

#### LOW · 9 Design principles · Field types handled by four separate switches
- Where: `ui/FormRenderer.tsx:71-116`, `ui/AnswerSheet.tsx:56-84`, `lib/fieldTypes.ts:26-37 defaultConfig` and `:45-54 typeSummary`, plus `typeIcons.ts`.
- Why: a new field type needs edits in five places; nothing fails if one is forgotten (it renders as a plain text box).
- Fix: one registry object per type (label, icon, default config, input, reader). Size M.

#### LOW · 18 API contracts · `api()` ignores the cancel signal TanStack Query passes
- Where: `api/client.ts:29-45` (no `signal` option); e.g. `ui/TopBar.tsx:61` search.
- Why: superseded searches and filters keep running on the server.
- Fix: accept `{ signal }` and pass it to `fetch`. Size S.

#### LOW · 8 Clean code · Page size 50 hard-coded in the client
- Where: `pages/ops/Bookings.tsx:171` `(page - 1) * 50 + 1`.
- Why: changing `PAGE_SIZE` on the server makes the "1–50 of N" text wrong.
- Fix: compute from `results.length` and the page, or read `page_size` from the response. Size S.

#### LOW · 12 Dependencies · Dev advisories and major versions behind
- Evidence: `npm audit` (dev): `tinypool <=2.1.1` critical (prototype-pollution → RCE), `@vitest/mocker` moderate, both via vitest 3.2.7; runtime only react-router (already R-20). `npm outdated`: react 18→19, react-router-dom 6→7, vite 6→8, vitest 3→4, typescript 5.9→7, jsdom 25→29, pdfjs-dist 4.10→6.5, @vitejs/plugin-react 4→6, @noble/hashes 1→2, jest-dom 6→8.
- Why: dev-only risk on CI runners; the gap makes a later upgrade a big-bang.
- Fix: upgrade vitest to 4.1.12+ now; plan React 19 / Router 7 / Vite 8 together. Size M.

#### LOW · 19 Testing · Test files are grouped by session, not by subject; e2e gaps
- Where: `ops2.test.tsx` (dates, views, dashboards, my leads, audit, integrations, field editor, menus, charts), `shell.test.tsx` ("shell v3", field editor, publish dialog, access matrix).
- E2E gaps (no spec mentions them): Ops replace/add a photo, resolve a two-expert conflict, force release, finish without missing files, change type, edit Key Checks, webhook resend.
- Fix: name tests after the module they cover; add e2e for replace-photo and conflict resolve (J3). Size M.

### Strengths worth keeping (max 5 lines, each with evidence)
- One rule engine proven against shared vectors: `rules/rules.test.ts` runs 1478 cases from `shared/rule-vectors` (same files as Python and Kotlin).
- Strict TypeScript with zero escapes: `tsconfig.json` `strict` + `noUncheckedIndexedAccess`; `tsc --noEmit` clean; 0 `any`, 0 `@ts-ignore`, 3 `as unknown`.
- One API client with typed errors, CSRF on writes only and plain-words messages, all tested (`api/client.ts`, `shell.test.tsx:77-120`).
- Pure, tested logic pulled out of screens: `lib/tree.ts`, `lib/schedule.ts`, `lib/wizard.ts`, `lib/conditions.ts`, `report/model.ts` each have their own test file.
- Tests check behaviour through roles and labels, plus a guard test that reads every UI string for the agreed words (`words.test.ts`).


## Appendix F: Web: behaviour, uploads, security, privacy, performance

### Coverage
- Files read in full (41): `web/src/` api/client.ts, api/hooks.ts, auth.tsx, guards.tsx, App.tsx, main.tsx, Layout.tsx, ThemeSync.tsx; lib/ store.ts, uploader.ts, uploadManager.ts, saveDirty.ts, format.ts, schedule.ts, timing.ts, formSpec.ts, problems.ts; ui/ FormRenderer.tsx, CameraCapture.tsx, MediaThumb.tsx, kit.tsx, TopBar.tsx, StaleDialog.tsx, Menu.tsx, PasswordForm.tsx; pages/ Login, Profile, ChangePassword, Public; expert/Job, expert/MyJobs; ops/Booking (all 825 lines), ops/Today, ops/Bookings, ops/Problems; admin/ApiKeys, admin/integrations/IntegrationEditor, admin/report/RichText, admin/report/Preview; `web/vite.config.ts`, `web/package.json`.
- Partly read: admin/PdfDesigner.tsx (lines 120–215), admin/FormBuilder.tsx (60–110, 150–175, 275–296), lib/wizard.ts (reconcileMedia), ops/Dashboards.tsx (date and CSV lines).
- Grep only, not read line by line: the other admin pages (Users, Roles, Settings, MasterLists, Audit, Forms, Library*, Promote, ImportForm, builder/*, report/* other than RichText and Preview, integrations/JsonEditor, ValueInput, Rows), ui/AnswerSheet, ConditionBuilder, Avatar, rules/rules.ts. For these I only checked for XSS sinks, unsafe URLs, swallowed errors, pagination and pending-disable.
- Backend read to confirm server rules: bookings/views.py (list/filter/order), bookings/services.py (assign, reschedule, cancel), bookings/stages.py, bookings/submissions.py (own_filter, INVALID_ANSWERS, set_overrides), media/services.py (initiate, complete, attach, remove), settings (PAGE_SIZE 50, MEDIA_URL_TTL 3600, TIME_ZONE).
- Tools I ran:
  - `npx vite build --outDir <scratch>`
  - Two headless Playwright scripts: `scratchpad/review/web-probe.mjs` and `web-probe2.mjs`. Every request that changes data was intercepted and answered in the browser, so no demo data changed.
  - An esbuild-bundled node probe of `uploadManager` with a mocked `fetch` (`qprobe/queue.ts`).
  - A rule-evaluation timing probe on the real 184-field form (`qprobe/perf.ts`).
  - curl GETs signed in as `ops` and as `expert`.
- Not checked:
  - Real phone speed. Timings are from this Mac.
  - Real R2 or S3 uploads. Locally I could not make a part PUT fail or stall, or let a signed part URL expire mid-upload, so those are from the code only.
  - What Android does when the web removes its pending files (finding H-2).
  - Safari or Firefox IndexedDB limits.
  - The full Admin builder flows.

### Scores
| Aspect | Score | One-line reason with evidence |
|---|---|---|
| 13 Correctness and edge cases | Weak | My leads shows only the first 50 bookings ever assigned (`useList` reads page 1 only); expert and user pickers have the same 50 cap; the web works out `_today` in UTC, the server in IST. |
| 14 Error handling | OK | Several Ops actions send twice on a double-click (proved: 2 reschedule requests); a missing booking or a 500 shows "Loading…" forever; Today says "all assigned" when the API is down. |
| 16 Offline and sync | Bad | The upload queue starts at most 2 files and never starts the rest (proved); a submitted lead never resumes its uploads after a reload (proved); opening a lead on the web deletes another device's unfinished uploads. |
| 17 Notifications (bell) | Good | The bell and "Needs you" share one cache, polled every 60 s and paused in the background. Only Low issues: counts stop at 50, and web experts get no new-lead signal. |
| 20 Security | Good | No `dangerouslySetInnerHTML`; `cleanHtml` keeps only safe tags and https/mailto/tel links; the CSRF header is on every unsafe call; sign-in redirects use router state, not a `next=` parameter. Only Low issues: a crafted `/zip/` path, and `window.open` without noopener. |
| 21 Privacy | OK | Customer phone numbers and names go into URLs and API query strings (`/bookings?search=98765`, proved). R-06 (sign-out leaves data) is known; one worse variant is added below. |
| 22 Performance | OK | Typing 6 letters in the Bookings filter sent 60 requests (proved); every count fetches a full 50-row page; each upload progress tick re-renders the whole wizard (~38 rule evaluations, 8.8 ms on this Mac). Bundle is fine: 269 kB / 85 kB gzip main chunk. |
| 27 Logging / observability | Weak | R-36 (known): no web errors reach anyone. Nothing new above Low: upload failures stay in the browser only. |

### Findings

#### CRITICAL · 16 Offline and sync · Upload queue never starts the 3rd and later files
- Where: `web/src/lib/uploadManager.ts:18-28` (and `:25`, `:80-83`)
- What: `pump()` starts at most 2 uploads. When one finishes (`.finally(() => { running--; })`), or fails (`queue.push(job)`), nothing calls `pump()` again. Queued files only start when the person adds another file, or presses "Retry uploads". That button shows only when something has *failed* (`Job.tsx:105`), and only after submit.
- Evidence: node probe `qprobe/queue.ts`: 5 files added with a mocked API, then 1 s later:
  `after 1 s: asset-1:done asset-2:done asset-3:queued asset-4:queued asset-5:queued`.
  The code:
  ```
  transfer(job, …).then(…).catch((e) => { …; queue.push(job); }).finally(() => { running--; });
  ```
  There is no `pump()` after `running--`. A failed file shows "Will retry" (`FormRenderer.tsx:240`) but nothing retries it: there is no timer and no `online` listener (grep found none).
- Why: an expert on the web takes 10 photos quickly. Only the first 2 (plus one per later photo) are sent. They submit; the page says "Uploading photos (2/10)… keep this page open" forever. The booking stays "Uploading". Ops end up pressing "Finish without the missing files", and the customer's report goes out without photos that are sitting in the expert's browser.
- Fix: call `pump()` in the `.finally`. Retry failed jobs on a timer with backoff and on the `online` event. Add an `xhr.timeout`, and more than 3 part attempts (they now give up after about 3.5 s, `uploader.ts:82-85`). Add a unit test with 5 files. Size S.

#### HIGH · 16 Offline and sync · A submitted lead never resumes its uploads after a reload
- Where: `web/src/pages/expert/Job.tsx:92`, `:97-108`, `:128-139`; `web/src/lib/uploadManager.ts:74-78`
- What: `resumeUploads()` is called only inside `Wizard`. `Wizard` renders only while the stage is `assigned` or `in_progress`. After submit the stage is `submitted`, so a reload or reopened tab shows `Finished`, which never resumes. Files waiting in IndexedDB stay there for good.
- Evidence: Playwright probe [1]. I put one waiting job for FIN-12 (submitted) into IndexedDB, then opened `/jobs/<FIN-12>`:
  - The page said "Submitted. Uploading photos… keep this page open".
  - `media calls after reload: 0 | jobs still in IndexedDB: 1`.
  - There is no `beforeunload` warning either (grep found none).
- Why: the expert submits with photos still sending (the page tells them they may: `Job.tsx:252`). Then the laptop sleeps, the browser discards the tab, or they press refresh. The photos never arrive and the booking is stuck at Uploading.
- Fix: call `resumeUploads(id)` in `Finished` too (or once for all bookings in `Layout` for experts). Warn on `beforeunload` while uploads are pending. Size S.

#### HIGH · 16 Offline and sync · Opening a lead on the web deletes another device's unfinished uploads
- Where: `web/src/lib/wizard.ts:56-59`; `web/src/pages/expert/Job.tsx:134-136`; server `backend/apps/media/services.py:438-451`
- What: when `Wizard` mounts, `reconcileMedia` marks every server file of this booking that is `pending` and not tracked *in this tab* as "discard". `discardFile` then sends `DELETE media/<id>`. The server allows it, because it is the same expert's own unsubmitted file, and hard-deletes it (`delete_asset`).
- Evidence: the code:
  ```
  if (!f || used.has(m.id) || tracked(m.id)) continue;
  if (m.status !== "uploaded" && m.status !== "verified") { discard.push(m.id); continue; }
  ```
  `tracked` only knows this tab's in-memory states. Neither the server's `remove()` nor the web checks whether the file is still being sent from elsewhere.
- Why: Example 1: an expert is uploading 300 MB of video from their phone (status `pending`) and opens the same lead on the office laptop. The laptop deletes the phone's videos mid-upload. Example 2: the same thing happens with a second browser tab while the first is still sending. The other device's draft then points at deleted ids. (What Android does after this was not checked.)
- Fix: only discard pending files older than a cut-off (for example 24 h). Better: let the server's stale-upload job clean up, and drop the client-side discard. Size S.

#### HIGH · 13 Correctness · "My leads" shows only the 50 most recently created bookings
- Where: `web/src/pages/expert/MyJobs.tsx:42`; `web/src/api/hooks.ts:5-12`; server `vayu/settings/base.py:87-88` (`PAGE_SIZE 50`), `bookings/models.py:59` (`ordering -created_at`), `bookings/submissions.py:72-75`
- What: `useList("my-jobs","bookings")` takes `results` of page 1 and ignores `next`. The server orders by newest created, and an expert's list includes every booking ever assigned to them (completed ones too).
- Evidence: the expert endpoint is paginated (`curl …/bookings` as expert gives `count 21, next None`; with more than 50 rows, `next` is set and never followed). `asList` returns only `x.results`. The counts on the filter buttons and the header also come from this one page.
- Why: an expert doing 3–4 leads a day passes 50 assigned bookings in about two weeks. After that, an open lead created earlier is no longer listed on the web: one booked for a date weeks ahead (like DEMO-7 for 4 Dec), or an old one Ops rescheduled. The "Completed" and "All" counts are wrong too.
- Fix: ask the server for open leads only (`stage__in`, or the sync endpoint the phone uses), or follow `next`. Size S.

#### MEDIUM · 13 Correctness · Experts, users and today's schedule also stop at 50
- Where:
  - `useList` callers: `ops/Booking.tsx:77`, `ops/Today.tsx:39`, `ops/Bookings.tsx:99`, `admin/Users.tsx:18`, `admin/Audit.tsx:37`
  - `ops/Today.tsx:37-38` (schedule reads `q.data.results`)
  - `lib/problems.ts:19-20` (conflicts and type changes)
  - `ops/Bookings.tsx:176-192` (the board has no paging)
- What: every list read through `useList`, and the Today schedule, uses page 1 only (50 rows). The KPI numbers use `count`, so they disagree with what is drawn.
- Evidence: `users?role=expert` is paginated (`PAGED count=20`). Today's schedule draws `q.data?.results` while "Today's bookings" shows `useCount(...)` = `count`.
- Why: with a 51st expert, Ops cannot pick them in Assign or in the expert filter, and they get no lane on Today. With 51 bookings on one day, the schedule silently drops some while the card says 51. On the board, bookings past 50 are not shown, with no hint.
- Fix: add `page_size` support on these endpoints (or `?all=1` for users) and follow `next` in `useList`. Show "first 50 of N" where the cap stays. Size S.

#### MEDIUM · 14 Error handling · Double-click sends Ops actions twice (assign, reschedule, cancel, delete, conflict, review)
- Where:
  - `ops/Booking.tsx:812-818` (`Actions`: no pending state)
  - `ui/kit.tsx:19-29` (`Confirm` has no busy state)
  - `ops/Booking.tsx:123`, `:238` (Mark reviewed, Keep this one)
  - `admin/ApiKeys.tsx:56`, `admin/Users.tsx:100`
- What: the submit buttons are not disabled while the request runs, and the server calls carry no idempotency key or `row_version`.
- Evidence: Playwright probe [2]: one `dblclick` on the dialog's Reschedule button gave `reschedule requests sent by one double-click: 2` (the requests were intercepted). On the server, `reschedule` writes a `RescheduleLog` row each time (`services.py:185`). `assign` allows `assigned→assigned` and emits `booking.assigned` each time (`services.py:169`, `stages.py:5`).
- Why:
  - Reschedule: two reschedule entries in the history and reports.
  - Assign: two "assigned" webhooks or notices to the expert and the CRM.
  - New API key: two keys are created, and the first one is never shown or revoked.
- Fix: give `Confirm` and `Actions` an `isPending` that disables the button, and use `useMutation`'s `isPending` on Users and ApiKeys. Size S.

#### MEDIUM · 14 Error handling · A missing booking or a server error shows "Loading…" forever, and Today says "all assigned" when the API is down
- Where:
  - `ops/Booking.tsx:85` (`if (!booking) return Loading…`)
  - `ops/Bookings.tsx:154-174` (no error branch)
  - `ops/Today.tsx:59` (`sub: unassigned ? … : "all assigned"`)
  - also `FormBuilder`, `PdfDesigner`, `IntegrationEditor` (`if (!x) Loading…`)
- What: queries do not retry (`main.tsx:11`) and the screens never read `isError`.
- Evidence: Playwright probe2:
  - [5] `/booking/00000000-…` showed `"Loading…"`.
  - [6] booking page with the API answering 500 showed `"Loading…"`.
  - [7] Bookings with a 500 showed an empty table and no message.
  - [8] Today with a 500 showed `Unassigned — all assigned`.
- Why: when the API is down at 9 am, Ops see "all assigned" and an empty list, and believe there is nothing to do. A mistyped link spins for ever.
- Fix: one `QueryState` helper: loading → spinner, error → `explain(e)` plus a Retry button, 404 → "not found". Never print "all assigned" when the count is unknown. Size S–M.

#### MEDIUM · 14 Error handling · Quick clicks on ratings, Overall or Key Checks get "changed by someone" against yourself
- Where: `ops/Booking.tsx:665-667`, `:647-653`, `:704-722`; server `bookings/submissions.py:408-411`
- What: `send()` uses `insp.row_version` from the last render. The `Seg` buttons stay enabled while saving, and the new `row_version` only arrives after `onSaved()` refetches. A second click within that window sends the old version. The server answers 409 `STALE_INSPECTION`, which shows as a red toast. No `StaleDialog` is used here.
- Evidence: code as cited. The server's `if row_version != insp.row_version: raise err("STALE_INSPECTION", … 409)`.
- Why: Ops set five category ratings in a row. Every other click fails with "Someone changed this inspection since you opened it", and they must notice which ones did not save.
- Fix: keep a `rowVersion` ref updated from each PATCH response (as PdfDesigner does), queue the saves, and disable the buttons while one is saving. Size S.

#### MEDIUM · 16 Offline and sync · Offline, a picked photo is refused with a wrong reason and not kept
- Where: `ui/FormRenderer.tsx:216-226`; `lib/uploadManager.ts:41-50`
- What: `addFile` calls `initiate` on the server *before* saving the file to IndexedDB. With no network, `fetch` throws a `TypeError`. The field then says "That file could not be added. Check its type and size, then try again." The photo is not kept anywhere, while the footer says "Saved on this device".
- Evidence: the message is chosen by `e instanceof ApiError && e.status < 500 … ? e.message : "…Check its type and size…"`. A network error is not an `ApiError`.
- Why: an expert in a basement garage with no signal takes photos on the web. Each one is rejected with advice about file size, and they must retake every photo later.
- Fix: store the job first (with a client UUID) and call initiate inside `transfer`. Show "No connection: kept on this device and sent when you are back online". Size M.

#### MEDIUM · 21 Privacy · Customer phone numbers and names go into URLs and API query strings
- Where:
  - `ui/TopBar.tsx:62`, `:69`, `:92` (`/bookings?search=<term>` and `GET bookings?search=`)
  - `ops/Bookings.tsx:84`, `:91`, `:98`
  - `admin/integrations/IntegrationEditor.tsx:143`
- What: the search term (a phone number, customer name or chassis) is put in the page URL and in every API GET.
- Evidence: Playwright probe [3b]: typing `98765` in the global search and pressing Enter gave `http://localhost:5173/bookings?search=98765`. Probe [3]: `…/api/v1/bookings?search=Sharma&page=1`.
- Why: the phone numbers end up in browser history on shared office PCs, and in web-server and proxy access logs. Those logs keep them beyond the photo and video retention rules, and nothing purges them.
- Fix: send search as POST `bookings/search` (or keep it out of the page URL and strip query strings from access logs). Size S–M.

#### MEDIUM · 22 Performance · 10 API requests per keystroke in the Bookings filter, and each count fetches 50 full bookings
- Where: `ops/Bookings.tsx:61-63` (`useCount` fetches a whole `Page<Booking>` to read `.count`), `:65-72`, `:96-98`, `:142`; `ops/Today.tsx:47-56`
- What: the filter box has no debounce. The list and every view tab (up to 9 `useCount` queries) refetch with the new `search` on each keystroke. Each count query returns a full 50-row page with prefetches, and the server runs an `icontains` search for each (R-17).
- Evidence: Playwright probe [3]: typing "Sharma" (6 letters) gave `/bookings requests while typing 6 letters: 60`. Today fires 7 count queries plus the list every 60 s per open tab.
- Why: 10 Ops typing customer names in parallel put about 100 search queries per second on Postgres, and each one serialises up to 50 bookings only to be thrown away.
- Fix: debounce the filter (250 ms, as GlobalSearch already does at `TopBar.tsx:55`). Add a `count_only=1` (or `page_size=1`) mode, or one `bookings/counts` endpoint that returns all view counts. Size S.

#### MEDIUM · 22 Performance · Every upload progress event re-renders the whole wizard (about 38 full-form rule evaluations)
- Where: `lib/uploadManager.ts:15-16`, `:23` (`emit()` on each progress tick); `pages/expert/Job.tsx:116`, `:168-198`, `:209-237`; `ui/FormRenderer.tsx:207`
- What: `useUploads` subscribes the whole `Wizard`. Each XHR progress event bumps `version`, and the wizard recomputes `missingOn` for every step twice (rail and select), `lockedFrom`, `gaps` and the `FormRenderer`. That is about 38 `evaluateTree` calls on the 11-page, 184-field form.
- Evidence: `qprobe/perf.ts` on the real form from `bookings/<DEMO-7>/forms`: `one evaluateTree: 0.33 ms; Wizard re-render (~38 evaluations): 8.8 ms` on an Apple-silicon Mac. A low-end phone is several times slower (not measured).
- Why: while photos upload, progress fires many times a second, so typing in a text field lags on a cheap phone.
- Fix: throttle progress `emit` (for example every 250 ms), memoise per-step gaps once per draft change, and subscribe only `MediaField` and the counters to upload state. Size S.

#### MEDIUM · 21 Privacy · R-06 variant: after sign-out, the upload queue keeps running in the tab and retries under the next person
- Where: `lib/uploadManager.ts:10-14` (module state); `auth.tsx:62-68` (logout wipes only the React Query cache)
- What: sign-out does not clear `states` or `queue` (photo preview blob URLs included). Queued jobs fail with 401, stay queued, and are retried the next time anyone in that tab adds a file. Under another user the server answers `UUID_CONFLICT` 409 (`media/services.py:185-186`), so they fail for ever, while the previous expert's photos stay in memory and in IndexedDB.
- Evidence: code as cited. Known R-06 covers IndexedDB and drafts; this adds the in-memory queue and its blob URLs.
- Why: on a shared laptop the next person's session keeps trying, and failing, to send the previous expert's car photos. Those photos remain viewable in that tab's memory.
- Fix: in `logout`, call a `uploadManager.reset()` that revokes blob URLs (and, per R-06, asks before clearing IndexedDB). Size S.

#### LOW · 13 Correctness · The web works out `_today` in UTC; the server uses IST
- Where: `web/src/lib/formSpec.ts:11` (`new Date().toISOString().slice(0, 10)`); server `bookings/services.py:30`, `submissions.py:207` (`timezone.localdate()`, `Asia/Kolkata`)
- Evidence, run at 02:02 IST:
  ```
  formSpec today (UTC): 2026-11-24 | format.ts today (local): 2026-11-25 ; server localdate 2026-11-25
  ```
  No frozen form uses `_today` today (0 fields), and the builder does not offer it, so this is latent.
- Why: between 00:00 and 05:30 IST, a rule like "date must not be after `_today`" would pass in the browser and fail on submit, or the other way round.
- Fix: use `isoDay(new Date())` from `format.ts`, or better, a date fixed to `Asia/Kolkata`. Size S.

#### LOW · 13 Correctness · Two tabs on one lead silently overwrite each other's draft
- Where: `pages/expert/Job.tsx:112`, `:119`
- What: each tab loads the draft once and saves its whole draft on every change. There is no `storage` event and no lock (grep found no `storage`, `BroadcastChannel` or `navigator.locks`).
- Why: answers typed in tab A are lost as soon as the expert types anything in tab B.
- Fix: listen to the `storage` event and warn "open in another tab", or merge per key. Size S.

#### LOW · 16 Offline and sync · The browser forgets a file before the server has checked its checksum
- Where: `lib/uploader.ts:66-95` (comment says "Returns when the server says verified"); `lib/uploadManager.ts:24`; server `media/services.py:368-374` (verification is async: `verify_asset.delay`)
- What: `transfer` resolves after `complete` returns `uploaded`. The IndexedDB copy is then deleted. In production (`CELERY_TASK_ALWAYS_EAGER=False`) the checksum is checked later. If it fails, the only good copy is already gone.
- Fix: keep the job until `media/<id>` reports `verified` (poll once later), and correct the comment. Size S.

#### LOW · 16 Offline and sync · IndexedDB save failures are swallowed
- Where: `lib/uploadManager.ts:47` (`await putJob(job).catch(() => {})`)
- Why: in a private window, or when the quota is full (300 MB videos), nothing is kept across a refresh, yet the screen says "Saved on this device".
- Fix: surface the error, or show "kept only while this tab is open". Size S.

#### LOW · 14 Error handling · The booking page offers actions the server always refuses
- Where: `ops/Booking.tsx:108-113` versus `ops/Bookings.tsx:120-122` and `bookings/stages.py:2-9`
- What:
  - Reschedule shows for any live stage, but the server allows only draft or assigned.
  - Reassign shows for in_progress, submitted and completed, which are refused.
  - Cancel shows for submitted, which is refused.
  - The Bookings list menu has the right rules; the detail page does not.
- Why: Ops click, fill in a reason, and get a 409 toast.
- Fix: share one `allowedActions(stage, can)` helper between the two pages. Size S.

#### LOW · 14 Error handling · Submit errors are spread over all parts by key; "Copy check link" is logged even when copying fails
- Where: `pages/expert/Job.tsx:184-188` (`setErrors({ inspection: errs, start: errs, end: errs })`); `ops/Booking.tsx:774-780`
- Why: an error on `start.odometer` also marks `inspection.odometer`. A share gets logged although the clipboard write failed (insecure context or permission).
- Fix: have the server key errors by part. Write to the clipboard first, then log. Size S.

#### LOW · 20 Security · `/zip/:token` and `/verify/:token` paths can be pointed at any same-origin API GET, which is then polled every 1.5 s
- Where: `pages/Public.tsx:19`, `:45-58`, `:95`
- What: the decoded route parameter is put into the API path unchanged. If the response says `status: "ready"`, its `url` goes to `window.location.assign`.
- Evidence: Playwright probe [4]: opening `/zip/..%2Fauth%2Fme` made the browser call `http://localhost:5173/api/v1/auth/me?format=json` repeatedly.
- Why: a crafted customer link makes a signed-in staff browser poll an internal endpoint with its cookies. Today no endpoint returns attacker-controlled `status`/`url`, so the impact is low, but any future one becomes an open redirect or `javascript:` sink.
- Fix: `encodeURIComponent(token)`, accept only a token pattern, and only follow `https:` URLs on the storage host. Size S.

#### LOW · 20 Security · "Open the old file" opens a window without `noopener`
- Where: `ops/Booking.tsx:164-167` (`window.open("", "_blank")`)
- Why: the opened storage page gets `window.opener` (reverse tabnabbing). The risk is low because the target is our own signed R2 URL.
- Fix: `const w = window.open("", "_blank"); w.opener = null;` Size S.

#### LOW · 22 Performance · Signed media links go stale on pages left open over an hour
- Where: `ui/MediaThumb.tsx:16-17`, `ui/FormRenderer.tsx:266` (`staleTime 600_000`, no refetch while mounted); server `MEDIA_URL_TTL = 3600`
- Why: Ops leave a booking open after lunch. Clicking play on a video, or "open full size", returns 403 from storage.
- Fix: `refetchInterval` just under the TTL, or refetch on error. Size S.

#### LOW · 17 Notifications · Bell counts stop at 50; web experts get no new-lead signal
- Where: `lib/problems.ts:19-20`, `:27-29` (`results.length`, not `count`); `pages/expert/MyJobs.tsx:42` (no `refetchInterval`)
- Why: with more than 50 conflicts, the bell says 50. An expert on the web never sees a newly assigned lead until they reload.
- Fix: use `count`, and poll My leads every 60 s like the Ops pages. Size S.

#### LOW · 27 Logging · Upload failures are never reported
- Where: `lib/uploadManager.ts:25`, `lib/uploader.ts:47`
- What: part-PUT failures ("network", "part upload failed (403)") stay in the tab's memory. Together with R-36, nobody can see why web uploads fail. The server's stuck-uploads list shows only that one is stuck.
- Fix: report the final failure reason with the asset (a `failed_reason` sent on retry, or the client error reporting planned for R-36). Size S.

#### NOTE · 20 Security · The UI hides pages the server allows (by design)
- `Layout.tsx:42`, `:51` (`OPS_PAGES`) and the `adminOnly` routes (`App.tsx:61-74`) hide Forms, Lists and Library from Ops even when their role has the permission. Server data is not exposed by bypassing a guard: every page reads its data through the API, which enforces permissions, so a forced URL shows nothing the server refuses.

#### NOTE · 13 Correctness · Dates use the browser's time zone
- `lib/format.ts:4-5` uses the browser zone. Ops or Admin working from outside India see a different "Today".

#### NOTE · 22 Performance · The PDF designer renders a full preview after each pause
- `admin/PdfDesigner.tsx:139-152` makes a full WeasyPrint render 500 ms after each pause in typing. This costs server CPU only while Admins edit templates.

### Strengths worth keeping
- Retries are safe: start, submit and upload each carry a client UUID the server deduplicates (`Job.tsx:41`, `:177`; `uploader.ts:59-64`; server `media/services.py:183-191`).
- One `api()` wrapper adds `X-CSRFToken` to every non-GET call, and `uploadFile` does too (`api/client.ts:40`, `:93`). `explain()` turns every error into plain words.
- No `dangerouslySetInnerHTML` anywhere. `cleanHtml` strips tags and attributes and allows only `https:`/`mailto:`/`tel:` or the three report links (`report/RichText.tsx:11-27`).
- Sign-in redirect comes from router state, not a `next=` parameter, so there is no open redirect (`Login.tsx:27`). Sign-out clears the React Query cache even if the logout call fails (`auth.tsx:62-68`).
- Booking and inspection edits send only changed fields with `row_version`, and a 409 opens `StaleDialog` with "save only my changes" (`saveDirty.ts`, `ops/Booking.tsx:306-327`). Routes are lazy and pdfjs loads on demand: the main chunk is 269 kB / 85 kB gzip (`vite build`).


## Appendix G: Web: UX, accessibility, wording (browser crawl)

Screenshots: `S/` = `(review scratch) webux/shots/`.
Raw data: `.../review/webux/results-{crawl,states,kbd}.json`. Script: `.../review/crawl.mjs` (read-only: navigates, screenshots, presses Tab/Enter/Escape on dialog openers, never submits).

### Coverage
- Files read: ~32. Web: `App.tsx`, `Layout.tsx`, `main.tsx`, `auth.tsx`, `ThemeSync.tsx`, `index.html`, `api/client.ts`, `api/labels.ts`, `api/hooks.ts`, `lib/theme.ts`, `ui/kit.tsx`, `ui/TopBar.tsx`, `ui/FormRenderer.tsx` (fields part), `ui/Avatar.tsx` (colours), `styles.css` (tokens, layout, media queries, focus rules), `pages/Public.tsx`, `pages/Login.tsx`, `pages/ops/{Today,Problems}.tsx`, `pages/ops/Booking.tsx` (load + empty states + dialogs), `pages/expert/{MyJobs,Job}.tsx`, `words.test.ts`. Android: `ui/theme/{Theme,Type}.kt`, `ui/ops/{OpsCommon,Lists}.kt` (stage words). Backend: `reports/views.py` (Verify), `reports/tasks.py` (render), `reports/models.py`, `settings/base.py` (throttles), `accounts/views.py` (login).
  Admin pages (FormBuilder, PdfDesigner, Integrations editor, Library, Roles…) were checked through the browser crawl, axe and screenshots, not read line by line.
- Tools: a Playwright crawl as admin, ops, expert and signed out: 41 routes × {1280, 375} × {light, dark} = 164 full-page screenshots. Dark mode was forced by rewriting the `theme` field of the `auth/me` response in the browser, so no profile data changed. Other runs: axe-core 4.12.1 on every route (1280 light and dark, 375 light); error / empty / loading states by blocking the API (500, empty lists, 9 s delay) on 16 pages; a 375 px overflow check with no mobile emulation; touch targets under 24 px; a 45-press Tab walk on 14 pages; keyboard dialog test (open with Enter, Tab ×20, Escape, close). Also `npx vitest run src/words.test.ts` (passes), a grep for stage and job words, and contrast ratios worked out from the tokens.
- NOT checked: a real screen reader (VoiceOver / TalkBack); Lighthouse; tablet 768 px; zoom to 200 %; the "Assign expert" dialog (no unassigned booking was showing in the default view); the real ZIP download to the end (a download starts, its contents were not opened); the 429 limit on ZIP polling was worked out from the code and settings, not run; forms with many server errors at once.

### Scores
| Aspect | Score | One-line reason with evidence |
|---|---|---|
| 24 Web UX and accessibility | Weak | Three High findings. A read error shows as "All clear", "No leads" or "Loading…" that never ends. A genuine report shows "We could not find this report" to the buyer. Dialogs do not trap focus and Escape does not close them. Every staff page also scrolls sideways at 375 px. |
| 26 Design and wording consistency | OK | "Job" never shows (words test passes, grep is clean). But Ops Today says "Done" / "To start" / "1 done" against the agreed stage words, severity colours are mixed, and web and Android colour tokens have drifted apart. |

### Findings

#### HIGH · 24 Web UX · A failed load shows as empty, "All clear" or a "Loading…" that never ends
- Where: `web/src/main.tsx:11` (`retry: false`, no global onError); `web/src/api/hooks.ts:11-13`; `pages/ops/Problems.tsx:21`; `pages/ops/Today.tsx:57-65,170`; `pages/ops/Bookings.tsx:169`; `pages/expert/MyJobs.tsx:67`; `pages/ops/Booking.tsx:85`; `pages/admin/Users.tsx`, `Forms.tsx`. `isError` is used in 0 of 23 page files; only `Dashboards.tsx` and `Integrations.tsx` handle errors.
- What: when a list call fails (server error, network drop), most pages show their empty state as if the data were really empty. The booking page shows "Loading…" forever, also for a booking that no longer exists (404).
- Evidence: every GET was answered with 500.
  - Ops "Needs you": "All clear. No unassigned bookings today, stuck uploads, conflicts…" (`review-2026-11-25/web/state_ops_problems_error.jpg`).
  - Today: every number "—", Unassigned "all assigned", empty schedule (`review-2026-11-25/web/state_ops_today_error.jpg`).
  - Bookings: table headers with no rows and no message (`review-2026-11-25/web/state_ops_bookings_error.jpg`).
  - Expert: "No leads right now. New leads show here as soon as Ops assign them to you." (`state_expert_jobs_error` in `results-states.json`).
  - Booking page: "Loading…" (`review-2026-11-25/web/state_ops_booking_24921d11_d70b_4c27_9db5_080f07150f44_error.jpg`).
  - Done right: Dashboards ("Could not load the numbers") and the expert lead page ("This lead could not be opened.").
- Why: during an API outage, an Ops person opens "Needs you", sees "All clear" and goes home while a conflict or a stuck upload waits. An expert sees "No leads" and does not go to the inspection. With `retry: false`, one dropped request on a weak mobile network is enough to cause this.
- Fix: one `<LoadError onRetry>` used by `useList` callers and by `BookingPage` (with "not found" for 404), plus `retry: 1` for reads. M.

#### HIGH · 24 Web UX (customer page) · The buyer is told a genuine report "could not be found"
- Where: `web/src/pages/Public.tsx:19,24`; `backend/apps/reports/views.py:235`; `backend/apps/reports/tasks.py:97-99`.
- What: (a) The verify page turns every failure (500, network, 429) into "We could not find this report. The link may be wrong or the report was replaced." (b) The server answers 404 whenever `status != "ready"`. A later re-render that fails sets `status="failed"` on the same row, so the QR on a genuine, already-delivered PDF goes to "not found" until a retry succeeds. The old PDF key is kept and the report is still genuine.
- Evidence: `review-2026-11-25/web/state_public_verify_R5UE8w_q2tpG5p6LQtOeTPxkM6xYG1z8_error.jpg` (500 → "could not find"). Code: `Report.objects.filter(token=token, status="ready")` (views.py:235); on failure `Report.objects.filter(pk=report.pk).update(status="failed", …)` (tasks.py:97). "Replaced" is also untrue: the token stays the same across revisions (models.py:61).
- Why: a buyer scans the QR on a printed report at the seller's house, reads "We could not find this report… may be wrong", and decides the report is fake. The sale or Car C.I.D.'s name is damaged by a server hiccup or a failed re-render.
- Fix: verify on "has a ready revision" (`revision > 0` / `key` set), not on the current status. On the web, show "could not check right now, try again" for anything except 404, and drop "replaced". S.

#### HIGH · 24 Web UX · Dialogs: focus not moved or trapped, Escape does nothing, focus lost on close
- Where: `web/src/ui/kit.tsx:7-17` (`Modal`, used by `Confirm` and `NameDialog`; 48 uses across 21 files, including expert "Discard draft" `pages/expert/Job.tsx:259`, Ops "Force release" / "Cancel" `pages/ops/Booking.tsx:813-823`, and New user).
- What: a `div role="dialog"` with no initial focus, no focus trap, no Escape handler and no focus return.
- Evidence (`results-kbd.json`, `review-2026-11-25/web/dlg_admin_New_user.jpg`):
  - Admin, Users, "New user" opened with Enter: focus stays on the "New user" button behind the dialog.
  - 20 Tabs reach "Find a user", "All", "Admin", "Ops"… on the page behind.
  - After Escape the dialog is still open (`openAfterEscape: true`).
  - After closing with Cancel, focus is on `<body>`.
  - Same on Forms, "New custom form" (Tab reaches the "Booking", "Start", "End" links behind).
- Why: a keyboard or screen-reader user opens "Force release this booking?" and is not taken into it. They hear nothing new, Tab through the page behind, and cannot leave with Escape. After closing they start again from the top of the page. A click on the backdrop also closes the dialog (`onClick={onClose}`) and loses what was typed in New user / New booking actions.
- Fix: render `Modal` as a native `<dialog>` opened with `showModal()`: focus trap, Escape and inert background come free. Return focus to the opener, and do not close on a backdrop click when there are inputs. S.

#### MEDIUM · 24 Web UX · At phone width (375 px) every staff page scrolls sideways; some content breaks
- Where: `web/src/styles.css:231-238` (64 px rail kept at every width under 1200), `.topbar` (no wrap or narrow rule), `.seg` on My leads, the Booking answers grid, the Dashboard chart.
- What: page width at a 375 px viewport (no mobile emulation): every Ops/Admin page 405 px (the top bar: search + "Local" + bell + account button). Expert My leads 609, Dashboards 724, API keys 586, Problems 492, Profile 432. The top-bar search is squeezed to 12 px wide. On the Ops booking page the 2-column answers grid stays at 375, so values break letter by letter: registration "D L 3 C A B 9 9 9 9" stacked vertically, "Not ans wered".
- Evidence: `results-crawl.json` phone checks and the phone pass output ("phone ops /today 405 HSCROLL div.right … button.acct-btn right=405"). Screenshots: `review-2026-11-25/web/ops_booking_745a4642_53cf_4f78_9073_b5b232370e42_375_light.jpg` (answer grid), `review-2026-11-25/web/expert_jobs_375_light.jpg` (filter row off-screen, names cut "Imran Quresh"), `review-2026-11-25/web/ops_dashboards_375_light.jpg` (chart runs out of its card), `review-2026-11-25/web/ops_booking_new_375_light.jpg` (2-column form, date shows "dd/mm/y"), `review-2026-11-25/web/ops_today_375_light.jpg` (account name cut). Customer pages and the expert lead page fit (375).
- Why: an Ops person checking a booking on their phone browser cannot read the registration number. An expert using the web on a phone has to scroll sideways to reach the "Completed" filter.
- Fix: under 600 px, hide the top-bar search and env tag (or move them to a menu), make answer and booking-form grids one column, let `.seg` wrap or scroll inside itself, and give the chart a width of 100 %. M.

#### MEDIUM · 24 Web UX (customer page) · Photo / video ZIP page gives up for good on the first error and polls fast enough to hit the limit
- Where: `web/src/pages/Public.tsx:51-58`; `backend/vayu/settings/base.py:91` (`"public": "60/min"`); `apps/media/views.py:152-153`, `apps/reports/media_links.py:58-59`.
- What: it polls every 1.5 s (40 requests a minute) against a 60-a-minute limit per IP. Any error, 429 included, sets `gone` and stops for good: "This download is not available right now."
- Evidence: code as cited. Not run to 429 (worked out: two tabs, photos plus videos, = 80 a minute → 429 within the first minute of building a large videos ZIP).
- Why: a buyer opens "Download all photos" and "Download all videos" from the report, or two people on the same mobile-carrier NAT do. One tab then says the download is not available, though the ZIP is still being built.
- Fix: back off (1.5 s → 5 s), keep polling through 429 / 5xx with a short "still working" message, and stop only on 404 / 410. S.

#### MEDIUM · 26 Design and wording · Ops Today breaks the agreed stage words
- Where: `web/src/pages/ops/Today.tsx:146` (legend "Done", "To start"), `:58` (KPI sub-text "1 done · 0 in progress · 2 cancelled").
- What: the agreed words are Unassigned · Assigned · In progress · Uploading · Completed · Cancelled, never "To start", and the Today card reads "11 of 26 completed". Android does this (`android/.../ui/ops/Lists.kt:163-176` "of N completed"); the web does not.
- Evidence: `review-2026-11-25/web/ops_today_1280_light.jpg`, `review-2026-11-25/web/admin_today_1280_dark.jpg` (legend "Done · In progress · To start · Unassigned · Started late"; card "1 done · 0 in progress · 2 cancelled", next to a "Completed 1" card).
- Why: the same booking reads "Done" in one place, "Completed" in the next card and "Assigned" on the phone. This is exactly the mix the owner asked to remove.
- Fix: legend "Completed / In progress / Assigned / Unassigned / Started late"; card "1 of 4 completed · 0 in progress · 2 cancelled". S.

#### MEDIUM · 24 Web UX · Text below contrast minimum (both themes)
- Where: `styles.css:535` `.sched-tick` and `:796` `.dash-vs` use `--faint #98a2b3`; `ui/Avatar.tsx:12` amber `#b7791f` with white initials; dark `.now-chip` white on `#f2776f`.
- Evidence (axe `color-contrast`, ratios worked out): schedule time labels 2.58:1 on white (30 nodes, `review-2026-11-25/web/admin_today_1280_light.jpg`); dashboard "vs 27 Sept – 26 Oct" 2.4:1 (`review-2026-11-25/web/ops_dashboards_1280_light.jpg`); amber avatar initials 3.64:1 (Users, Dashboard, Today); dark now-chip "2:04 am" 2.75:1 (`review-2026-11-25/web/admin_today_1280_dark.jpg`). Pills pass: warn 4.84, ok 5.41, bad 5.58, info 5.03 light; dark muted 7.62.
- Why: half-hour times on the schedule and the comparison range are hard to read for older Ops staff or in sunlight.
- Fix: use `--muted` for the ticks and `.dash-vs`, darken the amber avatar to about `#975a16`, and use dark text on the dark-mode now-chip. S.

#### MEDIUM · 24 Web UX · Form errors and required state not tied to the inputs
- Where: `web/src/ui/FormRenderer.tsx:66-68,117`; `web/src/ui/kit.tsx:63-81`. `grep -rn "aria-invalid\|aria-describedby" web/src` → 1 hit (none in forms).
- What: the error text is a sibling `<span role="alert">` with no `aria-describedby`, no `aria-invalid` and no `aria-required`. The input's `aria-label` drops the " *", so a screen reader never hears "required". Help text is not linked either.
- Why: a screen-reader user on New booking hears several alerts at once on submit, then tabs through fields that do not say which one is wrong or required.
- Fix: in `Field`, give the error and help ids and pass `aria-describedby`, `aria-invalid` and `aria-required` to the control. S.

#### MEDIUM · 24 Web UX (customer page) · The verify page cannot tell the buyer it is about THIS car or THIS copy
- Where: `backend/apps/reports/views.py:246-248`; `web/src/pages/Public.tsx:28-36`; the QR URL holds the token only (`apps/reports/context.py:179`).
- What: it shows only the model ("Mahindra XUV 3XO AX5"), no registration or chassis (not even masked). The rating shown is the latest revision's, and nothing tells the buyer which version their paper copy is.
- Evidence: `review-2026-11-25/web/public_verify_R5UE8w_q2tpG5p6LQtOeTPxkM6xYG1z8_375_light.jpg`.
- Why: a seller can show a genuine report for another white Creta, or a v1 printout made before Ops added a defect. The page says "genuine" in both cases.
- Fix: add a masked registration ("DL3C••9999") and "Latest version: 2, check the version printed on your copy". S (product decision on masking).

#### LOW · 24 Web UX (customer page) · Customer link previews and tab show "Vayu", no favicon
- Where: `web/index.html:6` (`<title>Vayu</title>`); `Public.tsx:8` sets the title only after JS runs; `web/public/` has no favicon.
- Evidence: `curl -s http://localhost:5173/verify/x | grep title` → `<title>Vayu</title>`; no `og:` tags.
- Why: a report link shared on WhatsApp previews as "Vayu", the internal app name, not Car C.I.D.
- Fix: serve the public routes with a Car C.I.D. title, `og:` tags and favicon (Caddy rule or a small static HTML). S.

#### LOW · 24 Web UX · Error toasts vanish after 4 s and are announced politely
- Where: `web/src/ui/kit.tsx:36-44`. Every `fail(e)` shows a toast with `role="status"` that is removed after 4000 ms.
- Why: "Could not save" disappears before a slow reader finishes it, and a screen reader may not interrupt to announce it.
- Fix: bad toasts use `role="alert"` and stay until closed. S.

#### LOW · 24 Web UX · No skip link; long tab path before the content
- Where: `web/src/Layout.tsx:65-90`.
- Evidence: the Tab walk starts "Collapse the menu, Today, Bookings…" on every page. Admin has 16 nav links plus the search, bell and account before the page. The Dashboard chart makes every day a tab stop (30 stops, `results-kbd.json`).
- Fix: add a "Skip to content" link to `<main>`, and make the chart one tab stop with arrow keys. S.

#### LOW · 24 Web UX · axe findings: small ARIA and structure errors
- `aria-allowed-attr` (critical): `aria-checked` on `<label class="theme-tile">` (`pages/Profile.tsx:74`), so the theme choice state is not announced. `review-2026-11-25/web/ops_profile_1280_light.jpg`.
- `aria-prohibited-attr`: `aria-label="Not ready yet"` on a plain span (`pages/ops/Booking.tsx:637` / MediaThumb).
- `empty-table-header`: an empty `<th>` on Bookings, Users, Lists, Library, Integrations, API keys, Settings.
- `heading-order`: h1 → h3 on Today ("Schedule by expert", `Today.tsx:145`), Settings ("Time limits") and the Integration editor.
- `landmark-one-main` / `region`: the public pages have no `<main>` (`Public.tsx:21,77,103`).
- `scrollable-region-focusable`: Integration preview `<pre>`, Dashboard chart at 375.
- `Job.tsx:228` and `Public.tsx:69`: progress bars have no `role="progressbar"` or value.
- Fix: one pass over the above. S.

#### LOW · 24 Web UX · Touch targets under 24 px at phone width
- Evidence (`results-crawl.json` phone.small): checkboxes 13×13 (Bookings filters, Audit, Library), info "i" buttons 18×18, PDF designer fold buttons 18×18 (25 small targets on `/pdf`), "Open in Maps" 83×16, top-bar search 12×31. Most buttons are about 34 px high (under 44).
- Fix: give checkboxes a 24 px hit area through their label, and `.tip-btn` / `.rd-fold` a minimum of 24 px. S.

#### LOW · 24 Web UX · Tables on a phone hide the important columns
- Where: `.table-card { overflow-x: auto }` (`styles.css:346`).
- Evidence: `review-2026-11-25/web/ops_bookings_375_light.jpg`. Only Booking / Car / When show; Expert and Status are off to the right with no hint that the table scrolls.
- Fix: a stacked card layout under 600 px, or put Status next to the booking ID. M.

#### LOW · 24 Web UX (customer page) · Small wording and link issues on the download page
- "Tap here if it does not" also shows on desktop (`Public.tsx:68`). The link sits in green text at 1.06:1 luminance contrast with no underline (axe `link-in-text-block`, `review-2026-11-25/web/public_verify_R5UE8w_q2tpG5p6LQtOeTPxkM6xYG1z8_photos_1280_light.jpg`).
- The verify page shows only the heading while loading (no "Checking…"; `state_public_verify_…_loading`).
- No way back to the report and no contact line for a confused buyer.
- Fix: say "Click or tap here", underline links, add a "Checking…" line and a support contact. S.

#### LOW · 26 Design and wording · Mixed patterns and colours for the same meaning
- Native `confirm()` in `pages/admin/ApiKeys.tsx:52` and `Integrations.tsx:60`, while every other destructive action uses the `Confirm` dialog.
- "Started late" is a red pill but an orange banner on the same booking page (`review-2026-11-25/web/ops_booking_745a4642_53cf_4f78_9073_b5b232370e42_1280_light.jpg`), red in the Today legend and an orange KPI on Today.
- My leads "Today 11" holds 10 overdue leads from earlier days (`MyJobs.tsx:18`, `review-2026-11-25/web/expert_jobs_375_light.jpg`), and "Uploading" leads (nothing left for the expert to do) sit under "To do".
- Fix: one rule (warn = orange) and the `Confirm` dialog everywhere; label the overdue group "Overdue". S.

#### NOTE · 26 Design and wording · Web and Android colour tokens have drifted
- `Theme.kt` says "The web app's colour tokens", but light bg is web `#f6f7f9` vs app `#FFFFFF`, line `#e3e6ec` vs `#ECEEF2`; dark line `#26324a` vs `#1F2A40`, and web has a dark `--panel #121a2a` that Android lacks. Brand, ok, warn, bad, info and muted match. No harm today; decide which side is the source and add a check.
- Web asks for `Inter` but never loads it (no `@font-face`), so the font differs by computer. Android uses the system font.
- Customer pages are always Light (`lib/theme.ts:31`, `index.html:11`), even on a phone in dark mode. That is fine, but it is a choice worth writing down.
- "Lead owner" (a booking-form field label) is shown to Ops on New booking (`review-2026-11-25/web/ops_booking_new_1280_light.jpg`). It is a sales term, not the expert "lead", but it sits next to the rule "Ops read booking".

### Strengths worth keeping
- The "job" word guard works: `npx vitest run src/words.test.ts` passes, and a grep of web strings and backend messages finds no on-screen "job". The expert pages say "lead" (`review-2026-11-25/web/expert_jobs_1280_light.jpg`).
- Page structure: every staff page has exactly one h1, one `<main>`, a labelled `<nav>`, and no unlabelled inputs (structure scan in `results-crawl.json`).
- Dark mode is token-based and complete: pills and muted text pass 4.5:1 in both themes, and no page fell back to light colours (`S/*_dark.png`).
- Customer pages are clean, on-brand Car C.I.D., and fit 375 px with no overflow and no small targets (`S/public_verify_…_375_light.png`).
- Dashboards and the expert lead page already show proper error states ("Could not load the numbers", "This lead could not be opened."): the pattern to copy.


## Appendix H: Android: code quality, contracts, tests, wording

### Coverage
- Files read: 46 main Kotlin/XML files, all read in full (`android/app/src/main/java/in/carcid/vayu/**`: root, core/{api,auth,alerts,draft,forms,media,ops,rules,sync,update}, ui/{components,theme,expert,ops}; AndroidManifest, res/values, res/xml). I did not read `baseline-prof.txt`, which is generated. All 19 test files were read or skimmed for their names and asserts. I also read `app/build.gradle.kts`, `gradle/libs.versions.toml` and `app/proguard-rules.pro`.
- Tools run (JAVA_HOME=openjdk@17):
  - `./gradlew lintDebug`: BUILD FAILED, 5 errors and 57 warnings (`app/build/reports/lint-results-debug.txt`).
  - `./gradlew testDebugUnitTest koverLog`: debug ran 111 tests and all passed; release ran 111 tests and **48 failed**.
  - `koverLogDebug`: core line coverage 87.2%.
  - A Python script compared every API path in the Kotlin source with `backend/openapi.yaml`. Every real path is present.
  - Greps for `!!`, `runCatching`, `runBlocking`, `@Suppress`, TODO/`ponytail:`, unsafe casts and "job" strings.
  - `git log --since=2026-08-24` to find hot spots.
- Not checked:
  - No CVE scan of the Android dependencies (no OSV or dependency-check tool available offline). Version gap comes from lint only.
  - The R8 release APK was not run on a phone (it builds: `app-release.apk` 6.4 MB).
  - Hand mutation was done by reading which tests touch a line, not by editing code (the brief says read-only).
  - No side-by-side screenshots against web.

### Scores
| Aspect | Score | One-line reason with evidence |
|---|---|---|
| 4 Long-term maintenance | OK | Hot spots: Parts.kt (941 lines, 18 changes in 3 months), MyJobs.kt (442/14), Lists.kt (353/14), AppViewModel.kt (230/16). Composables of 160–240 lines (Wizard, BookingScreen, AnswersScreen). Only 1 `ponytail:` note (OpsCommon.kt:245, fine). R-25 already covers big files. |
| 6 Structure and modularity | OK | Packages are clean (`core` has no UI imports). But the whole Ops side has no state holder: loading, actions and problem aggregation live in composables. InspectionModel hashes files and fsyncs on the main thread. |
| 7 Reuse and duplication | OK | The answer rules (Checks.kt) are a hand copy of `fieldtypes.py`, with no shared vectors and known drift. Two different `answered()` functions. Size, thumb, JSON-getter and retry-rule helpers are each copied 3–7 times. |
| 8 Clean code | OK | Dead `size()` in Uploads.kt:46. Dead HomeScreen (R-23). `call` and `callAny` are near copies. One bad draft stops the whole outbox. |
| 9 Design principles | OK | Field types are `when (f.type)` string switches in 4 places. OpsEnv/Bk/JsonObject are unstable, so whole Ops screens recompose. Form trees are re-parsed on every draft change. |
| 10 Comments | Good | Comments mostly explain *why*. Only 3 misplaced or stacked KDocs (Low). |
| 11 Types and static checks | OK | 57 `!!` (13 in Outbox.kt) and 16 unchecked `as JsonObject/JsonPrimitive` casts. One `!!` gives a real crash path (below). `lintDebug` fails with 5 errors. |
| 12 Dependencies | OK | The whole stack is pinned at Dec-2024 versions (Compose BOM 2024.12.01 vs 2026.11.01, AGP 8.7.3 vs 9.5.2, CameraX 1.4.1 vs 1.7.0, Firebase BOM 33.7 vs 35.2). 2 unneeded deps. Empty proguard file is fine (no reflection serialization). |
| 18 API contracts | Good | Every path the app calls exists in openapi.yaml (script). But ApiContractTest only scans Api.kt, and `getValue()` on optional fields throws a non-ApiError. Raw JSON parsing = R-11. |
| 19 Testing | OK | Core is 87% covered and the Outbox, rules and sync tests are strong. The background workers, `Graph.prune` (deletes drafts) and resume of half-sent uploads have no test and sit outside the Kover gate. `./gradlew test` fails 48 release tests. |
| 26 Design and wording | Good | Stage words match web `STAGE_LABEL` exactly (OpsCommon.kt STAGE_WORDS). Colours match web tokens except `line`. The "job" wording is R-15 (counts below). |

### Findings

#### MEDIUM · 11 Types and static checks · `drafts.get(id)!!` crashes the app when a draft is pruned while its Submitted screen is open
- Where:
  - android/app/src/main/java/in/carcid/vayu/ui/expert/InspectionModel.kt:47
  - ui/expert/Wizard.kt:110
  - VayuApp.kt:71-76 (`prune`)
  - ui/expert/MyJobs.kt:207, :232
- What:
  - `InspectionModel.draft` is `drafts.get(bookingId)!!`.
  - `InspectionScreen` re-reads it on every draft-store change (`remember(tick) { env.model.draft }`).
  - After a sync, `Graph.prune` discards a draft once the job is completed and every file is sent. `discard` bumps `tick`.
  - A completed job stays in My jobs for 7 days, so `ExpertHome` keeps showing `InspectionScreen` for it, and the `!!` throws a NullPointerException.
- Evidence:
  ```
  val draft: Draft get() = drafts.get(bookingId)!!                       // InspectionModel.kt:47
  val draft = remember(tick) { env.model.draft }                         // Wizard.kt:110
  drafts.all().filter { d -> d.submitSent && d.files.all { it.sent } && jobs[d.bookingId].let { it == null || it.stage == "completed" } }.forEach { drafts.discard(it.bookingId) }   // VayuApp.kt:74
  ```
  Found by reading the code; not reproduced on a phone.
- Steps:
  1. An expert taps a submitted job. A locked draft opens InspectionScreen (MyJobs.kt:232).
  2. They switch to WhatsApp. Meanwhile Ops completes the booking.
  3. They come back. `onForeground` runs a sync, `afterSync` calls `prune`, `discard` bumps `tick`, and the app crashes.
- Why: the expert sees "Vayu keeps stopping" on a job they finished. No data is lost (it was already sent), but it looks broken and is noise in Sentry.
- Fix: make `draft` nullable and have InspectionScreen close itself when it is null. Size S.

#### MEDIUM · 8 Clean code · One bad draft stops the outbox for every draft, and the worker gives up for good
- Where: core/draft/Outbox.kt:37-46 and :58-72, :154, :171, :231, :233; VayuApp.kt:122-128
- What:
  - `Outbox.run()` loops over drafts but only catches `ApiError`.
  - Any other exception in one draft leaves the loop: a `!!` NPE (13 in this file), `transfer`'s `intOrNull!!` on a missing `part_number`, `FormRules`' `check(settled)` IllegalStateException, or `FormTree.parse`'s `(p["id"] as JsonPrimitive)`.
  - `OutboxWorker.doWork` also only catches `ApiError`, so WorkManager marks the work FAILED, not RETRY.
- Evidence:
  ```
  try { push(d.bookingId) } catch (e: ApiError) { ... }        // Outbox.kt:39-44
  } catch (e: ApiError) { Result.success() }                    // VayuApp.kt:126
  ```
- Why:
  - One draft with a form rule cycle, or a server reply missing `part_number`, stops photos for *every other* job on that phone from sending.
  - Nothing retries until the expert edits something or reopens the app.
  - The 2-hour "photos stuck" alert also never fires, because `alertStuck` runs after `run()`.
- Fix: catch `Exception` (rethrowing `CancellationException`) per draft, record it as `problem` on that draft, and continue. Size S.

#### MEDIUM · 6 Structure and modularity · Ops has no state holder: loading, actions and business rules live in composables
- Where:
  - ui/ops/OpsHome.kt:57-77 (load loop, extra online probe)
  - ui/ops/Lists.kt:327 (`loadNeeds`: 7 parallel requests plus problem aggregation)
  - ui/ops/Booking.kt (`run` lambda)
  - ui/ops/Parts.kt:394-414 (OpsUploader upload, attach, take-back)
  - ui/ops/Dashboard.kt:132 (CSV built and fsynced in onClick on the main thread)
  - ui/UpdateScreen.kt:78-81 (APK download in a composable scope with a new `OkHttpClient()`)
- What:
  - Every Ops screen fetches with `produceState`/`rememberLoad` and acts in `rememberCoroutineScope()`.
  - The navigation stack is plain `remember { mutableStateListOf<Route>() }` (OpsHome.kt:53).
  - There is no ViewModel, so state dies with the composition. Only the expert side has models (JobsModel, InspectionModel).
- Why:
  - Leaving a screen cancels in-flight work. Example: Ops taps "Replace" on a photo and presses Back during the upload. The coroutine is cancelled, and the `finally` that should DELETE the loose upload (Parts.kt:409-412) calls a suspend function in a cancelled scope, so it throws and the orphan stays.
  - A config change (font size, dark mode, locale) drops the Ops stack back to the tab.
  - Rules such as "what needs you" can't be unit-tested without Robolectric.
- Fix: move Ops data and actions into one `OpsViewModel` (or a plain class in `core/ops`), keep composables for drawing only, and wrap clean-up in `withContext(NonCancellable)`. Size M.

#### MEDIUM · 6 Structure and modularity · InspectionModel hashes whole files and fsyncs on the main thread
- Where:
  - ui/expert/InspectionModel.kt:96 (`sha256(file)` inside `addFile`), called from Wizard.kt:184 `onTaken` (main thread)
  - InspectionModel.kt:82 `set` → `commit` → `DraftStore.save` → `writeAtomically` with `fd.sync()` (core/Files.kt:11) on every keystroke
- What: the model class does disk I/O on whatever thread calls it, which is the UI thread.
- Evidence: `val f = LocalFile(..., file.length(), sha256(file), label)` (InspectionModel.kt:96). Taking a 60 s 720p video (tens of MB) hashes it on the main thread before the camera closes.
- Why: on a low-end phone, "Use video" can freeze the screen for seconds (ANR risk), and every typed character pays for an fsync. This is separate from R-12, which is about thumbnail decoding.
- Fix: make `addFile` and `commit` suspend on `Dispatchers.IO`, or hash in the outbox before registering. Debounce text saves. Size M.

#### MEDIUM · 7 Reuse and duplication · The server's answer rules are hand-copied with no shared vectors, and already differ
- Where: core/forms/Checks.kt:10-29 vs backend/apps/forms/fieldtypes.py:195-215, 300-316 and backend/apps/core/phone.py
- What: `answerProblem` re-implements `clean_answer` (phone, number, decimals, range, text length, pattern). Only 4 hand tests cover it (ChecksTest). `shared/rule-vectors` covers only JsonLogic and form rules.
- Known drift:
  - Python uses the `regex` module with a timeout. Kotlin uses `java.util.regex` and treats a pattern Java can't compile as "fine" (`runCatching { !Regex(pattern).matches(text) }.getOrDefault(false)`, Checks.kt:23).
  - Length counts code points in Python but UTF-16 units in Kotlin (`text.length > max`, Checks.kt:22).
- Why: an Admin pattern using Python-only syntax passes on the phone and is refused only after Submit. The expert sees the draft come back "refused" hours later, possibly off-site.
- Fix: add an `answer_vectors.json` to shared/rule-vectors (field, config, value, expected code) and run it in pytest and SharedVectorsTest. Size S.

#### MEDIUM · 12 Dependencies · The whole Android stack is about 2 years behind
- Where: android/gradle/libs.versions.toml:2-19
- What: lint `GradleDependency` lists 48 outdated libraries. Main gaps:

  | Library | Pinned | Latest |
  |---|---|---|
  | Compose BOM | 2024.12.01 | 2026.11.01 |
  | AGP | 8.7.3 | 9.5.2 |
  | lifecycle | 2.8.7 | 2.11.1 |
  | CameraX | 1.4.1 | 1.7.0 |
  | WorkManager | 2.10.0 | 2.12.0 |
  | Firebase BOM | 33.7.0 | 35.2.0 |
  | core-ktx | 1.15.0 | 1.19.1 |

  Kotlin 2.1.0, OkHttp 4.12 and Sentry 7.18.1 are also old (not in lint's list). targetSdk is 35.
- Evidence: `app/build/reports/lint-results-debug.txt`, e.g. "A newer version of androidx.compose:compose-bom than 2024.12.01 is available: 2026.11.01".
- Why: each month the eventual jump (AGP 9 + Kotlin + Compose together) gets bigger and riskier. Security fixes in OkHttp, Firebase and CameraX are not picked up. Not checked for CVEs.
- Fix: one upgrade branch (Kotlin + AGP + BOM first, then the rest), with Roborazzi screenshots as the safety net. Then Renovate/Dependabot for `android/`. Size M.

#### MEDIUM · 19 Testing · Background workers and draft deletion have no tests and sit outside the coverage gate
- Where:
  - app/build.gradle.kts:18 (`filters { includes { packages("in.carcid.vayu.core") } }`)
  - VayuApp.kt:55-76 (`forgetCopies`, `prune`) and :118-140 (OutboxWorker)
  - Push.kt:75-165 (VayuMessaging, SyncWorker, Reminders, ReminderWorker, alertStuck)
- What: the 80% Kover gate counts only `core`. The root package, which holds every worker and `Graph.prune` (the only automatic draft deletion), has 0 tests (grep for `prune|OutboxWorker|SyncWorker|Reminders|alertStuck` in src/test: no hits).
- Untested otherwise:
  - `core/media` is 8.2% covered (`stampPhoto`, Locator).
  - `transfer()` part-resume: tests always return `"uploaded_parts":[]` (OutboxTest.kt:51), so deleting `if (n in have ...) continue` (Outbox.kt:236) fails nothing.
  - `Api.capped` size limit: no TOO_LARGE test.
  - AppViewModel `signOut` refusing while work is unsent (AppViewModel.kt:213): no test.
- Hand mutation, by reading which tests hit each line:

  | Line changed | Would a test fail? |
  |---|---|
  | Outbox.sendSubmit start-first rule | Yes (aJobTakenAway…, everythingIsSentInOrder…) |
  | DraftStore.clearSentCopies `it.sent` filter | Yes (OutboxTest:156) |
  | Api refresh-once | Yes (ApiTest) |
  | JsonLogic operators | Yes (shared vectors) |
  | Graph.prune condition | **No** |
  | transfer() resume | **No** |
  | signOut unsent guard | **No** |
  | Reminders 60-min rule wiring | **No** (only the pure `reminders()` is tested) |

- Why: a slip in `prune` deletes an expert's unsent photos and nothing catches it. A WorkManager change breaks background sending silently.
- Fix:
  - Add Robolectric + `work-testing` tests for OutboxWorker, SyncWorker and ReminderWorker.
  - Add a plain test for `Graph.prune`.
  - Add a part-resume case to OutboxTest.
  - Widen the Kover filter to `in.carcid.vayu` minus `ui`.
  - Size M.

#### LOW · 19 Testing · `./gradlew test` (and `koverLog`) fails 48 tests in the release variant
- Where: app/build.gradle.kts:106 (`debugImplementation(libs.compose.ui.test.manifest)`)
- Evidence: `testReleaseUnitTest 111 tests, 48 failed` with "Unable to resolve activity for Intent … androidx.activity.ComponentActivity". `testDebugUnitTest` 111 tests, 0 failed. CI runs only `…Debug` tasks (ci.yml:122), so CI is green.
- Why: a developer who runs the obvious `./gradlew test` or `koverLog` sees 48 red tests and may think the app is broken.
- Fix: `testOptions.unitTests` only for debug (`androidComponents { beforeVariants(selector().withBuildType("release")) { it.enableUnitTest = false } }`), or document `testDebugUnitTest`. Size S.

#### LOW · 11 Types and static checks · `lintDebug` fails with 5 errors, so lint can't simply be added to CI (worse variant of R-26)
- Where: ui/expert/Fields.kt:396, :445; ui/ops/OpsCommon.kt:168; ui/ops/Parts.kt:505, :521
- Evidence: `5 errors, 57 warnings`, BUILD FAILED. All 5 are `ProduceStateDoesNotAssignValue`, and all 5 lambdas *do* assign `value` (likely a lint/Kotlin-2.1 false positive).
- Other warnings:
  - ExifInterface platform class (core/media/Media.kt:16)
  - LockedOrientation
  - ObsoleteSdkInt `mipmap-anydpi-v26`
- Why: turning lint on in CI (R-26 fix) fails on day one unless a baseline or suppression is added.
- Fix: `lint { baseline = file("lint-baseline.xml") }` or `@SuppressLint` on those 5, then add `lintDebug` to CI. Size S.

#### LOW · 7 Reuse and duplication · Two `answered()` functions with different rules
- Where: ui/expert/Fields.kt:455 (`!FormRules.isEmpty(v)`) vs ui/ops/Parts.kt:155 (`v != null && v != "" && !(v is List<*> && v.isEmpty())`)
- What: the Ops version counts `"  "` (spaces) and `{}` (an empty GPS map) as answered. The expert version and FormRules do not.
- Why: the expert's section header says "3 of 4", while Ops' "Inspection Data · N answers" for the same inspection can show one more.
- Fix: delete the Ops copy and use `FormRules.isEmpty`. Size S.

#### LOW · 7 Reuse and duplication · Small helpers copied many times
- Where:
  - JSON string getter written 5 times: Api.kt:226, Outbox.kt:219, JobStore.kt:158, OpsData.kt:62, FormTree.kt:67.
  - The "uploaded/verified" status set is written 5 times (Outbox.kt:34 and :226, Booking.kt, Parts.kt ×2).
  - The retry rule `e.code == NETWORK || e.status >= 500 || DEVICE_REVOKED` appears 7 times in Outbox.kt.
  - Byte-size text is written 3 times: Storage.kt:39 `sizeText`, Uploads.kt:46 `size` (dead, private, unused), UpdateScreen.kt:43 `mb`.
  - Bitmap sampling is written twice: Fields.kt:396 `rememberThumb`, Parts.kt:378 `thumb`.
  - Initials are written 3 times: Api.kt:37, Lists.kt:68, Dashboard/AssignSheet inline.
  - `call`/`callAny` (Api.kt:228-249) repeat the same refresh, revoke and error code.
  - Light and dark colour schemes repeat 13 identical arguments (Theme.kt:63, :72).
  - The "d MMM" formatter is built twice in Dashboard.kt (:68 and inside `periodLabel`).
- Why: a fix in one copy misses the others. For example, the size wording already differs ("1 MB" floor only in `mb`).
- Fix: one `core/Json.kt` (`s/o/a`), one `isTransient(e)`, one `sizeText`, one `decodeSampled`. Delete `Uploads.size`. Size S.

#### LOW · 18 API contracts · ApiContractTest only checks Api.kt, and `getValue()` throws outside ApiError
- Where: app/src/test/…/core/api/ApiContractTest.kt:16-17; core/api/Api.kt:88, :219, :275
- What:
  - The test scans only `call(`/`send(` in Api.kt (about 17 paths). The 23+ Ops paths in `ui/ops/*` (`get/act/rememberLoad`) are never checked. My script found all of them in openapi.yaml today.
  - `heartbeat` uses `getValue("min_app_version")`, `parseMe` uses `getValue("id")`, and `refresh` uses `getValue("access")`. These throw NoSuchElementException, not ApiError. Callers catch only ApiError (e.g. AppViewModel.kt heartbeat launch), so a server that drops that field crashes the app at sign-in.
- Fix: scan all `src/main` for quoted API paths in the contract test, and use `["…"]?…` instead of `getValue`. Size S.

#### LOW · 11 Types and static checks · `runCatching` around suspend calls, and other unsafe casts
- Where:
  - Push.kt:90: `runCatching { runBlocking { … } }` on the FCM thread. Acceptable there, but it is the only `runBlocking`.
  - AppViewModel.kt:122 and signOut `runCatching { api.logout() }`; OpsHome.kt (assign follow-up `runCatching { data.load(...) }` then `it.data as JsonObject`).
  - Booking.kt:388 `u.int("id")!!`.
  - Fields.kt:339 and OpsCommon.kt:248 `(v["lat"] as Number)` (crashes on a GPS answer without `lng`).
  - FormTree.kt:27 `it["key"] as String` and :71 `(p["id"] as JsonPrimitive)` (crash on an option or page without key/id).
  - Draft.kt:94, :108 `s("booking")!!` / `fs("id")!!`, inside DraftStore.get's `runCatching` (Draft.kt:136). A draft file written by a future app version with a renamed key silently disappears from `all()`, `unsentCounts()` and the sign-out guard.
- Totals: 57 `!!`, 43 `runCatching`, 16 unchecked JSON casts.
- Fix: rethrow `CancellationException` in those `runCatching` blocks, and use `as?` with defaults. When a draft can't be parsed, keep it visible as "damaged" instead of dropping it. Size S.

#### LOW · 9 Design principles · Unstable Ops parameters and repeated parsing make recomposition and CPU cost high
- Where:
  - OpsHome.kt:57: `OpsEnv(...)` is a data class holding new lambdas every recomposition, so it never equals the old one and every Ops screen recomposes.
  - `Bk`/`Labels`/`JsonObject` are not `@Immutable`/`@Stable`.
  - `Field.options` (FormTree.kt:26) rebuilds its list on every access.
  - `JobStore.tree()` re-parses a form from JSON on every call, and `InspectionModel.commit` (InspectionModel.kt:67) plus `remember(tick)` in Wizard.kt:111 parse 3 form trees and run the rules fixpoint about twice per keystroke.
  - Field types are dispatched by `when (f.type)` string switches in 4 places (Fields.kt Input, Parts.kt answerText, Checks.kt, FormTree flags).
- Why: long forms (200 fields) on cheap phones type sluggishly. A new field type needs 4 edits.
- Fix: remember lambdas in OpsHome, cache parsed `FormTree` by version in JobStore, and mark models `@Immutable`. Size M. (Measure first: aspect 22.)

#### LOW · 8 Clean code · An extra request just to say "Updated."
- Where: ui/ops/OpsHome.kt:73
- Evidence: `val online = try { data.api.get("problems/reports"); true } catch (...) { false }`
- What: after the full reload, one more GET is sent to decide which snackbar to show. The reload results (`Loaded.offline`) already know this.
- Fix: use the `offline` flag from the loads just made. Size S.

#### LOW · 10 Comments · Misplaced and stacked doc comments
- Where:
  - ui/expert/Tools.kt:128-140: CameraScreen's KDoc and `@SuppressLint("MissingPermission")` now sit on `firstCameraIsBack`, not on `CameraScreen`. The suppression no longer covers the camera code it was written for.
  - core/draft/Outbox.kt:17-24: Outbox's class KDoc sits above the `JOB_CLOSED` constant.
  - ui/ops/Lists.kt:325-326: two KDocs stacked on `loadNeeds`, the first one stale.
  - ui/Screens.kt:154 "The real My jobs (Phase 14) and Today (Phase 16) replace these bodies" on dead code (R-23).
- Fix: move or delete. Size S.

#### LOW · 12 Dependencies · Two dependencies not needed
- Where: app/build.gradle.kts:99, :104
- What:
  - `compose.ui.tooling.preview` is shipped in release, but there are 0 `@Preview` in src (grep).
  - `androidx.lifecycle.runtime` (runtime-ktx) is declared by hand but already comes with `lifecycle-runtime-compose`.
- R8/proguard: `proguard-rules.pro` is empty. That is correct here: no `@Serializable` or reflection (JSON is read as `JsonElement`). WorkManager, Firebase, Sentry, OkHttp, CameraX and ML Kit ship their own consumer rules. The release APK builds at 6.4 MB but was not run.
- Fix: drop both lines. Size S.

#### LOW · 26 Design and wording · Two colour tokens differ from web
- Where: ui/theme/Theme.kt:27, :37 vs web/src/styles.css:2, :197
- Evidence:
  - Light `line` is `#ECEEF2` on Android and `--line: #e3e6ec` on web.
  - Dark `line` is `#1F2A40` on Android (equal to web `--hover`) and `--line: #26324a` on web.
  - Dark `soft` is `#161F31` vs web `--subtle` `#162034`.
  - All other shared tokens are exact (brand, ink, muted, ok, warn, bad, info, tints, primary).
- Why: dividers look lighter on the phone than on web. The comment says "the web app's colour tokens". Either fix the comment or the values.
- Fix: align the values, or note the prototype choice in a comment. Size S.

#### NOTE · 26 Design and wording · "job" wording (R-15): exact count for the fix
- `grep -rnoE '"[^"]*\b[Jj]obs?\b[^"]*"'` finds about 35 user-facing strings.
- 7 are on **Ops** screens, where the rule is "booking":
  - Booking.kt:268-269 "Force release this job?", "taken off the job", "The job can be assigned again".
  - Booking.kt (finish dialog) "The job is marked Completed".
  - AssignSheet "N jobs that day".
  - Dashboard "N jobs".
  - Lists.kt:295 "Jobs started, submitted…".
  - Parts.kt ReportCard "Made when the job is done".
- The Android notification channel "Jobs and updates" (Push.kt:46) shows in system Settings for Ops too.
- Stage words match web exactly (STAGE_WORDS vs web `STAGE_LABEL`).

#### NOTE · 4 Long-term maintenance · Hot spots
| File | Lines | Commits since 24 Aug | Risk |
|---|---|---|---|
| ui/ops/Parts.kt | 941 | 18 | 6 screens + upload logic + ReportCard in one file |
| ui/AppViewModel.kt | 230 | 16 | sign-in, revoke, theme, heartbeat, update in one VM |
| ui/ops/Lists.kt | 353 | 14 | Today + Bookings + Needs + problem aggregation |
| ui/expert/MyJobs.kt | 442 | 14 | home routing + list + detail + helpers |
| ui/expert/Wizard.kt | 494 | 9 | one 240-line composable |

### Strengths worth keeping
- The Outbox is idempotent by client UUIDs, and the order is well tested: 11 tests in OutboxTest.kt (e.g. runningAgainSendsNothingTwice, aJobTakenAwayStillSendsTheSubmitForOps).
- One JsonLogic/FormRules implementation passes the same shared vectors as Python and web (SharedVectorsTest.kt: eval, robust and form vectors).
- `writeAtomically` (core/Files.kt) writes temp file + fsync + rename, used for drafts, jobs, notes and Ops copies.
- Simple manual DI (`Graph`), no framework. `core` has no Compose imports, so it is easy to unit-test (87% line coverage).
- Careful privacy defaults: Sentry `beforeSend` strips message, values, extras and user (VayuApp.kt:99-104), and backup and device-transfer are excluded entirely (data_extraction_rules.xml).


## Appendix I: Android: offline, notifications, security, privacy, performance (code)

### Coverage
- Files read in full (24): `core/Files.kt`, `core/auth/TokenStore.kt`, `core/api/Api.kt`, `core/draft/Draft.kt`, `core/draft/Outbox.kt`, `core/sync/JobStore.kt`, `core/media/Media.kt`, `core/update/Update.kt`, `core/alerts/Alerts.kt`, `core/alerts/LocalNotes.kt`, `core/ops/OpsData.kt`, `VayuApp.kt`, `Push.kt`, `MainActivity.kt`, `ui/AppViewModel.kt`, `ui/Bell.kt`, `ui/UpdateScreen.kt`, `ui/expert/{JobsModel,InspectionModel,Storage,Wizard,Uploads}.kt`, `AndroidManifest.xml`, `res/xml/*`, `app/build.gradle.kts`, `proguard-rules.pro` (empty, 0 bytes).
- Read in part or by grep (file IO, threads, intents, errors): `ui/expert/{Tools,Fields,MyJobs}.kt`, `ui/ops/{Parts,Dashboard,Booking,OpsCommon}.kt`, `ui/Screens.kt`, `gradle/libs.versions.toml`.
- NOT read line by line: `core/rules/*`, `core/forms/*`, `ui/components/*`, `ui/theme/*`, `ui/Illustrations.kt`, `ui/ops/{Filters,Lists,OpsHome}.kt` and most of `ui/ops/Parts.kt` / `Booking.kt`. I grepped them for file IO, threads, intents and logging only. They hold UI and rules logic that belongs to other aspects.
- Backend contract read: `backend/apps/bookings/submissions.py` (start, submit, `_advance`), `bookings/sync.py` (`jobs_for`, `payload`), `bookings/views.py` (start/submit/sync views), `media/services.py` (initiate, complete, remove, delete_asset, LIMITS), `media/tasks.py` (`verify_asset`), `notify/push.py` (`send`), `accounts/services.py:61-75` (second-phone rule), `vayu/settings/base.py` (JWT lifetimes, throttles).
- Tools run: `aapt2 dump xmltree/badging` on `android/app/build/outputs/apk/release/app-release.apk` (usesCleartextTraffic=false, allowBackup=false, only MainActivity exported plus the library defaults, versionCode 1). `unzip` + `strings` on classes.dex: only `https://app.carcid.in/api/v1/`, no Sentry DSN, and no secrets found.
- Could NOT check: anything on a device (no phone or emulator run). So these are untested: real process death, reboot, Doze/standby, frame timing, ANRs, real video bitrate and file sizes, and FCM delivery. Every timing and size claim below is from the code, not measured.

#### Trace: offline inspection, check-in to submit
| Step | What is saved, when | Process killed here |
|---|---|---|
| Open job (Start) | `InspectionModel.begin` writes the draft file at once (pins form versions) `InspectionModel.kt:51` | Nothing lost |
| Each answer | `DraftStore.save` → `writeAtomically` (temp file, fsync, rename) runs before the screen updates `Draft.kt:145`, `Files.kt:7-12` | Nothing lost (a `.tmp` may be left) |
| Check-in complete | `startedAt` is set by a second `update`, then `kick()` puts the outbox job into WorkManager, which keeps it across restarts `InspectionModel.kt:69-74` | Nothing lost. The start is sent later |
| Camera shot | Raw JPEG saved, then stamped on Default, then held as `pending` (not in the draft yet) `Tools.kt:241-251` | The shot is lost (retake). Raw/pending files are left orphaned |
| "Use photo" | `addFile` hashes the file and saves the draft `InspectionModel.kt:92-106` | Nothing lost |
| Upload | Per file: initiate (same `client_uuid`), list the parts the server already has, PUT the missing 8 MB parts, complete. Progress saved after each part `Outbox.kt:203-245` | Resumes from the last whole part |
| Submit | `submittedAt` saved before `kick` `InspectionModel.kt:123`. The server makes it idempotent by `client_submission_uuid` `submissions.py:233-237` | Nothing lost. A retry cannot submit twice |
| Reboot | WorkManager work is persisted (`RECEIVE_BOOT_COMPLETED` merged into the manifest) | Resumes |

The server keys every repeatable step on a client UUID: start `submissions.py:142-147`, submit `:233-237`, media initiate `media/services.py:183-192`. I found no double-submit or double-upload path. The real gaps are elsewhere (findings below).

### Scores
| Aspect | Score | One-line reason with evidence |
|---|---|---|
| 13 Correctness | Weak | The version pinned on the phone is not the one the server uses at start (`submissions.py:159` vs `Api.kt:100-106`). The phone deletes forms its own drafts still need (`JobStore.kt:81-82`) |
| 14 Error handling | Weak | After Submit, a file the server refuses blocks the submit forever with no message, and it cannot be removed (`Outbox.kt:145-146,177`, `InspectionModel.kt:109`) |
| 15 Data integrity (local) | Weak | Drafts lose their forms (H-1). A checksum failure after "sent" is never re-sent, and "Free up" can delete the only copy (M-1) |
| 16 Offline and sync | Weak | H-1..H-4: stuck submits, and an invisible draft that blocks sign-out and sign-in on a new phone |
| 17 Notifications | Good | Push is data-only (`push.py:52`). Text is fetched with this phone's own sign-in (`Push.kt:87-91`). Reminders check the owner (`Push.kt:144`). `cancelAll` at sign-out. Only Low issues |
| 20 Security | Good | No exported surface beyond the launcher. FileProvider exposes only `cache/reports` and `cache/update`. APK sha256 checked. Release has no cleartext. Only Low/Note left (R-19 known) |
| 21 Privacy | OK | After sign-out, the drafts folder (customer answers, stamped photos) stays on the phone (M-8). Lock-screen reminders show customer and address (L-3) |
| 22 Performance | OK | Main-thread fsync on every keystroke. The whole file is hashed on the main thread, which is an ANR risk for videos (M-3). R-12 already known |
| 23 Running cost | OK | Photos are capped (2048 px, at most 700 KB). Video has no target bitrate, and gallery videos go up as-is up to 300 MB (M-7) |
| 27 Logging / crash reports | OK | Sentry strips PII well. The release is minified and no mapping is uploaded, so stack traces are unreadable (M-6) |
| 28 External services | OK | R2/API down → retry. Firebase down → reminders are still local. But retries can stall for hours behind WorkManager backoff (M-2) |

### Findings

#### HIGH · 15/16 Data integrity, Offline · The phone deletes the forms its own drafts are pinned to, so the work can never be sent
- Where: `android/.../core/sync/JobStore.kt:81-82`, `core/draft/Outbox.kt:156,176`, `VayuApp.kt:66-68`, `ui/expert/InspectionModel.kt:51-52`, `ui/expert/Wizard.kt:113-118`; `backend/apps/bookings/submissions.py:58-62`, `bookings/sync.py:19,25-28`
- What: A draft pins form versions when it is opened. Every sync then keeps only the form versions that the jobs in that sync use. If the draft's job no longer uses its pinned version, that form is deleted from the phone. Two ways this happens: (a) the Admin publishes a new version and the start has not reached the server yet, so `current_versions` gives the job the new version; (b) the job leaves the list (moved away more than 2 days ago, or cancelled more than 7 days after its date). After that, `filledOf` returns null, and `sendStart` and `sendSubmit` silently `return`. `forgetJobs` on a revoke deletes the whole jobs file, forms included, with the same result.
- Evidence: `val forms = (data().obj("forms") + payload.obj("forms")).filterKeys { it in used }`, where `used` comes from `payload["jobs"]` only. In the Outbox: `val filled = filledOf(d) ?: return`. In the UI: "This job's form isn't on the phone yet… tap Refresh". Refresh cannot fix it, because the server only sends the versions of listed jobs.
- Why: An expert does the check-in at a basement site with no signal. That afternoon the Admin publishes v6 of the form. The phone syncs and v5 disappears. The finished inspection stays "Answers locked; sending when there is signal" forever. The only way out is "Discard draft", which deletes the answers and any photos not yet sent.
- Fix: In `JobStore.apply`, also keep every version named in `drafts.all().versions` (pass the set in), and drop a version only once no draft uses it. Size S.

#### HIGH · 13 Correctness (API contract) · Start ignores the version the phone pinned, so answers are checked against a different form
- Where: `backend/apps/bookings/submissions.py:159` (`pinned = versions_to_pin(inspection_version(b.inspection_type))`), `:249` (submit uses `insp.pinned()`), `forms/rules.py:198` (`UNKNOWN_FIELD`); `android/.../core/api/Api.kt:100-106` (start sends no form version); `core/draft/Draft.kt:40-41` ("kept even if Ops changes the job's form")
- What: The phone fills the form version it pinned offline. When its start arrives after a new version was published, the server pins the latest version instead. The submit is then checked against that newer form: unknown keys fail, and new required fields count as missing. The phone shows "Fix the answers marked in red", but those fields do not exist in the phone's form (`Outbox.kt:184-187`).
- Evidence: `start(...)` has no version parameter, and `views.py:206-209` passes none. Only `submit` takes `form_version`, and only when there is no inspection yet (`submissions.py:239-246`).
- Why: Same publish-day case as above. Even if the phone keeps v5, the server pinned v6 at start. The expert loops between "refused" and "fix the red answers" with nothing red on screen.
- Fix: Send `form_version` with start. The server pins it if it is a published version of the type's form, as submit already does. Size S.

#### HIGH · 14/16 Error handling, Offline · After Submit, one refused file blocks the whole submission forever, silently, and the file cannot be removed
- Where: `core/draft/Outbox.kt:72-89` (register error → `serverId` stays null), `:140-150` (`outgoing` returns null), `:177` (`?: return`, so no submit and no problem message), `ui/expert/InspectionModel.kt:109` (`removeFile` refused when locked), `ui/expert/Uploads.kt:52-158` (no remove), `ui/expert/Fields.kt:375` (gallery allowed for video by default), `backend/apps/media/services.py:29-33` (limits: video 300 MB mp4/quicktime, file 20 MB)
- What: The Review page does not check file errors, so an expert can submit with a file the server will refuse. Examples: a gallery video that is `video/3gpp`/`webm` or bigger than 300 MB, or a PDF bigger than 20 MB. After Submit the answers are locked. The outbox then never sends the answers, never records a problem, and the expert cannot delete the bad file.
- Evidence: `if (v in server) server[v] ?: return null` → `PARTS.associateWith { outgoing(d, filled, it) ?: return }`. `fun removeFile(...) { if (draft.locked) return`. The same silent stop happens to the start if a check-in file is refused (`Outbox.kt:157`).
- Why: An expert picks a 400 MB walk-around video from the gallery offline and submits. Back online, Ops never receive the inspection. The phone shows "Sending files" with one red file. Sign-out stays blocked. The only escape is discarding the whole inspection.
- Fix: Check size and type when the file is picked (the same LIMITS table). On Review, block Submit while any file has `error`. In the outbox, set `problem` when `outgoing` returns null, and allow removing a refused file after submit. Size M.

#### HIGH · 16 Offline and sync · A draft for a job that has left the list is invisible, and it blocks sign-out and a new phone forever
- Where: `ui/expert/MyJobs.kt:269` (rows only from `state.jobs`), `ui/expert/Uploads.kt:61-62` (only drafts with unsent files or JOB_CLOSED), `core/draft/Draft.kt:166` (`unsentCounts` counts `!submitSent`), `VayuApp.kt:71-76` (`prune` keeps it), `ui/AppViewModel.kt:213-218` (sign-out refused), `backend/apps/accounts/services.py:69-75` (`DEVICE_HAS_UNSYNCED_DATA`), `backend/apps/bookings/sync.py:19,25-28` (moved job listed 2 days)
- What: Opening a job creates a draft. If the check-in is not finished (`startedAt == null`), the draft never contacts the server, so it never becomes JOB_CLOSED. When Ops move the job, it drops off the sync list after 2 days. The draft then shows nowhere (not My jobs, not Uploads), yet it is counted as unsent work.
- Evidence: Steps: expert taps Start on DEMO-8 (form has a check-in selfie), closes the screen → Ops reassign DEMO-8 → wait more than 2 days and Refresh → My jobs no longer shows DEMO-8, Uploads says "Everything is sent", Profile → Sign out says "This phone still has 1 job … not sent". The heartbeat reports drafts=1, so the server refuses this person's sign-in on any other phone.
- Why: That expert is stuck on this phone. They cannot hand it over or move to a new one. Only "Clear app data" gets them out.
- Fix: In Uploads (or My jobs), list every draft whose job is not in the list, with a Discard button. A draft that never started can also be pruned silently. Size S.

#### MEDIUM · 15 Data integrity · A server-side checksum failure after the phone marked the file "sent" is never re-sent; "Free up" can delete the only copy
- Where: `core/draft/Outbox.kt:34,77,209` (`arrived = uploaded|verified` → `sent=true`); `backend/apps/media/services.py:368-374` (complete returns "uploaded", then verifies in the background); `media/tasks.py:40-44,56-60` (mismatch or unreadable → object deleted, status "failed"); `core/draft/Draft.kt:170-174` (`clearSentCopies`)
- What: In production, verify runs later (Celery). The phone has already set `sent=true` and nothing ever checks again. The comment "the next run registers and sends it again" (`Outbox.kt:208`) only holds when Celery runs eagerly.
- Why: One photo fails verification. The booking waits forever for it, and Ops must "Finish without the missing files". Meanwhile the expert taps Free up space and the only good copy is gone.
- Fix: Treat only "verified" as sent for clearing. Before clearing (or on each run), re-ask `media/{id}`, and on "failed" reset `sent=false`. Size S.

#### MEDIUM · 16/28 Offline, External services · Uploads can stall for hours: new work waits behind a worker in exponential backoff; any non-API exception ends the queue
- Where: `VayuApp.kt:118-139` (`APPEND_OR_REPLACE`, `EXPONENTIAL 30 s`, no `setExpedited`/foreground), `ui/expert/InspectionModel.kt:73,105,119,125` (kick on every photo)
- What: (1) After repeated network errors on weak signal, WorkManager backoff grows to its 5 h cap. Every later kick (a new photo, opening the app) is appended behind the waiting worker, so nothing sends even on good Wi-Fi. (2) `doWork` catches only `ApiError`. A `NullPointerException` (draft discarded mid-run, `Outbox.kt:58-66`) or an `IOException` (disk full) fails the work, and nothing runs until the next user action. (3) There is no foreground or expedited work, so big videos only move in the 10-minute execution windows WorkManager allows.
- Evidence: `enqueueUniqueWork("outbox", ExistingWorkPolicy.APPEND_OR_REPLACE, work)`. WorkManager docs: appended work runs only after the pending predecessor finishes.
- Why: The "Photos for DEMO-8 haven't sent for 2 hours" alert fires while the phone sits on office Wi-Fi.
- Fix: Use `REPLACE` when the head is only waiting in backoff (or `KEEP` plus a separate "now" request), catch `Exception` → `retry`, and use `setExpedited` or foreground for big uploads. Size S.

#### MEDIUM · 22 Performance · Disk IO and hashing on the main thread in the inspection flow
- Where: `ui/expert/Fields.kt:160` → `Wizard.kt:275` → `InspectionModel.kt:84` → `Draft.kt:146` → `Files.kt:11` (`fd.sync()` on every keystroke). `InspectionModel.kt:96` (`sha256(file)` on the main thread: callers `Wizard.kt:167,177,185`, all on the main dispatcher after `withContext`). `ui/ops/Parts.kt:403-405` (Ops upload: `sha256` and `transfer`'s `RandomAccessFile` 8 MB reads on the main thread). `ui/expert/JobsModel.kt:49` (`JobStore.apply` builds and fsyncs the whole sync file on Main). `MainActivity.kt:143-149` (`drafts.all()`, `sentBytes()` stat every file, `StatFs` on every draft tick, which means every keystroke). `Wizard.kt:111` (FormTree re-parsed on every tick).
- What: Each typed character runs JSON encoding plus an fsync of the draft, and stats every file on the main thread. Picking a gallery video hashes up to 300 MB on the main thread.
- Why: Typing lags on a low-end phone. Picking a long video can freeze the screen for seconds or trigger an ANR (Ops replacing a video, too). Not measured on a device.
- Fix: Move `addFile` hashing and Ops `upload` into `withContext(Dispatchers.IO)`. Debounce text saves (or save on IO with an in-memory latest value). Cache `sentBytes`/`FormTree` per tick. Size M.

#### MEDIUM · 13 Correctness · Time marked "verified" forever after the first sync; a later phone-clock change goes undetected
- Where: `ui/expert/JobsModel.kt:72,75` (`verified() = store?.syncedAt() != null`), `core/sync/JobStore.kt:84` (offset frozen at sync), `ui/expert/Tools.kt:114-115` (stamp suffix), `core/draft/Draft.kt:59` (`unverifiedTime` written at `InspectionModel.kt:53`, never read or sent)
- What: Requirement 9 says the time is marked unverified when there was no sync that day. The code says verified if the phone ever synced. The offset is (server − phone) at the last sync, so if the expert changes the phone clock afterwards, stamps shift by that amount and still show as verified.
- Why: Photo stamps and check-in times reach the customer report claiming a checked time that can be wrong by hours or days.
- Fix: Verified = synced today and `elapsedRealtime` continuity (store the elapsedRealtime at sync and compare wall-clock drift). Send `unverified_time` with the start. Size S.

#### MEDIUM · 14 Error handling · An expired session is not handled while the app runs; refresh has no single-flight and shares the 20/min login throttle
- Where: `core/api/Api.kt:232-233,271-278` (no lock; only DEVICE_REVOKED clears), `core/draft/Outbox.kt:42-44,79-89,161-166` (401 becomes a per-file `error` or `problem`; run returns true → `Result.success`), `backend/vayu/settings/base.py:98-99` (refresh 60 days from login, no rotation), `:91` + `accounts/views.py:61-64` (refresh throttled by the "login" scope, 20/min, keyed by IP for unauthenticated calls)
- What: At day 60 every call fails with 401. Until the next cold start, screens show the server's raw "token not valid" text, files show it as their error, and the worker stops (success, no retry). Several screens loading at once each refresh separately, which can hit the throttle, especially for phones behind one carrier NAT IP.
- Why: An expert mid-shift on day 60 sees red errors on every photo and no sign-in prompt. Ops at a desk hit 429 on refresh and get spurious errors.
- Fix: On a 401 after a failed refresh, route to Sign in (keeping drafts). Make the outbox `retry` on 401. Put `@Synchronized`/a Mutex around `refresh()`. Give refresh its own throttle scope. Size S.

#### MEDIUM · 27 Logging · Release crash reports have unreadable stack traces
- Where: `android/app/build.gradle.kts:97-100` (`isMinifyEnabled = true`), plugins `:6-13` (no Sentry Gradle plugin), `gradle/libs.versions.toml:20,59` (only `sentry-android-core`); `VayuApp.kt:86-106` (init on a background thread)
- What: R8 renames every class and method, and no mapping file or ProGuard UUID is uploaded, so Sentry cannot de-obfuscate. Also, `beforeSend` blanks every exception value (`VayuApp.kt:102`), and crashes before the background init finishes are not captured.
- Why: A crash in the field arrives as `a.b.c(Unknown Source)` with no message, so nobody can tell where it broke.
- Fix: Add `io.sentry.android.gradle` with mapping upload (or keep and upload `mapping.txt` per release by hand). Keep exception type plus a scrubbed value. Size S.

#### MEDIUM · 23 Running cost · Videos are not compressed; gallery videos go up as picked
- Where: `ui/expert/Tools.kt:171-172` (`Recorder.Builder().setQualitySelector(QualitySelector.from(Quality.HD))`, no `setTargetVideoEncodingBitRate`), `ui/expert/Wizard.kt:168` (gallery video added unchanged); `docs/android-requirements.md` Camera §3 ("video up to 60 s at 720p, compressed on the phone")
- What: CameraX uses the device's HD encoder profile bitrate, which varies widely by phone (not measured here). Gallery videos (any resolution, up to the 300 MB server limit) are uploaded unchanged over the expert's mobile data.
- Why: Each inspection with a walk-around video can cost the expert tens to hundreds of MB of data and minutes of upload, and it grows R2 storage. At 10× volume this is the main storage line.
- Fix: Set a target bitrate (for example 2–3 Mbps for 720p) and cap or transcode gallery video. Measure on one phone first. Size S (camera) / M (gallery transcode).

#### MEDIUM · 21 Privacy · After sign-out, the person's drafts (customer answers, stamped photos) stay on the phone
- Where: `VayuApp.kt:51-61` (`forgetCopies`: notes, ops copies, cache only), `ui/AppViewModel.kt:154-159,220-228` (sign-out/revoke never touch `drafts-<id>`), `VayuApp.kt:71-76` (`prune` only after this user's own sync, only for completed or gone jobs)
- What: Sign-out requires everything to be sent, yet the `drafts-<id>/` folder (`<booking>.json` with customer name and answers, plus every sent photo and video) is kept. The comment "nothing that person opened stays on the phone" is not true. Submitted-but-not-completed jobs are never pruned once that person stops signing in on the phone.
- Why: A phone passed to a new expert still holds the previous expert's customers' details and car photos, indefinitely (app-private, but against the stated rule and data minimisation).
- Fix: At sign-out (where unsent == 0 is already guaranteed), delete `drafts-<id>` whole. On revoke, delete the drafts that are fully sent. Size S.

#### LOW · 15 Data integrity · Orphan files in the drafts folder are never cleaned
- Where: `ui/expert/Tools.kt:241-251` (`raw.jpg` / `pending` shot lost on process death; `DisposableEffect` doesn't run), `core/Files.kt:10-12` (`.tmp` left if killed between write and rename), `core/draft/Draft.kt:157-163` (discard deletes only files referenced by the draft)
- What: Full-resolution raw photos and unconfirmed shots can be left in `drafts-<id>/files` with no owner, and nothing ever deletes them.
- Why: Storage creeps up, and these copies hold customer car photos.
- Fix: On app start, delete files in `files/` not referenced by any draft and `*.tmp` older than 1 h. Size S.

#### LOW · 14 Error handling · Disk full crashes the app while typing
- Where: `core/Files.kt:11-12` (IOException / `check` failure), called from the UI path `InspectionModel.kt:68` with no catch
- What: When storage hits 0 (the 500 MB start block does not stop videos recorded mid-inspection), any answer change throws on the main thread.
- Why: The app crashes on every keystroke until space is freed.
- Fix: Catch at `InspectionModel.commit`, show "Phone full: free up space", and keep the in-memory value. Size S.

#### LOW · 21 Privacy · Reminder and problem notices show customer name and address on the lock screen
- Where: `Push.kt:57-62` (no `setVisibility(VISIBILITY_PRIVATE)` / public version), `core/alerts/Alerts.kt:30-31` (body = customer · address)
- Fix: `setVisibility(NotificationCompat.VISIBILITY_PRIVATE)` with a public version "Vayu: job reminder". Size S.

#### LOW · 21 Privacy · Ops "Open" hands a signed storage URL to an outside app
- Where: `ui/ops/Parts.kt:549-553` (`Intent(ACTION_VIEW, Uri.parse(url))` for files that are not video)
- What: The browser or viewer keeps a working link to a customer file in its history until the signature expires. The URL comes from the server reply, with no https check here (unlike `Api.download`).
- Fix: Download through `Api.download` into `cache/reports` and open via FileProvider, as the report PDF already does. Size S.

#### LOW · 21 Privacy · Leftovers not wiped at sign-out
- Where: `Push.kt:155-164` (`vayu.stuck` prefs with booking ids, never cleared), `Push.kt:129-133` (reminder WorkManager rows hold title/body with customer and address; cancelled rows stay in WorkManager's DB until it prunes them), `ui/AppViewModel.kt:221` (offline sign-out: `logout` failure ignored, so the server device and refresh token stay live for up to 60 days), `ui/AppViewModel.kt:87` (`lastPassword` kept in memory after a normal sign-in)
- Fix: Clear `vayu.stuck`, call `WorkManager.pruneWork()` after cancelling, retry logout at the next sign-in, and clear `lastPassword` after login unless a change is required. Size S.

#### LOW · 13 Correctness · Reminders use the phone's time zone for IST booking times
- Where: `core/alerts/Alerts.kt:24-26` (`ZoneId.systemDefault()`), same in `JobsModel.kt:104-105`
- Fix: Use `ZoneId.of("Asia/Kolkata")` (the server's zone) for booking date and time. Size S.

#### LOW · 13 Correctness · An offline-started job on an app below the minimum version can never be sent until the app is updated
- Where: `backend/apps/bookings/submissions.py:148-149` (APP_TOO_OLD on start, even for a check-in done before the minimum rose), `core/draft/Outbox.kt:175` (submit waits for start unless NOT_ASSIGNED/INVALID_STAGE)
- What: Requirement 8 ("can finish the current one") is not met when the check-in was done offline.
- Fix: The server accepts a start whose `client_started_at` is before the minimum version changed, or the phone lets the submit go alone on APP_TOO_OLD. Size S.

#### LOW · 16 Offline · The heartbeat is not sent after uploads finish
- Where: `ui/AppViewModel.kt:120,140-150` (only at sign-in and after sync); `OutboxWorker` never calls it
- What: The server keeps the old counts, so a sign-in on a new phone is refused (`DEVICE_HAS_UNSYNCED_DATA`) until this phone happens to sync again.
- Fix: Send the heartbeat at the end of a successful `OutboxWorker` run. Size S.

#### LOW · 22 Performance · The Ops offline cache grows without limit while signed in
- Where: `core/ops/OpsData.kt:26-35` (one file per distinct path, including every search and filter string), `ui/ops/Parts.kt:363-375` (`media-*` full photos in cache)
- Fix: Cap at N files or by age. Size S.

#### NOTE · 20 Security · No certificate pinning
- Where: `core/api/Api.kt:46` (plain `OkHttpClient`). The platform trust store plus no cleartext in release (checked in the APK manifest) is reasonable for now. A user-installed CA cannot intercept by default on API 24+.

#### NOTE · 13 Correctness · Gallery photos are stamped, but the requirement says "gallery photos are not stamped"
- Where: `ui/expert/Wizard.kt:161-166` vs `docs/android-requirements.md` Camera §2. Probably a deliberate later change. Confirm and update the doc.

#### NOTE · 15 Data integrity · A draft file that cannot be parsed is silently ignored
- Where: `core/draft/Draft.kt:135-137` (`runCatching … getOrNull()`). Its photos stay on disk and it is not counted as unsent, so sign-out is allowed. Writes are atomic, so this needs a format change or disk corruption. Consider reporting it to Sentry.

### Strengths worth keeping (max 5)
- Every repeatable step uses a client UUID that the server honours (`Outbox.kt:75,159,179`; `submissions.py:142-147,233-237`; `media/services.py:183-192`). Retries cannot double-submit or double-upload.
- Drafts are written atomically with fsync before the UI acknowledges a change (`Files.kt:7-12`, `Draft.kt:143-150`). Upload resume asks the server which parts it has (`Outbox.kt:230-240`).
- A push carries only a notice id, and the text is fetched with the phone's own sign-in (`Push.kt:87-92`, `notify/push.py:52`), so a shared phone never shows another person's notice.
- The self-update is checked by SHA-256 before it can be installed, kept in a `.part` file until it matches (`Update.kt:57-63`), and served only from `cache/update` through a non-exported FileProvider (`res/xml/shared_files.xml`).
- Sentry is opt-in by DSN and strips message, user, request, breadcrumbs, extras and exception values (`VayuApp.kt:86-104`). Backup and device transfer are excluded (`data_extraction_rules.xml`, `allowBackup=false` in the APK).


## Appendix J: Android: on a real phone

### Coverage
- Files read (code behind what the phone showed): 14 under `android/app/src/main/java/in/carcid/vayu/` (MainActivity, VayuApp, Push, core/draft/Draft+Outbox, core/media/Media, core/update/Update, ui/Screens, ui/UpdateScreen, ui/expert/Wizard+Tools+MyJobs+InspectionModel+Uploads (parts), ui/ops/OpsHome (parts)), `AndroidManifest.xml`, `app/build.gradle.kts`, backend `apps/notify/push.py`, `apps/notify/tasks.py`, `apps/media/services.py:150-165`, `apps/bookings/services.py:155-206`, `scripts/local.sh`.
- Build: `./gradlew assembleDebug -Pvayu.apiUrl=http://localhost:8000/api/v1/ -Pvayu.versionCode=2 -Pvayu.versionName=0.2.0` (versionCode 1 was refused: INSTALL_FAILED_VERSION_DOWNGRADE, the phone had code 2), `adb install -r` OK at 02:15, data kept.
- Tools run: `am start -W` (x3 cold, 1 hot), `dumpsys gfxinfo` (Ops photo grid, My jobs list), `uiautomator dump`, `screencap` (screenshots in `review-2026-11-25/phone/`, numbered 00–72), `dumpsys notification/package/jobscheduler`, `run-as ls/cat` of app files, `pm revoke/grant`, airplane mode via an on-phone script (`cmd connectivity airplane-mode`), `adb reverse --remove tcp:9000` to make storage unreachable, API polling (`bookings/<id>/media`, `/inspections`), celery `worker.log`.
- App state found: signed in as **ops (Priya Ops)**. I signed it out to test the expert, and signed **ops** back in at the end. App left installed (0.2.0, code 2).
- Test data made (all customer names `REVIEW-…`): RV-D1 PDI (in progress, 4 photos; expert draft discarded at the end), RV-D2 PDI (cancelled by me as ops), RV-T1 Field tour (completed), RV-T2 Field tour (assigned).
- Settings: originals font_scale=1.0, always_finish_activities=null, night mode=yes, airplane=0, wifi=1, rotation=1, CAMERA/POST_NOTIFICATIONS/location granted, RECORD_AUDIO not granted. All checked back to these values at 02:58 (incl. permission flags). Two notes: (1) `svc power stayon usb` was run by mistake (sets stay_on_while_plugged_in=2); put back to 0 at once (original almost surely 0: the screen had gone off while charging). (2) `always_finish_activities=1` had no effect on this phone (activity stayed STOPPED; AMS only applies it through Developer options' setAlwaysFinish), so "don't keep activities" is replaced by `am kill` process-death tests; setting deleted again (null).
- Transport: the USB serial 9TL7EYQCHQJVW8S8 kept dropping (a 70 MB `adb install` hung 2 h; "error: closed"), so I used the same phone over Wi-Fi adb (`192.168.29.199:5555`, `getprop ro.serialno` = 9TL7EYQCHQJVW8S8).
- NOT checked, and why: reboot (not allowed); battery saver; a small phone (only this 6.7" phone); back *gesture* (phone is on 3-button navigation and changing it is a system setting; the Back key was tested on every screen); rotation (manifest `screenOrientation="portrait"`, `AndroidManifest.xml:28`; changing rotation settings not allowed); a cut in the *middle* of a part upload (28 MB video went up in under 3 s on the local network, so only "registered but bytes not sent" was tested); self-update screen (needs an AppRelease row on the server that every phone on the local stack would see); picking from the gallery / Files (would upload the owner's personal photos); two phones / two users swapping.

### Scores
| Aspect | Score | One-line reason with evidence |
|---|---|---|
| 25 Android UX and platform | Weak | One "Don't allow" on the camera leaves the expert unable to take the check-in selfie, with no way to fix it from the app (High, shots 32–34) |
| 16 Offline and sync (device) | OK | Offline work, offline submit, force-stop and process death all arrived complete on the server; but sign-out is blocked by drafts that can never send (Medium) |
| 17 Notifications (device) | OK | Push arrives with the app process killed and shows only server text; but a tap after process death opens the old screen (Medium) and blocked notices are silent (Medium) |
| 26 Wording on screen | OK | "job" everywhere on the expert side (known R-15); new: contradicting status texts (Low/Medium) |

### Findings

#### HIGH · 25 Android UX · One camera denial blocks the check-in; no way back from the app
- Where: `android/app/src/main/java/in/carcid/vayu/ui/expert/Tools.kt:120-127` (rememberPermissions), `Tools.kt:248` (the only text)
- What: after the expert taps "Don't allow" on the camera prompt, the camera screen only says "Allow the camera to take photos here." There is no button to the app's settings, and the prompt never comes back (this phone marks the permission USER_FIXED after one denial).
- Evidence: `pm revoke … CAMERA` → open RV-T1 → Start inspection → Camera → system prompt (shot 32) → "Don't allow" → shot 33; close, tap Camera again → no prompt, same text (shot 34); `dumpsys package`: `CAMERA: granted=false, flags=[ USER_SET|USER_FIXED|…]`. The check-in selfie offers Camera only (no Gallery), so the check-in cannot be completed. The shutter still looks active (white).
- Why: an expert at the customer's car who mis-taps once cannot start the inspection and has no hint that the fix is in Android Settings → Apps → Vayu → Permissions.
- Fix: when not granted and `shouldShowRequestPermissionRationale` is false, show "Open settings" (`ACTION_APPLICATION_DETAILS_SETTINGS`) and re-check on resume; grey out the shutter. S.

#### MEDIUM · 17 Notifications · Tapping a notice after Android closed the app opens the old screen, not the lead
- Where: `android/app/src/main/java/in/carcid/vayu/MainActivity.kt:50-54`
- What: the new-intent listener is added in a `DisposableEffect`, which runs after the first frame; when the activity is re-created (process died in the background), `onNewIntent` with the notice's booking id is delivered before that, so it is lost. `opened(intent)` reads the activity's original launch intent.
- Evidence: expert in the RV-D1 wizard → Home → `am kill in.carcid.vayu` → push for "New lead: RV-T1" (arrived, shot 27) → tap → RV-D1 wizard again (shot 28). Repeated with RV-T2 → same (shot 31). With the app alive in the background the same tap opens the lead (shots 29, 30). Same code path for Ops.
- Why: Android kills background apps often (OnePlus especially); an expert tapping "New lead" lands in another inspection and must hunt for the lead; Ops tapping a "problem" notice lands on Today.
- Fix: override `onNewIntent` to call `setIntent` and push the extra to the VM in `onCreate`/`onNewIntent` (not in a composable effect). S.

#### MEDIUM · 16 Offline and sync · Sign-out blocked by drafts that can never be sent; the message contradicts Uploads
- Where: `android/app/src/main/java/in/carcid/vayu/ui/AppViewModel.kt:213-216`, `core/draft/Draft.kt:166`, `VayuApp.kt:74` (prune needs `submitSent`)
- What: sign-out counts every draft not submitted. A lead Ops cancelled (RV-D2) keeps its draft forever (prune skips it) and is not in Today/Upcoming, only under Completed. The Uploads tab says "Everything is sent." while sign-out says work is not sent.
- Evidence: Ops cancelled RV-D2 while the expert was in its wizard → Profile → Sign out → "This phone still has 2 jobs and 0 files not sent. Connect to the internet and wait until Uploads is empty, then sign out." (shot 61); Uploads: "Everything is sent." (shot 60); RV-D2 found only by searching under Completed (shot 62).
- Why: an expert handing the phone back cannot sign out and is told to wait for Uploads, which is already empty; the next person could see the old lead's answers.
- Fix: name the leads in the message with a link to each (Continue / Discard), and say "not finished" for unsubmitted ones vs "not sent" for files. S.

#### MEDIUM · 25 Android UX · Ops lose the open booking when Android closes the app in the background
- Where: `android/app/src/main/java/in/carcid/vayu/ui/ops/OpsHome.kt:53` (`val stack = remember { mutableStateListOf<Route>() }`)
- What: the Ops screen stack is not saved, so after process death Ops come back to Today instead of the booking they had open.
- Evidence: Ops opens RV-D1 booking detail → Home → `am kill` → reopen from launcher → Today (shot 06). The expert wizard, by contrast, came back on the same page with all answers (step and answers are in the draft file).
- Why: Ops switching to WhatsApp/the dialer to call a customer and coming back lose their place, often mid-review.
- Fix: keep the stack in `rememberSaveable` with a Saver (Routes are ids). S.

#### MEDIUM · 16 Offline and sync · "Discard draft" on the lead list and lead page deletes the work in one tap
- Where: `android/app/src/main/java/in/carcid/vayu/ui/expert/MyJobs.kt:313` and `:411`
- What: for a lead taken away or cancelled, "Discard draft" (next to "Submit anyway") deletes all answers and photos on the phone with no confirmation; the same action in Uploads (`Uploads.kt:76-82`) and the wizard asks first.
- Evidence: RV-D2 (cancelled) lead page → tap "Discard draft" → "Draft discarded." at once (shot 62, then dump). Draft file and its photos gone (`run-as ls`).
- Why: a mis-tap beside "Submit anyway" destroys an inspection the expert may still need to send to Ops (cannot be undone).
- Fix: reuse the AlertDialog from Uploads. S.

#### MEDIUM · 17 Notifications · When notices are blocked, nothing tells the expert or Ops
- Where: `android/app/src/main/java/in/carcid/vayu/Push.kt:52-53` (returns silently), `MainActivity.kt:121-130` (asks once), Profile screen
- What: after "Don't allow" on notices, new-lead pushes, reminders and "photos stuck" alerts are dropped silently; Profile and the bell show nothing about it.
- Evidence: revoke POST_NOTIFICATIONS → reopen → prompt (shot 35) → Don't allow (phone sets USER_FIXED) → push for notice 157 sent (`sent 1`) → `dumpsys notification` shows 0 Vayu notices; expert Profile has no notice item (shot 36).
- Why: an expert misses a lead assigned for the next hour and the 2-hour "photos haven't sent" alert.
- Fix: a "Notifications are off · Turn on" row in Profile and the bell, opening `ACTION_APP_NOTIFICATION_SETTINGS`. S.

#### MEDIUM · 25 Android UX · Videos are recorded without sound, with no warning, when the microphone is not allowed
- Where: `android/app/src/main/java/in/carcid/vayu/ui/expert/Tools.kt:154-155`, `:230`
- What: the video camera asks for the microphone; after "Don't allow" it records silent video and says nothing.
- Evidence: RV-T1 "Engine running video" → audio prompt (shot 47) → Don't allow → recorded 25 s → "Use video" → 27.9 MB uploaded and verified, no sound, no message.
- Why: PDI has "Engine noise video" / "Car start video"; a silent one is useless to Ops and the customer, found only after the visit.
- Fix: show "No sound — allow the microphone" on the video camera when RECORD_AUDIO is missing, with a settings link. S.

#### LOW · 16 Offline and sync · A shot left unconfirmed when the app dies stays on the phone forever
- Where: `android/app/src/main/java/in/carcid/vayu/ui/expert/Tools.kt:185` (cleanup only in `onDispose`), no orphan sweep anywhere (`grep listFiles` finds none for drafts)
- What: a photo waiting for Use/Retake when the process dies is never linked to a draft and never deleted, even after Discard and sign-out.
- Evidence: selfie taken, Home, `am kill` → reopen: wizard back, selfie not kept (shot 18); `files/drafts-3/files/493ae8de-…jpg` (530 KB) still there after the draft was discarded and the expert signed out (`run-as ls -laR`).
- Why: a stamped selfie (name, place, time) of one expert stays on a phone that may pass to another; storage slowly fills.
- Fix: at start, delete files in `drafts-*/files` not referenced by any draft. S.

#### LOW · 25 Android UX · A gallery or file pick is dropped if the app is re-created while the picker is open
- Where: `android/app/src/main/java/in/carcid/vayu/ui/expert/Wizard.kt:154-157`, `:171-173` (`picking` is `remember`)
- What: the field being filled is not saved; after re-creation the callback finds `picking == null` and drops the file silently.
- Evidence: code only. Not reproduced: "don't keep activities" could not be enabled by `settings put`, and I did not pick the owner's personal photos (shot 21 shows the picker over the wizard).
- Why: on low-memory phones, the Files picker (full screen) can cause it; the expert thinks the document was added.
- Fix: `rememberSaveable` for the part and field key. S.

#### LOW · 25 Android UX · Back on Ops Bookings or Dashboard leaves the app
- Where: `android/app/src/main/java/in/carcid/vayu/ui/ops/OpsHome.kt:91`
- What: the Back key goes to the phone's home screen from any Ops tab, not to Today first.
- Evidence: Ops → Bookings tab → Back → `mCurrentFocus=…Launcher`.
- Why: Ops expecting Back to return to Today close the app (small, but every day).
- Fix: `BackHandler(tab != TODAY) { tab = TODAY }`. S.

#### LOW · 25 Android UX · Font size 1.3: dates cut off and bell counts cover the bell
- Where: My jobs list row date column; top bar badge
- What: at font scale 1.3 the date shows "22 No", "23 No" and the unread badge (6, 26) covers the bell icon.
- Evidence: shots 40 (My jobs) and 70 (Ops Today). Wizard, lead page and Ops booking detail were fine (shots 43, 44, 71, 72).
- Why: older experts with large text cannot read the month of overdue leads.
- Fix: let the date column wrap or use "22/11"; offset the badge. S.

#### LOW · 25 Android UX · Sign-in: the keyboard hides the password and Sign in, and its key says Done
- Where: `android/app/src/main/java/in/carcid/vayu/ui/Screens.kt:107-108`
- What: after typing the username, the password field and button are under the keyboard; the keyboard key is ✓ (no Next to jump to password). The page scrolls by hand.
- Evidence: shot 13a (keyboard over the form), 13b after a manual scroll.
- Why: every sign-in takes extra taps; new users think the form has no password field.
- Fix: `ImeAction.Next` on username, `ImeAction.Done` → sign in on password. S.

#### LOW · 26 Wording · A cancelled lead's page does not say it is cancelled
- Where: expert lead page for a cancelled lead (`MyJobs.kt` lead detail)
- What: no customer name, no "Cancelled" chip or reason, and "Ready to work without signal" in green.
- Evidence: shot 62 (RV-D2 after Ops cancelled it with reason "Customer cancelled"; the bell has "RV-D2 cancelled", shot 59).
- Why: the expert cannot tell why "Discard draft / Submit anyway" appear.
- Fix: show the stage chip and Ops' reason; hide "Ready to work without signal" for closed leads. S.

#### LOW · 26 Wording · Status texts that contradict themselves
- Where: Submitted screen; Ops Today expert rows
- What: Submitted screen says "All files sent · 2 of 2" and right under it "They keep sending in the background, even with the app closed."; Ops Today rows show "10:00", "23:30" (24 h) beside "Next at 10:00 am".
- Evidence: shot 54 (submitted offline); Ops Today dump (`'10:00'` row, `'Next at 10:00 am'` subtitle).
- Why: small confusion; mixed time formats on one screen.
- Fix: show the "keep sending" line only while files are left; one time format. S.

#### LOW · 25 Android UX · Locked wizard pages look tappable and do nothing
- Where: `android/app/src/main/java/in/carcid/vayu/ui/expert/Wizard.kt:324`, `:341`
- What: in the page list, pages after a "finish first" page are disabled; tapping one does nothing, and the reason is printed only at the bottom of a 17-row sheet.
- Evidence: RV-D1 page list → tap "Engine" → nothing (shot 24).
- Why: the expert thinks the app is stuck.
- Fix: put "Finish Vehicle to open the other pages" at the top, or show it as a message on tap. S.

#### LOW · 17 Notifications · The local stack never sends pushes
- Where: `scripts/local.sh:72-73`
- What: the celery worker starts without `--env-file .env.local`, so `FIREBASE_CREDENTIALS_FILE` is empty and the push task sends nothing.
- Evidence: `worker.log:1382-1384` `apps.notify.tasks.push … succeeded in 6.3e-05s: 0` for the RV-T1 assignment; `ps eww` of the worker has no FIREBASE variable. Calling `push([156])` by hand with `uv run --env-file .env.local` returned `sent 1` and the phone showed it.
- Why: anyone testing pushes on the local stack concludes push is broken.
- Fix: pass `--env-file .env.local` to worker and beat in local.sh. S.

#### NOTE · 16 Offline and sync · Force-stop pauses all sending until the app is opened
- Evidence: odometer photo registered while storage was unreachable → `am force-stop` → storage back → still `pending` after 75 s; opened the app → `verified` within 5 s. This is Android's rule for force-stopped apps; worth one line in the expert guide ("don't force-stop Vayu").

#### NOTE · 26 Wording · Off-rule "job" words seen on the phone (known R-15; listed for the fix)
- Sign-in "Welcome back. Your jobs are waiting." (`Screens.kt:105`, shown to Ops too), "My jobs" title, "Jobs" tab, "Back to My jobs", "No job matches \"RV-D2\".", sign-out "2 jobs … not sent", Android notification channel "Jobs and updates" (`Push.kt:46`, visible in Android settings), Ops "Force release this job?" (`ui/ops/Booking.kt:268`). 41 string literals with job/jobs in `app/src/main`.

#### NOTE · 25 Android UX · Ops photo grid uses 3 columns on a wide phone
- Evidence: shot 09: fixed-size tiles leave the right quarter empty; 66 photos need more scrolling than needed.

### Device results (step tables)
| Case | Result |
|---|---|
| Cold start `am start -W` (x3) | 1257 / 1059 / 1236 ms; hot 107 ms |
| Jank, Ops photo grid (66 photos), 12 flings | 837 frames, 0.60 % janky, p90 13 ms, p99 17 ms |
| Jank, expert My jobs list, 10 flings | 583 frames, 0.17 % janky, p90 12 ms, p99 16 ms |
| Airplane on, take cover photo + type chassis, 50 s, airplane off | Photo + answer kept; photo `verified` on server ≤10 s after the phone could reach the server again |
| Storage unreachable, photo taken, `am kill` in background, storage back | Sent by WorkManager without opening the app: `verified` ~30 s later |
| Storage unreachable, photo taken, `am force-stop`, storage back | Not sent until the app was opened (then <5 s) |
| Submit with airplane on, back online after 30 s | Server: stage `completed`, answers (chassis, reg, odometer, bonnet, payment) and 2 files exactly as entered, ~30 s after reconnect |
| `am kill` in the wizard | Reopens the same lead and page with all answers; an unconfirmed shot is lost (orphan file) |
| `am kill` on Ops booking detail | Back on Today (lost) |
| Push, app process killed | Shown ("New lead: RV-T1"), app woken; tap opens old screen (finding) |
| Push, app in background | Shown; tap opens the lead |
| Ops cancels a lead the expert is working on | Bell notice "RV-D2 cancelled"; wizard shows no sign; photo taken after cancel still accepted by the server (by design, `apps/media/services.py:156-162`) |
| Sign-out (Ops) | `files/ops-2` emptied, prefs cleared, notices cleared |
| Back key on every screen | Wizard→lead→list; camera/Shot check→form; photo viewer→grid→booking→list; keyboard closes first. Ops tabs exit the app (finding) |

### Strengths worth keeping (max 5)
- Offline-first works on a real phone: offline photos, answers and a full submit reached the server complete (`/inspections` answers match what was typed; media `verified`).
- WorkManager picks up unsent files after process death with no user action (~30 s), and the client UUIDs made the re-sends safe (no duplicate media rows).
- Push carries only the notice id; the text comes from `GET notifications` with the phone's own sign-in (`Push.kt:84-95`), and it arrived with the app process killed.
- Sign-out clears Ops copies and auth prefs (`run-as ls`: `ops-2` empty, `vayu.auth.xml` empty map).
- Smooth and quick: 0.2–0.6 % janky frames on the longest lists, ~1.1–1.3 s cold start.


## Appendix K: Product: requirements trace, delivery, metrics, docs, journeys J1–J8

Hat: technical product manager (engineering background). Baseline: working tree = `refs/review/baseline` (`ba4b7df`).

### Coverage
- **Files read (whole or the relevant parts): ~75.** Requirements and plans: `REQUIREMENTS.md`, `plan.md` (amendments §600–700), all 9 `docs/plan-*.md` (status lines, open questions, phase notes), `docs/android-requirements.md`, `docs/review-strategy.md`, `docs/review-report-2026-11-24.md`. Docs: `README.md`, `docs/local.md`, `integrations.md`, `accounts-setup.md`, `benchmarks.md`, `r2-check.md`, `android-ops-report-auto.md`, `android-lead-words.md`, heads of `ui-review.md`, `pdi-field-map.md`. Backend: `accounts/{views,services,permissions,roles,catalog,authentication}.py`, `bookings/{views,services,submissions,stages,models,activity}.py`, `media/{services,tasks}.py` (+`flag_stuck_uploads`), `notify/{handlers,tasks}.py`, `integrations/{webhooks (routing),ext_views,apikeys,views (keys, scope, docs)}.py`, `reports/{tasks,handlers,views (report, verify)}.py`, `core/app_settings.py`, `core/events.py`, settings `base.py`/`prod.py`, `infra/docker-compose.prod.yml`, `setup_platform.py` header, `publish_apk.py`. Web: `App.tsx`, `guards.tsx`, `Layout.tsx`, `auth.tsx`, `lib/problems.ts`, parts of `pages/ops/Booking.tsx`, `pages/admin/Users.tsx`, `pages/ops/Dashboards.tsx`. Android: `core/media/Media.kt`, `core/alerts/*`, `ui/expert/Storage.kt`, `ui/AppViewModel.kt`, `Push.kt`, `VayuApp.kt`, parts of `Wizard.kt`, `MyJobs.kt`, `Tools.kt`, `Outbox.kt`, `ui/ops/Booking.kt`, manifest. Tests: grep-mapped per rule (backend 70 test files, Android 19).
- **Tools run:** local API with session cookies (`curl`) as `admin`, `ops`, `expert`, `expert19`, `expert20`; mobile-token logins for `expert19` only (never `expert`, to not sign out the owner's phone); read-only `manage.py shell` queries (`Delivery`, `Notification`, `MasterListItem`); `git log` / `git log -S`; grep across all layers.
- **Data I created (all named REVIEW-):** bookings `REVIEW-J1` (renamed `REVIEW-J1B` during the test; completed with PDF rev 3) and `REVIEW-J2` (submitted, waiting for files), their media (tiny JPEGs), one API key `REVIEW-key` (created and **revoked**). Side effects: bell rows for `expert19`, `expert20`, Ops users; webhook deliveries to the demo integrations (all "retrying": no receiver running); `expert19` phone devices revoked (that user has no real phone). Nothing existing was changed or deleted.
- **Not checked, and why:** no phone/emulator (Android parts are code-read only: camera stamp, WorkManager reminders, self-update install); J4 form publish/pinning by code and tests only (I did not publish a form on the shared stack); J6 push delivery (no Firebase credential locally); J8 `setup_platform` not run (would write to the shared DB; R-07 known) and the self-update flow not run; full web UI walk-through (another hat).

### Scores
| Aspect | Score | One-line reason with evidence |
|---|---|---|
| 1 Requirements fit (B) | **Weak** | Server enforces almost every rule (role probes all refused correctly, see table), but stuck-upload alerts never fire (P-01), assignment webhooks double (P-02), completion is not a `booking.updated` (P-03). |
| 1 Requirements fit (W) | OK | Ops can't sign a phone out on web (P-08), no APK download page (P-11), Ops read-only forms/library not reachable (P-09). |
| 1 Requirements fit (A) | OK | Gallery photos stamped against the rule (P-10), "unverified time" computed but never sent (P-07); rest matches (Admin refused, storage gates, min version, reminders). |
| 2 Product and delivery (all) | **Weak** | R-01/R-07 still block launch; plus P-11 (no APK page), P-01, no deploy runbook (P-27); 1 open question still open; REQUIREMENTS.md not updated for 6 agreed changes (P-25). |
| 3 Product metrics (B; W/A —) | OK | Duration, late start, per-expert volume, Ops edits, webhook failures answerable; upload-failure history overwritten, PDF failures keep only the last state, no app version per device (P-29, table below). |
| 30 Documentation (all) | OK | Medium: REQUIREMENTS.md out of date (P-25), no setup/deploy runbook (P-27); Low: local.md, android-ops-report-auto.md, r2-check.md, integrations.md claims wrong (P-26). |

### Findings

#### HIGH · 1 Requirements fit · Stuck-upload alerts never fire: no webhook, no Ops bell/push
- Where: `backend/apps/media/management/commands/flag_stuck_uploads.py:12-16` (the only place that emits `alert.stuck_upload`); `backend/vayu/settings/base.py:129-134` (beat schedule has retry-webhooks, sweep-reports, purge-media, late-starts, **not** this); `infra/docker-compose.prod.yml` (no cron); no doc or script mentions it (`grep -rn flag_stuck_uploads infra scripts docs` → nothing).
- What: the event behind REQUIREMENTS §8 "stuck-upload alerts" and android-requirements "Ops pushes: … stuck uploads" is only raised by a management command that nothing runs.
- Evidence: `grep -rn 'alert.stuck_upload"' backend/apps` → emit only in the command; the test calls it by hand (`media/tests/test_upload.py:481`). The Needs-you list still shows stuck uploads because it queries the table (`media/views.py:121`), so the gap is invisible on web.
- Why: an ERP/WhatsApp integration subscribed to `alert.stuck_upload` (the demo has "Alerts: stuck upload") never receives one; Ops on the phone never get the "Photos stuck for DEMO-x" push, so a customer's report can sit unfinished for days unless someone opens Needs you.
- Fix: add `flag_stuck_uploads` logic as a Celery beat task (every 15 min) + a test that the schedule contains it. **S**

#### HIGH · 1 Requirements fit · Every assignment sends `booking.updated` twice to integrations
- Where: `backend/apps/bookings/services.py:168-169` (`_changed` emits `booking.updated`, then `booking.assigned` is emitted); `backend/apps/integrations/webhooks.py:33` maps `booking.assigned` → `booking.updated`.
- What: one assign = two deliveries with different `X-Vayu-Delivery` ids, 3 ms apart.
- Evidence: `Delivery` rows for REVIEW-J1 after one `POST bookings/<id>/assign`: `booking.updated {'changed_keys': ['assigned_expert','stage']}` and `booking.updated {'changed_keys': ['assigned_expert']}`; same pair on DEMO-90, DEMO-91, DEMO-41 in the local DB.
- Why: REQUIREMENTS §8 "fires on every occurrence"; `docs/integrations.md` tells receivers to dedupe by `X-Vayu-Delivery`, which can't work here. A CRM that sends "expert assigned" SMS to the customer sends it twice per assignment.
- Fix: drop the mapping of `booking.assigned` to a public event (notify still uses it), test "one assign → one delivery". **S**

#### HIGH · 1 Requirements fit · "Completed" (and Ops "finish") is never sent as a `booking.updated` stage change
- Where: `backend/apps/media/services.py:413-435` (`check_completion` saves `stage="completed"`, emits only `inspection.completed` + `media.completed`); `:530-556` (`finish_without_missing`, only `inspection.completed`). Neither is in `webhooks.PUBLIC` as a booking event.
- What: REQUIREMENTS §8 "booking created/updated/deleted (incl. stage changes)" and `docs/integrations.md:11` ("updates include assignment and stage changes") are false for the most important stage move.
- Evidence: J1 run: REVIEW-J1's deliveries show `booking.updated` for assign, reschedule, type, ID edit, `in_progress`, `submitted`, then nothing when the booking became `completed` (verified via `GET bookings/<id>` → `completed`).
- Why: an ERP that tracks stage through `booking.updated` (the only booking-form events) never marks the job done; payouts and customer follow-ups stall.
- Fix: emit `booking.updated` with `changes={"stage": ["submitted","completed"]}` in both places (after commit); test. **S**

#### MEDIUM · 1 Requirements fit · Reports regenerate on every change, and each revision fires `pdf.ready` to customer-facing integrations
- Where: `backend/apps/reports/handlers.py:1-23` (re-render on `inspection.updated`, `media.deleted`, `booking.updated`), `reports/tasks.py:121` (`pdf.ready` each revision). REQUIREMENTS §7 still says "regenerated with a Regenerate PDF button"; `docs/local.md:41` still tells reviewers to press Regenerate.
- What: built differently from the written requirement (the change is recorded only in `docs/android-ops-report-auto.md`), with a side effect nobody wrote down.
- Evidence: J3 run: two Ops edits on REVIEW-J1B → `pdf.ready` deliveries for revisions 1, 2, 3 to "WhatsApp: PDF ready". Any `booking.updated` on a completed booking (e.g. Ops editing a payout field) also re-renders.
- Why: Ops fixing three typos one by one sends the customer three "your report is ready" messages, and the customer's link changes content without Ops deciding it is final.
- Fix: decide with the owner: either debounce (one `pdf.ready` per N minutes) or fire `pdf.ready` only for revision 1 plus an explicit "Send updated report" action; update REQUIREMENTS §7. **S–M**

#### MEDIUM · 1 Requirements fit · Media retention + auto-regenerate silently strips photos from a customer's PDF
- Where: `backend/apps/media/tasks.py:72-108` (purge after Admin's days; marks `purged`), `reports/render.py:60` (only `status="verified"` photos are drawn), `reports/tasks.py:111-113` (old PDF deleted).
- What: retention was built (commit `0daa0e4`) although REQUIREMENTS §10 says "keep everything; set a policy later" and no plan covers it; once photos are purged, any later change re-renders the report without them and deletes the old PDF.
- Evidence: code path above; default is 0 = keep (`core/app_settings.py:11`), so it bites only after an Admin sets days.
- Why: an Admin sets 180 days to save cost; a year later Ops correct the customer's phone number on an old booking → the report the customer downloads now has empty photo grids, and the full one is gone.
- Fix: never re-render a report whose photos were purged (keep the last PDF), or skip purge for photos used by a report; write the policy into REQUIREMENTS. **S**

#### MEDIUM · 1 Requirements fit · Rejected type-change alerts can never be cleared from Needs you
- Where: `backend/apps/bookings/views.py:85-88` (`problem=type_change` = any booking whose `alerts` contains the code), `submissions.py:123-124` (alerts only appended); no code removes or reviews alerts; `web/src/lib/problems.ts` lists them with no date limit.
- Evidence: `GET bookings?problem=type_change` as Ops → `REVIEW-J1B (completed)`, `DEMO-15`; REVIEW-J1B was finished long before and still shows "type change rejected".
- Why: Needs you grows by one row per rejected type change for ever; after a few weeks Ops stop trusting the list and miss real problems.
- Fix: "Mark reviewed" for this alert (like timing flags) or show only the last 7 days. **S**

#### MEDIUM · 1 Requirements fit · "Unverified time" is half-built: the phone computes it, nobody receives it
- Where: Android `ui/expert/InspectionModel.kt:53`, `core/draft/Draft.kt:59,80` (stored locally only; not in `Outbox.kt`/`Api.kt`); server has no field (`grep -rn unverified backend/apps` → nothing). REQUIREMENTS §6 and §9 (problem queue "unverified times") still promise it; `plan.md:644` says "not built".
- Why: an expert with a wrong phone clock and no sync that day submits a job "on time"; Ops can't tell, and the started-late flag (server clock) only covers starts that reached the server.
- Fix: decide: send `unverified_time` with start/submit and show a badge, or remove it from REQUIREMENTS and the app. **S**

#### MEDIUM · 1 Requirements fit · Ops can't sign a person's phone out on the web
- Where: `web/src/App.tsx` `/users` route `adminOnly`; `web/src/Layout.tsx:42` `OPS_PAGES` excludes `/users`; the only button is `pages/admin/Users.tsx:86`. Android Ops has it (`ui/ops/Booking.kt:271`).
- Evidence: Ops holds `users.sign_out_devices` (`GET auth/me` as ops) and the API works for Ops (J5: `POST users/23/sign-out-devices` as ops → 200), but no web page reachable by Ops calls it.
- Why: REQUIREMENTS §2/§9: Ops force sign-out for lost phones. An Ops person at a desk with a lost-phone call must find an Admin or pick up their own phone.
- Fix: add "Sign out their phone" to the expert row on the web booking page (same confirm text as Android). **S**

#### MEDIUM · 1 Requirements fit · The role matrix promises things the web never shows (Ops)
- Where: `web/src/Layout.tsx:40-55` ("Ops only ever work with bookings … whatever permissions their role has") and `guards.tsx:10` `adminOnly` on forms, library, lists, PDF, integrations, API keys, users, audit.
- What: REQUIREMENTS §2 says permissions are configurable per role and Ops have "read-only view of forms and library"; on web Ops can't open either, and any template/integration grant an Admin ticks for Ops in Roles does nothing in the UI (the API honours it).
- Why: an Admin grants Ops "Manage webhooks" to delegate work; Ops see nothing; the Admin thinks the grant failed. Conversely the API is wider than the UI suggests (R-34 Note).
- Fix: either drive the menu from permissions only (drop `adminOnly`), or mark those permissions not grantable and update REQUIREMENTS §2. **S**

#### MEDIUM · 1 Requirements fit · Gallery photos get the camera stamp, with the pick time and current GPS
- Where: `android/app/src/main/java/in/carcid/vayu/ui/expert/Wizard.kt:161-166` (`stampPhoto(... stampLines(draft.code, …, env.now(), …, Locator.last) … + " · gallery")`).
- What: REQUIREMENTS §5.3 and android-requirements "Camera 2": gallery photos are **not** stamped; the source is internal and never shown in the PDF. Here the stamp is burned in, with "· gallery" visible.
- Why: a photo taken last month is stamped with today's time and the car's current location, so it looks like proof from this inspection (the "· gallery" suffix is easy to miss); and "gallery" is printed in the customer's report.
- Fix: don't stamp gallery photos (resize only); keep `source` internal. **S**

#### MEDIUM · 2 Delivery · No APK download page on the web
- Where: REQUIREMENTS §10 "APK is served from a logged-in download page on the web app"; server has `GET app/download` (`notify/views.py:94`) but `grep -rn "app/download" web/src` → nothing.
- Why: the only way to install the app on a new expert's phone is a link someone sends by hand; launch blocker for distribution.
- Fix: a "Get the Android app" item in the profile menu linking to `/api/v1/app/download`. **S**

#### MEDIUM · 2 Delivery / 30 Docs · No runbook for a fresh server (J8)
- Where: `setup_platform` (users CSV, forms, reports), `publish_apk`, `seed_master_lists`, beat/worker setup: none is mentioned in `README.md`, `docs/local.md`, `plan.md` or any doc (`grep -rn "setup_platform\|publish_apk" docs README.md plan.md` → only the review docs).
- Why: on launch day nobody but the author knows the order: migrate → `setup_platform --users staff.csv` → `publish_apk` → set `MIN_APP_VERSION`, `VERIFY_BASE_URL`, Firebase file; a missed step (e.g. no APK row) shows as "No app build has been published yet".
- Fix: `docs/deploy.md` with the exact steps and checks (fold into launch prep). **S**

#### MEDIUM · 1 Requirements fit · API keys can't assign, reassign, cancel, reschedule or change type
- Where: `backend/apps/bookings/services.py:22` `ACTION_ONLY`; `integrations/ext_views.py` offers only list/create/get/patch/delete/bulk/inspection.
- Evidence: J7 run: PATCH with `assigned_expert` on an ext booking → refused (`OUT_OF_SCOPE`, and with full scope it would be `USE_ACTION`, `services.py:111-113`).
- Why: REQUIREMENTS §8 "full CRUD"; an ERP that dispatches experts can create an assigned booking but can't move it to another expert or cancel it when the customer calls the call centre.
- Fix: ext endpoints for assign / cancel / reschedule reusing `services.*` (scoped by a key flag). **M**

#### MEDIUM · 30 Documentation · REQUIREMENTS.md not updated for six agreed changes
- Where: §7 (Regenerate button → automatic), §6 + §3 (conflict always flagged → owner rule 2026-11-24, no conflict when the new expert never started, `bookings/tests/test_submissions.py:205-218`), §9 problem queue (unverified payments, pay-later, not regenerated, unverified times: not built, `plan.md:644`), §2 (Ops read-only templates; Android Ops parity), §10 retention, §5.3 gallery.
- Why: REQUIREMENTS is "the what" per README; anyone testing against it reports false bugs or misses real ones; both force-release dialogs still promise a conflict (`web/src/pages/ops/Booking.tsx:813`, `android/.../ui/ops/Booking.kt:269`), which is now wrong when the new expert hadn't started (J2 run: REVIEW-J2 went back to expert19 with `conflict=""`, no alert).
- Fix: one pass over REQUIREMENTS with a dated "changed" note per item; fix both dialog texts. **S**

#### LOW · 1 Requirements fit · Experts see Ops review activity (ratings and Key Check changes)
- Where: `backend/apps/bookings/activity.py:57-60` excludes only timing and report rows for experts.
- Evidence: `GET bookings/<DEMO-3>/activity` as `expert` → rows `{"kind":"key_checks_changed","by":{"role":"ops","name":"Priya Ops"}}`.
- Why: REQUIREMENTS §5.4 "Experts never see or set ratings" and §6 "Nothing goes back to the expert"; the expert learns Ops changed their scores. Fix: exclude `ratings_changed`, `key_checks_changed` for experts. **S**

#### LOW · 1 Requirements fit · Ops can set rating overrides on an unsubmitted inspection
- Where: `backend/apps/bookings/submissions.py:406-418` (stage check only for Key Check texts).
- Evidence: J2 run: `PATCH inspections/<REVIEW-J2 draft>/overrides {"ratings":{"engine":1}}` → 200, `status: draft`; the override then applied to the submitted inspection.
- Why: an Ops misclick on a running job decides the Engine rating before anyone saw the car. Fix: 409 unless the inspection is submitted. **S**

#### LOW · 1 Requirements fit · Type-change-rejected alert goes to integrations of the rejected type
- Where: `submissions.py:155-158` emits before `b.answers` changes; `webhooks.targets()` reads the booking's (old) type.
- Evidence: J1: REVIEW-J1 (Ops changed to used_car, expert started pdi) produced no `alert.conflict` delivery although "Alerts: conflict" is on the PDI form.
- Fix: emit after `sync_columns(b)`. **S**

#### LOW · 1 Requirements fit · Expert notifications show raw keys
- Where: `backend/apps/notify/handlers.py:56-65`.
- Evidence: expert20's bell: "Inspection type: pdi → used_car", "Booking id: REVIEW-J1 → REVIEW-J1B".
- Fix: use field labels and option labels from the booking form. **S**

#### LOW · 1 Requirements fit · Check-in answers are validated at Start but not kept
- Where: `submissions.py:161-170` (`_clean_all` result discarded; `Inspection` created without answers).
- Evidence: J1 start response: `inspection.answers == {}` although selfie and GPS were sent.
- Why: until submit, Ops can't see the arrival selfie/GPS of a running job; a phone lost mid-job loses proof of arrival. Fix: store `answers["start"]` at Start. **S**

#### LOW · 1 Requirements fit · Web sign-out is not blocked while work is unsent
- Where: `web/src/ui/TopBar.tsx:122` → `auth.tsx` `logout` (no check of drafts / upload queue). REQUIREMENTS §6 "Logout is blocked while data is unsynced"; Android does block (`ui/AppViewModel.kt:210-218`). Different from R-06 (privacy of what stays). Fix: same check as Android using `lib/store.ts`. **S**

#### LOW · 1 Requirements fit · Deactivate warning is generic, not based on the phone's real state
- Where: `web/src/pages/admin/Users.tsx:132`; the server knows `Device.unsynced` (`accounts/models.py:79`). REQUIREMENTS §6: warn when the account **has** unsynced data. Fix: show "their phone still holds 1 job and 3 files" from the device row. **S**

#### LOW · 1 Requirements fit · Video uploads are not checked to be videos
- Where: `backend/apps/media/tasks.py:38-72` (only photos/files are decoded).
- Evidence: J1: 3 JPEG files uploaded as `video/mp4` were marked `verified` and the booking completed. Fix: check the MP4/MOV header (`ftyp`) before verifying. **S**

#### LOW · 30 Documentation · Swagger is Admin-only, so API integrators can't read it
- Where: `backend/apps/integrations/views.py:447-452` (`roles.manage`); REQUIREMENTS §8 "Auto-generated Swagger docs" for key users. Fix: publish a static copy of the ext part, or allow API keys to read it. **S**

#### LOW · 30 Documentation · Stale or wrong docs
- `docs/local.md:38,41,53`: "Job board", "Ratings tab", "Report tab: Out of date → Regenerate" (no such step; nav is Today / Bookings / Needs you, `web/src/Layout.tsx:17-36`).
- `docs/android-ops-report-auto.md:1` "(to do)": built in `5b3d00a` (`ui/ops/Parts.kt:714-763`).
- `docs/r2-check.md` step 4 "expect status: verified": `complete` returns `uploaded`, verification is async (J1: `POST media/<id>/complete` → `"status":"uploaded"`, `verified` 3 s later).
- `docs/integrations.md:11,15`: stage changes and stuck-upload alerts claimed (see the two High findings).
- `docs/accounts-setup.md`: Firebase and keystore "Phase 15" (done; plan-android says Phase 17); CORS list fine.
- `README.md:9`: Android "(from Phase 13)" (R-27 known).
- Fix: one doc pass with the R-08 status fix. **S**

#### LOW · 19 Testing (product-critical paths without a test)
- Android "sign-out blocked while unsent" has no UI test (only `unsentCounts`, `OutboxTest.kt:155`); `stampPhoto` (gallery/camera stamp) untested; the stuck-upload *schedule* untested (only the command, `media/tests/test_upload.py:481`); no test that one assign = one webhook. Fix: four small tests. **S**

#### LOW · 3 Product metrics · History needed for metrics is overwritten
- Where: `media/services.py:186-191` (a failed upload is reset to `pending` on retry: the failure is gone), `reports/models.py:64-80` (one row, last status only), `accounts/models.py:70-86` (no app version per device), `notify/tasks.py:22-28` (push success not stored), `BookingActivity` cascades on booking delete. Adds evidence to R-38. Fix: keep `failed_attempts` on MediaAsset, `app_version` on Device (from heartbeat), a `ReportRender` log row. **S**

#### NOTE · 2 Delivery · Notification rules built slightly differently from android-requirements
- Late-start push uses the Settings grace (default **15 min**, `notify/tasks.py:43`), not "30 min past its time"; "New bookings" push only for API/ERP-created bookings (`notify/handlers.py:86-89`) and the plan's open question (`docs/plan-android.md:18-20`) is still open. Owner to confirm both.
- Photos target ≤700 KB, not ~500 KB (`core/media/Media.kt:82-85`); fine on cost, note only.

### Strengths worth keeping
- Every role rule probed through the API held: Ops 403 on templates/lists/users/integrations/keys/roles/audit/settings writes, `DELETE` on assigned/completed bookings → `DELETE_NOT_ALLOWED`, no submission delete endpoint (405); experts see only their own (21 bookings, all expert 3), 404 on others, 403 on reports/overrides/dashboards; Admin refused on mobile (`ADMIN_USE_WEB`).
- One-phone rule works end to end: second sign-in refused while the first holds work (`DEVICE_HAS_UNSYNCED_DATA`), old token and refresh dead after a clean switch (`DEVICE_REVOKED`), Ops can't sign out an Admin (`ADMIN_ONLY`).
- Offline rules are idempotent and race-safe: replayed start/submit return the same result (`client_start_uuid`, `client_submission_uuid`), stale edits answer 409 with who/what changed, expert's started type wins with an alert.
- Scoring matches §5.4 exactly (J3: Major −1 → 4, Critical caps overall at Average with avg 3.6, Ops override kept through a recalculation).
- Booking ID trimmed + case-insensitive unique (`"  REVIEW-J1  "` stored as `REVIEW-J1`, `" review-j1 "` → `DUPLICATE_BOOKING_ID`), and an ID edit carries `booking_id_change` to webhooks.

---

### A. Traceability table (requirement → server → web → Android → test → status)
Paths: B = `backend/apps/`, W = `web/src/`, A = `android/app/src/main/java/in/carcid/vayu/`. "API ✓" = verified by calling the local API in this review.

#### A1. Roles, users, security (REQUIREMENTS §2, android-req "Who and what")
| # | Rule | Server | Web | Android | Test | Status |
|---|---|---|---|---|---|---|
| 1 | Three roles, one per user | B accounts/models.py (Role) | — | — | accounts/test_permissions.py | met |
| 2 | Permissions configurable per role, Admin locked, `roles.manage` ungrantable | B accounts/roles.py:39-41, catalog.py:23 | W pages/admin/Roles.tsx:54 | — | test_permissions.py (NOT_GRANTABLE) | met (UI side: P-09) |
| 3 | Scoped own/all on bookings, submissions, reports | B permissions.py:29; bookings/views.py:52-57, 273-275 | — | — | bookings/test_access.py | met, API ✓ (expert sees 21 own) |
| 4 | Only Admin manages Admin users | B accounts/views.py:201, 286, 303 | — | — | test_permissions.py | met, API ✓ (`ADMIN_ONLY`) |
| 5 | Ops defaults: daily ops only, no templates/users/integrations/keys/permissions | B catalog.py:61-69 | W Layout.tsx:42 | A (Ops screens) | test_permissions.py | met, API ✓ (all 403) |
| 6 | Ops cannot delete bookings or submissions | B bookings/services.py:250-254 (drafts only, per android-req "delete drafts"); no submission delete route | W ops Booking delete hidden | A ui/ops/Booking.kt:272 (drafts) | bookings/test_lifecycle.py | built differently (agreed: Ops may delete unworked drafts), API ✓ |
| 7 | Ops read-only view of forms and library | B perms `forms.view`, `library.view` granted | **not reachable** (W guards.tsx:10, Layout.tsx:42) | — | — | built differently (P-09) |
| 8 | Ops regenerate/view reports | B reports/views.py:148 (view); regenerate removed | W ops Booking report row | A ui/ops/Parts.kt:714 | reports/test_reports.py | built differently (automatic, P-04) |
| 9 | Users: name, email, username, password, role, active; never deleted | B accounts/views.py UserViewSet destroy → 405 | W admin/Users.tsx | — | test_users_admin.py | met |
| 10 | Android: expert + Ops; Admin refused | B accounts/views.py:52-55 | — | A ui/AppViewModel.kt:90, ui/Screens.kt:125-130 | test_devices.py, SignInFlowTest | met, API ✓ |
| 11 | Builder, PDF designer, lists, users, integrations, keys web-only | B perms; app has no such screens | W admin pages | A none | — | met |
| 12 | Field access per role per stage | B forms/access.py:55; bookings/services.py:115-123; submissions.py:218 | W lib/access.ts | A uses `level` from server tree | bookings/test_access.py | met |
| 13 | Experts see only assigned bookings (+ own drafts) | B submissions.py:72-75 | W expert/MyJobs | A JobStore via sync | test_access.py, test_sync.py | met, API ✓ (404 on DEMO-6) |
| 14 | Tap-to-call customer phone | — | W expert/MyJobs.tsx:100 | A ui/expert/MyJobs.kt:386 | MyJobsTest | met |
| 15 | Lockout after failed logins | B accounts/services.py:25-51 (5 / 15 min) | W Login | A sign-in | test_lockout.py | met |
| 16 | Forced password change first login / after reset | B permissions.py:11-17; views.py:286-299 | W guards.tsx:15 | A AppViewModel.kt:117 | test_auth.py | met |
| 17 | Web sessions expire; Android persists | B settings base.py:154-156 (8 h idle); JWT 30 min / 60 d | — | A TokenStore | test_auth.py | met |
| 18 | One active device; new phone signs out old after sync | B accounts/services.py:64-83 (refuses until old is clean) | — | A AppViewModel heartbeat | test_devices.py | built differently (refuse, not wait), API ✓ |
| 19 | Ops/Admin force "sign out all devices" with warning | B accounts/views.py:303 | **Admin only** (W Users.tsx:86) | A ui/ops/Booking.kt:270-271 | test_devices.py | partly (P-08), API ✓ |
| 20 | Config audit log (forms, PDF, lists, webhooks, keys, users, roles) | B accounts/audit.py:4; 22 call sites (forms, reports, integrations, settings) | W admin/Audit.tsx:38 | — | test_audit.py | met |
| 21 | No app lock; portrait; English | — | — | A AndroidManifest.xml:28 | — | met |

#### A2. Booking model (§3)
| # | Rule | Server | Web | Android | Test | Status |
|---|---|---|---|---|---|---|
| 22 | Booking ID unique, case-insensitive, trimmed, editable | B bookings/models.py:58; services.py:67-80 | W ops Booking edit | A Ops edit | test_lifecycle.py | met, API ✓ |
| 23 | Internal UUID primary key for API | B models.py:12; ext_views.py:67 (`find`: UUID or Booking ID) | — | — | test_apikeys.py | met, API ✓ |
| 24 | Booking ID edit fires `booking.updated` old → new | B services.py:126-138; webhooks.py:126-127 | — | — | test_webhooks.py | met, DB ✓ (`booking_id_change`) |
| 25 | Stages Draft→Assigned→In progress→Submitted→Completed / Cancelled | B stages.py:1-13 | W lib/stages | A stage words | test_lifecycle.py | met |
| 26 | Ops status dropdown | B models.py:15 + master list | W | A | test_master_lists.py | met (not exercised) |
| 27 | Only Ops/Admin create/edit/reschedule/cancel/assign | B views.py:21-30 | W | A | test_permissions.py | met, API ✓ (expert 403) |
| 28 | Reschedule history (who, why) | B services.py:174-193, RescheduleLog | W ops Booking | A ReasonDialog | test_activity.py | met, API ✓ |
| 29 | Cancel needs a master-list reason | B services.py:197-206 | W | A Booking.kt:264 | test_lifecycle.py | met |
| 30 | Reassign blocked once started unless force-release | B services.py:160-162, 210-220 | W Booking.tsx:813 | A Booking.kt:269 | test_lifecycle.py | met, API ✓ (`ALREADY_STARTED`) |
| 31 | Released draft arriving later flagged as conflict | B submissions.py:295-299 | — | — | test_submissions.py:243-251 | partly: not when the job was reassigned to someone who hadn't started (owner rule; P-25), API ✓ |
| 32 | Delete: Admin only, permanent | B services.py:250-257 | W admin | A Ops drafts | test_lifecycle.py | built differently (Ops drafts allowed); R-04 files left |
| 33 | Type change only before Start; expert's started type wins + alert | B services.py:237-247; submissions.py:150-158 | W Booking.tsx:816 | A TypeDialog | test_submissions.py, test_review_fixes.py | met, API ✓ (`TYPE_LOCKED`, `TYPE_CHANGE_REJECTED`); alert can't be cleared (P-06) |
| 34 | Locked system fields (relabel, never remove) | B forms/services.py:117-120 (`MISSING_SYSTEM_FIELD`) | W builder | — | forms/test_system_forms.py | met |
| 35 | Master lists Admin-managed; lead owner = user picker | B forms/views.py:52,83 (`master_lists.manage`) | W admin/MasterLists | — | test_master_lists.py | met, API ✓ (Ops 403) |
| 36 | Address text only; payout etc. plain fields | booking form fields | — | — | — | met |

#### A3. Form engine (§4)
| # | Rule | Server | Web | Android | Test | Status |
|---|---|---|---|---|---|---|
| 37 | Form kinds booking / start / end / custom (was booking/ops/inspection) | B forms/models.py FormType | W admin/Forms | A FormTree | forms/test_form_types.py | built differently (agreed plan-form-types) |
| 38 | Form → Version → Page → Section → Field, order + visibility | B forms/models.py | W builder | A core/forms/FormTree.kt | forms/test_structure.py | met |
| 39 | Library linked items; in-use can't be deleted, only archived | B forms/library.py:241-243 | W admin/Library | — | forms/test_library.py | met |
| 40 | Promote staging → production (form, library, lists, PDF) | B forms/promote.py:62, 342 | W admin/Promote.tsx | — | forms/test_promote.py | met (file-based, push mode deferred `plan.md` Phase 9 note) |
| 41 | Draft → PDF preview → publish; no prod test mode | B forms/views.py:394 | W FormBuilder.tsx:35 | — | forms/test_publish.py | met |
| 42 | Version frozen at Start; unstarted jobs move to latest | B submissions.py:160-170; sync.py:34 | W | A JobStore | test_sync.py | met |
| 43 | Field key never editable | B forms/models.py:362, library.py:210 | W | — | test_structure.py | met |
| 44 | Options with defect flag + severity | B fieldtypes.py, scoring/service.py:42 | W FieldEditor | A severity tag | test_scoring.py | met |
| 45 | Required, required-if, min/max, regex, cross-field checks | B forms/rules.py:109-160, 188 | W lib/conditions.ts | A core/rules/* | test_rule_vectors.py, SharedVectorsTest | met |
| 46 | Input types incl. GPS, signature, user picker, master list | B forms/fieldtypes.py:239 | W | A ui/expert/Fields.kt | forms/test_answers.py | met |
| 47 | Conditions across forms of the same booking | B submissions.py:206-207 (context) | W | A | test_rule_vectors.py | met |
| 48 | System-filled (Key Checks, suggested ratings) read-only, Ops override | B scoring/service.py:87,128 | W Booking.tsx:666 | A Parts.kt:661 | scoring/test_engine.py | met |
| 49 | Scan switch on short text (android-req) | B config `scan` | W FieldEditor.tsx:85 | A ui/expert/Fields.kt:187-200 | — | met |

#### A4. Inspection flow, media (§5, android-req Offline/Camera)
| # | Rule | Server | Web | Android | Test | Status |
|---|---|---|---|---|---|---|
| 50 | Forced minimum app version: can finish, can't start | B submissions.py:136-137 (`APP_TOO_OLD` 426) | — | A ui/expert/MyJobs.kt:171,295 | test_submissions.py:149 | met (not testable locally: `MIN_APP_VERSION=0`) |
| 51 | Pushes: assigned, rescheduled, cancelled/reassigned away, details changed; each triggers sync | B notify/handlers.py:86-121 | — | A Push.kt:85-95 | notify/test_notify.py | met, API ✓ (expert20 bell rows) |
| 52 | Check-in: GPS + server time + selfie; in progress only after check-in | B submissions.py:161-165 | W expert/Job | A Wizard check-in | test_submissions.py | met, API ✓ (selfie required); check-in not stored until submit (Low) |
| 53 | Wizard with review; submit blocked until required filled | B submissions.py:261 (`_clean_all`) | W expert/Job.tsx:162-163 | A Wizard.kt:143 | InspectionFlowTest | met, API ✓ (INVALID_ANSWERS) |
| 54 | Payment = ordinary wrap-up fields; filter by answer | B bookings/answers_filter.py:68 | W ops/Bookings.tsx:26 | A ui/ops/Filters.kt:97 | test_answers_filter.py | met |
| 55 | In-app camera stamp; gallery **not** stamped | — | — | A core/media/Media.kt:66-98; Wizard.kt:164 | — | partly (P-10) |
| 56 | Camera-only fields hide Gallery | B field config | W | A Fields.kt:377 | — | met |
| 57 | ~2048 px / ~500 KB + preview; video 60 s 720p | B media/tasks.py:51-55 (shrink + 480 px preview) | W client resize | A Media.kt:27,82-85 (≤700 KB); Tools.kt:172,227 | media/test_upload.py | met (≈); gallery videos not limited |
| 58 | Upload direct to R2, chunked 8 MB, resumable, checksum | B media/services.py:151-232, 347-375; tasks.py:38-48 | W lib/uploader.ts | A core/draft/Outbox.kt:229-241 | test_upload.py, OutboxTest | met, API ✓ |
| 59 | Unuploaded files never cleared; warn <2 GB; block Start <500 MB | — | — | A ui/expert/Storage.kt:59-73; MyJobs.kt:172,294 | MyJobsTest | met |
| 60 | Key Checks any/all/count | B scoring/keychecks.py | W | A Ops review | bookings/test_key_checks.py | met |
| 61 | Rating launch rules (start 5, −0.25/−1/−3, min 1, overall words, Critical caps Average) | B scoring/service.py | — | — | scoring/test_engine.py | met, API ✓ (J3 numbers) |
| 62 | Experts never see ratings | B submissions.py:109-111; serializer hides scores | W | A | test_submission_visibility.py | met, API ✓; activity leak (Low) |
| 63 | Recalc keeps Ops overrides | B scoring/service.py:87,128 | — | — | test_scoring.py | met, API ✓ |

#### A5. Offline and sync (§6)
| # | Rule | Server | Web | Android | Test | Status |
|---|---|---|---|---|---|---|
| 64 | Drafts on phone only; answers saved instantly | — | W localStorage | A core/draft/Draft.kt | InspectionFlowTest | met |
| 65 | Submit → Submitted "uploading x/y" → Completed when media verified → PDF → webhooks | B submissions.py:233-272; media/services.py:413-435 | W | A Uploads | test_submissions.py, test_upload.py | met, API ✓; no `booking.updated` for completion (P-03) |
| 66 | After submit only Ops/Admin/API edit | B views.py:262-284 (`submissions.edit`) | W | A | test_access.py | met, API ✓ (expert 403) |
| 67 | Concurrent web edits stopped; retry applies only changed fields | B services.py:105-110; submissions.py:344-347 | W lib/saveDirty.ts, ui/StaleDialog | A Ops "someone else saved" | test_lifecycle.py | met, API ✓ (409 with who/keys) |
| 68 | Ops changes while expert offline → push + banner old→new | B activity.py:24-62 (`since`) | — | A MyJobs.kt:141,240 | test_sync.py | met |
| 69 | Cancelled with draft → draft still syncs and is kept | B submissions.py:277-278; media/services.py:155-162 | — | A | test_submissions.py:235 | met |
| 70 | Reassigned with draft → stays "Reassigned – submit or discard"; conflict rules | B submissions.py:279-293 | — | A MyJobs.kt:98-101,269 | test_submissions.py:205-230 | built differently (no conflict when new expert hadn't started), API ✓ |
| 71 | Logout blocked while unsynced | — | **not blocked** (W ui/TopBar.tsx:122) | A AppViewModel.kt:210-218 | none | partly (Low) |
| 72 | Admin disabling account with unsynced data sees warning | B Device.unsynced exists | W Users.tsx:132 (generic) | — | — | partly (Low) |
| 73 | Server-corrected time; "unverified" if no sync that day | — | — | A JobStore.kt:62; InspectionModel.kt:53 (not sent) | — | partly (P-07) |

#### A6. PDF reports (§7)
| # | Rule | Server | Web | Android | Test | Status |
|---|---|---|---|---|---|---|
| 74 | Block designer, one template per form, draft→preview→publish | B reports/views.py (Drafts, Publish, Preview) | W admin/PdfDesigner.tsx:88 | — | reports/test_reports.py, web reportDesigner.test | met |
| 75 | Labels in template; values only from app | B reports/context.py | W | — | test_reports.py | met |
| 76 | Block-level show-if; rows print when empty; missing fields blank | B reports/render.py | W | — | test_reports.py | met (by tests; not re-run) |
| 77 | Publishing a form warns about fields the PDF doesn't use | B forms/views.py:404,485; reports/service.py:169 | W publish dialog | — | forms/test_report_support.py | met |
| 78 | Branding, page numbers, footer time + revision, filename pattern | B reports/render.py | W | — | test_reports.py | met (J1 filename `REVIEW-J1BPDI.pdf`) |
| 79 | Verify QR → summary only | B reports/views.py:225 | W pages/Public.tsx:15 | — | test_media_links.py | met, API ✓ (booking ID, car, type, date, rating, revision) |
| 80 | Automatic once media complete; **Regenerate button** after edits | B reports/handlers.py | W | A Parts.kt:714-763 | test_reports.py | built differently (always automatic, P-04) |
| 81 | Only latest PDF kept; one render at a time; memory limit; timeout | B reports/tasks.py:20-21,72-122; compose `pdf-worker -c 1 mem_limit 6g` | — | — | test_reports.py | met |
| 82 | Access Ops + Admin + webhook link | B `reports.view` | W | A | API ✓ (expert 403) | met |

#### A7. Integrations (§8)
| # | Rule | Server | Web | Android | Test | Status |
|---|---|---|---|---|---|---|
| 83 | One integration = one event; Duplicate | B integrations/models.py; webhooks.py:28-30 | W admin/Integrations.tsx | — | integrations/test_designer.py | met |
| 84 | Events incl. stage changes, conflict, stuck-upload | B webhooks.py:28-38 | — | — | test_webhooks.py | **partly**: stuck never fires (P-01), completion missing (P-03), assign doubled (P-02) |
| 85 | API writes fire webhooks incl. bulk | B ext_views.py:106-160 → services | — | — | test_apikeys.py | met, DB ✓ |
| 86 | Visual request editor; values only in path; standard/custom body | B integrations/values.py; webhooks.py:272-312 | W integrations/IntegrationEditor.tsx | — | test_designer.py | met |
| 87 | Preview never sends | B integrations/views.py:282 | W IntegrationEditor.tsx:18 | — | test_designer.py | met |
| 88 | No HMAC; token header; retries with backoff; log; resend; test with `X-Vayu-Test` | B settings base.py:125; webhooks.py:301; tasks.py:21; views.py:326 | W | — | test_webhooks.py | met |
| 89 | PDF links 7 days; ZIP "Preparing x%" cached 7 days | B settings base.py:111,128; media/zips.py:96 | W Public.tsx:73 | — | test_media_links.py | met (R-09 token never expires) |
| 90 | API keys scoped to forms and fields; delete off by default | B integrations/views.py:345-368; ext_views.py:139-147 | W admin/ApiKeys.tsx:23 | — | test_apikeys.py | met, API ✓ |
| 91 | Full CRUD, field keys, bulk, lookup by UUID or Booking ID | B ext_views.py | — | — | test_apikeys.py | partly (no assign/cancel/reschedule, Medium) |
| 92 | Swagger docs; no rate limiting | B integrations/views.py:447-452 (Admin only) | — | — | — | partly (Low) |

#### A8. Ops web, timing, notifications, stack (§9, §10, android-req Notifications)
| # | Rule | Server | Web | Android | Test | Status |
|---|---|---|---|---|---|---|
| 93 | Booking actions: create, assign, reschedule, cancel, force-release, force sign-out, submission edit, media add/replace/delete, ZIP, overrides, PDF | B (above) | W ops/Booking.tsx:238-816 (no force sign-out) | A ui/ops/Booking.kt:260-290, Parts.kt:462,661 | web ops tests; OpsFlowTest | partly (web sign-out, P-08) |
| 94 | Today / date-range with stage + Ops status; filters city/expert/type/stage | B views.py:72-131 | W ops/Today, Bookings | A ui/ops/Filters.kt | test_search_dashboards.py | met |
| 95 | Problem queue: stuck, conflicts, rejected type, unverified payments, pay-later, not regenerated, unverified times, late, too quick | B views.py:84-102; media/views.py:121; reports Problems | W lib/problems.ts | A ui/ops/Lists.kt | — | partly: 4 items dropped by decision (`plan.md:644`), type alerts never clear (P-06) |
| 96 | Global search: Booking ID, name, phone, chassis, car | B views.py:117-126; submissions.py:381-402 | W | A | test_search_dashboards.py | met |
| 97 | Dashboards by period × type/city/expert/lead owner; CSV | B dashboards.py:22,83,172 | W ops/Dashboards.tsx:190 | A ui/ops/Dashboard.kt:133-139 | test_search_dashboards.py | met |
| 98 | Timing settings (Admin edits, Ops view, audited); late / too quick flags; Mark reviewed | B core/app_settings.py; core/views.py:46; timing.py:26-49; services.py:224-233 | W admin/Settings.tsx:13; ops/Booking.tsx:123 | A | test_timing.py | met, API ✓ (Ops GET 200, PUT 403; expert 403) |
| 99 | Expert reminder 60 min before; photos not sent 2 h | — | — | A core/alerts/Alerts.kt:15,18; Push.kt:120-162 | AlertsTest | met (WorkManager, not device-checked) |
| 100 | Ops pushes: problems, submitted, completed, started, late start (30 min), new bookings; mute except problems | B notify/handlers.py:9-18,128-144; tasks.py:33-58 | — | A Profile notifications | test_notify.py | partly: late uses 15 min grace; new bookings API-only (open question); stuck never fires (P-01) |
| 101 | Error tracking app, web, server | B settings base.py:174-178, prod.py:15-16 | **none** (R-36) | A Sentry (`f184063`) | test_prod_settings.py | partly (known) |
| 102 | APK from a logged-in web download page; in-app updater checks same | B notify/views.py:73-105; publish_apk | **none** (P-11) | A core/update/Update.kt:20-30, UpdateScreen.kt:100 | test_notify.py | partly |
| 103 | Media retention: keep everything | B media/tasks.py:72-108 (configurable purge) | W admin/Settings | — | reports/test_media_links.py | built differently (scope creep, P-05) |
| 104 | Non-functional: PDF ≤2 min/150 photos; API p95 <500 ms | B bench_pdf | — | — | docs/benchmarks.md | partly: laptop 16 s; staging runs "to do" |

---

### B. Plan status vs git (adds to R-08; only what R-08 misses)
| Plan | Status line says | Reality (git / code) | Half-built / open |
|---|---|---|---|
| plan.md | rev 2, Phases 1–16 | Phases 1–12 built (`plan.md` amendments), Android replaced by plan-android | §87 "Open Questions: none blocking" but plan-android has one open; F13 payment row and §439/§499 still describe QR / slots / Ops verify (replaced by "payments are forms") |
| plan-android | not started (R-08) | Phases 13–17 built (`08f5d6d`, `5b3d00a`, `f184063`…) | Open question "New bookings" push (line 18) unanswered; lead words on Android pending (R-15); `docs/android-ops-report-auto.md` says "(to do)" but built |
| plan-form-types | not started (R-08) | built `975e815` | — |
| plan-library | not started (R-08) | built `7bb197b` | — |
| plan-profile | not started (R-08) | built `c82f3be` | Android profile picture not mentioned |
| plan-integrations | not committed (R-08) | committed `839f822` | — |
| plan-leads-bookings-words | not built (R-08) | web + server `ee15cf9`; Android not built | Android half (R-15) |
| plan-timing | not committed (R-08) | `73be9c6` | — |
| plan-reports | "No code written yet" (R-08) | Phases 1–6 built (`a4a9a32`, `aa34e84`, `0980b6a`…) | §12 five owner questions still open (battery/generator fields, problem levels, extra key-check slots, missing documents as issues, tyre layout); staging PDF benchmark "to do" |
| plan-quality | finalized, not started | true: no Q-item commit after `c5f90bc` | all of Q1–Q7 open; its numbers measured at `891ec08` are stale |
| **Not in any plan (scope creep)** | — | media retention (`0daa0e4`), report download/share logging, Ops finish without missing files (`175f06b`), release site (`docs/release-site/`, untracked), `setup_platform`/`seed_test_data` (R-07) | — |

**Launch blockers (product view):** R-01 CI red/not running · R-07 setup not in git · P-01 stuck alerts never fire · P-11 no APK download page · P-27 no deploy runbook · R-29 hosting for web + verify domain, backups · Firebase server credential in prod · staging PDF and load benchmarks (`docs/benchmarks.md` "to do") · real R2 CORS browser check (`benchmarks.md` §3) · owner answers: plan-reports §12 (5), plan-android open question, P-04 (customer re-notification) · R-15 Android wording.

### C. Product metrics: what stored data can answer
| Question | How today | Answerable? |
|---|---|---|
| Time per inspection | `Booking.duration_minutes` (server Start→Submit), `Inspection.client_started_at/submitted_at` | yes |
| Inspections per expert per day | `Inspection(expert, submitted_at)`; Dashboard per expert (`dashboards.py:83`) | yes |
| Late starts / too quick | `Booking.late_minutes`, `duration_minutes` vs settings (`timing.py:45-49`) | yes |
| Upload time (submit → completed) | `BookingActivity` stage rows (`submitted`, `completed` timestamps) | yes (by query) |
| Upload failures and retries | `MediaAsset.status="failed"` is reset to `pending` on retry (`media/services.py:186-191`) | **no** (history lost) |
| Stuck uploads over time | `stuck_alerted` flag, but the flagging never runs (P-01) | **no** |
| PDF failures | `Report.status/error` = last state only; detail in logs | current only |
| PDF render time | `render_started_at` cleared at the end; `generated_at` only | **no** |
| How often Ops edit a submission | `BookingActivity kind="inspection_edited"` with actor | yes (lost if booking deleted) |
| Rating overrides / Key Check changes | `ratings_changed`, `key_checks_changed` activity rows | yes |
| Conflicts, force-releases | activity rows; `AuditLog booking.force_release` | yes |
| Webhook failure rate | `Delivery.status, attempts, error` | yes |
| Push delivered | `push` task returns a count; nothing stored | **no** |
| App version in the field / crash rate | `X-App-Version` only read at start, not stored; crashes in Android Sentry only; web none | **no** (crash: Sentry for app only) |
| Reports downloaded / shared to customers | `report_downloaded`, `report_shared` activity rows | yes |

### D. Documentation check (claims followed against code)
| Doc | Claims checked | Wrong / stale |
|---|---|---|
| README.md | layout, local stack command, test commands, secrets, rule vectors | Android "from Phase 13" / no Android steps (R-27) |
| docs/local.md | 10: users/password (API ✓), roles, DEMO data, walk-through steps 1–10, verify URL, webhooks http allowed (settings local.py ✓) | steps 3/5 "Job board", "Ratings tab", "Out of date → Regenerate" (no regenerate); DEMO-1 "not assigned" differs on this DB (state, not doc) |
| docs/integrations.md | 12: events (9 ✓), body, path-only values, retries (base.py:125 ✓), redirects off (webhooks.py:338 ✓), check on save (views.py:119 ✓), scope/OUT_OF_SCOPE (API ✓), DELETE off (API ✓), bulk `items` (API ✓), revoke instant (API ✓), Swagger Admin only (✓) | "updates include stage changes" (P-03), stuck-upload alert (P-01), dedupe by `X-Vayu-Delivery` (P-02) |
| docs/accounts-setup.md | Sentry required in prod (prod.py:15 ✓), R2 CORS + ETag, keystore offline, buckets | Firebase/keystore "Phase 15" (Phase 17 per plan-android) |
| docs/benchmarks.md | bench command exists (`reports/management/commands/bench_pdf.py` ✓), locust file | staging rows "to do" (true; launch item) |
| docs/r2-check.md | part size 8 MB (base.py:109 ✓), endpoints exist (✓) | step 4 "expect verified" → actually `uploaded`, verified async |
| docs/android-ops-report-auto.md | regenerate gone (✓ 404), `updating` (✓ J1 report body), `/download` (✓) | header "(to do)": done in `5b3d00a` |
| docs/android-lead-words.md | expert web "My leads" (Layout.tsx:17 ✓) | Android still "jobs" (R-15) |
| docs/plan-*.md | status lines (R-08) | see table B |
| docs/review-strategy.md | §1 entry checklist | not true at baseline (tree dirty, CI red) |

---

### E. Journeys
#### J1 Booking → assign → notice → inspection → upload → submit → scores → PDF → webhook → customer link (driven via API with REVIEW-J1)
| Step | Function | Layer | Result | Evidence |
|---|---|---|---|---|
| Ops creates booking (ID with spaces) | `BookingViewSet.create` → `services.create` (services.py:89) | B / W ops Bookings | pass | 201, ID stored trimmed; duplicate lower-case → `DUPLICATE_BOOKING_ID` |
| Webhook `booking.created` | `webhooks.on_event` | B | pass | Delivery "ERP: new bookings" |
| Assign to expert | `services.assign` (:155) | B / W Booking.tsx:816 / A Booking.kt | **fail (P-02)** | 2 `booking.updated` deliveries |
| Expert gets notice | `notify.handlers.on_event` → `to_user` | B / A Push.kt | pass | expert20 bell "New lead: REVIEW-J1" |
| Reschedule, type change, ID edit while assigned | `services.reschedule/change_type/edit` | B | pass | history row; bells "moved", "details changed" (raw keys, Low) |
| Stale edit | `services.edit` row_version | B / W StaleDialog | pass | 409 with `changed_by`, `changed_keys` |
| Selfie upload | `media.initiate` → S3 part PUT → `complete` → `verify_asset` | B / A Outbox.kt:229-241 / W uploader | pass | `uploaded` then `verified` |
| Start without selfie | `submissions.start` → `_clean_all` | B | pass | `INVALID_ANSWERS selfie: required` |
| Start offline with old type | `submissions.start` :150-158 | B / A | pass | stage in_progress, type pdi, alert `TYPE_CHANGE_REJECTED`; replay same uuid → same result |
| Ops tries reassign / type change after start | `assign`, `change_type` | B | pass | 409 `ALREADY_STARTED`, `TYPE_LOCKED` |
| Submit (302 answers, 25 photo refs pending) | `submissions.submit` :233 | B / A Wizard / W Job.tsx | pass | stage `submitted`; replay → same; expert PATCH after → 403 |
| Upload remaining files → Completed | `media.complete` → `verify_asset` → `check_completion` | B | pass | stage `completed` |
| `booking.updated` for completion | `check_completion` | B | **fail (P-03)** | no delivery |
| Scores and Key Checks | `scoring.recompute` | B | pass | 5 categories 5, overall excellent, 9 Key Checks |
| PDF rendered | `reports.tasks.render_report` | B | pass | rev 1, `REVIEW-J1BPDI.pdf` |
| `inspection.submitted`, `pdf.ready` webhooks | `webhooks.on_event` | B | pass | deliveries to WhatsApp integrations |
| Customer opens link | `reports.views.Verify` | B / W Public.tsx:15 | pass | summary only; bad token 404 |
| Ops pushes (started, submitted, completed, problem) | `to_ops` | B | pass | rows for ops, ops2, newuser |

#### J2 Trouble: offline, killed, moved (REVIEW-J2 via API + code)
| Step | Function | Result | Evidence |
|---|---|---|---|
| Expert19 starts | `submissions.start` | pass | in_progress |
| Ops edits the draft inspection | `edit_inspection` | pass (refused by validation) | 400 required fields: Ops can't change a draft |
| Ops overrides ratings on the draft | `set_overrides` | **fail (Low)** | 200, `status: draft`, engine=1 kept after submit |
| Force-release, reassign to expert20 | `force_release`, `assign` | pass | stage assigned, `released_draft_expected` true; expert19 bell "moved to another expert"; expert19 list still has it |
| Old expert submits | `_advance` :279-293 | pass per owner rule; **docs/UI wrong (P-25)** | stage submitted, back to expert19, `withdrawn_expert=24`, `conflict=""`, no alert |
| App killed / phone restart / no network | Android Outbox + WorkManager | unclear | not device-tested (R-review: no phone) |
| Cancelled with draft | `_advance` :277 | pass (test) | test_submissions.py:235 |

#### J3 Ops review (REVIEW-J1B via API)
| Step | Function | Result | Evidence |
|---|---|---|---|
| Edit answer to a Major defect | `edit_inspection` → `scoring.recompute` | pass | Engine 5→4, overall 4.8 Excellent |
| Override Engine to 2 | `set_overrides` | pass | value 2, overridden, overall Good |
| Edit Critical + tyre bad | `edit_inspection` | pass | override kept; Critical caps Average (avg 3.6) |
| Stale edit | row_version | pass | 409 `STALE_INSPECTION` with keys |
| PDF updates | `reports.handlers` | pass / **side effect (P-04)** | rev 3, verify shows "average"; 3 `pdf.ready` deliveries |
| Replace a photo, finish without missing file | `media.attach`, `finish_without_missing` | pass (code + tests) | media/test_finish.py; not driven here |

#### J4 Admin form change (code + tests, not driven)
| Step | Function | Result | Evidence |
|---|---|---|---|
| Draft → validate → publish with PDF/integration warnings | `PublishVersion` (forms/views.py:394-404) | pass | forms/test_publish.py, test_report_support.py |
| Library edit + push | `library_push` | pass | forms/test_library_push.py |
| Expert mid-job keeps old version | `Inspection.form_version` pinned at start (submissions.py:167) | pass | REVIEW-J1 pinned v8 / start 2 / end 3 |
| Unstarted job gets the new version | `sync.payload` (sync.py:34) | pass | test_sync.py |
| Late delivery after Admin switched the form off | `submit` `is_active=True` filter | fail (known R-35) | — |

#### J5 Sign-in and devices (driven via API with expert19)
| Step | Function | Result | Evidence |
|---|---|---|---|
| Phone A signs in, reports 1 draft | `register_device_and_tokens`, `HeartbeatView` | pass | 200 |
| Phone B signs in | `register_device_and_tokens` | pass | 409 `DEVICE_HAS_UNSYNCED_DATA` (drafts 1, files 3) |
| A clean → B signs in; A dead | `revoke_devices`, `DeviceJWTAuthentication` | pass | A access + refresh → `DEVICE_REVOKED` |
| Ops signs out B | `sign_out_devices` | pass (API) / **fail on web (P-08)** | 200 + warning; web has no button for Ops |
| Ops signs out Admin / resets password | `_admin_only`, `users.manage` | pass | `ADMIN_ONLY`; 403 |
| Admin on the app | `LoginView` | pass | `ADMIN_USE_WEB` |
| Sign-out clears phone data | `AppViewModel.signOut/revoked` | pass (code) | forgets copies, notices, tokens; drafts kept; web R-06 |
| Password change signs out other phones | `ChangePasswordView` (:177) | pass (code + test) | test_auth.py |

#### J6 Notices (API + code; no Firebase)
| Step | Function | Result | Evidence |
|---|---|---|---|
| Expert: assigned / moved / changed / reassigned away | `handlers._updated` | pass | bells for expert19/expert20 |
| Ops: started / submitted / completed / type rejected | `to_ops` | pass | rows for 3 Ops users |
| Ops: stuck upload | `flag_stuck_uploads` | **fail (P-01)** | never scheduled |
| Ops: late start | `notify.tasks.late_starts` every 5 min | pass (15 min grace, Note) | base.py:133 |
| Repeat floors (24 h / 10 min) | `to_ops(quiet=)` | pass | handlers.py:25-26,138-143 |
| Push carries only id; wrong phone sees nothing | `notify.tasks.push`; A Push.kt:85-92 | pass | code |
| Expert reminder 60 min / photos 2 h | A Alerts.kt, Push.kt Reminders | unclear | code only, no device |

#### J7 Integrations and API (API key REVIEW-key, revoked after)
| Step | Function | Result | Evidence |
|---|---|---|---|
| Create key with field scope | `ApiKeyList.post` (views.py:386) | pass | `allow_delete: false` default |
| Read by Booking ID, only scoped fields | `ext_views.find`, `booking_body` | pass | `data` has 3 fields |
| Write out-of-scope field | `need_keys` | pass | `OUT_OF_SCOPE` |
| Delete without grant | `BookingDetail.delete` | pass | `DELETE_NOT_ALLOWED` |
| Reassign / cancel via API | — | **fail (Medium)** | no endpoint; `ACTION_ONLY` |
| Revoke → refused at once | `ApiKeyAuthentication` | pass | "This API key was revoked." |
| Webhook delivery, retry, resend | `tasks.deliver`, `retry_due`, `Resend` | pass (code/tests) | deliveries "retrying" (no receiver) |

#### J8 Fresh setup and self-update (code only)
| Step | Function | Result | Evidence |
|---|---|---|---|
| New server: migrate, `setup_platform --users` | `setup_platform.py` (never deletes, users left alone) | unclear | not run (shared DB); uncommitted (R-07); no runbook (P-27) |
| Stuck/late/retry schedules start | beat schedule | **fail (P-01)** | stuck flag not scheduled |
| Publish APK | `publish_apk` (version code must rise, SHA-256) | pass (code) | — |
| Expert downloads the app from the web | `AppDownloadView` | **fail (P-11)** | no web link |
| App self-updates, checks SHA-256, min version blocks Start | A Update.kt, UpdateScreen.kt:100, MyJobs.kt:171 | unclear | not on a device |

