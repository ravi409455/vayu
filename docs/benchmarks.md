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

## 2. Load
Replaced by the load tests in `docs/plan-load-test.md` (the owner's real day: phones, Ops, the
external system, uploads, PDFs, webhooks): `perf/local/run.sh` on the Mac, `perf/cloud.sh` on
throwaway servers. Results go there (§9).

## 3. Real Cloudflare R2
Done 2026-11-23 on `vayu-staging`: the whole media + PDF test suite (122 tests) passes against the
real bucket (see `docs/r2-check.md`). Still to do: the browser CORS check on the real domains.
