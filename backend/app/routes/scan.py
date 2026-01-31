"""
/scan endpoint for Wine Shelf Scanner.

Receives an image and returns wine detection results.
Uses tiered recognition pipeline: fuzzy match → LLM fallback.
"""

import logging
import uuid
from functools import lru_cache
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile

from ..config import Config
from ..mocks.fixtures import get_mock_response
from ..models import BoundingBox, FallbackWine, ScanResponse, WineResult
from ..services.ocr_processor import OCRProcessor, extract_wine_names
from ..services.recognition_pipeline import RecognitionPipeline
from ..services.vision import MockVisionService, VisionService
from ..services.wine_matcher import WineMatcher

logger = logging.getLogger(__name__)
router = APIRouter()


# === Dependency Injection ===


@lru_cache(maxsize=1)
def get_wine_matcher() -> WineMatcher:
    """Get or create wine matcher instance (singleton via lru_cache)."""
    return WineMatcher()


def get_pipeline(use_llm: bool = True) -> RecognitionPipeline:
    """Create recognition pipeline with specified LLM setting."""
    return RecognitionPipeline(
        wine_matcher=get_wine_matcher(),
        use_llm=use_llm
    )


# === Endpoints ===


@router.post("/scan", response_model=ScanResponse)
async def scan_shelf(
    image: UploadFile = File(..., description="Wine shelf image"),
    mock_scenario: Optional[str] = Query(None, description="Mock scenario for testing"),
    use_vision_api: bool = Query(False, description="Use real Vision API"),
    use_llm: bool = Query(True, description="Use LLM fallback for unknown wines"),
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

    # Validate file size
    if len(image_bytes) > Config.MAX_IMAGE_SIZE_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"Image too large. Maximum size is {Config.MAX_IMAGE_SIZE_MB}MB."
        )

    # Process image
    try:
        return await process_image(
            image_id, image_bytes, use_vision_api, use_llm, wine_matcher
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
    wine_matcher: WineMatcher,
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
    if use_real_api:
        vision_service = VisionService()
    else:
        vision_service = MockVisionService("full_shelf")

    # Step 1: Analyze image
    vision_result = vision_service.analyze(image_bytes)

    if not vision_result.objects:
        # No bottles detected - return fallback only
        return _fallback_response(image_id, wine_matcher)

    # Step 2: Group text to bottles and normalize
    ocr_processor = OCRProcessor()
    bottle_texts = ocr_processor.process(
        vision_result.objects,
        vision_result.text_blocks
    )

    # Step 3 & 4: Tiered recognition (fuzzy match → LLM fallback)
    pipeline = get_pipeline(use_llm=use_llm)
    recognized = await pipeline.recognize(bottle_texts)

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
                source=wine.source
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

    return ScanResponse(
        image_id=image_id,
        results=results,
        fallback_list=fallback
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
        if match:
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
