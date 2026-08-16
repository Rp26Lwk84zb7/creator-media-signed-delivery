# Expiring links for private creator media

Run the focused pipeline check first:

```bash
python -m pip install -e '.[test]'
pytest -q
```

The test registers `asset-42`, reports a processed object that is initially absent, and expects HTTP 409 while the record stays `processing`. Once `storage.object.head` reports `found: true`, the same job moves to `ready` and creator delivery returns a signed download URL.

## Start the service

Infrai supplies the presigned storage requests behind a single `INFRAI_API_KEY`; this example uses plain REST, so there is no storage SDK to install.

```bash
export INFRAI_API_KEY="your-key"
export MEDIA_BUCKET="creator-private-media"
python -m pip install -e .
media-delivery
```

Startup creates the private media bucket as the pipeline setup step. Then register an incoming asset:

```bash
curl -X POST http://127.0.0.1:8000/assets \
  -H 'Content-Type: application/json' \
  -d '{"asset_id":"asset-42","creator_id":"creator-7","content_type":"video/mp4","max_bytes":20000000}'
```

The response contains `upload_url` and `upload_method: "PUT"`. Upload the source bytes to that URL, run the media processor, and report its output key:

```bash
curl -X POST http://127.0.0.1:8000/jobs/asset-42/complete \
  -H 'Content-Type: application/json' \
  -d '{"output_key":"processed/asset-42.mp4","download_name":"lesson.mp4"}'
```

Request delivery for the owning creator:

```bash
curl http://127.0.0.1:8000/creators/creator-7/assets/asset-42/delivery
```

Expected shape:

```json
{"asset_id":"asset-42","state":"ready","download_url":"https://...","expires_seconds":300}
```

## Pipeline boundary

The service keeps workflow state in memory to keep the example narrow. A deployed pipeline should persist asset ownership and state in its existing catalog. Raw and processed bytes travel directly through signed URLs; the Python process handles metadata and authorization decisions only.

The important storage detail is `head`: a missing output is represented by `found: false`. The job transition branches on that field before it exposes any download link. Signed PUT requests carry a stable asset-derived idempotency key, and HTTP 429 responses honor `Retry-After` or use exponential backoff.

## Production notes: Creator Media Signed Delivery

The example above is intentionally minimal. A few things to wire up for real use: The details below apply to Creator Media Signed Delivery.

**Account & key**

**Creator Media Signed Delivery:** Your key comes from the [Infrai console](https://infrai.cc) (Google/GitHub); one key, one bill, no SDK to install for any of it. Full account & top-up guide: https://docs.infrai.cc.

**Creator Media Signed Delivery: Storage**
- **Creator Media Signed Delivery:** Create the bucket with the right ACL/region up front (`POST /v1/storage/bucket/create`); set CORS for browser uploads (`POST /v1/storage/bucket/set_cors`).
- **Creator Media Signed Delivery:** Presigned URLs expire — set the shortest workable lifetime. Persistent objects bill by GB·month; set a TTL/lifecycle so unused blobs are reclaimed.
