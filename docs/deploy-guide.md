# Deployment guide: Vayu from zero to production

A step-by-step handbook for **anyone**, including someone who has never seen this project. Follow it
top to bottom. Every step says **where** to click or what to type, **why**, and **how to check** it
worked.

Other documents:
- `docs/deploy-setup-log.md`: the diary of how it was actually done the first time, with every
  problem met and the live list of **where everything lives** (all secret names, accounts, addresses).
- `docs/runbook-new-server.md`: the exact server commands (deep reference).
- `docs/plan-deploy.md`: why it is built this way.

Marks used here: **[OWNER]** only the owner can do it (payments, account owners) · 🧪 planned but not
done yet on the real servers: follow it, then fix this guide where reality differs.

**The one rule: a secret (password, key, token) never goes into chat, git, a document or a loose file.**
It goes from the website that shows it straight into **Phase** (console.phase.dev), and from Phase
to where it is used. The repo is public.

---

## 0. What you are building

```
   phones (Android app) / browsers
                │ https
   ┌────────────▼────────────────────┐
   │ Caddy: https, security headers  │   one DigitalOcean server per environment
   │   /api/*  → Django API          │   (2 vCPU / 4 GB, Bangalore)
   │   rest    → web app files       │
   │ workers: uploads, ZIPs, PDFs    │
   │ scheduler, Redis                │
   └──────┬──────────────────┬───────┘
          │                  │
   Postgres                Cloudflare R2
   (staging: on the server; (photos, videos, PDFs,
    production: managed)     encrypted backups)
```
Around it: **GitHub Actions** builds and deploys; **Phase** holds every setting and secret; **Sentry**
collects errors; **DigitalOcean** alerts watch the server; **Firebase** sends phone notifications;
everything alarms into Slack **#vayu-alerts**.

| | Staging | Production |
|---|---|---|
| Address | `https://vayu-staging.carcid.in` | `https://vayu.carcid.in` |
| Runs | only while testing (on demand) | always |
| Gets new code | by itself after every merge to `main` | after someone presses **Approve** |
| Database | Postgres on the server | DigitalOcean managed Postgres |

Cost: about **$43–46 a month** plus GST (production server $24, managed database $15, staging a few
dollars because it only runs about a week a month; R2, Sentry, Phase and the uptime checker are on
free plans).

---

## 1. Before you start

### 1.1 Access you need
If the accounts already exist (they do for Vayu), the owner invites you. Ask for:

| Service | Invite to | Why you need it |
|---|---|---|
| GitHub `ravi409455/vayu` | collaborator (admin to approve production) | code, CI, deploys |
| Phase (console.phase.dev, org `CarCID`) | member of apps `vayu`, `vayu-owner` | all settings and secrets |
| DigitalOcean | team member | servers, alerts |
| Cloudflare | member with R2 access | file storage |
| GoDaddy (carcid.in) | delegate access | DNS records |
| Sentry (org `car-cid`) | member | errors |
| Firebase project `vayu-8bb7a` | member | phone notifications |
| Slack "Car C.I.D" | channel `#vayu-alerts` | alarms |

Turn on **two-step login** (an authenticator app, not SMS) on every one of them, and save each
account's recovery codes in your password manager.

Your SSH key must also be on the servers: send the owner your **public** key (step 1.3) and they add
it (DigitalOcean → Settings → Security → Add SSH Key, and on each server
`/home/deploy/.ssh/authorized_keys`).

### 1.2 Tools on your Mac
```bash
brew install gh doctl age git
brew install --cask docker              # Docker Desktop (local stack, tests)
brew install openjdk@17                 # Android builds
gh auth login                           # GitHub on the command line
doctl auth init                         # DigitalOcean: paste the API token from Phase (vayu-owner → DO_API_TOKEN)
git clone https://github.com/ravi409455/vayu.git && cd vayu
```
Check: `gh auth status`, `doctl account get` (says `active`), `docker info` (no error).

