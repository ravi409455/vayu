# Development Plan
**PRD:** REQUIREMENTS.md
**Design Doc:** none (design decisions are recorded in REQUIREMENTS.md §§2–11b)
**Snapshot date:** 2026-11-22 (rev 2, after the critical review)
**Project type:** mixed — Python (Django backend), TypeScript (React web), Kotlin (Android)
**Build order:** **Backend + complete web app first (Phases 1–12), then Android (Phases 13–15), then launch (Phase 16).**
**Honest estimate:** **~21 weeks** solo with Claude Code (range 18–22). The 3-month target isn't achievable at this scope. See the Timeline section.

---

## Requirements Summary

**Goal:** Replace Car CID's Clappia setup with a purpose-built booking → expert inspection → PDF report platform: offline-first on Android, heavy on media, and fully configurable through an admin form builder.

**Scope In:**
- Booking lifecycle.
- Expert check-in, inspection and wrap-up (web online + Android offline).
- Form engine: library, versioning, staging→production promotion.
- Media pipeline.
- Key Checks and rating suggestions.
- Basic PDF designer + renderer; public verify page.
- Templated webhooks; scoped REST API; push notifications.
- Ops web: job board, problem queue, search, dashboards.
- Config audit log; APK distribution and self-update.

**Scope Out:** Service History, Expense Manager, Leave, customer messaging, payout computation, calendar, Hindi, Clappia migration, repeating blocks, photo annotation and damage diagram, test mode in production, custom roles, trash/soft delete, uptime alerts. **v1.1:** form-version diff + rollback, Android Ops/Admin screens, polished PDF designer UX.

**Functional Requirements:**
| ID | Description | Pri | Acceptance Criteria |
|----|-------------|-----|---------------------|
| F1 | Auth: 3 fixed roles, username+password, lockout, forced password change, active/inactive | P1 | Locked after 5 failures for 15 min; first login forces a new password; inactive users can't log in |
| F2 | One active device per user; Ops/Admin "sign out all devices" | P1 | A second-device login is refused while the first has unsynced data, unless forced |
| F3 | Master lists + user picker | P1 | List edits are reflected in every form that uses them; picker shows only active users of the role |
| F4 | Form engine: form→version→page→section→field, immutable keys, all input types, locked system fields | P1 | Key edits rejected; system fields can't be removed |
| F5 | Conditions (show/hide, required-if, cross-form) + validation | P1 | Python, TypeScript and Kotlin produce identical results on every shared test case |
| F6 | Field access per role × stage | P1 | Reads and writes outside the access matrix return 403 / field omitted |
| F7 | Linked library, update-on-publish, archive-only when in use | P2 | Library edit shows as "update available"; deleting an item in use → 409 |
| F8 | Staging→production promotion (form + library + lists + PDF template) | P1 | Imported version is identical; master lists matched by key |
| F9 | Booking: 2 IDs, stages, Ops status, reschedule history, cancel reason, assign/reassign/force-release, type lock at Start, Admin-only delete | P1 | Duplicate Booking ID (case-insensitive, trimmed) → 409; illegal state moves → 409 |
| F10 | Expert flow: My Jobs, summary confirm, check-in, linear wizard, blank answers, gap review | P1 | Submit is blocked while any required field is empty |
| F11 | Offline sync: version frozen at Start, conflict rules, logout block, min app version | P1 | Every REQUIREMENTS §6 scenario passes as an integration test |
| F12 | Media: camera/gallery, stamp, ~2048px, resumable direct-to-R2, checksum, local storage rules | P1 | Kill mid-upload → resumes; checksum mismatch → re-upload |
| F13 | Payment: static QR, 2 slots, pay later, Ops verify | P1 | Submit is blocked with no payment and no pay-later |
| F14 | Submitted (x/y) → Completed when all media is verified | P1 | PDF and webhooks fire only at Completed |
| F15 | Key Checks + rating suggestions, recalculated on edit, overrides kept | P1 | Numbers match REQUIREMENTS §5.4; overrides survive recalculation |
| F16 | Ops post-submit edits with a "changed by X" guard; media add/replace/delete | P1 | A stale save → 409 carrying the editor's name and time |
| F17 | PDF designer: blocks, label mapping, show-if, branding, publish, unmapped-field warning | P1 | The SA37926 layout can be rebuilt with no code changes |
| F18 | PDF render: auto + regenerate, latest only, page numbers, revision, filename, QR | P1 | Revision increments; the old file is replaced |
| F19 | Public verify page (summary only) | P2 | No customer name, phone or address in the response |
| F20 | Webhooks: integrations × events, toggles, sandboxed templating, HMAC, retries, log, test | P1 | Signature verifies; backoff schedule respected |
| F21 | ZIP "Preparing…" page with a 7-day cache | P2 | Second request is served from cache |
| F22 | REST API: scoped keys, delete off by default, bulk, internal/booking ID, Swagger | P1 | DELETE without the grant → 403 |
| F23 | Push notifications (FCM) for 4 event types | P2 | The right expert receives each push; it triggers a sync |
| F24 | Ops job board, problem queue, global search | P1 | Search finds bookings by ID, name, phone, chassis no. and car |
| F25 | Dashboards (volume) + CSV export | P2 | CSV rows equal the filtered table rows |
| F26 | Config audit log | P2 | Every config mutation writes an audit row |
| F27 | APK self-update + forced minimum version | P1 | An app below the minimum can't start new jobs but can finish one in progress |

