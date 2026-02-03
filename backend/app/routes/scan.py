"""
/scan endpoint for Wine Shelf Scanner.

Receives an image and returns wine detection results.
Uses tiered recognition pipeline: fuzzy match → LLM fallback.
"""

import io
import logging
import uuid
from functools import lru_cache
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from PIL import Image
from pillow_heif import register_heif_opener

from ..config import Config
from ..mocks.fixtures import get_mock_response
from ..models import BoundingBox, DebugData, FallbackWine, ScanResponse, WineResult
from ..models.debug import PipelineStats
from ..models.enums import RatingSource, WineSource
from ..services.claude_vision import get_claude_vision_service, VisionIdentifiedWine
from ..services.ocr_processor import BottleText, OCRProcessor, OCRProcessingResult, OrphanedText, extract_wine_names
from ..services.recognition_pipeline import RecognizedWine, RecognitionPipeline
from ..services.vision import MockVisionService, ReplayVisionService, VisionResult, VisionService
from ..services.wine_matcher import WineMatcher

logger = logging.getLogger(__name__)
router = APIRouter()


def _vision_to_recognized(
    vision_wine: VisionIdentifiedWine,
    bottle_text: BottleText
) -> RecognizedWine:
    """Convert Claude Vision result to RecognizedWine."""
    # Cap confidence for vision-identified wines (never top-3 emphasis)
    capped_confidence = min(vision_wine.confidence, Config.VISION_FALLBACK_CONFIDENCE_CAP)

    return RecognizedWine(
        wine_name=vision_wine.wine_name,
        rating=vision_wine.estimated_rating,
        confidence=capped_confidence,
        source=WineSource.VISION,
        identified=True,
        bottle_text=bottle_text,
        rating_source=RatingSource.LLM_ESTIMATED if vision_wine.estimated_rating else RatingSource.NONE,
        wine_type=vision_wine.wine_type,
        brand=vision_wine.brand,
        region=vision_wine.region,
        varietal=vision_wine.varietal,
        blurb=vision_wine.blurb,
    )


def _to_wine_result(wine: RecognizedWine) -> WineResult:
    """Convert RecognizedWine to WineResult for API response."""
    return WineResult(
        wine_name=wine.wine_name,
        rating=wine.rating,
        confidence=wine.confidence,
        bbox=BoundingBox(
            x=wine.bottle_text.bottle.bbox.x,
            y=wine.bottle_text.bottle.bbox.y,
            width=wine.bottle_text.bottle.bbox.width,
            height=wine.bottle_text.bottle.bbox.height
        ),
        identified=wine.identified,
        source=wine.source,
        rating_source=wine.rating_source,
        wine_type=wine.wine_type,
        brand=wine.brand,
        region=wine.region,
        varietal=wine.varietal,
        blurb=wine.blurb,
        review_count=wine.review_count,
        review_snippets=wine.review_snippets,
    )


def _process_orphaned_texts(
    orphaned_texts: list[OrphanedText],
    wine_matcher: WineMatcher
) -> list[FallbackWine]:
    """
    Process orphaned text blocks through wine matcher.

    Orphaned texts are OCR text blocks not assigned to any detected bottle.
    They may contain wine names from bottles the Vision API failed to detect.

    Args:
        orphaned_texts: List of OrphanedText with normalized wine name candidates
        wine_matcher: Wine matcher for fuzzy matching

    Returns:
        List of FallbackWine for wines matched from orphaned text
    """
    matches = []
    seen_names = set()

    for orphan in orphaned_texts:
        if not orphan.normalized_name or len(orphan.normalized_name) < 3:
            continue

        # Skip if we've already matched this name
        name_lower = orphan.normalized_name.lower()
        if name_lower in seen_names:
            continue

        # Try to match against wine database
        match = wine_matcher.match(orphan.normalized_name)
        if match and match.rating is not None:
            # Only add if confidence is reasonable (avoid false positives)
            if match.confidence >= 0.60:
                matches.append(FallbackWine(
                    wine_name=match.canonical_name,
                    rating=match.rating
                ))
                seen_names.add(name_lower)
                seen_names.add(match.canonical_name.lower())

    return matches


