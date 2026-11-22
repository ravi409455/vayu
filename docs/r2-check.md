# Manual check against the real Cloudflare R2 staging bucket

Automated tests use an in-memory S3 (moto). R2 is S3-compatible but not identical, so run this once
on staging (and before each release that touches media):

1. Set `S3_*` env vars to the **staging** bucket (see `.env.example`); CORS per `docs/accounts-setup.md`.
2. `POST /api/v1/media/initiate` for an 11 MB file with `MEDIA_PART_SIZE` 5 MB: expect 3 part URLs.
3. `curl -X PUT --data-binary @part1 "<part url>"` for each part; note each `ETag` response header.
4. `POST /api/v1/media/<id>/complete` with the parts: expect `status: verified`.
5. Kill the upload after part 1 and call `GET /api/v1/media/<id>`: expect `uploaded_parts` = [1].
6. Open the `url` from `/media/<id>/url`: the file downloads; open the ZIP link from `/media-zip`.
7. From a browser on `staging.carcid.in` do one PUT to a part URL: it must not fail on CORS and the
   `ETag` header must be readable.
Record the result in `docs/benchmarks.md`.
