# Review report: backend, web and Android (2026-11-24) — FIRST PASS

> **Superseded by [`review-report-2026-11-25.md`](review-report-2026-11-25.md)** (full six-phase review).
> Kept because the full report refers to the findings R-01 … R-38 below.

Method: `docs/review-strategy.md`. Hats: software architect / senior engineer (backend, structure,
data), security expert, senior front-end / UI-UX engineer (web), senior Android engineer, DevOps
(build, CI, release), technical product manager (requirements, plans, cost).

## Baseline
- **Code reviewed:** the latest code on this machine on 2026-11-24 at 23:40 IST: commit `ab75050`
  (`main`, newest on any branch) **plus all uncommitted work** (setup / seed commands, report renderer
  change, release site, Clappia read-out). Frozen as git ref **`refs/review/baseline` = `ba4b7df`**
  (`git show refs/review/baseline:<path>` shows any file exactly as reviewed). Excluded: `.claude/`,
  `backups/`, Roborazzi `*_actual.png` / `*_compare.png`.
- **Not reviewed:** branch `claude/ops-filters-4c5084` beyond what is merged; anything committed later.
- **Devices / browsers:** macOS, Chromium (Playwright), Robolectric for Android. **No real phone or
  emulator was used**: aspects that need a device (25, part of 16) are marked *Not checked*.
- **How:** tools run on the baseline (numbers below), every URL scanned for its permission class,
  code read along the journeys in §5, the local web app probed in a browser, findings cross-checked
  between hats (a finding that could not be reproduced or pointed to in code was dropped).

## 1. Numbers (phase 0)

| Check | Result |
|---|---|
| Code size (non-test) | backend 17.8 k lines (core 4.9 k, forms 3.7 k, reports 2.7 k), web 10.1 k, Android 8.8 k |
| Backend `ruff` | clean |
| Backend `mypy apps vayu` | **22 errors, all in uncommitted setup code** (`apps/core/setup/*`, `freeze_forms.py`, `test_setup_forms.py`); committed code clean |
| Backend migrations check | in sync |
| Backend `pip-audit` (runtime deps) | no known vulnerabilities |
| Backend tests (pytest + coverage) | **2991 passed** (7 first-run errors were another session holding the `test_vayu` database; they pass on re-run), **coverage 94 %**, run time **29 min** |
| OpenAPI | `openapi.yaml` in sync with code, but generation reports **345 errors (68 unique)** and 244 warnings |
| Endpoints | 136 routes: 86 single-permission, 33 per-action (viewsets), 5 any-of, 4 API-key, 5 public (`AllowAny`, all throttled), 1 refresh |
| Backend logging | **12** logger calls in all of `apps/` |
| Web `tsc --noEmit` | clean (`strict` + `noUncheckedIndexedAccess`), 0 `any`, 2 `as unknown as` |
| Web Vitest | **1763 passed** (26 files, 11.7 s) |
| Web Playwright (e2e) | **55 passed, 1 failed** (2.4 min) |
| Web `npm audit --omit=dev` | 2 moderate (`react-router` 6.30: open redirect via backslash; SSR hydration item not used) |
| Web bundle (gzip) | main 85 KB, PDF viewer chunk 107 KB (lazy), largest page 27 KB; **source maps published** |
| Web accessibility probe (10 Admin / Ops pages) | 0 unnamed buttons / links, 0 unlabeled inputs, 0 images without alt, one `h1` per page; page title is always "Vayu" |
| Android unit tests (Robolectric) | 111 tests; **`OpsFlowTest.todayStatusChipsNarrowTheDay` failed in 1 of 2 runs** (flaky) |
| Android Roborazzi screenshots | pass |
| Android Kover coverage | lines 87.2 %, branches 64.4 %, methods 88.0 % |
| Android lint (not in CI) | 5 errors (`ProduceStateDoesNotAssignValue`, false positives here), 48 outdated-dependency warnings, 8 other warnings |
| Android release APK | 6.5 MB, minified; only the (public) Firebase API key inside, no other secrets |
| CI (GitHub Actions) | **only 2 green runs in the last 100**; dozens of runs never started (billing); newest run on `9318157`: android **failed**, e2e **failed**, web and docker passed |
| TODO / FIXME | 0 in app code; 2 `ponytail:` notes |


## 2. Scorecard
Good = nothing above Low · OK = Medium findings only · Weak = a High finding · Bad = a Critical finding
· — = does not apply · *Not checked* = reason given.

