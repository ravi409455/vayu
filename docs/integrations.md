# Integrations: webhooks and the REST API

## Webhooks (Admin → Integrations)
Each integration belongs to one form and sends **one event** as **one request** you design: method,
URL, query parameters, headers and body. It fires on every occurrence of that event. To react to
several events, make several integrations (the **Duplicate** button copies one).

| Event | When |
|---|---|
| `booking.created` / `booking.updated` / `booking.deleted` | bookings (updates include assignment and stage changes; an edited Booking ID carries `booking_id_change: {from, to}`) |
| `inspection.started` / `inspection.submitted` | the expert's inspection |
| `media.completed` | every file verified, booking is Completed |
| `pdf.ready` | a PDF was made (also on every regenerate) |
| `alert.conflict` / `alert.stuck_upload` | two experts, force-released draft, rejected type change; a file stuck uploading |

An integration on the **booking form** can use the three `booking.*` events (for bookings of every
inspection type). An integration on an **inspection form** can use all nine, for bookings of that
inspection type.

**Request.** Method `POST` (default), `PUT`, `PATCH`, `GET` or `DELETE`; `GET` and `DELETE` send no
body. The URL may hold values **in the path only** (`https://crm.example.com/leads/{{job.booking_id}}`):
values are URL-encoded, and an empty one fails that delivery (`missing_path_value`). Query parameters
and headers are rows of name and value; a row whose value is empty for this job is left out, and a
list value is joined with commas. Headers are stored as typed, tokens included. `Content-Type`,
`Content-Length`, `Host`, `User-Agent` and every `X-Vayu-*` header are set by the system. We always
send `X-Vayu-Event` and `X-Vayu-Delivery` (use it to ignore duplicates); the Test button adds
`X-Vayu-Test: 1`.

**Values.** In the URL path, query, headers and body, `{{ref}}` is replaced by a value of the job,
picked from a searchable list in the editor (the list depends on the form and the event):
`booking.<field>`, `start.<field>`, `inspection.<field>`, `end.<field>` (answers, from the latest
published version), `job.*` (Booking ID, `job.previous_booking_id` after an ID edit, type, stage,
city, expert, times), `result.*` (overall rating, ratings, Key Checks, final values after Ops
changes), `link.pdf`, `link.image_zip`, `link.video_zip`, `link.photos.<photo field>` (signed, 7
days; a ZIP link opens a "Preparing… x%" page, cached 7 days), `event.*` (name, delivery id, time,
changed fields, alert code). A body value that is exactly one `{{ref}}` keeps its type (number,
yes/no, list, ISO date); mixed text is text (yes/no as `Yes`/`No`, lists joined with `, `). A value
that does not exist is `null`. Nothing of a **deleted** booking leaves except its Booking ID.

**Body.** *Standard*: `event`, `delivery`, `occurred_at`, `booking: {id, booking_id}`; the toggles add
`data` (booking + inspection answers, limited to the ticked fields when set), `pdf_url`,
`image_zip_url`, `video_zip_url`. *Custom*: only the rows you built, nested objects allowed, e.g.
`{"ref": "{{job.booking_id}}", "customer": {"name": "{{booking.customer_name}}"}}`.

**Authentication.** There is no signature. Put the token your receiver expects in a header (for
example `Authorization: Bearer …`); always use HTTPS.

**Preview.** The editor shows the whole request (method, final URL, headers, body) as it would be
sent for the latest job of the form, or one you pick; a form without jobs shows sample values. A
preview never sends anything and never builds a ZIP. If you remove a field that an integration uses,
publishing the form (and a library push) warns you; the value is then sent as `null`.

**Retries.** 5xx, 429, timeouts and network errors are retried after 1 min, 5 min, 30 min, 2 h, 6 h, 12 h, then marked failed. Any other answer (400, 401, 404, redirects…) is final. Run by the `beat` service every minute.

**Safety.** HTTPS only; addresses that are private, loopback or link-local are refused (checked when saving and again when sending); redirects are not followed. The delivery log keeps metadata only (event, booking, status, HTTP code, a reason code): never customer data. Re-send and the Test button build the body again from today's data.

## REST API (API keys)
Admin → API keys. A key is shown once, stored only as a hash, and can be revoked instantly. Send it as `Authorization: Api-Key <key>` or `X-API-Key: <key>`.

* **Scope** = forms and fields: `{"forms": {"booking": ["*"], "pdi": ["door", "odometer"]}}`. Reads only return in-scope fields; a write with any out-of-scope field is refused with 403 `OUT_OF_SCOPE` and `keys: [...]`.
* **DELETE** is off per key until an Admin turns it on (403 `DELETE_NOT_ALLOWED`); deletes are audited.
* Bookings are found by internal ID (preferred) or Booking ID.

| Call | |
|---|---|
| `GET /api/v1/ext/bookings?stage=&type=&city=&search=` | list (paged) |
| `POST /api/v1/ext/bookings` `{answers}` | create |
| `GET/PATCH/DELETE /api/v1/ext/bookings/<id or Booking ID>` | PATCH `{answers, row_version?}`; without `row_version` the last write wins |
| `POST /api/v1/ext/bookings/bulk` `{items: [{ref, answers}]}` | up to 100; each item succeeds or fails alone |
| `GET/PATCH /api/v1/ext/bookings/<ref>/inspection` | the latest inspection's answers |

API writes fire the same webhooks as the web app (each bulk item fires its own). No rate limiting on keys. Swagger: `/api/v1/docs` (Admin only), schema at `/api/v1/schema`.
