# Benchmarks

Both are **manual runs on staging** (never in CI): they need the real server, database and bucket.

## 1. PDF with 150 photos (target: at most 2 minutes)
```bash
cd backend && uv run python manage.py bench_pdf --photos 150
```
Creates a temporary booking and 150 photos, renders the report the way the worker does, prints the
time, and removes everything again.

| When | Where | Result |
|---|---|---|
| 2026-11-23 | developer laptop (Apple silicon), in-memory S3 | **150 photos → 1.7 MB PDF in 16.3 s** |
| _to do_ | staging (the real 6 GB `pdf` worker) | |

## 2. Load: 200 mixed users (target: p95 under 500 ms)
```bash
export LOAD_OPS_USER=... LOAD_OPS_PASSWORD=... LOAD_EXPERT_USER=... LOAD_EXPERT_PASSWORD=...
uvx locust -f perf/locustfile.py --host https://staging.carcid.in --users 200 --spawn-rate 10 --run-time 10m --headless
```
25 Ops users (board, search, booking, dashboards) and 175 experts (job list, one job). Use two
throw-away accounts on staging; the passwords stay in your shell, never in the repo.

| When | Where | p95 | Notes |
|---|---|---|---|
| _to do_ | staging | | |

## 3. Real Cloudflare R2
Done 2026-11-23 on `vayu-staging`: the whole media + PDF test suite (122 tests) passes against the
real bucket (see `docs/r2-check.md`). Still to do: the browser CORS check on the real domains.
