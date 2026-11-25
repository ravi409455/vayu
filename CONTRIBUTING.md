# Contributing

Read `docs/engineering-standards.md` before your first change: it is the rulebook (tests first, fix
the cause once, privacy, words on screen, the checklist before "done"). This page is the practical
part. How the system fits together: `docs/architecture.md`.

## Set up

| Part | Needs | First run |
|---|---|---|
| Everything at once | Docker Desktop, `uv`, Node 22 | `scripts/local.sh up`, then http://localhost:5173 (users and demo data: `docs/local.md`) |
| Backend only | Docker (Postgres + Redis), `uv` | `docker compose -f infra/docker-compose.dev.yml up -d` then `cd backend && uv sync` |
| Web only | Node 22 | `cd web && npm ci` |
| Android | JDK 17, Android SDK | see `README.md` |

## Tests and checks

Run what applies to what you touched; CI runs all of it (`.github/workflows/ci.yml`).

**Backend** (`cd backend`). When other runs share the machine, give yours its own database and
coverage file:

```bash
export DB_NAME=vayu_mine COVERAGE_FILE=/tmp/cov_mine
uv run ruff check .
uv run mypy apps vayu
uv run pytest -n 4 --cov --cov-fail-under=85
```

- Ruff includes security (`S`) and complexity (`C90`, at most 12). The per-file complexity allow
  list in `pyproject.toml` only shrinks: split a function, then remove its line.
- Nine areas must keep **100% branch coverage** (rules, bookings, media, reports, promote, library,
  scoring, integrations, permissions); their commands are in `ci.yml`, job `backend-gates`.
- The OpenAPI file must match the code and the generator must print no warnings:

  ```bash
  DJANGO_SETTINGS_MODULE=vayu.settings.test uv run python manage.py spectacular --fail-on-warn --file openapi.yaml
  ```

- A change CI's `oasdiff` reports as breaking needs `[api-break-ok]` in the commit message and the
  reason, and a line in the changelog of `docs/integrations/README.md` when integrators see it.

**Web** (`cd web`):

```bash
npx tsc --noEmit
npm run lint          # typescript-eslint, react-hooks, jsx-a11y; a switch-off needs "-- reason"
npm run format:check  # Prettier (npm run format fixes it)
npx vitest run
npx playwright test   # journeys; own ports and database
```

**Android** (`cd android`): `./gradlew testDebugUnitTest verifyRoborazziDebug koverVerifyDebug lintDebug assembleDebug`

## Commits and branches

- Branch from the integration branch the lead names (or `main`); one topic per branch; never commit
  to `main` directly.
- One commit per change that stands on its own. Subject `type(area): what changed` in plain words,
  e.g. `fix(bookings): a cancelled booking refuses a reschedule`, `docs: logging policy`. Types:
  `feat`, `fix`, `refactor`, `perf`, `test`, `docs`, `chore`. The body says why, and the numbers
  for anything claimed faster.

## How to add…

**A field type**

1. Backend: one entry in `TYPES` in `backend/apps/forms/fieldtypes.py` (allowed config keys, how an
   answer is cleaned, how its config is checked, whether it is a value, a choice or system-filled)
   and the name in `FieldType` in `apps/forms/models.py` (then `makemigrations`).
2. Web: one entry in `TYPES` in `web/src/lib/fieldTypes.ts` (label, group, icon) and its input in
   `INPUTS` in `web/src/ui/FieldInputs.tsx`.
3. Android: `core/forms/FieldTypes.kt` and the input in `ui/expert/Fields.kt`.
4. Tests: answer cleaning and config checks (backend), the input (Vitest), and the shared vectors
   in `shared/rule-vectors/` if conditions can read it.

**A domain event** (something happened; other apps react)

1. Add the name to `NAMES` in `backend/apps/core/events.py` (an unknown name raises).
2. `events.emit("thing.happened", booking=str(b.id), ...)` from the service, after the change.
3. React in a subscriber (`AppConfig.ready` → `events.subscribe`). If integrators should get it,
   add it to `EVENTS` / `PUBLIC` in `apps/integrations/webhooks.py` and to
   `docs/integrations/webhooks.md`.
4. Test with `events.capture()`.

**A log event**: `log.event("area.what", booking=..., ...)` from `apps/core/log.py`, a row in
`docs/logging.md`, a test with the `logged` fixture. Never a customer value.

**An endpoint**

1. The rule in a service; the view only parses, calls it and shapes the reply.
2. Declare the permission: `permission_classes = [perm("<key>")]` (a new key goes in
   `apps/accounts/catalog.py`); a test fails for a view without one.
3. Refusals with `raise fail("CODE", "A sentence a person can act on.", status)`; regenerate
   `docs/error-codes.md` (the command is in that file).
4. A list gets pages (`apps.core.pagination.Pages`) and a query-count test.
5. Regenerate `openapi.yaml` (above); give the operation a serializer or `extend_schema` so the
   generator has no warnings.

## Security problems

Please do not open a public issue. Tell the project owner directly, with the steps to see it.
