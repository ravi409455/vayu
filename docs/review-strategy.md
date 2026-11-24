# Review strategy: full review of backend, web and Android

Status: **ready to use, not started.** Start it only after the planned changes and fixes are in
(see §1). This document says **how** to review; it holds no findings. The findings go to a new
report (§5).

The review looks at the product through four hats:

| Hat | Looks for | Leads |
|---|---|---|
| **Senior software engineer** | Design, correctness, security, data, server performance | Backend column, groups B, C, D, aspects 22, 27, 28 |
| **Technical product manager** | Does it do what was agreed, is it measurable, what blocks launch, what it costs | Group A, aspects 23, 30, 31 |
| **Senior front-end developer** | React code, what users see in a browser, accessibility | Web column, aspects 24, 26 |
| **Senior Android developer** | Kotlin / Compose code, offline, phone behaviour, release | Android column, aspects 16, 25 |

A hat **leads** an aspect (writes its score). Every hat may log findings anywhere.

---

## 1. Before you start (entry checklist)
Do not start until every line is true.

- [ ] All planned work you want reviewed is merged (library, integrations, profile, wording, quality
      fixes you chose to do first). Plans not built yet are reviewed **as plans** only (aspect 2).
- [ ] Working tree is clean; `main` is pushed; CI is green on that commit.
- [ ] **Baseline commit written down** at the top of the report (`git rev-parse HEAD`). Every finding
      refers to this commit. Work merged during the review is not reviewed in this round.
- [ ] Local stack runs from scratch (`scripts/local.sh`, `docs/local.md`) and the Android app builds
      and runs on an emulator **and** one real phone (low-end if possible).
- [ ] Demo data and the real setup are both available: `seed_demo` for play, `setup_platform` for the
      real PDI / Used Car / EV forms.
- [ ] Accounts for the 3 roles (Expert, Ops, Admin) on web and phone.

## 2. How the review runs (phases)
Run the phases in order. Each phase feeds the next.

| Phase | What happens | Output |
|---|---|---|
| **0. Measure** | Run every tool in §7 on the baseline commit and save the numbers (coverage, type errors, bundle size, APK size, slow queries, audit results, test time). | `numbers` table at the top of the report |
| **1. Map** | Short map of the code per layer: apps / folders, size, owners of each rule, where each requirement lives. List the 10 biggest and 10 most-changed files per layer (`git log --format= --name-only \| sort \| uniq -c \| sort -rn`). | Code map + hot spots |
| **2. Journeys** | Trace the journeys in §6 end to end through all three layers, in the code **and** by using the app. Most correctness, security and UX findings come from here. | Findings |
| **3. Aspect passes** | Go through the 31 checklists in §4, layer by layer. Skip questions a journey already answered (write "see J3"). | Findings + score per aspect × layer |
| **4. Cross-check** | Each hat reads the other hats' Critical / High findings and confirms or disputes them. A finding nobody can reproduce is dropped. | Confirmed list |
| **5. Plan** | Group confirmed findings into fix work (like `docs/plan-quality.md`), ordered by severity and by which files they touch. | Fix plan |

**Slicing.** One slice = one layer × one group (e.g. "Android × C. Correctness"). 3 layers × 7 groups
= 21 slices, each small enough for one sitting or one reviewer session. A slice ends with its scores
filled in.

## 3. Rules for findings

**Evidence first.** A finding needs at least one of: a file and line at the baseline commit, a command
and its output, a test that fails, steps to reproduce, or a screenshot. "Feels slow" is not a finding;
"Today page takes 2.8 s with 500 bookings (steps…)" is.

**No confirmation bias.** Earlier reviews and plans are not proof. If `plan-quality.md` says
something is fixed, check it again. Look for what is wrong, not for what works.

**Severity**

| Level | Meaning | Example |
|---|---|---|
| **Critical** | Data loss, security or privacy breach, a wrong report reaching a customer, app unusable for a role | An Expert can read another Expert's lead; a submitted inspection can be lost when the app is killed |
| **High** | A requirement is broken, or a likely failure with real harm | Ops can delete a submission; webhook retries send a booking twice |
| **Medium** | Works, but fragile, slow, confusing or costly | Same rule written in web and Android differently; page loads all bookings |
| **Low** | Quality issue with small effect | Stale comment, unclear name, missing empty state |
| **Note** | Observation or idea, no fix needed now | Library that will need an update next year |

