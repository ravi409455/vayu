# Plan: code quality fixes (from the principal-architect review, 2026-11)

Status: **mostly done** (2026-11-25; see "Status 2026-11-25" at the end for what is left).
Open points closed 2026-11-23. Source: the whole-codebase review (logging, documentation, comments,
SOLID, optimisation, reuse, modularity, structure, clean code, security, long-term maintenance). Every
item below was measured in the code at `891ec08`; numbers are quoted so progress can be checked.
**Re-measure every number when Q1 starts**: form types (`1d2de51`) and the library plan land first and
change them.

**Deployment-related items are deferred** (the product is still under development) and listed at the end.

## How this fits with the other plans
The form-types, library and profile plans (`docs/plan-form-types.md`, `docs/plan-library.md`,
`docs/plan-profile.md`) touch many of the same files. To avoid doing work twice:

| Order | Work | Why here |
|---|---|---|
| done | Form-types plan | Already built (`975e815`, `1d2de51`). |
| 1 | **Library plan** | In progress; Q2 rewrites code it is changing, so it lands first. |
| 2 | **Q1 guardrails** (lint, typing, scanning) | Cheap; stops new problems while the rest changes. Re-measure here. |
| 3 | **Q2 structure** (errors, stale guard, devtools app, cycles) | After the library so its new code is cleaned once. |
| 4 | **Q3 field-type registry** | Register the `form_choice` type that form types added instead of the `if` chains. |
| 5 | **Q4 logging** | The model (booking / start / end / custom) is final. |
| 6 | **Q5 performance** | Independent; small. |
| 7 | **Profile plan** | |
| 8 | **Q6 API + integration docs** | After the API's last planned break (form types) so nothing is written twice. |
| 9 | **Q7 user + architecture docs** | After the screens settle (library editor, profile). |

Estimate for this plan: **about 8 days** spread across the sequence above.

---

## Q1: guardrails (≈1 day)
Today: Ruff runs only `E, F, I, B, UP, DJ`; mypy is not strict; the web app has **no ESLint or Prettier**;
CI has **no dependency or code security scanning**.

- **Q1.1 Ruff rules:** add `S` (security, with `S101` off in tests), `C90` (complexity, max 12 with a
  per-file allow list for the 13 current offenders until Q3 removes them), `SIM`, `RET`, `PIE`, `PL`
  (selected: `PLR0911/0912/0915` with sane limits), `T20` (no `print`). Fix or annotate every hit.
- **Q1.2 mypy:** turn on `disallow_untyped_defs` for `apps/*/services.py`, `apps/*/library*.py`,
  `apps/integrations/*`, `apps/core/*` in Q1 (new code is typed). **Decided:** every other module becomes
  strict during Q2-Q5 (each step types what it touches) and the **whole backend is strict by the end of
  this plan**, enforced in CI.
- **Q1.3 Web lint and format:** ESLint (typescript-eslint, react-hooks, jsx-a11y) + Prettier with the
  repo's current style; `npm run lint` in CI. Fix the existing `eslint-disable` comments properly where
  possible (`react-hooks/exhaustive-deps` in the wizard and builder).
- **Q1.4 Dependency and code scanning in CI:** `pip-audit` (uv export) and `npm audit --audit-level=high`
  as CI steps; **Decided:** GitHub **security alerts only** (Dependabot security updates on, no routine
  version-update PRs; big upgrades are done deliberately); Ruff `S` covers basic static security checks.
- **Done when:** CI runs all of the above and is green; the allow list for complexity is the only
  exception and shrinks in Q3.

## Q2: structure and reuse (≈1.5 days)
Today: the error helper exists **three times** (`bookings.services.err`, `forms.library.bad`,
`forms.promote.bad`) and **five other apps import `err` from `bookings.services`**; the "someone changed
this first" check is **copied six times**; `core` depends on accounts, bookings, forms and media (it should
depend on nothing); **50 function-local imports** hide cycles (bookings ↔ media, forms ↔ reports); request
validation lives in views (`integrations/views._clean_integration`, helpers in `forms/views.py`, 466 lines).