**Non-Functional Requirements:**
| ID | Category | Description | Measurable Target |
|----|----------|-------------|-------------------|
| NF1 | Reliability | Answers survive crash, kill or reboot | Every answer is committed to Room **before** the UI acknowledges it (DAO test) + manual kill check per release |
| NF2 | Reliability | Media is kept until server checksum verification | 0 files lost; SHA-256 match 100% |
| NF3 | Performance | PDF render | ≤ 2 min for a 150-photo report on 4 vCPU / 8 GB (measured on staging per release) |
| NF4 | Performance | API latency | p95 < 500 ms for list/open/save at 200 users (Locust on staging per release) |
| NF5 | Scalability | Concurrent uploads | Uploads go straight to R2; the API only signs and verifies |
| NF6 | Security | Webhooks, keys, URLs, templates, auth | HMAC-SHA256; keys stored hashed; signed URLs expire in 7 days; Jinja `SandboxedEnvironment`; HTTPS; lockout |
| NF7 | Observability | Errors, logs, audit | Sentry (server, web, Android); webhook delivery log; config audit log; JSON logs with request ID |
| NF8 | Compatibility | Clients and API | Android 11+; `/api/v1`; OpenAPI breaking-change check (oasdiff) in CI after the freeze |
| NF9 | Correctness | Time | Server-offset timestamps; "unverified" when the offset is from an earlier day |
| NF10 | Reliability | Flaky 4G | 8 MB chunks, resumable |
| NF11 | Quality | Coverage gates (CI) | **100% branch coverage on the 8 critical areas** (below); backend ≥ 85% lines; Android domain/data ≥ 80%; web gated by E2E journeys, not by a coverage %. |

**Design Decisions:**
- Django 5 + DRF + drf-spectacular, Postgres 16, Celery + Redis (separate `pdf` queue with concurrency 1), Playwright Chromium for PDFs.
- React + Vite + TS + TanStack Query; **Uppy (AWS S3 multipart plugin) for browser uploads**.
- Kotlin + Compose + Room + WorkManager + CameraX.
- Cloudflare R2 (S3 multipart pre-signed URLs, CORS for the web app origin); FCM.
- DigitalOcean Bangalore 4/8 VPS + staging VPS, Docker Compose + Caddy.
- **Rules = JsonLogic** with existing libraries (`json-logic-qubit` in Python, `json-logic-js` in TypeScript, `json-logic-java` on Android). Custom operations registered in each, about 30 lines per language:
  - `any_defect(keys)`
  - `count_defect(keys)`
  - cross-form `var` paths like `booking.fuel_type`
  - Proven by the official JsonLogic tests plus `shared/rule-vectors/*.json`.
- Optimistic concurrency via an integer `row_version`.

**Open Questions:** none blocking.

**Domain Keywords:** booking, expert, inspection, form, version, page, section, field, library, master list, media, upload, payment, rating, key check, pdf template, render, verify, webhook, integration, api key, sync, conflict, device, notification, audit, promote.

---

## Project Map

**Type:** Greenfield monorepo (Python + TypeScript + Kotlin). **Needs `git init` + a GitHub remote in Phase 1.**
```
backend/
  vayu/              settings, urls, celery
  apps/accounts        users, roles, devices, lockout, config audit log
  apps/forms           master lists, forms, versions, pages, sections, fields, library, rules adapter, promotion
  apps/bookings        bookings, stages, submissions, access policy, search, dashboards/CSV, sync endpoints
  apps/media           uploads, assets, processing, zips
  apps/scoring         key checks, ratings
  apps/reports         pdf templates, context, renderer, verify page
  apps/integrations    webhooks, api keys, push sender
web/                   React app (admin, ops, expert screens, APK download page)
  src/rules/           JsonLogic adapter (custom ops)
android/               Kotlin app
shared/rule-vectors/   JSON test cases run by all three rule adapters
infra/                 docker-compose.{prod,staging}.yml, Caddyfile
loadtest/              Locust scenarios (run on staging, not CI)
```
**Entry points:** `backend/manage.py`, `celery -A vayu worker -Q default,pdf`, `web/src/main.tsx`, `android/app/.../MainActivity.kt`
**Test layout:**
- Backend: `backend/apps/<app>/tests/` (pytest-django, factory_boy, hypothesis where noted, freezegun, responses, minio in Docker).
- Web: `web/src/**/*.test.ts(x)` (Vitest + Testing Library + MSW) only for logic-heavy components, plus `web/e2e/*.spec.ts` (Playwright).
- Android: `android/app/src/test` (JUnit5, MockK, Turbine, Robolectric, MockWebServer) and `androidTest` (Compose UI, WorkManager, Room).

---

