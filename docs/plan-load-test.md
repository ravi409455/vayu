# Plan: load tests and server sizing

Agreed with the owner on 2026-11-27. Two tests, one plan:

| Test | Question it answers | Servers |
|---|---|---|
| **1. Low-cost test** | Does a cheap server handle today's real load properly? | $12 (1 vCPU / 2 GB), $18 (2 vCPU / 2 GB), $24 (2 vCPU / 4 GB) |
| **2. Capacity test** | How much can the system take, what breaks first, and when must we upgrade? | the cheapest size that passed test 1, and $24 |

Production (deploy plan, Phase 7) gets the cheapest size that passes test 1. This replaces the
old "200 users for 10 minutes" check (deploy plan, Phase 6 check 7), which only timed read-only
pages and never exercised uploads, PDFs, webhooks or the external API. Not built yet.

## 1. Preconditions

- **PR 42 merged** (photos for a PDF fetched 8 at a time; render limit 120 s). Before it, a full
  PDI took 43 s on staging (30 s of it fetching ~150 photos one by one), so the 30 s PDF target
  would fail for a reason already fixed.
- **Phase 6 functional checks passed** (real phone, push, PDF, QR, backups): first prove it works,
  then size it.
- A 5-minute **dry run on the Mac** at tiny load: checks the scripts, decides nothing.

## 2. The load (the owner's numbers; never scaled up without asking)