**Finding format** (one row each):

```
ID       R-031
Aspect   20 Security
Layer    Backend
Severity High
Where    backend/apps/bookings/views.py:142 (baseline abc1234)
What     One sentence: what is wrong.
Evidence Command / steps / test and what it showed.
Why      Plain example of the harm ("an Ops user could…").
Fix      One line + size S (< ½ day) / M (≤ 2 days) / L (more).
```

**Scores** (one per aspect × layer): **Good** (nothing above Low), **OK** (Medium findings only),
**Weak** (any High), **Bad** (any Critical), **Not checked** (say why). "—" where the aspect does not
apply.

## 4. Aspect checklists
For each aspect: **Ask** = the questions to answer; **How** = how to check; **Evidence** = what proves
the answer. Layer letters: **B** backend, **W** web, **A** Android.

### A. Product and delivery

**1. Requirements fit** (B W A)
- Ask: For every rule in `REQUIREMENTS.md`, `docs/android-requirements.md` and each built plan: where is
  it enforced, and is it enforced **on the server** (not only hidden in a screen)? Which rules are
  missing, half-built or built differently than agreed?
- How: build a traceability table *requirement → code → test*. Try each role's forbidden actions
  through the API directly, not only the UI (e.g. Ops `DELETE` on a submission).
- Evidence: the table; one line per gap.

**2. Product and delivery** (B W A)
- Ask: Which plans are done, partly done, not started? Does `plan.md` match reality? What is built but
  not in any plan (scope creep)? What blocks launch? Which open questions are still open (e.g. the
  "New bookings" push question in `plan-android.md`)?
- How: read every `docs/plan-*.md` status line against `git log`; list TODO / "later" notes.
- Evidence: a status table per plan; a launch-blocker list.

**3. Product metrics** (B W A)
- Ask: Can we answer, from data we already store: time per inspection, inspections per Expert per day,
  upload failures and retries, PDF failures, late starts, how often Ops edit a submission, crash rate?
  What is missing to answer them?
- How: write each question as a query or a log search; mark which cannot be answered.
- Evidence: question → how it is answered today (or "cannot").

**4. Long-term maintenance** (B W A)
- Ask: Which files are big **and** change often (hot spots)? Which parts only one session / person
  understands? How many TODO / FIXME / `ponytail:` notes, and are their ceilings still fine?
- How: hot-spot list from phase 1; `grep -rn "TODO\|FIXME\|ponytail:"`; read the top 5 hot spots.
- Evidence: hot-spot table with size, change count, short risk note.

**5. Setup and form content** (B)
- Ask: Is `setup_platform` safe to re-run on production (never deletes, only publishes on real change,
  leaves users alone)? Do the frozen forms match `docs/clappia/` and the agreed mapping
  (`mapping_worklist.json`)? Can `seed_demo` / `seed_test_data` ever run on production?
- How: run `setup_platform` twice on a copy and diff the DB; compare frozen forms with the Clappia
  read-out field by field (a script, not by eye); check the guards on the seed commands.
- Evidence: diff after second run is empty; mapping diff list.

### B. Code quality

**6. Structure and modularity** (B W A)
- Ask: Does each module have one job? Do views / screens hold business rules that belong in a service
  or view model? Any import loops between backend apps (`accounts`, `bookings`, `core`, `forms`,
  `integrations`, `media`, `notify`, `reports`, `scoring`)? Is the web folder layout
  (`pages`, `ui`, `lib`, `api`) followed? Do Android packages separate UI, state and data?
- How: import graph per layer (backend: `grep -rn "^from apps\." `; web: imports between `pages`;
  Android: package imports); read the biggest file in each module.
- Evidence: list of rules found in the wrong layer; any cycle.

**7. Reuse and duplication** (B W A)
- Ask: Is the same rule written twice (inside a layer, or web vs Android vs server)? Examples to check:
  answer rules (`shared/rule-vectors`), date / money formatting, stage words, upload logic, permission
  checks, field-type handling.
- How: search for the same constant / message / regex in several places; compare web and Android
  implementations of the same rule against the shared vectors.
- Evidence: pairs of duplicated code with paths.