| # | Aspect | Backend | Web | Android |
|---|---|---|---|---|
| 1 | Requirements fit | Good | Good | OK (R-15) |
| 2 | Product and delivery | **Weak** (R-01, R-07) | **Weak** (R-01) | **Weak** (R-01) |
| 3 | Product metrics | OK | — | OK |
| 4 | Long-term maintenance | Good | Good | OK (R-11) |
| 5 | Setup and form content | **Weak** (R-07) | — | — |
| 6 | Structure and modularity | Good | Good | OK (R-11, R-25) |
| 7 | Reuse and duplication | Good | Good | Good |
| 8 | Clean code | Good | Good | Good |
| 9 | Design principles | OK (field-type `if` chains, plan-quality Q3) | OK | OK |
| 10 | Comments and in-code docs | Good | Good | Good |
| 11 | Types and static checks | Good | Good | OK (R-11) |
| 12 | Dependencies | Good | Good (R-20 Low) | Good (R-26 Low) |
| 13 | Correctness and edge cases | Good (R-35 Low) | Good | Good |
| 14 | Error handling | Good | OK (R-13) | Good (R-33 Low) |
| 15 | Data integrity and migrations | **Weak** (R-04) | — | Good |
| 16 | Offline and sync | — | Good (e2e J3c/J3d) | *Not checked on a device*; unit tests pass |
| 17 | Notifications and alerts | Good | Good | Good (R-33 Low) |
| 18 | API contracts | OK (R-10) | Good | OK (R-11) |
| 19 | Testing | Good (94 %, all pass; 29-min run) | OK (R-02) | OK (R-03) |
| 20 | Security | Good | Good (R-20, R-21 Low) | Good (R-19 Low) |
| 21 | Privacy and data retention | **Weak** (R-04, R-05) | OK (R-06) | Good |
| 22 | Performance | OK (R-17) | Good | OK (R-12) |
| 23 | Running cost | OK (R-18) | — | Good |
| 24 | Web UX and accessibility | — | OK (R-13, R-14) | — |
| 25 | Android UX and platform | — | — | *Not checked*: no device in this round |
| 26 | Design and wording consistency | Good | Good | OK (R-15) |
| 27 | Logging and observability | OK (R-16) | OK (R-36) | Good |
| 28 | External services | OK (R-05 counted under 21) | — | Good (R-32 Note) |
| 29 | Build, CI and dev setup | **Weak** (R-01) | **Weak** (R-01) | **Weak** (R-01) |
| 30 | Documentation | OK (R-08, R-10) | OK (R-08) | OK (R-27) |
| 31 | Deployment readiness | *Before launch* (R-29 Note) | *Before launch* | *Before launch* |

**No Critical findings. 4 High, 15 Medium, 14 Low, 4 Notes.**

## 3. Findings (most severe first)

### High

**R-01 · 29 Build, CI · all layers · High**
- **What:** `main` is not being checked by CI. Only 2 of the last 100 runs passed; most never started
  ("recent account payments have failed or your spending limit needs to be increased"), e.g. run
  45443406421. The newest run (on `9318157`) has the android and e2e jobs **failing**.
- **Evidence:** `gh run list`; `gh run view 45443406421`; R-02 and R-03 reproduce the failures locally.
- **Why:** about 40 commits (notifications, push security fixes, offline delivery, wording, payments)
  reached `main` without the gates the plans rely on (coverage gates, e2e, Android screenshots). A
  broken build or a security regression would not be noticed.
- **Fix:** fix billing, re-run CI on `main`, then fix R-02 / R-03 until all five jobs are green; add a
  branch rule so `main` only moves on green. **S**

**R-04 · 15 Data integrity, 21 Privacy, 23 Cost · Backend · High**
- **What:** deleting a booking deletes its database rows but **never its files**: original photos and
  videos, previews, print copies, the PDF and ZIPs stay in R2 for ever. The retention job cannot
  clean them later because it looks for `MediaAsset` rows, which the delete cascaded away.
- **Where:** `backend/apps/bookings/services.py:250` (`delete` → `b.delete()`), cascades in
  `apps/media/models.py:16,46`, `apps/reports/models.py:67`; no `pre_delete` / storage call anywhere
  (`grep -rn "post_delete\|pre_delete" apps` is empty).