## Relevant Files
### Target — Full Read
None exist yet; every file in this plan is **create**.
### Interface — Signatures Only
- `shared/rule-vectors/*.json`: the contract between the 3 rule adapters (Phase 2).
- `backend/openapi.yaml`: frozen at the end of Phase 12; Android codes against it. Sync-only endpoints are added in Phase 13 as an explicit, additive amendment.
### Referenced — Name Only
- Cloudflare R2, Firebase Cloud Messaging, Sentry, JsonLogic libraries, Uppy.

---

## Critical Areas (100% branch coverage, CI-enforced)
1. Rule adapters (Python, TS, Kotlin) against the shared test cases
2. Scoring (Key Checks, ratings, recalculation with overrides)
3. Booking state machine + type lock + force-release
4. Access policy (role × stage × field)
5. Sync conflict resolution (reassign / cancel / type / force-release / idempotent submit)
6. Upload protocol (initiate / resume / complete / checksum / Completed transition)
7. PDF render context (labels, blanks, missing keys, show-if, photo selection, overrides)
8. Webhook signing, retry schedule, payload toggles

## Critical Journeys (E2E, run on every PR)
- **J1 Admin:** build a 2-page form with a condition → publish → map it in a PDF template → preview PDF.
- **J2 Ops lifecycle:** create booking → assign → reschedule → cancel; duplicate Booking ID rejected.
- **J3 Expert (web):** My Jobs → confirm → check-in → full inspection with photos → payment → submit → Completed → PDF.
- **J4 Ops review:** edit an answer → ratings recalc (override kept) → regenerate → download; stale-save 409 dialog.
- **J5 Integration:** webhook to a local receiver with a valid HMAC → ZIP link prepares and downloads → verify page shows the summary only.
- **J6 Android (Phase 15):** offline inspection → reconnect → uploads resume → Completed; reassign-conflict path.

---