**8. Clean code** (B W A)
- Ask: Clear names? Functions short enough to read at once? Dead code, unused exports, commented-out
  code, magic numbers?
- How: read hot spots; unused-code search per layer; longest functions list.
- Evidence: examples with paths (sample, not every case).

**9. Design principles (SOLID)** (B W A)
- Ask: Classes / components doing several jobs? `if type == …` chains that a registry should replace
  (field types, events, problem kinds)? Hard-wired dependencies that make testing hard?
- How: grep for long `if/elif` and `when` chains on a type; read large classes / composables.
- Evidence: each case with the change it would make easier.

**10. Comments and in-code docs** (B W A)
- Ask: Do comments explain *why*? Are any stale (describe old behaviour)? Do module docstrings say
  what the module owns?
- How: while reading hot spots, check each comment against the code next to it.
- Evidence: stale or wrong comments with paths.

**11. Types and static checks** (B W A)
- Ask: How many `type: ignore`, `Any`, `as unknown`, `!!` (Kotlin)? Is mypy strict where the quality
  plan says? Is TypeScript `strict`? Is Android lint run at all?
- How: counts by grep; run each checker (§7); run Android lint once even though CI doesn't.
- Evidence: counts and the worst examples.

**12. Dependencies** (B W A)
- Ask: Known vulnerabilities? Versions far behind? Unused packages? Licences that forbid our use?
  Is each dependency still needed (could the standard library do it)?
- How: `pip-audit`, `npm audit`, Gradle dependency updates report; check unused imports of each
  package.
- Evidence: audit outputs; list of drop / update candidates.

### C. Correctness and reliability

**13. Correctness and edge cases** (B W A)
- Ask: What happens with: two users editing the same thing, two experts on one lead, time zones
  (IST vs UTC at midnight), empty lists, very long text, 0 / max photos, an old form version, a
  deleted master-list value, a cancelled booking with offline work?
- How: pick the risky functions from the journeys; write a quick failing test or try it in the app.
- Evidence: failing test or reproduction steps.

**14. Error handling** (B W A)
- Ask: What does each user see when the server is down, slow, returns 400 / 403 / 409 / 500? Are
  retries safe (no double submit, double upload, double webhook)? Are errors swallowed anywhere?
- How: kill the API / network mid-action on web and phone; grep for bare `except` / empty `catch`.
- Evidence: screenshots of each error state; list of swallowed errors.

**15. Data integrity and migrations** (B A)
- Ask: Are rules that must always hold written as DB constraints? Can a migration lose data or lock a
  big table? Can rows or R2 files be left orphaned (deleted booking, replaced photo)? On the phone,
  can local files / drafts get out of step with the server?
- How: read models and constraints; read every migration since the last review; compare R2 keys with
  DB rows on demo data; inspect the app's local storage after typical flows.
- Evidence: missing constraints; orphan counts.

**16. Offline and sync** (W A)
- Ask: App killed mid-inspection, mid-upload, mid-submit: what is lost? Phone offline for a day, then
  back: does everything arrive, in order? Job moved or cancelled by Ops meanwhile? Web upload resume
  after a browser restart?
- How: on a real phone, airplane mode + force-stop at each step of J2; on web, close the tab during an
  upload and reopen.
- Evidence: step-by-step results table.

**17. Notifications and alerts** (B W A)
- Ask: Does the right person get each notice, exactly once? Do repeat floors and once-a-day rules work?
  Does a push carry only a notice id? Does it arrive with the app closed? Does sign-out clear notices
  and the push token? Can a notice for one person show on another's phone?
- How: trace J6; two phones, two users, sign in / out swaps.
- Evidence: notice log vs what each phone showed.

**18. API contracts** (B W A)
- Ask: Does `openapi.yaml` match the code? Are error codes consistent and documented? Do web and
  Android parse the same responses the same way (nulls, dates, enums)? Do both pass
  `shared/rule-vectors`?
- How: regenerate the schema and diff; list error codes in code vs docs; compare web `api/types.ts`
  with Android models for the same endpoints.
- Evidence: mismatches with paths.

**19. Testing** (B W A)
- Ask: Which critical paths have no test? Would a test fail if the code broke (try breaking one line in
  a few key functions)? Flaky tests? How long do the suites take? Are Android screenshot tests
  (Roborazzi) and coverage (Kover) meaningful?
