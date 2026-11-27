# Deployment guide: Vayu from zero to production

A step-by-step handbook for **anyone**, including someone who has never seen this project.
Do the steps **in order**, top to bottom. Each step says what to click or type, why, and how to
check it worked. Every secret is its own step, with its exact name in Phase.

Other documents: `docs/deploy-setup-log.md` (the diary of the first time, with every problem met),
`docs/runbook-new-server.md` (deep server reference), `docs/plan-deploy.md` (why it is built so).

Marks: **[OWNER]** needs the account owner (payment, owner rights) · 🔐 creates a secret ·
🧪 planned, not yet done on the real servers (do it, then correct this guide where reality differs).

> **The one rule.** A secret (password, key, token) never goes into chat, git, a document or a
> loose file. It goes from the website or command that makes it **straight into Phase**, and from
> Phase to where it is used. The code is public.

---

## Part 0 · What you are building, and the basics

### What
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
   Postgres                  Cloudflare R2
   (staging: on the server;  (photos, videos, PDFs,
    production: managed)      encrypted backups)
```
- **GitHub Actions** builds the code and deploys it. **Phase** holds every setting and secret.
  **Sentry** collects errors. **DigitalOcean alerts** watch the server. **Firebase** sends phone
  notifications. Alarms go to Slack **#vayu-alerts**.
- **Staging** `https://vayu-staging.carcid.in`: for testing; runs only while testing; gets every
  merge to `main` by itself.
- **Production** `https://vayu.carcid.in`: for real work; always on; gets a release only after
  someone presses **Approve**.
- Cost: about $43–46 a month plus GST.

### Basic B1 · Run a command on your Mac
Open **Terminal** (Cmd+Space, type "Terminal", Enter). Copy one grey command block from this guide,
paste it (Cmd+V), press **Enter**. Run blocks one at a time and read what they print.
Lines starting with `#` are comments.

### Basic B2 · Add a secret in Phase
1. console.phase.dev → sign in → open the **app** the step names (`vayu` or `vayu-owner`).
2. You see a table: one row per secret, one column per **environment** (Development, Staging,
   Production).
3. Click **New Secret** → type the **name** exactly as the step says (capitals and underscores) →
   paste the value in the column of the environment the step says.
4. Click **Deploy** (top right) and confirm. ⚠️ **Until you click Deploy, nothing is saved**: the
   value shows on screen and even copies back out, but the servers do not get it.
5. Check: reload the page; the secret is still there.

To change a secret: click its value in that column, replace it, **Deploy**.

### Basic B3 · Copy a value without a hidden line break
Commands that end with `| pbcopy` put the value on your clipboard; then you paste it into Phase.
`print(...)` and `echo` add an invisible line break at the end, so this guide uses `end=''` or
`tr -d '\n'`. After pasting, always clear the clipboard:
```bash
pbcopy < /dev/null
```

### Basic B4 · Work on a server
```bash
ssh deploy@<server ip or name>      # you are now ON the server (the prompt says deploy@vayu-...)
exit                                # back to your Mac
```
⚠️ A command typed into Claude's chat box runs on **your Mac**, not on the server. Commands meant
for the server go in a Terminal where you are logged in to it.

---

## Part A · Your computer (steps 1–5)

