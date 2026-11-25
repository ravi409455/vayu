# Runbook: a fresh server (production or staging)

Plan batch 6 (F-215 / F-227, journey J8). One VPS running Docker; Cloudflare R2 for files;
Caddy in front for TLS. Staging is the same, with its own env file, bucket and Sentry environment.

## 1. Before you start
- DNS: `app.carcid.in` (and `verify.carcid.in`) point at the server.
- An R2 bucket and a key pair for this server only.
- A Sentry DSN (the server refuses to start without one).
- The Firebase service-account JSON, copied to the server outside the repo.

## 2. Env file
```bash
cp .env.example .env.prod
```
Fill in every value. Do not leave `PUBLIC_BASE_URL` or `SENTRY_DSN` out: the API refuses to
start without them. Set `VAYU_SERVER_KIND=production` (or `test` for staging) and a
`VAYU_SERVER_NAME` you will type back for any wipe or forced setup.

## 3. Start
```bash
docker compose -f infra/docker-compose.prod.yml --env-file .env.prod up -d --build
```
The `api` service runs the migrations, then gunicorn (`backend/gunicorn.conf.py`: access log
without query strings or tokens). Workers: `worker` (default, uploads, notify), `zip-worker`
(ZIPs, storage clean-up), `pdf-worker` (one render at a time) and `beat` (schedules).

Check health (database, Redis, storage, workers):
```bash
curl -fsS https://app.carcid.in/api/v1/health
```

## 4. Forms, reports, lists and staff
Write the staff file (see `backend/apps/core/setup/users.example.csv`): `username,name,role,phone,password`,
at least one `admin`. Then:
```bash
docker compose -f infra/docker-compose.prod.yml --env-file .env.prod exec api python manage.py setup_platform --users /tmp/staff.csv
```
- It writes the server kind into the database (the wipe guards read it), adds the master lists,
  the booking / check-in / wrap-up forms, the PDI, Used Car and EV forms with their reports, and
  the staff.
- Passwords it made up are in `/tmp/staff.csv.passwords` (readable by you only). Hand them out,
  then delete the file. Everyone changes their password at first sign-in.
- Running it again only adds what is missing; it never changes what an Admin edited.
  `--force --confirm <VAYU_SERVER_NAME>` publishes the setup's forms and templates again as new
  versions (it stops if an Admin has a draft open).
- Never run `seed_test_data` on production: it refuses (server kind and real bookings).

## 5. The Android app
```bash
docker compose -f infra/docker-compose.prod.yml --env-file .env.prod exec api python manage.py publish_apk /tmp/vayu.apk --version-code 1 --version-name 1.0.0 --notes "First release"
```
Experts download it from the web portal (signed in). Raise `MIN_APP_VERSION` only after the build
that meets it is published.

## 6. Check it works
- Sign in on the web as the Admin; the Settings page shows the time limits and retention.
- Create a booking, assign an expert, start and submit it from the app; the booking completes and
  its PDF appears; the verify link from the QR opens.
- `GET /api/v1/health` is `{"status": "ok"}`.

## 7. Before launch (not covered here)
Backups and a restore test, monitoring, CSP, restricting the Firebase API key (plan §9).

## 8. Rolling back a release
Schema changes reverse with `python manage.py migrate <app> <previous>`. These data migrations
are **one-way** (their reverse does nothing, so a rollback past them keeps the data as it is now):
accounts 0004, 0005, 0007, 0009, 0010, 0013, 0014 (permission grants; 0014's sign-out grant does
reverse); bookings 0006, 0008 (back-filled answers and timing); forms 0008, 0010, 0014, 0015, 0018,
0019, 0020; integrations 0002, 0003 (dropped webhook fields: restore from a backup); notify 0002;
reports 0003, 0004. Take a database backup before every release (plan §9).
