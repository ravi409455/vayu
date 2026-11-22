# Accounts setup guide

Create these under a **company email**, not a personal one, and keep owner access with at least
two people. **Never paste secret keys into chat or commit them.** They go in git-ignored
`.env.*` files (local) and the server's env file (deploy). Screens change; if a label differs,
look for the closest one.

| Account | Needed at | Why |
|---|---|---|
| GitHub | done | code + CI |
| Cloudflare R2 | **Phase 6** (~week 6) | photo/video/PDF storage |
| Firebase (FCM) | **Phase 15** | push notifications to experts |
| Android keystore | **Phase 15** | signing the APK (no account; a file) |
| Sentry | at deploy | error tracking |
| DNS for carcid.in | at deploy | app / staging / verify subdomains |
| DigitalOcean | at the very end | the two servers |

## Cloudflare R2 (Phase 6)
1. Sign up at dash.cloudflare.com. R2 needs a payment method on file even though the free tier
   (10 GB, no download fees) will cover early use.
2. Left menu → **R2 Object Storage** → enable R2.
3. Create two buckets: `vayu-staging` and `vayu-prod` (location hint: Asia-Pacific). Keep them
   **private**: no public access, no custom domain.
4. R2 → **Manage API tokens** → create a token with **Object Read & Write**, limited to those two
   buckets. Copy the **Access Key ID** and **Secret Access Key** (shown once) and note the
   **S3 endpoint** `https://<ACCOUNT_ID>.r2.cloudflarestorage.com`.
5. On each bucket → **Settings → CORS policy**, allow:
   - origins: `https://app.carcid.in`, `https://staging.carcid.in`, `http://localhost:5173`
   - methods: `GET, PUT, POST, HEAD`; allowed headers: `*`; **expose header `ETag`**; max age 3600.
   (Browser uploads break without CORS; the ETag header is required for multipart uploads.)
6. Put the key pair in `backend/.env.local` (git-ignored). Tell me only the bucket names and
   account ID, never the secret.

