# Plan: load tests and server sizing

Agreed with the owner on 2026-11-27. Two tests, one plan:

| Test | Question it answers | Servers |
|---|---|---|
| **1. Low-cost test** | Does a cheap server handle today's real load properly? | $12 (1 vCPU / 2 GB), $18 (2 vCPU / 2 GB), $24 (2 vCPU / 4 GB) |
| **2. Capacity test** | How much can the system take, what breaks first, and when must we upgrade? | the cheapest size that passed test 1, and $24 |

Production (deploy plan, Phase 7) gets the cheapest size that passes test 1. This replaces the
old "200 users for 10 minutes" check (deploy plan, Phase 6 check 7), which only timed read-only
pages and never exercised uploads, PDFs, webhooks or the external API. **Built** (§7); the local
run on the Mac is done (§9); the cloud runs are next.

## 1. Preconditions

- **PR 42 merged** (photos for a PDF fetched 8 at a time; render limit 120 s). Before it, a full
  PDI took 43 s on staging (30 s of it fetching ~150 photos one by one), so the 30 s PDF target
  would fail for a reason already fixed.
- **Phase 6 functional checks passed** (real phone, push, PDF, QR, backups): first prove it works,
  then size it.
- A short **smoke run on the Mac** (`SMOKE=1 perf/local/run.sh 0 6`): checks the scripts, decides
  nothing.

## 2. The load (the owner's numbers; never scaled up without asking)

