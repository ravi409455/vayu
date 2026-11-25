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

## 2a. Design principles (SOLID, in plain words)
- **One job per unit.** A function, class, component or file does one thing and has one reason to
  change. Signs it does too much: "and" in its name, over ~60 lines for a function or ~300 for a
  file, flags that switch its behaviour. Split it.
- **Add a case without editing five places.** Things that come in kinds (field types, events,
  stages, problem kinds, media kinds) are handled by one registry or table, never by `if type ==`
  chains repeated across modules. A new kind = one new entry plus its tests.
- **Keep promises.** Anything that stands in for another (a subclass, a fake in tests, a second
  implementation) behaves the same for the caller: same results, same errors. A test fake that is
  more forgiving than the real thing hides bugs.
- **Small, exact interfaces.** A function takes what it needs, not a whole request or a whole
  object "in case". A component gets the few props it uses.
- **Depend on the layer below, never sideways or up.** Backend: views → services → models;
  `core` imports no other app; no import cycles. Web: pages → ui / lib → api. Android: ui → view
  model → core. Outside services (storage, push, time, network) are passed in or wrapped in one
  place, so tests can replace them.
- **No speculative design.** No interface with one implementation, no option nobody sets, no
  layer that only forwards. Build the second case when it exists.

## 2b. Clean code
- **Names say what it is in the product's words** (booking, lead, inspection, counted inspection),
  not how it is built. No abbreviations a new person must look up. Booleans read as facts
  (`is_active`, `canFinish`).
- **Short, flat functions.** Return early instead of nesting. One level of abstraction per
  function. More than four arguments: pass a small object.
- **No magic values.** A number or string with a meaning gets a name in one place (limits, days,
  status words, error codes).
- **No dead code**: unused functions, parameters, exports, permissions, screens and commented-out
  blocks are deleted, not kept "for later". Git remembers.
- **Make wrong states impossible** where cheap: enums over free strings, a DB constraint over a
  check in code, a required parameter over a default that hides a mistake.
- **Same thing, same way.** Follow the pattern the file and layer already use (how errors are
  raised, how a list is loaded, how a dialog is built). A better pattern replaces the old one
  everywhere in that change, or not at all.
- **Tests are code too:** one behaviour per test, a name that reads as the rule, no copy-pasted
  setup (use the fixtures), no sleeping.

## 2c. Performance
- **Measure before and after** anything claimed as faster (query count, time, size). Put the
  number in the commit message.
- **Backend:** a fixed number of queries per request (`select_related` / `prefetch_related`,
  aggregates in the database, never a query inside a loop); a query-count test on every list
  endpoint; an index for every filter and ordering a list uses; pages, never unbounded lists; heavy
  work (PDF, ZIP, image copies, webhooks, push) in a Celery task with a time limit, on its queue;
  timeouts on every outside call; stream large files, never hold them in memory. Targets: API
  reads under 500 ms, phone sync under 500 ms at 250 leads, PDF render within its limit.
- **Web:** pages are lazy-loaded; no request per keystroke (debounce, ask for counts instead of
  lists); long lists are paged; frequent updates (upload progress) don't re-render the whole page;
  nothing heavy imported into the first bundle.
- **Android:** nothing slow on the main thread; parse and build each form once; stable parameters
  so screens don't redraw for nothing; photos resized before upload (2048 px, ~500 KB), video
  720p ~2.5 Mbps; caches have a size limit; no work in the background without WorkManager.
- **Cost is performance too:** don't store a second copy of a file without deleting the first;
  generated files (ZIPs, print copies) have an expiry and a clean-up.

## 2d. Logging and observability
- **You must be able to tell the story of one booking from the logs.** Log each step that
  matters with the booking id (the internal uuid, never the customer's name): started, submitted,
  upload verified or failed, report made or failed, webhook sent or failed, push sent or failed.
- **Levels:** `info` for a step that happened, `warning` for something refused or retried,
  `error` / `exception` for something that needs a person. No log line inside a loop per item at
  `info`. No `print`.
- **Structure:** JSON logs with the request id; a Celery task carries the request id of the
  request that started it. Message = fixed text; values go in fields, so lines can be searched.
- **Never log:** customer names, phone numbers, addresses, answers, photos' links, tokens,
  passwords, API keys, request bodies, typed usernames on a failed sign-in (log the user's
  internal id or "unknown user", the address and the reason).
- **Every failure is visible to someone:** a failed background job raises an alert Ops can see
  (problem queue, bell) or an error report (Sentry) — not only a log line. Crash and error reports
  carry no customer text and no request bodies.
- **Audit log** for every configuration change and privileged action (who, what, when), written in
  the same transaction as the change; it says what changed, never the secret values.
- **Metrics come from stored facts:** keep the timestamps and counts a question will need
  (when it started, failed, was retried, by whom) instead of overwriting them.

## 2e. Security (always, not only in "security" changes)
- Check permission **and** ownership on the server for every object touched; a list is filtered
  by what the caller may see. Fields hidden from a role are neither returned nor writable.
- Validate every input at the edge: type, size, shape, allowed values; files by size, type and
  real content. Reject, don't repair.
- Anything fetched from an address a person typed goes through the address guard (no private
  networks, no redirects). HTML from people is cleaned with the allow-list on the server.
- Secrets come from the environment, never from code, logs, error messages, the APK or git.
- Rate-limit anything open to the internet or to guessing (sign-in, public links).
- A link that works without sign-in carries an unguessable token, shows the minimum, and expires.
- New permission, new public endpoint, new outgoing data or a change in who can see what: stop
  and ask (see §8).

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
- Types and style: `ruff` clean (includes security `S` and complexity `C90`, max 12; the allow list in `pyproject.toml` only shrinks), `mypy apps vayu` clean, lines ≤ 100, type hints on new functions.
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
