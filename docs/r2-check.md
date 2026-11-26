# Manual check against the real Cloudflare R2 staging bucket

Automated tests use an in-memory S3 (moto). R2 is S3-compatible but not identical, so run this once
on staging (and before each release that touches media):

1. Set `S3_*` env vars to the **staging** bucket (see `.env.example`); CORS per `docs/accounts-setup.md`.
2. `POST /api/v1/media/initiate` for an 11 MB file with `MEDIA_PART_SIZE` 5 MB: expect 3 part URLs.
3. `curl -X PUT --data-binary @part1 "<part url>"` for each part; note each `ETag` response header.
4. `POST /api/v1/media/<id>/complete` with the parts: expect `status: uploaded`; the check runs in the
   background, so `GET /api/v1/media/<id>` turns `verified` a few seconds later (with the workers on).
5. Kill the upload after part 1 and call `GET /api/v1/media/<id>`: expect `uploaded_parts` = [1].
6. Open the `url` from `/media/<id>/url`: the file downloads; open the ZIP link from `/media-zip`.
7. From a browser on `staging.carcid.in` do one PUT to a part URL: it must not fail on CORS and the
   `ETag` header must be readable.
Record the result in `docs/benchmarks.md`.

## Running the whole media + PDF test suite against a real bucket

The tests use an in-memory S3 by default. To run them against a real bucket (use **staging**, never
prod; the tests leave objects behind, so empty the bucket afterwards):

```bash
set -a; . backend/.env.local; set +a
S3_BUCKET=vayu-staging S3_ENDPOINT_URL=$R2_ENDPOINT_URL S3_ACCESS_KEY_ID=$R2_ACCESS_KEY_ID \
S3_SECRET_ACCESS_KEY=$R2_SECRET_ACCESS_KEY S3_REGION=auto VAYU_REAL_S3=1 \
  uv run --directory backend pytest -q apps/media apps/reports
```

Result 2026-11-23 on `vayu-staging`: 122 passed (it found that R2 upload ids are ~343 characters,
longer than the old 300-character column; fixed).
