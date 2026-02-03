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

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from PIL import Image
from pillow_heif import register_heif_opener

from ..config import Config
from ..mocks.fixtures import get_mock_response
from ..models import BoundingBox, DebugData, FallbackWine, ScanResponse, WineResult
from ..services.ocr_processor import OCRProcessor, extract_wine_names
from ..services.recognition_pipeline import RecognitionPipeline
from ..services.vision import MockVisionService, ReplayVisionService, VisionService
from ..services.wine_matcher import WineMatcher

logger = logging.getLogger(__name__)
router = APIRouter()

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
            image_id, image_bytes, use_vision_api, use_llm, debug, wine_matcher, use_vision_fixture
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

    # Step 1: Analyze image
    vision_result = vision_service.analyze(image_bytes)
    logger.info(f"[{image_id}] Vision API: {len(vision_result.objects)} bottles, {len(vision_result.text_blocks)} text blocks")

    if Config.is_dev():
        logger.debug(f"[{image_id}] Raw OCR: {vision_result.raw_text[:500] if vision_result.raw_text else 'None'}...")

    if not vision_result.objects:
        # No bottles detected - try matching raw OCR text directly
        logger.info(f"[{image_id}] No bottles detected, trying direct OCR match")
        return await _direct_ocr_response(
            image_id, vision_result, wine_matcher, use_llm, debug_mode
        )

    # Step 2: Group text to bottles and normalize
    ocr_processor = OCRProcessor()
    bottle_texts = ocr_processor.process(
        vision_result.objects,
        vision_result.text_blocks
    )

    # Step 3 & 4: Tiered recognition (fuzzy match → LLM fallback)
    # Enable debug mode if explicitly requested OR if in dev mode
    enable_debug = debug_mode or Config.is_dev()
    pipeline = get_pipeline(use_llm=use_llm, debug_mode=enable_debug)
    recognized = await pipeline.recognize(bottle_texts)

    logger.info(f"[{image_id}] Recognized {len(recognized)} wines")
    if Config.is_dev():
        for w in recognized:
            logger.debug(f"[{image_id}]   {w.wine_name}: rating={w.rating}, conf={w.confidence:.2f}, src={w.source}")

    # Build response
    results: list[WineResult] = []
    fallback: list[FallbackWine] = []

    for wine in recognized:
        if wine.confidence >= Config.VISIBILITY_THRESHOLD:
            # Add to positioned results
            results.append(WineResult(
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
                rating_source=wine.rating_source
            ))
        elif wine.rating is not None:
            # Low confidence with rating → fallback
            fallback.append(FallbackWine(
                wine_name=wine.wine_name,
                rating=wine.rating
            ))

    # Sort results by rating (wines with ratings first, then by rating value)
    results.sort(key=lambda x: (x.rating is not None, x.rating or 0), reverse=True)
    fallback.sort(key=lambda x: x.rating, reverse=True)

    logger.info(f"[{image_id}] Response: {len(results)} results, {len(fallback)} fallback")

    # Build debug data if requested or in dev mode
    debug_data = None
    if debug_mode or Config.is_dev():
        debug_data = DebugData(
            pipeline_steps=pipeline.debug_steps,
            total_ocr_texts=len(bottle_texts),
            bottles_detected=len(vision_result.objects),
            texts_matched=len([s for s in pipeline.debug_steps if s.included_in_results]),
            llm_calls_made=pipeline.llm_call_count
        )

        # Log summary table in dev mode
        if Config.is_dev():
            logger.info(f"[{image_id}] Pipeline Summary:\n{debug_data.format_summary_table()}")

    # Only include debug in response if explicitly requested
    response_debug = debug_data if debug_mode else None

    return ScanResponse(
        image_id=image_id,
        results=results,
        fallback_list=fallback,
        debug=response_debug
    )


async def _direct_ocr_response(
    image_id: str,
    vision_result,
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

    # Run pipeline
    enable_debug = debug_mode or Config.is_dev()
    pipeline = get_pipeline(use_llm=use_llm, debug_mode=enable_debug)
    recognized = await pipeline.recognize([bottle_text])

    logger.info(f"[{image_id}] Direct OCR recognized {len(recognized)} wines")

    results: list[WineResult] = []
    fallback: list[FallbackWine] = []

    for wine in recognized:
        if wine.confidence >= Config.VISIBILITY_THRESHOLD:
            results.append(WineResult(
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
                rating_source=wine.rating_source
            ))
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