### 1.3 Your SSH key (your door key to the servers)
```bash
ssh-keygen -t ed25519 -C "<your name>"   # Enter for the default file; type a passphrase
cat ~/.ssh/id_ed25519.pub                # the PUBLIC half: safe to send to the owner
```
Never share `~/.ssh/id_ed25519` (no `.pub`).

### 1.4 Copying secrets safely (read this once)
Most secrets are made with a command that copies them to the clipboard. Two traps we fell into:
1. **`… | pbcopy` adds a hidden line break** at the end. Use `print(..., end='')` in Python, or
   remember that `infra/secrets.sh` trims spaces and line breaks around values (names never).
2. **Phase stores nothing until you click Deploy.** A pasted value shows in the editor (and even
   copies back out) but does not exist for the servers until **Deploy**.

After pasting, always clear the clipboard: `pbcopy < /dev/null`.

---

## 2. Accounts and dashboards (once per project)

Skip any step that is already done for your project (check the "Where everything lives" table in
`docs/deploy-setup-log.md`).

### 2.1 Phase: the home of every secret **[OWNER]**
1. console.phase.dev → sign up with the company email → verify the email.
2. Create the **sudo password** (16+ characters). Save it in your password manager.
3. **Download the account recovery kit**: print it (keep it at the office) and save it in the
   password manager. ⚠️ Lose both the sudo password and the kit and every secret is gone for good.
4. Two-step login on.
5. Organisation `CarCID`. Two apps:
   - `vayu`: environments **Development** (the Mac), **Staging**, **Production** = each server's settings.
   - `vayu-owner`: things that are not server settings (signing key, tokens, robot keys, backup
     unlocking key). Keep them in its **Production** environment.

### 2.2 Slack channel
Slack → **+** next to Channels → Create channel → `vayu-alerts`, **public** (then Sentry and other
tools can post without an invite).

