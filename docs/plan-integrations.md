# Plan: integration request designer (body, method, URL, query, headers, preview)

Status: **built and committed** (`839f822`, `b7d66d9`); the custom body became a JSON editor after first use (see the change note below). Open items: [`plan-fixes.md`](plan-fixes.md). *(Status corrected 2026-11-25.)*

**Change after first use (2026-11-24):** the Custom body is a **JSON editor** (suggestions on `{{`, `{{ref | text}}` forces text, any JSON object or list) instead of a row builder; the form of a saved integration can be changed; the standard body's field checklist lists every field of the form whatever the event. Migration `0003_json_body` converts old row bodies.

Changes found while building P1:
- **`result.defects`** (fields with defect answers) replaces "failed Key Checks": a Key Check is a rule that is true or false, and which one counts as failed depends on the check, so `result.key_checks` sends `[{name, result: true|false}]` as the rule decided (Ops changes included).
- A deleted booking's picker offers the Booking ID and the event values only (not the internal id).
- Delivery error codes: `template_failed` is now `request_failed`; `missing_path_value` is new.
- Value syntax is validated on save (`INVALID_VALUE`, `UNKNOWN_VALUE`, `LOCKED_HEADER`, `INVALID_BODY`); an integration that already has a broken value can still be switched off or renamed. Order: after `docs/plan-library.md`, before quality Q1
(`docs/plan-quality.md`), because form publish and library push warn about integrations that use removed
fields. Depends on form types (`start.*` / `end.*` namespaces, done).

## Agreed requirements
**One integration = one event.**
- "Send when…" becomes a **single choice**. Existing integrations keep their **first** event; the others are
  dropped (pre-production, demo data is reseeded).
- **Duplicate integration** button: copies everything into an unsaved editor (client-side, saved with the
  normal create call), **switched off**; Admin changes the event.
- An integration on the **booking form** fires for bookings of every inspection type, so it offers only
  `booking.*` events and only booking values (answers, facts, event); inspection / start / end answers,
  results and links exist only on integrations of a custom (inspection) form.

**Request**
- **Method:** POST (default), PUT, PATCH, GET, DELETE. GET and DELETE send **no body** (body section hidden).
- **URL:** values allowed **in the path only** (`https://crm.example.com/leads/[Booking ID]`); the scheme and
  host never contain a value (refused on save, so the address check still holds). Path values are
  URL-encoded. An empty path value fails the delivery with `missing_path_value`.
- **Query parameters:** rows key → value (text and / or picked values), URL-encoded.
- **Headers:** rows key → value (text and / or picked values), stored and shown **plain** (tokens included).
  Locked, refused on save: `Content-Type`, `Content-Length`, `Host`, `User-Agent`, `X-Vayu-Event`,
  `X-Vayu-Delivery`.
- **No signing.** `X-Vayu-Signature`, the per-integration secret and the Rotate button are removed; receivers
  authenticate us by a token Admin puts in a header.
- Empty value in a query parameter or header → that parameter / header is **left out**. A list value in a
  query parameter or header is **joined with commas**.

**Body (POST / PUT / PATCH)**
- **Two modes:**
  - **Standard:** today's JSON with the toggles (data, PDF link, image ZIP, video ZIP) and a **searchable field
    checklist** (all, or only the ticked fields) replacing the comma-separated box.
  - **Custom:** a **visual builder** of rows *output key → value*; objects (groups) nest freely; only what is
    mapped leaves. No raw template.
- **Lists come only from the system** as ready-made values: multi-choice answers, photo links of a photo
  field, Key Checks `[{name, result}]`, ratings `[{category, rating}]`, changed fields. No hand-built lists.
- **Types:** a value picked alone keeps its type (number, `true` / `false`, list, ISO date / time, text). Text
  mixed with values is always text; a list inside text is joined with `", "`. One per-row conversion:
  **Force text** (`2019` → `"2019"`, yes / no → `"Yes"` / `"No"`). A fixed value has a type: Text, Number,
  Yes / No.
