# Plan: Vayu Android app (Experts and Ops)

Status: **planned, not started.** Design approved by the product owner on 2026-11-24.
This plan **replaces plan.md Phases 13–15** (Android expert screens only). The old Phase 16
(Launch) becomes Phase 18.

- What the app must do: [`docs/android-requirements.md`](android-requirements.md) (agreed rules).
- What it must look like: the approved clickable prototype (Design canvas "Vayu Android prototype",
  https://claude.ai/artifact/MispXpMpVHpRVgUFjMtu6a). Screens on the "Parked ideas" page are **not** built.

## Scope in one paragraph
One Kotlin / Jetpack Compose app (`in.carcid.vayu`, "Vayu", Android 11+, phones, portrait). Experts get
My jobs, the offline inspection (check-in, wizard, camera, scan, review, submit, uploads). Ops get
everything Ops web does (Today, Bookings, booking detail with answer/media/rating/payment edits,
reports, Needs you, Dashboard), read-only when offline. Admins are refused at sign-in. One phone per
person. Push notifications for both roles. APK download + self-update.

## Open question (default applies until answered)
- **"New bookings" push to Ops:** only bookings created through the API/ERP (default), or every new
  booking including ones Ops create themselves?

## Architecture (decided)
| Concern | Choice | Why |
|---|---|---|
| UI | Jetpack Compose + Material 3, with a **Vayu theme** built from the web tokens (light, dark, match phone) | Approved look; standard Android behaviour (back, sheets, pickers) |
| Structure | One `app` module; packages `core/` (api, db, sync, rules, media, push), `ui/` (design system), `expert/`, `ops/`, `shared/` (sign-in, profile, notifications) | One APK, roles split by package, no premature multi-module |
| State | ViewModel + Kotlin Flow; manual constructor injection (no Hilt) | Small team, fewer moving parts |
| Network | OkHttp + kotlinx.serialization JSON (no Retrofit: one small `Api` class); `ApiContractTest` checks every call the app makes exists in `backend/openapi.yaml` | API is frozen; drift is caught in CI |
| Local data | App-private JSON files with atomic writes (no Room): `jobs-<user>.json` (jobs, frozen form versions, lists), one file per draft (answers saved on every change), the upload queue, the Ops read cache | Offline-first for experts; simpler than a database for a few hundred records |
| Background | Sync on sign-in, on opening the app and on Refresh; WorkManager for uploads (8 MB parts, resumable) from Phase 15 | Uploads must survive restarts and reboots |
| Rules | Own port of json-logic-js (`core/rules`), **passes 100% of `shared/rule-vectors`** | Same answers as Python and TypeScript (no Java library matched JS coercion) |
| Camera | CameraX; stamp burned in on the phone; video 720p up to 60 s | Requirement |
| Scan | ML Kit on-device text recognition (no network) | Works offline; text always shown for confirmation |
| Push | Firebase Cloud Messaging (`android/app/google-services.json` is already present) | Requirement |
| Errors | Sentry Android (added in Phase 17, needs the DSN) | Same as web/server |

## Backend additions (all additive: no breaking API change, oasdiff stays green)
| # | Change | Notes |
|---|---|---|
| B1 | Mobile sign-in refuses Admins: `403 ADMIN_USE_WEB` | Web sign-in unchanged |
| B2 | `GET sync/jobs?since=` (expert: assigned + own drafts, frozen forms, master-list changes, Ops-change "old → new" list) and `POST devices/heartbeat` (`unsynced` counts) | As planned in old Phase 13. Sign-in on a second phone while the first reports unsynced data → `409 DEVICE_HAS_UNSYNCED_DATA`. Applies to Ops too (one phone each) |
| B3 | Push: `POST devices/push-token`; `Notification` rows (the bell list) + `GET notifications`, `POST notifications/read`; FCM sender task; prefs `User.notify_prefs` set through `PATCH auth/me/profile` (problems can't be muted) | Expert events: assigned, rescheduled, cancelled / reassigned away, details changed. Ops events: Needs-you problems, submitted, completed, started, late start, new booking (see open question) |
| B4 | Late-start check: beat task every 5 min, "30 min past its time and not started" → Ops push once per booking | |
| B5 | Field option `scan` (true/false) on **short-text fields only**; field editor switch in the web form builder ("Let the expert scan this with the camera") | Web wizard ignores it |
| B6 | `GET app/latest` (version code, download URL, SHA-256, notes, minimum version) + a download page on the web; APK stored in R2 | Self-update |

## Phases
Each phase: tests first (red), then the code, then CI green, then a short demo on a real phone.

### Phase 13 — Foundation (≈ 1.5 weeks)
- **Backend:** B1, B2 (tests first; 100% branch coverage on the new sync/heartbeat code).
- **App:** project skeleton, CI (lint, unit tests, Compose UI tests, release build), Sentry.
- **Design system:** colours and type from the web tokens (light/dark/system), top bars, the two bottom
  bars, rows, segmented controls, chips, sheets, banners (all closable except the offline strip),
  status dots and pills. **Screenshot tests** (Roborazzi) for each component in light and dark.
- **Sign-in flow:** sign in (illustration + logo mark), Admin refused, forced password change, one
  phone per person, sign-out blocked while unsynced (with counts).
- **Role routing:** Expert → My jobs; Ops → Today. Profile (picture, theme shared with web, password).
- **Rules adapter:** passes all shared rule vectors (gate for Phase 14).

### Phase 14 — Expert inspection, offline (≈ 2 weeks)
- My jobs (Today / Upcoming / Done, search by booking ID or customer), job details with Call /
  WhatsApp / Directions, Start.
- Sync worker (B2), frozen versions, Ops-change banner, clock offset and "unverified" time.
- Check-in: job becomes "in progress" only when the check-in is complete (queued offline, sent with
  the check-in time).
- Wizard: one page per screen, page list (ticks, needed counts, not-opened dots), gate pages,
  conditions live, **every field type**, answers saved on each change (NF1: committed before the
  screen acknowledges it), auto-scroll to the next unanswered question, per-section counts,
  "Next · page name", "N still needed · Show me".
- **Choice layout rule:** up to 4 short options → one row; 5–8 or long labels → stacked rows with
  severity tags; 9+ → plain scrolling list from the bottom (no search). Multi-select: chips up to 8,
  checklist beyond.
- Review (needed answers, pages not opened), Submit (idempotent), answers locked after submit.
- Reassigned (submit or discard), cancelled with draft, type change after offline start, minimum
  app version (finish but not start).

### Phase 15 — Media and scan (≈ 1.5 weeks)
- CameraX with stamp (booking ID, expert, corrected time, GPS or "GPS unavailable"); gallery only
  when the field allows it; video 720p ≤ 60 s; photo review, delete, retake.
- ~2048 px / ~500 KB + preview; uploads start immediately; WorkManager 8 MB parts, resume after
  restart / airplane mode / reboot, checksum mismatch → resend.
- Uploads tab: per-job files, progress, retries, phone storage, clear sent copies (never unsent).
  Storage < 2 GB warning, < 500 MB blocks Start.
- Scan (B5): Scan icon inside text fields where the Admin enabled it; confirm sheet; field stays
  editable.
- Payment (QR, two slots, pay later) on the wrap-up page.

### Phase 16 — Ops screens (≈ 2.5 weeks)
- Today (variant B: day-progress bar, Unassigned with Assign, experts expandable).
- Bookings (search, Today / Upcoming / All, one Filter sheet, "Need an expert" and "Scheduled").
- New / edit booking, assign / reassign sheet, reschedule, cancel, force-release, sign out the
  expert's phone, delete draft (Ops) — all from the booking's ⋮ menu.
- Booking: customer and details, attention card (conflict: compare and choose), rows to Answers
  (edit in a sheet, "someone else saved" handling), Photos and videos (view, play, add, replace,
  delete, ZIP), Ratings and payment (override ratings and Key Checks, verify / record payments),
  Report (open, share, remake), History.
- Needs you (Problems / Updates), Dashboard (period, one chart, split by, CSV export and share).
- Offline for Ops: last-loaded data with the "Offline · as of 10:42" strip; actions show a lock.

### Status after Phases 13–16 (built, not yet tried on a phone)
- Done: everything listed in 14, 15 and 16, with these differences:
  - Payments: the server has no "verify / record a payment" API, so Ratings and payment shows the
    wrap-up answers only (change them through Answers). Needs a backend addition if wanted.
  - Needs you → Updates waits for notifications (Phase 17); Problems is complete.
  - Ops screens refresh on Refresh, after every change and when the app comes back to the front
    (not every minute).
  - Booking ⋮ menu also has "Sign out the expert's phone" (users.sign_out_devices).
- Next: try it on a phone, then Phase 17.

### Phase 17 — Push, alerts, release (≈ 1.5 weeks)
- **Backend:** B3, B4, B6.
- Push for both roles; tapping opens the job or booking; each push triggers a sync. Bell lists.
  Ops notification settings (mute types, problems always on).
- On-phone alerts: reminder 60 min before each job; "photos haven't sent for 2 hours".
- Self-update (download, Android install prompt), release signing (keystore backed up offline;
  release build fails without it), Sentry release tags.
- **E2E J6** (on the owner's test phone, not an emulator — owner's choice): offline inspection → reconnect → uploads resume → Completed; reassign
  conflict path; Ops assigns a job and the expert gets the push.

- **Release signing set up (2026-11-24).** Key and passwords live in `~/vayu-keys` (outside the
  project, backed up offline by the owner). Every release must show this signer:
  `CN=Vayu, O=CarCID, C=IN`, SHA-256 `251bb5d28b2423c1ff6dd3d6badfd94be503956e36590f48abe8fd356640f0cd`
  (check: `apksigner verify --print-certs app-release.apk`).

### Phase 18 — Launch (was Phase 16)
Unchanged from plan.md: seeds, release rehearsal, staging trial with 2–3 experts and Ops.
- Payments (owner, 2026-11-24): **done as generic form features, not payment screens**: payment is
  ordinary wrap-up fields (unlocked), the two unused payment permissions are removed, and Bookings can
  be filtered by an answer (web and Android). See REQUIREMENTS §5.2.

## Testing and gates
- Unit (JUnit 4, a route-based fake server instead of mocks), Robolectric, Compose UI tests for every
  screen, Roborazzi screenshots of every prototype screen in light and dark (reviewed against the
  canvas once, then locked).
- Coverage: `core/` (domain and data) ≥ 80%, enforced by Kover in CI (plan NF11); rules 100% of the shared vectors.
- CI also builds the release APK (catches shrinking problems early).
- Backend additions follow the existing 100% branch-coverage gates.

## What you (the owner) need to provide, and when
| Item | Needed by |
|---|---|
| A test phone on Android 11+ (and the Android Studio setup on this Mac, I can guide) | Phase 13 |
| Firebase: the server credential for sending pushes (put in `backend/.env.local`, never in chat) | Phase 17 |
| Release signing keystore, created by you and backed up offline (I give the exact command) | Phase 17 |
| Answer the open question above | Phase 17 |

## Estimate
About **9 weeks** for Phases 13–17 (the original plan had 5 weeks for an expert-only app; full Ops
parity adds about 3–4 weeks).

## Risks
| Risk | Mitigation |
|---|---|
| Ops parity doubles every future Ops change (web and app) | Shared API and the same screen structure; note it in each future Ops plan |
| `json-logic-java` disagrees with the other two libraries on some rule | Gate in Phase 13 on the shared vectors; banned operators stay banned |
| Upload reliability on bad networks | WorkManager resume tests in airplane mode and after process death; checksum on every part |
| Push delivery delays (FCM) | Every push only triggers a sync; Pull-to-refresh and the Refresh button always work |
| Lost signing key | Keystore backup checklist; release build refuses to run without it |