- How: coverage reports per layer; mutation by hand on 5–10 key functions; CI history for flakes.
- Evidence: untested critical paths; mutation results.

### D. Security and privacy

**20. Security** (B W A)
- Ask: Every endpoint checks permission on the server (3 roles, own vs all)? Input validated at every
  entry (API, uploads, imports, webhooks config)? SSRF guard on every outgoing call? Secrets never in
  git, logs or the APK? CSRF / XSS on web? Push tokens bound to one person's device? Tokens and files
  on the phone stored safely and wiped on sign-out? Customer pages leak nothing beyond the summary?
- How: URL scan of all views for permission classes; try each forbidden action with each role through
  the API; `git log -p` grep for keys; decompile the release APK and grep; check
  `django check --deploy`.
- Evidence: per-endpoint permission table; any bypass with steps.

**21. Privacy and data retention** (B W A)
- Ask: Where does customer data go (logs, Sentry, webhooks, push, exports, phone cache)? How long are
  photos, videos, reports kept, and does deletion really delete (DB **and** R2)? What does the phone keep
  after sign-out? Do shared links expire?
- How: list every place personal data is written; follow one booking's data through J1 and check each
  place; run the retention job on old demo data.
- Evidence: data-flow table; any copy that outlives its rule.

### E. Performance and cost

**22. Performance** (B W A)
- Ask: Slow or repeated queries (N+1) on list pages? PDF render time and memory? Web bundle size and
  first load? App start time, APK size, frame drops on long forms, main-thread disk / network?
- How: query counts on the main list endpoints with 500+ bookings; `bench_pdf`; `vite build` sizes;
  Android startup trace and StrictMode; scroll a 200-field form on a low-end phone.
- Evidence: numbers compared with `docs/benchmarks.md`.

**23. Running cost** (B A)
- Ask: What does one inspection cost in storage and traffic (photos, videos, ZIPs, PDFs)? Are photos
  compressed on the phone before upload? What grows with users (Sentry events, Firebase messages,
  server size)? What happens at 10× today's volume?
- How: sizes from R2 for demo jobs; read the phone's compression settings; check free-tier limits of
  Sentry and Firebase.
- Evidence: cost per inspection and per month at 1× and 10×.

### F. User experience

**24. Web UX and accessibility** (W)
- Ask: Every page has loading, empty and error states? Usable by keyboard only? Labels for screen
  readers? Dark mode correct? Works at phone and tablet width? Customer pages (report download,
  verify) clear and on-brand for a car buyer?
- How: walk every page per role; axe / Lighthouse accessibility run; keyboard-only pass; 375 px width.
- Evidence: screenshots; axe results.

**25. Android UX and platform** (A)
- Ask: Back button and gestures behave? State survives process death (Android closing the app in the background)? Permission denials
  handled (camera, notifications)? Works on small screens and large font size? Self-update flow clear?
  Background work (WorkManager) survives reboot and battery saver?
- How: "Don't keep activities" developer option; deny each permission; font scale 1.3; reboot during
  uploads; test on the smallest supported phone.
- Evidence: screenshots / screen recordings per case.

**26. Design and wording consistency** (B W A)
- Ask: Do web and Android match the approved designs and the shared tokens? Is the wording rule kept
  everywhere (experts read "lead", Ops and Admin read "booking", never "job"), including server
  messages, notifications and PDFs? Same stage words on all screens?
- How: grep for "job" in user-facing strings (web, Android `strings` / composables, server messages);
  side-by-side screenshots of the same screen on web and phone.
- Evidence: list of off-rule strings; screenshot pairs.

### G. Operations and docs

**27. Logging and observability** (B W A)
- Ask: From the logs alone, can you explain what happened to one booking? Is every log line free of
  customer values? Is the audit log complete for config changes? Do crash reports arrive and are they
  useful?
- How: pick one booking from J1 and reconstruct its story from logs; grep log calls for values.
- Evidence: the reconstructed story and its gaps.

**28. External services** (B W A)
- Ask: For Sentry, Firebase and R2: what data each receives, where its keys live, what happens when it
  is down or slow (does the app wait, retry, lose data?), and how we would notice?
