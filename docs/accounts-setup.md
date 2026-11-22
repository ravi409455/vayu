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

## Android signing key (Phase 15)
Create once, and back it up before first use. **If it's lost, installed apps can never be
updated.**
```bash
keytool -genkeypair -v -keystore vayu-release.jks -alias vayu \
  -keyalg RSA -keysize 2048 -validity 10000
```
Store the file and its passwords in the company password manager plus two offline copies. It must
never enter the repo.

## Sentry (at deploy)
1. sentry.io → sign up (free Developer plan) → create an organization.
2. Create three projects: **Django** `vayu-server`, **React** `vayu-web`, **Android** `vayu-android`.
3. For each: Settings → Projects → **Client Keys (DSN)**. The DSN goes in `SENTRY_DSN`
   (server env). The server refuses to start in production without it.

## DNS (at deploy)
At wherever carcid.in is registered, add `A` records pointing to the DigitalOcean droplets:
`app.carcid.in` and `verify.carcid.in` → production IP; `staging.carcid.in` → staging IP.

## DigitalOcean (the very end)
Production droplet: Bangalore (BLR1), 4 vCPU / 8 GB. Staging: smaller (2 vCPU / 4 GB is enough).
Add your SSH key at creation. Backups are yours to configure.

## Decide before Phase 13
- **Android application ID** (permanent once published). Suggestion: `in.carcid.vayu`.