- **Missing value → `null`**, key always present.
- **Deleted booking:** only event, delivery id, event time and Booking ID are filled; every other value is
  `null` (today's rule: nothing of a deleted booking leaves).
- Photo links per photo field are offered **in Custom bodies only** (signed, 7-day expiry, like the PDF link).

**Value picker** (one list for body, URL path, query and headers)
- Insert a value by typing `{{` or clicking **+ value**; a picked value shows as a **chip** deleted as one piece.
  No raw keys are typed.
- Groups:
  - **Answers:** Booking form, Start (check-in), Inspection, End (wrap-up), each under its own heading, so a
    key in two forms never collides.
  - **Booking & job facts:** Booking ID, **previous Booking ID** (`booking.updated` when the ID was edited,
    so a path like `/leads/[Previous Booking ID]` still reaches the receiver's record), internal id, type,
    stage, scheduled time, city, assigned expert name, created / submitted times, revision.
  - **Results:** overall rating, rating per category, Key Check results, failed Key Checks; always the
    **final** values (Ops overrides over computed: `Inspection.overrides` over `Inspection.scores`).
  - **Links & event:** PDF link, image ZIP link, video ZIP link, photo links per photo field, event name,
    delivery id, event time, changed fields.
- Lists fields of the form's **latest published version** only.
- **Hides values that can never be filled for the chosen event**:

| Event | Offered |
|---|---|
| `booking.created` | booking answers, booking & job facts, event |
| `booking.updated` | everything (a booking can change after submission) |
| `booking.deleted` | event, delivery id, event time, Booking ID |
| `inspection.started` | booking values + start answers |
| `inspection.submitted` | + inspection and end answers, results, photo links |
| `media.completed` | + image / video ZIP links |
| `pdf.ready` | + PDF link |
| `alert.conflict`, `alert.stuck_upload` | booking values + alert code |

**Preview** ("works in all cases")
- **Live** panel next to the editor (short debounce): method, final URL with query, headers, body, for both
  Standard and Custom, for the chosen event.
- Job: the **latest job of this form** by default; Admin can search another by Booking ID. When the form has
  no jobs, **sample values** are made up from each field's type and marked "sample".
- Building a preview **never sends** anything and **never builds a ZIP** (ZIP links shown as example links).
- The **Test** button sends the previewed request with **real** links (it may build a ZIP, the preview never
  does), plus `X-Vayu-Test: 1`.

**Fields that disappear**
- A mapped field missing from the latest published version: the integration list and the editor warn
  ("uses 1 field that no longer exists"); **form publish** and the **library push review** list the
  integrations affected, as a **warning, not a block**. At send time the value is `null`.

**Defaults written in (not asked)**
- Limits: 200 body rows, 20 headers, 30 query parameters, existing 1 MB body cap.
- Admin-only (`integrations.manage`, unchanged). Integrations are **not promoted** staging → production
  (URLs differ).
- Not in v1: date formats, value mapping (Petrol → P), hand-built lists, per-header secrets, signing.

## Accepted risks
| Risk | Decision |
|---|---|
| Header tokens stored plain, visible to every Admin | Accepted. Audit rows never hold values (checked: `audit.record` stores a sentence only). |
| No HMAC: receiver cannot prove the body came from us unchanged | Accepted. HTTPS in transit; token header is the proof of origin. |
| One event per integration means more integrations | Duplicate button. |

## Current state
- `Integration(form, name, url, secret, events[], include_data, include_pdf, include_image_zip,
  include_video_zip, fields[], template)`; `Delivery` holds metadata only (body rebuilt at send time).
- `webhooks.build_payload` (standard JSON), `render_template` (Jinja sandbox, text output, so a `"` in a value
  breaks JSON; `field.*` merges booking and inspection answers, start / end not reachable), `encode` sniffs
  JSON vs text, `sign`, `attempt` always POSTs.
- `RenderSample` previews only the template, always as `booking.updated`, ignores toggles and the field list;
  an empty template shows nothing.
- SSRF guard: `check_url` (scheme, host, public addresses) + `GuardedAdapter` peer check.

## Design
**Data model** (`apps/integrations/models.py`, one migration)
- Add `event` (CharField), `method` (CharField, default `POST`), `query` (JSON list of `{key, value}`),
  `headers` (JSON list of `{key, value}`), `body_mode` (`standard` | `custom`), `body` (JSON tree).
- Remove `events` (data migration keeps `events[0]`), `template`, `secret`.
- **One string syntax everywhere** (URL, query, headers, body values): text with `{{ref}}` tokens, e.g.
  `"Inspection for {{booking.customer_name}}"`, `url = "https://crm.example.com/leads/{{job.booking_id}}"`.
  A value that is **exactly one** `{{ref}}` keeps its type; anything else renders as text. Chips are only
  how the web shows tokens (label from the catalogue). One renderer for all four places.
- Body tree: `{"rows": [{"key": "customer", "rows": [...]}, {"key": "ref", "value": "{{job.booking_id}}",
  "as_text": false}, {"key": "source_id", "fixed": 12}]}`. `fixed` (Text, Number, Yes / No) is the only
  non-string value.

**Backend** (`apps/integrations/values.py`, new; `webhooks.py` reworked)
- `catalogue(form, event) -> [{group, ref, label, type, list}]`: the picker list, from the latest published
  version (booking form + start + inspection + end forms used by it) plus the fixed facts / results / links,
  filtered by the event table.
- `context(delivery, *, preview=False, sample=False)`: one object holding the job's values; ZIP links are
  example links when `preview`; sample values from field types when `sample`.
- `resolve(ref, ctx)`: typed value or `None`; `render_value(parts, ctx, as_text)`.
- `build_request(integration, ctx) -> (method, url, headers, body_bytes | None)`: standard body =
  today's `build_payload` (checklist applied); custom body = tree walk; query / headers drop empty values,
  join lists; path values URL-encoded, empty → `missing_path_value`; deleted booking → only the allowed refs.
- `broken_refs(integration) -> [ref]`; used by list / detail serializers, form publish warnings
  (`forms.services.publish` response) and `library_push` preview warnings.
- `attempt` uses `build_request`; `sign` and secret code removed; `check_url` runs on the final URL.
- Save validation: method in the list; event in `EVENTS`; host has no value; header names are HTTP token
  characters, locked names refused, CR / LF never allowed in a rendered header value: refused on save for
  typed text, **replaced by a space at send** for picked values (a multi-line answer would otherwise make
  `requests` raise `InvalidHeader`, a `RequestException`, and the delivery would be retried six times as
  `connection_error`); refs exist in `catalogue` (unknown → 400 with the row); limits.
- `broken_refs` warnings are appended to the existing publish `warnings` list (`forms/views.py`,
  `pdf_warnings`); the library push review calls the same function.
- Endpoints: `GET integrations/catalogue?form=&event=`; `POST integrations/preview {integration (unsaved),
  booking?}` → `{method, url, headers, body, sample: bool, broken_refs}`. `RenderSample` and
  `RotateSecret` removed. OpenAPI change is breaking (`[api-break-ok]` once).
- `scripts/webhook_receiver.py`: signature check and `--secret` removed; prints method, URL, headers, body.

**Web** (`pages/admin/Integrations.tsx` split into `pages/admin/integrations/`)
- Editor page (not a dialog): left = name, form, event (single choice), method, URL, query rows, header rows,
  body mode (Standard: toggles + field checklist; Custom: builder); right = live preview.
- `ValueInput`: chips, `{{` trigger, **+ value**, keyboard friendly; used by URL path, query, headers, body.
- `ValuePicker`: grouped searchable list from `catalogue`.
- `BodyBuilder`: rows with key, value, Force text, fixed value; add group / row; remove. Rows keep the
  order they were added (no reordering in v1; JSON key order rarely matters).
- `FieldChecklist` replaces the comma box; list warnings for broken refs; **Duplicate** on each row.
- **Main risk:** `ValueInput` (chips inside editable text) is the easiest piece to get wrong (cursor,
  delete, paste, IME). No new dependency; it stores the `{{ref}}` string, so a fallback to a plain input with
  `{{` autocomplete needs no backend change.

## Phases
### P1: backend (≈3 days), PR "feat(integrations): one event, request designer, preview"
Tests first.
- **T1.1** migration: `events[0]` kept, `template` / `secret` / `events` gone; existing integrations still
  send the standard body.
- **T1.2** catalogue: groups and labels per form; latest published version only; event table hides values;
  no key collision across booking / start / inspection / end; a booking-form integration gets only
  `booking.*` events and booking values.
- **T1.3** values: types kept for single refs (number, bool, list, ISO date); mixed text; list in text
  joined; Force text; fixed values typed; missing → `null`; photo links signed; deleted booking only allowed
  refs; ratings use Ops overrides; previous Booking ID filled after an ID edit.
- **T1.4** request: each method; GET / DELETE no body and no Content-Type; path values encoded; empty path
  value → `missing_path_value`; query / header empty left out, lists comma-joined; locked headers;
  CR / LF typed → 400, multi-line picked value → space, delivery succeeds; host with a value refused; SSRF
  check on the final URL.
- **T1.5** preview: standard and custom, every event, chosen job / latest job / sample; no ZIP built, nothing
  sent, no Delivery row; Test sends the same request with real links and `X-Vayu-Test`.
- **T1.6** broken refs: listed on integration, warned on form publish and library push preview, sent as
  `null`.
- **T1.7** chore: 100% gate on `apps.integrations` kept (incl. `values.py`); `openapi.yaml` regenerated;
  `docs/integrations.md` (receiver guide without signing, token header example).

### P2: web (≈3 days), PR "feat(web): integration request designer"
- **T2.1 (unit/component):** `ValueInput` chip insert / delete / paste / `{{` trigger and string round-trip;
  picker search and groups; builder nesting, Force text, fixed values; method hides body for GET / DELETE;
  locked header message; checklist; broken-ref warning; duplicate opens an unsaved inactive copy.
- **T2.2 (browser):** build a PATCH with the Booking ID in the path, a token header, a query value and a nested
  custom body with a photo list → preview matches → Test reaches `scripts/webhook_receiver.py` with the same
  request; sample preview on a form without jobs; remove a mapped field in a new form version → warning on
  publish and on the integration, value `null`.
- **T2.3:** docs (`docs/local.md` walk-through, `README`, `plan.md` Amendments, `REQUIREMENTS.md` §8: one
  event per integration, no HMAC, visual builder replaces templating); demo seed gets one custom-body
  integration.

## Done when
Backend suite + gates, Vitest, full Playwright and the local-stack check green in CI; the T2.2 journey passes
in a browser against the local receiver; `REQUIREMENTS.md` and `plan.md` Amendments updated.
