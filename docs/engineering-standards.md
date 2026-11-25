# Engineering standards: how every change is made

For every person and every Claude session that changes this repo. Read it before the first edit.
It is the short form of what the full review (`docs/review-report-2026-11-25.md`) and the fix round
(`docs/plan-fixes.md`) settled. If a rule here and the code disagree, fix the code or ask; don't
copy the old pattern.

## 1. Before you start
- Read the requirement: `REQUIREMENTS.md`, `docs/android-requirements.md`, the plan for the area.
  A decision written there is not reopened in code.
- Read the code you will touch **and its callers**. Look for an existing helper before writing one.
- Work on a branch from the latest integration branch (`main`, or the branch the lead names). One
  topic per branch. Never commit straight to `main`.
- A change in behaviour another layer depends on (API field, error code, rule) lands **backend
  first**, with the contract written down, then web and Android.

## 2. Rules for every layer
1. **A test first.** A behaviour fix starts with a test that fails without it. Visual and
   accessibility changes are checked with screenshots / axe instead.
2. **Fix the cause, once.** Put the fix where every caller passes through, not in one caller.
3. **The smallest change that is correct.** No new abstraction, option or dependency "for later".
   Standard library and what is already installed come first.
4. **One definition of each rule.** Stage words, statuses, media kinds, "is this answered", field
   types, error messages: one place per layer, shared test vectors across layers
   (`shared/rule-vectors/`). Never retype a list.
5. **No silent failure.** Never swallow an error. Every refusal has a code and a sentence a person
   can act on. A retry must be safe to repeat (same request id → same result).
6. **The server enforces every rule.** Screens only hide; permissions, limits and stage rules are
   checked on the server, per object.
7. **Privacy.** No customer value in logs, crash reports, push messages, URLs or audit text. What
   leaves the system is listed in the plan. Sign-out clears what the device holds.
8. **Comments say why**, not what. Update the comment when the code changes. No commented-out
   code, no TODO without an owner and a reason (a deliberate shortcut is marked `ponytail:` with
   its limit and when to upgrade).
9. **Words on screen:** experts read "lead", Ops and Admin read "booking", nobody reads "job".
   Plain words, no codes or raw keys. Use the agreed stage words.
10. **Docs move with the code:** `REQUIREMENTS.md` when behaviour changes, the plan's status line
    when work is done, `openapi.yaml` when the API changes.

## 3. Backend (Django)
- Business rules live in services (`apps/<app>/services.py` and friends); views only parse,
  call and answer. No rule in a serializer or view.
- Every view declares its permission (`perm(...)`); scoped permissions filter the queryset
  ("own"); hidden forms / fields are respected on reads **and** writes.
- State changes on a booking or inspection run in a transaction with the row locked
  (`select_for_update`), and edits carry `row_version`. Stage changes go through the stage rules.
- Work for after the commit (Celery tasks, events that tasks read) goes through
  `core_tasks.after_commit`. Tasks are safe to run twice and have a time limit.
- Errors: `err("CODE", "Sentence.", status)` / `CodedError`; a new code is added to the documented
  list. Use the enums for stages, statuses and event names, never a bare string.
- Queries: no query per row. A list endpoint gets a query-count test. Filters used in lists have an
  index.
- Migrations: reversible, or the reason is written in the migration and the runbook. Data
  migrations don't import app code. Never edit an applied migration.
- Outgoing calls (webhooks, storage, push): timeouts, the address guard, no secrets in logs.
- Types and style: `ruff` clean, `mypy apps vayu` clean, lines ≤ 100, type hints on new functions.
- Tests: pytest, real database, API-level where possible. The modules with a 100% branch-coverage
  gate (see `.github/workflows/ci.yml`, job `backend-gates`) stay at 100%.

## 4. Web (React + TypeScript)
- `strict` TypeScript, no `any`, no `@ts-ignore`. ESLint clean with zero warnings.
- Server data only through `api()` and TanStack Query; keys come from the query-key module;
  every mutation invalidates what it changed.
- Every query shows its **loading, empty and error** state; an action is disabled while it is
  being sent (no double submit); a 409 conflict is shown, never overwritten.