- **Why:** a customer asks to be removed; Admin deletes the booking; their car photos, RC / document
  photos and the report remain downloadable by anyone holding an old presigned link until it expires,
  and are stored (and paid for) for ever with no record of what they belonged to.
- **Fix:** collect every storage key of the booking (assets, previews, print keys, report, zips)
  before the delete and remove them after commit (same helper the retention job uses). **S**

**R-05 · 21 Privacy, 28 External services · Backend · High**
- **What:** backend Sentry is started with `send_default_pii=False` only
  (`vayu/settings/base.py:174-178`). That flag does not stop the Sentry SDK from sending **request
  bodies** (`max_request_body_size` defaults to "medium") and **local variables of every stack frame**
  (`include_local_variables` defaults to on). Sentry is mandatory in production
  (`settings/prod.py`).
- **Why:** any server error while an expert submits, or Ops edit answers, sends the customer's name,
  phone and answers to Sentry. Android was fixed for exactly this (commit `9635cee`: "crash reports
  carry no text or extras"); the server was not.
- **Fix:** `sentry_sdk.init(..., max_request_body_size="never", include_local_variables=False)`
  plus a `before_send` that drops `request.data`; test that an error event carries no body. **S**

**R-07 · 5 Setup and form content, 2 Delivery · Backend · High**
- **What:** the production setup is **not in git**: `setup_platform`, `seed_test_data`,
  `freeze_forms`, `apps/core/setup/` (2.3 MB: the frozen PDI / Used Car / EV forms and the Clappia
  read-out), their tests, and the `SERVER_KIND` settings are untracked or modified files on one laptop.
  `mypy` reports 22 errors in them, so CI would fail the moment they are committed.
- **Evidence:** `git status`; `mypy apps vayu` output; the plan status in `docs/plan-*.md` doesn't
  mention them.
- **Why:** a lost or wiped laptop loses the only copy of the agreed forms and the setup that puts them
  on a server; nobody else can review or run it.
- **Fix:** fix the 22 type errors, commit on a branch, let CI run (with R-01 fixed). **S**

### Medium

**R-02 · 19 Testing, 24 UX · Web · Medium**: e2e test `builder.spec.ts:156` (system forms renamed)
fails on `main`. The failure screenshot shows a real information loss, not only a stale test: since
`4f923c5` ("Forms list … no keys, tidy headings") the System forms table shows only Name / Live
version / Draft, so after the Admin renames the end form to "Payment and review" nothing on the list
says it is the **end (wrap-up)** form (same for a renamed start form). Show the type as a small muted
label ("Start" / "End" / "Booking") next to the name; the test then passes as written. **S**

**R-03 · 19 Testing · Android · Medium**: `OpsFlowTest.todayStatusChipsNarrowTheDay` failed in one of
two identical runs ("could not find any node … 'Ravi Expert'", `OpsFlowTest.kt:126`), passed in the
other. A flaky test either gets ignored or blocks CI at random. Wait for the list to settle
(`waitUntil`) before clicking. **S**

**R-06 · 21 Privacy · Web · Medium**: signing out on the web clears only the query cache
(`web/src/auth.tsx:19`). Inspection drafts (`localStorage` `vayu:draft:<id>`, `pages/expert/Job.tsx:23`)
and queued photos / videos (IndexedDB, `lib/store.ts`) stay in the browser. On a shared office PC the
next person can open DevTools and read the customer's answers and photos. Android already wipes on
sign-out (`bafd197`). Clear both stores in `wipe()` (after warning when unsent work exists). **S**

**R-08 · 2 Delivery, 30 Docs · all · Medium**: 7 of 9 plan files state the wrong status:
`plan-android` "not started" (built to Phase 17), `plan-form-types` "not started" (built `975e815`),
`plan-library` "not started" (built), `plan-profile` "not started" (built: `/profile`, `c82f3be`),
`plan-integrations` "not committed" (committed `839f822`, and its body still describes the row
builder replaced by the JSON editor), `plan-leads-bookings-words` "not built" (web + server built
`ee15cf9`), `plan-timing` "not committed" (`73be9c6`), `plan-reports` "No code written yet" (designer
built `a4a9a32`). Anyone deciding "what's left" from the docs gets it wrong. One pass to fix the status
lines. **S**

**R-09 · 21 Privacy · Backend · Medium**: the customer's report links (verify page and the photo /
video ZIP links, `apps/reports/media_links.py`) use the report token, which **never expires and can't
be revoked** (`models.py:60` "stable across revisions"). A PDF forwarded to the wrong person gives them
every inspection photo and video for as long as the files are kept. Add "Reset report links" for
Ops / Admin (new token, old links dead) and log ZIP downloads. **S**

