# REST API for other systems

Part of the [integration guide](README.md). Code: `backend/apps/integrations/ext_views.py`.

## Authentication

An Admin makes a key in Admin → API keys. The full key (`vk_<8 hex>_<secret>`) is shown **once**;
Vayu keeps only its hash and the 8-character prefix. Send it on every call, either way:

```bash
curl -H "Authorization: Api-Key vk_1a2b3c4d_xxxxxxxx" https://vayu.example.com/api/v1/ext/bookings
curl -H "X-API-Key: vk_1a2b3c4d_xxxxxxxx" https://vayu.example.com/api/v1/ext/bookings
```

A wrong or revoked key answers `401`. Revoking is immediate. Keys work only on `/api/v1/ext/*`; a
signed-in web session does not.

## What a key may do

Each key has three settings, chosen by the Admin:

- **scope**: the forms and fields it may read and write, by form key.
  `{"forms": {"booking": ["*"], "pdi": ["door", "odometer"]}}` gives every booking field and two
  fields of the `pdi` inspection form. Reads leave out fields outside the scope; a write that names
  one is refused with `403 OUT_OF_SCOPE` and `keys: [...]`. A form not in the scope at all:
  `403 OUT_OF_SCOPE`.
- **allow_delete** (off by default): without it `DELETE` answers `403 DELETE_NOT_ALLOWED`.
- **allowed_actions** (none by default): any of `assign`, `cancel`, `reschedule`, `change_type`.
  Without the flag the action answers `403 ACTION_NOT_ALLOWED`. Creating a booking with
  `assigned_expert` needs `assign`; a PATCH that moves `inspection_date` / `inspection_time`
  needs `reschedule`.

Writes made with a key follow the same rules as the web app (validation, stages, audit log) and fire
the same webhooks.

## Finding a booking

Every `<ref>` below is the booking's internal id (a UUID, preferred) or its Booking ID
(`SA37926`, any letter case).

## Calls

### List bookings

`GET /api/v1/ext/bookings?stage=&type=&city=&search=&page=&page_size=`

`stage`, `type` (inspection type) and `city` match exactly; `search` matches part of the Booking ID.

```json
{"count": 132, "next": "https://vayu.example.com/api/v1/ext/bookings?page=2", "previous": null,
 "results": [
  {"id": "9c0e6a52-3f0b-4c1d-8f53-1e2a7b9d4c10", "booking_id": "SA37926", "stage": "assigned",
   "inspection_type": "pdi", "assigned_expert": 14, "row_version": 3,
   "created_at": "2026-11-24T09:12:44.120000+05:30",
   "data": {"booking_id": "SA37926", "city": "delhi", "inspection_date": "2026-11-27",
            "inspection_time": "15:30", "customer_name": "Asha", "...": "..."}}]}
```

`data` holds only the booking fields in the key's scope.

### Create a booking

`POST /api/v1/ext/bookings` with `{"answers": {...}}` (booking form field keys):

```bash
curl -X POST https://vayu.example.com/api/v1/ext/bookings \
  -H "Authorization: Api-Key $KEY" -H "Content-Type: application/json" \
  -d '{"answers": {"booking_id": "SA37926", "customer_name": "Asha", "customer_phone": "9876543210",
       "address": "12 MG Road", "city": "delhi", "inspection_date": "2026-11-27",
       "inspection_time": "15:30", "inspection_type": "pdi", "car_make_model": "maruti_victoris"}}'
```

Answers `201` with the booking (the same shape as a list row). Invalid answers:
`400 INVALID_ANSWERS` with `errors` (`{field: code}`) and `messages` (`{field: words}`).

### Read, change, delete one booking

- `GET /api/v1/ext/bookings/<ref>`: the booking.
- `PATCH /api/v1/ext/bookings/<ref>` with `{"answers": {...}, "row_version": 3}`. Send the
  `row_version` you read to be told if someone changed it since (`409 STALE_BOOKING`, with
  `changed_by`, `changed_at`, `changed_keys` and the current `row_version`). Without
  `row_version` the last write wins.
- `DELETE /api/v1/ext/bookings/<ref>`: `204`; needs **allow_delete**; audited.

### Actions

`POST /api/v1/ext/bookings/<ref>/<action>`; each needs its flag (see above):

| Action | Body |
|---|---|
| `assign` | `{"expert": 14}` (an active expert's user id; also reassigns) |
| `cancel` | `{"reason": "on_arrival"}` (a key of the cancel reasons list) |
| `reschedule` | `{"date": "2026-11-28", "time": "11:00", "reason": "customer_request"}` |
| `change-type` | `{"inspection_type": "ev"}` (only before the expert starts) |

Answers the booking. An unknown action: `404 UNKNOWN_ACTION`.

### Many changes at once

`POST /api/v1/ext/bookings/bulk` with 1 to 100 items. Each item is a PATCH on its own: one that
fails does not stop the others, and nothing of a failed item is saved.

```json
{"items": [{"ref": "SA37926", "answers": {"city": "gurgaon"}},
           {"ref": "SA00000", "answers": {"city": "gurgaon"}}]}
```

```json
{"results": [{"ref": "SA37926", "ok": true, "booking": {"id": "9c0e…", "...": "..."}},
             {"ref": "SA00000", "ok": false,
              "error": {"code": "NOT_FOUND", "detail": "Booking not found."}}],
 "failed": 1}
```

Each changed booking fires its own webhook.

### The inspection

- `GET /api/v1/ext/bookings/<ref>/inspection`: the latest inspection,
  `{"id", "status", "row_version", "data"}`, `data` limited to the inspection form's fields in
  scope. No inspection yet: `404 NO_INSPECTION`.
- `PATCH /api/v1/ext/bookings/<ref>/inspection` with `{"answers": {...}, "row_version"?}` changes
  the submitted inspection (an Ops-style edit). Not submitted yet: `409 NOT_SUBMITTED`; a stale
  `row_version`: `409 STALE_INSPECTION`.

## Pagination

Lists are pages: `{count, next, previous, results}`, 50 rows by default, `page_size` up to 200.
Follow `next` until it is `null`. A page past the end answers `404 NOT_FOUND`.

## Errors

Every error has the same body:

```json
{"code": "OUT_OF_SCOPE", "detail": "This key may not write these fields.", "keys": ["customer_phone"]}
```

Key your handling on `code`; `detail` is English for people. A field problem in the request shape
is `400 INVALID` with `fields`. Every code, its HTTP status and meaning is in
[error-codes.md](../error-codes.md), made from the code by a test, so it is always complete.

## Limits

There is **no rate limit per API key** (decided; see `docs/plan-quality.md`). A key that misbehaves
or leaks is revoked by an Admin, which takes effect on the next request.

## Machine-readable description

The OpenAPI file is `backend/openapi.yaml` in the repository; a signed-in Admin can also open it at
`/api/v1/schema` and browse it at `/api/v1/docs` (Swagger UI). Every operation tagged `ext` is part
of this API.
