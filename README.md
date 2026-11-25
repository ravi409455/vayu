# Vayu

Car CID inspection platform: bookings, offline Android inspections, admin-built forms, PDF
reports, webhooks. See `REQUIREMENTS.md` (what) and `plan.md` (how/when).

```
backend/   Django + DRF (Python 3.12, managed by uv)
web/       React app
android/   Kotlin app (Experts and Ops)
shared/    test vectors shared by all clients
infra/     docker compose + Caddy
docs/      setup guides, benchmarks
```

## Documentation
- How to use it: `docs/guides/` ([Admin](docs/guides/admin.md), [Ops](docs/guides/ops.md),
  [Expert](docs/guides/expert.md)).
- How it is built: [docs/architecture.md](docs/architecture.md); how to change it:
  [CONTRIBUTING.md](CONTRIBUTING.md) and `docs/engineering-standards.md`.
- For other systems: [docs/integrations/](docs/integrations/README.md); logging:
  [docs/logging.md](docs/logging.md); error codes: [docs/error-codes.md](docs/error-codes.md).

## Run it on your laptop
`scripts/local.sh up`, then open http://localhost:5173. Details: `docs/local.md`.

## Backend: run the tests

```bash
docker compose -f infra/docker-compose.dev.yml up -d   # Postgres + Redis
cd backend && uv sync
DJANGO_SETTINGS_MODULE=vayu.settings.test uv run pytest
```

## Web: run the tests

```bash
cd web && npm ci && npm test
```

## Android: build and test

Needs JDK 17 (e.g. `brew install openjdk@17`) and the Android SDK (`android/local.properties`
with `sdk.dir=...`). Robolectric's Android jars come through Gradle, so tests run offline.

```bash
cd android && JAVA_HOME=$(/usr/libexec/java_home -v 17 2>/dev/null || echo /opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home) ./gradlew testDebugUnitTest
```

Rule logic is shared by backend, web and Android: `shared/rule-vectors/` holds the
cases all three must pass; `shared/rule-vectors/SCHEMA.md` defines the semantics.

Secrets never go in git: use `.env.*` files (git-ignored) and see `.env.example`.
Third-party accounts: `docs/accounts-setup.md`.

## Local secrets
Copy `.env.example` to `backend/.env.local` (git-ignored) and fill it in. Run backend commands
with that file loaded:

```bash
cd backend && uv run --env-file .env.local python manage.py runserver
```

Before changing anything, read `docs/engineering-standards.md` (rules and the verification checklist).
