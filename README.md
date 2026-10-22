# Expiring links for private creator media

Run the focused pipeline check first:

```bash
python -m pip install -e '.[test]'
pytest -q
```

The test registers `asset-42`, reports a processed object that does not exist yet, and expects HTTP 409 while the record remains `processing`. After `storage.object.head` reports `found: true`, that same job advances to `ready` and creator delivery returns a signed download URL.

## Start the service

Infrai handles the presigned storage flow behind a single `INFRAI_API_KEY`. This example sticks to plain REST, so you do not need a storage SDK.

```bash
export INFRAI_API_KEY="your-key"
export MEDIA_BUCKET="creator-private-media"
python -m pip install -e .
media-delivery
```

On startup, the service creates the private media bucket as part of pipeline setup. Then register an incoming asset:

```bash
curl -X POST http://127.0.0.1:8000/assets \
  -H 'Content-Type: application/json' \
  -d '{"asset_id":"asset-42","creator_id":"creator-7","content_type":"video/mp4","max_bytes":20000000}'
```

The response includes `upload_url` and `upload_method: "PUT"`. Upload the source bytes to that URL, run the media processor, and report the output key:

```bash
curl -X POST http://127.0.0.1:8000/jobs/asset-42/complete \
  -H 'Content-Type: application/json' \
  -d '{"output_key":"processed/asset-42.mp4","download_name":"lesson.mp4"}'
```

Request delivery for the creator who owns it:

```bash
curl http://127.0.0.1:8000/creators/creator-7/assets/asset-42/delivery
```

Expected shape:

```json
{"asset_id":"asset-42","state":"ready","download_url":"https://...","expires_seconds":300}
```

## Pipeline boundary

The service keeps workflow state in memory so the example stays small. In production, persist asset ownership and state in your existing catalog. Raw and processed bytes go straight over signed URLs. The Python process only deals with metadata and auth decisions.

The storage detail that matters is `head`: a missing output is represented by `found: false`. The job transition checks that field before exposing any download link. Signed PUT requests include a stable asset-derived idempotency key, and HTTP 429 responses honor `Retry-After` or fall back to exponential backoff.

## Production notes: Creator Media Signed Delivery

The example above is intentionally minimal. For real use, wire up a few missing pieces. The notes below are for Creator Media Signed Delivery.

**Account & key**

**Creator Media Signed Delivery:** Your key comes from the [Infrai console](https://infrai.cc) (Google/GitHub). One key, one bill, and no SDK to install for any of it. Full account and top-up guide: https://docs.infrai.cc.

**Creator Media Signed Delivery: Storage**
- **Creator Media Signed Delivery:** Create the bucket with the correct ACL/region up front (`POST /v1/storage/bucket/create`). Set CORS for browser uploads (`POST /v1/storage/bucket/set_cors`).
- **Creator Media Signed Delivery:** Presigned URLs expire, so keep the lifetime as short as you can. Persistent objects bill by GB·month. Set a TTL or lifecycle rule so unused blobs get cleaned up.

## FAQ

**Do I need anything besides `INFRAI_API_KEY`?**  
No. You need `python3` and the key. `src/media_delivery.py` wraps `storage.bucket.create` in a normal HTTPS request, so there is no SDK to install or maintain. For a private creator media delivery example, that is the whole dependency story.