**R-10 · 18 API contracts, 30 Docs · Backend · Medium**: `manage.py spectacular` reports 345 errors
(68 unique): many `APIView`s have no serializer, so Swagger shows them with no request / response
shape. API-key users (ERP) can't rely on the docs. Covered by plan-quality Q6; keep it there. **M**

**R-11 · 18 API contracts, 11 Types · Android · Medium**: Ops screens read server JSON by string key
(`JsonObject` 163 uses; `fun JsonObject.s(k) = … ?: ""` in `core/ops/OpsData.kt:62`). A renamed or
missing server field shows as an empty label, never as a failed test or a crash report. Add typed
models (`@Serializable data class`) for the Ops responses, at least booking, inspection, media,
notice, and decode them in the API layer. **M**

**R-12 · 22 Performance · Android · Medium**: photos are decoded on the main thread. In
`ui/ops/Parts.kt:505` and `:521` the `produceState` block calls `mediaBytes(...)` (IO) and then
`thumb(...)` (`BitmapFactory.decodeFile`, `Parts.kt:378`) **on the UI thread**, for every tile in a
list and for the 2000-px viewer. This causes visible stutter on low-end phones (commit `f9a6db4`
claimed "no main-thread disk reads"). Move `thumb` inside `withContext(Dispatchers.IO)` (or
`Default`). **S**

**R-13 · 14 Error handling, 24 UX · Web · Medium**: there is no error boundary anywhere (`grep
componentDidCatch|ErrorBoundary|errorElement` finds nothing). Any render error, or a lazy page chunk
that no longer exists after a deploy (`App.tsx` uses `lazy()` for every page), leaves a blank white
screen with no way back. Add one boundary around the routes with "Something went wrong · Reload"; on
a chunk-load error reload once. **S**

**R-14 · 24 Accessibility · Web · Medium**: search boxes remove the focus outline with nothing in its
place (`styles.css:174 .searchbox input { outline: 0 }`, `:227 .gsearch input { outline: none }`; no
`:focus-within` rule for them, unlike `.vinput:focus-within` at `:629`). Keyboard users can't see that
they are in the search box. Add `.searchbox:focus-within, .gsearch:focus-within { border-color:
var(--primary) }`. **S**

**R-15 · 26 Wording, 1 Requirements · Android · Medium**: the agreed rule (experts read "lead", Ops
"booking", never "job") is built on web and server (`ee15cf9`) but not on Android: "Welcome back. Your
jobs are waiting." (`ui/Screens.kt:105`), bottom bar "Jobs" (`ui/components/Bars.kt:28`),
notification channel "Jobs and updates" (`Push.kt:46`), update screen "start new jobs"
(`UpdateScreen.kt:62`). Known as pending in memory; listed so it is not lost. **S**

**R-16 · 27 Logging · Backend · Medium**: 12 log calls in the whole backend. From the logs you can't
tell what happened to one booking (no lines for start, submit, upload complete, PDF done, webhook
sent); failed sign-ins aren't logged (plan-quality Q4 decided the format, not built). The audit /
activity tables cover config and booking changes, not failures. Build plan-quality Q4. **M**

**R-17 · 22 Performance · Backend · Medium**: the bookings list (Today, Bookings, search) filters on
`stage`, `inspection_date`, `city`, `inspection_type` with no index on any of them
(`apps/bookings/models.py`: only the unique `Lower(booking_id)`), and search is `icontains` on four
columns (`views.py`, `_filtered`). Fine at today's size; at tens of thousands of bookings every list
load is a full table scan. Add indexes on `(stage, inspection_date)`, `city`, `inspection_type`; add
`pg_trgm` GIN indexes when search slows. Measure first with `perf/`. **S**

**R-18 · 21 Retention, 23 Cost · Backend · Medium**: the retention job only purges media of
**completed** bookings (`apps/media/tasks.py:73`, `booking__stage="completed"`). Photos and videos of
cancelled bookings (and of bookings stuck in any other stage) are kept for ever, against the Admin's
setting. Include cancelled bookings (by cancel date). **S**

