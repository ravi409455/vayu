# Deployment setup log

> **New here, or doing a deployment yourself? Use `docs/deploy-guide.md`**: the clean
> step-by-step handbook from zero to production. This file is the diary of how it was done the
> first time (with every problem met) and the live list of where everything lives.

What was actually done, step by step, while setting up staging and production. The plan (the why,
and steps not done yet) is `docs/plan-deploy.md`; the exact server commands are
`docs/runbook-new-server.md`. This file is updated after every step until production is live.

**No secrets in this file, ever.** It names where each secret lives (Phase), never the value.
The repo is public, so nothing here may be more than what anyone could look up.

Status: ✅ done · 🔄 in progress · ⏳ not started

| Phase | What | Status |
|---|---|---|
| 0 | Safety first: secrets home, 2-step login, SSH key | ✅ 2026-11-26 |
| 1 | Code changes (PR 27) | ✅ merged 2026-11-26 as `35fdec9` |
| 2 | Accounts and dashboards | ✅ 2026-11-26 (2.5c, the Firebase key restriction, 2026-11-28) |
| 3 | Staging server setup | ✅ 2026-11-26: live, with test data |
| 4 | Deploy pipeline | 🔄 merge → staging works; rollback not yet rehearsed |
| 5 | Backups and alerts | ✅ 2026-11-27 on staging: DigitalOcean alerts, Better Stack (monitor, heartbeats, Slack), first restore drill. Production gets its own set in Phase 7 |
| 6 | Prove staging | 🔄 all done but the rollback rehearsal (2026-11-28) |
| 7 | Production | ⏳ |