**Step 1 · Install the tools**
```bash
brew install gh doctl age git
brew install --cask docker
brew install openjdk@17
```
(No `brew`? Install it first from https://brew.sh.) Then open **Docker** once from Applications.

**Step 2 · Get the code**
```bash
git clone https://github.com/ravi409455/vayu.git
cd vayu
```

**Step 3 · Sign in to GitHub on the command line**
```bash
gh auth login
gh auth status          # check: "Logged in to github.com"
```

**Step 4 · Your SSH key** (your door key to the servers)
```bash
ssh-keygen -t ed25519 -C "<your name>"     # Enter for the default file; type a passphrase
cat ~/.ssh/id_ed25519.pub                  # the PUBLIC half: safe to share
```
Save the passphrase in your password manager. Never share `~/.ssh/id_ed25519` (without `.pub`).
🔐 Owner only, as a backup copy: `pbcopy < ~/.ssh/id_ed25519` → Phase `vayu-owner` →
**`OWNER_SSH_PRIVATE_KEY`** (still locked by its passphrase) → Deploy → `pbcopy < /dev/null`
(do this after step 7 exists).
Let the Mac remember the passphrase:
```bash
ssh-add --apple-use-keychain ~/.ssh/id_ed25519
printf 'Host *\n  AddKeysToAgent yes\n  UseKeychain yes\n  IdentityFile ~/.ssh/id_ed25519\n' >> ~/.ssh/config
```

**Step 5 · Check the Mac's disk is encrypted**
```bash
fdesetup status         # must say "FileVault is On"; if not: System Settings → Privacy & Security → FileVault
```

---

## Part B · Phase and two-step login (steps 6–9)

**Step 6 · Phase account [OWNER]** (joining an existing project: ask the owner for an invite to
organisation `CarCID`, apps `vayu` and `vayu-owner`)
1. console.phase.dev → sign up with the company email → verify the email.
2. Create the **sudo password** (16+ characters): it unlocks the secrets. Save it in your password
   manager.
3. **Download the account recovery kit**: print it, keep it at the office, also save it in the
   password manager. ⚠️ Lose both the sudo password and the kit and every secret is gone for good.
4. Turn on **two-step login** (authenticator app).

**Step 7 · Organisation and apps [OWNER]**
Create organisation `CarCID`, then two apps:
- `vayu`: its environments **Development**, **Staging**, **Production** hold each server's settings.
- `vayu-owner`: things that are not server settings. Always use its **Production** environment.

**Step 8 · Two-step login on every account**
Authenticator app (not SMS). Save each account's recovery codes in your password manager.

| Account | Where |
|---|---|
| GitHub | profile picture → Settings → Password and authentication → Two-factor authentication |
| Google (Firebase) | myaccount.google.com → Security → 2-Step Verification |
| Cloudflare | profile → My Profile → Authentication → Two-Factor Authentication |
| Sentry | avatar → User Settings → Security → Two-Factor Authentication |
| GoDaddy | Account Settings → Login & PIN → 2-Step Verification |
| DigitalOcean | avatar → My Account → Security |

**Step 9 · Slack channel**
Slack → **+** next to Channels → Create channel → name `vayu-alerts` → **Public** → Create.

---

## Part C · The Android signing key (steps 10–13)

The key signs every app build. **If it is lost, the app on every phone can never be updated.**

**Step 10 · The key file** (only for a brand-new project; Vayu already has one in `~/vayu-keys/`)
```bash
mkdir -p ~/vayu-keys && chmod 700 ~/vayu-keys
keytool -genkeypair -v -keystore ~/vayu-keys/vayu-release.jks -alias vayu -keyalg RSA -keysize 2048 -validity 10000
```
It asks for a store password and a key password. Then write `~/vayu-keys/keystore.properties`
(`chmod 600`), four lines:
```
storeFile=/Users/<you>/vayu-keys/vayu-release.jks
storePassword=<store password>
keyAlias=vayu
keyPassword=<key password>
```

**Step 11 🔐 The key file into Phase** → `vayu-owner` → Production → **`ANDROID_KEYSTORE_B64`**
```bash
shasum -a 256 ~/vayu-keys/vayu-release.jks          # note the fingerprint
base64 -i ~/vayu-keys/vayu-release.jks | tr -d '\n' | pbcopy
```
Paste into Phase (B2), Deploy. Check: copy it back from Phase (copy icon), then
```bash
pbpaste | base64 -d | shasum -a 256                 # must equal the fingerprint above
pbcopy < /dev/null
```

**Step 12 🔐 Its three passwords** → `vayu-owner` → Production
Open `~/vayu-keys/keystore.properties` (`open -e ~/vayu-keys/keystore.properties`) and copy each
value into its own secret: **`ANDROID_STORE_PASSWORD`** (storePassword), **`ANDROID_KEY_ALIAS`**
(keyAlias, usually `vayu`), **`ANDROID_KEY_PASSWORD`** (keyPassword). Deploy.

**Step 13 · Two offline copies**
USB stick (labelled, locked away at the office) and a private company drive folder: copy
`vayu-release.jks` only. Check each copy: `shasum -a 256 <copy>` gives the same fingerprint.

---

## Part D · DigitalOcean (steps 14–17)

**Step 14 · Account [OWNER]** cloud.digitalocean.com → sign up with the company email → card →
two-step login (step 8).

**Step 15 · Your SSH key** → Settings → Security → **Add SSH Key** → paste `~/.ssh/id_ed25519.pub`
→ name it after you (the owner's is `owner-mac`).

**Step 16 · The firewall** → Networking → Firewalls → **Create Firewall** `vayu-web`:
- Inbound rules: **SSH 22**, **HTTP 80**, **HTTPS 443**, sources All IPv4 + All IPv6. Delete any
  other inbound rule.
- Outbound rules: leave the defaults.
- Apply to Droplets: type the **tag** `vayu-web` (not a droplet name) → Create Firewall.
Why: only web and SSH can come in; the database, Redis and the app's inner port cannot. SSH is open
to all because GitHub deploys from changing addresses; the servers accept keys, never passwords.

**Step 17 🔐 DigitalOcean API token** → `vayu-owner` → Production → **`DO_API_TOKEN`**
API → **Generate New Token** → name `vayu-owner-laptop`, expiry 90 days, Full Access → copy → Phase,
Deploy. Write the expiry date in the setup log. Then:
```bash
doctl auth init                 # paste the token
doctl account get               # check: status "active"
```

---

## Part E · Cloudflare R2, file storage (steps 18–27)

dash.cloudflare.com **[OWNER]** (R2 needs a card) → left menu **R2 Object Storage**.

**Step 18 · Buckets** → **Create bucket**, three times, location hint **Asia-Pacific**, all
**private** (no public access, no custom domain): `vayu-staging`, `vayu-prod`, `vayu-backups`.

**Step 19 · CORS on `vayu-staging`** → bucket → Settings → CORS Policy → Add/Edit → replace all with:
```json
[{"AllowedOrigins": ["https://vayu-staging.carcid.in"],
  "AllowedMethods": ["GET", "PUT", "POST", "HEAD"], "AllowedHeaders": ["*"],
  "ExposeHeaders": ["ETag"], "MaxAgeSeconds": 3600}]
```
**Step 20 · CORS on `vayu-prod`**: the same with `https://vayu.carcid.in`. (`vayu-backups`: none.)
Why: without it, uploads from the web portal fail.

**Step 21 · Clean-up rules** → each bucket → Settings → Object lifecycle rules → Add rule:
- `vayu-staging` and `vayu-prod`: name `abort-unfinished-uploads`, all objects, **abort incomplete
  multipart uploads after 14 days**; do not delete objects.
- `vayu-backups`: name `expire-backups`, all objects, **delete objects after 35 days**, abort
  incomplete multipart uploads after 1 day.

**Step 22 · The backup lock** → `vayu-backups` → Settings → Bucket lock rules → Add rule: name
`keep-30-days`, prefix empty, retention **30 days** (not indefinite). Now nobody can delete a
backup younger than 30 days, not even someone who breaks into a server.

Steps 23–26: **Manage API tokens → Create Account API token**, permission **Object Read & Write**,
**Specify bucket**: only the bucket named, TTL **Forever**, no IP filtering → Create. The page shows
**Access Key ID** and **Secret Access Key** once: copy each straight into Phase (B2) and Deploy.

**Step 23 🔐 Token `vayu-staging-app`** (bucket `vayu-staging`) → `vayu` → **Staging** →
**`S3_ACCESS_KEY_ID`** and **`S3_SECRET_ACCESS_KEY`**.

**Step 24 🔐 Token `vayu-prod-app`** (bucket `vayu-prod`) → `vayu` → **Production** →
**`S3_ACCESS_KEY_ID`** and **`S3_SECRET_ACCESS_KEY`**.

**Step 25 🔐 Token `vayu-backups-staging`** (bucket `vayu-backups`) → `vayu` → **Staging** →
**`BACKUP_ACCESS_KEY_ID`** and **`BACKUP_SECRET_ACCESS_KEY`**.

**Step 26 🔐 Token `vayu-backups-prod`** (bucket `vayu-backups`) → `vayu` → **Production** →
**`BACKUP_ACCESS_KEY_ID`** and **`BACKUP_SECRET_ACCESS_KEY`**.

**Step 27 🔐 The storage address** → `vayu` → **Staging** and **Production** → **`S3_ENDPOINT_URL`**
The same token page shows the **S3 API** endpoint `https://<account id>.r2.cloudflarestorage.com`.
(Not secret, but every server needs it.)

---

## Part F · Firebase, phone notifications (steps 28–31)

console.firebase.google.com → project `vayu-8bb7a` (new project: Add project `vayu`, Analytics off,
then Add app → Android `in.carcid.vayu`) → gear → **Project settings**.

**Step 28 · The "Vayu Staging" app** → General → Your apps → **Add app** → Android → package
`in.carcid.vayu.staging`, nickname `Vayu Staging` → Register → **Download google-services.json** →
skip the other wizard steps. The file is not secret: it goes in `android/app/google-services.json`
through a PR (it must list both `in.carcid.vayu` and `in.carcid.vayu.staging`).

**Step 29 🔐 Staging's server key** → `vayu` → **Staging** → **`FIREBASE_SERVICE_ACCOUNT_JSON`**
Service accounts → **Generate new private key** → a JSON file downloads. Then:
```bash
pbcopy < ~/Downloads/<the downloaded file>.json
```
Paste the **whole file** as the value, Deploy, `pbcopy < /dev/null`, delete the downloaded file.

**Step 30 🔐 Production's server key** → `vayu` → **Production** → **`FIREBASE_SERVICE_ACCOUNT_JSON`**
The same, a **new** key (each server has its own).

**Step 31 · 🧪 Restrict the Firebase API key** (when "Vayu Staging" is on a phone)
console.cloud.google.com → project vayu → APIs & Services → Credentials → "Android key (auto created
by Firebase)": Application restrictions **Android apps**: `in.carcid.vayu` and
`in.carcid.vayu.staging` with the signing key's SHA-1
(`keytool -list -v -keystore ~/vayu-keys/vayu-release.jks -alias vayu | grep SHA1`); API
restrictions: Firebase Installations API, FCM Registration API. Save. Then check a notification
still arrives on the phone.

---

## Part G · Sentry, errors (steps 32–37)

sentry.io → organisation `car-cid` (new: create it).

**Step 32 · Projects** → `vayu-server` (Django), `vayu-web` (React), `vayu-android` (Android).
Each project → Settings → **Client Keys (DSN)** gives its address:

**Step 33 🔐** `vayu-server` DSN → `vayu` → **Staging and Production** → **`SENTRY_DSN`** (the same
value in both: Sentry tells them apart by the label each server sends).

**Step 34 🔐** `vayu-web` DSN → `vayu-owner` → **`SENTRY_DSN_WEB`**.

**Step 35 🔐** `vayu-android` DSN → `vayu-owner` → **`SENTRY_DSN_ANDROID`**.

**Step 36 🔐 Build token** → `vayu-owner` → **`SENTRY_AUTH_TOKEN`**
Settings → Developer Settings → **Organization Tokens** → Create → name `vayu-ci`. (Builds use it to
make error reports readable.)

**Step 37 · Alert to Slack**
1. Settings → Integrations → **Slack** → Add workspace → allow.
2. Alerts → **New Alert** → "Alert on all issues in selected projects" → the three `vayu-*`
   projects (not "all projects") → environment **production** → WHEN any: **A new issue is
   created**, **An issue escalates** → THEN Slack workspace → `#vayu-alerts`, and Notify Member →
   you (email) → name `vayu production errors` → **Send Test Notification** (a message arrives in
   Slack) → **Create Alert**.

---

## Part H · GitHub settings (steps 38–42) [OWNER]

github.com/ravi409455/vayu → **Settings**.

**Step 38 · Protect `main`** → Rules → Rulesets → New branch ruleset → name `main protect`,
Enforcement **Active**, bypass list empty, target **Include default branch**. Turn on: Restrict
deletions, Block force pushes, Require status checks to pass (add `backend`, `backend-gates`,
`web`, `android`, `docker`, `e2e`). ⚠️ Leave **Restrict updates OFF** (with an empty bypass list
nobody could change `main` at all). Save.

**Step 39 · Environments** → Environments → New environment:
- `staging`: Deployment branches → Selected → `main`. Save.
- `production`: tick **Required reviewers** → add who may release; Deployment branches → `main`;
  click **Save protection rules** (its own button).

**Step 40 · Outside pull requests** → Actions → General → "Require approval for all external
contributors" → Save.

**Step 41 · Web build settings** → Secrets and variables → Actions:
- Variables → New repository variable: **`SENTRY_ORG`** = `car-cid`; **`VITE_SENTRY_DSN`** = the
  value of `SENTRY_DSN_WEB` from Phase.
- Secrets → New repository secret 🔐: **`SENTRY_AUTH_TOKEN`** = the value from Phase.

**Step 42 · Check**
```bash
gh variable list --repo ravi409455/vayu         # SENTRY_ORG, VITE_SENTRY_DSN
gh secret list --repo ravi409455/vayu           # SENTRY_AUTH_TOKEN
```

---

## Part I · The staging server's settings in Phase (steps 43–49)

Each server reads **all** its settings from Phase at every deploy (`infra/secrets.sh`). Nobody
edits a settings file on a server.

**Step 43 · The non-secret settings** → app `vayu` → New Secret menu → **Import secrets** → paste
the whole file `infra/phase-staging.env` (open it in the repo) → import into **Staging only** →
Preview Import → **Deploy**. It adds 24 settings (address, sizes, bucket names, database name…).

**Step 44 🔐 `DJANGO_SECRET_KEY`** → `vayu` → Staging
```bash
python3 -c "import secrets;print(secrets.token_urlsafe(50),end='')" | pbcopy
```

**Step 45 🔐 `DB_PASSWORD`** → `vayu` → Staging (staging's own database): the same command again
(a new value).

**Step 46 🔐 `STAGING_TESTER_PASSWORD`** → `vayu` → Staging (password of the test logins)
```bash
python3 -c "import secrets;print(secrets.token_urlsafe(24),end='')" | pbcopy
```

**Step 47 🔐 The backup key pair** (once for the project)
The unlocking half → `vayu-owner` → **`BACKUP_AGE_SECRET_KEY`** (never on a server: it opens every
backup):
```bash
age-keygen 2>/dev/null | grep AGE-SECRET-KEY | tr -d '\n' | pbcopy
```
Paste, Deploy. **Then, with that still on the clipboard**, the locking half → `vayu` → **Staging and
Production** → **`BACKUP_PUBLIC_KEY`** (not secret; it can only lock):
```bash
pbpaste | age-keygen -y | tr -d '\n' | pbcopy
```
Paste, Deploy, `pbcopy < /dev/null`.

**Step 48 · Check Staging holds** the 24 imported values plus: `DJANGO_SECRET_KEY`, `DB_PASSWORD`,
`STAGING_TESTER_PASSWORD`, `SENTRY_DSN`, `S3_ENDPOINT_URL`, `S3_ACCESS_KEY_ID`,
`S3_SECRET_ACCESS_KEY`, `BACKUP_ACCESS_KEY_ID`, `BACKUP_SECRET_ACCESS_KEY`, `BACKUP_PUBLIC_KEY`,
`FIREBASE_SERVICE_ACCOUNT_JSON` (35 in all). Every one **Deployed**.

**Step 49 🔐 The server's own Phase key** → `vayu-owner` → **`PHASE_TOKEN_STAGING_SERVER`**
Phase → **Access Control** → Service Accounts → **Create Service Account** → name
`vayu-staging-server`, role **Service** → open app `vayu` → **Access** tab → Service accounts →
**Add service account** → pick it → environment **Staging only** → Add → back in Access Control →
Service Accounts → **Manage** → **+ Create Token** → name, expiry (none, or a year) → Create → copy
the `pss_service:v2:…` token → Phase (B2). Write any expiry date in the setup log.

---

## Part J · The staging server (steps 50–60)

**Step 50 · Create the droplet** → DigitalOcean → **Create → Droplets**:

| Setting | Value |
|---|---|
| Region | Bangalore (BLR1) |
| Image | Ubuntu 24.04 (LTS) x64 |
| Size | Basic → Regular → 2 vCPU / 2 GB ($18; staging is never bigger) |
| Monitoring | on |
| Backups | off (staging's backup is its snapshot) |
| Authentication | SSH Key (yours / `owner-mac`); never Password |
| Hostname | `vayu-staging` |
| Tags | `vayu-staging`, `vayu-web` |

Create → copy the **IP address**.

**Step 51 · The DNS name** → godaddy.com → My Products → carcid.in → **DNS** → **Add New Record**:
Type **A**, Name `vayu-staging`, Value the IP, TTL **600 seconds** → Save. Change no other record.
```bash
dig +short vayu-staging.carcid.in        # after a few minutes: prints the IP
```

**Step 52 · First contact** (trust the server's key once)
```bash
ssh -o StrictHostKeyChecking=accept-new root@<ip> 'uname -sr'
```

**Step 53 · Set up the server** (about 5 minutes; run from the `vayu` folder on your Mac)
```bash
ssh root@<ip> 'bash -s' < infra/bootstrap.sh
```
Installs updates and Docker, a firewall, automatic security updates, the user `deploy`, swap, the
code in `/srv/vayu` and the nightly backup timer; then root and passwords can no longer log in.
```bash
ssh root@<ip> true                     # check: "Permission denied" (good)
ssh deploy@<ip> 'docker --version'     # check: prints a Docker version
```

**Step 54 · The server's Phase key on the server** (the only secret ever typed onto a server)
```bash
ssh deploy@<ip>
umask 077 && nano /srv/vayu/.phase
```
Type these two lines (the token from Phase `PHASE_TOKEN_STAGING_SERVER`), save with Ctrl+O, Enter,
Ctrl+X, then `exit`:
```
PHASE_ENV=Staging
PHASE_SERVICE_TOKEN=pss_service:v2:...
```
Check (from your Mac):
```bash
ssh deploy@<ip> 'bash /srv/vayu/infra/secrets.sh'     # "settings: 36 values from Phase ..."
```
(36 = the 35 in Phase, with the Firebase key turned into a file plus its two file paths.)
An error names what is missing in Phase (step 48) or a value with a line break inside.

**Step 55 🔐 GitHub's deploy key** (a key only GitHub uses, locked to the deploy script)
```bash
K=$(mktemp -d)
ssh-keygen -q -t ed25519 -N "" -C github-deploy-staging -f "$K/key"
ssh deploy@<ip> "echo 'command=\"/srv/vayu/infra/deploy.sh\",restrict $(cat $K/key.pub)' >> ~/.ssh/authorized_keys"
ssh-keyscan -t ed25519 <ip> 2>/dev/null | sed 's/^[^ ]*/vayu-staging.carcid.in/' > "$K/known_hosts"
```

**Step 56 🔐 GitHub environment `staging` secrets** (same Terminal)
```bash
gh secret set SSH_KEY --env staging --repo ravi409455/vayu < "$K/key"
gh secret set SSH_HOST --env staging --repo ravi409455/vayu --body vayu-staging.carcid.in
gh secret set SSH_KNOWN_HOSTS --env staging --repo ravi409455/vayu < "$K/known_hosts"
gh secret list --env staging --repo ravi409455/vayu          # check: the three names
```

**Step 57 🔐 The deploy key's copy** → `vayu-owner` → **`DEPLOY_SSH_KEY_STAGING`**
```bash
pbcopy < "$K/key"           # paste into Phase, Deploy
pbcopy < /dev/null; rm -r "$K"
```

**Step 58 · First deploy**
GitHub → **Actions** → **deploy** → **Run workflow** → paste the full commit id of the newest `main`:
```bash
git fetch && git rev-parse origin/main
```
(Or merge any PR: it deploys by itself.) Wait for **build** and **staging** to turn green. The
**production** step then waits for Approve: until production exists, open the run and **Cancel** it.

**Step 59 · Check staging**
```bash
curl -s https://vayu-staging.carcid.in/api/v1/health                    # {"status":"ok"}
ssh deploy@vayu-staging.carcid.in 'cat /srv/vayu/.deployed; docker ps --format "{{.Names}}: {{.Status}}"'
```
`.deployed` = the commit; 8 containers up (api healthy, worker, zip-worker, pdf-worker, beat,
postgres, redis, caddy). Open https://vayu-staging.carcid.in in a browser: the sign-in page, with a
padlock (the https certificate is made by itself).

**Step 60 · Test logins and test bookings** (about 20 minutes; do not deploy meanwhile)
```bash
ssh -o ServerAliveInterval=30 deploy@vayu-staging.carcid.in 'cd /srv/vayu && bash infra/secrets.sh >/dev/null && source infra/lib.sh && export VAYU_TAG=$(cat .deployed) P=$(envval STAGING_TESTER_PASSWORD) && compose exec -T -e P api sh -c "python manage.py seed_test_data --confirm staging-1 --password \"\$P\""'
```
It sets up every form, report and list, logins `admin`, `ops`, `ops2`, `expert` … `expert7`
(password: Phase `STAGING_TESTER_PASSWORD`) and 30 bookings in every stage. It refuses on
production. Do not look at full process lists (`ps`, `docker top`) while it runs: the password is
visible there. Check: sign in at https://vayu-staging.carcid.in as `ops`.

---

## Part K · Everyday work

**Release a change.** Merge a PR into `main` (only through a PR with green checks). CI runs, the
deploy workflow builds the images **once** and puts them on staging by itself. Check staging. To
release: open the run → **Review deployments** → production → **Approve**: the same images go to
production, after a database safety copy. Release outside 9 am–8 pm (each deploy restarts services
for 10–20 s). If health fails after a deploy, the server puts the previous version back by itself.

**Roll back.** Actions → deploy → **Run workflow** → the full commit id to go back to (the Actions
history shows earlier ones). About 3 minutes; the images are reused. The database is not rolled back.

**Change a setting or secret.** Change it in Phase → **Deploy** → Actions → deploy → Run workflow →
the commit that is live now (`ssh deploy@<server> cat /srv/vayu/.deployed`).

**Look at a server.**
```bash
ssh deploy@<server>
cd /srv/vayu && source infra/lib.sh && export VAYU_TAG=$(cat .deployed)
compose ps                        # what runs
compose logs --tail 100 api       # or worker, zip-worker, pdf-worker, beat, caddy
docker stats --no-stream          # CPU and memory per service
```

**Staging on demand** (a switched-off server is still billed; staging lives as a snapshot).
From GitHub: **Actions → staging → Run workflow** (branch `main`) → choose:

| Choice | What happens |
|---|---|
| `up` | fails if staging is already running; otherwise creates it from the newest snapshot with staging's fixed SSH key, points `vayu-staging.carcid.in` at it, checks the key, then starts **deploy** for the newest built commit of main: staging deploys, production waits for your **Approve**, as after a merge (about 10 minutes) |
| `down` | points the name at the "off" marker `192.0.2.1`, then power off → snapshot → delete (billing stops; the 2 newest snapshots are kept) |
| `status` | is staging up, where its name points, which snapshots are kept |

The same from the laptop: `infra/staging.sh up | down | status` (`up` needs `STAGING_HOST_KEY` set).
No DNS editing by hand: GoDaddy hands just `vayu-staging` to DigitalOcean's DNS (3 NS records). While
staging is off, a merge shows "staging is off" (green, not deployed) and production waits; `up` brings
staging to the newest main by itself. To release: `up`, test, Approve. When done testing: `down`.

**A phone says "your other phone still has work".** One phone per person: sync the old phone, or an
Admin signs it out (web → Users → ⋯ → **Sign out of every device**).

**The Android app 🧪.** On a Mac with `~/vayu-keys/` (step 10), and `SENTRY_DSN_ANDROID`,
`SENTRY_AUTH_TOKEN` set in the Terminal. The version code must be higher than every build ever
installed:
```bash
cd android
./gradlew assembleStaging -Pvayu.versionCode=<n> -Pvayu.versionName=<x.y.z>    # "Vayu Staging"
./gradlew assembleRelease -Pvayu.versionCode=<n> -Pvayu.versionName=<x.y.z>    # "Vayu"
```
Publish it on its server: `docs/runbook-new-server.md` §3 (`publish_apk`). Then the welcome pages'
**Download the app** button (`/welcome/engineers`, `/welcome/ops`) offers it.

---

## Part L · Alerts and backups

**DigitalOcean alerts** (Insights → Alerts → Alert Rules → Create): four rules, resource type
**Droplets**, resource **tag `vayu-web`** (the form starts on *All Droplets*: change it),
notification channel Slack `#vayu-alerts`, re-notify every 4 hours:

| Rule name | Condition |
|---|---|
| `vayu: CPU above 80% for 10 min` | CPU ≥ 80% over 10 minutes |
| `vayu: memory above 85% for 10 min` | Memory ≥ 85% over 10 minutes |
| `vayu: disk above 80%` | Disk ≥ 80% over 5 minutes |
| `vayu: load above 3 for 10 min` | Load average (5 min) ≥ 3 over 10 minutes |

Make them in the web form, not with `doctl` (it only knows the old alert system).

**Backups.** Every night at 02:00 IST the server runs `infra/backup.sh`: database → encrypted with
`BACKUP_PUBLIC_KEY` → `vayu-backups`. Check: `ssh deploy@<server> 'systemctl list-timers vayu-backup.timer'`.

🧪 **Uptime checks** (Better Stack, free): a monitor on `https://<server>/api/v1/health` every
minute; heartbeats → Phase `vayu` → that environment → **`BACKUP_HEARTBEAT_URL`** 🔐 and
**`WORKERS_HEARTBEAT_URL`** 🔐; Slack `#vayu-alerts`.

🧪 **Restore drill** (first Monday of the month): `docs/runbook-new-server.md` §7
(`infra/restore.sh`; it asks for `BACKUP_AGE_SECRET_KEY`).

---

## Part M · Production 🧪 (not built yet)

Do it only after staging passed all its checks (`docs/plan-deploy.md` Phase 6).

1. **Droplet** `vayu-prod` (step 50 with: hostname `vayu-prod`, tag **`vayu-web` only**).
2. **Managed database** → Create → Databases → PostgreSQL 16, BLR1, 1 GB, name `vayu-prod-db` →
   Settings → Trusted sources: `vayu-prod` only → Users & Databases: database `vayu`, user `vayu` →
   🔐 its password → Phase `vayu` → Production **`DB_PASSWORD`**; its **private (VPC)** host →
   **`DB_HOST`** → Maintenance window Sunday 21:30 UTC.
3. **Phase Production**: import `infra/phase-production.env` (step 43, into Production; its
   `DB_HOST` line replaced by step 2), 🔐 **`DJANGO_SECRET_KEY`** (step 44, a new value).
   Check against step 48 (no `STAGING_TESTER_PASSWORD`).
4. 🔐 Service account `vayu-prod-server`, **Production only** (step 49) → `vayu-owner` →
   **`PHASE_TOKEN_PROD_SERVER`**.
5. **DNS**: A record `vayu` → the production IP (step 51).
6. Steps 52–57 with `PHASE_ENV=Production`, key comment `github-deploy-prod`, GitHub environment
   **production**, `SSH_HOST` = `vayu.carcid.in`, Phase **`DEPLOY_SSH_KEY_PROD`** 🔐.
7. Deploy: the next run's production step → **Approve**. Check as step 59 with `vayu.carcid.in`.
8. Staff: `docs/runbook-new-server.md` §2 (`setup_platform --users`). Never `seed_test_data`.
9. Release app build published; uptime checks and heartbeats; first restore drill.

---

## Part N · Every secret, in one table

| # | Secret | Phase app → environment | Made at | Used by |
|---|---|---|---|---|
| 1 | `ANDROID_KEYSTORE_B64` | vayu-owner → Production | step 11 | app release builds (backup copy) |
| 2 | `ANDROID_STORE_PASSWORD` | vayu-owner → Production | step 12 | app builds |
| 3 | `ANDROID_KEY_ALIAS` | vayu-owner → Production | step 12 | app builds |
| 4 | `ANDROID_KEY_PASSWORD` | vayu-owner → Production | step 12 | app builds |
| 5 | `DO_API_TOKEN` | vayu-owner → Production | step 17 | `doctl`, `infra/staging.sh` (expires) |
| 6 | `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY` | vayu → Staging | step 23 | staging server: files |
| 7 | `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY` | vayu → Production | step 24 | production server: files |
| 8 | `BACKUP_ACCESS_KEY_ID`, `BACKUP_SECRET_ACCESS_KEY` | vayu → Staging | step 25 | staging backups |
| 9 | `BACKUP_ACCESS_KEY_ID`, `BACKUP_SECRET_ACCESS_KEY` | vayu → Production | step 26 | production backups |
| 10 | `S3_ENDPOINT_URL` | vayu → Staging, Production | step 27 | both servers |
| 11 | `FIREBASE_SERVICE_ACCOUNT_JSON` | vayu → Staging | step 29 | staging notifications |
| 12 | `FIREBASE_SERVICE_ACCOUNT_JSON` | vayu → Production | step 30 | production notifications |
| 13 | `SENTRY_DSN` | vayu → Staging, Production | step 33 | both servers |
| 14 | `SENTRY_DSN_WEB` | vayu-owner → Production | step 34 | GitHub variable `VITE_SENTRY_DSN` |
| 15 | `SENTRY_DSN_ANDROID` | vayu-owner → Production | step 35 | app builds |
| 16 | `SENTRY_AUTH_TOKEN` | vayu-owner → Production | step 36 | GitHub secret, app builds |
| 17 | `DJANGO_SECRET_KEY` | vayu → Staging | step 44 | staging server |
| 18 | `DB_PASSWORD` | vayu → Staging | step 45 | staging database |
| 19 | `STAGING_TESTER_PASSWORD` | vayu → Staging | step 46 | test logins |
| 20 | `BACKUP_AGE_SECRET_KEY` | vayu-owner → Production | step 47 | restoring backups (never on a server) |
| 21 | `BACKUP_PUBLIC_KEY` | vayu → Staging, Production | step 47 | both servers: lock backups |
| 22 | `PHASE_TOKEN_STAGING_SERVER` | vayu-owner → Production | step 49 | staging `/srv/vayu/.phase` |
| 23 | `DEPLOY_SSH_KEY_STAGING` | vayu-owner → Production | step 57 | copy of GitHub `staging` `SSH_KEY` |
| 24 | `OWNER_SSH_PRIVATE_KEY` | vayu-owner → Production | step 4 (owner) | owner's server access (backup copy) |
| 25 🧪 | `BACKUP_HEARTBEAT_URL`, `WORKERS_HEARTBEAT_URL` | vayu → each environment | Part L | uptime alerts |
| 26 🧪 | `DB_PASSWORD`, `DB_HOST`, `DJANGO_SECRET_KEY` | vayu → Production | Part M | production |
| 27 🧪 | `PHASE_TOKEN_PROD_SERVER`, `DEPLOY_SSH_KEY_PROD` | vayu-owner → Production | Part M | production server, GitHub |

Plus, outside Phase: the 24 non-secret values (`infra/phase-staging.env` /
`phase-production.env`, imported into Phase); GitHub `SENTRY_ORG`, `VITE_SENTRY_DSN` (variables),
`SENTRY_AUTH_TOKEN` (secret), environment `staging` → `SSH_KEY`, `SSH_HOST`, `SSH_KNOWN_HOSTS`; the
Phase sudo password, recovery kit, account passwords and 2-step recovery codes (password manager);
the signing key's offline copies (step 13).

---

## Part O · When something goes wrong

| You see | Why | Do |
|---|---|---|
| Deploy: "error: missing in Phase: X" | X not in that environment, or not **Deployed** in Phase | add it (B2), Deploy, Run workflow again |
| "X has a line break or a '" | a value with a line break inside | fix the value in Phase |
| "could not fetch from Phase" | the server's token is wrong or expired, or Phase is down | check `/srv/vayu/.phase`; the last good settings stay meanwhile |
| Deploy says "staging is off" | staging is on demand and switched off (on purpose) | Actions → staging → `up` (it deploys the newest main) |
| staging `up` says "an SSH key that is not staging's" | the new server did not take the fixed key | look at the droplet in DigitalOcean, then Actions → staging → `down` and `up` again |
| Staging deploy fails at SSH (red) | staging is on but not answering | `infra/staging.sh status`; the droplet's console in DigitalOcean |
| A run waits forever on production | it needs Approve | Approve (release) or Cancel (no production yet) |
| A merge did not reach staging | a newer merge cancelled its CI; only the newest deploys | `.deployed` must equal the newest `main` commit |
| Phone: "your other phone still has work" (409) | one phone per person | sync the old phone, or an Admin signs it out |
| Sentry: "vayu-alerts does not exist" | channel missing or private | create it public, or `/invite @Sentry` in it |
| GitHub refuses a push to `main` | the ruleset | open a PR |
| A long SSH command ends with exit 255 | the connection dropped while idle | use `-o ServerAliveInterval=30`; check whether it finished |
| Your Mac cannot find a new name | it remembered "not found" from before | wait a few minutes or use the IP |
| `chmod: … No such file` right after editing on the server | the command ran on the Mac, not the server | run it in the server's Terminal (B4) |

---

## Part P · Dates to remember

| What | When |
|---|---|
| DigitalOcean API token `vayu-owner-laptop` | expires around 2027-02-24: step 17 again |
| Phase service tokens | if given an expiry: step 49 again, then step 54 |
| https certificates | renew by themselves |
| Restore drill | first Monday of every month |
| Ubuntu 24.04 | supported to 2029 |

The live list of every account, name and address: **"Where everything lives"** in
`docs/deploy-setup-log.md`.