## Firebase / push (Phase 15)
1. console.firebase.google.com → **Add project** `vayu` (turn Google Analytics off).
2. Project settings → **Add app → Android**. The **package name is permanent** (see "Decide
   before Phase 13" below). Download `google-services.json` (goes into the Android project).
3. Project settings → **Service accounts → Generate new private key**. This JSON lets the backend
   send pushes. It is a secret: server env only, never in git.

Where the two files go:

| File | What it is | Where it lives |
|---|---|---|
| `google-services.json` | App config for Android (not a secret) | `android/app/google-services.json`, committed |
| service-account JSON (`...-firebase-adminsdk-....json`) | **Secret** key that can send pushes as you | `~/vayu-keys/firebase-service-account.json`; its path goes in `FIREBASE_CREDENTIALS_FILE` in `backend/.env.local`. On the server, a file outside the repo, mounted into the api container read-only. Never in git (`.gitignore` blocks the usual names). |

## Android signing key (Phase 15)
**Not needed until Phase 15.** Create it once, and back it up before first use. **If it's lost,
installed apps can never be updated.**

`keytool` comes with a Java JDK, which this Mac doesn't have yet. Either install Android Studio
(needed from Phase 13 anyway; it bundles a JDK) or run `brew install openjdk@17`. Then create
the key **outside the repo**:
```bash
mkdir -p ~/vayu-keys && cd ~/vayu-keys
keytool -genkeypair -v -keystore vayu-release.jks -alias vayu \
  -keyalg RSA -keysize 2048 -validity 10000
```
With Homebrew's JDK, `keytool` may not be on your PATH; run
`/opt/homebrew/opt/openjdk@17/bin/keytool` instead. Store the file and its passwords in the
company password manager plus two offline copies. It must never enter the repo (`*.jks` is
git-ignored as a safety net).

## Sentry (needed at deploy; the web and Android DSNs are used in Phases 10 and 15)
Sentry catches crashes and errors in the server, the web app and the Android app, and shows the
stack trace and what the user did. Screens change; look for the closest label.

### 1. Create the account
1. Go to **sentry.io** → **Get Started** and sign up with the **company email** (or GitHub).
2. **Choose the data region** when asked (US or EU). It **cannot be changed later**. Sentry has no
   India region, so we keep personal data out of events (see step 5). EU is the safer choice for
   customer data.
3. Create the **organization**: name `Car CID` (the slug becomes part of URLs, e.g. `car-cid`).
4. Plan: stay on the free **Developer** plan. It is **limited to one user**, so only one person
   can log in. A paid Team plan is needed to add more people; don't upgrade until you need it.
   Check **Settings → Subscription** for the current error quota.
5. If you're asked to enable tracing, session replay or profiling, you can say no; we only need
   **errors**.

### 2. Create three projects
**Projects → Create Project**, one each. For every project choose the platform first, then the
name, and set the team to the default. Choose **"Alert me on every new issue"** when asked.
| Platform to pick | Project name | Used by |
|---|---|---|
| **Django** | `vayu-server` | backend |
| **React** | `vayu-web` | web app (Phase 10) |
| **Android** | `vayu-android` | Android app (Phase 15) |

Sentry shows a setup page with sample code. **You don't need to follow it**; we add the SDK in
our code. Just copy the DSN from it.

### 3. Copy each project's DSN
The DSN is a URL like `https://<key>@o123456.ingest.sentry.io/456789`. To find it later:
**Settings → Projects → (project) → Client Keys (DSN)**, then copy the **DSN** value.
- `vayu-server` DSN → `SENTRY_DSN` in the server env files `.env.staging` and `.env.prod` (see
  `.env.example`). The server **refuses to start in production without it**.
- `vayu-web` DSN → used in the web build (Phase 10).
- `vayu-android` DSN → used in the Android build (Phase 15).

A DSN only lets someone *send* events to your project. It is not a password, but treat it as
configuration and keep it out of chat. Leave `SENTRY_DSN` empty in local development so test
runs never create noise.

### 4. Separate staging from production
Don't create extra projects for staging. Both servers use the **same project and DSN**, with a
different environment tag in each env file:
```
SENTRY_ENVIRONMENT=staging      # in .env.staging
SENTRY_ENVIRONMENT=production   # in .env.prod
```
The Sentry SDK reads this variable by itself. In Sentry, use the **environment filter** at the top
of the Issues page to look at one at a time.

### 5. Keep personal data out of events
Customer names, phone numbers and number plates must not leak into error reports. Our code
already sets `send_default_pii=False`. Also check in Sentry:
**Settings → Security & Privacy**: turn **Data Scrubber** on, **Use Default Scrubbers** on, and
**Prevent Storing of IP Addresses** on.

### 6. Make it tell you about errors
1. **Alerts → Create Alert → Issues** (per project).
2. Condition: **A new issue is created**. Environment: **production**.
3. Action: **Send a notification to** yourself (email). If the project already has the default
   "high priority issues" alert, keep it.
4. Optional later: **Settings → Integrations → Slack** to post alerts to a channel.

### 7. Check it works (after the server is deployed, or locally once)
With the `vayu-server` DSN in `SENTRY_DSN`:
```bash
cd backend
SENTRY_DSN='<paste-dsn>' DJANGO_SETTINGS_MODULE=vayu.settings.test \
  uv run python manage.py shell -c "import sentry_sdk; sentry_sdk.capture_message('vayu test'); sentry_sdk.flush()"
```
The message `vayu test` should appear in **Issues** within a minute. Then remove the DSN from your
shell and don't leave it in `.env.local`.

### 8. Keep the free quota safe
Developer-plan limits drop events once the monthly quota is used; they don't bill you. If one
noisy bug floods the quota, set a cap: **Settings → Projects → (project) → Client Keys → Configure
→ Rate Limit**.

## DNS (GoDaddy): prepare now, add records at deploy
`carcid.in` is registered at **GoDaddy** and its DNS is hosted there (nameservers
`ns19/ns20.domaincontrol.com`). We only **add three subdomain records** there. We do **not** move
the domain or change its nameservers, because that could break the existing website and email.

### The three names
| Name | Record | Points to | Used for |
|---|---|---|---|
| `app.carcid.in` | A | production server IP | web app + API (`/api/v1`) + APK download page |
| `verify.carcid.in` | CNAME | `app.carcid.in` | public page behind the QR code on every PDF |
| `staging.carcid.in` | A | staging server IP | staging copy used to build and test forms |

- **`verify.carcid.in` is permanent.** The QR code printed on each report contains this address,
  so every report ever issued depends on it. Pick the name now, and never rename it.
- `verify` is a CNAME to `app`, so if the production server ever changes, one record moves both.

### Do now (about 10 minutes, no server needed)
1. Log in at **godaddy.com** → profile menu → **My Products** → find `carcid.in` → **DNS**
   (sometimes shown as **Manage DNS**).
2. Make sure you can open the **records table** and the **Add New Record** button. If you can't
   (the domain belongs to someone else's GoDaddy account), get delegate or admin access now.
3. Check the table for conflicts and fix them before deploy:
   - Existing records named `app`, `staging` or `verify`. A name can't be both a CNAME and
     another record, so remove or rename any clash.
   - A wildcard `*` record. It's allowed, but tell me; it can hide mistakes.
   - A **CAA** record. If one exists, it must allow `letsencrypt.org`, or HTTPS certificates
     will fail. Add `0 issue "letsencrypt.org"` if needed.
4. Don't touch `@`, `www`, `MX`, `TXT` (email, SPF, DKIM) or the nameservers.

### Do at deploy, once the servers exist
For each row in the table above: **Add New Record** → choose the **Type** → **Name** is only the
part before `.carcid.in` (e.g. `app`, not `app.carcid.in`) → **Value** is the IP address (for the
CNAME, `app.carcid.in`) → **TTL** the shortest offered (e.g. 600 seconds) → **Save**.

Use a **Reserved IP** on DigitalOcean for each server and point DNS at it. Then a rebuilt or
resized server keeps the same address and DNS never needs to change.

### Check it
Records usually work within minutes. From any terminal:
```bash
dig +short app.carcid.in        # should print the production IP
dig +short verify.carcid.in     # should print app.carcid.in, then the same IP
dig +short staging.carcid.in    # should print the staging IP
curl -I https://app.carcid.in/api/v1/health   # HTTP 200 once the server is running
```
**HTTPS is automatic.** Caddy gets a free certificate from Let's Encrypt the first time a
browser asks, provided DNS already points to the server and **ports 80 and 443 are open** in the
DigitalOcean firewall (allow only 22, 80 and 443). If DNS is wrong, Caddy retries and logs
errors; fix DNS and it succeeds on its own.

### Where the names are used in the code
`ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` in the server env files, the CORS rules on the R2
buckets (already in this guide), and the Caddyfile (`verify.carcid.in` is added in Phase 7 when
the verify page exists).

## DigitalOcean (the very end)
Production droplet: Bangalore (BLR1), 4 vCPU / 8 GB. Staging: smaller (2 vCPU / 4 GB is enough).
Add your SSH key at creation. Backups are yours to configure.

## Decide before Phase 13
- **Android application ID** (permanent once published). Suggestion: `in.carcid.vayu`.