- **Q2.1 One error helper:** `apps/core/errors.py` gets `fail(code, message, status=400, **extra)`; remove
  `err` / `bad` copies; update imports. One test that every raised `CodedError` has a code from a single
  `ERROR_CODES` list (also feeds the error catalogue in Q6).
- **Q2.2 One stale-edit guard:** `core.concurrency.check_row_version(obj, sent, code, *, last_change=None)`
  used by bookings, inspections, form drafts, PDF drafts (and the library editor later).
- **Q2.3 `devtools` app:** move `seed_demo`, `demo_forms.py`, `e2e_reset`, `local_bucket`, `bench_pdf`
  and `core/testing.py` into `apps/devtools`, installed only by the local, test and e2e settings. `core`
  then imports nothing from other apps (add an import-linter contract or a small test that enforces it).
- **Q2.4 Break the cycles with events:** media completion → bookings and reports reacting to forms use the
  existing `core.events` (subscribe in `AppConfig.ready`) instead of function-local imports; the remaining
  function-local imports are listed in a test so they cannot grow silently.
- **Q2.5 Thin views:** move integration body validation into `IntegrationSerializer`, form-builder helpers
  out of `forms/views.py` into `forms/services.py`; views only parse, call a service, and shape the reply.
- **Q2.6 Web reuse:** replace the **11** hand-written master-list fetches with the existing `useLabels` /
  a `useListItems(key)` hook; move the **80** inline `style={{…}}` objects that repeat into CSS classes
  (keep genuinely dynamic ones); split `pages/ops/Booking.tsx` (326 lines) into one file per tab and
  `ui/FormRenderer.tsx` (258 lines) into renderer + inputs + media field.
- **Done when:** one error helper, one stale guard, `core` has no outgoing app imports, the local-import
  list is fixed and short, no view holds validation logic, the two big web files are split; all suites green.

## Q3: field-type registry (≈2 days, after the library plan)
Today: `fieldtypes.clean_answer` has **complexity 53 over 127 lines**, `validate_config` **41 over 86
lines**; adding one field type means editing about six places (config check, answer cleaning, PDF display,
scoring, web renderer, web field editor, web type list). This breaks the open/closed principle.

- **Q3.1 Backend:** `apps/forms/fieldtypes/` package: a `FieldTypeSpec` per type (`config_keys`,
  `validate_config`, `clean`, `display`, `is_media`, `is_choice`) in one registry; `validate_config` and
  `clean_answer` become one-line look-ups; `reports/context.display` and scoring ask the registry.
  Behaviour must not change: the existing answer / config tests are the safety net (run before and after).
- **Q3.2 Web:** one `fieldTypes` registry (label, group, default config, input component, editor panel)
  used by `FormRenderer`, `FieldEditor`, the add-field dialog and `lib/fieldTypes.ts`.
- **Q3.3** Remove the complexity allow-list entries for these functions (Q1.1).
- **Done when:** adding a test-only field type needs one backend spec and one web entry (proved by a test
  that registers a fake type); every existing test passes unchanged.

## Q4: logging (≈1.5 days, after the form-types plan)
Today: **five** application log calls in about 9,000 lines; Celery workers log `request_id: "-"`; no rule
says what must never be logged.

- **Q4.1 Helper:** `core.log.event(name, **fields)` writing structured JSON (`event`, `request_id`, `user_id`,
  `booking`, `inspection`, durations), never free text with values in it.
- **Q4.2 Request ID into jobs:** pass the request ID as a Celery header and restore it in a
  `task_prerun` signal; tasks also log their task ID.