- Pure logic lives in `src/lib` with unit tests; a page file holds one page; a component over
  ~300 lines is split. Pages don't import other pages.
- Accessibility: every control has a name, dialogs trap and return focus and close on Escape,
  focus is visible, errors are tied to their inputs, text meets contrast in light and dark.
- Layout: staff pages work from 768 px, customer pages from 375 px.
- Dates and "today" are India time. No customer data in `localStorage` beyond drafts, which
  sign-out clears.
- Tests: Vitest + Testing Library for behaviour (by role and text, not implementation), Playwright
  for journeys (its own ports and database).

## 5. Android (Kotlin + Compose)
- Screens draw; view models hold state, loading and actions; `core/` holds data, rules and sync
  and imports no UI.
- Server replies are decoded into typed `@Serializable` models in the API layer. Raw JSON only
  where the shape is the Admin's form (answers, scores, Key Checks).
- No disk, network, hashing or bitmap decoding on the main thread. No `!!` on data that can be
  missing. No `runCatching` around suspend calls (use the cancellation-safe helper).
- Offline first: everything the expert enters is saved at once; sending goes through the outbox
  and WorkManager; every request carries its client id so a retry is safe; a refusal from the
  server is shown and never blocks unrelated work.
- Sign-out refuses while unsent work exists, then wipes drafts, files, caches and tokens. Tokens
  stay sealed with the Keystore.
- Text follows font scale; back always goes somewhere sensible; a denied permission offers the
  way to Settings.
- Tests: unit tests for rules and the outbox, Robolectric for flows, Roborazzi for screens (a new
  reference image is recorded on purpose, never to hide a difference). Tests wait for the screen to
  settle; no fixed sleeps.

## 6. Verification checklist (before you say "done")
Run what applies to the layers you touched; all must pass.

**Backend** (`cd backend`)
- [ ] `uv run ruff check .`
- [ ] `uv run mypy apps vayu`
- [ ] `DJANGO_SETTINGS_MODULE=vayu.settings.test uv run python manage.py makemigrations --check --dry-run`
- [ ] OpenAPI in sync: `… manage.py spectacular --file /tmp/o.yaml && diff openapi.yaml /tmp/o.yaml`
- [ ] `uv run pytest -n 4 --cov --cov-fail-under=85` (use your own `DB_NAME` and `COVERAGE_FILE`
      when other runs share the machine)
- [ ] the 100% gates for the modules you touched (commands in `ci.yml`, job `backend-gates`)

**Web** (`cd web`)
- [ ] `npx tsc --noEmit` · `npm run lint` · `npx vitest run`
- [ ] `npx playwright test` (affected specs at least; own ports / database)
- [ ] the page tried by hand: loading, empty, error, keyboard, 768 px, dark

**Android** (`cd android`, JDK 17)
- [ ] `./gradlew testDebugUnitTest verifyRoborazziDebug koverVerifyDebug lintDebug assembleDebug`
- [ ] on a phone or emulator when the change is about camera, permissions, offline or notifications

**Every change**
- [ ] a test fails without the change and passes with it
- [ ] no rule written twice; no dead code left; comments still true
- [ ] no customer value in a log, URL, push or crash report
- [ ] error paths tried: server down, 403, 409, retry
- [ ] `REQUIREMENTS.md`, plan status, `openapi.yaml`, contract notes updated where they apply
- [ ] the diff holds only this topic; no generated or local files (`node_modules`, build output,
      `.env*`, keys)

## 7. Commits and pull requests
- One topic per commit; message = what changed and why, in plain words; finding / requirement IDs
  when there are any.
- A PR says what it fixes, what it leaves out, and which checks were run locally with their
  results. CI must be green; nobody merges their own red PR.
- Secrets never go in git, chat or logs. Never run a wipe or seed command against a server whose
  kind is not `local` or `test`.

## 8. When you are unsure
Stop and ask the owner (or the lead session) when: a requirement is unclear or two documents
disagree; the change needs a new dependency, a new permission, or a break in the API; the fix would
change what a customer sees or receives; a test can only pass by loosening it.