- How: block each service (firewall / wrong key) in local and on the phone and run J1.
- Evidence: behaviour table per service.

**29. Build, CI and dev setup** (B W A)
- Ask: Do CI gates match what the plans promise? How long is CI? Can a new developer set up
  everything from `README` / `docs/local.md` without help? Are release builds signed from a key kept
  outside the project, with correct version codes?
- How: fresh clone on a clean machine (or container), follow the docs only; CI timing from history;
  build a release APK and check its signature.
- Evidence: every step where the docs were wrong or missing.

**30. Documentation** (B W A)
- Ask: Is each doc still true? README, API docs, integration guide, architecture, user help for each
  role? Are plans marked done when done?
- How: follow each how-to literally; spot-check 10 claims per doc against the code.
- Evidence: list of wrong or missing docs.

**31. Deployment readiness** (B W A) — **before launch only**
- Ask: Hosting, backups and restore test, monitoring and alerts, secret handling, release steps, APK
  self-update and the release site, rollback.
- How: walk the launch checklist when launch prep starts; in this round only note anything already
  known.
- Evidence: launch checklist with owner per line.

## 5. Outputs
One file, `docs/review-report-<date>.md`, with:
1. Baseline commit, date, who reviewed (hats), devices and browsers used.
2. **Numbers** table from phase 0.
3. **Scorecard**: 31 aspects × 3 layers, each Good / OK / Weak / Bad / Not checked / —.
4. **Findings**, most severe first, in the §3 format.
5. **Journey results** (J1–J8): pass / fail per step.
6. **Fix plan**: findings grouped into work items with order and size, like `docs/plan-quality.md`.
   Anything in `plan-quality.md` that is still open is merged in, not listed twice.

## 6. Journeys to trace (all three layers)
Trace each in code and by using the app, with the role named.

| ID | Journey | Main aspects |
|---|---|---|
| J1 | Booking created (web and via API) → assigned → Expert gets a notice → offline inspection on the phone → photos / videos upload → submit → scores and Key Checks → PDF → webhook → customer opens the report link | 1, 13, 16, 17, 20, 21, 22, 27 |
| J2 | Same inspection with trouble: no network, app killed, phone restarted, Ops move or cancel the lead meanwhile | 14, 15, 16 |
| J3 | Ops review: edit answers, replace a photo, override a rating, regenerate the PDF, finish a job with a missing file | 1, 13, 20, 26 |
| J4 | Admin changes a form: draft → preview → publish; library edit and push; an Expert mid-job keeps the old version | 1, 13, 15 |
| J5 | Sign-in and devices: sign in on a second phone, Ops force sign-out, password change, sign-out clears phone data | 17, 20, 21 |
| J6 | Notices: reminder, late start, stuck upload, conflict; repeat rules; two users on two phones | 17, 21 |
| J7 | Integrations and API: API key with field scope, bulk update, webhook delivery, failure and resend | 18, 20, 21, 28 |
| J8 | Fresh setup: new server, `setup_platform`, users file, first booking end to end; app self-update to a new version | 5, 29, 31 |

## 7. Tools
What is set up today, and what to run once for the review. A missing tool is not a finding by itself;
missing **coverage of a risk** is.

| Layer | Already in CI | Run once for the review |
|---|---|---|
| Backend | `ruff`, `mypy apps vayu`, `makemigrations --check`, `pytest --cov` (85% + per-module gates), Docker checks | `pip-audit`, `manage.py check --deploy` (prod settings), query counts on list endpoints, `bench_pdf`, locust (`perf/`, `loadtest/`) |
| Web | `tsc --noEmit`, Vitest, `vite build`, Playwright e2e | `npm audit`, bundle size report, axe / Lighthouse, keyboard-only pass |
| Android | Roborazzi screenshots, Kover coverage, debug + release build | Android lint, dependency updates report, startup trace, StrictMode, APK analyzer (size, secrets), low-end phone pass |
| All | — | `git log` hot spots, TODO / `ponytail:` count, secret scan of history |

## 8. Done when
- Entry checklist (§1) was true at the baseline commit.
- Every aspect × layer has a score, or "Not checked" with a reason.
- All 8 journeys traced, with pass / fail per step.
- Every Critical and High finding confirmed by a second hat (phase 4).
- The fix plan exists and the owner of the product has agreed its order.
