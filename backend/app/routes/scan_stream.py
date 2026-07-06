"""
POST /scan/stream — progressive scan via Server-Sent Events.

Detect+Read makes 2-4 parallel crop-read LLM calls per scan; each completed
chunk is a natural streaming boundary. First badges reach the client as soon
as detection + the fastest chunk finish (~6-8s) instead of after the slowest
chunk + rescue pass (~12-18s).

Events:
  - `partial` (0+ times): complete ScanResponse JSON with the wines read so
    far. Cumulative replacement — the client swaps its entire state.
  - `done` (exactly once on success): the final complete ScanResponse,
    identical to what POST /scan would have returned.
  - `error` (terminal, on pipeline failure): {"message": str}. Clients
    should keep any partial results they already rendered, or fall back to
    POST /scan if nothing arrived.

Only PIPELINE_MODE=detect_read supports streaming; other modes return 501 so
clients fall back to POST /scan. POST /scan itself is unchanged (iOS uses it).
"""

import json
import logging
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from ..config import Config
from ..feature_flags import FeatureFlags, get_feature_flags
from ..models import ScanQuality, ScanResponse
from ..services.abuse_protection import enforce_abuse_protection, record_scan_spend
from ..services.detect_read_pipeline import DetectReadPipeline
from ..services.wine_matcher import WineMatcher
from .scan import (
    build_results_from_recognized,
    convert_heic_to_jpeg,
    get_wine_matcher,
    is_valid_image_content_type,
    map_pipeline_error,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@router.post("/scan/stream")
async def scan_shelf_stream(
    image: UploadFile = File(..., description="Wine shelf image"),
    wine_matcher: WineMatcher = Depends(get_wine_matcher),
    flags: FeatureFlags = Depends(get_feature_flags),
    device_key: str = Depends(enforce_abuse_protection),
) -> StreamingResponse:
    """Progressive scan: stream partial results as crop-read chunks complete."""
    if Config.pipeline_mode() != "detect_read":
        raise HTTPException(
            status_code=501,
            detail="Streaming scan requires PIPELINE_MODE=detect_read; use POST /scan.",
        )

    if not is_valid_image_content_type(image.content_type):
        raise HTTPException(
            status_code=400,
            detail="Invalid image type. Supported formats: JPEG, PNG, HEIC, WebP."
        )

    try:
        image_bytes = await image.read()
    except IOError as e:
        logger.error(f"Failed to read uploaded image: {e}")
        raise HTTPException(status_code=400, detail="Failed to read image file")

    image_bytes = convert_heic_to_jpeg(image_bytes, image.content_type)

    if len(image_bytes) > Config.MAX_IMAGE_SIZE_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"Image too large. Maximum size is {Config.MAX_IMAGE_SIZE_MB}MB."
        )

    image_id = str(uuid.uuid4())

    async def event_stream():
        try:
            pipeline = DetectReadPipeline(wine_matcher=wine_matcher)
            async for result in pipeline.scan_stream(image_bytes, image_id=image_id):
                # Partial snapshots skip enrichment/DB-sync (fast, repeated);
                # the final one gets the full POST /scan treatment.
                results, fallback = build_results_from_recognized(
                    result.recognized_wines,
                    wine_matcher,
                    flags=flags,
                    skip_enrichment=result.partial,
                )
                response = ScanResponse(
                    image_id=image_id,
                    results=results,
                    fallback_list=fallback,
                    scan_quality=(ScanQuality(**result.scan_quality)
                                  if result.scan_quality else None),
                )
                event = "partial" if result.partial else "done"
                yield _sse(event, response.model_dump(mode="json"))
                if not result.partial:
                    record_scan_spend(result.timings.get("cost_usd"))
                    logger.info(
                        f"[{image_id}] /scan/stream done: {len(results)} results "
                        f"(model={result.timings.get('model')}, "
                        f"cost=${result.timings.get('cost_usd')}, "
                        f"{result.timings.get('notes')})"
                    )
        except Exception as e:
            # Already streaming — status is committed, so signal in-band.
            mapped = map_pipeline_error(e)
            if mapped:
                logger.warning(f"[{image_id}] /scan/stream pipeline failure: {e}")
            else:
                logger.error(f"[{image_id}] /scan/stream failed: {e}", exc_info=True)
            yield _sse("error", {
                "message": mapped[1] if mapped else "Scan failed. Please try again.",
            })

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # Disable proxy buffering so partials actually reach the client.
            "X-Accel-Buffering": "no",
        },
    )