- **Q4.3 Events to log** (each with a test that it fires, and that no personal data is in it):
  sign-in success / failure / lockout (**decided:** a failure logs the user's internal id when the account
  exists, otherwise `unknown user`, plus IP and reason; the typed username is never written, since it can
  be a mistyped password), device registered / revoked, password changed; permission refused
  (view name, permission key); booking created / stage changed / cancelled / reassigned / conflict;
  submission accepted / rejected (error codes only); upload initiated / verified / failed (reason code);
  ZIP built (size, duration); PDF render start / done (duration, pages) / failed (reason); webhook delivery
  result (status, attempt, duration); API key used / refused (prefix only); library push (forms count).
- **Q4.4 Policy:** `docs/logging.md`: levels per environment, event names, and the never-log list (names,
  phone numbers, addresses, answers, passwords, tokens, API keys, signed URLs, **typed usernames on failed
  sign-in**). A test runs a full journey
  with log capture and asserts none of the seeded personal values appear in any log line.
- **Done when:** every event above is emitted and tested; worker logs carry the originating request ID.

## Q5: performance (≈0.5 day)
Measured: lists are fine (bookings list = **9 queries** for 5 or 40 bookings). Not fine:

- **Q5.1 Search:** **50 queries per request** regardless of data size: `searchable_stages()` recomputes
  field levels for every form × stage. Published versions never change, so cache levels per
  `(version_id, role)` in process memory (bounded `lru_cache`) and per request. Target: ≤ 12 queries;
  a test pins the number.
- **Q5.2 Dashboards:** counted in Python over every booking in range; use the database
  (`TruncDay/TruncWeek/TruncMonth` + `Count`, grouped). A test compares old and new output on the same data.
- **Q5.3 Indexes:** bookings have no index on `stage`, `inspection_date`, `city`, `inspection_type`,
  `created_at` (ordering); add them in one migration. Text search over four columns stays `icontains` for
  now; note `pg_trgm` GIN indexes as the next step when bookings pass ~50k.
- **Done when:** query-count tests for search, list and dashboards are in the suite.

## Q6: API and integration documentation (≈2 days, after the form-types plan)
Measured: of **130** documented operations, **114** have no description, **73** say they return nothing,
**37** write endpoints show no request body; the generator prints **99 warnings**. `docs/integrations.md`
is 39 lines.

- **Q6.1 Real schemas, external surface first:** request / response serializers (or `extend_schema`) for
  the API-key endpoints (`/ext/*`), integrations, webhooks test / deliveries, report / verify, media upload
  flow; then the rest. Summaries and descriptions on every operation; tags per area; examples.
- **Q6.2 CI:** fail on generator warnings (`spectacular --fail-on-warn`) once fixed, so it cannot regress;
  the existing drift and oasdiff checks stay.
- **Q6.3 Integration guide** (`docs/integrations/`): authentication with API keys and scopes; every
  `/ext` call with request and response examples; bulk semantics; pagination; error format and the **error
  code catalogue** (generated from `ERROR_CODES`, Q2.1); webhooks: every event with a JSON schema and an
  example payload, headers, **signature verification code in Python and Node**, retries and idempotency
  (`X-Vayu-Delivery`), test button; rate limits; **versioning and deprecation policy** and a **changelog**.
- **Q6.4 Comments and docstrings:** module docstring on every module (today 36 of 92), docstrings on
  public service functions (today 81 of 408) and on models (today 34 of 211 classes); Ruff `D` rules for
  `services.py` and models only, so it stays useful rather than noisy.
- **Done when:** Swagger shows request and response bodies for every operation, no generator warnings, the
  guide lets an external developer integrate without asking us (checked by following it end to end in a test).

## Q7: user and architecture documentation (≈1 day, after the library and profile plans)
- **Q7.1 User guides** (`docs/guides/`): Admin (users and roles, master lists, form builder, library and
  "update everywhere", PDF designer, integrations, API keys, export / import), Ops (bookings, job board,
  reviewing and editing, ratings, reports, problems, dashboards), Expert (jobs, the inspection steps,
  photos and uploads, what offline will mean on Android). Short, task-based, with screenshots taken by the
  Playwright journeys so they stay current.