**R-36 · 27 Observability · Web · Medium**: the web app has no error reporting (no Sentry, no
`window.onerror` / `unhandledrejection` handler; `grep -ri sentry web/` is empty). Backend and Android
report crashes; a broken Ops or Admin page is only known when someone complains. Add Sentry (no PII,
no request bodies) or a small `/api/v1/client-errors` endpoint. **S**

### Low

| ID | Aspect · layer | What | Fix |
|---|---|---|---|
| R-19 | 20 · Android | Sign-in tokens (60-day refresh) in plain `SharedPreferences` (`core/auth/TokenStore.kt:18`). Backup is off and the file is app-private, but a rooted or forensically copied phone yields a working token. | Wrap with an Android Keystore key. |
| R-20 | 12 · Web | `react-router-dom` 6.30.x has a moderate open-redirect advisory (backslash in `<Link>` / `navigate`). The app navigates only to its own paths, so exposure is low. | Update within 6.x. |
| R-21 | 20 · Web | `vite.config.ts:8 sourcemap: true`: the full front-end source is downloadable in production. | Upload maps to Sentry (R-36) and don't publish them. |
| R-22 | 19, 22 · Backend | Only 4 query-count assertions in the suite: an N+1 on a list endpoint would pass every test. | Add `django_assert_max_num_queries` to the 5 main list endpoints. |
| R-23 | 8 · Android, Backend | Dead code: `HomeScreen` placeholder ("Your jobs arrive with Phase 14", `ui/Screens.kt:153`) has no caller; permission `submissions.delete` (`accounts/catalog.py:53`) is used by no endpoint but appears in the Roles screen. | Delete both (or wire the permission). |
| R-24 | 24 · Web | `document.title` is "Vayu" on every page; browser tabs, history and screen-reader page announcements can't tell pages apart. | Set the title from `PageHeader`. |
| R-25 | 4, 6 · Android, Web | Hot spots: `ui/ops/Parts.kt` 941 lines / 18 changes, `ui/ops/Booking.kt` 466, web `pages/ops/Booking.tsx` 825; backend `bookings/submissions.py` is the most-changed file (24). | Split `Parts.kt` by screen when next touched. |
| R-26 | 11, 12, 29 · Android | Android lint is not run in CI (48 outdated dependencies, 5 lint "errors" that are false positives here). | Run `lintDebug` in CI with a baseline file. |
| R-27 | 29, 30 · Android | README has no Android build / test steps; Gradle needs JDK 17 and fails with "Unable to locate a Java Runtime" on a fresh shell here; README still says Android "later". | Add an Android section (`JAVA_HOME`, `./gradlew testDebugUnitTest`). |
| R-28 | 29 · Web | With the local stack running, `npx playwright test` silently reuses the dev servers on 8000 / 5173 and fails at login (401); it only works with `E2E_WEB_PORT` / `E2E_API_PORT`. | Default the e2e ports to free ones (e.g. 5199 / 8099). |
| R-30 | 22 · Backend | Deleting a picture loads and `json.dumps` every PDF template version and shared revision (`reports/views.py:258 _in_use`). | Fine now; index usages if templates grow. |
| R-33 | 17 · Android | Saving the push token swallows errors (`AppViewModel.kt:122`, `Push.kt:81` `runCatching`), with no retry until the next app start: a phone that was offline at sign-in gets no pushes for that session. | Retry through the existing outbox / WorkManager. |
| R-35 | 13, 16 · Backend | An inspection started offline whose start never reached the server can't be submitted if Admin switched the form off meanwhile (`submissions.py` `submit`: `is_active=True` filter → `NOT_STARTED`); the expert's work is stuck on the phone. | Accept any published version of the form for late delivery; alert Ops. |
| R-37 | 30 · all | `docs/plan-integrations.md` contradicts itself (header: JSON editor; body: row builder). | Fold into R-08. |

### Notes
- **R-29 (31, before launch):** `infra/Caddyfile` only proxies the API. Not yet set up: hosting for the
  web app and the verify domain (`verify.carcid.in`), security headers / CSP, database and R2 backups
  with a restore test, monitoring. Belongs to launch prep.
- **R-32 (28):** the Firebase API key in the APK is public by design; check that it is restricted to
  the app's package and SHA-1 in Google Cloud.
