# Vayu

Car CID inspection platform: bookings, offline Android inspections, admin-built forms, PDF
reports, webhooks. See `REQUIREMENTS.md` (what) and `plan.md` (how/when).

```
backend/   Django + DRF (Python 3.12, managed by uv)
web/       React app (from Phase 7)
android/   Kotlin app (from Phase 13)
shared/    test vectors shared by all clients
infra/     docker compose + Caddy
docs/      setup guides, benchmarks
```

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

Rule logic is shared by backend, web and (later) Android: `shared/rule-vectors/` holds the
cases all three must pass; `shared/rule-vectors/SCHEMA.md` defines the semantics.

Secrets never go in git: use `.env.*` files (git-ignored) and see `.env.example`.
Third-party accounts: `docs/accounts-setup.md`.

## Local secrets
Copy `.env.example` to `backend/.env.local` (git-ignored) and fill it in. Run backend commands
with that file loaded:

```bash
cd backend && uv run --env-file .env.local python manage.py runserver
```
