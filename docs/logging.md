# Logging

Every log line is one JSON object on standard output (`vayu/settings/base.py`, `LOGGING`). A line
looks like this:

```json
{"asctime": "2026-11-25 18:39:02,136", "levelname": "INFO", "name": "vayu.events",
 "message": "booking.stage_changed", "event": "booking.stage_changed",
 "request_id": "6267b7def43d4be0a32e72c7dbe7c666", "task_id": "-",
 "booking": "3f1c…", "booking_id": "SA37926", "from_stage": "draft", "to_stage": "assigned",
 "user_id": 12}
```

## Following one request

- `request_id`: the API request's id. A client may send `X-Request-ID` (letters, digits, `.`, `_`,
  `-`, up to 64); otherwise the server makes one. The response carries it back in `X-Request-ID`.
- A Celery job queued by that request logs **the same** `request_id`, plus its own `task_id`
  (`vayu/celery.py`). Outside a request or job both are `-`.

So to follow a booking from the click to the PDF: find the request id in the web or app error, then
search the logs for it.

## Levels

The same in every environment (local, test, e2e, production):

| Logger | Level | Why |
|---|---|---|
| everything (root) | INFO | the events below are INFO or WARNING |
| `weasyprint`, `weasyprint.progress` | WARNING | about 8 lines per PDF otherwise |

WARNING means "something was refused or failed and may need a look" (a failed sign-in, a refused
permission, a failed upload). ERROR (with the stack trace) is a bug or an outage (a PDF that would
not render, a ZIP that would not build, a value the database refused).

## Events

Application events are written with one helper, `apps/core/log.py`:

```python
from apps.core import log

log.event("pdf.render_done", booking=str(booking.id), revision=3, pages=12, duration_ms=840)
log.event("auth.sign_in_failed", level=logging.WARNING, user_id="unknown user", ip=ip,
          reason="no_user")
log.event("library.pushed", user=request.user, item=item.id, forms=4)   # user= logs user_id only
```

The message is the event name; values go in fields, never inside the message text.

| Event | Level | Fields | Where |
|---|---|---|---|
| `auth.sign_in` | INFO | user_id, ip | `accounts/services.authenticate` |
| `auth.sign_in_failed` | WARNING | user_id (or `unknown user`), ip, reason (`no_user`, `inactive`, `bad_password`) | same |
| `auth.locked_out` | WARNING | user_id (or `unknown user`), ip | the failure that reaches the limit (5) |
| `auth.sign_in_locked` | WARNING | user_id (or `unknown user`), ip | a try while locked |
| `auth.device_registered` | INFO | user_id, device | phone sign-in |
| `auth.device_revoked` | INFO | user_id, count | sign-out, new phone, Admin sign-out, password reset |
| `auth.password_changed` | INFO | user_id, changed_by | own change, or Admin reset |
| `permission.refused` | WARNING | user_id, view, permission (the keys missing) | `accounts/permissions.perm` / `perm_any` |
| `booking.created` | INFO | booking, booking_id | from the `booking.created` domain event |
| `booking.stage_changed` | INFO | booking, booking_id, from_stage, to_stage, user_id | any stage change |
| `booking.cancelled` | INFO | booking, booking_id, user_id | |
| `booking.assigned` | INFO | booking, booking_id, expert_id | assign and reassign |
| `booking.conflict` | WARNING | booking, booking_id, code | two experts / a released draft arrived |
| `submission.accepted` | INFO | booking, inspection | |
| `submission.rejected` | WARNING | booking, booking_id, user_id, code, errors (error codes only) | `bookings/submissions.submit` |
| `upload.initiated` | INFO | booking, media, kind, size, user_id | `media/services/uploads.initiate` |
| `upload.verified` | INFO | booking, media, kind, size | `media/tasks.verify_asset` |
| `upload.failed` | WARNING | booking, media, field, reason (`checksum`, `not_a_video`, `unreadable_image`) | same |
| `zip.built` | INFO | booking, zip, kind, files, size, duration_ms | `media/zips.build_zip` |
| `zip.failed` | ERROR | booking, zip, kind (+ stack trace) | same |
| `pdf.render_started` | INFO | booking, revision | `reports/tasks.render_report` |
| `pdf.render_done` | INFO | booking, revision, pages, duration_ms | same |
| `pdf.render_failed` | ERROR | booking, reason (`timeout`, `storage_failed`, `render_failed`) (+ stack trace) | same |
| `webhook.delivery` | INFO (success) / WARNING | booking, delivery, integration, webhook_event, status, error, http, attempt, duration_ms | `integrations/webhooks` (every attempt) |
| `api_key.used` | INFO | key_prefix, method | `integrations/apikeys` |
| `api_key.refused` | WARNING | key_prefix (or `unknown`), reason (`invalid`, `revoked`, `action_not_allowed`), action | `integrations/apikeys`, `ext_views.need_action` |
| `library.pushed` | INFO | item, revision, forms, skipped, published, user_id | `forms/library_push` |

`booking` is the booking's internal id (UUID); `booking_id` is its reference (`SA37926`).
The booking events are made from the domain events (`apps/core/events.py`) by
`apps.core.log.on_domain_event`, so every path that changes a stage is covered.

To add an event: call `log.event(...)` with a dotted name, add a row above, and add a test with the
`logged` fixture (`apps/core/testing.py`):

```python
def test_it_is_logged(job, logged):
    ...
    assert logged("upload.verified")[0]["media"] == media_id
```

## Never logged

Whatever the level, these never go into a log line, a log field or an exception message that is
logged:

- customer names, phone numbers, addresses and every other **answer** in a form
- **typed usernames on a failed sign-in** (one can be a password typed into the wrong box): a
  failure logs the account's internal id when the account exists, otherwise `unknown user`
- passwords, tokens (JWT, refresh, report links), API keys (only their 8-character prefix),
  webhook signing secrets
- signed URLs (uploads, downloads, report links) and webhook target URLs and bodies
- the text of a database error (it can quote the customer's value): only its SQLSTATE and path

Two guards keep it that way:

1. `log.event()` refuses field names that would carry such data (`name`, `username`, `password`,
   `phone`, `address`, `answers`, `token`, `key`, `api_key`, `secret`, `url`, `email`,
   `customer`): it raises `ValueError`, so a test fails.
2. `apps/bookings/tests/test_log_events.py` runs a booking journey (create, assign, start, a
   refused and an accepted submission, cancel) with every logger at DEBUG and checks that the
   customer's name, phone, address and a refused answer appear in no log line.

Errors sent to Sentry are scrubbed the same way (`vayu/sentry_scrub.py`).