Quick links: [Where everything lives](#where-everything-lives) · [Open items](#open-items)

---

## Phase 0 · Safety first ✅ (2026-11-26)

### Step 1 · Phase account (console.phase.dev) ✅
Phase is the one home for every Vayu secret (end-to-end encrypted).
1. Signed up at **console.phase.dev** with the company email, verified the email.
2. Created the **sudo password** (16+ characters). It unlocks the secrets. Saved in the Mac
   **Passwords** app.
3. Downloaded the **account recovery kit**: printed, kept at the office, and saved in Passwords.
   ⚠️ Without the sudo password AND the recovery kit, every secret in Phase is gone for good.
4. Turned on **two-step login** (authenticator app); recovery codes in Passwords.
5. Organisation `CarCID`, two apps:

| Phase app | Environment | Holds |
|---|---|---|
| `vayu` | Development | the Mac's local stack (nothing needed today) |
| `vayu` | Staging | the staging server's env-file values |
| `vayu` | Production | the production server's env-file values |
| `vayu-owner` | Production | things that are not server settings: signing key, Sentry web/Android, DO token, robot keys, backup unlocking key |

What can't live inside Phase: its own sudo password and recovery kit (paper + Passwords app).
Account passwords and 2-step recovery codes of the other services also live in Passwords.

### Step 2 · Existing secrets moved into Phase ✅
Files on the Mac (`~/vayu-keys`, readable by the owner only; FileVault on):

| File | What it is | Now in Phase | Check |
|---|---|---|---|
| `vayu-release.jks` | Android signing key | `vayu-owner` → Production: `ANDROID_KEYSTORE_B64` (the file as base64 text), `ANDROID_STORE_PASSWORD`, `ANDROID_KEY_ALIAS`, `ANDROID_KEY_PASSWORD` | fingerprint of the copy in Phase = the file's (SHA-256 `cf8f24d2…0e601e90`) ✅ |
| `vayu-8bb7a-firebase-adminsdk-….json` | Firebase server key | `vayu` → Staging: `FIREBASE_SERVICE_ACCOUNT_JSON` (staging's key; production gets its own new one in 2.5) | fingerprint of normalised JSON matches (`b0c8f44c…cce29897`) ✅ |
| `sentry-dsns.env` | 3 Sentry addresses | server DSN → `vayu` Staging and Production `SENTRY_DSN`; web → `vayu-owner` `SENTRY_DSN_WEB`; Android → `vayu-owner` `SENTRY_DSN_ANDROID` | looked at; then the file was **deleted** ✅ |

How a file was checked (the fingerprint is not a secret):
```bash
shasum -a 256 ~/vayu-keys/vayu-release.jks                 # the original
base64 -i ~/vayu-keys/vayu-release.jks | pbcopy             # copy as text, paste into Phase
pbpaste | base64 -d | shasum -a 256                         # after copying it back from Phase
pbcopy < /dev/null                                          # clear the clipboard
```

Kept on the Mac on purpose (tools use them): the signing key and `keystore.properties` (release
builds), the Firebase file (the local stack's pushes), `backend/.env.local` (the local stack).

**Old R2 test key** (`R2_*` lines in `backend/.env.local`): not moved. It was used once
(2026-11-23, `docs/r2-check.md`); the local stack uses a fake local bucket. It is replaced by the
per-server keys in 2.4c, then deleted in Cloudflare together with its lines in `.env.local`.

### Step 3 · Two offline copies of the signing key ✅
- USB stick, labelled, locked away at the office.
- Private folder in the company Google Drive (the file only; its passwords stay in Phase).
- Both copies checked: same fingerprint `cf8f24d2…`.

Why: if the signing key is lost, the app on every phone can never be updated again.

### Step 4 · Two-step login everywhere ✅
Authenticator app (not SMS) on each; recovery codes saved in the Mac Passwords app.

| Account | Where |
|---|---|
| GitHub | Settings → Password and authentication → Two-factor authentication |
| Google (Firebase) | myaccount.google.com → Security → 2-Step Verification |
| Cloudflare | My Profile → Authentication → Two-Factor Authentication |
| Sentry | User Settings → Security → Two-Factor Authentication |
| GoDaddy (carcid.in) | Account Settings → Login & PIN → 2-Step Verification |
| Phase | done in step 1 |

### Step 5 · FileVault ✅
Already on (`fdesetup status` → "FileVault is On").

### Step 6 · Owner SSH key ✅
```bash
ssh-keygen -t ed25519 -C "vayu-owner"                       # passphrase saved in Passwords
ssh-add --apple-use-keychain ~/.ssh/id_ed25519
printf 'Host *\n  AddKeysToAgent yes\n  UseKeychain yes\n  IdentityFile ~/.ssh/id_ed25519\n' >> ~/.ssh/config
```
- Private half: `~/.ssh/id_ed25519` on the Mac, and in Phase → `vayu-owner` →
  `OWNER_SSH_PRIVATE_KEY` (still locked by its passphrase).
- Public half (safe to share): `ssh-ed25519 …W68za vayu-owner`, added to DigitalOcean as `owner-mac`.

---

## Phase 1 · Code changes ✅ (PR 27, merged as `35fdec9`)

Branch `deploy/phase-1`, PR https://github.com/ravi409455/vayu/pull/27.
- One address per server: `vayu.carcid.in`, `vayu-staging.carcid.in`; QR page
  `/report/verify/<code>`.
- Security headers in Caddy (HSTS, CSP enforced by default, framing blocked, nosniff, referrer,
  permissions).
- One web image for both servers; images built once per commit by GitHub Actions.
- Compose: images by commit id, env file per server, sizes from it (4 GB box: 2 / 2 / 1 / 1500m),
  migrations first, Postgres only on staging.
- Scripts: `infra/bootstrap.sh`, `deploy.sh`, `backup.sh`, `restore.sh`, `staging.sh`.
- Deploy workflow (staging by itself, production after Approve), Dependabot.
- "Vayu Staging" Android build (`in.carcid.vayu.staging`, blue icon).
- Bug found and fixed: Celery workers crashed in the production image (missing `packaging`).
- Security review fixes: CSP enforced by default, encrypted database link required, restore never
  writes the unlocked dump to disk.

Added to PR 27 later the same day:
- **Staging on demand**: `infra/staging.sh up | down | status` (snapshot → delete; re-create from
  the snapshot); both servers sized for 2 vCPU / 4 GB.
- **Settings from Phase**: `infra/secrets.sh` (run by every deploy), `infra/phase-staging.env` and
  `infra/phase-production.env` (the non-secret values to import). Security review fixes: private
  temp file, token blanked in error text, files created `0600`, secrets never on a command line.
- **CI fixes**: database connections are kept only in production (the development server leaked
  them and hung the browser tests); type fixes and a coverage test after PR 28 (`main` had gone red);
  the made-up-token browser test uses `/report/verify/`; `google-services.json` lists Vayu Staging.

Follow-up PR 30 (open): `secrets.sh` trims spaces and line breaks around values; Dependabot grouped.

---

## Phase 2 · Accounts and dashboards ✅

### Decisions taken on 2026-11-26
- **Staging is on demand.** A switched-off droplet is still billed, so staging lives as a
  snapshot between test rounds (`infra/staging.sh up` / `down`), about a week a month.
- **Production starts on 2 vCPU / 4 GB ($24).** It moves to 8 GB only if the staging load test
  (same size) or the alerts say so.
- Cost: about **$43–46 a month** (≈ ₹4,300–4,900 with GST). Table in `docs/plan-deploy.md` §1.

### 2.1 · Slack channel `#vayu-alerts` ✅
Slack (workspace "Car C.I.D") → **+** next to Channels → Create channel → `vayu-alerts`,
**public** (so Sentry and Better Stack can post without an invite). Every alarm goes here.
Checked: `#vayu-alerts` exists, public.
Lesson: Sentry's "The resource vayu-alerts does not exist or has not been granted access" meant
the channel had not been created yet. For a private channel the fix would be `/invite @Sentry`.

### 2.2 · DigitalOcean: staging server ✅
The company's existing DigitalOcean account (it also runs other, unrelated servers; nothing here
touches them).
1. Two-step login on; SSH key `owner-mac` added (Settings → Security → Add SSH Key).
2. **Create → Droplets**:

| Setting | Value |
|---|---|
| Region | Bangalore (BLR1) |
| Image | Ubuntu 24.04 (LTS) x64 |
| Size | Basic → Regular → 2 vCPU / 4 GB |
| Monitoring | on |
| Backups | **off** (staging's backup is its snapshot) |
| Authentication | SSH key `owner-mac` (never a password) |
| Hostname | `vayu-staging` |
| Tags | `vayu-staging`, `vayu-web` |

   Result: droplet `vayu-staging`, IP `139.59.39.207` (changes each time staging is re-created).
3. **Networking → Firewalls → Create Firewall** `vayu-web`:

| Inbound type | Port | Sources | Why |
|---|---|---|---|
| SSH | 22 | all IPv4 + IPv6 | owner logins and GitHub's deploy key (keys only, no passwords) |
| HTTP | 80 | all | Let's Encrypt proves the domain; redirect to https |
| HTTPS | 443 | all | web portal, phone app API, customer QR page |

   Everything else inbound is blocked (database, Redis and the app's port 8000 are unreachable).
   Outbound: left at the defaults (the server must reach GitHub, Ubuntu updates, R2, Sentry,
   Firebase, Let's Encrypt, the managed database).
   **Applied to the tag `vayu-web`**, not one droplet: every staging droplet made from a
   snapshot, and production, are covered by themselves.
4. **API → Generate New Token** `vayu-owner-laptop` (90 days, Full Access) → Phase →
   `vayu-owner` → `DO_API_TOKEN`. On the Mac:
   ```bash
   brew install doctl
   doctl auth init          # paste the token
   ```
   Checked: account active; droplet, tags and firewall rules as above.
   ⚠️ The token expires after 90 days (around 2027-02-24): make a new one, update Phase, run
   `doctl auth init` again.

### 2.3 · DNS record for staging (GoDaddy) ✅
carcid.in is registered at GoDaddy, which also runs its DNS (`ns19/ns20.domaincontrol.com`).
GoDaddy → My Products → carcid.in → **DNS** → **Add New Record**:

| Type | Name | Value | TTL |
|---|---|---|---|
| A | `vayu-staging` | the staging droplet's IP (now `139.59.39.207`) | 600 seconds |

No other record was touched (the company website and email depend on them).
The short TTL lets a new IP reach everyone within 10 minutes; `infra/staging.sh up` prints the
new IP each time and waits until DNS shows it.
Checked: GoDaddy, Cloudflare (1.1.1.1) and Google (8.8.8.8) all answer `139.59.39.207`.

**Changed 2026-11-27: the staging name moved to DigitalOcean's DNS** ✅ (so `infra/staging.sh` can
point it itself when staging is re-made; GoDaddy's API is not open to small accounts).
1. DigitalOcean → Networking → Domains: zone `vayu-staging.carcid.in`, record **A `@`** →
   `139.59.39.207`, TTL 60 s (made with `doctl`, 2026-11-27).
2. GoDaddy → carcid.in → DNS: the A record `vayu-staging` deleted; three records added:

| Type | Name | Value | TTL |
|---|---|---|---|
| NS | `vayu-staging` | `ns1.digitalocean.com` | 1 hour |
| NS | `vayu-staging` | `ns2.digitalocean.com` | 1 hour |
| NS | `vayu-staging` | `ns3.digitalocean.com` | 1 hour |

Everything else (the `vayu` production record, the company website, email) stays at GoDaddy.
While staging is off the name points to `192.0.2.1` (the "off" marker the deploy workflow reads).
Checked: GoDaddy answers with the 3 NS records; Cloudflare and Google answer `139.59.39.207` with
DigitalOcean's 60 s TTL; `https://vayu-staging.carcid.in/api/v1/health` says ok.
First real cycle (2026-11-27): `down` (marker → snapshot `vayu-staging-20261127-1614` → delete) and
`up` (new IP `159.89.168.78`, name pointed, newest main `d64a196` deployed, health ok). It showed the
new-SSH-key behaviour above; `up` now handles it.

**Staging from GitHub (2026-11-27)** ✅: Actions → **staging** → up / down / status
(`.github/workflows/staging.yml`, runs `infra/staging.sh`). One-time setup:
1. DigitalOcean → API → **Generate New Token** `vayu-staging-github`, **Custom Scopes** only:
   droplet (create, read, update, delete), snapshot (read, delete), image (create, read), domain (read,
   update), ssh_key (read), tag (create, read), actions (read), regions (read), sizes (read).
   Saved in Phase `vayu-owner` → `DO_API_TOKEN_STAGING` and as GitHub secret `DO_API_TOKEN_STAGING`
   (environment `staging`).
2. Staging's fixed SSH key (ED25519): private half in GitHub secret `STAGING_HOST_KEY` (environment
   `staging`) and Phase `vayu-owner` → `STAGING_HOST_KEY`; public half in `SSH_KNOWN_HOSTS`.
   A server made from a snapshot would otherwise get new keys on its first boot; `up` hands it this
   one (cloud-init user data) and refuses to deploy if the server shows another.
3. Tried 2026-11-27: `status` ok; `down` failed at the snapshot (the first token lacked
   image:create; a second token has it; the down was finished from the Mac); `up` made staging from
   `vayu-staging-20261127-1718` at `64.227.191.1`, it showed staging's fixed key, and the deploy it
   started put `948a9f3` on staging (health ok; production waited for Approve).

### 2.4a · R2 buckets and CORS ✅
dash.cloudflare.com → R2 Object Storage. All buckets **private** (no public access, no custom domain):

| Bucket | Use | CORS allowed origin |
|---|---|---|
| `vayu-staging` | staging's photos, videos, PDFs, ZIPs | `https://vayu-staging.carcid.in` |
| `vayu-prod` | production's | `https://vayu.carcid.in` |
| `vayu-backups` | encrypted database backups (both servers) | none (no browser uses it) |

CORS policy (each bucket → Settings → CORS Policy), staging shown:
```json
[
  {
    "AllowedOrigins": ["https://vayu-staging.carcid.in"],
    "AllowedMethods": ["GET", "PUT", "POST", "HEAD"],
    "AllowedHeaders": ["*"],
    "ExposeHeaders": ["ETag"],
    "MaxAgeSeconds": 3600
  }
]
```
Why: without it, uploads from the web portal fail; `ETag` must be readable for multipart uploads.
`http://localhost:5173` was left out: the local stack uses a fake local bucket, not R2.

### 2.4b · R2 clean-up rules and the backup lock ✅
Each bucket → Settings:

| Bucket | Rule | Setting |
|---|---|---|
| `vayu-staging`, `vayu-prod` | Object lifecycle rule `abort-unfinished-uploads` | abort incomplete multipart uploads after **14 days**; no object deletion (the app decides) |
| `vayu-backups` | Object lifecycle rule `expire-backups` | delete objects after **35 days**; abort incomplete uploads after 1 day |
| `vayu-backups` | **Bucket lock rule** `keep-30-days` | all objects, retention **30 days** (not indefinite) |

Why: unfinished uploads (a phone losing signal mid-video) cost money until removed; 14 days lets
an expert offline for a week still finish. The lock means nobody, not even someone who breaks into
a server, can delete a backup younger than 30 days; at day 35 it expires by itself.

### 2.4c · R2 access keys ✅
One key per job, each limited to one bucket: a leaked key reaches only that bucket, and each can be
replaced alone. dash.cloudflare.com → R2 Object Storage → **Manage API tokens** → **Create
Account API token**, four times:

| Token name | Permission | Bucket | Saved in Phase (app → environment) |
|---|---|---|---|
| `vayu-staging-app` | Object Read & Write | `vayu-staging` | `vayu` → Staging: `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY` |
| `vayu-prod-app` | Object Read & Write | `vayu-prod` | `vayu` → Production: `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY` |
| `vayu-backups-staging` | Object Read & Write | `vayu-backups` | `vayu` → Staging: `BACKUP_ACCESS_KEY_ID`, `BACKUP_SECRET_ACCESS_KEY` |
| `vayu-backups-prod` | Object Read & Write | `vayu-backups` | `vayu` → Production: `BACKUP_ACCESS_KEY_ID`, `BACKUP_SECRET_ACCESS_KEY` |

TTL: forever. Client IP filtering: none (servers get new IPs). Each token page shows the
Access Key ID and Secret Access Key **once**: copy straight into Phase.
Also in Phase (not secret), `vayu` → Staging and Production: `S3_ENDPOINT_URL` =
`https://<ACCOUNT_ID>.r2.cloudflarestorage.com` (shown on the same page as "S3 API" endpoint).
Two backup keys rather than one: no secret is shared between staging and production. The backup
lock (2.4b) still stops either from deleting a backup younger than 30 days.
Then the **old test token** (the one in `backend/.env.local`, `R2_*` lines) is deleted in the same
list; nothing uses it. Done, and its 5 `R2_*` lines were removed from `backend/.env.local`.
### 2.5 · Firebase: staging app, production key, API key restriction 🔄
Firebase project `vayu-8bb7a` (console.firebase.google.com).

**2.5a · The "Vayu Staging" app** ✅ — Project settings (gear) → General → **Add app** → Android:
package name `in.carcid.vayu.staging`, nickname `Vayu Staging` → Register → **download
`google-services.json`** (it now lists both apps; not a secret) → given to Claude, who puts it in
`android/app/` (PR 27). Without it, `./gradlew assembleStaging` fails.
Checked: the new file lists `in.carcid.vayu` (entry unchanged) and `in.carcid.vayu.staging`;
`assembleStaging` builds.

**2.5b · Production's own server key** ✅ — Project settings → **Service accounts** → **Generate
new private key** → the JSON goes straight into Phase → `vayu` → Production →
`FIREBASE_SERVICE_ACCOUNT_JSON`, then the downloaded file is deleted. Staging keeps the existing
key (already in Phase, step 2 of Phase 0), so production shares no key with staging or the Mac.

**2.5c · Restrict the Firebase API key (R-32)** ✅ (2026-11-28, by the owner) — Google Cloud →
APIs & Services → Credentials → "Android key (auto created by Firebase)" (ends `5Rc8`):
Android apps `in.carcid.vayu` and `in.carcid.vayu.staging`, both with the release key's SHA-1
`4E:9E:AD:F9:4D:73:82:90:D7:4F:F9:3E:2A:3B:17:59:52:52:62:97` (not secret; read from the APK with
`apksigner verify --print-certs`); API restrictions: Firebase Installations, FCM Registration,
Firebase Cloud Messaging. Google Cloud only shows project `vayu-8bb7a` to the Google account that
owns Firebase: open it from Firebase → Project settings → Service accounts → "Manage service account
permissions". Checked: after the lock the app restarted with no Firebase errors and a push arrived
(6.3). Not yet seen: a brand-new install getting its first push token under the lock (check in the
phone test).

### 2.6 · Sentry: projects, build token, Slack alert ✅
Organisation slug **`car-cid`** (`https://car-cid.sentry.io`; not a secret).
1. Projects: `vayu-server` (Django), `vayu-web` (React), `vayu-android` (Android).
2. Build token: Settings → Developer Settings → **Organization Tokens** → `vayu-ci` → Phase →
   `vayu-owner` → `SENTRY_AUTH_TOKEN`. The builds use it to upload source maps / R8 mappings, so
   error reports show real file names and lines.
3. Slack: Settings → Integrations → Slack → workspace "Car C.I.D" connected.
4. **One alert for all three projects** (Monitors → Alerts → New Alert), named `vayu production errors`:

| Part | Setting |
|---|---|
| Source | "Alert on all issues in selected projects": `vayu-server`, `vayu-web`, `vayu-android` (not "all projects": the org has other company projects) |
| Filter issues | environment **production** only (staging tests never ping Slack) |
| WHEN any of | **A new issue is created**; **An issue escalates** (Sentry's own spike detection) |
| IF | Any event |
| THEN | Slack message to "Car C.I.D" → `#vayu-alerts`; Notify Member → the owner (email) |

   Checked with **Send Test Notification**.
   If `production` was not offered in the environment list (no production event yet), set it
   once the first production error has arrived.

### 2.7 · GitHub: branch rules, environments, fork approval ✅
github.com/ravi409455/vayu → Settings.

**Ruleset `main protect`** (Rules → Rulesets), active on the default branch, empty bypass list:

| Rule | Setting | Why |
|---|---|---|
| Restrict deletions | on | `main` can't be deleted |
| Block force pushes | on | history can't be rewritten |
| Require status checks | `backend`, `backend-gates`, `web`, `android`, `docker`, `e2e`; branch must be up to date | nothing red reaches `main` (which deploys to staging by itself) |
| Require a pull request | **off** (owner's choice, 2026-11-26) | |
| Restrict updates | **off** | ⚠️ on with an empty bypass list, nobody can change `main` at all |

Effect: a direct push to `main` is refused (its new commit has no green checks yet); changes
arrive by merging a PR whose checks passed (squash).

**Environments** (Environments):

| Environment | Deployment branches | Protection |
|---|---|---|
| `staging` | `main` only | none: deploys by itself |
| `production` | `main` only | **Required reviewers: `ravi409455`** (the Approve button); self-review allowed. Saved with "Save protection rules" (a separate button). |

**Outside pull requests** (Actions → General): "Require approval for all external contributors"
(the repo is public: a stranger's PR runs no workflow until the owner looks).

**Web build settings** (Secrets and variables → Actions):

| Kind | Name | Value from |
|---|---|---|
| Variable | `SENTRY_ORG` | `car-cid` |
| Variable | `VITE_SENTRY_DSN` | Phase → `vayu-owner` → `SENTRY_DSN_WEB` (every browser sees it; not a secret) |
| Secret | `SENTRY_AUTH_TOKEN` | Phase → `vayu-owner` → `SENTRY_AUTH_TOKEN` |

Checked from the GitHub API: ruleset rules, required checks, reviewer, fork policy, variables and
secret names.
Server SSH secrets per environment come in Phase 3 / 4.

---

## Phase 3 · Staging server setup 🔄

### Decision (2026-11-26): the server fetches its settings from Phase
Instead of pasting ~15 secrets into a file on the server, every deploy runs `infra/secrets.sh`,
which asks Phase (app `vayu`, environment Staging or Production) for all settings and writes the
env file and the Firebase key file. The only secret on the server is one Phase service token in
`/srv/vayu/.phase`. Change a secret: edit it in Phase, deploy again. Phase down: the last good
settings stay. A missing value stops the deploy before anything changes. (PR 27, `b4d2681`;
tested with a fake Phase: normal, `$`/`#` in secrets, missing value, Phase down, wrong file mode.)
Free plan note: a service account can be limited to one environment, but read-only needs a paid
plan; the token can also change that environment's secrets. Accepted: the server holds those
secrets anyway.

### 3.0 · Settings in Phase (owner) ✅
**a) Non-secret values.** Open `infra/phase-staging.env` (in the repo). Phase → app `vayu` → **New
Secret** → **Import secrets** → paste the file → import into **Staging** only → **Preview Import**
→ **Deploy**.

**b) Two new secrets**, made on the Mac and pasted into Phase → `vayu` → Staging:

| Key | Make it with |
|---|---|
| `DJANGO_SECRET_KEY` | `python3 -c "import secrets;print(secrets.token_urlsafe(50))" \| pbcopy` |
| `DB_PASSWORD` | same command (a different value) |

**c) The backup key pair** (`brew install age` once):
```bash
age-keygen 2>/dev/null | grep AGE-SECRET-KEY | pbcopy   # the UNLOCKING half
```
→ Phase `vayu-owner` → Production → `BACKUP_AGE_SECRET_KEY` (never on a server). Then:
```bash
pbpaste | age-keygen -y | pbcopy                         # the LOCKING half (not secret)
```
→ Phase `vayu` → Staging **and** Production → `BACKUP_PUBLIC_KEY`. Then `pbcopy < /dev/null`.

**d) Check Staging holds:** the 24 imported values + `DJANGO_SECRET_KEY`, `DB_PASSWORD`,
`SENTRY_DSN`, `S3_ENDPOINT_URL`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`,
`BACKUP_ACCESS_KEY_ID`, `BACKUP_SECRET_ACCESS_KEY`, `BACKUP_PUBLIC_KEY`,
`FIREBASE_SERVICE_ACCOUNT_JSON`.

**e) The server's Phase key:** Access Control → Service Accounts → **Create Service Account**
`vayu-staging-server` (role Service) → app `vayu` → **Access** → Service accounts → **Add service
account** → environment **Staging only** → Access Control → Service Accounts → **Manage** →
**+ Create Token** → copy the `pss_service:v2:…` token → Phase `vayu-owner` →
`PHASE_TOKEN_STAGING_SERVER` (it goes on the server in 3.2).

### 3.1 · Server set up with `infra/bootstrap.sh` ✅ (Claude, 2026-11-26)
```bash
ssh root@139.59.39.207 'bash -s' < infra/bootstrap.sh      # once, from the laptop
```
Result, checked afterwards:
- `root` and passwords can no longer log in (both refused); log in as `deploy@<staging>`.
- `deploy`: Docker (29.10, Compose 5.8) and logs; no admin rights (it has no password).
- Firewall on the server too (22, 80, 443); automatic security updates on; 2 GB swap; clock UTC.
- Code in `/srv/vayu` (from `main`); `/srv/vayu/secrets` readable by `deploy` only.
- Nightly backup timer enabled (20:30 UTC = 02:00 IST).
- The server's own SSH fingerprint: `SHA256:yOMBc1Z3D4XpkN6a7LGHAREreTlKmgOAAkrKZxQSjoQ` (the same
  as at the first connection). **Correction 2026-11-27:** it does NOT survive a snapshot: a server
  made from one gets new keys on its first boot. `infra/staging.sh up` reads the new key and updates
  the Mac's known_hosts and GitHub's `SSH_KNOWN_HOSTS` itself (re-made 2026-11-27: ED25519
  `SHA256:TLSc0mqGF3rY3ZMVT2GQb/QTEwJY00Fk/PbXDmJTk9s`).

### 3.2 · GitHub robot key ✅
A key pair made for GitHub Actions only. Its public half is in the server's
`~/.ssh/authorized_keys`, locked: `command="/srv/vayu/infra/deploy.sh",restrict ssh-ed25519 …
github-deploy-staging`: it can only run the deploy script, nothing else.
Owner: private half → GitHub environment `staging` secret `SSH_KEY` and Phase `vayu-owner` →
`DEPLOY_SSH_KEY_STAGING`; `SSH_HOST` = `vayu-staging.carcid.in`; `SSH_KNOWN_HOSTS` = the server's
fingerprint line (so GitHub can't be fooled into deploying to another machine). Then the key files
on the laptop are deleted.

### 3.3 · The server's Phase key ✅
`/srv/vayu/.phase` on the server (chmod 600):
```
PHASE_ENV=Staging
PHASE_SERVICE_TOKEN=<PHASE_TOKEN_STAGING_SERVER from Phase>
```
Typed on the server (`ssh deploy@<staging>`, `umask 077 && nano /srv/vayu/.phase`). Note: a command
typed into Claude's chat box runs on the Mac, not on the server.
GitHub `staging` environment secrets set with (from the Mac):
```bash
gh secret set SSH_KEY --env staging --repo ravi409455/vayu < deploy-staging
gh secret set SSH_HOST --env staging --repo ravi409455/vayu --body vayu-staging.carcid.in
gh secret set SSH_KNOWN_HOSTS --env staging --repo ravi409455/vayu < known_hosts
```
Robot key's private half also in Phase `vayu-owner` → `DEPLOY_SSH_KEY_STAGING`; the files deleted.

### 3.4 · First settings fetch from Phase ✅ (after fixes)
`bash /srv/vayu/infra/secrets.sh` → "settings: 35 values from Phase", both files `600`.
What it took (lessons):
1. `FIREBASE_SERVICE_ACCOUNT_JSON` was missing in Phase Staging: pasted in Phase 0 but never
   **Deployed**. Phase keeps unsaved edits in the editor (copying from there works), but nothing is
   stored until **Deploy**. Re-added from `~/vayu-keys/vayu-8bb7a-firebase-adminsdk-fbsvc-5905526895.json`.
2. `BACKUP_PUBLIC_KEY`, `DJANGO_SECRET_KEY`, `DB_PASSWORD` ended in a hidden line break: `… | pbcopy`
   copies the command's final line break and Phase keeps it. Removed in Phase (End, Backspace,
   Deploy). PR 30 makes `secrets.sh` trim spaces and line breaks around values from now on (names
   are never trimmed: a spaced name is refused).
3. Production's Firebase key was still in `~/Downloads`: put in Phase Production, file deleted.

### Merged
- PR 27 (Phase 1 code, settings from Phase, staging on demand) → `main` as `35fdec9`.
- PR 18 (`docs/plan-deploy.md` and this log) → `main` as `2f1408a`. From now on this log changes
  through a docs PR (the `main` ruleset refuses direct pushes).

### 3.5 · First deploy ✅ (2026-11-26, automatic)
Nobody touched the server: PR 27 merged → CI green on `main` → the deploy workflow built both
images once (`ghcr.io/ravi409455/vayu-api` and `vayu-web`, tag = commit id) → logged in with the
locked robot key → `deploy.sh` fetched the settings from Phase, ran the migrations, started
everything, health ok. The run then waited for **Approve** on production: not approved (no
production server yet), the run was cancelled. Until Phase 7, cancel that waiting step each time.

Checked from outside:

| Check | Result |
|---|---|
| `https://vayu-staging.carcid.in/` | 200 in 0.3 s |
| `/api/v1/health` (database, Redis, R2 storage, workers, Firebase push) | `{"status":"ok"}` |
| `/report/verify/<code>` | 200 |
| https certificate | Let's Encrypt, valid to 2027-02-24, Caddy renews it by itself |
| Headers | HSTS, nosniff, CSP report-only (staging, as planned) |
| Services | api (healthy), worker, zip-worker, pdf-worker, beat, postgres (healthy), redis (healthy), caddy |
| Live commit (`/srv/vayu/.deployed`) | `35fdec9` |

### 3.6 · Forms, reports, staff and test data ✅
`seed_test_data` sets up every form, report and list (it runs `setup_platform`), then makes the
test logins and 3 days of test bookings. Staging only: it refuses on production.
1. Owner: one password for all test logins, made without a trailing line break and saved in
   Phase → `vayu` → Staging → `STAGING_TESTER_PASSWORD` (Deploy):
   ```bash
   python3 -c "import secrets;print(secrets.token_urlsafe(24),end='')" | pbcopy
   ```
2. Claude, on the server (the password is read there from the settings file; it never passes
   through chat):
   ```bash
   bash infra/secrets.sh        # fetch the new setting
   source infra/lib.sh && export VAYU_TAG=$(cat .deployed) P=$(envval STAGING_TESTER_PASSWORD)
   compose exec -T -e P api sh -c 'python manage.py seed_test_data --confirm staging-1 --password "$P"'
   ```
Test logins on https://vayu-staging.carcid.in (password: Phase `STAGING_TESTER_PASSWORD`):

| Login | Role |
|---|---|
| `admin` | Admin |
| `ops`, `ops2` | Ops |
| `expert`, `expert2` … `expert7` | Expert |

Result (it took about 20 minutes, mostly uploading the test photos to R2):

| What | Count |
|---|---|
| Logins | 10 |
| Forms | 7 |
| Bookings | 30: draft 3, assigned 5, in progress 3, submitted 2, completed 16, cancelled 1 |
| PDF reports | 16 (one per completed booking) |
| Photos | 1,685 verified in R2; 5 left "uploading" on purpose (the stuck-upload screen) |

Sign-in checked: `ops` and `expert` sign in; `admin` is refused by the phone app on purpose (Admins
use the web portal).

Lessons:
- Run long commands on the server with `ssh -o ServerAliveInterval=30`: the first run's SSH
  connection dropped while idle (exit 255), although the command itself finished.
- A command's arguments are visible in `ps` / `docker top`. Claude printed the running process
  list and the testers' password appeared in the chat: the password was replaced in Phase and on
  the test logins (3.7). Since then: process lists by name only. (Better later: let
  `seed_test_data` read the password from the environment instead of an argument.)

### 3.7 · Replace the exposed testers' password ✅ (2026-11-26)
New value in Phase → `vayu` → Staging → `STAGING_TESTER_PASSWORD` (Deploy), then set on all 10
test logins on the server from the fetched setting (Django `set_password`, value read from the
settings file inside the container, never printed): "passwords changed: 10".
Checked: the old password is refused (`/api/v1/auth/login` → 401), the new one signs in (200).

### Dependabot ✅ grouped (now in PR 42)
Its first run opened 6 PRs at once (Actions and the Node image), each a full CI run, which queued
ahead of `main`'s CI. Closed them and cancelled their runs. New rule: one grouped PR a week for all
GitHub Actions and one for all Docker images; no Node major jumps (stay on LTS), no Python minor
jumps. In force on `main` since PR 42 (`cc40087`); #43 (one more single update from before) closed.

### 3.8 · First bugs found on staging, and the "staging round" PR 42 ✅ merged as `cc40087` (from session "bugs on staging")
**PDF template preview failed** ("The server had a problem"). The preview draws the whole PDF
inside the web request. A full PDI took 43 s on staging: 1 s data, 30 s fetching ~150 photos one by
one (a new storage client each time), 12 s drawing. That is past gunicorn's 30 s limit, so the
worker was killed. A bug in the log formatter (request path empty) then hid the real error behind
a `TypeError`. Measured on staging with 40 photos:

| How the photos are fetched | Time |
|---|---|
| one by one, a new storage client each | 7.2 s |
| one by one, one client | 4.7 s |
| one client, 8 at a time | 0.8 s |

**PR 42 "Staging round"** (combines PRs 30, 39, 40 and 41, which are closed):
- `secrets.sh` trims spaces and line breaks around Phase values, never names (a spaced name is
  refused, so it can't shadow a real setting).
- Dependabot grouped (above).
- gunicorn timeout 120 s (setting `GUNICORN_TIMEOUT`); the access log survives an empty path.
- Photos fetched 8 at a time over one storage client, one database query per photo grid: faster
  preview and faster final PDF.
- CI on `main`: a newer merge cancels the older run.
- Deploy queues per job: staging deploys one at a time and a running deploy is never cut off;
  production has its own queue, so a run waiting for **Approve** no longer blocks staging.
- `deploy.sh` never goes backwards by accident: an older commit is skipped (a `::warning::` in
  GitHub). A hand-started run (Run workflow) is sent as `<commit> rollback` and may go back. A
  damaged `.deployed` or a git error stops the deploy. Tested against a real clone: older skipped;
  rollback, same commit and newer go through; extra words refused.
After it deploys, the preview is timed again on staging (result to be added here).

**Phone sign-in of the test logins:** 7 of 9 phone logins sign in with the current password;
`ops` and `expert` answer 409 `DEVICE_HAS_UNSYNCED_DATA` (signed in from the server as a test
"phone"; one phone per person). Fix when needed: an Admin signs that phone out (web → Users →
the person's ⋯ menu → **Sign out of every device**), or `revoke_devices` on the server.

---

## Phase 4 · Deploy pipeline 🔄

### 4.1 · A code release was skipped, and the fix 🔄 (2026-11-26)
After PR 42 (code) and PR 37 (docs) merged a few minutes apart, staging still ran `35fdec9`:
1. PR 42 merged → `main`'s CI started for `cc40087`.
2. PR 37 merged → CI on `main` cancels the older run when a newer merge arrives (added by PR 42
   itself), so `cc40087` never finished CI and never deployed.
3. The deploy for PR 37 compared it only with the commit before it, saw "docs only", and skipped
   building and deploying.
Fix (PR 45): no docs-only shortcut. **The newest merge always deploys, whatever files it changed.**
Merges close together (A, B, C a few minutes apart): CI cancels A's and B's runs, and only C
deploys; it contains A's and B's changes, so nothing is lost and staging restarts once. If C's CI
fails, nothing deploys and staging stays on the last good version until a green merge.
A docs-only merge costs a cached build and a 10-20 s restart of staging.
A hand-started run (Actions → deploy → Run workflow) builds the images if they are missing, so it works for any commit on `main`.
After the security review of that change:
- a hand-started run takes only a full commit id that is already on `main` (checked with GitHub
  before anything is built or pushed);
- images are never rebuilt or overwritten: if a commit's images exist, they are deployed as they are;
- only merges to `main` write the build cache.
How to notice next time: `ssh deploy@<staging> cat /srv/vayu/.deployed` should equal the newest
commit on `main` after each deploy run.
## Phase 5 · Backups and alerts ✅

### 5.1 · Watching the server's resources (owner asked 2026-11-26)
DigitalOcean alerts say **when** the server was busy. (A recorder of *which service* used what,
`infra/resources.sh` every 5 minutes, was built and then **removed** on the owner's decision the
same day: script, cron line and `/srv/vayu/logs` are gone. Which service is busy can be seen live
with `docker stats` when needed.)

**DigitalOcean alerts ✅ → Slack `#vayu-alerts`** (2026-11-26). DigitalOcean → **Insights** →
**Alerts** → **Alert Rules** (the new place; there is no "alert policy" menu any more). Four rules,
each: resource type **Droplets**, resource **tag `vayu-web`** (not "All Droplets": the account
has other company servers; production gets the tag too), notification channel
**`slack-vayu-alerts`** only, re-notify every 4 hours:

| Rule | Condition |
|---|---|
| `vayu: CPU above 80% for 10 min` | CPU utilization ≥ 80% over 10 minutes |
| `vayu: memory above 85% for 10 min` | Memory utilization ≥ 85% over 10 minutes |
| `vayu: disk above 80%` | Disk utilization ≥ 80% over 5 minutes |
| `vayu: load above 3 for 10 min` | Load average (5 min) ≥ 3 over 10 minutes |

Notification Channels: `slack-vayu-alerts` (Slack, the owner made it) used by 4 rules; `email`
used by 0 (can be deleted).
Lessons:
- `doctl monitoring alert` only knows the old alert system: email, or a raw Slack webhook URL. It
  cannot use the new Notification Channels. Rules made with it appear twice in the new screen
  (a Droplets row and a Kubernetes row, because a tag can sit on both). So these rules were made
  in the web form (by Claude, in the owner's browser), resource type Droplets only.
- The web form defaults to **All Droplets**: always swap it for the tag.

### 5.2 · Better Stack: uptime monitor and heartbeats ✅ (2026-11-27, staging test)
Account: Better Stack (Uptime), signed up by the owner with the company email, **Free plan**
(10 monitors, 10 heartbeats; alerts by e-mail and Slack only; phone call, SMS and app push need
the paid plan). Made by Claude in the owner's browser. **Staging is a test only: at launch the same
set is made for production and the staging ones are deleted** (staging is switched off between
rounds, so its monitor would alert every time).

| Name | What | Setting |
|---|---|---|
| `Vayu staging health` (monitor) | `https://vayu-staging.carcid.in/api/v1/health` | alert when the page lacks `"ok"`; checked every 3 min (the Free plan's fastest; 1 min is paid); incident after 1 min failing; recovery 3 min |
| `staging-workers` (heartbeat) | ping from a worker every 5 min (`apps.platform.tasks.heartbeat`) | expected every 5 min, grace 10 min; URL in Phase `vayu` → Staging `WORKERS_HEARTBEAT_URL` |
| `staging-backup` (heartbeat) | ping at the end of the nightly `infra/backup.sh` | expected every 1 day, grace 3 h; URL in Phase `vayu` → Staging `BACKUP_HEARTBEAT_URL` |
| `carcid.com` (monitor) | made by Better Stack's sign-up; the company site | left as it was |

Tested:
- Monitor: staging went down and up during the test → Better Stack opened "DNS lookup failed"
  incidents and resolved them by itself when staging came back ✅.
- `staging-workers`: **Up** a few minutes after staging started ✅ (values reached
  `.env.staging` and the worker container after a hand-started deploy).
- `staging-backup`: **Up** ✅ after a backup run by hand (`ssh deploy@<staging> /srv/vayu/infra/backup.sh nightly`;
  the service runs as `deploy`, so no sudo). Only `nightly` backups ping; `predeploy-<sha>` ones do not.
- Slack `#vayu-alerts` integration: connected by the owner; the staging incidents arrived there ✅.

Lessons:
- **A heartbeat stays "Pending" until its first ping, and a Pending heartbeat never alerts.** To
  test the alert, let it go Up first, then stop the pings.
- Better Stack refuses a monitor while the address points to the placeholder `192.0.2.1` (staging
  switched off): "Domain … was restricted and cannot be added as a monitor". Make it while staging is up.
- After `staging.sh up` the Mac may still have the placeholder address cached; check with
  `dig +short vayu-staging.carcid.in @1.1.1.1`.

### 5.3 · First restore drill ✅ (2026-11-27, staging)
`infra/restore.sh 2026-11-27T1809Z-nightly.dump.age --drill`, run by the owner from the Mac
(`ssh -t`; the unlocking key `BACKUP_AGE_SECRET_KEY` pasted from Phase at the prompt, never stored).
Restored into the throwaway container in **6 s**; the 12 biggest tables of the backup and of live
staging were **equal** (1820 fields, 1768 media files, 208 booking activities, ...). Logged in
`docs/runbook-new-server.md` §7. Next drill: first Monday of the month.

## Phase 6 · Prove staging 🔄

### 6.6 · Security headers and the content rules (CSP) ✅ (2026-11-28)

**What they are (plain words).** Rules Caddy sends with every page; the browser obeys them.
| Header | What it stops | Example |
|---|---|---|
| `Content-Security-Policy` (CSP) | code or files from anywhere but the places we list | a customer name `<script>steal()</script>` shown by a bug never runs: that code is not from an allowed place |
| `X-Frame-Options: DENY` (+ CSP `frame-ancestors 'none'`) | another site showing Vayu inside its page | a fake "Win a prize" button laid over an invisible "Delete booking" |
| `Strict-Transport-Security` (HSTS, 1 year) | being pushed onto plain http | someone on café Wi-Fi reading a password |
| `X-Content-Type-Options: nosniff` | a "photo" being run as code | an upload that is really a script |
| `Referrer-Policy` | other sites seeing our full page address | a booking id in the URL leaking when a link is clicked |
| `Permissions-Policy` | camera / location for anyone but us; microphone, payment, USB for everyone | |

**Where they live:** `infra/Caddyfile` (the `header` block at the top, and the `@app` CSP line).
Which way CSP applies comes from `CSP_HEADER` in Phase → `vayu` → each environment:
`Content-Security-Policy` = enforced (blocks); `Content-Security-Policy-Report-Only` = only warns in
the browser console, blocks nothing. Production is always enforced.

**What our CSP allows (the `@app` line):** code, styles and fonts only from our own address; photos
and videos from our address, `data:`/`blob:` and `*.r2.cloudflarestorage.com`; network calls to our
address, R2 (uploads) and `*.sentry.io` (errors); frames (the PDF preview) from our address, `blob:`
and R2. The welcome pages (`/welcome/*`) have their own looser line (inline code, Google fonts).

**Done on staging:**
- Grades: **SSL Labs A+** (TLS 1.3, HSTS). **securityheaders.com B** while CSP was report-only and
  X-Frame-Options missing.
- With a violation listener in Chrome, nothing would have been blocked on: Today, Bookings, a
  booking (Booking, Inspection, Media with 88 R2 photos, Review, Report with the PDF preview),
  Dashboard, Forms, Library, the PDF designer, the customer QR check page.
- PR 69: `X-Frame-Options: DENY`; `infra/phase-staging.env` → enforced; runbook §9. Caddyfile
  checked with `caddy validate`.
- Owner set Phase → `vayu` → Staging → `CSP_HEADER` = `Content-Security-Policy` and merged PR 69.
  PR 70 merged minutes later, so CI cancelled PR 69's run and staging got both with `ea99876`
  (by design: the newest merge deploys).
- After: **securityheaders.com A+** (all six headers), CSP **enforced**, `X-Frame-Options: DENY`.
  Booking tabs (88 R2 photos, PDF preview) and the PDF designer work; nothing blocked ✅.
- Also seen on this deploy: the Firebase key file stayed 644 by itself (PR 67 now in effect, 6.3).

**If something breaks one day because of CSP — how to know and fix it:**
1. *What it looks like:* a blank or half-drawn page, photos or the PDF preview not showing, uploads
   stuck at 0%, or Sentry getting no web errors. It shows up right after a change that adds
   something new (a map, chat widget, analytics, a font from a CDN, a new storage address, a new
   Sentry region) or after the R2 / Sentry address changes.
2. *Confirm it is CSP:* open the page in Chrome → right-click → Inspect → **Console**. A CSP block
   reads: `Refused to load ... because it violates the following Content Security Policy directive:
   "img-src ..."`. The word after "directive" (`img-src`, `script-src`, `connect-src`, `frame-src`...)
   says which rule, and the address it names is what was blocked.
3. *Quick relief on staging only:* Phase → Staging → `CSP_HEADER` =
   `Content-Security-Policy-Report-Only` → deploy (Actions → deploy → Run workflow, the live commit).
   Pages work again; the console still lists what would be blocked. **Never on production.**
4. *Real fix (both servers):* in `infra/Caddyfile`, add the blocked address to that rule on the
   `@app` line (e.g. a new photo host into `img-src` **and** `media-src`; a new API into
   `connect-src`). Add only that address, never `*` or `'unsafe-inline'`. Check with
   `docker run --rm -e APP_HOST=localhost -e CSP_HEADER=Content-Security-Policy -v "$PWD/infra/Caddyfile:/etc/caddy/Caddyfile:ro" caddy:2 caddy validate --config /etc/caddy/Caddyfile`,
   then a PR; the merge deploys it.
5. *After the fix:* set staging's `CSP_HEADER` back to `Content-Security-Policy`, deploy, open the
   page with the console open: no "Refused" lines. Re-run securityheaders.com.
6. *Check what a server sends:* `curl -sI https://<address>/ | grep -iE "content-security|x-frame|strict"`.

### 6.7 · Load test ✅ (2026-11-27, owner + load-test session)
Cloud run on throwaway servers (`perf/cloud.sh all`, PR 46/61, cost $1.06, real car photos; results
kept on the Mac, `perf/results/20261127-1237-all`, not in git). At the test's 1× day:
| Server | Screens p95 | PDF | CPU | Verdict |
|---|---|---|---|---|
| $12 (1 vCPU / 2 GB) | 3.7 s | 106-176 s | 102% | fails |
| $18 (2 vCPU / 2 GB) | 0.45 s | 31 s | 81%, swap 0.6 GB | near pass |
| $24 (2 vCPU / 4 GB, the plan's size) | 0.43 s | 31 s | 76%, no swap | near pass |
Capacity: $24 and $18 both break at 3× (PDFs first). PDF time (~30 s) is per-core speed, not size.
The owner's real day (20 experts, 5 Ops, 50 inspections) is well under the test's 1×.
Open: a few 502s on `media/initiate` ($12 ×6, $24 ×2); the report's API p95 should leave uploads
out; `loadtest_cleanup` too slow on 1M history rows; PR 61's stop-all treats a clean-up failure as a
test failure.

### 6.10 · Reboot test ✅ (2026-11-28)
`doctl compute droplet-action power-cycle <staging id> --wait` (the same as DigitalOcean → Power →
Power cycle). Power cycle took 29 s; **health answered ok 62 s after the start**, with nobody
logging in. After it: all 8 containers up (api, worker, pdf-worker, zip-worker, beat, caddy healthy
postgres and redis), web page 200, data unchanged (30 bookings, 1768 media, 10 users), backup timer
still set for 02:00 IST, the worker reads the Firebase key, both Better Stack heartbeats Up. The
health monitor (every 3 min) did not even notice the 1-minute gap.

### 6.11 · On-demand cycle ✅ (2026-11-27, by the owner)
Staging taken down and brought back up (Actions → staging down / up, PR 63 and 64) during these
checks: it came back healthy with its data, https and settings; Better Stack saw the outage and the
recovery (5.2). After an up, the server has a new IP; the Mac may keep the old address cached
(`dig +short vayu-staging.carcid.in @1.1.1.1` shows the new one).

### 6.3 · Push ✅ (2026-11-28)
**No push had ever been sent from staging.** The push task failed with `PermissionError:
/run/secrets/firebase-service-account.json` (Sentry, since 26 Nov): `secrets.sh` wrote the key 600
for `deploy` (uid 1000), the api and worker containers run as uid 10001. Fixed by PR 67: the file
is 644 (still private: `secrets/` is 700). Five test notifications to `ops` on the phone ("Push
test", "Inspection started", "Inspection submitted", "New booking", one after the key lock), sent
through `notify.handlers.to_user`: all arrived ✅.
Lesson: **a deploy runs `secrets.sh` from the code it replaces**, before checking out the new
commit, so a change to `secrets.sh` works from the deploy after the one that brings it. PR 67's own
deploy still wrote 600; fixed by hand once (`chmod 644`), the next deploy keeps it.

### 6.4 · Update prompt ✅ (2026-11-28)
"Vayu Staging" 0.3.0 (version code 12) built from `main` `005b6c8` on the Mac (`assembleStaging`,
signing key in `~/vayu-keys`, `SENTRY_DSN_ANDROID` and `SENTRY_AUTH_TOKEN` pasted at a hidden prompt
in the terminal, so the mapping was uploaded) and published on staging with `publish_apk`. The
phone, on code 11, offered the update; installed and opened ✅.
Lessons: a new worktree needs `android/local.properties` (`sdk.dir`) copied in. A command typed
in the chat box runs in Claude's shell, not the Terminal tab, so it never sees keys pasted there.

### 6.5 · Sentry ✅ (2026-11-28)
One test error from each, all three arrived labelled **`staging`**:
| Where | How | Issue |
|---|---|---|
| Server | `capture_exception` in `manage.py shell` in `vayu-api-1` | `VAYU-SERVER-8` (release = the deployed commit) |
| Web | an uncaught error thrown on the signed-in staging site | `VAYU-WEB-1` |
| App | `adb shell am crash in.carcid.vayu.staging`, then open the app (it sends on the next start) | `VAYU-ANDROID-1`, release 0.3.0 (12) |
Found: the earlier staging app on the phone ("photos-top", code 11) had **no DSN built in**, so its
crashes went nowhere; any app build for testers must be built with `SENTRY_DSN_ANDROID`.
Slack: the Sentry alert "Notify #vayu-alerts via Slack, Notify techxcid@gmail.com" covers all three
projects and **all environments**, and fires on **a new issue** or **an issue escalating** (30 min
throttle). Server and web posted to `#vayu-alerts` ✅. The app crash did **not**: it joined
`VAYU-ANDROID-1`, an issue first seen 3 days earlier from a debug build, so it was neither new nor
escalating. Fix (owner's OK, 2026-11-28): the alert also fires when **a resolved issue regresses**
(comes back after being marked fixed). Then `VAYU-ANDROID-1` was resolved and the app crashed again →
the alert fired (6:52 PM UTC) and reached `#vayu-alerts` ✅ (owner saw it). So: mark an issue **Resolved** once fixed, and it alerts if it returns.
## Phase 7 · Production ⏳

---

## Where everything lives

**Never in this file, git or chat: values.** Names only.

### Phase (console.phase.dev, organisation `CarCID`)
| App → environment | Keys | Used by |
|---|---|---|
| `vayu` → Staging | the 24 non-secret values of `infra/phase-staging.env`; `WORKERS_HEARTBEAT_URL`, `BACKUP_HEARTBEAT_URL` (Better Stack, 5.2); `DJANGO_SECRET_KEY`, `DB_PASSWORD`, `SENTRY_DSN`, `S3_ENDPOINT_URL`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY` (token `vayu-staging-app`), `BACKUP_ACCESS_KEY_ID`, `BACKUP_SECRET_ACCESS_KEY` (token `vayu-backups-staging`), `BACKUP_PUBLIC_KEY`, `FIREBASE_SERVICE_ACCOUNT_JSON` (the Mac's/staging's Firebase key) | the staging server, through `infra/secrets.sh` |
| `vayu` → Production | **so far**: `SENTRY_DSN`, `S3_ENDPOINT_URL`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY` (token `vayu-prod-app`), `BACKUP_ACCESS_KEY_ID`, `BACKUP_SECRET_ACCESS_KEY` (token `vayu-backups-prod`), `BACKUP_PUBLIC_KEY`, `FIREBASE_SERVICE_ACCOUNT_JSON` (production's own key). **Still to add (Phase 7)**: import `infra/phase-production.env`, new `DJANGO_SECRET_KEY`, the managed database's `DB_PASSWORD` and `DB_HOST` | the production server |
| `vayu` → Development | nothing yet | the Mac's local stack |
| `vayu-owner` → Production | `ANDROID_KEYSTORE_B64`, `ANDROID_STORE_PASSWORD`, `ANDROID_KEY_ALIAS`, `ANDROID_KEY_PASSWORD`, `SENTRY_DSN_WEB`, `SENTRY_DSN_ANDROID`, `SENTRY_AUTH_TOKEN` (`vayu-ci`), `DO_API_TOKEN` (`vayu-owner-laptop`), `OWNER_SSH_PRIVATE_KEY`, `BACKUP_AGE_SECRET_KEY` (unlocks backups; never on a server), `PHASE_TOKEN_STAGING_SERVER`, `DEPLOY_SSH_KEY_STAGING` | the owner |

Service account `vayu-staging-server`: role Service, app `vayu`, **Staging only**.

### Not in Phase
| What | Where |
|---|---|
| Phase sudo password, Phase recovery kit | Mac **Passwords** app + printed kit at the office |
| Account passwords and 2-step recovery codes (GitHub, Google, Cloudflare, Sentry, GoDaddy, DigitalOcean, Phase) | Mac **Passwords** app |
| SSH key passphrase | Mac **Passwords** app |
| Android signing key, offline | USB stick at the office + private company Google Drive folder |
| `~/vayu-keys/` on the Mac (owner only, FileVault) | `vayu-release.jks`, `keystore.properties` (release builds), `vayu-8bb7a-firebase-adminsdk-fbsvc-5905526895.json` (local stack) |
| `~/.ssh/id_ed25519` on the Mac | owner SSH key |
| `doctl` login on the Mac | `doctl auth init` (the `DO_API_TOKEN`) |
| Staging server `/srv/vayu/.phase` | the server's Phase token (the only secret typed onto a server) |
| Staging server `/srv/vayu/.env.staging`, `/srv/vayu/secrets/` | written by `secrets.sh` from Phase; never edited by hand |
| GitHub → environment `staging` → secrets | `SSH_KEY`, `SSH_HOST`, `SSH_KNOWN_HOSTS` |
| GitHub → repository → secrets / variables | secret `SENTRY_AUTH_TOKEN`; variables `SENTRY_ORG` (`car-cid`), `VITE_SENTRY_DSN` |
| Cloudflare R2 API tokens | `vayu-staging-app`, `vayu-prod-app`, `vayu-backups-staging`, `vayu-backups-prod` (the old test token: deleted) |

### Names and addresses (not secret)
| What | Value |
|---|---|
| Staging | `https://vayu-staging.carcid.in` (droplet `vayu-staging`, BLR1; IP and SSH key change when re-made, `infra/staging.sh up` handles both) |
| Production | `https://vayu.carcid.in` (not created yet) |
| Customer QR page | `https://<address>/report/verify/<code>` |
| DNS | GoDaddy (`ns19/ns20.domaincontrol.com`); just `vayu-staging` is DigitalOcean DNS (`ns1-3.digitalocean.com`) |
| Sentry | organisation `car-cid`; projects `vayu-server`, `vayu-web`, `vayu-android`; alert `vayu production errors` → `#vayu-alerts` |
| Firebase | project `vayu-8bb7a`; apps `in.carcid.vayu`, `in.carcid.vayu.staging` |
| DigitalOcean | firewall `vayu-web` (by tag), tags `vayu-web`, `vayu-staging`; SSH key `owner-mac` |
| GitHub | ruleset `main protect`; environments `staging`, `production` (reviewer `ravi409455`) |
| Slack | `#vayu-alerts` (public, workspace "Car C.I.D") |
| Better Stack | Uptime, Free plan; monitor `Vayu staging health`, heartbeats `staging-workers`, `staging-backup` (5.2) |

---

## Open items

| Item | When |
|---|---|
| Merge PR 37 (this log, DigitalOcean alerts) | when CI is green |
| Time the PDF preview on staging after PR 42 deploys | after the merge |
| Phase 4: rehearse a rollback (Actions → deploy → Run workflow → previous commit) | after the merges |
| Every deploy run waits for production Approve: cancel it until production exists (after PR 42 it no longer blocks staging) | until Phase 7 |
| Welcome pages (`/welcome/engineers`, `/welcome/ops`, public APK download; PR welcome-pages): open both on staging after the next deploy; on production in Phase 7, with an uptime monitor on `/welcome/engineers` | next deploy, Phase 7 |
| 5.2 Better Stack for production: monitors on `/api/v1/health`, `/` and `/welcome/engineers`; heartbeats `prod-workers`, `prod-backup` → Phase `vayu` → Production; then delete the staging monitor and heartbeats and clear their two Phase Staging values | Phase 7 |
| Phase Production environment: the rest of its values (table above) | Phase 7 |
| Production server's Phase service account (`vayu-prod-server`, Production only) and robot key | Phase 7 |
| DigitalOcean API token `vayu-owner-laptop` expires (90 days) | around 2027-02-24 |
| Phase service token `vayu-staging-server`: if it was given an expiry, note the date here | check |

