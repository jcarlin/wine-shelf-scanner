"""
SSE streaming scan endpoint for progressive wine recognition.

Streams results in two phases:
- phase1: Vision API + DB matching (turbo-quality, ~3.5s)
- phase2: Gemini-enhanced full results (~6-8s)
- done: stream complete

Both phase1 and phase2 emit complete ScanResponse JSON.
Phase2 is a full replacement — the frontend swaps its entire state.
"""

import io
import json
import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from PIL import Image
from pillow_heif import register_heif_opener

from ..config import Config
from ..feature_flags import FeatureFlags, get_feature_flags
from ..models import DebugData, DebugPipelineStep, ScanResponse
from ..services.flash_names_pipeline import FlashNamesPipeline
from ..services.wine_matcher import WineMatcher
from .scan import build_results_from_recognized, convert_heic_to_jpeg, get_wine_matcher

logger = logging.getLogger(__name__)
router = APIRouter()

# Ensure HEIF opener is registered
register_heif_opener()


@router.post("/scan/stream")
async def scan_stream(
    image: UploadFile = File(..., description="Wine shelf image"),
    debug: bool = Query(default=None, description="Include pipeline debug info"),
    wine_matcher: WineMatcher = Depends(get_wine_matcher),
    flags: FeatureFlags = Depends(get_feature_flags),
):
    """
    Progressive scan endpoint using Server-Sent Events (SSE).

    Streams wine recognition results in two phases:
    - event: phase1 — turbo-quality results from Vision API + DB matching (~3.5s)
    - event: phase2 — Gemini-enhanced results with full metadata (~6-8s)
    - event: done — stream complete

    Both phase1 and phase2 data are complete ScanResponse JSON objects.
    Phase2 is a full replacement of phase1.

    If the SSE connection drops after phase1, the client still has usable results.
    If Gemini fails, phase2 still emits with turbo-only data (graceful degradation).
    """
    # Validate content type
    if image.content_type not in Config.ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Invalid image type. Only JPEG and PNG are supported."
        )

    # Read image
    try:
        image_bytes = await image.read()
    except IOError as e:
        logger.error(f"Failed to read uploaded image: {e}")
        raise HTTPException(status_code=400, detail="Failed to read image file")

    # Convert HEIC/HEIF to JPEG
    image_bytes = convert_heic_to_jpeg(image_bytes, image.content_type)

    # Validate file size
    if len(image_bytes) > Config.MAX_IMAGE_SIZE_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"Image too large. Maximum size is {Config.MAX_IMAGE_SIZE_MB}MB."
        )

    image_id = str(uuid.uuid4())

    async def event_generator():
        pipeline = FlashNamesPipeline(
            wine_matcher=wine_matcher,
            model=f"gemini/{Config.fast_pipeline_model()}",
        )

        async for partial in pipeline.scan_progressive(image_bytes):
            phase = partial.timings.get('phase', 1)

            results, fallback = build_results_from_recognized(
                partial.recognized_wines,
                wine_matcher,
                pipeline_fallback=partial.fallback,
                flags=flags,
            )

            debug_data = None
            if debug:
                pipeline_steps = []
                for idx, rw in enumerate(partial.recognized_wines):
                    bt = rw.bottle_text
                    pipeline_steps.append(DebugPipelineStep(
                        raw_text=(bt.combined_text or "") if bt else "",
                        normalized_text=(bt.normalized_name or "") if bt else rw.wine_name,
                        bottle_index=idx,
                        final_result={
                            "wine_name": rw.wine_name,
                            "confidence": rw.confidence,
                            "source": rw.source.value,
                        },
                        included_in_results=True,
                    ))
                for fw in partial.fallback:
                    wine_name = fw.get("wine_name", "") if isinstance(fw, dict) else str(fw)
                    pipeline_steps.append(DebugPipelineStep(
                        raw_text=wine_name,
                        normalized_text=wine_name,
                        bottle_index=-1,
                        final_result=None,
                        included_in_results=False,
                    ))
                timings = partial.timings
                debug_data = DebugData(
                    pipeline_steps=pipeline_steps,
                    total_ocr_texts=timings.get('ocr_texts_count', 0),
                    bottles_detected=timings.get('vision_bottles', 0),
                    texts_matched=len(partial.recognized_wines),
                    llm_calls_made=1 if timings.get('llm_wines', 0) > 0 else 0,
                )

            response = ScanResponse(
                image_id=image_id,
                results=results,
                fallback_list=fallback,
                debug=debug_data,
            )

            data = response.model_dump_json()
            yield f"event: phase{phase}\ndata: {data}\n\n"

            logger.info(
                f"[{image_id}] SSE phase{phase}: "
                f"{len(results)} results, {len(fallback)} fallback "
                f"({partial.timings.get('total_ms', 0)}ms)"
            )

        yield f"event: done\ndata: {{}}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )
