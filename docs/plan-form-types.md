# Plan: form types (booking / start / end / custom)

Status: **planned, not started** (re-reviewed after the builder redesign and the check-in/wrap-up work). **Estimate now ≈ 6 days** (was 4–5: the recent changes added more `ops` / `kind` touch points). Do this one **first**: the library plan and the profile plan build on it.
Order of the three plans: **form types (this) → library + form import (`docs/plan-library.md`) → profile
(`docs/plan-profile.md`)**.

## Agreed requirements
- One field, **`type`**, with four values: `booking`, `start`, `end`, `custom`. It replaces `kind`
  (`booking` / `ops` / `inspection`). "System form" means booking, start or end.
- **System forms** exist from install, **exactly one of each**, and cannot be created, deleted or
  deactivated. Admins build out their content (and Admins only).
- **Custom forms** are what PDI, PPI, EV… become. Admins create as many as they like.
- The single check-in & wrap-up ("ops") form is **split**: **start** = today's check-in, **end** = today's
  wrap-up. (The parent work already marks these as page slots `before` / `after`; the slot goes away.)
- Each custom form **version** has two switches: **"begins with the start form"** and **"ends with the end
  form"**. Set in a draft, frozen on publish, carried by export / duplicate / library pushes.
- Answers are named **`start.*`** and **`end.*`** (replacing `ops.*`) in rules, PDF templates, the API,
  webhooks and stored data.
- When the expert starts a job, the **versions of the custom, start and end forms are pinned together**.
- **Publish check:** a custom form that uses `start.*` / `end.*` in a rule, Key Check, rating or PDF row
  but does not include that form is **blocked** with a clear message.
- The hidden link `inspection_type` stays on bookings, **auto-filled with the custom form's key**; the
  "inspection type" master list and picker are removed from the UI. The booking dropdown lists the active
  custom forms **by name**.
- The API change `kind → type` is **one deliberate breaking change** (pre-launch, no outside users).

## Current state (re-checked against the code at `3a3f2c0`)
- `Form.kind` (`booking` / `ops` / `inspection`), `FORMS = ("booking","ops","inspection")` in
  `apps/forms/rules.py` and `web/src/rules/rules.ts`, `shared/rule-vectors/SCHEMA.md`. About 80 backend
  references to `kind`; `ops` appears in `access.py`, `services.py`, `models.py`, `fieldtypes.py`, `rules.py`,
  `serializers.py`, `system_fields.py`, `promote.py`, `bookings/*`, `reports/*`, `scoring/service.py`,
  `media/services.py`, the seeds (`seed_demo`, `demo_forms.py`, `e2e_reset`), the web renderer, wizard,
  builder and tests.
- One `ops` form. `create_form` special-cases it: two pages **Check-in** (`slot="before"`, `gate=True`) and
  **Wrap-up** (`slot="after"`), filled from `SYSTEM_FIELDS["ops"]` entries that carry `page` / `section`
  (`checkin_gps`, `checkin_time`, `selfie`, then `taking_payment`, `payment_mode`, `payment_amount`,
  `payment_screenshot`). **Every** inspection goes through both.
- `Page.gate` (a page that blocks "Next" until its required fields are filled), `Page.slot`, and
  `Form.submission_roles` (which roles may see an inspection form's submissions; applied where
  `kind == INSPECTION`, `hidden_inspection_forms()` blanks hidden forms in the API, media, search, reports)
  now exist.
- `stamp_auto()` in `bookings/submissions.py` server-stamps `config.auto` date / time / GPS fields for the
  `inspection` and `ops` parts. `FormAsset` images (e.g. a payment QR code) travel in export bundles.
- `ops_version()` returns the **latest published** ops version at submit time: **not pinned** (a hole this
  plan closes). Inspections pin only the custom form's version.
- `Inspection.answers = {"inspection": …, "ops": …}`; PDF templates and rules use `ops.<key>`.
- Export bundles are still `SCHEMA = 1` although they already carry `gate`, `slot`, `submission_roles` and
  `assets` (added without a bump); v2 below is the honest bump.

## Design
**Data**
- `Form.type` (choices above) replaces `Form.kind`. Constraints: `booking`/`start`/`end` each at most one
  row and always active; `custom` unlimited. `inspection_type` (hidden) = form key, set on create and never
  edited; unique-active constraint stays (keys are unique, so it always holds).
- `FormVersion.use_start`, `FormVersion.use_end` (booleans, draft-editable, frozen once published). **Default
  true** for new and migrated custom versions (today every inspection goes through both).
- `Inspection.start_version`, `Inspection.end_version` (nullable FKs to `FormVersion`), set at start next
  to `form_version`; null when the version opts out.
- `Inspection.answers = {"inspection", "start", "end"}`. Booking answers unchanged.
- `Page.slot` removed (start form = before, end form = after); `Page.gate` stays (the start form's check-in
  page keeps `gate=True`). `create_form` loses its `ops` special case: `SYSTEM_FIELDS` gets `start` and `end`
  entries (start: `checkin_gps`, `checkin_time`, `selfie` on page **Check-in**; end: `taking_payment`,
  `payment_mode`, `payment_amount`, `payment_screenshot` on page **Wrap-up**), and `custom` keeps
  `chassis_no`.
- `Form.submission_roles` applies to **custom** forms only (the `kind != INSPECTION` checks become
  `type != custom`); start / end data of an inspection is visible exactly to the roles that may see the
  custom form's submissions (a hidden custom form hides its start / end answers too).
- New field type **`form_choice`** for the booking's system field `inspection_type`: valid values are the keys
  of active custom forms that have a published version; the web renders a select of form **names** from
  `GET forms?type=custom`.

**Rules and engine**
- `FORMS = ("booking","start","end","inspection")` in Python and TypeScript; `SCHEMA.md` and
  `form_vectors.json` updated (spec.form values, data shape, hidden-field rule); eval/robust vectors only use
  variable names so they need a check, not a rewrite. The Kotlin adapter (Phase 13) must pass the same
  vectors.
- A one-time data migration rewrites `ops.<key>` → `start.<key>` / `end.<key>` everywhere a rule can live:
  field `show_if` / `required_if`, derived-field rules, Key Checks, section/page `show_if`, **library
  definitions**, **PDF template rules and row refs**. Which side a key goes to is decided by which form
  owns the key (system keys known; other keys by the page slot they were on).

**Publish validation** (extend `validate_version` and PDF `publish`): reference to `start.*` / `end.*` while
`use_start` / `use_end` is false → `PUBLISH_BLOCKED` with the path. PDF template: `_known_keys` knows
`start` / `end` keys; a row referencing them needs the form to include them.

**Start flow (API)**
- `POST bookings/<id>/start` pins `form_version`, `start_version`, `end_version` and returns
  `{form, start_form, end_form}` (replaces `ops_form`; each null when not used).
- `submit` validates `{inspection, start, end}` against the **pinned** versions; field access (role × stage)
  unchanged. Media completion waits for media referenced in all three parts (`expected_media`).
- `stamp_auto` runs per part (`inspection`, `start`, `end`) against the pinned versions.
- Scoring, reports (`context.py`), search, ext API and webhooks read start / end answers from the pinned
  versions. Webhook `data` keeps `booking` + `inspection` (start/end only when full data is on, new keys).

**System forms**
- `ensure_system_forms()` creates the three forms (draft v1 with their system fields) in a data migration
  and on `seed_*`; `POST forms` accepts only `type = custom`; `PATCH`/`DELETE` refuse type change, deactivate
  and delete for system forms; the Forms list shows **System (3)** and **Custom**.
- Export/import (Promote) works for all four types; a bundle imports only into a form of the same type.

**Export format v2** (`apps/forms/promote.py`, bump `SCHEMA` to 2; keeps `gate`, `submission_roles`, `assets`; drops `slot`): `form.type`, version `use_start`/`use_end`; the importer
still reads **v1 custom (`inspection`) bundles** (including those with `gate` / `submission_roles` / `assets`) (maps `kind: inspection → custom`, rewrites `ops.` refs with
the system-key map; an unknown `ops.` key fails clearly). **v1 `ops` bundles are rejected** with a message
(re-export after this change).

**Web** (files that change: `pages/expert/Job.tsx`, `pages/admin/FormBuilder.tsx`,
`pages/admin/builder/Inspector.tsx` and `AddDialogs.tsx`, `pages/admin/FieldEditor.tsx` (its `kind` prop),
`pages/admin/Forms.tsx`, `pages/ops/Booking.tsx`, `lib/useTrees.ts`, `lib/useChoices.ts`, `lib/formSpec.ts`,
`ui/FormRenderer.tsx`, `rules/rules.ts`, `api/types.ts`, the demo seeds, and the e2e specs `builder`,
`camera`, `j1`, `j3`, `e2e-local`)
- Wizard: steps = start pages (if pinned) → custom pages → end pages (if pinned) → review; the page-title /
  slot logic is deleted; `gate` pages still block "Next", including a gated start page. Ops `InspectionTab`
  shows start / end sections only when the inspection has them pinned.
- Builder: type badge; a **Form settings** panel on a custom version with the two switches (disabled on
  published); "New form" creates `custom` only (no type picker); system forms show no delete / deactivate.
