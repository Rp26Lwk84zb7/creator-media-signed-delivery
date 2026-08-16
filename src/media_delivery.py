from __future__ import annotations

import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from collections.abc import AsyncIterator
from typing import Literal

import uvicorn
from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field

from signed_download import InfraiError, InfraiStorage


BUCKET = os.getenv("MEDIA_BUCKET", "creator-private-media")


class AssetIngestRequest(BaseModel):
    asset_id: str = Field(min_length=1, pattern=r"^[a-zA-Z0-9_-]+$")
    creator_id: str = Field(min_length=1)
    content_type: str = Field(min_length=1)
    max_bytes: int = Field(gt=0, le=5_000_000_000)


class AssetIngestResponse(BaseModel):
    asset_id: str
    state: Literal["awaiting_upload"]
    upload_url: str
    upload_method: Literal["PUT"] = "PUT"


class ProcessingResult(BaseModel):
    output_key: str = Field(min_length=1)
    download_name: str = Field(min_length=1)


class DeliveryResponse(BaseModel):
    asset_id: str
    state: Literal["ready"]
    download_url: str
    expires_seconds: int = 300


@dataclass
class AssetRecord:
    creator_id: str
    state: Literal["awaiting_upload", "processing", "ready"]
    output_key: str | None = None
    download_name: str | None = None


class AssetPipeline:
    def __init__(self, storage: InfraiStorage, bucket: str = BUCKET) -> None:
        self.storage = storage
        self.bucket = bucket
        self.assets: dict[str, AssetRecord] = {}

    def ingest(self, request: AssetIngestRequest) -> AssetIngestResponse:
        key = f"incoming/{request.creator_id}/{request.asset_id}"
        signed = self.storage.presign_put(
            self.bucket,
            key,
            request.content_type,
            request.max_bytes,
            f"asset-ingest-{request.asset_id}",
        )
        self.assets[request.asset_id] = AssetRecord(request.creator_id, "awaiting_upload")
        return AssetIngestResponse(
            asset_id=request.asset_id, state="awaiting_upload", upload_url=signed["url"]
        )

    def complete_processing(self, asset_id: str, result: ProcessingResult) -> AssetRecord:
        record = self._asset(asset_id)
        record.state = "processing"
        head = self.storage.head_object(self.bucket, result.output_key)
        if not head.get("found", False):
            raise HTTPException(status_code=409, detail="Processed media is not ready")
        record.state = "ready"
        record.output_key = result.output_key
        record.download_name = result.download_name
        return record

    def delivery(self, asset_id: str, creator_id: str) -> DeliveryResponse:
        record = self._asset(asset_id)
        if record.creator_id != creator_id:
            raise HTTPException(status_code=404, detail="Asset not found")
        if record.state != "ready" or not record.output_key or not record.download_name:
            raise HTTPException(status_code=409, detail="Asset is not ready")
        signed = self.storage.presign_get(self.bucket, record.output_key, record.download_name)
        return DeliveryResponse(asset_id=asset_id, state="ready", download_url=signed["url"])

    def _asset(self, asset_id: str) -> AssetRecord:
        record = self.assets.get(asset_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Asset not found")
        return record


storage = InfraiStorage()
pipeline = AssetPipeline(storage)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    storage.create_bucket(BUCKET)
    yield


app = FastAPI(title="Private creator media delivery", lifespan=lifespan)


def get_pipeline() -> AssetPipeline:
    return pipeline


@app.post("/assets", response_model=AssetIngestResponse, status_code=201)
def ingest_asset(
    request: AssetIngestRequest, service: AssetPipeline = Depends(get_pipeline)
) -> AssetIngestResponse:
    try:
        return service.ingest(request)
    except InfraiError as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from error


@app.post("/jobs/{asset_id}/complete", status_code=204)
def complete_job(
    asset_id: str,
    result: ProcessingResult,
    service: AssetPipeline = Depends(get_pipeline),
) -> None:
    try:
        service.complete_processing(asset_id, result)
    except InfraiError as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from error


@app.get("/creators/{creator_id}/assets/{asset_id}/delivery", response_model=DeliveryResponse)
def creator_delivery(
    creator_id: str, asset_id: str, service: AssetPipeline = Depends(get_pipeline)
) -> DeliveryResponse:
    try:
        return service.delivery(asset_id, creator_id)
    except InfraiError as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from error


def run() -> None:
    uvicorn.run("media_delivery:app", host="127.0.0.1", port=8000)


if __name__ == "__main__":
    run()
