# Integration guide

How another system works with Vayu. Two ways, often used together:

| | Who starts it | Use it to |
|---|---|---|
| [Webhooks](webhooks.md) | Vayu calls your URL when something happens | hear about new bookings, stage changes, finished inspections, the PDF |
| [REST API](rest-api.md) | your system calls Vayu with an API key | create and change bookings, read answers, assign, cancel, reschedule |

## A first integration, end to end

1. **Get a key.** An Admin opens Admin → API keys → New key, names it ("CRM"), gives it the
   `booking` form with `*` (all fields), and copies the key shown once.
2. **Create a booking** from your system:
   `POST /api/v1/ext/bookings` with `{"answers": {...}}` ([details](rest-api.md#create-a-booking)).
   Keep the `id` it returns.
3. **Hear what happens.** The Admin opens Admin → Integrations → New, picks the booking form and
   the `booking.updated` event, enters your URL, adds a header `Authorization: Bearer <a token you
   choose>`, and presses **Test**. Your server receives a `test.ping` ([what arrives](webhooks.md#what-arrives-at-your-server)).
4. When Ops assign the booking or the expert finishes, your server receives `booking.updated`
   with `changed_keys` (for example `["stage", "assigned_expert"]`). Fetch the details with
   `GET /api/v1/ext/bookings/<id>`.
5. Answer every webhook with a 2xx within 10 seconds, and ignore an `X-Vayu-Delivery` you have
   already handled (retries carry the same one).

## Errors

The REST API answers every refusal with `{"code", "detail", ...}`; the codes are listed in
[error-codes.md](../error-codes.md). Webhook failures are shown to the Admin in the delivery log with
a reason code (`http_500`, `timeout`, `connection_error`, `missing_path_value`, `blocked_address`,
`retries_exhausted`, …).

## Versioning and changes

- Everything is under `/api/v1`. There is one version today.
- Fields can be **added** to answers and webhook bodies at any time: ignore keys you do not know.
- A change that removes or renames something, or changes a type, is caught in CI by comparing the
  OpenAPI file with the previous one (`oasdiff`); it can only land when marked as deliberate, and
  it is then listed in the changelog below. There is no fixed notice period yet: before launch
  there are no outside consumers; agree one with each integrator before going live.

## Changelog

| Date | Change |
|---|---|
| 2026-11-25 | OpenAPI: list operations renamed `*_list` (`api_keys_list`, `integrations_list`, `ext_bookings_list`, `pdf_shared_list`), `ext_bookings_action`, `verify_media_retrieve`; field types filled in where they showed as `string` (for example `locked` is a boolean). No request or response changes. |
| 2026-11-25 | One error body for every refusal (`code`, `detail`); one pagination (`page_size` up to 200); stage and status fields documented as enums; API-key action flags (`allowed_actions`). |
| 2026-11-24 | Webhooks: one event per integration and a request designer (method, URL, query, headers, Standard or Custom body). The signature header `X-Vayu-Signature` and per-integration secrets were removed: use a token header. |