- Booking form: `inspection_type` renders as the form-name select. Remove the inspection-type master list
  from the Master lists screen (delete the list if nothing else uses it).
- Rule field choices offer `start.*` / `end.*` only when the version includes them.

**API / CI**
- `kind` → `type` in forms, promote, ext API and web types; regenerate `backend/openapi.yaml`.
- The oasdiff step in CI allows a deliberate break when the commit message contains `[api-break-ok]`
  (one-line change to the existing step); use it once for this change.

## Phases
### P1: backend model + data (≈2 days), PR "feat(forms): form types, start/end forms, pinned versions"
Tests first.
- **T1.1** `type` constraints: one active booking/start/end; create custom only via API; system forms refuse
  delete / deactivate / type change; `ensure_system_forms` is idempotent.
- **T1.2** data migration (build a pre-migration fixture: ops form with `before`/`after` pages, an
  inspection form, bookings with `ops` answers, a PDF template and a library item using `ops.` refs) →
  assert forms, answers, rules, library and PDF refs all converted; running twice is harmless.
- **T1.3** versions: `use_start/use_end` editable on draft, 409 on published; copied by `create_draft`,
  promote, duplicate; default true.
- **T1.4** pinning: start pins all three versions; publishing a newer start/end form afterwards does not
  affect a started job; an opted-out form pins none and submit ignores / refuses start/end answers.
- **T1.5** publish validation (rules, Key Checks, PDF rows, ratings) blocks `start.*` / `end.*` when not
  included; passes when included.
- **T1.6** engine: `FORMS` change; all shared vectors pass in Python; `form_choice` validation.
- **T1.7** visibility: a role left out of a custom form's `submission_roles` sees none of that inspection's
  start / end answers (API, media, search, reports); `type != custom` forms have no `submission_roles`.
- **T1.8** auto-stamping: `config.auto` fields in start / end forms are stamped per part from the pinned versions.

### P2: backend behaviour (≈2 days)
- **T2.1** submit / edit / scoring / media completion / search / dashboards use pinned start/end versions
  and `answers.start|end`; field-access levels per form; Ops edits after submit.
- **T2.2** reports + PDF templates (`start.` / `end.` refs, blank when not used), verify page unchanged.
- **T2.3** promote v2 + v1 importer rules above; ext API, webhooks (new `data` keys), demo seeds and
  `e2e_reset` rebuilt on the new model.
- **T2.4** `[api-break-ok]` CI tweak, regenerate `openapi.yaml`, update gates (rules, bookings+access,
  scoring, promote, reports, media must stay at 100%).

### P3: web (≈2 days)
- **T3.1 (unit):** rules adapter + vectors; `formSpec` (start/end namespaces, gaps across all three forms);
  wizard step builder (start/end on/off, empty form skipped, order); builder panel (switches disabled when
  published); booking `form_choice` select; Forms list grouping and "no delete" for system forms.
- **T3.2 (browser):** expert journey with start + custom + end, one with both off (no payment step); Admin
  flips a switch → new version → old job still uses the pinned one; publish blocked message when a rule
  uses `end.*` while the end form is off; booking dropdown shows form names; J1–J5 and the local-stack
  check updated.
- **T3.3:** docs (`REQUIREMENTS.md` §3/§11, `docs/integrations.md`, `docs/local.md`), `plan.md` Amendments.

## Risks and answers
| Risk | Handling |
|---|---|
| Breadth: rename touches rules, PDF, API, webhooks, scoring, media, auto-stamping, submission visibility | Migration test with a realistic fixture; grep-based checklist of every `ops` reference; keep the 100% gates. |
| A rule hides inside data we forget to rewrite | The migration walks every JSON column that can hold a rule (list in T1.2); a final test scans all stored rules for `ops.`. |
| Phone offline contract changes (Android not built yet) | Pinned versions + start/end forms in the `start` response are the Android contract; write it in `docs/` before Phase 13. |
| Existing local/demo data | Migration converts it; `scripts/local.sh reset` is the fallback. |
| Breaking the frozen API by mistake | One planned break, flagged with `[api-break-ok]`; everything else must stay additive. |

## Assumptions to confirm before starting
1. Default of both switches is **on** for new and existing custom forms.
2. Exactly **one** start and **one** end form (no per-custom start/end variants for now).
3. An included start or end form with **no fields** is skipped in the wizard.
4. v1 **ops** export files are rejected; v1 **inspection** files import.
5. System forms are exportable and importable (same type only).

## Done when
Backend suite + all gates, Vitest, full Playwright and the local-stack check pass in CI; a stored-rule scan
finds no `ops.`; `openapi.yaml` regenerated; the three journeys above pass; `plan.md` Amendments updated.