## Risk Register
| Risk | Affected Phase | Mitigation |
|------|---------------|------------|
| Rule results differ between server, web and phone | 2, 12, 13 | One format (JsonLogic) with maintained libraries; official tests + shared test cases in all 3 CIs; server re-validates every submit |
| Android starts at week 16 and gets the least slack | 13–15 | Web expert flow (Phase 12) proves forms, rules and start/submit/conflict semantics first; API frozen; Android phases are client-only apart from 2 small sync endpoints; web flow is the fallback for experts with signal |
| Form builder UI is bigger than estimated | 10 | Given 3.5 weeks; the condition builder emits JsonLogic directly (no custom AST); diff/rollback already deferred |
| Chromium PDF render too slow or out of memory | 7 | Measured on staging with a 150-photo fixture before Phase 8; `pdf` queue concurrency 1, 6 GB container limit, 120 s timeout |
| R2 multipart behaves differently from minio | 6 | One manual test against the staging R2 bucket at the end of Phase 6 and before each release |
| Seed inspection forms entered late or wrong | 12 | You build PDI/PPI/EV in the real builder in weeks 13–15 (also the builder's acceptance test); J3 uses them |
| Timeline (21 weeks vs a 3-month wish) | all | Web milestone at week 16 is usable for Ops/admin even if Android slips |
| Lost APK signing key | 15 | Setup checklist; release build fails without the keystore env |

---

## Phases

> Each task = one commit `<type>(<scope>): <description>`. Test lists are minimums for the critical areas and **examples elsewhere**: test behaviour we wrote, not Django, DRF, Jinja or React internals.

### Phase 1 — Foundation & Auth (PR: "chore: repo, CI, auth, devices, audit") · week 1
**Goal:** Deployable skeleton on staging with login, roles, lockout, forced password change, device registration, force sign-out and the audit log.
**Depends on:** none

**Task 1.1 — `chore(repo): git, monorepo skeleton, compose, CI, Sentry`**
- **What:** `git init` + GitHub remote; layout as in the Project Map; Compose (api, worker, redis, postgres, minio, caddy); CI runs ruff, mypy (django-stubs, normal strictness), eslint, tsc, tests and coverage; Sentry init.
- **Test cases:** [ ] `/api/v1/health` → 200 with db/redis/storage status, 503 when db is down · [ ] request-ID header present and in the logs
- **Acceptance:** CI green; staging reachable over HTTPS.

**Task 1.2 — `test(accounts): users, roles, auth, lockout, password, devices, audit`**
- **Files:** `backend/apps/accounts/tests/{test_auth,test_lockout,test_users_admin,test_devices,test_audit}.py`
- **Test cases:**
  - [ ] Login returns tokens + `must_change_password`; inactive → 403 without revealing whether the password was right
  - [ ] Wrong password ×5 → locked 15 min (freezegun); unlocks after; counter resets on success
  - [ ] Admin create/reset forces a password change; every other endpoint → 403 until changed
  - [ ] Password: min 8, not equal to the username
  - [ ] Only Admin creates/resets/deactivates (parametrised over roles); deactivated users keep their bookings linked
  - [ ] Username unique, case-insensitive
  - [ ] Mobile login registers a device; a new device revokes the old one (the unsynced-data rule arrives in Phase 13 with the heartbeat)
  - [ ] Ops/Admin "sign out all devices" revokes tokens and writes an audit row; Expert → 403
  - [ ] Revoked device token → 401 `DEVICE_REVOKED`
  - [ ] Web session doesn't count as a device
  - [ ] Audit rows are append-only (no update/delete path); list is Admin-only, filterable by actor, action and date
- **Acceptance:** all fail on missing code.

**Task 1.3 — `feat(accounts): implement`**
- **How:** custom `User` with a `role` enum; simplejwt for mobile, session+CSRF for web; DRF permission classes; `audit.record()` as a plain function (no interface, one implementation).
- **Acceptance:** 1.2 green.

---

### Phase 2 — Form Engine Core + Rules (PR: "feat(forms): engine, field types, JsonLogic adapters") · weeks 2–3
**Goal:** Forms/versions/pages/sections/fields, every input type, immutable keys, locked system fields, master lists, and JsonLogic adapters in Python **and TypeScript** proven by shared test cases.
**Depends on:** Phase 1

#### Context Reload Instructions
> Load plan.md (Phase 2), REQUIREMENTS §4, §11. Of Phase 1, only `accounts/permissions.py`.

**Task 2.1 — `test(forms): master lists, structure, keys, system fields`**
- **Test cases:**
  - [ ] Master list with a stable key; duplicate → 409; items ordered; archived items are hidden for new answers but still resolve old labels; only Admin mutates; audit row
  - [ ] Form kinds booking/ops/inspection; one active booking form and one active ops form
  - [ ] Draft editable; published version immutable (every mutation → 409)
  - [ ] Field key matches `^[a-z][a-z0-9_]{1,62}$`, unique within the form across versions; **changing a key → 400**; a deleted key stays reserved
  - [ ] Locked system fields auto-created per form kind; delete → 400; relabel OK
  - [ ] Ordering and visibility at page/section/field level; helper text stored
- **Task 2.2 — `feat(forms): implement`**

**Task 2.3 — `test(forms): input types & validation`** (parametrised valid / invalid / empty-required / empty-optional per type)
- [ ] single, multi, yes/no, master-list dropdown, user picker (active users of the role only)
- [ ] short/long text, number (unit, min/max, decimals), currency (≥ 0, 2 dp), phone (10-digit, optional +91)
- [ ] date, time, datetime (Asia/Kolkata), GPS bounds
- [ ] photo/video count min/max, file type and ≤ 20 MB, signature non-empty
- [ ] system-filled fields reject Expert writes; Ops override stored separately
- [ ] option `is_defect` + `severity`; severity without defect → 400
- [ ] regex: invalid pattern rejected at design time; evaluation runs with a timeout (`regex` module)
- **Task 2.4 — `feat(forms): implement validators`**

**Task 2.5 — `test(rules): shared test cases + Python & TS adapters`**
- **Files:** `shared/rule-vectors/{conditions,required_if,cross_field,derived}.json`, `backend/apps/forms/tests/test_rule_vectors.py`, `web/src/rules/rules.test.ts`
- **Test cases** (critical area, 100% branches):
  - [ ] Official JsonLogic tests pass in Python and TS (sanity check of the libraries)
  - [ ] Custom op `any_defect` / `count_defect`: no answers, all defects, mixed, hidden fields excluded
  - [ ] Cross-form `var` (`booking.fuel_type`) resolves; a missing form or key resolves to null without throwing
  - [ ] Hidden field counts as empty and is never required
  - [ ] required-if chains (A shows B; B required-if C)
  - [ ] Cross-field (`mfg_date <= today`, `odometer > 0`)
  - [ ] Design-time validator: unknown op, unknown key, cycles → error with a path
  - [ ] Property (hypothesis, Python only): evaluation is deterministic and doesn't mutate its input
- **Task 2.6 — `feat(rules): adapters`** (Python + TS; ~30 lines of custom ops each, no custom engine)

---

### Phase 3 — Library & Versioning (PR: "feat(forms): library, publish") · week 4
**Depends on:** Phase 2

**Task 3.1 — `test(library+versions)`**
- [ ] Add a library item as linked or form-local; choose "save to library" vs "form only"
- [ ] Library edit → drafts that use it show `update_available`; published versions are untouched; accept pulls it in, reject keeps the snapshot
- [ ] Publishing snapshots linked items
- [ ] Deleting a library item in use → 409; archive hides it from the picker and keeps existing uses
- [ ] Publish validates: rules compile, no dangling refs, system fields present, keys unique
- [ ] Publish returns a `warnings` list (PDF unmapped fields wired in Phase 7; empty until then)
- [ ] Only Admin publishes; audit row; concurrent publish → one 409 (row_version)
- **Task 3.2 — `feat(library+versions): implement`**

---

### Phase 4 — Bookings, Access, Submissions, Conflicts (PR: "feat(bookings): lifecycle, access, submit, conflicts") · weeks 4–5
**Goal:** Full booking domain + start/submit/conflict semantics (used by the web expert flow and later Android). **No delta-sync or heartbeat endpoints yet** (Phase 13).
**Depends on:** Phases 2–3

**Task 4.1 — `test(bookings): IDs, state machine, actions`** (critical area 3)
- [ ] Internal UUID; Booking ID trimmed, unique case-insensitively (hypothesis over case/whitespace variants)
- [ ] Booking ID edit → `booking.updated` event with old→new (event bus stub); Expert → 403
- [ ] Stage machine: full 6×6 transition matrix (legal pass, illegal → 409)
- [ ] Assign/reassign by user ID; inactive expert → 400
- [ ] Reschedule history (old, new, actor, reason); cancel requires a reason; cancelled keeps data
- [ ] Type change before `started_at` OK, after → 409 `TYPE_LOCKED`
- [ ] Admin-only hard delete + audit; Ops → 403
- [ ] Force-release (Ops/Admin): clears the start lock, records actor, marks `released_draft_expected`
- **Task 4.2 — `feat(bookings): implement`**

**Task 4.3 — `test(access): role × stage × field policy`** (critical area 4)
- [ ] Generated matrix from a fixture form: reads omit hidden, writes to view/hidden → 403 listing keys
- [ ] Expert sees assigned bookings + bookings where they own an unsubmitted draft
- [ ] Rating/derived fields and Extra conveyance never visible to Expert
- [ ] After submit only Ops/Admin (and API keys, Phase 9) can write
- **Task 4.4 — `feat(access): implement`**

**Task 4.5 — `test(submissions): answers, start, submit, conflicts, concurrency`** (critical area 5)
- [ ] Answers keyed to the frozen version; unknown key → 400
- [ ] `start`: freezes the version, records `client_started_at` + device; idempotent by client UUID
- [ ] Start after an offline type change by Ops → expert's type wins, booking type reverted, `TYPE_CHANGE_REJECTED` alert
- [ ] Submit re-validates with the rule adapter; payment rule (slot 1 complete or pay-later)
- [ ] Submit idempotent by `client_submission_uuid`
- [ ] Submit for a booking reassigned to B: accepted + `CONFLICT_TWO_EXPERTS`; B not started → B withdrawn; B started → both kept for Ops choice
- [ ] Submit on a cancelled booking → stored on it; submit after force-release → accepted + conflict
- [ ] Ops edit with stale `row_version` → 409 `{changed_by, changed_at, changed_keys}`; retry with own keys succeeds; `last_edited_by/at` updated; no history rows
- [ ] Minimum app version header: below → 426 on `start`, allowed on `submit`
- [ ] `server_time` returned on start/submit
- **Task 4.6 — `feat(submissions): implement`**

**Task 4.7 — `test+feat(search, dashboards)`**
- [ ] Search by Booking ID (partial), customer name, phone (last 4+), chassis no., car; Expert limited to own jobs (indexed `icontains`, no trigram until measured slow)
- [ ] Volume aggregates by day/week/month × type/city/expert/lead owner; CSV equals the query rows

---

### Phase 5 — Scoring (PR: "feat(scoring): key checks, ratings") · week 6
**Depends on:** Phases 2, 4

**Task 5.1 — `test(scoring)`** (critical area 2)
- [ ] Categories per form (PDI/PPI five; EV swaps Engine for Battery & Charging) and section mapping exactly as REQUIREMENTS §5.4
- [ ] Deductions 0.25 / 1 / 3 from 5, floor 1 (≥ 20 parametrised combinations)
- [ ] Round half up (3.5→4, 3.25→3, 3.75→4)
- [ ] Overall boundaries: 4.5 Excellent, 4.49 Good, 3.5 Good, 3.49 Average, 2.5 Average, 2.49 Bad
- [ ] Any Critical → overall capped at Average
- [ ] Hidden and unanswered fields never count
- [ ] Key Checks via the rule adapter
- [ ] Recalc on Ops edit: non-overridden values update, overridden values never change, clearing an override re-derives
- [ ] Property: rating ∈ [1,5]; adding a defect never raises a rating
- **Task 5.2 — `feat(scoring): implement`**

---

### Phase 6 — Media (PR: "feat(media): R2 multipart, verify, completion, zips") · weeks 6–7
**Depends on:** Phase 4

**Task 6.1 — `test(media): protocol`** (critical area 6)
- [ ] Initiate → asset id + 8 MB part URLs; size/type not allowed by the field → 400; field count limits enforced
- [ ] Same client asset UUID → same asset (no duplicates)
- [ ] Resume: list uploaded parts
- [ ] Complete with SHA-256: match → verified; mismatch → `CHECKSUM_MISMATCH`, stays pending; complete is idempotent
- [ ] Access: assigned expert / draft owner / Ops / Admin only
- [ ] Source tag stored; never in the PDF context
- **Task 6.2 — `feat(media): implement`**

**Task 6.3 — `test(media): processing, completion, ops edits, stuck`**
- [ ] Preview ≤ 480 px; stored image ≤ 2048 px long edge (re-encoded if larger)
- [ ] Video > 60 s flagged; poster frame generated
- [ ] Submitted (x/y) → Completed **exactly once** under 10 parallel completes (select_for_update)
- [ ] Completed enqueues PDF render + `media.completed` event
- [ ] Stuck > X h → problem-queue item + `alert.stuck_upload`
- [ ] Ops add/replace/delete renumbers positions
- **Task 6.4 — `feat(media): implement`**

**Task 6.5 — `test+feat(media): ZIP preparing page`**
- [ ] First request starts the build and returns the page; progress endpoint; cached for 7 days; regenerate invalidates; separate image/video ZIPs; filenames by field label + index
- **Task 6.6 — `chore(media): R2 CORS + manual staging R2 check`** (documented checklist step, not CI)

---

### Phase 7 — Reports & Verify (PR: "feat(reports): templates, renderer, verify") · weeks 7–8
**Depends on:** Phases 2–6

**Task 7.1 — `test(reports): template model`**
- [ ] Block types (cover+info grid, label/value table, ratings row, documents grid, photo grid 1/2/3 cols, heading, rich text, page break, spacer); field key → report label; block show-if via the rule adapter
- [ ] Branding: header/footer, watermark, value colour rules, font sizes
- [ ] Filename tokens `{booking_id} {type_code} {date}`; unknown token → 400
- [ ] Draft → preview → publish; independent from form versions; publish warnings for unmapped form fields (fills the Phase 3 stub)
- **Task 7.2 — `feat(reports): model`**

**Task 7.3 — `test(reports): render context + HTML`** (critical area 7)
- [ ] Values by key, labels from the template; empty rows print blank; **keys missing in older form versions print blank**
- [ ] Hidden blocks skipped; rows in shown blocks always print
- [ ] Photos only by explicit field + position
- [ ] Ratings: override else suggestion
- [ ] No gallery/source data anywhere in the HTML
- [ ] Golden HTML snapshot for the SA37926 fixture
- **Task 7.4 — `feat(reports): context + Jinja HTML`**

**Task 7.5 — `test(reports): render pipeline`**
- [ ] Page numbers, footer "Generated <ts>, rev N"; revision increments; old object deleted (latest only)
- [ ] QR → `https://verify.carcid.in/<token>`, token ≥ 128 bits
- [ ] `pdf` queue concurrency 1; timeout 120 s → failure recorded, problem-queue item, 2 retries
- [ ] Auto on Completed; Regenerate (Ops/Admin) clears the "edited, not regenerated" flag
- **Task 7.6 — `feat(reports): renderer`** + **manual benchmark** of a 150-photo fixture on staging (≤ 120 s) recorded in `docs/benchmarks.md`

**Task 7.7 — `test+feat(verify)`**
- [ ] Valid token → booking ID, car, type, date, overall rating, revision; **payload scanned for customer name/phone/address → none**; invalid → 404; only served on the verify host

---

### Phase 8 — Promotion (PR: "feat(forms): staging→prod promote") · week 9
**Goal:** One promotion feature covering everything authored on staging: form version, linked library items, referenced master lists and PDF template.
**Depends on:** Phases 3, 7

**Task 8.1 — `test(promote)`**
- [ ] Export bundle (JSON) = form version + library items + referenced master lists + PDF template
- [ ] Round trip: export → import into an empty DB → export is identical
- [ ] Import into prod matches master lists by key; missing items created; label differences reported, never overwritten
- [ ] Import always creates a **draft** in prod
- [ ] Key conflict (same key, different type) → rejected with a list
- [ ] Push: staging calls prod `/api/v1/promote` with an Admin API key (no extra bundle signing); prod audit row records the source
- [ ] Bundle schema version newer than the server → 400
- **Task 8.2 — `feat(promote): implement`**

---

### Phase 9 — Webhooks & API Keys (PR: "feat(integrations): webhooks, scoped API, docs") · weeks 9–10
**Depends on:** Phases 4–8

**Task 9.1 — `test(webhooks)`** (critical area 8)
- [ ] Integration CRUD per form (Admin, audited); several per form
- [ ] Only subscribed events are sent (all 9 event types)
- [ ] Payload toggles: full data / PDF link / image ZIP / video ZIP (parametrised combinations)
- [ ] Default payload has internal ID + Booking ID
- [ ] Templating with `SandboxedEnvironment`: `{{ field.key }}` renders; 3 escape attempts (`__class__`, `__subclasses__`, attribute traversal) are blocked; render errors → delivery failed, worker survives
- [ ] HMAC-SHA256 over the raw body; secret rotation
- [ ] Retries 1m, 5m, 30m, 2h, 6h, 12h on 5xx/timeout/429; other 4xx not retried
- [ ] Delivery log, manual re-send, test button
- [ ] API writes and bulk updates fire events
- **Task 9.2 — `feat(webhooks): implement`**

**Task 9.3 — `test(apikeys)`**
- [ ] Shown once, stored hashed, prefix visible, revoke immediate
- [ ] Scoped by form and field keys; out-of-scope write → 403 listing keys
- [ ] DELETE off by default → 403; granted → allowed + audited
- [ ] Lookup by internal ID or Booking ID
- [ ] Bulk PATCH reports per-item failures
- [ ] Swagger at `/api/v1/docs` (Admin)
- **Task 9.4 — `feat(apikeys): implement`**

---

### Phase 10 — Web Shell + Admin (PR: "feat(web): shell and admin") · weeks 10–13
**Depends on:** Phases 1–9

**Task 10.1 — `test(web): shell + admin`**
- **Component tests (logic-heavy only):**
  - [ ] Route guards: forced password change, role-based nav, 401/403/409/426 handlers
  - [ ] Condition builder emits valid JsonLogic (round-trips through `shared/rule-vectors`)
  - [ ] Access-matrix editor state
  - [ ] Key field read-only after first save
  - [ ] Publish dialog shows errors and PDF warnings
- **E2E:** **J1**; users screen (create/reset/deactivate/force sign-out); master lists; rating config; integrations (events, toggles, template sample-render, test button, delivery log); API keys; promote (staging → prod); audit viewer.
- **Task 10.2 — `feat(web): shell`** (Vite, TanStack Query, router, typed client from OpenAPI, Sentry)
- **Task 10.3 — `feat(web): form builder + library + masters + users + rating config`**
- **Task 10.4 — `feat(web): PDF designer`** (block list, properties panel, field→label mapping, live preview iframe, publish)
- **Task 10.5 — `feat(web): integrations, API keys, promote, audit`**

---

### Phase 11 — Web Ops (PR: "feat(web): job board, booking, review") · weeks 13–14
**Depends on:** Phase 10

**Task 11.1 — `test(web-ops)`**
- **Component tests:** 409 "changed by X" dialog retries only own keys; problem-queue tab counts.
- **E2E:** **J2**, **J4**; job board filters (city, expert, type, stage) saved per user; problem queue (stuck, conflicts with choose-inspection, rejected type changes, unverified payments, pay-later outstanding, not regenerated, unverified times); global search; media gallery add/replace/delete; ZIP download; payment verify; dashboards + CSV.
- **Task 11.2 — `feat(web-ops): implement`**

---

### Phase 12 — Web Expert Flow + Web Milestone (PR: "feat(web): expert flow; API freeze") · weeks 15–16
**Goal:** Experts can do a full inspection online on the web. **You build the PDI/PPI/EV forms in the builder during weeks 13–15** (acceptance test of the builder; no seed code for them). API frozen at the end.
**Depends on:** Phases 1–11

**Task 12.1 — `test(web-expert)`**
- **Component tests:** wizard gap review lists every missing required field; payment rule (slot 1 or pay later); ratings never rendered for Expert.
- **E2E:** **J3** using the PDI form you built; **J5**; upload resumes after a page refresh (Uppy); GPS denied → "GPS unavailable".
- **Task 12.2 — `feat(web-expert): implement`** (My Jobs, summary confirm, check-in with browser geolocation + camera input, wizard, client-side resize to 2048 px, Uppy S3 multipart to R2, payment, Google review, submit)

**Task 12.3 — `chore(perf): staging load + PDF benchmark`**
- Locust 200 mixed users → p95 < 500 ms; PDF benchmark; results in `docs/benchmarks.md`. Manual run on staging, not CI.

**Task 12.4 — `chore(api): freeze OpenAPI v1`**
- Commit `backend/openapi.yaml`; oasdiff in CI blocks breaking changes. Additive amendments allowed only for the Phase 13 sync endpoints.

**Milestone gate:** the web app runs on staging and is **used for 2 days by you plus 2–3 Ops/experts**. Feedback is fixed before Android starts.

---

### Phase 13 — Android Core + Sync Endpoints (PR: "feat(android): offline core") · weeks 16–18
**Depends on:** Phase 12

#### Context Reload Instructions
> Load plan.md (Phase 13), `backend/openapi.yaml`, `shared/rule-vectors/*`. Backend source only for the two new sync endpoints.

**Task 13.1 — `test(sync-api): delta sync + heartbeat (server)`**
- [ ] `GET /sync/jobs?since=` → assigned + draft-owned jobs, frozen form versions, master-list delta, Ops changes (old→new for the banner); respects the access policy
- [ ] Not-started jobs report the latest published version; started jobs keep their frozen version
- [ ] `server_time` on every sync; `time_unverified` when the client offset is from an earlier day
- [ ] Heartbeat stores `unsynced`; second-device login while unsynced → 409 `DEVICE_HAS_UNSYNCED_DATA`; never-reported → treated as unsynced; force sign-out still wins
- **Task 13.2 — `feat(sync-api): implement`** (additive OpenAPI amendment)

**Task 13.3 — `test(android-core)`**
- [ ] MockWebServer: auth, `DEVICE_REVOKED`, `DEVICE_HAS_UNSYNCED_DATA`, 426
- [ ] Room migrations; **every answer committed before the UI acknowledges it** (DAO + ViewModel test) — NF1
- [ ] **Kotlin JsonLogic adapter passes 100% of `shared/rule-vectors`** + the official JsonLogic tests
- [ ] Sync worker: stores versions, applies the Ops-change banner, clock offset, version pinning rules
- [ ] Compose UI: login, forced password change, My Jobs, summary confirm, offline Start, wizard renders every input type, conditions live, gap review, Back + page jump
- **Task 13.4 — `feat(android-core): implement`**

---

### Phase 14 — Android Media, Payment, Submit (PR: "feat(android): media and submit") · weeks 18–19
**Depends on:** Phase 13

**Task 14.1 — `test(android-media)`**
- [ ] CameraX stamp (booking ID, expert, corrected time, GPS or "GPS unavailable"); gallery → no stamp, `source=gallery`
- [ ] ~2048 px / ~500 KB; video 720p auto-stops at 60 s
- [ ] Count limits; delete/retake; full-screen review
- [ ] WorkManager 8 MB parts: resume after process death / airplane mode / reboot; SHA-256 mismatch → re-upload (NF2)
- [ ] Uploads start during the inspection
- [ ] Storage: < 2 GB warning, < 500 MB blocks Start; manual clear removes only verified files
- [ ] Payment: QR, 2 slots, pay later; submit idempotent; answers locked; "uploading x/y"
- **Task 14.2 — `feat(android-media): implement`**

---

### Phase 15 — Android Conflicts, Push, Release (PR: "feat(android): conflicts, push, self-update") · weeks 19–20
**Depends on:** Phase 14

**Task 15.1 — `test(push-server)`**
- [ ] Assigned / rescheduled / cancelled-or-reassigned-away / details-changed → FCM to the right expert with `sync=true`; invalid tokens pruned; none to inactive users or revoked devices (FCM mocked)
- **Task 15.2 — `feat(push-server): implement`**

**Task 15.3 — `test(android-edge)`** (mirrors the Phase 4.5 server scenarios)
- [ ] Reassigned with a draft → listed "Reassigned – submit or discard"; both paths work
- [ ] Cancelled with a draft → still syncs; banner
- [ ] Ops type change after an offline Start → app keeps its type, no data loss
- [ ] Force-release → "Released by Ops"; local draft uploaded as a conflict
- [ ] Logout blocked while unsynced (counts shown); force sign-out → data-loss notice
- [ ] Below minimum version → can't Start, can Submit; update prompt
- [ ] Self-update downloads from the web download page and hands off to the system installer (Android verifies the signature)
- [ ] FCM: 4 event types notify and trigger an immediate sync; tap opens the job
- **E2E:** **J6**.
- **Task 15.4 — `feat(android-edge): implement`**

---

### Phase 16 — Launch (PR: "chore: seeds, release, rehearsal") · week 21
**Depends on:** Phases 1–15

**Task 16.1 — `test+feat(seed)`:** Booking form (§11, system fields locked), Ops form (3 pages, stage access per §11), master lists, rating configs (§5.4). Idempotent. Inspection forms come from your builder work and are **promoted**, not seeded.
**Task 16.2 — `chore(release)`:** setup checklist (REQUIREMENTS §11b, including R2 CORS) verified; signed APK on the download page; minimum version set; Sentry releases; DNS. Full regression + staging benchmarks + manual kill check + manual R2 check.
**Task 16.3 — `chore(launch)`:** 1–2 days of rehearsal with 5–10 experts on staging (Clappia still live) → big-bang cut-over.

---

## Timeline (~21 weeks)
| Weeks | Phase |
|---|---|
| 1 | 1 Foundation & auth |
| 2–3 | 2 Form engine + rules |
| 4 | 3 Library & versioning |
| 4–5 | 4 Bookings, access, submit, conflicts |
| 6 | 5 Scoring |
| 6–7 | 6 Media |
| 7–8 | 7 Reports & verify |
| 9 | 8 Promotion |
| 9–10 | 9 Webhooks & API keys |
| 10–13 | 10 Web shell + admin |
| 13–14 | 11 Web Ops |
| 15–16 | 12 Web expert + **milestone + API freeze** |
| 16–18 | 13 Android core + sync endpoints |
| 18–19 | 14 Android media & submit |
| 19–20 | 15 Android conflicts, push, release |
| 21 | 16 Launch |

If 3 months is a hard business date, the honest options are: (a) launch web-only at week ~16, with experts on the web flow wherever they have signal and Android following; or (b) cut scope (e.g. webhook templating, PDF designer → fixed layout). Decide before Phase 10.

---

## Phase Execution Checklist
For each phase before starting:
- [ ] Re-read plan.md — Phase N section only
- [ ] Confirm Phase N-1 tests are passing and coverage gates are green
- [ ] Load only the files listed in this phase's tasks
- [ ] Write tests first (Task N.1) before any implementation
- [ ] After Phase 12: never change `backend/openapi.yaml` incompatibly. Any API change is a Plan Amendment.

---

## Out of Scope Guard
Do not implement these under any circumstance, even if they seem like natural extensions:
- Service History, Expense Manager, Leave apps
- Customer messaging (WhatsApp/SMS/email to customers)
- Payout / conveyance / distance **computation** (plain fields only)
- Calendar / scheduling views, clash detection
- Hindi or any i18n
- Clappia data migration
- Repeating blocks / "add another" groups (payments use 2 fixed slots)
- Photo annotation, car damage diagram
- Test mode in production
- Custom roles, city/team scoping
- Trash / soft delete / data history (simple overwrite; latest PDF only)
- Uptime alerting, rate limiting
- Customer-facing video/gallery links
- A custom rule engine (use JsonLogic + custom ops)
- Seed code for inspection forms (built in the builder and promoted)
- v1.1 items: form-version diff + rollback, Android Ops/Admin screens, polished PDF designer UX