- **Q7.2 Architecture:** `docs/architecture.md` (apps and their allowed dependencies, request and job flow,
  events, data model overview, where rules live); ADRs for the decisions already made (JsonLogic and shared
  vectors, WeasyPrint, direct-to-storage uploads, pinned versions, library ownership, form types); move
  the long amendment log out of `plan.md` into ADRs and a changelog.
- **Q7.3 Contributor docs:** `CONTRIBUTING.md` (setup, tests, gates, commit style, how to add a field type
  / an event / an endpoint) and `SECURITY.md` (how to report, what is in scope).

## Security items that are not deployment (inside the plans above)
- Scanning (Q1.4), security lint rules (Q1.1), never-log policy and test (Q4.4).
- **Decided: no per-API-key rate limit** (as originally required). Accepted risk: a runaway or leaked key
  can slow the system; the response is to revoke the key (immediate). Documented in the integration guide.
- **Decided: keep 60-day mobile refresh tokens without rotation.** Accepted risk: a copied token works
  until the device is revoked or the token expires; device revocation (and sign-out on password change) is
  the control.

## Deferred (deployment-related, do before launch)
- Serve the web app in production (static build) behind Caddy, with security headers: Content-Security-Policy,
  `frame-ancestors`, Permissions-Policy, Referrer-Policy, HSTS for the web host.
- Exclude dev tooling from the production image (after Q2.3 it is one `INSTALLED_APPS` difference; the
  image build should also leave out `apps/devtools`).
- Encrypt webhook signing secrets at rest (envelope key from the environment).
- Web Sentry (needs the DSN), uptime checks, alerting on error rates and stuck jobs.
- Runbooks: deploy, roll back, backup and restore drill, incident checklist, secret rotation.
- Staging load test and PDF benchmark (`docs/benchmarks.md`), CORS check on the real domains.

## Done when (whole plan)
All Q items closed, CI enforces lint / type / scan / schema / query-count / log-privacy checks, and the
review numbers above are re-measured and recorded here.

## Status 2026-11-25
Done (fix round + quality branch): Q1.1 (Ruff `S` and `C90` max 12 with a per-file allow list of 18
files; `SIM`/`RET`/`PIE`/`PL`/`T20` not added), Q1.2, Q1.3 (jsx-a11y, Prettier), Q1.4, Q2.1
(`core.errors.fail`), Q2.2 (`core.concurrency.check_row_version`), Q2.3, Q2.4, Q2.5
(`IntegrationSerializer`, form-builder saves in `forms/services.py`), Q2.6 (`useListItems`,
FormRenderer split; `pages/ops/Booking.tsx` split earlier), Q3, Q4 (`core.log.event`,
`docs/logging.md`), Q5 (search 90 → 12 queries, pinned by a test), Q6.2 (0 generator warnings,
`--fail-on-warn` in CI), Q6.3 (`docs/integrations/`), module docstrings on every module, Q7.1
(`docs/guides/`), Q7.2 `docs/architecture.md`, Q7.3 `CONTRIBUTING.md`.

Left:
- Q1.1: `SIM`, `RET`, `PIE`, `PL`, `T20`; the C901 allow list (18 files) to shrink.
- Q2.6: repeated inline `style={{…}}` objects into CSS classes.
- Q6.1: real request / response schemas and descriptions on every operation (many still say
  "any object"); Q6.3's end-to-end test that follows the guide; Q6.4 Ruff `D` rules and
  docstrings on public service functions and models.
- Q7.1 screenshots from the Playwright journeys; Q7.2 ADR files and moving the amendment log out of
  `plan.md` (the decisions are listed in `docs/architecture.md`); Q7.3 `SECURITY.md` (a short note
  is in `CONTRIBUTING.md`).
- Webhook signature code (Q6.3) does not apply: requests are not signed since 2026-11-24 (token
  header instead), so the guide shows token checks.