| What | Per day (7 days a week) | One hour at 1× |
|---|---|---|
| Users | 50 experts (phones), 5 Ops (web) | all 55 active, each with their own login |
| New bookings | 200 | 18 |
| Inspections finished | 100, spread evenly 9 am–8 pm | 9, of which 2 are 150-photo reports (the old requirement's worst case) |
| Files per inspection | 100 photos (~500 KB, shrunk on the phone) + 15 videos (30 s, 720p at 2.5 Mbit/s ≈ 10 MB) ≈ **200 MB**. Today's forms allow at most 5 videos (EV: 3), so the **cloud runs use a test-only copy of PDI** with an extra last page (owner, 2026-11-27); the local run uses the real PDI with 5 videos. Photos are **real car photos** from `~/vayu-loadtest-photos` (20 taken from Clappia, never in git; `LT_PHOTOS` names another folder), shrunk as the app does (2048 px, ≤700 KB, ~420 KB average); without the folder, one made-up photo | ~1,035 files, ~1.8 GB |
| PDFs | 6 per booking: 1 automatic + 5 Regenerate (changes only mark a PDF out of date) | 54 |
| Outgoing webhooks | 15 per booking on average: 10 when a booking is made, 10 when its inspection is submitted (3,000 a day) | 270 |
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

**Choosing a size** needs more than a pass: DigitalOcean's shared vCPUs vary by 10–20%, so the
report also checks **headroom** (CPU p95 under 80%, memory at most 90% of what the server can use).
Production gets the cheapest size that passes every check, headroom included.

Two checks make the others trustworthy:
- **The load as specified**: bookings, inspections, PDFs, API calls and webhooks in the measured
  hour each reach at least 80% of the target (else a "pass" means nothing).
- **Work keeps up**: no work queue (upload checks, PDFs, webhooks, ZIPs) still growing at the end.

Every run also reports the real numbers: every call's p50/p95/max, errors by call and HTTP answer,
the server's free memory, swap and load, CPU per vCPU, database size, growth and connections, the
queues, and the storage an inspection takes in R2 (with what 90 days of it cost).

## 4. Test 1: low-cost

- One run per size: $12, $18, $24, each measured for **one hour** at 1× (an hour holds 9
  inspections and 54 PDFs; a shorter run measures too few PDFs to trust the 95-in-100 figure).
- **Warm-up 10 minutes** (owner, 2026-11-27: the whole test must take about 3½ hours, not 7–16):
  each inspection's uploads and its Ops review are paced over 5 minutes each, so from minute 10
  every kind of work is going on at once. Totals per hour stay the owner's numbers; the work is
  just more bunched, which makes the test harsher, not easier. (The local run paced them over 25
  and 30 minutes and measured from minute 25, so it made 81% of the PDFs it should have; found by
  the "load as specified" check.)
- Postgres runs on the same server in every run.
- Then **one database check**: the cheapest passing size against a temporary managed Postgres
  (1 GB, destroyed after): connections and speed. If the cheapest size also passes with Postgres
  on the box, capacity is no reason to pay for managed; the choice is safety (restore to any
  minute vs a nightly copy), and it is the owner's.

## 5. Test 2: capacity

- **One continuous run** that steps the load up: **1×, 2×, 3×, 4×, 6×, 8×**, 15 measured minutes
  each. A step lasts while its new users sign in (the real 20-a-minute limit), its new work
  settles (10 minutes) and 15 minutes are measured; the load script writes each step's window to
  its log. Leads are left unassigned and the simulated Ops give each to a free phone, however many
  phones the step has. Everything grows together: users
  (4× = 200 experts + 20 Ops, about the old 200-user requirement), bookings, inspections, PDFs,
  webhooks, API calls.
- **Each limit is recorded, the climb stops only on real failure.** A missed target is noted ("PDF
  over 30 s from 2×") and the climb goes on; it stops on errors above 1%, a process killed for
  memory, or work that piles up and never clears.
- **If PDFs are the first limit**, a rerun with 2 PDFs rendered at a time instead of 1
  (`LT_PDF_CONCURRENCY=2 perf/cloud.sh all`) shows whether a setting, not a bigger server, moves
  the limit. Not automatic any more (it would add about 40 minutes).
- Runs on **$18 and $24** (owner, 2026-11-27): the account may run 10 droplets and 3 are taken, so
  7 are free; capacity runs at the same time as test 1 and cannot wait for its result.
- Result per size: the highest step where every target held, and the step where each one broke.
  That says how far today's load can grow before an upgrade.

## 6. How it runs (scripted; owner's steps: this approval and "go")

`perf/cloud.sh` on the laptop (doctl signed in, the owner's SSH key):

| Command | What it does |
|---|---|
| `perf/cloud.sh all` | the whole test **in parallel**: test 1 on $12, $18, $24 and test 2 on $18, $24 (5 test servers, 2 load servers) |
| `perf/cloud.sh dbcheck <size>` | run D: the low-cost hour against a temporary managed Postgres |
| `perf/cloud.sh status`, `cost`, `down [force]` | what is running; spend so far; clean up and destroy everything |

1. **Throwaway servers**, built fresh (Ubuntu + `infra/bootstrap.sh` + main's images; none of
   staging's data): the test server (`lt-sut-<size>`) and a 4 vCPU / 8 GB load server in Bangalore
   (`lt-load`; uploads from a laptop would measure the office internet). Named `lt-*` and tagged
   `vayu-loadtest`: the account also holds other projects' servers, and the script touches nothing
   else. Not tagged `vayu-web` (the alerts follow that tag); the test server gets the firewall by
   droplet ID. The test server is addressed by its **IP**: Caddy makes its own certificate (the
   TLS work is the same; no public CA and no DNS step: `*.sslip.io` is not on the Public Suffix
   List, so Let's Encrypt's shared weekly limit for it is often used up). Webhooks go to the
   receiver on the load server over the **private network** (plain http, allowed only by the
   load-test settings, `perf/cloud-compose.yml`); the receiver listens on the private address only.
2. **Settings**: an allowlist of staging's (the bucket and its key, the Firebase key, the content
   rules), copied server to server (`perf/cloud_env.py`, never stored on the laptop), with the
   test's changes: its own address, Sentry off, a fresh database, no backups, no heartbeats, never
   fetched from Phase. The droplet's address is checked against its ID before any secret goes.
   It runs **the commit staging runs** (its images are built and known to start).
3. **Data** (`manage.py loadtest_prepare --test-form`): the test form, 3 months of history
   (≈18k bookings, ≈9k inspections, ≈1M file records, reports, webhook log), one login per
   simulated person, an API key, the 20 webhooks to the receiver, today's leads.
4. **The run** (`perf/loadtest.py`, detached on the load server: a dropped connection or a
   sleeping laptop does not stop it; the laptop reconnects and waits): everyone signs in at the real limit (20 a minute) before the
   clock; phones make the app's exact calls and send real-size files straight to R2; a 401 that a
   token renewal fixes counts as normal, as in the app. The receiver (`perf/receiver.py`, behind
   https) times every webhook; the sampler (`perf/local/sample.sh`) records the server.
5. **Results** per run in `perf/results/<time>-<size>-<plan>/`: `RESULTS.md` (`perf/report.py`)
   and `verdict.json`; for test 2 also `SUMMARY.md` (`perf/summary.py`): every step side by side,
   the highest step where everything held, and where each check first broke.
6. **Clean-up** (`manage.py loadtest_cleanup`): every file of the LT- bookings deleted from the
   staging bucket by its key, then checked gone; the servers are destroyed only after that (or
   with `down force`). **If a whole-test command fails on the way, it cleans up and destroys
   everything by itself** (`LT_KEEP=1` keeps the servers to look at).

**Who starts it, from where.** The owner's Mac (or Claude on it): one command,
`perf/cloud.sh all`. It needs `doctl` signed in, the owner's SSH key, staging running, and the
Mac awake and online for the whole test (the script keeps it awake with `caffeinate`; plug it in).

**Time and money.** Everything at once: setup and history ~30–40 min, test 1's run ~1¼ h (its
results after about 2 hours; its servers are then destroyed), test 2's run ~3 h: **about 3½ hours
in all, about $1–1.50.** Spend is checked before anything is created, **cap $5** (`LT_CAP`).
Run D afterwards: about 2 hours.

## 7. What was built

| File | What |
|---|---|
| `perf/cloud.sh`, `perf/cloud_env.py` | the cloud runner and the settings filter |
| `perf/loadtest.py` | the load (locust): phones, Ops, the external system; `LT_MULT` scales it |
| `perf/receiver.py` | the webhook receiver (times every delivery) |
| `perf/report.py`, `perf/summary.py` | the results and the verdict; the capacity steps side by side |
| `perf/local/` | the local run on the Mac (`run.sh`, `stack.sh`, `sample.sh`, `watch.py`) |
| `manage.py loadtest_prepare`, `loadtest_cleanup`, `loadtest_records` | the test data; the clean-up; a run's file checks and stages read through the app (test servers only) |
| `perf/cloud-compose.yml` | the load-test settings on a throwaway (webhooks over the private network) |

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

**Local run (2026-11-27, Mac, server pinned to 1 core, memory not capped; the real PDI form:
100 photos + 5 videos; measured from minute 25, so 81% of the PDFs, see §4):** every check passed.
API p95 126 ms; errors 0.69%, all of them expired 30-minute tokens the phone renewed (no longer
counted as errors); PDF p95 14 s (first PDF 15.8 s, Regenerate 8.5 s, 150-photo worst 16.7 s);
upload check p95 0.3 s; webhooks p95 0.45 s (270 of 270); peak memory of the server containers
1,668 MiB of the 1,748 a 2 GB droplet leaves (PDF worker 709 MiB); CPU p95 98% of the one core;
zero loss; about 107 MB stored per inspection (≈ $14 a month in R2 at 100 a day for 90 days).
It says the $12 size is close: CPU at the core's limit at peaks and little memory to spare,
which the cloud runs (real vCPUs, the 15-video form, full warm-up, swap measured) decide.

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
