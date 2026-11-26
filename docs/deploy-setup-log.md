# Deployment setup log

What was actually done, step by step, while setting up staging and production. The plan (the why,
and steps not done yet) is `docs/plan-deploy.md`; the exact server commands are
`docs/runbook-new-server.md`. This file is updated after every step until production is live.

**No secrets in this file, ever.** It names where each secret lives (Phase), never the value.
The repo is public, so nothing here may be more than what anyone could look up.

Status: ✅ done · 🔄 in progress · ⏳ not started

| Phase | What | Status |
|---|---|---|
| 0 | Safety first: secrets home, 2-step login, SSH key | ✅ 2026-11-26 |
| 1 | Code changes (PR 27) | ✅ written, waiting for merge |
| 2 | Accounts and dashboards | 🔄 |
| 3 | Staging server setup | ⏳ |
| 4 | Deploy pipeline | ⏳ |
| 5 | Backups and alerts | ⏳ |
| 6 | Prove staging | ⏳ |
| 7 | Production | ⏳ |

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

## Phase 1 · Code changes ✅ (in PR 27, not merged yet)

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

**Must be merged before Phase 3** (`bootstrap.sh` downloads the code from `main`).

---

## Phase 2 · Accounts and dashboards 🔄

### Decisions taken on 2026-11-26
- **Staging is on demand.** A switched-off droplet is still billed, so staging lives as a
  snapshot between test rounds (`infra/staging.sh up` / `down`), about a week a month.
- **Production starts on 2 vCPU / 4 GB ($24).** It moves to 8 GB only if the staging load test
  (same size) or the alerts say so.
- Cost: about **$43–46 a month** (≈ ₹4,300–4,900 with GST). Table in `docs/plan-deploy.md` §1.

### 2.1 · Slack channel `#vayu-alerts` ⏳
Slack → **+** next to Channels → Create channel → `vayu-alerts`. Needed in Phase 5 (alerts).

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

**2.5c · Restrict the Firebase API key (R-32)** ⏳ — done once "Vayu Staging" is built, and checked
in Phase 6 (a push still arrives).
### 2.6 · Sentry: projects check, auth token, Slack alerts ⏳
### 2.7 · GitHub: branch rules, environments, fork approval ⏳

---

## Phase 3 · Staging server setup ⏳
## Phase 4 · Deploy pipeline ⏳
## Phase 5 · Backups and alerts ⏳
## Phase 6 · Prove staging ⏳
## Phase 7 · Production ⏳
