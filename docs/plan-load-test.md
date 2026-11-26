# Plan: realistic load test and server sizing

Agreed with the owner on 2026-11-27. Goal: find the **cheapest server that handles today's real
load**, with numbers, before production is created. It replaces the old "200 users for 10 minutes"
check (deploy plan, Phase 6 check 7). Runs on staging (on demand), not built yet.

## 1. The load (the owner's numbers, no multiplier)

| What | Per day (7 days a week) | In the test hour |
|---|---|---|
| Users | 50 experts (phones), 5 Ops (web) | all 55 active |
| New bookings | 200 | 18 |
| Inspections finished | 100, spread evenly 9 am–8 pm | 9 |
| Files per inspection | 100 photos (~500 KB, shrunk on the phone) + 15 videos (30 s, 720p at 2.5 Mbit/s ≈ 10 MB) ≈ **200 MB** | ~1,035 files, ~1.8 GB |
| PDFs | 6 per booking: 1 automatic + 5 Regenerate (changes only mark a PDF out of date; Ops press Regenerate) | 54 |
| Outgoing webhooks | exactly 15 per booking over its life | 270 |
| External system (REST API) | peaks of 100 calls/min | 100/min the whole hour: ~200 writes (18 creates + changes), the rest reads |

The test hour is the even daily rate, with the external API held at its peak. **Known limit:** a
day busier than this is not proven; the server alerts (deploy plan 5.5) would show it.

## 2. Pass

| Check | Target (95 of 100 must meet it) |
|---|---|
| Web and API answers | ≤ 0.5 s; under 1% errors |
| Upload checked (fingerprint, previews) | ≤ 5 min after upload |
| PDF ready after submit or Regenerate | ≤ 30 s |
| Webhook delivered after its event | ≤ 5 s |
| Server | no process killed for memory; swap barely used; CPU not pinned at 100% |

Every run also reports the real numbers (for example "PDF typically 22 s, worst 41 s").

## 3. The runs

| Run | Droplet | Database |
|---|---|---|
| A | 1 vCPU / 2 GB ($12) | Postgres on the same server |
| B | 2 vCPU / 2 GB ($18) | Postgres on the same server |
| C (baseline) | 2 vCPU / 4 GB ($24) | Postgres on the same server |
| D (one check) | the smallest size that passed | a temporary managed Postgres (1 GB, about $0.50 for the day): connections and speed |

- Staging is created at each size (`infra/staging.sh up`), with worker counts set for that size.
- **Data first:** about 3 months of history (≈18k bookings, ≈9k inspections, ≈1M file records),
  because an empty database is fast and a full one is the truth.
- **Load from a temporary droplet in Bangalore** (cents for the run), not a laptop: 1.8 GB of
  uploads an hour would test the office connection, not the server.
- Uploads are real-size files into the `vayu-staging` bucket; they are deleted after the runs.
- The database question: if the smallest passing size also passes with Postgres on the box,
  capacity is no reason to pay for managed; the choice is then safety (restore to any minute vs a
  nightly copy) and is the owner's.

## 4. What gets built (not yet)

1. **History generator** (staging only, refuses production like `seed_test_data`): 3 months of
   bookings, inspections, file records, reports and webhook logs, written in bulk.
2. **Load script** (`perf/`, extends `locustfile.py`): 50 phones (sync, start, upload real-size
   files through the pre-signed URLs, submit), 5 Ops (Today, bookings, search, Key Checks, 5
   Regenerate per booking), the external API client (API key; 100 calls/min, ~200 writes/hour).
3. **Webhook receiver** on the load droplet: 15 integrations point at it; it records the delay
   from event to arrival.
4. **Measurement:** upload-check and PDF delays from the database timestamps; CPU, memory, swap
   and OOM kills from the server; one results table per run.

## 5. Estimates (to be replaced by the measured numbers)

- **Server work per hour:** one upload check every ~3 s (about 4 Mbit/s of downloads into the
  server, which are free); PDFs are the heaviest: ~54 × ~25 s ≈ 23 minutes of one CPU core.
  API and webhooks are light. PDF memory has never been measured on a server: it decides whether
  2 GB is enough. Webhooks share a worker with upload checks; if they wait behind them, the fix is
  a separate webhook worker (a setting), not a bigger server.
- **R2:** 20 GB a day, kept 3 months ≈ 1.8 TB ≈ **$27/month** (requests stay in the free tier).
  Video is 75% of it; recording at 1.5 instead of 2.5 Mbit/s would save about $8/month (a separate
  decision).
- **Database:** about 6–8 GB in year 1 (answers ~2 GB, file records ~4 GB, webhook log ~0.5 GB,
  plus indexes); under 15 connections. The smallest managed database (10 GB disk) lasts about a year.
- **Prediction** (the test decides): $12 probably copes on CPU; whether 2 GB holds a PDF render is
  unknown.

## 6. Result (fill in after the runs)

| Run | Size | API p95 | Upload check p95 | PDF p95 | Webhook p95 | Peak memory | Pass? |
|---|---|---|---|---|---|---|---|
| A | 1 vCPU / 2 GB | | | | | | |
| B | 2 vCPU / 2 GB | | | | | | |
| C | 2 vCPU / 4 GB | | | | | | |
| D | smallest pass + managed DB | | | | | | |

Decision: production size ____ , database ____ , monthly total (server + database + R2) ____ .
