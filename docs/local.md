# Run Vayu on your laptop (for manual review)

```bash
scripts/local.sh up        # first run: starts everything, creates the database and demo data
```
Then open **http://localhost:5173**. Everything real is running: Postgres, Redis, the API, a Celery
worker (PDFs, ZIPs, webhooks, file checks), the scheduler (webhook retries), and a file store that
stands in for Cloudflare R2. Needs Docker Desktop, `uv` and Node 22.

| Command | What it does |
|---|---|
| `scripts/local.sh up` | start (safe to repeat) |
| `scripts/local.sh down` | stop the app (your data stays) |
| `scripts/local.sh reset` | **throw away** the local database and files, then start fresh with demo data |
| `scripts/local.sh status` | what is running |

Logs are in `.local/` (`api.log`, `worker.log`, `beat.log`, `web.log`).

## Sign in (password for everyone: `Vayu-local-1`)
| User | Role | Try |
|---|---|---|
| `admin` | Admin | forms, PDF templates, users, roles, integrations, API keys, audit |
| `ops` | Ops | job board, bookings, reports, problems, dashboards |
| `expert` | Expert | My jobs → DEMO-2 (assigned to Ravi) |
| `expert2` | Expert | a second expert, to try reassigning and conflicts |
| `newuser` | Ops | must choose a new password at first sign in |

Demo data: **DEMO-1** not assigned, **DEMO-2** assigned to `expert`, **DEMO-3** completed with a PDF.
The **PDI** form is a small stand-in. Your real inspection forms (PDI, Used car, EV) are meant to be
built by you in the form builder (Admin → Forms): that is the test of the builder itself.

## A suggested walk-through
1. **Admin** → Forms → open PDI → "Start a new draft", add a field, "Check & publish".
2. **Admin** → PDF templates → open PDI → add a block, map a field, Preview PDF (use DEMO-3's id from the URL).
3. **Ops** → Job board → New booking → assign to Ravi → open it.
4. **Expert** (other browser or private window) → My jobs → start the inspection, take/choose photos, submit.
   Watch the stage go Submitted → Completed, then see the PDF under the booking's Report tab.
5. **Ops** → edit an answer → Ratings tab (override a rating) → Report tab: "Out of date" → Regenerate.
6. Open the same inspection in two windows, change different fields in each, save in both: the second
   save shows "someone changed this" and keeps both people's fields.
7. **Admin** → Integrations → new integration → start a receiver:
   `python3 scripts/webhook_receiver.py --secret <the secret shown once>` and use the **Test** button.
8. **Admin** → API keys → create one → `curl -H "Authorization: Api-Key <key>" http://localhost:5173/api/v1/ext/bookings`.
   Docs: http://localhost:5173/api/v1/docs.
9. Reassign a started job to `expert2` (Ops → "Force release", then assign) to see how conflicts show up.

## Things to know
* Files are kept in a Docker volume (`s3-data`); `reset` empties them.
* Webhooks and the receiver may use plain `http://127.0.0.1:...` here; production requires https and
  refuses private addresses.
* The report check page is http://localhost:5173/verify/<token> (the link is on the booking's Report tab).
* Check the stack itself any time: `cd web && npx playwright test -c playwright.local.config.ts`
  (this uses the demo data, so run `scripts/local.sh reset` afterwards to get it back).
* Not part of this setup: your real Cloudflare R2 buckets (see `docs/r2-check.md`), email/SMS, push.