# Register HEIF/HEIC opener with Pillow
register_heif_opener()


# === Image Conversion ===


def convert_heic_to_jpeg(image_bytes: bytes, content_type: str) -> bytes:
    """
    Convert HEIC/HEIF images to JPEG. Pass through other formats unchanged.

    Args:
        image_bytes: Raw image bytes
        content_type: MIME type of the image

    Returns:
        JPEG bytes if HEIC/HEIF, otherwise original bytes
    """
    if content_type not in ("image/heic", "image/heif"):
        return image_bytes

    img = Image.open(io.BytesIO(image_bytes))

    # Convert to RGB (HEIC may have alpha channel)
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")

    output = io.BytesIO()
    img.save(output, format="JPEG", quality=90)
    return output.getvalue()


# === Dependency Injection ===


@lru_cache(maxsize=1)
def get_wine_matcher() -> WineMatcher:
    """Get or create wine matcher instance (singleton via lru_cache)."""
    return WineMatcher(use_sqlite=Config.use_sqlite())


def get_pipeline(use_llm: bool = True, debug_mode: bool = False) -> RecognitionPipeline:
    """Create recognition pipeline with specified LLM setting."""
    return RecognitionPipeline(
        wine_matcher=get_wine_matcher(),
        use_llm=use_llm,
        llm_provider=Config.llm_provider(),
        debug_mode=debug_mode
    )


# === Endpoints ===