| What | Per day (7 days a week) | One hour at 1× |
|---|---|---|
| Users | 50 experts (phones), 5 Ops (web) | all 55 active, each with their own login |
| New bookings | 200 | 18 |
| Inspections finished | 100, spread evenly 9 am–8 pm | 9, of which 2 are 150-photo reports (the old requirement's worst case) |
| Files per inspection | 100 photos (~500 KB, shrunk on the phone) + 15 videos (30 s, 720p at 2.5 Mbit/s ≈ 10 MB) ≈ **200 MB** | ~1,035 files, ~1.8 GB |
| PDFs | 6 per booking: 1 automatic + 5 Regenerate (changes only mark a PDF out of date) | 54 |
| Outgoing webhooks | exactly 15 per booking over its life | 270 |
| External system (REST API key) | peaks of 100 calls/min | 100/min the whole hour: ~200 writes (the 18 creates + changes), the rest reads |
| Pushes | one per assignment | sent for real to Firebase, to fake device tokens (nobody receives anything) |

**Known limit:** a day busier than this is not proven by test 1; test 2 shows how much room there
is, and the server alerts (deploy plan 5.5) show it in real life.

## 3. Pass targets (both tests)

| Check | Target (95 of 100 must meet it) |
|---|---|
| Web and API answers | ≤ 0.5 s; under 1% errors |
| Upload checked (fingerprint, previews) | ≤ 5 min after upload |
| PDF ready after submit or Regenerate (100-photo report) | ≤ 30 s |
| PDF ready, 150-photo report (old requirement) | ≤ 2 min |
| Webhook delivered after its event | ≤ 5 s |
| Server | no process killed for memory; swap barely used; CPU not pinned at 100% |
| **Zero loss** (old requirement) | every answer and file the test sent is stored and verified, counted at the end |

Every run also reports the real numbers (for example "PDF typically 22 s, worst 41 s").

## 4. Test 1: low-cost

- One run per size: $12, $18, $24, each **one hour** at 1× (an hour holds 9 inspections and 54
  PDFs; a shorter run measures too few PDFs to trust the 95-in-100 figure).
- Postgres runs on the same server in every run.
- Then **one database check**: the cheapest passing size against a temporary managed Postgres
  (1 GB, destroyed after): connections and speed. If the cheapest size also passes with Postgres
  on the box, capacity is no reason to pay for managed; the choice is safety (restore to any
  minute vs a nightly copy), and it is the owner's.

## 5. Test 2: capacity

- Load in steps, **15 minutes each: 1×, 2×, 3×, 4×, 6×, 8×**. Everything grows together: users
  (4× = 200 experts + 20 Ops, about the old 200-user requirement), bookings, inspections, PDFs,
  webhooks, API calls.
- **Each limit is recorded, the climb stops only on real failure.** A missed target is noted ("PDF
  over 30 s from 2×") and the climb goes on; it stops on errors above 1%, a process killed for
  memory, or work that piles up and never clears.
- **If PDFs are the first limit**, one extra step at that load with 2 PDFs rendered at a time
  instead of 1: shows whether a setting, not a bigger server, moves the limit.
- Runs on the cheapest size that passed test 1, and on $24.
- Result per size: the highest step where every target held, and the step where each one broke.
  That says how far today's load can grow before an upgrade.

## 6. How it runs (scripted; owner's steps: this approval and "go")

Staging is not touched: other sessions use it, and the history would replace its test data.

1. **Throwaway server** per size from the staging snapshot (`doctl`, from the Mac), tag
   `vayu-loadtest` (no Slack alerts; the script adds it to the firewall), address
   `vayu-loadtest.<ip>.sslip.io` (no DNS step; https works). Same version as staging, staging's
   settings from Phase, **Sentry off** (the test counts errors itself and keeps the server logs;
   the free Sentry quota stays for real errors).
2. **History**: 3 months of made-up data (≈18k bookings, ≈9k inspections, ≈1M file records,
   reports, webhook logs), plus one login per simulated person (up to 400 experts and 40 Ops).
   The generator refuses production, like `seed_test_data`.
3. **Load server**: a second throwaway in Bangalore (4 vCPU / 8 GB) runs the script and a webhook
   receiver (https, its own sslip.io name) that times every delivery. 15 integrations point at it.
   Uploads from a laptop would measure the office internet, not the server.
4. **Sign-in before the clock**: each simulated person signs in at the normal limit (20 a minute
   from one address; about 22 minutes at 8×), then the timed test starts. Phones refresh their
   tokens as the real app does. No setting on the test server differs from production.
5. **Simulated phones** make the app's exact server calls: sync, start, ask for upload links,
   send real-size files straight to R2, submit. The app's own behaviour (offline queue, retries)
   is proven by the real-phone checks in Phase 6, not here.
6. **Measured**: request times and errors (the load script); upload-check, PDF and webhook delays
   (database timestamps and the receiver); CPU, memory, swap and memory kills (the server).
7. **Clean-up**: every test booking deleted through the app (which deletes its files from the
   staging bucket); the script checks the bucket is back to its earlier size; both servers
   destroyed. The results table below is filled in; the deployment session records it in the
   setup log.

**Time and money.** Per server: ~45 min setup and history, 60 min test 1, up to 90 min test 2,
~10 min clean-up. About one working day in all, mostly unattended; results arrive after each
server. Cost about $1.50 (hourly droplets, the load server, a temporary managed database, a few
hours of test files in R2). **Cap: $5**; the script stops and asks before going over.

## 7. What gets built (not yet)

1. History generator (staging and test servers only).
2. Load script (`perf/`, replacing today's `locustfile.py`): phones, Ops (Today, bookings, search,
   Key Checks, 5 Regenerate per booking), the external API client, the step plan for test 2.
3. Webhook receiver with timing.
4. `perf/run.sh`: create the servers, deploy, fill history, sign in, run, measure, clean up,
   destroy, write the results.

## 8. Estimates (replaced by the measured numbers)

- **Server work per hour at 1×:** one upload check every ~3 s (about 4 Mbit/s of downloads into
  the server, which are free); PDFs are the heaviest: ~54 × ~20–25 s ≈ 20 minutes of one CPU core.
  API and webhooks are light. PDF memory has never been measured on a server: it decides whether
  2 GB is enough. Webhooks share a worker with upload checks; if they wait behind them, the fix is
  a separate webhook worker (a setting), not a bigger server.
- **R2:** 20 GB a day, kept 3 months ≈ 1.8 TB ≈ **$27/month** (requests stay in the free tier).
  Video is 75% of it; recording at 1.5 instead of 2.5 Mbit/s would save about $8/month (a separate
  decision).
- **Database:** about 6–8 GB in year 1 (answers ~2 GB, file records ~4 GB, webhook log ~0.5 GB,
  plus indexes); under 15 connections at 1×. The smallest managed database (10 GB disk) lasts
  about a year.
- **Prediction** (the tests decide): $12 probably copes on CPU at 1×; whether 2 GB holds a PDF
  render is unknown; PDFs are the likely first limit in test 2.

## 9. Results (fill in after the runs)

**Test 1: low-cost (1×, one hour)**

| Size | Database | API p95 | Upload check p95 | PDF p95 (100 / 150 photos) | Webhook p95 | Peak memory | Zero loss | Pass? |
|---|---|---|---|---|---|---|---|---|
| 1 vCPU / 2 GB | on server | | | | | | | |
| 2 vCPU / 2 GB | on server | | | | | | | |
| 2 vCPU / 4 GB | on server | | | | | | | |
| cheapest pass | managed | | | | | | | |

**Test 2: capacity (step where each target broke)**

| Size | All held up to | API | Upload check | PDF | Webhook | Memory | Stopped at (why) | PDF with 2 at a time |
|---|---|---|---|---|---|---|---|---|
| cheapest pass | | | | | | | | |
| 2 vCPU / 4 GB | | | | | | | | |

Decision: production size ____ , database ____ , monthly total (server + database + R2) ____ ,
upgrade when daily load passes ____ .
