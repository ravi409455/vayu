# Webhooks

Part of the [integration guide](README.md). Set up in Admin → Integrations.

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
`image_zip_url`, `video_zip_url`. *Custom*: a JSON document you write in the editor (any object or
list, nested as deep as you like), e.g.
`{"ref": "{{job.booking_id}}", "customer": {"name": "{{booking.customer_name}}"}}`. Type `{{` inside
a string and the values of this form and event are suggested. A string that is exactly one
`{{value}}` keeps the value's type; `{{value | text}}` sends it as text; other JSON (numbers,
true/false, null) is sent as written. Only strings are filled in, names are plain text.

**Authentication.** There is no signature. Put the token your receiver expects in a header (for
example `Authorization: Bearer …`); always use HTTPS.

**Preview.** The editor shows the whole request (method, final URL, headers, body) as it would be
sent for the latest job of the form, or one you pick; a form without jobs shows sample values. A
preview never sends anything and never builds a ZIP. If you remove a field that an integration uses,
publishing the form (and a library push) warns you; the value is then sent as `null`.

**Retries.** 5xx, 429, timeouts and network errors are retried after 1 min, 5 min, 30 min, 2 h, 6 h, 12 h, then marked failed. Any other answer (400, 401, 404, redirects…) is final. Run by the `beat` service every minute.

**Safety.** HTTPS only; addresses that are private, loopback or link-local are refused (checked when saving and again when sending); redirects are not followed. The delivery log keeps metadata only (event, booking, status, HTTP code, a reason code): never customer data. Re-send and the Test button build the body again from today's data.

## What arrives at your server

Example: an integration on the booking form, event `booking.updated`, method `POST`, Standard body
with "Include data" ticked, plus one header row `Authorization: Bearer s3cr3t`:

```http
POST /hooks/vayu HTTP/1.1
Host: crm.example.com
Content-Type: application/json
User-Agent: Vayu-Webhooks/1
X-Vayu-Event: booking.updated
X-Vayu-Delivery: 2b7f4c1e-0a5d-4d8e-9a43-6f1d2c3b4a59
Authorization: Bearer s3cr3t

{"event":"booking.updated","delivery":"2b7f4c1e-0a5d-4d8e-9a43-6f1d2c3b4a59",
 "occurred_at":"2026-11-25T10:42:07.512000+00:00",
 "booking":{"id":"9c0e6a52-3f0b-4c1d-8f53-1e2a7b9d4c10","booking_id":"SA37926"},
 "changed_keys":["inspection_date","inspection_time"],
 "data":{"booking":{"booking_id":"SA37926","city":"delhi","inspection_date":"2026-11-27", "...": "..."},
         "inspection":{},"start":{},"end":{}}}
```

Extra top-level keys appear only for some events: `changed_keys` (`booking.updated`),
`booking_id_change: {from, to}` (an edited Booking ID), `inspection` (inspection events),
`revision` (`pdf.ready`), `alert` and `reason` (alerts). `pdf_url`, `image_zip_url` and
`video_zip_url` appear when their toggles are on. A `booking.deleted` body carries only `event`,
`delivery`, `occurred_at` and `booking`.

### Headers we always set

| Header | Value |
|---|---|
| `X-Vayu-Event` | the event name, e.g. `booking.updated` (`test.ping` for the Test button) |
| `X-Vayu-Delivery` | the delivery's id (UUID); the same on every retry of that delivery |
| `X-Vayu-Test` | `1`, only on the Test button's request |
| `User-Agent` | `Vayu-Webhooks/1` |
| `Content-Type` | `application/json` (only when there is a body) |

### Answering

Answer with any 2xx within **10 seconds**. The body of your answer is ignored.

### Proving the request is ours

Requests are **not signed** (the signature was removed on 2026-11-24 in favour of a token you
choose). Add a header row with a long random token, check it on every request, and use HTTPS. For
example, in Python (Flask):

```python
import hmac, os
from flask import Flask, abort, request

app = Flask(__name__)
TOKEN = os.environ["VAYU_WEBHOOK_TOKEN"]            # the same value as the integration's header
seen = set()                                        # use your database in real life

@app.post("/hooks/vayu")
def vayu():
    sent = request.headers.get("Authorization", "")
    if not hmac.compare_digest(sent, f"Bearer {TOKEN}"):
        abort(401)
    delivery = request.headers["X-Vayu-Delivery"]
    if delivery in seen:                            # a retry of one we already handled
        return "", 200
    seen.add(delivery)
    body = request.get_json()
    print(body["event"], body["booking"]["booking_id"])
    return "", 200
```

and in Node (Express):

```js
const crypto = require("crypto");
const express = require("express");
const app = express();
app.use(express.json());
const token = Buffer.from(`Bearer ${process.env.VAYU_WEBHOOK_TOKEN}`);
const seen = new Set();                              // use your database in real life

app.post("/hooks/vayu", (req, res) => {
  const sent = Buffer.from(req.get("Authorization") || "");
  if (sent.length !== token.length || !crypto.timingSafeEqual(sent, token)) return res.sendStatus(401);
  const delivery = req.get("X-Vayu-Delivery");
  if (seen.has(delivery)) return res.sendStatus(200);   // a retry
  seen.add(delivery);
  console.log(req.body.event, req.body.booking.booking_id);
  res.sendStatus(200);
});
app.listen(8080);
```

### Retries and duplicates

A delivery is tried once, then again after 1 min, 5 min, 30 min, 2 h, 6 h and 12 h when the answer
was a 5xx, a 429, a timeout or a network error; after that it is marked failed. Every other answer
(400, 401, 404, a redirect…) is final. Each try of one delivery carries the same `X-Vayu-Delivery`,
so treat it as the idempotency key: if you have seen it, answer 200 and do nothing.
**Re-send** in the delivery log makes a *new* delivery (a new id) with today's data.

### The Test button

Sends a `test.ping` right away (with `X-Vayu-Test: 1`) for a real booking: the one you pick, else
the newest booking of the form (for inspection events, the newest with a submitted inspection).
With no booking at all, the body has only `event`, `delivery`, `occurred_at` and an empty
`booking`. A test is never retried; the result shows in the delivery log.
