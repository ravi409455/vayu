# Architecture

How Vayu is put together, for a developer joining the project. What it must do is in
`REQUIREMENTS.md`; how changes are made is in `docs/engineering-standards.md`.

## The pieces

```
 Android app (experts, Ops)        Web app (React, all roles)        Other systems
        │  JWT per phone                  │  session cookie                 │  API key
        └───────────────┬─────────────────┴──────────────┬─────────────────┘
                        ▼                                ▼
              Caddy (TLS) ──► gunicorn: Django + DRF  /api/v1/...
                                   │        │
                         PostgreSQL 16    Redis ──► Celery workers + beat
                                   │                      │
                                   └── Cloudflare R2 (files; phones upload directly)
```

| Part | Where | Notes |
|---|---|---|
| API | `backend/` (Django 5, DRF) | one process type, `vayu/urls.py` mounts every app under `/api/v1` |
| Jobs | Celery, queues `default`, `uploads`, `notify`, `zips`, `purge`, `pdf` | `CELERY_TASK_ROUTES` in `vayu/settings/base.py`; in production one worker per group so a pile of ZIPs never holds up uploads (`infra/docker-compose.prod.yml`); `pdf` renders one at a time |
| Schedule | Celery beat | webhook retries (1 min), report sweep (5 min), late starts (5 min), stuck uploads and media purge (hourly) |
| Files | S3 API (R2 in production, a local stand-in in dev) | phones and browsers upload straight to storage with signed URLs; the API only signs and checks |
| Web | `web/` (React 18, TypeScript, TanStack Query, Vite) | pages in `src/pages`, shared UI in `src/ui`, rules in `src/lib`, server access in `src/api` |
| Android | `android/` (Kotlin, Compose) | `core/` data, rules, sync and outbox; `ui/` screens; offline first |

## Backend apps and who may use whom

| App | Holds |
|---|---|
| `core` | the shared basics: the coded error (`errors.fail`), the stale-edit guard (`concurrency`), domain events (`events`), log events (`log`), request ids, pagination, run-time settings |
| `accounts` | users, roles and permissions, phones (devices), sign-in, audit log |
| `forms` | master lists, forms and versions, the field-type registry (`fieldtypes.py`), rules (JsonLogic), field access, the library, promote |
| `bookings` | bookings, inspections (start, submit, edit, conflicts), stages, search, dashboards, sync for the app |
| `media` | uploads, file checks, previews, ZIPs, retention |
| `scoring` | ratings and Key Checks computed from answers |
| `reports` | PDF templates, rendering (WeasyPrint), the report and its verify page |
| `integrations` | webhooks, API keys and the `/ext` API |
| `notify` | the bell, pushes, app releases |
| `platform` | health, settings API, setup and demo data, the OpenAPI schema class and the error-code catalogue |

Rules: views → services → models; `core` uses no other app (only its test helpers,
`core/testing.py`, use `accounts`). Many apps still call each other inside functions
(for example `forms` asks `reports` and `integrations` for publish warnings); those imports are
local to the function to keep import time free of cycles. Prefer an event (below) for new
"something happened, others react" links.

## A request

1. `RequestIdMiddleware` gives the request an id (logged on every line, returned as
   `X-Request-ID`).
2. Authentication: the web session, a phone's JWT (the phone must still be signed in), or an API
   key (`/ext` only).
3. Permission: every view declares `perm("<key>")`; a test checks no view forgets. "own" scopes
   filter querysets to what is assigned to the caller. Field access (hidden / view / edit per role
   and stage) filters answers on the way out and refuses hidden fields on the way in.
4. The view parses and calls a service; the service checks the rules, locks the row
   (`select_for_update`), checks `row_version` (`core.concurrency.check_row_version`), saves,
   writes the audit or activity row and emits a domain event.
5. Errors leave as `{"code", "detail", ...}` (`core/exceptions.py`); every code is in
   `docs/error-codes.md`.

## Events

`apps/core/events.py` lists every domain event (`booking.created`, `inspection.submitted`,
`pdf.ready`, `alert.conflict`, …). Services `emit` them; apps subscribe in their `AppConfig.ready`:

- `integrations` → webhook deliveries,
- `reports` → render the PDF on completion, mark it out of date on later changes,
- `notify` → the bell and pushes,
- `core` → structured log events (`docs/logging.md`).

Work that must only happen if the transaction commits (queuing a task) goes through
`core.tasks.after_commit`.

## An inspection, end to end

1. Ops create a booking (booking form answers) and assign an expert → `booking.updated`, push.
2. The phone syncs (`GET sync/jobs`), keeps the booking and the published form versions it needs.
3. **Start** (`POST bookings/<id>/start`) pins the form versions; stage `in_progress`.
4. Photos upload directly to storage (`media/initiate` → signed part URLs → `complete`); a
   `verify_asset` task checks the checksum and real content and makes previews.
5. **Submit** (`POST bookings/<id>/submit`): answers are validated against the pinned version,
   scoring runs, stage `submitted` ("Uploading").
6. When every expected file is verified the booking becomes `completed`; the PDF renders on the
   `pdf` queue; webhooks for `media.completed` and `pdf.ready` go out.

## Data, briefly

- `Form` → `FormVersion` (draft or published; a published one never changes) → `Page` →
  `Section` → `Field`. A field's `key` never changes. Library items link fields and sections across
  forms with a revision.
- `Booking` (one car) holds the booking answers plus copies of the searchable columns (city, date,
  stage, chassis no.); `Inspection` holds the start / inspection / end answers, the pinned versions,
  scores and Ops overrides. One inspection "counts" for the report.
- `MediaAsset` is one file; `MediaZip` a built ZIP; `Report` the latest PDF and its render history.
- `Integration` / `Delivery` / `ApiKey`; `Notification`; `AuditLog` (append-only).

## Where rules live

| Rule | Place |
|---|---|
| field types (config, answer cleaning, display) | `backend/apps/forms/fieldtypes.py` `TYPES`; web `src/lib/fieldTypes.ts` + `src/ui/FieldInputs.tsx`; Android `core/forms/FieldTypes.kt` |
| conditions (show-if, required-if) | JsonLogic, the same test vectors in `shared/rule-vectors/` for every layer |
| field access | `backend/apps/forms/access.py` (and its web / Android mirrors for display only) |
| stages and allowed moves | `backend/apps/bookings/stages.py` |
| ratings and Key Checks | `backend/apps/scoring/` |
| permissions catalogue | `backend/apps/accounts/catalog.py` |
| error codes | raised with `fail()`; catalogue `apps/platform/error_codes.py` → `docs/error-codes.md` |

## Decisions already made

Recorded in `plan.md` (amendments) and the plan files in `docs/`: JsonLogic with shared test
vectors for conditions; WeasyPrint for PDFs; files go directly from the device to storage; an
inspection's form version is pinned at Start; the library owns linked fields and sections
(edits arrive as updates, archived not deleted); form types (booking, start, end, custom);
webhooks authenticated by a token header, not a signature; no per-API-key rate limit.
