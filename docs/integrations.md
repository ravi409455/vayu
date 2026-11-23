# Integrations: webhooks and the REST API

## Webhooks (Admin → Integrations)
Each integration belongs to one form and subscribes to events. It fires on every occurrence.

| Event | When |
|---|---|
| `booking.created` / `booking.updated` / `booking.deleted` | bookings (updates include assignment and stage changes; an edited Booking ID carries `booking_id_change: {from, to}`) |
| `inspection.started` / `inspection.submitted` | the expert's inspection |
| `media.completed` | every file verified, booking is Completed |
| `pdf.ready` | a PDF was made (also on every regenerate) |
| `alert.conflict` / `alert.stuck_upload` | two experts, force-released draft, rejected type change; a file stuck uploading |

An integration on the **booking form** receives the `booking.*` events of all bookings. An integration on an **inspection form** receives all nine events for bookings of that inspection type.

**Body.** Always `event`, `delivery`, `occurred_at`, `booking: {id, booking_id}` (internal ID and Booking ID). Toggles add `data` (booking + inspection answers, limited to the integration's *fields* list when set), `pdf_url` (signed, 7 days), `image_zip_url`, `video_zip_url` (a web page that shows "Preparing… x%" and then downloads; ZIP cached 7 days; machines can call `GET /api/v1/zips/<token>?format=json`). With a **template** the body is your text instead: `{{ field.customer_name }}`, `{{ booking.booking_id }}`, `{{ event }}`, `{{ pdf_url }}`. Templates run in a sandbox; anything unsafe fails that delivery (it never runs).

**Signature.** `X-Vayu-Signature: sha256=<hex>` = HMAC-SHA256 of the raw body with the integration's secret (shown once; rotate any time). Also `X-Vayu-Event` and `X-Vayu-Delivery` (use it to ignore duplicates).

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