- **R-38 (3):** dashboards answer volume, completion rate, average minutes and late / too-quick shares
  (`bookings/dashboards.py`). Not answerable without a database query: upload failure and retry
  rates, PDF render failures, how often Ops edit a submission, webhook failure rate across
  integrations. Add them to the dashboard when someone needs them.
- **R-34 (1):** "Ops cannot change templates" holds by default only: `forms.edit`,
  `pdf_templates.edit`, `master_lists.manage` are grantable to Ops by an Admin. If the rule is
  absolute, make them `grantable=False` like `library.edit`.

## 4. Confirmed strengths (checked, nothing to fix)
- **Permissions:** every one of 136 routes declares a permission; scoped ("own") permissions filter
  querysets for bookings, inspections, media and reports; the role grants in the local database match
  the requirements (Ops: no template, user or permission rights, delete only drafts).
- **Public surface:** 5 public endpoints, all throttled (60/min); report tokens are 192-bit random;
  ZIP links are signed and time-stamped; the verify page shows a summary only.
- **PDF and rich text:** WeasyPrint may fetch only `data:` URLs (no SSRF, `render.py:520`); rich text is
  cleaned with `nh3` on the server and the same tag list in the browser.
- **Webhooks:** SSRF guard on the final URL plus a peer-address check (DNS rebinding); host can't
  contain values; path values URL-encoded; locked headers; CR / LF removed.
- **Wipe guards:** `seed_test_data` refuses unless `VAYU_SERVER_KIND` is local / test **and** the
  server name is typed back; `e2e_reset`, `seed_demo`, `local_bucket` refuse other settings.
- **Android:** backup and device transfer off; FileProvider private; self-update checks SHA-256;
  Admin refused at sign-in; release minified; crash reports without text.
- **Types:** TypeScript strict with zero `any`; mypy clean on committed code; shared rule vectors run
  on all three layers.
- **Push:** sent from a worker after commit, carrying only a notice id.

## 5. Journeys

| ID | Journey | Result | How checked |
|---|---|---|---|
| J1 | Booking → assign → expert inspection → upload → submit → scores → PDF → webhook → customer link | **Pass** on web; Android by unit tests only | e2e J1–J3, J5 pass; code read (`submissions.start/submit`, `media.complete`, `reports`, `webhooks`) |
| J2 | Same with trouble (no network, refresh, app killed, job moved) | **Pass** on web (J3c, J3d, J3f); Android *not on a device* | e2e; code read of `deliver_filter`; R-35 found |
| J3 | Ops review: edit, replace photo, override, regenerate, finish without missing files | **Pass** | e2e J4; code read (`row_version` locks, `media.attach`, `finish_without_missing`) |
| J4 | Admin form change: draft → publish; mid-job expert keeps version | **Fail (test)** | e2e builder suite: 1 failure (R-02); versions stay `published` (no superseded state), pinning confirmed in code |
| J5 | Sign-in and devices | **Pass**, with R-06 | code read (`LoginView`, device refresh check, Admin refused on app); web wipe gap |
| J6 | Notices and pushes | **Pass** in code | `notify` handlers / tasks; repeat floors covered by tests; device not used |
| J7 | Integrations and API | **Pass** | e2e J5 integration; code read of `build_request`, `check_url`, save validation |
| J8 | Fresh setup and app self-update | *Not run* | Setup code read (guards fine, R-07); `setup_platform` not run twice on a copy; self-update read only |

## 6. Fix plan (order)
1. **Today, before more features:** R-01 (CI green again), R-02, R-03, R-07 (commit the setup).
   Everything else is unverified until CI runs.
2. **Privacy batch (≈1 day):** R-05 Sentry scrubbing, R-04 delete files with the booking, R-06 web
   sign-out wipe, R-18 retention for cancelled bookings, R-09 reset report links.
3. **Robustness batch (≈1 day):** R-13 web error boundary, R-36 web error reporting, R-12 Android image
   decode off the main thread, R-33 push-token retry, R-35 late delivery to a switched-off form.
4. **Wording and docs (≈½ day):** R-15 Android "lead", R-08 / R-37 plan statuses, R-27 Android README.
5. **Fold into the quality plan:** R-10 → Q6, R-16 → Q4, R-17 and R-22 → Q5, R-11 → new Android item,
   R-26 → Q1, R-14 / R-24 → a small accessibility item, Lows as they are touched.
6. **Launch prep:** R-29, R-32, R-34 decision, R-21.
