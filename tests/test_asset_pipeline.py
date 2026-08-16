from typing import Any

import pytest
from fastapi import HTTPException

from media_delivery import AssetIngestRequest, AssetPipeline, ProcessingResult


class RecordingStorage:
    def __init__(self) -> None:
        self.output_found = False
        self.get_requests: list[tuple[str, str, str]] = []

    def presign_put(
        self, bucket: str, key: str, content_type: str, max_bytes: int, request_id: str
    ) -> dict[str, Any]:
        return {"url": "https://signed.example/upload"}

    def head_object(self, bucket: str, key: str) -> dict[str, Any]:
        return {"found": self.output_found}

    def presign_get(self, bucket: str, key: str, filename: str) -> dict[str, Any]:
        self.get_requests.append((bucket, key, filename))
        return {"url": "https://signed.example/download"}


def test_delivery_waits_for_processed_object_and_checks_creator() -> None:
    storage = RecordingStorage()
    pipeline = AssetPipeline(storage, bucket="test-media")  # type: ignore[arg-type]
    pipeline.ingest(
        AssetIngestRequest(
            asset_id="asset-42",
            creator_id="creator-7",
            content_type="video/mp4",
            max_bytes=20_000_000,
        )
    )
    result = ProcessingResult(output_key="processed/asset-42.mp4", download_name="lesson.mp4")

    with pytest.raises(HTTPException, match="Processed media is not ready") as pending:
        pipeline.complete_processing("asset-42", result)
    assert pending.value.status_code == 409
    assert pipeline.assets["asset-42"].state == "processing"

    storage.output_found = True
    pipeline.complete_processing("asset-42", result)
    delivery = pipeline.delivery("asset-42", "creator-7")

    assert delivery.download_url == "https://signed.example/download"
    assert storage.get_requests == [("test-media", "processed/asset-42.mp4", "lesson.mp4")]