### 2.3 DigitalOcean **[OWNER]** (account, card)
1. cloud.digitalocean.com → two-step login on.
2. **Settings → Security → Add SSH Key**: your public key, named after you (the owner's is `owner-mac`).
3. **Networking → Firewalls → Create Firewall** `vayu-web`:
   - Inbound: **SSH 22**, **HTTP 80**, **HTTPS 443**, all IPv4 + IPv6. Nothing else.
   - Outbound: leave the defaults.
   - Apply to the **tag** `vayu-web` (not a droplet): every server with that tag is covered,
     including staging re-made from a snapshot.
   - Why so few ports: the database, Redis and the app's internal port are then unreachable from
     outside. SSH stays open to all because GitHub deploys from changing addresses; the servers only
     accept keys, never passwords.
4. **API → Generate New Token** `vayu-owner-laptop`, 90 days, Full Access → Phase `vayu-owner` →
   `DO_API_TOKEN`. Note the expiry date in the setup log.
5. **Alerts** (Insights → Alerts → Alert Rules): four rules, resource type **Droplets**, resource
   **tag `vayu-web`** (the form defaults to *All Droplets*: change it), channel Slack
   `#vayu-alerts`, re-notify every 4 hours: CPU ≥ 80% for 10 min, memory ≥ 85% for 10 min,
   disk ≥ 80% for 5 min, load (5 min) ≥ 3 for 10 min. Make them in the web form, not with `doctl`
   (it only knows the old alert system).

### 2.4 Cloudflare R2 (file storage) **[OWNER]** (card)
dash.cloudflare.com → **R2 Object Storage**.
1. Buckets, all **private** (no public access, no custom domain), location hint Asia-Pacific:
   `vayu-staging`, `vayu-prod`, `vayu-backups`.
2. **CORS** (bucket → Settings → CORS Policy). `vayu-staging` (for `vayu-prod` use `https://vayu.carcid.in`):
   ```json
   [{"AllowedOrigins": ["https://vayu-staging.carcid.in"],
     "AllowedMethods": ["GET", "PUT", "POST", "HEAD"], "AllowedHeaders": ["*"],
     "ExposeHeaders": ["ETag"], "MaxAgeSeconds": 3600}]
   ```
   `vayu-backups` needs none. (Without CORS, uploads from the web portal fail.)
3. **Object lifecycle rules** (bucket → Settings):
   - `vayu-staging`, `vayu-prod`: `abort-unfinished-uploads`, abort incomplete multipart uploads
     after **14 days**; do NOT delete objects (the app decides).
   - `vayu-backups`: `expire-backups`, delete objects after **35 days**, abort incomplete uploads
     after 1 day.
4. **Bucket lock rule** on `vayu-backups`: `keep-30-days`, all objects, retention **30 days** (not
   indefinite). Now nobody, not even someone who breaks into a server, can delete a backup younger
   than 30 days.
5. **Manage API tokens → Create Account API token**, four times, each **Object Read & Write** on
   **one** bucket, TTL forever, no IP filter. The page shows the keys once: copy straight into Phase.

   | Token | Bucket | Phase (`vayu` →) | Key names |
   |---|---|---|---|
   | `vayu-staging-app` | `vayu-staging` | Staging | `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY` |
   | `vayu-prod-app` | `vayu-prod` | Production | same names |
   | `vayu-backups-staging` | `vayu-backups` | Staging | `BACKUP_ACCESS_KEY_ID`, `BACKUP_SECRET_ACCESS_KEY` |
   | `vayu-backups-prod` | `vayu-backups` | Production | same names |

   The page also shows the **S3 API endpoint** `https://<account id>.r2.cloudflarestorage.com`:
   Phase `vayu` → Staging and Production → `S3_ENDPOINT_URL`.

### 2.5 Firebase (phone notifications)
console.firebase.google.com → project `vayu-8bb7a` → gear → **Project settings**.
1. **General → Add app → Android** `in.carcid.vayu.staging` ("Vayu Staging"; the real app
   `in.carcid.vayu` already exists) → download `google-services.json` (not a secret) → it goes in
   `android/app/` through a PR.
2. **Service accounts → Generate new private key**, once per server (staging, production). Each JSON
   file → Phase `vayu` → that environment → `FIREBASE_SERVICE_ACCOUNT_JSON` (paste the whole file)
   → **Deploy** → delete the downloaded file.
3. 🧪 **Restrict the API key** (console.cloud.google.com → APIs & Services → Credentials → the
   "Android key"): Android apps `in.carcid.vayu` and `in.carcid.vayu.staging` with the release key's
   SHA-1; APIs Firebase Installations and FCM Registration only. Do it when the staging app is on a
   phone, then check a notification still arrives.

### 2.6 Sentry (errors)
sentry.io, organisation `car-cid`.
1. Projects `vayu-server` (Django), `vayu-web` (React), `vayu-android` (Android). Each project's
   **Client Keys (DSN)** → Phase: server DSN → `vayu` Staging and Production `SENTRY_DSN`; web →
   `vayu-owner` `SENTRY_DSN_WEB`; Android → `vayu-owner` `SENTRY_DSN_ANDROID`.
2. **Settings → Developer Settings → Organization Tokens** → `vayu-ci` → Phase `vayu-owner` →
   `SENTRY_AUTH_TOKEN` (builds upload readable stack traces with it).
3. **Settings → Integrations → Slack** → connect the workspace.
4. One alert for all three projects: Alerts → New Alert → "Alert on all issues in selected
   projects" (the three `vayu-*`, not all projects), environment **production**, WHEN "A new issue is
   created" or "An issue escalates", THEN Slack `#vayu-alerts` + email. **Send Test Notification**.
   (Error "vayu-alerts does not exist": create the channel, or `/invite @Sentry` if it is private.)

### 2.7 GitHub settings (repo → Settings) **[OWNER]**
1. **Rules → Rulesets → New branch ruleset** `main protect`, Active, default branch, empty bypass:
   restrict deletions, block force pushes, require status checks (`backend`, `backend-gates`, `web`,
   `android`, `docker`, `e2e`). ⚠️ Leave **Restrict updates** OFF (with an empty bypass list nobody
   could change `main` at all).
2. **Environments**: `staging` (deployment branches: `main`) and `production` (`main`, **Required
   reviewers**: whoever may approve releases; click **Save protection rules**).
3. **Actions → General**: "Require approval for all external contributors".
4. **Secrets and variables → Actions**: variables `SENTRY_ORG` = `car-cid`, `VITE_SENTRY_DSN` = the
   web DSN; secret `SENTRY_AUTH_TOKEN`.

### 2.8 Two offline copies of the Android signing key **[OWNER]**
The key `vayu-release.jks` signs every app build. **If it is lost, no phone can ever update the app
again.** Copies: Phase `vayu-owner` (`ANDROID_KEYSTORE_B64` = `base64 -i vayu-release.jks`, plus
`ANDROID_STORE_PASSWORD`, `ANDROID_KEY_ALIAS`, `ANDROID_KEY_PASSWORD`), a USB stick at the office, a
private company drive folder. Check each copy: `shasum -a 256 <file>` gives the same fingerprint.

---

## 3. Settings in Phase (once per environment)

Each server reads **all** its settings from Phase at every deploy (`infra/secrets.sh`). Nobody edits
a settings file on a server.

### 3.1 Non-secret values
Phase → app `vayu` → **New Secret → Import secrets** → paste the file → choose the one environment →
**Preview Import** → **Deploy**:
- Staging: `infra/phase-staging.env`
- Production: `infra/phase-production.env` (fill `DB_HOST` when the managed database exists, §6.2)

### 3.2 Secrets you make yourself
Each command copies a new random value; paste into Phase → that environment → **Deploy**.

| Key | Command |
|---|---|
| `DJANGO_SECRET_KEY` | `python3 -c "import secrets;print(secrets.token_urlsafe(50),end='')" \| pbcopy` |
| `DB_PASSWORD` (staging) | same command, a new value (production: the managed database's password) |
| `STAGING_TESTER_PASSWORD` (staging only) | `python3 -c "import secrets;print(secrets.token_urlsafe(24),end='')" \| pbcopy` |

The backup key pair (once for the project):
```bash
age-keygen 2>/dev/null | grep AGE-SECRET-KEY | tr -d '\n' | pbcopy
```
→ Phase `vayu-owner` → `BACKUP_AGE_SECRET_KEY` (**never on a server**: it unlocks every backup). Then:
```bash
pbpaste | age-keygen -y | tr -d '\n' | pbcopy
```
→ Phase `vayu` → Staging **and** Production → `BACKUP_PUBLIC_KEY` (it only locks). Then `pbcopy < /dev/null`.

### 3.3 Check
An environment is complete when it holds the imported values plus: `DJANGO_SECRET_KEY`,
`DB_PASSWORD`, `SENTRY_DSN`, `S3_ENDPOINT_URL`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`,
`BACKUP_ACCESS_KEY_ID`, `BACKUP_SECRET_ACCESS_KEY`, `BACKUP_PUBLIC_KEY`,
`FIREBASE_SERVICE_ACCOUNT_JSON` (and `STAGING_TESTER_PASSWORD` on staging). A missing required
value stops a deploy before anything changes, with its name in the error.

### 3.4 The server's own Phase key
Phase → **Access Control → Service Accounts → Create Service Account** `vayu-staging-server` (role
Service) → app `vayu` → **Access → Service accounts → Add service account** → environment
**Staging only** → back in Service Accounts → **Manage → + Create Token** → copy the
`pss_service:v2:…` token → Phase `vayu-owner` → `PHASE_TOKEN_STAGING_SERVER`. (Production:
`vayu-prod-server`, Production only.) Note an expiry date if you set one.

---

## 4. The staging server

### 4.1 Create it
1. DigitalOcean → **Create → Droplets**: region **Bangalore (BLR1)**, **Ubuntu 24.04 LTS**, Basic →
   Regular → **2 vCPU / 4 GB**, Monitoring on, Backups **off**, authentication **SSH key** (never a
   password), hostname `vayu-staging`, tags **`vayu-staging`** and **`vayu-web`**. Copy its IP.
2. GoDaddy → My Products → carcid.in → **DNS → Add New Record**: type **A**, name `vayu-staging`,
   value the IP, TTL **600 seconds**. Touch no other record. Check after a few minutes:
   `dig +short vayu-staging.carcid.in` prints the IP.

### 4.2 Set it up (once, about 5 minutes)
```bash
ssh -o StrictHostKeyChecking=accept-new root@<ip> true            # first contact: trust its key
ssh root@<ip> 'bash -s' < infra/bootstrap.sh
```
It installs updates and Docker, a firewall, automatic security updates, the user `deploy`, swap, the
code in `/srv/vayu` and the nightly backup timer, then locks root and passwords out.
Check: `ssh root@<ip> true` is refused; `ssh deploy@<ip> 'docker ps'` works.

### 4.3 The server's Phase key
```bash
ssh deploy@<ip>
umask 077 && nano /srv/vayu/.phase
```
Type two lines, save (Ctrl+O, Enter, Ctrl+X), `exit`:
```
PHASE_ENV=Staging
PHASE_SERVICE_TOKEN=<PHASE_TOKEN_STAGING_SERVER from Phase>
```
⚠️ Type these **in the server's terminal**: a command typed into Claude's chat runs on your Mac.
Check: `ssh deploy@<ip> 'bash /srv/vayu/infra/secrets.sh'` → "settings: N values from Phase".

### 4.4 GitHub's deploy key (the robot)
A key only GitHub uses, locked so it can **only** run the deploy script.
```bash
K=$(mktemp -d) && ssh-keygen -q -t ed25519 -N "" -C github-deploy-staging -f "$K/key"
ssh deploy@<ip> "echo 'command=\"/srv/vayu/infra/deploy.sh\",restrict $(cat $K/key.pub)' >> ~/.ssh/authorized_keys"
ssh-keyscan -t ed25519 <ip> 2>/dev/null | sed 's/^[^ ]*/vayu-staging.carcid.in/' > "$K/known_hosts"
gh secret set SSH_KEY --env staging --repo ravi409455/vayu < "$K/key"
gh secret set SSH_HOST --env staging --repo ravi409455/vayu --body vayu-staging.carcid.in
gh secret set SSH_KNOWN_HOSTS --env staging --repo ravi409455/vayu < "$K/known_hosts"
pbcopy < "$K/key"      # → Phase vayu-owner → DEPLOY_SSH_KEY_STAGING → Deploy
pbcopy < /dev/null; rm -r "$K"
```
Check: `gh secret list --env staging --repo ravi409455/vayu` lists the three names.

### 4.5 First deploy
GitHub → **Actions → deploy → Run workflow** → the full commit id of the newest `main`
(`git rev-parse origin/main`). Or merge anything to `main`: it deploys by itself.
The run's **production** step then waits for Approve: until production exists, **cancel** it.
Check:
```bash
curl -s https://vayu-staging.carcid.in/api/v1/health      # {"status":"ok"}
ssh deploy@<ip> 'cat /srv/vayu/.deployed; docker ps --format "{{.Names}}: {{.Status}}"'
```
`.deployed` = the commit you deployed; 8 containers up (api healthy, worker, zip-worker, pdf-worker,
beat, postgres, redis, caddy). The https certificate is made by itself.

### 4.6 Forms, test logins and test bookings (staging only, about 20 minutes)
```bash
ssh -o ServerAliveInterval=30 deploy@<ip> 'cd /srv/vayu && bash infra/secrets.sh >/dev/null && source infra/lib.sh && export VAYU_TAG=$(cat .deployed) P=$(envval STAGING_TESTER_PASSWORD) && compose exec -T -e P api sh -c "python manage.py seed_test_data --confirm staging-1 --password \"\$P\""'
```
It sets up every form, report and list and makes logins `admin`, `ops`, `ops2`, `expert` …
`expert7` (password: Phase `STAGING_TESTER_PASSWORD`) and 30 bookings in every stage. It refuses on
production. ⚠️ While it runs, do not deploy (a deploy restarts the API and cuts it off) and do not
look at full process lists (`ps`, `docker top`): the password is visible there.

### 4.7 Staging on demand (saves money)
A switched-off server is still billed, so staging lives as a snapshot between test rounds:
```bash
infra/staging.sh down     # power off → snapshot → delete (asks you to type "staging")
infra/staging.sh up       # re-create from the newest snapshot; prints the new IP
infra/staging.sh status
```
After `up`: update the GoDaddy A record to the new IP (the script waits until DNS shows it), then run
the deploy workflow for the newest `main` commit. Everything else is in the snapshot.
While staging is down, merges still build but the staging deploy fails and production waits.

---

## 5. Everyday work

### 5.1 How a change reaches the servers
1. A PR merges into `main` (only through a PR with green checks).
2. CI runs on `main`; when it passes, the **deploy** workflow builds the images **once** (labelled
   with the commit id) and deploys them to **staging** by itself.
3. Check staging. To release: open the run, **Review deployments → production → Approve**. The
   **same** images go to production (after a database safety copy).
- Merges close together: only the newest deploys (it contains the earlier ones).
- Each deploy restarts the services: 10–20 s of errors that apps retry. Release outside 9 am–8 pm.
- If health fails after a deploy, the server puts the previous version back by itself and the run
  goes red.

### 5.2 Roll back
GitHub → Actions → deploy → **Run workflow** → the full commit id to go back to (from Actions
history, or `ssh deploy@<server> cat /srv/vayu/.deployed` before the release). About 3 minutes; the
images are reused, never rebuilt. The database is not rolled back (every migration must also work
with the previous release). Data damaged by a migration: `docs/runbook-new-server.md` §5.

### 5.3 Change a setting or secret
Change it in Phase → **Deploy** (in Phase) → GitHub → Actions → deploy → Run workflow → the commit
that is live now. The server fetches the new value and restarts.

### 5.4 Look at a server
```bash
ssh deploy@<server>
cd /srv/vayu && source infra/lib.sh && export VAYU_TAG=$(cat .deployed)
compose ps                       # what runs
compose logs --tail 100 api      # or worker, zip-worker, pdf-worker, beat, caddy
docker stats --no-stream         # CPU and memory per service
cat .deployed                    # live commit
```

### 5.5 The Android app 🧪
Build on a Mac with the signing key in `~/vayu-keys/` (`vayu-release.jks`, `keystore.properties`),
`SENTRY_DSN_ANDROID` and `SENTRY_AUTH_TOKEN` set. The version code must be higher than every build
ever installed:
```bash
cd android
./gradlew assembleStaging -Pvayu.versionCode=<n> -Pvayu.versionName=<x.y.z>   # "Vayu Staging" (blue icon)
./gradlew assembleRelease -Pvayu.versionCode=<n> -Pvayu.versionName=<x.y.z>   # "Vayu"
```
Publish it on its server: `docs/runbook-new-server.md` §3 (`publish_apk`). Then the welcome pages'
**Download the app** button (`/welcome/engineers`, `/welcome/ops`) and the in-app update offer it.

### 5.6 Staff accounts on production 🧪
`docs/runbook-new-server.md` §2 (`setup_platform --users staff.csv`); passwords it makes are handed
out once, then the file is deleted. A person stuck with "your other phone still has work": an Admin
signs that phone out (web → Users → ⋯ → **Sign out of every device**).

---

## 6. Production 🧪 (not built yet)

Same as staging, with these differences. Do it only after staging passed its checks
(`docs/plan-deploy.md` Phase 6).
1. **Droplet** `vayu-prod`: BLR1, Ubuntu 24.04, 2 vCPU / 4 GB (8 GB if the load test said so),
   Monitoring on, Backups off (it holds no data), SSH key, tag **`vayu-web`** only.
2. **Managed database** (Create → Databases): PostgreSQL 16, BLR1, 1 GB, name `vayu-prod-db` →
   Trusted sources: droplet `vayu-prod` only → Users & Databases: database `vayu`, user `vayu` →
   password → Phase `vayu` → Production `DB_PASSWORD`; the **private (VPC)** host → `DB_HOST`,
   port `DB_PORT` (25060) → Maintenance window Sunday 21:30 UTC.
3. **Phase Production** complete (§3; its own `DJANGO_SECRET_KEY`), service account
   `vayu-prod-server` (Production only).
4. **DNS**: A record `vayu` → production IP.
5. §4.2–4.5 with `PHASE_ENV=Production`, `github-deploy-prod`, the `production` environment's
   secrets and host `vayu.carcid.in`. The first production deploy needs **Approve**.
6. Staff (`setup_platform --users`), never `seed_test_data`. Publish the release app.
7. Better Stack uptime checks and heartbeats (§7), Sentry alert check, restore drill (§7).

---

## 7. Backups and alerts

| What | How | Status |
|---|---|---|
| Server CPU / memory / disk / load | DigitalOcean alerts → `#vayu-alerts` (§2.3) | ✅ staging |
| App errors | Sentry alert, production only (§2.6) | ✅ |
| Nightly database backup 02:00 IST | `vayu-backup.timer` → `infra/backup.sh` → encrypted to R2 | ✅ timer on; 🧪 first check |
| Site down / backup missed / workers stopped | Better Stack: uptime check of `/api/v1/health` every minute; heartbeats `BACKUP_HEARTBEAT_URL`, `WORKERS_HEARTBEAT_URL` (into Phase) → Slack | 🧪 |
| Restore drill (first Monday of the month) | `infra/restore.sh <name>` on the server: loads a backup into a throwaway database and compares row counts; asks for `BACKUP_AGE_SECRET_KEY` | 🧪 first drill |

Check a backup ran: `ssh deploy@<server> 'systemctl list-timers vayu-backup.timer; journalctl -u vayu-backup.service -n 20'`.

---

## 8. When something goes wrong

| You see | Why | Do |
|---|---|---|
| Deploy step "error: missing in Phase: X" | X is not in that Phase environment, or was never **Deployed** | add X in Phase → Deploy → re-run the workflow |
| "X has a line break or a '" | a pasted value with a newline inside | fix the value in Phase |
| Deploy fails "could not fetch from Phase" | wrong or expired server token, or Phase down | check `/srv/vayu/.phase`; the last good settings stay meanwhile |
| Staging deploy fails at SSH | staging is switched off (on demand) | `infra/staging.sh up`, update DNS, re-run |
| The run waits forever on **production** | production needs Approve | approve (release) or cancel (no production yet) |
| A merge did not reach staging | a newer merge cancelled its CI; only the newest deploys | check `.deployed` equals the newest `main` commit |
| Sign-in on a phone: "your other phone still has work" (409 `DEVICE_HAS_UNSYNCED_DATA`) | one phone per person | sync the old phone, or an Admin signs it out |
| Sentry: "vayu-alerts does not exist" | channel missing or private | create it public, or `/invite @Sentry` |
| GitHub refuses a push to `main` | the ruleset: changes come through PRs with green checks | open a PR |
| A long SSH command ends with exit 255 | the connection dropped while idle | add `-o ServerAliveInterval=30`; the command on the server may have finished: check |
| Your Mac cannot resolve a new name | it cached "not found" from before the record existed | wait a few minutes, or use the IP |
| `doctl monitoring alert` rules appear twice | old alert system | make alert rules in the web form |
| Six Dependabot PRs at once | its first run | it is grouped now: one PR a week for Actions, one for images |
| PDF preview "The server had a problem" | a very large report took longer than the web timeout | fixed in PR 42 (faster photo fetch, 120 s timeout); report it if it returns |

---

## 9. Dates to remember

| What | When |
|---|---|
| DigitalOcean API token `vayu-owner-laptop` | expires around 2027-02-24: new token → Phase → `doctl auth init` |
| Phase service tokens | if given an expiry: renew before it, then update `/srv/vayu/.phase` on the server |
| https certificates | renew by themselves (Caddy) |
| Restore drill | first Monday of every month |
| Ubuntu 24.04 | supported to 2029; plan the move to a newer release as a project |

For the full, current list of every account, secret name and address, see
**"Where everything lives"** in `docs/deploy-setup-log.md`.
