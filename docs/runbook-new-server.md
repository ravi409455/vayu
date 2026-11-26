# Runbook: a server (staging or production)

How a Vayu server is built, deployed, backed up and restored. The why and the owner's dashboard
clicks are in `docs/plan-deploy.md`; this file is the exact commands. Staging and production are
the same steps; the differences are in the env file (`.env.example` marks each staging value).

| | Staging | Production |
|---|---|---|
| Address | `vayu-staging.carcid.in` | `vayu.carcid.in` |
| Droplet | 2 vCPU / 4 GB, BLR1 | 4 vCPU / 8 GB, BLR1 |
| Database | Postgres in Docker (`DB_HOST=postgres`) | DigitalOcean managed Postgres (`DB_SSLMODE=require`) |
| Env file | `/srv/vayu/.env.staging` | `/srv/vayu/.env.prod` |
| Bucket / backups | `vayu-staging` / `vayu-backups/staging/` | `vayu-prod` / `vayu-backups/prod/` |
| Deploys | after every merge to `main` (CI green) | after the owner presses Approve |

Every customer QR link is `https://<address>/report/verify/<code>`.

## 1. Build the server (once)
1. Create the droplet (plan 2.2 / 7.1), add it to the `vayu-web` firewall, point DNS at it.
2. From the laptop:
   ```bash
   ssh root@<server ip> 'bash -s' < infra/bootstrap.sh
   ```
   Updates, automatic security updates, firewall (22, 80, 443), Docker with log limits, the
   `deploy` user, swap on small servers, UTC clock, the code in `/srv/vayu`, the nightly backup
   timer. After it, `root` and passwords can't log in: `ssh deploy@<address>`.
3. Env file: copy `.env.example` to `/srv/vayu/.env.staging` (or `.env.prod`), set the
   non-secret values, then paste each secret from Phase (`nano`). Then `chmod 600` it.
   Avoid `$` in secrets (Docker Compose reads it as a variable).
4. Firebase file (from the laptop):
   ```bash
   scp vayu-<server>-firebase.json deploy@<address>:/srv/vayu/secrets/firebase-service-account.json
   ssh deploy@<address> chmod 600 /srv/vayu/secrets/firebase-service-account.json
   ```
5. The GitHub robot's key, locked to the deploy script. Make it on the laptop:
   ```bash
   ssh-keygen -t ed25519 -N "" -C "github-deploy-<server>" -f ./deploy-<server>
   ```
   On the server, append ONE line to `~/.ssh/authorized_keys` (the public half after the options):
   ```
   command="/srv/vayu/infra/deploy.sh",restrict ssh-ed25519 AAAA... github-deploy-<server>
   ```
   GitHub → Settings → Environments → `staging` (or `production`) → secrets: `SSH_KEY` (the
   private file), `SSH_HOST` (the address) and `SSH_KNOWN_HOSTS` (the output of
   `ssh-keyscan -t ed25519 <address>`, run once you trust the server). Save the private file in
   Phase, then delete both files from the laptop.
6. First deploy: GitHub → Actions → deploy → Run workflow → the latest commit id of `main`
   (or merge anything to `main`). Caddy gets the https certificate by itself.
7. Check: `curl -fsS https://<address>/api/v1/health` → `{"status": "ok"}` (database, Redis,
   storage, workers, push).

The images live in GitHub's package store (`ghcr.io/ravi409455/vayu-api` and `vayu-web`). While the
repo is public they are public. Once it is private: make a GitHub token with only `read:packages`
and put `GHCR_USER` / `GHCR_TOKEN` in the env file; `deploy.sh` logs in with it.

## 2. Forms, reports, lists and staff (once per server)
```bash
cd /srv/vayu
C() { VAYU_TAG=$(cat .deployed) bash -c 'source infra/lib.sh; compose "$@"' _ "$@"; }
C cp staff.csv api:/tmp/staff.csv
C exec api python manage.py setup_platform --users /tmp/staff.csv
C cp api:/tmp/staff.csv.passwords ./staff.csv.passwords && chmod 600 ./staff.csv.passwords
C exec api rm /tmp/staff.csv /tmp/staff.csv.passwords
```
- Staff file (see `backend/apps/platform/setup/users.example.csv`): `username,name,role,phone,password`,
  at least one `admin`. Made-up passwords land in `staff.csv.passwords`: hand them out, then delete
  the file. Everyone changes their password at first sign-in.
- Running it again only adds what is missing. `--force --confirm <VAYU_SERVER_NAME>` publishes the
  setup's forms and templates again as new versions (it stops if an Admin has a draft open).
- **Staging only**, test bookings (a random 20+ character password from Phase: staging is on the
  open internet and the code is public):
  ```bash
  C exec api python manage.py seed_test_data --confirm staging-1 --password '<from Phase>'
  ```
  It refuses on production (server kind, real bookings).

## 3. The Android app
Build on the laptop (signing key in `~/vayu-keys`, `SENTRY_DSN_ANDROID` and `SENTRY_AUTH_TOKEN`
set). The version code must be higher than every build ever installed (a phone already has 2):
```bash
cd android
./gradlew assembleStaging -Pvayu.versionCode=3 -Pvayu.versionName=0.3.0   # "Vayu Staging"
./gradlew assembleRelease -Pvayu.versionCode=3 -Pvayu.versionName=0.3.0   # "Vayu" (production)
```
Publish on its server (the APK page and the in-app update read it):
```bash
scp app/build/outputs/apk/staging/app-staging.apk deploy@vayu-staging.carcid.in:/srv/vayu/vayu.apk
# on the server
C cp vayu.apk api:/tmp/vayu.apk
C exec api python manage.py publish_apk /tmp/vayu.apk --version-code 3 --version-name 0.3.0 --notes "..."
rm vayu.apk
```
Raise `MIN_APP_VERSION` only after the build that meets it is published.

## 4. Deploying
- Normal: merge to `main`. CI → images built once → staging deploys → production waits for Approve.
- Deploy outside 9 am to 8 pm unless urgent: services restart (10 to 20 seconds of errors that
  phones and browsers retry). A running job gets 60 seconds; if cut, it goes back in the queue.
- What `infra/deploy.sh <commit>` does: checks the commit is on `main`; on production dumps the
  database first; checks out that commit's infra files; pulls its images; runs migrations
  (`migrate` service), restarts everything, waits up to 3 minutes for health `ok`. If health
  fails it puts the previous commit back and the GitHub run goes red.
- The commit that is live: `cat /srv/vayu/.deployed`.

**The migration rule.** Every migration must also work with the previous release (add a column
in one release, stop using it in the next, drop it in a third). That is what makes rolling back
code safe without touching the database.

## 5. Rolling back
- **Code (the usual case):** GitHub → Actions → deploy → Run workflow → the previous commit id
  (from the Actions history or `.deployed` before the release). About 3 minutes.
- **A migration that damaged data (rare):** the owner's call; everything typed in since the dump
  is lost.
  1. Stop the app: `C stop api worker zip-worker pdf-worker beat`.
  2. `infra/restore.sh` → pick the `predeploy-<commit>` dump → `infra/restore.sh <name> --into-live`.
     (Production can instead use the managed database's restore to a minute, §7.)
  3. Deploy the previous commit (above). Check booking and user counts.
- Reverse a schema change by hand only with care: `python manage.py migrate <app> <previous>`.
  These data migrations are **one-way** (their reverse does nothing): accounts 0004, 0005, 0007,
  0009, 0010, 0013, 0014 (0014's sign-out grant does reverse); bookings 0006, 0008; forms 0008,
  0010, 0014, 0015, 0018, 0019, 0020; integrations 0002, 0003 (dropped webhook fields: restore from
  a backup); notify 0002; reports 0003, 0004.

## 6. Backups
- Nightly at 02:00 IST (`vayu-backup.timer`, 20:30 UTC) and before every production deploy:
  `infra/backup.sh` dumps the database, encrypts it with `BACKUP_PUBLIC_KEY` (age) and uploads it to
  `vayu-backups/<prefix>/`. The bucket lock keeps each for 30 days; the lifecycle rule deletes after 35.
- The nightly run pings `BACKUP_HEARTBEAT_URL`; no ping in a day → Slack alert.
- By hand: `infra/backup.sh manual`. Timer status: `systemctl list-timers vayu-backup.timer`;
  last run's log: `journalctl -u vayu-backup.service -n 50`.
- Production also has the managed database's own backups: restore to any minute of the last 7 days.

## 7. Restore drill (first Monday of every month, both servers)
```bash
infra/restore.sh                       # list
infra/restore.sh <name>                # load into a throwaway database, compare row counts
```
It asks for the backup unlocking key (Phase), loads the dump into a temporary Postgres
container on the same server, prints the biggest tables of the backup and of the live database,
then deletes the container. Record each drill below.

**Managed restore to a minute** (production; rehearse once before launch). It makes a NEW database:
1. DigitalOcean → Databases → `vayu-prod-db` → Backups → Restore from backup → pick the minute.
2. New cluster → Trusted sources → add `vayu-prod`; Users & Databases: same user.
3. In `.env.prod` change `DB_HOST` to the new private host; deploy the live commit again.
4. Check booking and user counts. Destroy the old cluster a day later, not at once.

| Date | Server | Backup | Restore took | Counts match | By |
|---|---|---|---|---|---|
| | | | | | |

## 8. Watching
- `https://<address>/api/v1/health` every minute (Better Stack) → `#vayu-alerts`.
- Heartbeats: `BACKUP_HEARTBEAT_URL` (daily), `WORKERS_HEARTBEAT_URL` (every 5 minutes: beat queues
  it, a worker sends it, so it stops if beat, Redis or the workers stop).
- Sentry (server, web, app): new issues and spikes in `production` → `#vayu-alerts`.
- DigitalOcean alerts: disk > 80%, memory > 90%, CPU > 90%; database disk and connections > 80%.
  The 1 GB managed database allows about 22 connections; we use about 14. Add a worker → 2 GB first.
- Logs: `C logs --tail 100 api` (or `worker`, `pdf-worker`, `caddy`...). Kept about a week.

## 9. Security headers
Caddy sends HSTS, nosniff, a referrer policy, a permissions policy and the content rules (CSP).
`CSP_HEADER` defaults to `Content-Security-Policy` (enforced). Staging alone starts with
`CSP_HEADER=Content-Security-Policy-Report-Only` (the browser only reports, in its console) until a
full run (sign-in, booking, inspection with photos and video, PDF preview, QR page) shows nothing
blocked; then remove the line and redeploy. Production never runs report-only.