@router.post("/scan", response_model=ScanResponse)
async def scan_shelf(
    image: UploadFile = File(..., description="Wine shelf image"),
    mock_scenario: Optional[str] = Query(None, description="Mock scenario for testing"),
    use_vision_api: bool = Query(True, description="Use real Vision API"),
    use_llm: bool = Query(True, description="Use LLM fallback for unknown wines"),
    use_vision_fallback: bool = Query(True, description="Use Claude Vision for unmatched bottles"),
    debug: bool = Query(False, description="Include pipeline debug info in response"),
    use_vision_fixture: Optional[str] = Query(None, description="Path to captured Vision API response fixture for replay"),
    wine_matcher: WineMatcher = Depends(get_wine_matcher),
) -> ScanResponse:
    """
    Scan a wine shelf image and return detected wines with ratings.

    Args:
        image: The shelf image (JPEG or PNG)
        mock_scenario: Optional fixture name for testing (full_shelf, partial_detection, etc.)
        use_vision_api: Whether to use real Google Vision API (requires credentials)
        use_llm: Whether to use LLM fallback for OCR normalization

    Returns:
        ScanResponse with detected wines and fallback list
    """
    # Validate content type
    if image.content_type not in Config.ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Invalid image type. Only JPEG and PNG are supported."
        )

    # Generate unique image ID
    image_id = str(uuid.uuid4())

    # Check if we should use mocks
    use_mocks = Config.use_mocks()

    if mock_scenario:
        # Explicit mock scenario requested
        return get_mock_response(image_id, mock_scenario)

    if use_mocks and not use_vision_api:
        # Default to mock response
        return get_mock_response(image_id, "full_shelf")

    # Read and validate image
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

    # Process image
    try:
        return await process_image(
            image_id, image_bytes, use_vision_api, use_llm, use_vision_fallback, debug, wine_matcher, use_vision_fixture
        )
    except ValueError as e:
        logger.warning(f"Invalid image format: {e}")
        raise HTTPException(status_code=400, detail="Invalid image format")
    except Exception as e:
        logger.error(f"Unexpected error processing image: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


async def process_image(
    image_id: str,
    image_bytes: bytes,
    use_real_api: bool,
    use_llm: bool,
    use_vision_fallback: bool,
    debug_mode: bool,
    wine_matcher: WineMatcher,
    vision_fixture: Optional[str] = None,
) -> ScanResponse:
    """
    Tiered recognition pipeline:
    1. Vision API (object detection + OCR)
    2. OCR grouping (text → bottle assignment)
    3. Enhanced fuzzy matching (rapidfuzz + phonetic)
    4. LLM fallback for low-confidence/unknown wines
    5. Response construction
    """
    # Choose vision service
    if vision_fixture:
        # Use captured fixture for deterministic replay
        vision_service = ReplayVisionService(vision_fixture)
        logger.info(f"[{image_id}] Using vision fixture: {vision_fixture}")
    elif use_real_api:
        vision_service = VisionService()
    else:
        vision_service = MockVisionService("full_shelf")

    # === Pipeline Stats Collection ===
    # Track where bottles are lost at each stage
    stats_bottles_detected = 0
    stats_bottles_with_text = 0
    stats_bottles_empty = 0
    stats_fuzzy_matched = 0
    stats_llm_validated = 0
    stats_unmatched_count = 0
    stats_vision_attempted = 0
    stats_vision_identified = 0
    stats_vision_error: Optional[str] = None

    # Step 1: Analyze image
    vision_result = vision_service.analyze(image_bytes)
    stats_bottles_detected = len(vision_result.objects)
    logger.info(f"[{image_id}] BOTTLES DETECTED: {stats_bottles_detected}")

    # Log individual bottle bboxes in debug mode
    if Config.is_dev():
        for i, obj in enumerate(vision_result.objects):
            logger.debug(f"[{image_id}]   Bottle {i}: bbox=({obj.bbox.x:.2f},{obj.bbox.y:.2f},{obj.bbox.width:.2f}x{obj.bbox.height:.2f}) conf={obj.confidence:.2f}")

    if Config.is_dev():
        logger.debug(f"[{image_id}] Raw OCR: {vision_result.raw_text[:500] if vision_result.raw_text else 'None'}...")

    if not vision_result.objects:
        # No bottles detected - try matching raw OCR text directly
        logger.info(f"[{image_id}] No bottles detected, trying direct OCR match")
        return await _direct_ocr_response(
            image_id, vision_result, wine_matcher, use_llm, debug_mode
        )

    # Step 2: Group text to bottles and normalize (also track orphaned text)
    ocr_processor = OCRProcessor()
    ocr_result = ocr_processor.process_with_orphans(
        vision_result.objects,
        vision_result.text_blocks
    )
    bottle_texts = ocr_result.bottle_texts
    orphaned_texts = ocr_result.orphaned_texts

    # Track bottles with/without text
    stats_bottles_with_text = sum(1 for bt in bottle_texts if bt.combined_text)
    stats_bottles_empty = len(bottle_texts) - stats_bottles_with_text
    logger.info(f"[{image_id}] TEXT ASSIGNMENT: {stats_bottles_with_text} with text, {stats_bottles_empty} empty")

    if orphaned_texts:
        logger.info(f"[{image_id}] {len(orphaned_texts)} orphaned text blocks not assigned to bottles")

    # Step 3 & 4: Tiered recognition (fuzzy match → LLM fallback)
    # Always enable debug mode to collect pipeline stats
    pipeline = get_pipeline(use_llm=use_llm, debug_mode=True)
    recognized = await pipeline.recognize(bottle_texts)

    # Count matches by source
    from ..models.enums import WineSource
    stats_fuzzy_matched = sum(1 for w in recognized if w.source == WineSource.DATABASE)
    stats_llm_validated = sum(1 for w in recognized if w.source == WineSource.LLM)

    logger.info(f"[{image_id}] MATCHED: {len(recognized)} of {len(bottle_texts)} bottles (fuzzy={stats_fuzzy_matched}, llm={stats_llm_validated})")
    if Config.is_dev():
        for w in recognized:
            logger.debug(f"[{image_id}]   {w.wine_name}: rating={w.rating}, conf={w.confidence:.2f}, src={w.source}")

    # Step 5: Claude Vision fallback for unmatched bottles
    # Find bottles that weren't matched by the pipeline
    # Use id() since BottleText is not hashable
    recognized_bottle_ids = {id(w.bottle_text) for w in recognized}
    unmatched_bottles = [bt for bt in bottle_texts if id(bt) not in recognized_bottle_ids]

    # Use vision fallback if enabled both via parameter and config
    stats_unmatched_count = len(unmatched_bottles)
    enable_vision = use_vision_fallback and Config.use_vision_fallback()
    logger.info(f"[{image_id}] UNMATCHED FOR VISION: {stats_unmatched_count} bottles")

    if unmatched_bottles and enable_vision:
        stats_vision_attempted = len(unmatched_bottles)
        try:
            vision_service = get_claude_vision_service()
            vision_results = await vision_service.identify_wines(
                image_bytes=image_bytes,
                unmatched_bottles=unmatched_bottles,
                image_media_type="image/jpeg",  # We convert to JPEG earlier
            )

            # Convert vision results to RecognizedWine and add to recognized list
            for vision_wine in vision_results:
                if vision_wine.wine_name and vision_wine.bottle_index < len(unmatched_bottles):
                    bottle_text = unmatched_bottles[vision_wine.bottle_index]
                    recognized_wine = _vision_to_recognized(vision_wine, bottle_text)
                    recognized.append(recognized_wine)
                    stats_vision_identified += 1
                    logger.info(
                        f"[{image_id}] Claude Vision identified: {vision_wine.wine_name} "
                        f"(conf={vision_wine.confidence:.2f}, rating={vision_wine.estimated_rating})"
                    )

            logger.info(f"[{image_id}] VISION RESULTS: {stats_vision_identified} of {stats_vision_attempted} identified")
        except Exception as e:
            stats_vision_error = str(e)
            logger.warning(f"[{image_id}] Claude Vision fallback failed: {e}")

    # Build response
    results: list[WineResult] = []
    fallback: list[FallbackWine] = []

    for wine in recognized:
        if wine.confidence >= Config.VISIBILITY_THRESHOLD:
            # Add to positioned results
            results.append(_to_wine_result(wine))
        elif wine.rating is not None:
            # Low confidence with rating → fallback
            fallback.append(FallbackWine(
                wine_name=wine.wine_name,
                rating=wine.rating
            ))

    # Step 6: Process orphaned text blocks into fallback list
    # These are OCR texts not near any detected bottle - may be from undetected bottles
    if orphaned_texts:
        orphan_matches = _process_orphaned_texts(orphaned_texts, wine_matcher)
        if orphan_matches:
            logger.info(f"[{image_id}] Matched {len(orphan_matches)} wines from orphaned text")
            # Add to fallback, avoiding duplicates
            existing_names = {f.wine_name.lower() for f in fallback}
            existing_names.update(r.wine_name.lower() for r in results)
            for match in orphan_matches:
                if match.wine_name.lower() not in existing_names:
                    fallback.append(match)
                    existing_names.add(match.wine_name.lower())

    # Sort results by rating (wines with ratings first, then by rating value)
    results.sort(key=lambda x: (x.rating is not None, x.rating or 0), reverse=True)
    fallback.sort(key=lambda x: x.rating, reverse=True)

    stats_final_results = len(results)
    logger.info(f"[{image_id}] Response: {stats_final_results} results, {len(fallback)} fallback")

    # Log pipeline summary
    logger.info(
        f"[{image_id}] === PIPELINE SUMMARY ===\n"
        f"  Bottles detected by Vision API: {stats_bottles_detected}\n"
        f"  Bottles with OCR text: {stats_bottles_with_text} ({stats_bottles_empty} empty)\n"
        f"  Fuzzy matches (high conf): {stats_fuzzy_matched}\n"
        f"  LLM validated/identified: {stats_llm_validated}\n"
        f"  Unmatched bottles: {stats_unmatched_count}\n"
        f"  Claude Vision attempted: {stats_vision_attempted}\n"
        f"  Claude Vision identified: {stats_vision_identified}"
        + (f" (ERROR: {stats_vision_error})" if stats_vision_error else "") +
        f"\n  Final results: {stats_final_results}"
    )

    # Build pipeline stats
    pipeline_stats = PipelineStats(
        bottles_detected=stats_bottles_detected,
        bottles_with_text=stats_bottles_with_text,
        bottles_empty=stats_bottles_empty,
        fuzzy_matched=stats_fuzzy_matched,
        llm_validated=stats_llm_validated,
        unmatched_count=stats_unmatched_count,
        vision_attempted=stats_vision_attempted,
        vision_identified=stats_vision_identified,
        vision_error=stats_vision_error,
        final_results=stats_final_results
    )

    # Always build debug data (pipeline_stats is always useful)
    debug_data = DebugData(
        pipeline_steps=pipeline.debug_steps,
        total_ocr_texts=len(bottle_texts),
        bottles_detected=stats_bottles_detected,
        texts_matched=len([s for s in pipeline.debug_steps if s.included_in_results]),
        llm_calls_made=pipeline.llm_call_count,
        pipeline_stats=pipeline_stats
    )

    return ScanResponse(
        image_id=image_id,
        results=results,
        fallback_list=fallback,
        debug=debug_data
    )


async def _direct_ocr_response(
    image_id: str,
    vision_result: VisionResult,
    wine_matcher: WineMatcher,
    use_llm: bool,
    debug_mode: bool
) -> ScanResponse:
    """
    Handle case where no bottles detected but OCR text exists.

    Creates a synthetic bottle from all the text and tries to match it.
    This handles close-up label shots where bottle shape isn't visible.
    """
    from ..services.ocr_processor import BottleText
    from ..services.vision import DetectedObject, BoundingBox as VisionBBox

    # Combine all text blocks
    all_text = ' '.join([tb.text for tb in vision_result.text_blocks])
    logger.info(f"[{image_id}] Direct OCR text: {all_text[:100]}...")

    if not all_text or len(all_text.strip()) < 3:
        return _fallback_response(image_id, wine_matcher)

    # Create a synthetic bottle covering the whole image
    synthetic_bottle = DetectedObject(
        name="Bottle",
        confidence=0.9,  # Slightly lower since we didn't detect it
        bbox=VisionBBox(x=0.0, y=0.0, width=1.0, height=1.0)
    )

    # Process OCR
    ocr_processor = OCRProcessor()
    normalized_text = ocr_processor._normalize_text(all_text)

    if not normalized_text or len(normalized_text.strip()) < 3:
        return _fallback_response(image_id, wine_matcher)

    # Create bottle text
    bottle_text = BottleText(
        bottle=synthetic_bottle,
        text_fragments=[all_text],
        combined_text=all_text,
        normalized_name=normalized_text
    )

    # Run pipeline (always enable debug for stats collection)
    pipeline = get_pipeline(use_llm=use_llm, debug_mode=True)
    recognized = await pipeline.recognize([bottle_text])

    logger.info(f"[{image_id}] Direct OCR recognized {len(recognized)} wines")

    results: list[WineResult] = []
    fallback: list[FallbackWine] = []

    for wine in recognized:
        if wine.confidence >= Config.VISIBILITY_THRESHOLD:
            results.append(_to_wine_result(wine))
        elif wine.rating is not None:
            fallback.append(FallbackWine(
                wine_name=wine.wine_name,
                rating=wine.rating
            ))

    # If no results, add to fallback
    if not results and not fallback:
        return _fallback_response(image_id, wine_matcher)

    # Build debug data if requested
    debug_data = None
    if debug_mode:
        debug_data = DebugData(
            pipeline_steps=pipeline.debug_steps,
            total_ocr_texts=1,
            bottles_detected=0,
            texts_matched=len([s for s in pipeline.debug_steps if s.included_in_results]),
            llm_calls_made=pipeline.llm_call_count
        )

    return ScanResponse(
        image_id=image_id,
        results=results,
        fallback_list=fallback,
        debug=debug_data if debug_mode else None
    )


def _fallback_response(image_id: str, wine_matcher: WineMatcher) -> ScanResponse:
    """Return empty results with common wines in fallback."""
    # Add some popular wines to fallback
    popular_wines = [
        "Caymus Cabernet Sauvignon",
        "Opus One",
        "La Crema Sonoma Coast Pinot Noir",
        "Kendall-Jackson Vintner's Reserve Chardonnay",
    ]

    fallback = []
    for name in popular_wines:
        match = wine_matcher.match(name)
        if match and match.rating is not None:
            fallback.append(FallbackWine(
                wine_name=match.canonical_name,
                rating=match.rating
            ))

    return ScanResponse(
        image_id=image_id,
        results=[],
        fallback_list=fallback
    )


@router.post("/scan/debug")
async def scan_debug(
    image: UploadFile = File(..., description="Wine shelf image"),
) -> dict:
    """
    Debug endpoint: raw OCR results + wine name extraction.

    Returns raw OCR text from Vision API and extracted wine names.
    Use this to test OCR quality before full pipeline processing.
    """
    # Validate content type
    if image.content_type not in Config.ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Invalid image type. Only JPEG and PNG are supported."
        )

    try:
        image_bytes = await image.read()
    except IOError as e:
        logger.error(f"Failed to read uploaded image for debug: {e}")
        raise HTTPException(status_code=400, detail="Failed to read image file")

    # Convert HEIC/HEIF to JPEG
    image_bytes = convert_heic_to_jpeg(image_bytes, image.content_type)

    # Validate file size
    if len(image_bytes) > Config.MAX_IMAGE_SIZE_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"Image too large. Maximum size is {Config.MAX_IMAGE_SIZE_MB}MB."
        )

    try:
        vision_service = VisionService()
        result = vision_service.analyze(image_bytes)

        # Extract wine names from raw OCR text
        wine_names = extract_wine_names(result.raw_text)

        return {
            "labels_identified": len(wine_names),
            "wine_names": wine_names,
            "raw_ocr_text": result.raw_text,
            "bottles_detected": len(result.objects),
        }
    except ValueError as e:
        logger.warning(f"Invalid image in debug endpoint: {e}")
        raise HTTPException(status_code=400, detail="Invalid image format")
    except Exception as e:
        logger.error(f"Debug endpoint error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


@router.post("/preview")
async def preview_image(
    image: UploadFile = File(..., description="Image to convert for preview"),
) -> Response:
    """
    Convert an image to JPEG for preview display.

    Useful for HEIC files that browsers can't display natively.
    Returns the image as JPEG bytes with appropriate content type.
    """
    # Validate content type
    if image.content_type not in Config.ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Invalid image type."
        )

    try:
        image_bytes = await image.read()
    except IOError as e:
        logger.error(f"Failed to read uploaded image for preview: {e}")
        raise HTTPException(status_code=400, detail="Failed to read image file")

    # Validate file size
    if len(image_bytes) > Config.MAX_IMAGE_SIZE_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"Image too large. Maximum size is {Config.MAX_IMAGE_SIZE_MB}MB."
        )

    try:
        # Convert to JPEG (handles HEIC/HEIF, passes through JPEG/PNG)
        img = Image.open(io.BytesIO(image_bytes))

        # Convert to RGB if needed
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")

        # Save as JPEG
        output = io.BytesIO()
        img.save(output, format="JPEG", quality=85)
        jpeg_bytes = output.getvalue()

        return Response(
            content=jpeg_bytes,
            media_type="image/jpeg",
            headers={"Cache-Control": "no-cache"}
        )
    except Exception as e:
        logger.error(f"Failed to convert image for preview: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail="Failed to process image")


@router.get("/cache/stats")
async def cache_stats():
    """
    Get cache statistics for monitoring.

    Returns stats for:
    - Vision API response cache (if enabled)
    - LLM rating cache
    """
    from ..services.vision_cache import get_vision_cache
    from ..services.llm_rating_cache import get_llm_rating_cache

    return {
        "vision_cache": get_vision_cache().get_stats(),
        "llm_rating_cache": get_llm_rating_cache().get_stats(),
    }
