# Plan: deployment (staging and production)

Agreed with the owner on 2026-11-25. This plan takes Vayu from "runs on a Mac" to a staging server
and a production server that deploy themselves, are backed up, and tell us when they break.

It does **not** cover moving the team off Clappia, staff training or the go-live day. That is a
later plan. Clappia stays read-only and untouched.

How to read it: steps marked **[YOU]** are clicks only the owner can do (accounts, payments,
anything that shows a secret). Steps marked **[CODE]** are changes Claude makes in a PR.
Steps marked **[SERVER]** are commands on a server; Claude runs the ones that need no secret.

**The one rule for secrets:** a secret (password, key, token, the Firebase JSON) is never typed
into chat and never put in git. You copy it from the dashboard straight into Phase, then into
the place this plan names (the server's env file or a GitHub secret).

---

## 1. Decisions taken

| Topic | Decision |
|---|---|
| Hosting | DigitalOcean, Bangalore (BLR1). Both 2 vCPU / 4 GB ($24). Production is always on; its size is the cheapest one that passes the realistic load test (`docs/plan-load-test.md`: 1 vCPU / 2 GB, 2 vCPU / 2 GB or 2 vCPU / 4 GB), and it grows later if the alerts say so (one click, about a minute down). |
| Staging | **On demand** (decided 2026-11-26): a switched-off droplet is still billed, so staging lives as a snapshot and is only created while testing, about once a month (`infra/staging.sh up` / `down`). |
| Database | Production: DigitalOcean **Managed Postgres** (restore to any minute of the last 7 days) plus our own nightly dump to R2. Staging: Postgres in Docker, nightly dump. |
| Files | Cloudflare R2 (already set up): one bucket per server, plus a new backups bucket. |
| Addresses | Production `vayu.carcid.in`. Staging `vayu-staging.carcid.in`. DNS stays at the registrar. |
| Customer QR link | `https://vayu.carcid.in/report/verify/<code>` (one host; no separate verify domain). |
| Deploys | GitHub Actions. Merge to `main` → staging updates by itself → production updates only after the owner presses **Approve**. |
| Alerts | Email and one Slack channel, `#vayu-alerts`. |
| Staging phone app | A separate app, "Vayu Staging" (`in.carcid.vayu.staging`), installs next to the real one. |
| Repo | Stays public until after launch, then goes private (step in §12). |
| Access | Owner only for now. A second owner on every account is an after-launch task (§12). |
| Secrets | Today they sit in files on the owner's Mac. They move to Phase (console.phase.dev) in Phase 0. **Production is not created until this is done.** |
| Working mode | The owner clicks, this plan guides. Claude writes all code and config. |
| Order | Staging end to end first. Production is then a copy of what worked. |

Monthly cost (DigitalOcean prices read 2026-11-26):

| Item | $ a month |
|---|---|
| Production droplet, 2 vCPU / 4 GB | 24.00 |
| Managed Postgres, 1 GB, 10 GB disk | 15.15 |
| Staging on demand (about a week a month at $0.0357/h) + snapshot (~8 GB × $0.06) | 3 to 6.50 |
| Production droplet backups | 0 (it holds no data) |
| R2 | 0 up to 10 GB, then $0.015 per GB a month (downloads free) |
| Sentry, Better Stack, Phase, Firebase pushes, GitHub (public repo) | 0 (free plans) |
| **Total** | **about $43 to 46**, plus 18% GST if DigitalOcean charges it (about ₹4,300 to 4,900) |

If production moves to 8 GB: +$24. Going private on GitHub: 2,000 free CI minutes a month, then
pay per minute or about $4 per user a month.

This plan was reviewed a second time on 2026-11-26 (as a senior engineer and a DevOps engineer
would) and corrected; the rules that came out of that review are in §1a.

## 1a. Rules that keep us out of trouble

1. **Every database change must also work with the previous release.** Example: to remove a
   column, release A stops using it, release B (later) deletes it. Then rolling the code back
   one release is always safe.
2. **One build, two servers.** Production runs the exact files staging just proved, web app
   included. Nothing is rebuilt for production.
3. **Deploy outside 9 am to 8 pm** unless it is an urgent fix. A deploy restarts the services:
   for 10 to 20 seconds phones and browsers get an error and retry.
4. **No secret is shared** between staging and production.
5. **A backup that was never restored is not a backup.** Restore drill monthly.

## 2. What it looks like when done

```
              phone app / browser
                     │ https
        ┌────────────▼─────────────┐
        │ Caddy  (https, headers)  │   one server (droplet)
        │  /api/*  → api           │
        │  else    → web app files │
        ├──────────────────────────┤
        │ api (Django)             │
        │ worker · zip-worker      │
        │ pdf-worker · beat        │
        │ Redis                    │
        └───┬──────────────────┬───┘
            │                  │
   Managed Postgres       Cloudflare R2
   (prod; staging has     (photos, videos,
    Postgres in Docker)    PDFs, ZIPs, backups)
```

Around it: GitHub Actions builds and deploys; Sentry catches errors from server, web and app;
an uptime checker pings the health page every minute; Firebase sends pushes.

## 3. What is missing today (found in the repo)

1. Caddy only forwards to the API. Nothing serves the web app, so `vayu.carcid.in` would show
   nothing. (Fresh review, High #9.)
2. There is no step that builds the web app for a server.
3. The compose file always reads `.env.prod`; staging can't use it as is.
4. The Firebase JSON file is named in the env file but never handed to the containers.
5. The API can't yet talk to a database that demands an encrypted connection (managed Postgres does).
6. No backups, no restore test, no alerts, no security headers (CSP).
   Also: the compose file gives the PDF worker up to 6 GB of memory, more than the whole staging
   server has (4 GB).
7. No deploy pipeline; `main` has no branch protection (fresh review, High #8).
8. Old addresses (`app.carcid.in`, `verify.carcid.in`) are written into code, the Android app and docs.
9. The QR link page lives at `/verify/<code>`; the decision is `/report/verify/<code>`.
10. The Firebase API key in the app is not restricted (R-32).

---

## Phase 0 · Safety first (owner, about 1 hour)

**0.1 [YOU] Phase (console.phase.dev).** The one home for every Vayu secret (end-to-end
encrypted; free plan: 3 apps, 3 environments each, 5 members).
- Sign up with the company email (or "Sign in with GitHub"), verify the email.
- Create the **sudo password** (16+ characters, letters and numbers). It unlocks the secrets.
- **Download the account recovery kit.** Print it and keep the paper somewhere safe at the office,
  and save it in the Mac's Passwords app too. Without the sudo password AND the recovery kit, every
  secret in Phase is gone for good: Phase can't recover it.
- Turn on two-step login (authenticator app) for the console.
- Create the organisation, then two apps:
  - `vayu`: its environments **Staging** and **Production** hold the server settings (one key per
    line of the env file); **Development** is unused for now.
  - `vayu-owner`: things that are not server settings (signing key, recovery codes, robot keys).

Two things can't live inside Phase: the Phase sudo password and its recovery kit (they unlock it).
They go on paper and in the Mac's Passwords app, which also keeps the account passwords and the
2-step recovery codes of the other services.

**0.2 [YOU] Move the secrets you already have** into Phase (Mac files and notes are then deleted):
- `vayu-owner` → Production: the Android keystore as text (`base64 -i ~/vayu-keys/vayu-release.jks | pbcopy`,
  paste as `ANDROID_KEYSTORE_B64`), `ANDROID_STORE_PASSWORD`, `ANDROID_KEY_ALIAS` (`vayu`),
  `ANDROID_KEY_PASSWORD`. *If the keystore is lost, the app on every phone can never be updated.*
- `vayu` → Staging / Production: the Firebase service-account JSON (paste the whole file as
  `FIREBASE_SERVICE_ACCOUNT_JSON`), the R2 key pair, the Sentry DSN.
- `vayu-owner`: the Sentry auth token and the web/Android DSNs.

**0.3 [YOU] Two more copies of the keystore**: one on a USB stick kept at the office, one in a
second place you trust (for example a private Google Drive of the company account).

**0.4 [YOU] Turn on two-step login everywhere**: GitHub, Cloudflare, Firebase/Google, Sentry,
the domain registrar, and Phase. Save each account's recovery codes in the Mac's Passwords app.

**0.5 [YOU] Mac check**: System Settings → Privacy & Security → FileVault is **On**.

**0.6 [YOU] An SSH key** (your "door key" for the servers). In Terminal:
```bash
ssh-keygen -t ed25519 -C "vayu-owner"
```
Press Enter for the default file, and type a passphrase (save it in the Mac's Passwords app). Then show the
public half, which is safe to share:
```bash
cat ~/.ssh/id_ed25519.pub
```

Done when: every secret you own is in Phase, the recovery kit is printed, and the loose copies on the Mac are deleted.

---

## Phase 1 · Code changes (Claude, one PR, about 1 day)

All **[CODE]**. One PR, CI must be green. Nothing here needs a server.

| # | Change | Why |
|---|---|---|
| 1.1 | **Web image**: a Dockerfile that builds the web app and puts the files inside a Caddy image. **One image for both servers**: the web app reads which server it is on from its own address (`vayu-staging…` → Sentry label `staging`, else `production`), so nothing is baked in per server. | So Caddy can serve the portal, and rule 2 holds. |
| 1.2 | **Caddyfile**: `/api/*` goes to the API; everything else serves the web app (unknown paths fall back to `index.html`); compression on; long cache for hashed files, no cache for `index.html`. | The portal and the QR page load. |
| 1.3 | **Security headers in Caddy**, CSP included: scripts and styles only from our own address; pictures and uploads only from our address and the R2 address; errors only to Sentry; no framing by other sites. On staging it starts in "report only" mode for a few days, then is enforced. | F-251 / R-29. |
| 1.4 | **QR page moves** to `/report/verify/<code>`. `VERIFY_BASE_URL` becomes `https://vayu.carcid.in/report/verify`. Tests updated. | Owner's decision. No report has been printed with the old path. |
| 1.5 | **New addresses everywhere**: `.env.example`, settings defaults, the Android release URL (`https://vayu.carcid.in/api/v1/`), the text on the Android sign-in help, the load-test example, docs. | Old names would send phones to a dead address. |
| 1.6 | **Compose file** takes the env file as a setting (`.env.staging` or `.env.prod`), pulls ready-made images by tag instead of building on the server, mounts the Firebase JSON read-only, keeps the schedule file and Redis data on a disk, limits log size. Postgres becomes optional (on for staging, off for production). **Worker counts and memory limits come from the env file** (staging: PDF worker 1.5 GB, 2 web workers; production: 6 GB, 4). Workers get 60 seconds to finish their job when stopped. | Gaps 3, 4 and 6. |
| 1.7 | **Database settings**: `DB_SSLMODE` (set to `require` on production) and a kept-open connection, so we stay well under the managed database's connection limit. | Gap 5. |
| 1.8 | **Health checks in compose** for api and workers, and a one-off "migrate" step that runs before the new API starts. | A bad release stops before it takes traffic. |
| 1.9 | **Backup script** `infra/backup.sh`: dump the database, compress, **encrypt** (tool: `age`; the server holds only the locking key, the unlocking key lives in Phase), upload to the backups bucket, delete local copy, then ping the uptime checker ("backup ran"). **Restore script** `infra/restore.sh`: download a dump, unlock it, load it into a **throwaway Postgres container** and print row counts. | §Phase 5. Dumps hold customer names and phone numbers. |
| 1.10 | **Deploy workflow** `.github/workflows/deploy.yml` (details in Phase 4). | Gap 7. |
| 1.11 | **Android "Vayu Staging"**: a `staging` build type: id `in.carcid.vayu.staging`, name "Vayu Staging", a different icon colour, talks to `vayu-staging.carcid.in`, signed with the same key. | Owner's decision. |
| 1.12 | **Runbook rewrite** (`docs/runbook-new-server.md`) to match all of the above, and `docs/accounts-setup.md` corrected. | One true set of instructions. |
| 1.13 | `scripts/local.sh` worker listens on all queues (fresh review, High #1). Tiny, and it lets us rehearse on the Mac. | Local rehearsal works. |
| 1.14 | **Server setup script** `infra/bootstrap.sh`: everything in step 3.1 as one file. Staging and production run the same file. | Hand-typed commands drift; a script does not. |
| 1.15 | **"Workers alive" ping**: a scheduled job that runs every 5 minutes and pings the uptime checker. | If the scheduler, the workers or Redis die quietly, the pings stop and Slack hears about it. |
| 1.16 | **Deploy script** `infra/deploy.sh <commit>` on the server: pull, migrate, restart, wait for health, put the old images back if health fails. The workflow only calls this script. | Lets us lock the robot's key to this one command (4.1). |
| 1.17 | **Load test logs in slowly** (a few users a second, each from its own test login), because sign-in allows 20 tries a minute per address. | Otherwise the test fails on the sign-in limit, not on speed. |
| 1.18 | **Dependabot** for Docker base images and GitHub Actions; actions pinned to exact versions. | Old base images collect security holes. |

Check before the PR: on the Mac, start the production compose file with a throwaway env file and
open `http://localhost` → the portal loads, sign-in works, a QR link opens.

The other new High findings from the fresh review (#2 to #7: resubmit gap, phone files stuck
after Ops close a lead, 50-row lists, API-key switches, PDF never retried, Roles page) are app
fixes. They go in their own fix PR and **must be merged before production gets real users**.
Staging can be built without them.

Two of them matter more once we deploy, because **every deploy restarts the workers**: "a first
PDF that never started is never retried" (High #6) and "interrupted photo checks are never
retried" (Medium). A job cut by a restart is put back in the queue (checked: `acks_late` is on),
but these two are the safety net when that fails. Both are in the production gate (§9).

---

## Phase 2 · Accounts and dashboards (owner, about 2 hours, guided)

Do these in order. After each one, tell Claude "2.3 done" (never the secret itself).

### 2.1 [YOU] Slack channel
Slack → **+** next to Channels → Create channel → name `vayu-alerts` → Create.

### 2.2 [YOU] DigitalOcean account and the staging server
1. cloud.digitalocean.com → sign up with the company email → add a payment card → turn on
   two-step login (My Account → Security).
2. Settings → Security → **Add SSH Key** → paste the public key from step 0.6 → name it `owner-mac`.
3. Top right **Create → Droplets**:
   - Region: **Bangalore (BLR1)**.
   - Image: **Ubuntu 24.04 (LTS) x64**.
   - Size: **Basic → Regular → 2 vCPU / 4 GB** ($24 a month if left on; billed by the hour).
   - Tick **Monitoring** (free). Leave **Backups off**: staging's backup is its snapshot.
   - Authentication: **SSH Key** → tick `owner-mac`. Never choose Password.
   - Hostname: `vayu-staging`. Tags: `vayu-staging` and `vayu-web`.
   - Create. Copy the **IP address** it shows (not a secret; tell Claude).
4. Networking → **Firewalls → Create Firewall** → name `vayu-web`:
   - Inbound: **SSH (22)**, **HTTP (80)**, **HTTPS (443)** from all addresses; delete anything else.
   - Outbound: leave as is. Apply to the **tag** `vayu-web` (not one droplet: then every staging
     droplet made from a snapshot, and production, are covered by themselves). Create.
5. **API → Generate New Token**, name `vayu-owner-laptop`, 90 days, **Full Access** (doctl needs
   droplets, snapshots, SSH keys, tags). Save it in Phase → `vayu-owner` → `DO_API_TOKEN`.
   On the Mac: `brew install doctl`, then `doctl auth init` and paste the token.
   This is what `infra/staging.sh up` / `down` use.

### 2.3 [YOU] DNS record for staging
Log in to the registrar where carcid.in was bought → DNS / Manage DNS → **Add record**:
- Type **A**, Name/Host **`vayu-staging`**, Value **the staging IP**, TTL 600 (or lowest offered).

Do not touch any other record (the company website and email live there). Check after 5 minutes:
```bash
dig +short vayu-staging.carcid.in
```
It should print the staging IP.

### 2.4 [YOU] Cloudflare R2
You already have the buckets. Check and add:
1. dash.cloudflare.com → **R2 Object Storage**. Confirm `vayu-staging` and `vayu-prod` exist and
   are private. **Create bucket** `vayu-backups` (location hint Asia-Pacific), private.
2. On `vayu-staging` and `vayu-prod` → **Settings → CORS policy → Edit**. The allowed origins
   must now be the new addresses:
   - `vayu-staging`: `https://vayu-staging.carcid.in`, `http://localhost:5173`
   - `vayu-prod`: `https://vayu.carcid.in`
   - methods `GET, PUT, POST, HEAD`; allowed headers `*`; expose header `ETag`; max age 3600.
3. On each of the three buckets → **Settings → Object lifecycle rules → Add rule**: "Abort
   incomplete multipart uploads after 7 days". On `vayu-backups` also add "Delete objects after
   35 days".
4. On `vayu-backups` → **Settings → Bucket lock rules → Add rule**: lock all objects for
   **30 days**. Now nobody, not even someone who breaks into the server, can delete a backup
   younger than 30 days. (The 35-day delete rule above then clears old ones.)
5. **Manage API tokens → Create API token**, three times, each **Object Read & Write** and each
   limited to **one bucket**: `vayu-staging-app`, `vayu-prod-app`, `vayu-backups-writer`.
   Each shows an Access Key ID and Secret **once**: save each straight into Phase.
   (One token per server means a leak on staging can never touch production photos.)
6. If an older token covers both buckets, delete it after both servers run on the new ones.

### 2.5 [YOU] Firebase
1. console.firebase.google.com → project `vayu` → gear → **Project settings → General → Add app →
   Android** → package name `in.carcid.vayu.staging` → Register → **download the new
   `google-services.json`** (it now lists both apps) → give that file to Claude (it is not a
   secret; it goes in the Android project).
2. **Project settings → Service accounts → Generate new private key** twice: one file for
   staging, one for production. Save both in Phase. These **are** secrets.
3. **Restrict the API key (R-32).** console.cloud.google.com → pick project `vayu` → **APIs &
   Services → Credentials** → click the key named "Android key (auto created by Firebase)":
   - Application restrictions: **Android apps** → Add: package `in.carcid.vayu` with the SHA-1 of
     the release key, and package `in.carcid.vayu.staging` with the same SHA-1. Get the SHA-1 with:
     ```bash
     keytool -list -v -keystore ~/vayu-keys/vayu-release.jks -alias vayu | grep SHA1
     ```
   - API restrictions: **Restrict key** → tick only **Firebase Installations API** and
     **FCM Registration API** (and **Firebase Cloud Messaging API** if listed).
   - Save. Then test: a push still reaches the phone (Phase 6).

### 2.6 [YOU] Sentry
1. sentry.io → confirm three projects exist: `vayu-server` (Django), `vayu-web` (React),
   `vayu-android` (Android). Create any that are missing (Projects → Create Project).
2. For each: **Settings → Projects → (project) → Client Keys (DSN)** → copy the DSN into Phase.
   The same DSN is used on staging and production; the "environment" label keeps them apart.
3. **Settings → Auth Tokens → Create New Token** with scope `project:releases` (and `org:read`)
   → Phase. Note the **organization slug** (the short name in the URL; not a secret).
4. **Settings → Integrations → Slack → Add Workspace** → allow → then for each project:
   **Alerts → Create Alert → Issues** → "A new issue is created" and "issue seen more than 20
   times in 1 hour" → environment `production` → action "Send a Slack notification to
   `#vayu-alerts`" and email.

### 2.7 [YOU] GitHub
1. Repo → **Settings → Branches → Add branch ruleset** for `main`: require a pull request,
   require status checks to pass (pick the CI jobs), block force pushes. (Fresh review, High #8.)
2. **Settings → Environments → New environment** `staging`. Then another, `production`, and on
   it tick **Required reviewers** → add yourself. This is the Approve button.
3. **Settings → Actions → General → Fork pull request workflows** → choose **Require approval
   for all outside collaborators**. The repo is public: this stops a stranger's PR from running
   our workflows without you looking first.
4. Secrets come in Phase 4, once the server exists.

Done when: Claude can `dig` the staging name and you have, in Phase: 3 R2 key pairs,
2 Firebase JSON files, 3 DSNs, 1 Sentry token.

---

## Phase 3 · Staging server setup (about half a day)

### 3.1 [SERVER] Lock the server down (Claude, over SSH with your approval)
One script does all of this, `infra/bootstrap.sh` (1.14), so production later gets exactly the same:
- Create a user `deploy` (no password, your SSH key), allowed to run Docker. Turn off root login
  and password login for SSH.
- Firewall on the server itself (`ufw`): only 22, 80, 443.
- Automatic security updates (`unattended-upgrades`).
- Install Docker from Docker's own repository. Set log limits so logs can't fill the disk.
- Clock in UTC. A 2 GB swap file on staging (PDF rendering is memory-hungry).

Check: `ssh root@…` is refused; `ssh deploy@vayu-staging.carcid.in` works.

### 3.2 [YOU] Put the secrets on the server
Claude prepares `/srv/vayu/.env.staging` with every non-secret value filled in and each secret
line left as `NAME=`. Then you open it and paste the secrets from Phase:
```bash
ssh deploy@vayu-staging.carcid.in
nano /srv/vayu/.env.staging
```
Lines you fill: `DJANGO_SECRET_KEY` (Claude gives a command that makes a random one on the
server), `DB_PASSWORD` (same), `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `SENTRY_DSN`,
and the backups bucket key pair. Save with Ctrl+O, Enter, Ctrl+X.

For backup encryption Claude gives one command that makes a key pair on your Mac: the
**unlocking** half goes into Phase only (never on a server); the **locking** half is not a
secret and goes in the env file as `BACKUP_PUBLIC_KEY`.

Then the Firebase file, from your Mac:
```bash
scp ~/Downloads/vayu-staging-firebase.json deploy@vayu-staging.carcid.in:/srv/vayu/secrets/firebase-service-account.json
```
Claude then sets both files so only `deploy` can read them (`chmod 600`).

Values Claude sets (not secret): `VAYU_SERVER_KIND=test`, `VAYU_SERVER_NAME=staging-1`,
`APP_HOST=vayu-staging.carcid.in`, `PUBLIC_BASE_URL`, `VERIFY_BASE_URL=https://vayu-staging.carcid.in/report/verify`,
`SENTRY_ENVIRONMENT=staging`, `S3_BUCKET=vayu-staging`.

### 3.3 First start (after Phase 4's pipeline exists)
The first deploy from GitHub brings everything up. Caddy fetches the https certificate by itself
within a minute. Check:
```bash
curl -fsS https://vayu-staging.carcid.in/api/v1/health
```
→ `{"status": "ok"}` (it checks database, Redis, storage and workers).

### 3.4 [SERVER] Forms, staff and test data
```bash
docker compose ... exec api python manage.py setup_platform --users /tmp/staff.csv
docker compose ... exec api python manage.py seed_test_data --confirm staging-1 --password '<from Phase>'
```
Staging is on the open internet and the code is public, so the testers' password is **random**
(`openssl rand -base64 24`), saved in Phase, never a guessable one.
The first adds forms, reports, lists and the test staff. The second adds test bookings; it only
works because this server's kind is `test`.

---

## Phase 4 · The deploy pipeline (Claude + owner, about half a day)

### How a release travels
1. A PR merges to `main`. CI runs (as today).
2. **Build once**: the API image and the web image are built and stored in GitHub's image store
   (GHCR), labelled with the commit id, for example `abc1234`. A merge that only changes `docs/`
   builds and deploys nothing.
3. **Staging deploys by itself**: the workflow logs in to staging as `deploy`, pulls images
   `abc1234`, runs database migrations, restarts the services, waits for the health page to say
   ok. If health fails, it puts the previous images back and the run goes red (Slack alert).
   This is safe because of rule 1 (§1a): the old code still works with the new database.
4. **Production waits** for you. GitHub shows "Review deployments" → you check staging → press
   **Approve**. The workflow then takes a database dump (safety copy), and does the same steps
   on production with the **same images** that staging just proved.
5. **Rollback of code**: Actions → Deploy → **Run workflow** → type the previous commit id →
   Approve. Code goes back in about 3 minutes; the database is left as it is (rule 1 makes that safe
   for one release back).
6. **When a database change itself was wrong** (rare, and the only case where data goes back):
   stop the services, restore the dump taken in step 4 (or "restore to a point in time", §5.3),
   deploy the previous commit, check counts. Everything typed in since that dump is lost, so this
   is the owner's call, not automatic. The runbook carries the exact commands.

### 4.1 [YOU] A separate key for the robot
The pipeline needs its own door key, not yours. Claude gives one command to make it on your Mac;
then:
- Repo → Settings → **Environments → staging → Add secret**: `SSH_KEY` (paste the private half)
  and `SSH_HOST` (`vayu-staging.carcid.in`).
- Repo → Settings → **Secrets and variables → Actions**: `SENTRY_AUTH_TOKEN`, `SENTRY_ORG`.
- Web Sentry DSN: a repo **variable** (not a secret; it is visible in any browser anyway).
- Claude adds the public half to the server, **locked to one command**: this key can only run
  `infra/deploy.sh <commit>`. It cannot open a shell or read the env file. So if the key ever
  leaks, the worst someone can do is redeploy a version we already built.
- Delete the private file from the Mac once it is in GitHub and Phase.
- The deploy workflow runs only for `main` and by hand; never for pull requests.

### 4.2 Prove it
Merge a tiny docs change → watch staging update without anyone touching the server → then run a
rollback to the previous commit and forward again.

---

## Phase 5 · Backups and alerts (about half a day)

### 5.1 What is backed up, and how

| What | Where it lives | Backup | Worst-case loss |
|---|---|---|---|
| Production database | Managed Postgres | DigitalOcean: restore to any minute, last 7 days. Plus our nightly dump in `vayu-backups` (encrypted, locked against deletion for 30 days, kept 35). Plus a dump before every deploy. | Minutes |
| Staging database | Docker on staging | Nightly dump to `vayu-backups/staging/` | 1 day (test data only) |
| Photos, videos, PDFs | R2 | R2 keeps several copies itself. There is **no undo**: a file the app deletes is gone. Only the clean-up job deletes, and the key lives only on the server. Accepted risk. | None expected |
| Server settings (`.env`, Firebase file) | The server | Phase holds every value; the server can be rebuilt from the runbook in about an hour. | None |
| Whole server | Droplet | Staging: its snapshot (the 2 newest are kept). Production: none needed (it holds no data); rebuild with `bootstrap.sh` + one deploy, about 30 minutes. | Nothing |
| Android keystore | Mac | Phase + 2 offline copies (Phase 0) | None |
| Redis (job queue) | Docker | Not backed up. If lost, jobs in flight are redone by the hourly checks. | A few delayed jobs |

### 5.2 [SERVER] Nightly dump
A timer on each server runs `infra/backup.sh` at 02:00 IST (the servers' clocks are UTC, so the
timer says 20:30). Its last line pings the uptime
checker's "heartbeat" address: **if a night passes with no ping, Slack gets "backup missed"**.
A backup that fails silently is the usual way backups fail.

### 5.3 The restore drill (the part most teams skip)
On staging, run `infra/restore.sh` against last night's dump: it loads into a scratch database,
prints counts of bookings, users and files, and we compare them with the live staging numbers.
Then scratch is deleted. **Done once now, and on the first Monday of every month.** Write the
date and the time it took in `docs/runbook-new-server.md`. For production, the drill loads the
production dump into a **throwaway Postgres container on the production server** (customer data
never goes to staging, and the managed database's small disk is not touched).

**Restore to a point in time** (the managed database's own feature) is rehearsed once before
launch, because it does not put data back in place: it makes a **new** database with a new
address. The procedure, also in the runbook:
1. DigitalOcean → Databases → `vayu-prod-db` → Backups → **Restore from backup** → pick the minute.
2. On the new cluster: Trusted sources → add `vayu-prod`.
3. On the server: change `DB_HOST` in `.env.prod` to the new address, run a deploy of the same commit.
4. Check booking and user counts, then destroy the old cluster (after a day, not at once).

### 5.4 [YOU] Uptime checks
1. betterstack.com (Better Stack Uptime, free plan) → sign up with the company email.
2. **Monitors → Create monitor**: URL `https://vayu-staging.carcid.in/api/v1/health`, check every
   1 minute, alert when the response does not contain `ok`. Later the same for production, plus
   one for `https://vayu.carcid.in/` (the portal page itself). It also warns before the https
   certificate expires.
3. **Heartbeats → Create heartbeat** `staging-backup`, expected every 1 day, grace 3 hours. Copy
   its URL into `.env.staging` as `BACKUP_HEARTBEAT_URL` (treat as a secret). Same later for production.
4. **Heartbeats → Create heartbeat** `staging-workers`, expected every 5 minutes, grace 10
   minutes → URL into the env file as `WORKERS_HEARTBEAT_URL` (1.15). Same later for production.
5. **Integrations → Slack** → send to `#vayu-alerts`. Add your email and phone as on-call contact.

### 5.5 [YOU] Server alerts
DigitalOcean → **Monitoring → Create alert policy**, four policies, applied to both droplets,
sent to email and Slack (`#vayu-alerts`):
- Disk used above 80% for 5 min.
- Memory used above 90% for 10 min.
- CPU above 90% for 10 min.
- (Production database) Databases → your cluster → **Alerts**: disk above 80%, connections above 80%.
  The 1 GB database allows about 22 connections and we use about 14 (4 web, 7 workers, scheduler,
  backup). Adding a worker later means moving to the 2 GB size first.

### 5.6 What a normal bad day looks like
- *Slack says "vayu.carcid.in is down".* Open Actions: did a deploy just run? → roll back (§Phase 4).
  If not, `ssh` in, `docker compose ps`, read the unhealthy service's log; the runbook has the list.
- *Slack says "disk 80%".* Usually Docker images: `docker image prune`. The deploy also prunes old ones.
- *Sentry says "new issue".* Read it; it names the screen and the release. Fix forward, or roll back if many users hit it.

---

## Phase 6 · Prove staging (about 1 day)

Staging is "done" only when all of these pass. Each is a line in the runbook's check list.

1. **Web**: sign in as Admin, Ops and Expert test users. Create a booking, assign it.
2. **Phone**: build "Vayu Staging" (version code 3 or higher; the phone has 2), publish it with
   `publish_apk`, download it from the portal's APK page on the phone, sign in, do one inspection
   with photos and a video, submit. The booking completes, the PDF appears, the QR opens
   `https://vayu-staging.carcid.in/report/verify/<code>`.
3. **Push**: assign a booking → the phone gets the notification (proves the restricted Firebase key works).
4. **Update prompt**: publish a build with a higher version code → the app offers the update.
5. **Sentry**: Claude triggers one test error in server, web and app → three issues appear,
   labelled `staging`, with readable code lines → the Slack alert arrives.
6. **Security headers**: securityheaders.com and SSL Labs both grade **A** for the staging address.
   The CSP report shows nothing blocked during steps 1 and 2 → switch CSP from "report only" to enforced.
7. **Load test**: the realistic test in `docs/plan-load-test.md` (owner's numbers: 50 experts,
   5 Ops, 100 inspections and 200 bookings a day, external API at 100 calls/min, 15 webhooks per
   booking), run at 1 vCPU / 2 GB, 2 vCPU / 2 GB and 2 vCPU / 4 GB. Production gets the cheapest
   size that passes.
8. **Backup and restore drill** passed (5.3).
9. **Rollback** rehearsed (4.2).
10. **Reboot test**: restart the droplet from the DigitalOcean dashboard → everything comes back
    by itself within 2 minutes, health is ok.
11. **On-demand cycle**: `infra/staging.sh down`, then `up`, update DNS → health is ok, test data
    and https certificate are still there.

---

## Phase 7 · Production (about half a day, after Phase 6 and Phase 0 are fully done)

Same steps as staging, with these differences.

### 7.1 [YOU] Production server
Create → Droplets → BLR1, Ubuntu 24.04, **the size the load test chose** (`docs/plan-load-test.md`
§6; 2 vCPU / 4 GB until it has run), Monitoring ticked (Backups not needed: this server holds no data), your SSH key,
hostname `vayu-prod`, tag `vayu-web` (the firewall then covers it). Tell Claude the IP. Claude runs the same `infra/bootstrap.sh` as on staging.

### 7.2 [YOU] Managed database
Create → **Databases** → PostgreSQL **16** → region **BLR1** → Basic, **1 GB / 1 vCPU** ($15; grow
later with two clicks, no downtime worth noting) → name `vayu-prod-db` → Create. Then:
- **Settings → Trusted sources** → add droplet `vayu-prod` only. Now nothing else on the internet
  can even reach it.
- **Users & Databases** → add database `vayu` and user `vayu`. Copy the password to Phase.
- **Connection details** → choose **VPC network** (the private address) → note host and port
  (not secret; tell Claude).
- **Settings → Maintenance window** → Sunday, 21:30 UTC (3 am Monday IST).

### 7.3 [YOU] DNS
Registrar → Add record: Type **A**, Name **`vayu`**, Value **production IP**, TTL 600.

### 7.4 Env file
As 3.2, into `/srv/vayu/.env.prod`. Differences: `VAYU_SERVER_KIND=production`,
`VAYU_SERVER_NAME=prod-1`, `APP_HOST=vayu.carcid.in`, `S3_BUCKET=vayu-prod` with the
`vayu-prod-app` key, `DB_HOST`/`DB_PORT` of the managed database, `DB_SSLMODE=require`,
`SENTRY_ENVIRONMENT=production`, its own new `DJANGO_SECRET_KEY`, the production Firebase file.
**No secret is shared between staging and production.**

### 7.5 GitHub
Environments → `production` → secrets `SSH_KEY` (a new robot key, not staging's, locked to the
deploy command the same way) and `SSH_HOST`.

### 7.6 First production deploy
Actions → Deploy → Approve. Then `setup_platform --users` with the **real staff file** (the owner
writes it; passwords it makes are handed out and the file deleted, as the runbook says).
`seed_test_data` is never run here; the server refuses it anyway.

### 7.7 Production checks
Repeat Phase 6 items 1 to 6, 8 and 10 on production with one real-looking test booking, then
cancel that booking. Build the **release** Android app (`in.carcid.vayu`, version code higher
than any earlier build, release Sentry DSN, mapping uploaded) and publish it with `publish_apk`.
Add the production uptime monitors, backup heartbeat and alert policies (5.4, 5.5).

Production is now ready and empty of real work. Opening it to the team is the launch plan.

---

## 8. Secrets: what exists and where each one lives

| Secret | Made at | Lives in (besides Phase) |
|---|---|---|
| `DJANGO_SECRET_KEY` (one per server) | made on the server | server env file |
| Database password (one per server) | server / DigitalOcean | server env file |
| R2 key pairs: staging app, prod app, backups | Cloudflare | server env file |
| Firebase service-account JSON (one per server) | Firebase | `/srv/vayu/secrets/` on the server |
| Sentry DSNs (server, web, Android) | Sentry | server env file; GitHub repo variable (web; not really secret); build machine (Android) |
| Backup unlocking key | your Mac | **Phase only** (`vayu-owner`), never on a server |
| Sentry auth token | Sentry | GitHub secret; build machine (Android) |
| Robot SSH keys (one per server) | your Mac | GitHub environment secret |
| Backup and workers heartbeat URLs | Better Stack | server env file |
| Android keystore + passwords | your Mac | `~/vayu-keys/` + 2 offline copies |
| Owner SSH key | your Mac | `~/.ssh/` |

Changing a leaked secret: make a new one in its dashboard, paste it in the place above, redeploy,
delete the old one. Each line above is independent, so one leak means one change.

## 9. Order and time

| Phase | Who | Time | Needs |
|---|---|---|---|
| 0 Safety | Owner | 1 h | nothing |
| 1 Code PR | Claude | 1½–2 days | nothing (can run alongside 0 and 2) |
| 2 Accounts | Owner, guided | 2 h | Phase 0 |
| 3 Staging server | Claude + owner for secrets | ½ day | 1, 2 |
| 4 Pipeline | Claude + owner for secrets | ½ day | 3 |
| 5 Backups and alerts | Claude + owner | ½ day | 4 |
| 6 Prove staging | Claude + owner's phone | 1 day | 5 |
| 7 Production | Both | ½ day | Phase 0 done, Phase 6 passed, fix PR merged (Highs #2–#7 and the "interrupted photo check" retry) |

**6 to 8 working days** end to end. Five is the best case; first-time dashboard work and DNS
waits usually add a day or two.

## 10. Done when

- A merge to `main` reaches staging with nobody touching a server, and production after one Approve.
- Both health pages say ok and are watched every minute; a test outage reaches `#vayu-alerts`.
- A restore from backup has been done and timed, on staging and on production.
- All ten staging checks (Phase 6) pass, and the production checks (7.7) pass.
- Every secret is in Phase, none is in git, chat or a loose file.
- `docs/runbook-new-server.md` describes exactly what was done.

## 11. Not in this plan

- Moving off Clappia, the parallel run, staff training, go-live day, rollback of the launch itself.
- The app fixes from the fresh review (Highs #2 to #7 and the Mediums): separate fix PR.
- Device time and GPS time (the owner handles that separately).
- A support contact line (not needed now).
- A second server or automatic failover. One server with fast restore is right for this size;
  revisit if a one-hour outage becomes unacceptable.
- Cloudflare in front of the site (DNS stays at the registrar). Revisit if we see attack traffic.
- A central log store. Logs stay on each server (size-limited, about a week) and errors go to
  Sentry. Revisit the first time we can't answer "what happened at 3 pm last Tuesday".
- Zero-downtime deploys. A 10 to 20 second blip outside working hours is fine at this size.

## 12. After launch (small, but do them)

- Make the GitHub repo private (check CI minutes: free private repos get 2,000 a month), ideally
  under a company organization.
- Add a second owner to DigitalOcean, Cloudflare, Firebase, Sentry, GitHub, the registrar and
  Phase, and a second SSH key on both servers.
- Monthly: restore drill, apply server updates that need a reboot, look at disk and database size.
- Remove the `http://localhost:5173` origin from the staging bucket's CORS if it is no longer used.
